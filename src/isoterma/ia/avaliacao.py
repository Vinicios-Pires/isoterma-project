"""Benchmark de LLMs: perguntas com resposta conhecida, corrigidas automaticamente.

As perguntas são geradas a partir da própria simulação: as respostas esperadas saem do motor
e do gabarito de incidentes, que o agente não enxerga. Assim a avaliação vale para qualquer
seed e mede o que importa no produto: achar fatos, investigar uma janela de tempo e
diagnosticar a causa de uma anomalia.

Há duas versões. A v1 pergunta pelo alvo do incidente ("o que aconteceu com o sensor X?"), o
que já entrega metade do diagnóstico. A v2 pergunta sempre pelo rack, para que o modelo descubra
sozinho qual sensor ou CRAC explica o que aconteceu, tem controles de todos os tipos e uma
pergunta de descoberta sem pista nenhuma ("quais incidentes houve no dia X?").
"""

import json
import re
import statistics
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from isoterma import __version__
from isoterma.ia.agente import Agente
from isoterma.ia.provedores.base import ErroProvedor, Provedor
from isoterma.ia.tipos import Uso
from isoterma.motor import Hall
from isoterma.simulador.esquema import FAIXA_ASHRAE_C

Tipo = Literal["numero", "texto", "conjunto", "opcao", "horario", "incidentes"]
Versao = Literal["v1", "v2"]
VERSOES: tuple[Versao, ...] = ("v1", "v2")

CATEGORIAS_DIAGNOSTICO = {
    "falha_crac": "falha_crac",
    "super_refrigeracao": "super_refrigeracao",
    "rack_sobrecarregado": "sobrecarga",
    "recirculacao": "recirculacao",
    "sensor_congelado": "defeito_sensor",
    "sensor_deriva": "defeito_sensor",
    "sensor_picos": "defeito_sensor",
    "sensor_sem_leitura": "defeito_sensor",
}
OPCOES_DIAGNOSTICO = (
    "falha_crac",
    "super_refrigeracao",
    "sobrecarga",
    "recirculacao",
    "defeito_sensor",
    "normal",
)

INSTRUCAO_AVALIACAO = (
    "Esta pergunta faz parte de uma avaliação automática. Responda normalmente e, no fim, "
    "escreva uma última linha exatamente neste formato: RESPOSTA: <valor>\n{formato}"
)


@dataclass(frozen=True)
class Questao:
    id: str
    categoria: Literal["fatos", "investigacao", "diagnostico", "descoberta"]
    pergunta: str
    formato: str
    tipo: Tipo
    esperado: Any
    tolerancia: float = 0.0


# --- geração das perguntas ------------------------------------------------------------------


def _local(hall: Hall, instante: datetime) -> str:
    return f"{instante.astimezone(hall.fuso):%d/%m às %H:%M}"


def _escalar(hall: Hall, sql: str) -> Any:
    return hall.consultar(sql).tabela.column(0)[0].as_py()


