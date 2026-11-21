"""Benchmark de LLMs: perguntas com resposta conhecida, corrigidas automaticamente.

As perguntas são geradas a partir da própria simulação: as respostas esperadas saem do motor
e do gabarito de incidentes, que o agente não enxerga. Assim a avaliação vale para qualquer
seed e mede o que importa no produto: achar fatos, investigar uma janela de tempo e
diagnosticar a causa de uma anomalia.
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

Tipo = Literal["numero", "texto", "conjunto", "opcao", "horario"]

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
    categoria: Literal["fatos", "investigacao", "diagnostico"]
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

    # Controles: racks e janelas sem nenhum incidente no rack, nos sensores dele ou no CRAC
    # da zona. Um modelo que vê problema em tudo erra estas.
    racks = gabarito.consultar("SELECT rack_id, zona_crac FROM racks ORDER BY rack_id").linhas()
    duracao = timedelta(hours=3)
    # Janelas espalhadas pelo período, alternando os racks; vale para simulações de 1 dia ou
    # de 1 mês.
    passo = max(duracao, (gabarito.fim - gabarito.inicio) / (4 * controles + 1))
    janelas = []
    inicio_janela = gabarito.inicio + passo / 2
    while inicio_janela + duracao <= gabarito.fim:
        janelas.append(inicio_janela.replace(minute=0, second=0, microsecond=0))
        inicio_janela += passo
    combinacoes = [(racks[(i * 7) % len(racks)], janela) for i, janela in enumerate(janelas)]
    for rack, inicio in combinacoes:
        if len(questoes) >= len(vistos) + controles:
            break
        fim = inicio + duracao
        afetado = any(
            (
                inc["alvo"] in (rack["rack_id"], rack["zona_crac"])
                or inc["alvo"].startswith(rack["rack_id"] + "/")
            )
            and inc["inicio"] < fim + timedelta(hours=1)
            and inc["fim"] > inicio - timedelta(hours=1)
            for inc in incidentes
        )
        if afetado:
            continue
        questoes.append(
            Questao(
                f"controle_{rack['rack_id']}",
                "diagnostico",
                f"O que aconteceu com o rack {rack['rack_id']} entre {_local(hall, inicio)} e "
                f"{_local(hall, fim)} (horário local)?",
                formato,
                "opcao",
                "normal",
            )
        )
    return questoes


def gerar_questoes(diretorio: Path, *, controles: int = 2) -> list[Questao]:
    with Hall(diretorio, ocultar_gabarito=True) as hall, Hall(diretorio) as gabarito:
        return (
            _questoes_de_fatos(hall)
            + _questoes_de_investigacao(hall, gabarito)
            + _questoes_de_diagnostico(hall, gabarito, controles)
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
    questoes: Sequence[Questao] | None = None,
    aviso: Callable[[str], None] | None = None,
) -> ResultadoAvaliacao:
    questoes = list(questoes) if questoes is not None else gerar_questoes(diretorio)
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
    )


# --- relatório ------------------------------------------------------------------------------


def gerar_relatorio(resultado: ResultadoAvaliacao) -> str:
    from isoterma.terminal import numero

    categorias = {q["id"]: q["categoria"] for q in resultado.questoes}
    por_modelo: dict[tuple[str, str], list[Tentativa]] = {}
    for t in resultado.tentativas:
        por_modelo.setdefault((t.provedor, t.modelo), []).append(t)

    linhas = [
        "# Avaliação da IA",
        "",
        "<!-- Gerado por `isoterma relatorio-ia`. Não edite à mão: rode a avaliação de novo. -->",
        "",
        f"Simulação `{resultado.simulacao}`, {len(resultado.questoes)} perguntas, executada em "
        f"{datetime.fromisoformat(resultado.gerado_em):%d/%m/%Y}. As perguntas e as respostas "
        "esperadas são geradas a partir dos dados e do gabarito de incidentes, que o agente não "
        "enxerga. Cada resposta é corrigida automaticamente pela última linha `RESPOSTA:`.",
        "",
        "| Provedor | Modelo | Acerto | Fatos | Investigação | Diagnóstico "
        "| Tempo médio | Ferramentas por pergunta | Custo total |",
        "|---|---|--:|--:|--:|--:|--:|--:|--:|",
    ]
    for (provedor, modelo), tentativas in por_modelo.items():

        def taxa(grupo: list[Tentativa]) -> str:
            return f"{sum(t.acertou for t in grupo)}/{len(grupo)}" if grupo else "—"

        def da(categoria: str, grupo: list[Tentativa] = tentativas) -> list[Tentativa]:
            return [t for t in grupo if categorias.get(t.questao) == categoria]

        custos = [t.custo_usd for t in tentativas if t.custo_usd is not None]
        custo = (
            f"US$ {numero(sum(custos), 4)}" if len(custos) == len(tentativas) else "não estimado"
        )
        linhas.append(
            f"| {provedor} | `{modelo}` | **{taxa(tentativas)}** | {taxa(da('fatos'))} "
            f"| {taxa(da('investigacao'))} | {taxa(da('diagnostico'))} "
            f"| {numero(statistics.mean(t.segundos for t in tentativas), 1)} s "
            f"| {numero(statistics.mean(t.ferramentas for t in tentativas), 1)} | {custo} |"
        )

    linhas += ["", "## Pergunta a pergunta", ""]
    for q in resultado.questoes:
        linhas += [
            f"**{q['id']}** ({q['categoria']}): {q['pergunta']}",
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
    uso_total = sum((Uso(**t.uso) for t in resultado.tentativas if t.uso), Uso())
    linhas.append(
        f"Tokens no total: {numero(uso_total.entrada)} de entrada, "
        f"{numero(uso_total.cache_leitura)} lidos do cache e {numero(uso_total.saida)} de saída."
    )
    return "\n".join(linhas) + "\n"
