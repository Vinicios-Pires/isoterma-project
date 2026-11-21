"""As ferramentas do agente: as consultas do motor e o SQL seguro, com argumentos validados."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, tzinfo
from typing import Any, Literal

import pyarrow as pa
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from isoterma.ia.tipos import ChamadaFerramenta, DefinicaoFerramenta, ResultadoFerramenta
from isoterma.motor import ConsultaExpirou, ConsultaInvalida, ConsultaRecusada, Hall

LIMITE_LINHAS_SQL = 50
LIMITE_LINHAS = 200
TEMPO_MAX_SQL_S = 20.0
PONTOS_PADRAO = 48

DESCRICAO_DATA = "no horário local do hall, no formato AAAA-MM-DDTHH:MM"


class _Argumentos(BaseModel):
    # Todos os campos são obrigatórios (os opcionais aceitam null): é o que o modo estrito
    # de ferramentas de Claude e OpenAI exige.
    model_config = ConfigDict(extra="forbid")


class ArgsJanela(_Argumentos):
    inicio: str | None = Field(
        description=f"Início da janela, {DESCRICAO_DATA}. null: começo da simulação."
    )
    fim: str | None = Field(
        description=f"Fim da janela (exclusivo), {DESCRICAO_DATA}. null: fim da simulação."
    )


class ArgsMapa(_Argumentos):
    instante: str | None = Field(description=f"Instante, {DESCRICAO_DATA}. null: fim da simulação.")
    tipo: Literal["temp_entrada", "temp_saida", "potencia_kw"] | None = Field(
        description="O que medir em cada rack. null: temp_entrada."
    )
    altura: Literal["base", "meio", "topo"] | None = Field(
        description="Só para temp_entrada. null: a altura mais quente de cada rack."
    )


class ArgsSerie(_Argumentos):
    alvo: str = Field(
        description="Código de um sensor (ex.: 'C-07/entrada-topo'), um rack (ex.: 'C-07', traz os "
        "5 sensores dele) ou um CRAC (ex.: 'CRAC-02', traz insuflamento e retorno)."
    )
    inicio: str | None = Field(description=f"Início, {DESCRICAO_DATA}. null: começo da simulação.")
    fim: str | None = Field(
        description=f"Fim (exclusivo), {DESCRICAO_DATA}. null: fim da simulação."
    )
    pontos: int | None = Field(
        description=f"Máximo de pontos por sensor (até 200). null: {PONTOS_PADRAO}."
    )


class ArgsSQL(_Argumentos):
    sql: str = Field(description="Um único SELECT em SQL do DuckDB. Horários das tabelas em UTC.")


@dataclass(frozen=True)
class Execucao:
    texto: str
    linhas: int
    sql: str | None = None  # o SQL executado, quando a ferramenta é a de SQL livre


@dataclass(frozen=True)
class Ferramenta:
    nome: str
    descricao: str
    argumentos: type[_Argumentos]
    executar: Callable[[Hall, Any], Execucao]

    def definicao(self) -> DefinicaoFerramenta:
        return DefinicaoFerramenta(self.nome, self.descricao, esquema_estrito(self.argumentos))


def esquema_estrito(modelo: type[BaseModel]) -> dict[str, Any]:
    """JSON Schema sem títulos, com todas as propriedades obrigatórias e sem extras."""

    def limpar(no: Any) -> Any:
        if isinstance(no, dict):
            return {k: limpar(v) for k, v in no.items() if k != "title"}
        if isinstance(no, list):
            return [limpar(v) for v in no]
        return no

    esquema = limpar(modelo.model_json_schema())
    esquema["required"] = list(esquema["properties"])
    esquema["additionalProperties"] = False
    return esquema


def _data(texto: str | None) -> datetime | None:
    if texto is None:
        return None
    try:
        return datetime.fromisoformat(texto)
    except ValueError as erro:
        raise ValueError(f"Data inválida {texto!r}: use AAAA-MM-DDTHH:MM") from erro


def _valor(valor: Any, fuso: tzinfo) -> str:
    if valor is None:
        return "null"
    if isinstance(valor, datetime):
        return f"{valor.astimezone(fuso):%Y-%m-%d %H:%M}"
    if isinstance(valor, float):
        return f"{valor:.2f}".rstrip("0").rstrip(".")
    return str(valor)


def formatar_tabela(tabela: pa.Table, fuso: tzinfo, limite: int, truncado: bool = False) -> str:
    """Tabela compacta em texto, com horários locais: barata em tokens e fácil de ler."""
    if tabela.num_rows == 0:
        return "(nenhuma linha)"
    linhas = [" | ".join(tabela.column_names)]
    for registro in tabela.slice(0, limite).to_pylist():
        linhas.append(" | ".join(_valor(v, fuso) for v in registro.values()))
    if tabela.num_rows > limite or truncado:
        total = f"{tabela.num_rows}" if not truncado else f"mais de {tabela.num_rows}"
        linhas.append(f"(mostrando {min(limite, tabela.num_rows)} de {total} linhas)")
    return "\n".join(linhas)


def _resumo(hall: Hall, args: ArgsJanela) -> Execucao:
    r = hall.resumo(_data(args.inicio), _data(args.fim))
    texto = json.dumps(
        {k: _valor(v, hall.fuso) if isinstance(v, datetime) else v for k, v in r.items()},
        ensure_ascii=False,
        indent=1,
    )
    return Execucao(texto, 1)


def _mapa(hall: Hall, args: ArgsMapa) -> Execucao:
    tabela = hall.mapa_termico(
        _data(args.instante), tipo=args.tipo or "temp_entrada", altura=args.altura
    )
    return Execucao(formatar_tabela(tabela, hall.fuso, LIMITE_LINHAS), tabela.num_rows)


def _fora(hall: Hall, args: ArgsJanela) -> Execucao:
    tabela = hall.fora_da_faixa(_data(args.inicio), _data(args.fim))
    return Execucao(formatar_tabela(tabela, hall.fuso, LIMITE_LINHAS), tabela.num_rows)


def _serie(hall: Hall, args: ArgsSerie) -> Execucao:
    pontos = min(args.pontos or PONTOS_PADRAO, LIMITE_LINHAS)
    tabela = hall.serie(args.alvo, _data(args.inicio), _data(args.fim), max_pontos=pontos)
    return Execucao(formatar_tabela(tabela, hall.fuso, LIMITE_LINHAS * 5), tabela.num_rows)


def _sql(hall: Hall, args: ArgsSQL) -> Execucao:
    resultado = hall.consultar(args.sql, limite=LIMITE_LINHAS_SQL, tempo_max_s=TEMPO_MAX_SQL_S)
    texto = formatar_tabela(resultado.tabela, hall.fuso, LIMITE_LINHAS_SQL, resultado.truncado)
    return Execucao(texto, resultado.tabela.num_rows, args.sql)


FERRAMENTAS: tuple[Ferramenta, ...] = (
    Ferramenta(
        "resumo",
        "Visão geral do hall numa janela: volume de leituras, mínimo/média/máximo por tipo de "
        "sensor, potência média total e quantos racks saíram da faixa ASHRAE.",
        ArgsJanela,
        _resumo,
    ),
    Ferramenta(
        "mapa_termico",
        "Valor de cada rack num instante (média dos 5 minutos anteriores), com fileira, posição, "
        "zona do CRAC e, para temp_entrada, a faixa ASHRAE: 'acima', 'abaixo' ou 'ok'.",
        ArgsMapa,
        _mapa,
    ),
    Ferramenta(
        "fora_da_faixa",
        "Racks cuja entrada saiu de 18–27 °C na janela: minutos acima e abaixo, pico, mínimo e "
        "a primeira e a última vez. Ordenado pelos mais afetados.",
        ArgsJanela,
        _fora,
    ),
    Ferramenta(
        "serie",
        "Série temporal (mínimo, média e máximo por intervalo) de um sensor, de um rack ou de "
        "um CRAC. O intervalo entre pontos se ajusta à janela.",
        ArgsSerie,
        _serie,
    ),
    Ferramenta(
        "consultar_sql",
        "Executa um SELECT livre no DuckDB, só leitura, com no máximo 50 linhas no resultado. "
        "Use quando as outras ferramentas não respondem. Agregue no SQL em vez de listar linhas.",
        ArgsSQL,
        _sql,
    ),
)


class CaixaDeFerramentas:
    """Executa as chamadas do modelo sobre um hall, transformando erros em resultados."""

    def __init__(self, hall: Hall, ferramentas: tuple[Ferramenta, ...] = FERRAMENTAS) -> None:
        self.hall = hall
        self._por_nome = {f.nome: f for f in ferramentas}

    def definicoes(self) -> list[DefinicaoFerramenta]:
        return [f.definicao() for f in self._por_nome.values()]

    def executar(self, chamada: ChamadaFerramenta) -> tuple[ResultadoFerramenta, Execucao | None]:
        def falha(mensagem: str) -> tuple[ResultadoFerramenta, None]:
            return ResultadoFerramenta(chamada.id, chamada.nome, mensagem, erro=True), None

        ferramenta = self._por_nome.get(chamada.nome)
        if ferramenta is None:
            return falha(
                f"Ferramenta {chamada.nome!r} não existe. Use: {', '.join(self._por_nome)}"
            )
        try:
            argumentos = ferramenta.argumentos.model_validate(chamada.argumentos)
        except ValidationError as erro:
            problemas = "; ".join(
                f"{'.'.join(map(str, e['loc'])) or 'argumentos'}: {e['msg']}" for e in erro.errors()
            )
            return falha(f"Argumentos inválidos para {chamada.nome}: {problemas}")
        try:
            execucao = ferramenta.executar(self.hall, argumentos)
        except (ConsultaRecusada, ConsultaInvalida, ConsultaExpirou, ValueError) as erro:
            return falha(str(erro))
        return ResultadoFerramenta(chamada.id, chamada.nome, execucao.texto), execucao