def _questoes_de_fatos(hall: Hall) -> list[Questao]:
    resumo = hall.resumo()
    racks = hall.consultar(
        "SELECT rack_id, zona_crac, potencia_nominal_kw FROM racks ORDER BY rack_id"
    ).linhas()
    no_meio = racks[len(racks) // 2]
    mais_potente = max(racks, key=lambda r: r["potencia_nominal_kw"])
    com_nulos = _escalar(
        hall,
        "SELECT count(DISTINCT sensor_id) FROM leituras WHERE valor IS NULL",
    )
    numero = "O valor deve ser só o número, sem unidade."
    return [
        Questao("racks", "fatos", "Quantos racks há no hall?", numero, "numero", len(racks)),
        Questao(
            "zona",
            "fatos",
            f"Qual CRAC refrigera principalmente o rack {no_meio['rack_id']}?",
            "O valor deve ser o identificador do CRAC, como CRAC-01.",
            "texto",
            no_meio["zona_crac"],
        ),
        Questao(
            "potencia_nominal",
            "fatos",
            "Qual rack tem a maior potência nominal?",
            "O valor deve ser o identificador do rack, como C-07.",
            "texto",
            mais_potente["rack_id"],
        ),
        Questao(
            "media_entrada",
            "fatos",
            "Qual foi a temperatura média de entrada dos racks no período inteiro, em °C?",
            numero + " Use uma casa decimal.",
            "numero",
            resumo["por_tipo"]["temp_entrada"]["media"],
            tolerancia=0.15,
        ),
        Questao(
            "potencia_total",
            "fatos",
            "Qual foi a potência média total do hall no período, em kW?",
            numero,
            "numero",
            resumo["potencia_media_total_kw"],
            tolerancia=max(1.0, resumo["potencia_media_total_kw"] * 0.01),
        ),
        Questao(
            "sensores_sem_leitura",
            "fatos",
            "Quantos sensores ficaram sem leitura em algum momento do período?",
            numero,
            "numero",
            com_nulos,
        ),
    ]


def _questoes_de_investigacao(hall: Hall, gabarito: Hall) -> list[Questao]:
    falhas = gabarito.consultar(
        "SELECT alvo, inicio, fim FROM incidentes WHERE tipo = 'falha_crac' "
        "ORDER BY intensidade DESC, inicio LIMIT 1"
    ).linhas()
    if not falhas:
        return []
    falha = falhas[0]
    # Janela redonda em volta da falha, no horário local, como uma pessoa perguntaria.
    inicio = falha["inicio"].astimezone(hall.fuso).replace(minute=0, second=0) - timedelta(hours=1)
    fim = falha["fim"].astimezone(hall.fuso).replace(minute=0, second=0) + timedelta(hours=2)
    fora = hall.fora_da_faixa(inicio, fim).to_pylist()

    # Racks cuja passagem de 27 °C se explica por defeito de sensor não contam: a pergunta
    # pede eventos térmicos reais.
    com_defeito = {
        linha["alvo"].split("/")[0]
        for linha in gabarito.consultar(
            f"""
            SELECT alvo FROM incidentes
            WHERE alvo_tipo = 'sensor' AND inicio < '{fim.astimezone(UTC).isoformat()}'
              AND fim > '{inicio.astimezone(UTC).isoformat()}'
            """
        ).linhas()
    }
    quentes = sorted(
        r["rack_id"] for r in fora if r["minutos_acima"] and r["rack_id"] not in com_defeito
    )
    if not quentes:
        return []
    primeira = min(r["primeira_vez"] for r in fora if r["rack_id"] in quentes).astimezone(hall.fuso)
    janela = f"entre {inicio:%d/%m %H:%M} e {fim:%d/%m %H:%M} (horário local)"
    return [
        Questao(
            "racks_quentes",
            "investigacao",
            f"Quais racks tiveram a entrada acima de {FAIXA_ASHRAE_C[1]:g} °C {janela} por um "
            "evento térmico real? Desconsidere defeitos de sensor.",
            "O valor deve ser a lista dos racks separados por vírgula, como A-01, A-02.",
            "conjunto",
            quentes,
            # Racks no limite de 27 °C tornam o conjunto exato rígido demais: vale Jaccard ≥ 0,85.
            tolerancia=0.85,
        ),
        Questao(
            "primeira_vez",
            "investigacao",
            f"{janela.capitalize()}, a que horas a entrada de algum rack passou de "
            f"{FAIXA_ASHRAE_C[1]:g} °C pela primeira vez?",
            "O valor deve ser o horário local no formato HH:MM.",
            "horario",
            f"{primeira:%H:%M}",
            tolerancia=3,
        ),
    ]


def _questoes_de_diagnostico(hall: Hall, gabarito: Hall, controles: int) -> list[Questao]:
    incidentes = gabarito.consultar(
        "SELECT incidente_id, tipo, alvo_tipo, alvo, inicio, fim FROM incidentes ORDER BY inicio"
    ).linhas()
    formato = f"O valor deve ser uma destas opções: {', '.join(OPCOES_DIAGNOSTICO)}."
    nomes = {"crac": "o", "rack": "o rack", "sensor": "o sensor"}

    questoes: list[Questao] = []
    vistos: set[str] = set()
    for inc in incidentes:
        if inc["tipo"] in vistos:
            continue
        vistos.add(inc["tipo"])
        artigo = nomes[inc["alvo_tipo"]]
        questoes.append(
            Questao(
                f"diagnostico_{inc['tipo']}",
                "diagnostico",
                f"O que aconteceu com {artigo} {inc['alvo']} entre {_local(hall, inc['inicio'])} e "
                f"{_local(hall, inc['fim'])} (horário local)?",
                formato,
                "opcao",
                CATEGORIAS_DIAGNOSTICO[inc["tipo"]],
            )
        )

    questoes += _controles(hall, gabarito, incidentes, controles, formato, "O que aconteceu com o")
    return questoes


def _afeta(inc: dict[str, Any], rack: dict[str, Any], inicio: datetime, fim: datetime) -> bool:
    """O incidente atinge o rack (ele, um sensor dele ou o CRAC da zona) perto da janela?"""
    alvo = inc["alvo"]
    no_rack = alvo in (rack["rack_id"], rack["zona_crac"]) or alvo.startswith(rack["rack_id"] + "/")
    margem = timedelta(hours=1)
    return no_rack and inc["inicio"] < fim + margem and inc["fim"] > inicio - margem


def _controles(
    hall: Hall,
    gabarito: Hall,
    incidentes: list[dict[str, Any]],
    quantidade: int,
    formato: str,
    abertura: str,
) -> list[Questao]:
    """Racks e janelas sem nenhum incidente; um modelo que vê problema em tudo erra estas."""
    racks = gabarito.consultar("SELECT rack_id, zona_crac FROM racks ORDER BY rack_id").linhas()
    duracao = timedelta(hours=3)
    # Janelas espalhadas pelo período, alternando os racks; vale para simulações de 1 dia ou
    # de 1 mês.
    passo = max(duracao, (gabarito.fim - gabarito.inicio) / (4 * quantidade + 1))
    janelas = []
    inicio_janela = gabarito.inicio + passo / 2
    while inicio_janela + duracao <= gabarito.fim:
        janelas.append(inicio_janela.replace(minute=0, second=0, microsecond=0))
        inicio_janela += passo
    sufixo = "" if abertura.startswith("O que") else " Se houve, qual foi a causa?"
    questoes: list[Questao] = []
    for i, inicio in enumerate(janelas):
        if len(questoes) >= quantidade:
            break
        rack, fim = racks[(i * 7) % len(racks)], inicio + duracao
        if any(_afeta(inc, rack, inicio, fim) for inc in incidentes):
            continue
        questoes.append(
            Questao(
                f"controle_{rack['rack_id']}",
                "diagnostico",
                f"{abertura} rack {rack['rack_id']} entre {_local(hall, inicio)} e "
                f"{_local(hall, fim)} (horário local)?{sufixo}",
                formato,
                "opcao",
                "normal",
            )
        )
    return questoes


def _diagnostico_por_rack(hall: Hall, gabarito: Hall, controles: int) -> list[Questao]:
    """v2: pergunta sempre pelo rack. O modelo precisa achar o sensor ou o CRAC responsável."""
    incidentes = gabarito.consultar(
        "SELECT incidente_id, tipo, alvo_tipo, alvo, inicio, fim FROM incidentes ORDER BY inicio"
    ).linhas()
    racks = {
        r["rack_id"]: r
        for r in gabarito.consultar("SELECT rack_id, zona_crac, x_m, y_m FROM racks").linhas()
    }
    cracs = {
        c["crac_id"]: c for c in gabarito.consultar("SELECT crac_id, x_m, y_m FROM cracs").linhas()
    }
    formato = f"O valor deve ser uma destas opções: {', '.join(OPCOES_DIAGNOSTICO)}."

    def rack_do(inc: dict[str, Any]) -> str | None:
        if inc["alvo_tipo"] == "rack":
            return inc["alvo"]
        if inc["alvo_tipo"] == "sensor":
            dono = inc["alvo"].split("/")[0]
            return dono if dono in racks else None  # sensores de CRAC não têm rack
        crac = cracs[inc["alvo"]]
        da_zona = [r for r in racks.values() if r["zona_crac"] == inc["alvo"]]
        if not da_zona:
            return None
        # O rack da zona mais perto do CRAC: é onde o efeito é mais claro.
        mais_perto = min(
            da_zona, key=lambda r: (r["x_m"] - crac["x_m"]) ** 2 + (r["y_m"] - crac["y_m"]) ** 2
        )
        return mais_perto["rack_id"]

    questoes: list[Questao] = []
    vistos: set[str] = set()
    for inc in incidentes:
        rack_id = rack_do(inc)
        if inc["tipo"] in vistos or rack_id is None:
            continue
        rack = racks[rack_id]
        outros = [o for o in incidentes if o["incidente_id"] != inc["incidente_id"]]
        if any(_afeta(o, rack, inc["inicio"], inc["fim"]) for o in outros):
            continue  # dois incidentes no mesmo rack ao mesmo tempo: resposta ambígua
        vistos.add(inc["tipo"])
        questoes.append(
            Questao(
                f"diagnostico_{inc['tipo']}",
                "diagnostico",
                f"Houve algo anormal no rack {rack_id} entre {_local(hall, inc['inicio'])} e "
                f"{_local(hall, inc['fim'])} (horário local)? Se houve, qual foi a causa?",
                formato,
                "opcao",
                CATEGORIAS_DIAGNOSTICO[inc["tipo"]],
            )
        )
    questoes += _controles(hall, gabarito, incidentes, controles, formato, "Houve algo anormal no")
    return questoes


def _questao_de_descoberta(hall: Hall, gabarito: Hall) -> list[Questao]:
    """v2: sem pista nenhuma, listar os incidentes de um dia inteiro."""
    incidentes = gabarito.consultar(
        "SELECT tipo, alvo_tipo, alvo, inicio, fim FROM incidentes ORDER BY inicio"
    ).linhas()
    dias: list[tuple[datetime, list[dict[str, Any]]]] = []
    dia = gabarito.inicio.astimezone(hall.fuso).replace(hour=0, minute=0, second=0, microsecond=0)
    while dia < gabarito.fim:
        seguinte = dia + timedelta(days=1)
        dias.append((dia, [i for i in incidentes if i["inicio"] < seguinte and i["fim"] > dia]))
        dia = seguinte
    # O dia mais variado, com 2 a 8 incidentes: difícil, mas possível em 12 turnos.
    candidatos = [(d, lista) for d, lista in dias if 2 <= len(lista) <= 8]
    if not candidatos:
        return []

    def variedade(candidato: tuple[datetime, list[dict[str, Any]]]) -> tuple[int, int]:
        lista = candidato[1]
        return len({CATEGORIAS_DIAGNOSTICO[i["tipo"]] for i in lista}), -len(lista)

    escolhido, lista = max(candidatos, key=variedade)
    esperado = [
        {
            "categoria": CATEGORIAS_DIAGNOSTICO[i["tipo"]],
            # Um defeito de sensor conta se o modelo apontar o sensor ou o rack dele.
            "alvos": [i["alvo"], i["alvo"].split("/")[0]]
            if i["alvo_tipo"] == "sensor"
            else [i["alvo"]],
        }
        for i in lista
    ]
    categorias = ", ".join(c for c in OPCOES_DIAGNOSTICO if c != "normal")
    return [
        Questao(
            "descoberta",
            "descoberta",
            f"Quais incidentes aconteceram no hall no dia {escolhido:%d/%m} (horário local)? "
            "Considere falhas e super-refrigeração de CRAC, sobrecargas de rack, recirculação "
            "de ar quente e defeitos de sensor.",
            "O valor deve ser a lista de incidentes no formato categoria:alvo, separados por "
            "ponto e vírgula, como falha_crac:CRAC-01; defeito_sensor:B-04/saida. Categorias: "
            f"{categorias}. O alvo é o CRAC, o rack ou o sensor. Se não houve nenhum, responda "
            "nenhum.",
            "incidentes",
            esperado,
            tolerancia=0.7,  # F1 mínimo entre os incidentes apontados e os do gabarito
        )
    ]


def gerar_questoes(diretorio: Path, *, versao: Versao = "v2") -> list[Questao]:
    with Hall(diretorio, ocultar_gabarito=True) as hall, Hall(diretorio) as gabarito:
        comuns = _questoes_de_fatos(hall) + _questoes_de_investigacao(hall, gabarito)
        if versao == "v1":
            return comuns + _questoes_de_diagnostico(hall, gabarito, controles=2)
        return (
            comuns
            + _diagnostico_por_rack(hall, gabarito, controles=3)
            + _questao_de_descoberta(hall, gabarito)
        )


# --- correção -------------------------------------------------------------------------------


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", sem_acento.strip().strip(".`*\"'").lower())


def extrair_resposta(texto: str) -> str | None:
    """A última linha ``RESPOSTA: ...`` do texto, sem formatação markdown."""
    achados = re.findall(
        r"^[\s*_>#-]*RESPOSTA\s*:\s*(.+?)\s*$", texto, re.IGNORECASE | re.MULTILINE
    )
    return achados[-1].strip("*_` ") if achados else None


def _numero(texto: str) -> float | None:
    achado = re.search(r"-?\d[\d.]*(?:,\d+)?|-?\d+(?:\.\d+)?", texto)
    if not achado:
        return None
    bruto = achado.group(0)
    if "," in bruto:  # padrão brasileiro: 1.234,5
        bruto = bruto.replace(".", "").replace(",", ".")
    elif bruto.count(".") > 1 or re.fullmatch(r"-?\d{1,3}(\.\d{3})+", bruto):
        bruto = bruto.replace(".", "")  # 1.020 escrito como milhar
    try:
        return float(bruto)
    except ValueError:
        return None


def _f1_incidentes(valor: str, esperado: list[dict[str, Any]]) -> float:
    """F1 entre os incidentes apontados (``categoria:alvo``) e os do gabarito."""
    apontados: list[tuple[str, str]] = []
    if _normalizar(valor) not in ("nenhum", "nenhum incidente"):
        for item in re.split(r"[;\n]+", valor):
            categoria, _, alvo = item.partition(":")
            if alvo.strip():
                apontados.append((_normalizar(categoria).replace(" ", "_"), _normalizar(alvo)))
    encontrados: set[int] = set()
    acertos = 0
    for categoria, alvo in apontados:
        for i, inc in enumerate(esperado):
            alvos = {_normalizar(a) for a in inc["alvos"]}
            if i not in encontrados and inc["categoria"] == categoria and alvo in alvos:
                encontrados.add(i)
                acertos += 1
                break
    if not apontados and not esperado:
        return 1.0
    precisao = acertos / len(apontados) if apontados else 0.0
    cobertura = len(encontrados) / len(esperado) if esperado else 0.0
    return 2 * precisao * cobertura / (precisao + cobertura) if precisao + cobertura else 0.0


def corrigir(questao: Questao, texto: str) -> tuple[bool, str | None]:
    """Devolve (acertou, valor extraído da resposta)."""
    valor = extrair_resposta(texto)
    if valor is None:
        return False, None
    match questao.tipo:
        case "numero":
            numero = _numero(valor)
            return numero is not None and abs(
                numero - questao.esperado
            ) <= questao.tolerancia, valor
        case "texto":
            return _normalizar(valor) == _normalizar(str(questao.esperado)), valor
        case "opcao":
            return _normalizar(valor).replace(" ", "_") == questao.esperado, valor
        case "conjunto":
            itens = {_normalizar(p) for p in re.split(r"[,;\s]+", valor) if p.strip()} - {"e"}
            esperado = {_normalizar(e) for e in questao.esperado}
            jaccard = len(itens & esperado) / len(itens | esperado) if itens | esperado else 1.0
            return jaccard >= (questao.tolerancia or 1.0), valor
        case "horario":
            achado = re.search(r"(\d{1,2})[:h](\d{2})", valor)
            if not achado:
                return False, valor
            minutos = int(achado.group(1)) * 60 + int(achado.group(2))
            hora, minuto = map(int, str(questao.esperado).split(":"))
            diferenca = abs(minutos - (hora * 60 + minuto))
            return min(diferenca, 1440 - diferenca) <= questao.tolerancia, valor
        case "incidentes":
            f1 = _f1_incidentes(valor, questao.esperado)
            return f1 >= questao.tolerancia, f"{valor} (F1 {f1:.2f})"


# --- execução -------------------------------------------------------------------------------


@dataclass
class Tentativa:
    questao: str
    provedor: str
    modelo: str
    acertou: bool
    obtido: str | None
    esperado: Any
    segundos: float = 0.0
    turnos: int = 0
    ferramentas: int = 0
    uso: dict[str, int] = field(default_factory=dict)
    custo_usd: float | None = None
    parada: str = ""
    erro: str | None = None
    resposta: str = ""


@dataclass
class ResultadoAvaliacao:
    simulacao: str
    gerado_em: str
    isoterma: str
    questoes: list[dict[str, Any]]
    tentativas: list[Tentativa]
    versao: str = "v1"  # resultados gravados antes da v2 não têm o campo

    def salvar(self, caminho: Path) -> None:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def carregar(cls, caminho: Path) -> ResultadoAvaliacao:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        dados["tentativas"] = [Tentativa(**t) for t in dados["tentativas"]]
        return cls(**dados)


def avaliar(
    diretorio: Path,
    provedores: Sequence[Provedor],
    *,
    versao: Versao = "v2",
    questoes: Sequence[Questao] | None = None,
    aviso: Callable[[str], None] | None = None,
) -> ResultadoAvaliacao:
    questoes = list(questoes) if questoes is not None else gerar_questoes(diretorio, versao=versao)
    avisar = aviso or (lambda _: None)
    tentativas: list[Tentativa] = []
    with Hall(diretorio, ocultar_gabarito=True) as hall:
        for provedor in provedores:
            agente = Agente(hall, provedor)
            for questao in questoes:
                tentativa = Tentativa(
                    questao.id, provedor.nome, provedor.modelo, False, None, questao.esperado
                )
                try:
                    resposta = agente.perguntar(
                        questao.pergunta,
                        instrucao_extra=INSTRUCAO_AVALIACAO.format(formato=questao.formato),
                    )
                except ErroProvedor as erro:
                    tentativa.erro = str(erro)
                    tentativas.append(tentativa)
                    avisar(f"{provedor.nome:<7} {questao.id:<32} erro: {erro}")
                    continue
                acertou, obtido = corrigir(questao, resposta.texto)
                tentativa.acertou, tentativa.obtido = acertou, obtido
                tentativa.segundos = resposta.segundos
                tentativa.turnos = resposta.turnos
                tentativa.ferramentas = len(resposta.passos)
                tentativa.uso = asdict(resposta.uso)
                tentativa.custo_usd = resposta.custo_usd
                tentativa.parada = resposta.parada.value
                tentativa.resposta = resposta.texto
                tentativas.append(tentativa)
                marca = (
                    "acertou"
                    if acertou
                    else f"errou (obteve {obtido!r}, esperado {questao.esperado!r})"
                )
                avisar(f"{provedor.nome:<7} {questao.id:<32} {resposta.segundos:6.1f} s  {marca}")
    return ResultadoAvaliacao(
        simulacao=diretorio.name,
        gerado_em=datetime.now(UTC).isoformat(timespec="seconds"),
        isoterma=__version__,
        questoes=[asdict(q) for q in questoes],
        tentativas=tentativas,
        versao=versao,
    )


# --- relatório ------------------------------------------------------------------------------

NOMES_CATEGORIA = {
    "fatos": "Fatos",
    "investigacao": "Investigação",
    "diagnostico": "Diagnóstico",
    "descoberta": "Descoberta",
}
SOBRE_VERSAO = {
    "v2": (
        "Pergunta sempre pelo rack (*houve algo anormal no rack X?*): o modelo precisa descobrir "
        "sozinho se a causa é um sensor com defeito, o CRAC da zona ou o próprio rack. Tem três "
        "controles sem incidente e uma pergunta de descoberta sem pista nenhuma (*quais "
        "incidentes houve no dia X?*), corrigida pelo F1 entre os incidentes apontados e os do "
        "gabarito (mínimo de 0,7)."
    ),
    "v1": (
        "Primeira versão, mantida como registro. Perguntava pelo alvo do incidente (*o que "
        "aconteceu com o sensor X?*), o que já entregava metade do diagnóstico, e o modelo mais "
        "barato acertou tudo. Por isso foi substituída pela v2."
    ),
}


def _secao(resultado: ResultadoAvaliacao, numero: Callable[..., str]) -> list[str]:
    categorias = {q["id"]: q["categoria"] for q in resultado.questoes}
    presentes = [c for c in NOMES_CATEGORIA if c in categorias.values()]
    por_modelo: dict[tuple[str, str], list[Tentativa]] = {}
    for t in resultado.tentativas:
        por_modelo.setdefault((t.provedor, t.modelo), []).append(t)

    linhas = [
        f"## Versão {resultado.versao[1:]}: {len(resultado.questoes)} perguntas",
        "",
        SOBRE_VERSAO.get(resultado.versao, ""),
        "",
        f"Simulação `{resultado.simulacao}`, executada em "
        f"{datetime.fromisoformat(resultado.gerado_em):%d/%m/%Y}.",
        "",
        "| Provedor | Modelo | Acerto | "
        + " | ".join(NOMES_CATEGORIA[c] for c in presentes)
        + " | Tempo médio | Ferramentas por pergunta | Custo total |",
        "|---|---|--:|" + "--:|" * len(presentes) + "--:|--:|--:|",
    ]
    for (provedor, modelo), tentativas in por_modelo.items():

        def taxa(grupo: list[Tentativa]) -> str:
            return f"{sum(t.acertou for t in grupo)}/{len(grupo)}" if grupo else "—"

        custos = [t.custo_usd for t in tentativas if t.custo_usd is not None]
        custo = (
            f"US$ {numero(sum(custos), 4)}" if len(custos) == len(tentativas) else "não estimado"
        )
        por_categoria = " | ".join(
            taxa([t for t in tentativas if categorias.get(t.questao) == c]) for c in presentes
        )
        linhas.append(
            f"| {provedor} | `{modelo}` | **{taxa(tentativas)}** | {por_categoria} "
            f"| {numero(statistics.mean(t.segundos for t in tentativas), 1)} s "
            f"| {numero(statistics.mean(t.ferramentas for t in tentativas), 1)} | {custo} |"
        )

    linhas += ["", "<details><summary>Pergunta a pergunta</summary>", ""]
    for q in resultado.questoes:
        linhas += [
            f"**{q['id']}** ({NOMES_CATEGORIA[q['categoria']].lower()}): {q['pergunta']}",
            "",
            f"Esperado: `{q['esperado']}`",
            "",
        ]
        for t in resultado.tentativas:
            if t.questao == q["id"]:
                marca = "✅" if t.acertou else ("💥 " + t.erro if t.erro else "❌")
                linhas.append(
                    f"- {marca} {t.provedor} `{t.modelo}`: `{t.obtido}` "
                    f"({numero(t.segundos, 1)} s, {t.ferramentas} ferramentas)"
                )
        linhas.append("")
    uso = sum((Uso(**t.uso) for t in resultado.tentativas if t.uso), Uso())
    linhas += [
        "</details>",
        "",
        f"Tokens no total: {numero(uso.entrada)} de entrada, {numero(uso.cache_leitura)} lidos do "
        f"cache e {numero(uso.saida)} de saída.",
        "",
    ]
    return linhas


def gerar_relatorio(resultados: ResultadoAvaliacao | Sequence[ResultadoAvaliacao]) -> str:
    """Relatório de uma ou mais avaliações; a versão mais nova aparece primeiro."""
    from isoterma.terminal import numero

    lista = [resultados] if isinstance(resultados, ResultadoAvaliacao) else list(resultados)
    lista.sort(key=lambda r: (r.versao, r.gerado_em), reverse=True)
    linhas = [
        "# Avaliação da IA",
        "",
        "<!-- Gerado por `isoterma relatorio-ia`. Não edite à mão: rode a avaliação de novo. -->",
        "",
        "As perguntas e as respostas esperadas são geradas a partir dos dados e do gabarito de "
        "incidentes, que o agente não enxerga. Cada resposta é corrigida automaticamente pela "
        "última linha `RESPOSTA:` que a avaliação pede ao agente. Detalhes em [IA.md](IA.md).",
        "",
    ]
    for resultado in lista:
        linhas += _secao(resultado, numero)
    return "\n".join(linhas)
