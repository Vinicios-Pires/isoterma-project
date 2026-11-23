"""Mede os detectores contra o gabarito dos incidentes injetados.

A comparação é por evento: uma detecção acerta quando tem o mesmo tipo e o mesmo alvo de um
incidente e o período dela encosta no dele (com uma folga pequena, porque as janelas móveis
borram as bordas). Daí saem, por tipo:

- **precisão:** das detecções, quantas correspondem a um incidente;
- **recall:** dos incidentes, quantos foram detectados;
- **atraso:** quanto tempo depois do início do incidente veio a primeira detecção dele.

Detecções no alvo certo e na hora certa, mas com o tipo errado, aparecem como **confusões**.

Alguns incidentes não deixam rastro: um defeito de "picos" em 2% das leituras durante uma hora
pode, no sorteio, não afetar nenhuma. Esses ficam marcados como **invisíveis** e fora do recall,
mas aparecem no relatório.
"""

import statistics
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb

from isoterma.anomalias.detectores import Deteccao, Resultado
from isoterma.dados import conectar

TIPOS = (
    "falha_crac",
    "super_refrigeracao",
    "rack_sobrecarregado",
    "recirculacao",
    "sensor_congelado",
    "sensor_deriva",
    "sensor_picos",
    "sensor_sem_leitura",
)
FOLGA = timedelta(minutes=30)


@dataclass(frozen=True)
class Incidente:
    tipo: str
    alvo: str
    inicio: datetime
    fim: datetime
    intensidade: float
    descricao: str
    visivel: bool = True


# Desvio mínimo, em relação aos minutos vizinhos, para um pico contar como visível. Os picos
# injetados têm de 8 a 25 °C: a régua aqui é a do simulador, não a do detector.
PICO_VISIVEL_C = 8.0


def _visivel(conexao: duckdb.DuckDBPyConnection, inc: Incidente) -> bool:
    """Se o defeito afetou alguma leitura (só picos e falta de leitura podem não afetar)."""
    if inc.tipo not in ("sensor_picos", "sensor_sem_leitura"):
        return True
    condicao = (
        "valor IS NULL"
        if inc.tipo == "sensor_sem_leitura"
        else f"abs(valor - (anterior + seguinte) / 2) >= {PICO_VISIVEL_C}"
    )
    linha = conexao.execute(
        f"""
        WITH s AS (
            SELECT l.ts, l.valor, lag(l.valor) OVER w AS anterior, lead(l.valor) OVER w AS seguinte
            FROM leituras AS l JOIN sensores AS s USING (sensor_id)
            WHERE s.codigo = ? AND l.ts BETWEEN ?::TIMESTAMPTZ - INTERVAL 1 HOUR
                AND ?::TIMESTAMPTZ + INTERVAL 1 HOUR
            WINDOW w AS (ORDER BY l.ts)
        )
        SELECT count(*) FROM s WHERE ts >= ? AND ts < ? AND {condicao}
        """,
        [inc.alvo, inc.inicio, inc.fim, inc.inicio, inc.fim],
    ).fetchone()
    return bool(linha and linha[0])


def ler_gabarito(diretorio: Path) -> list[Incidente]:
    """O gabarito, com cada incidente marcado como visível ou não nos dados."""
    conexao = conectar(diretorio)
    try:
        linhas = conexao.execute(
            "SELECT tipo, alvo, inicio::TIMESTAMP, fim::TIMESTAMP, intensidade, descricao "
            "FROM incidentes ORDER BY inicio, tipo, alvo"
        ).fetchall()
        incidentes = [
            Incidente(tipo, alvo, inicio.replace(tzinfo=UTC), fim.replace(tzinfo=UTC), i, texto)
            for tipo, alvo, inicio, fim, i, texto in linhas
        ]
        return [replace(inc, visivel=_visivel(conexao, inc)) for inc in incidentes]
    finally:
        conexao.close()


def _encostam(a_inicio: datetime, a_fim: datetime, b_inicio: datetime, b_fim: datetime) -> bool:
    return a_inicio < b_fim + FOLGA and b_inicio < a_fim + FOLGA


def corresponde(deteccao: Deteccao, incidente: Incidente) -> bool:
    """Se a detecção acertou o incidente: mesmo tipo, mesmo alvo e períodos que se encostam."""
    return (
        deteccao.tipo == incidente.tipo
        and deteccao.alvo == incidente.alvo
        and _encostam(deteccao.inicio, deteccao.fim, incidente.inicio, incidente.fim)
    )


def _mesmo_lugar(deteccao: Deteccao, incidente: Incidente) -> bool:
    """Mesmo equipamento: o rack ou CRAC, ou um sensor dele (para achar confusões)."""
    return deteccao.alvo.split("/")[0] == incidente.alvo.split("/")[0]


@dataclass
class PlacarTipo:
    incidentes: int = 0  # só os visíveis nos dados
    invisiveis: int = 0
    detectados: int = 0
    deteccoes: int = 0
    corretas: int = 0
    atrasos_min: list[float] = field(default_factory=list[float])

    @property
    def precisao(self) -> float | None:
        return self.corretas / self.deteccoes if self.deteccoes else None

    @property
    def recall(self) -> float | None:
        return self.detectados / self.incidentes if self.incidentes else None

    @property
    def f1(self) -> float | None:
        p, r = self.precisao, self.recall
        if p is None or r is None or p + r == 0:
            return None if p is None or r is None else 0.0
        return 2 * p * r / (p + r)

    def somar(self, outro: PlacarTipo) -> None:
        self.incidentes += outro.incidentes
        self.invisiveis += outro.invisiveis
        self.detectados += outro.detectados
        self.deteccoes += outro.deteccoes
        self.corretas += outro.corretas
        self.atrasos_min += outro.atrasos_min

    def como_dict(self) -> dict[str, Any]:
        def arredondar(valor: float | None) -> float | None:
            return None if valor is None else round(valor, 3)

        return {
            "incidentes": self.incidentes,
            "invisiveis": self.invisiveis,
            "detectados": self.detectados,
            "deteccoes": self.deteccoes,
            "corretas": self.corretas,
            "precisao": arredondar(self.precisao),
            "recall": arredondar(self.recall),
            "f1": arredondar(self.f1),
            "atraso_mediano_min": (
                round(statistics.median(self.atrasos_min), 1) if self.atrasos_min else None
            ),
        }


@dataclass
class Avaliacao:
    simulacao: str
    por_tipo: dict[str, PlacarTipo]
    perdidos: list[Incidente]
    invisiveis: list[Incidente]
    falsos: list[Deteccao]
    confusoes: list[tuple[Deteccao, Incidente]]
    resultado: Resultado

    @property
    def total(self) -> PlacarTipo:
        soma = PlacarTipo()
        for placar in self.por_tipo.values():
            soma.somar(placar)
        return soma

    def como_dict(self) -> dict[str, Any]:
        def incidente(i: Incidente) -> dict[str, Any]:
            return {
                "tipo": i.tipo,
                "alvo": i.alvo,
                "inicio": i.inicio.isoformat(),
                "fim": i.fim.isoformat(),
                "descricao": i.descricao,
                "visivel": i.visivel,
            }

        def deteccao(d: Deteccao) -> dict[str, Any]:
            return {
                "tipo": d.tipo,
                "alvo": d.alvo,
                "inicio": d.inicio.isoformat(),
                "fim": d.fim.isoformat(),
                "evidencia": d.evidencia,
            }

        return {
            "simulacao": self.simulacao,
            "segundos": round(self.resultado.segundos, 2),
            "fonte": self.resultado.fonte,
            "total": self.total.como_dict(),
            "por_tipo": {t: p.como_dict() for t, p in self.por_tipo.items()},
            "perdidos": [incidente(i) for i in self.perdidos],
            "invisiveis": [incidente(i) for i in self.invisiveis],
            "falsos": [deteccao(d) for d in self.falsos],
            "confusoes": [
                {"deteccao": deteccao(d), "incidente": incidente(i)} for d, i in self.confusoes
            ],
        }


def avaliar(simulacao: str, resultado: Resultado, gabarito: list[Incidente]) -> Avaliacao:
    por_tipo = {t: PlacarTipo() for t in TIPOS}
    deteccoes = resultado.deteccoes

    detectados: set[int] = set()
    for indice, inc in enumerate(gabarito):
        placar = por_tipo.setdefault(inc.tipo, PlacarTipo())
        if not inc.visivel:
            placar.invisiveis += 1
            detectados.add(indice)  # fora do recall e da lista de perdidos
            continue
        placar.incidentes += 1
        acertos = [d for d in deteccoes if corresponde(d, inc)]
        if acertos:
            detectados.add(indice)
            placar.detectados += 1
            primeira = min(d.inicio for d in acertos)
            placar.atrasos_min.append(max(0.0, (primeira - inc.inicio).total_seconds() / 60))

    falsos: list[Deteccao] = []
    confusoes: list[tuple[Deteccao, Incidente]] = []
    for d in deteccoes:
        placar = por_tipo.setdefault(d.tipo, PlacarTipo())
        placar.deteccoes += 1
        if any(corresponde(d, i) for i in gabarito):
            placar.corretas += 1
            continue
        falsos.append(d)
        perto = [
            i
            for i in gabarito
            if _mesmo_lugar(d, i) and _encostam(d.inicio, d.fim, i.inicio, i.fim)
        ]
        confusoes += [(d, i) for i in perto]

    perdidos = [inc for indice, inc in enumerate(gabarito) if indice not in detectados]
    invisiveis = [inc for inc in gabarito if not inc.visivel]
    return Avaliacao(simulacao, por_tipo, perdidos, invisiveis, falsos, confusoes, resultado)
