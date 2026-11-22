"""Detectores de anomalias explicáveis, em SQL, sobre as leituras de cada minuto.

Cada detector compara um sensor com o que a física do hall espera dele e só alerta quando a
diferença dura o bastante. A ideia central é separar **evento físico** de **defeito de sensor**:

- Um evento físico mexe em vários sensores de forma coerente. Uma falha de CRAC aquece o
  insuflamento *e* a entrada dos racks da zona; a recirculação aquece as três alturas do rack na
  proporção que o ar quente impõe (pouco na base, muito no topo).
- Um defeito de sensor mexe só nele: o valor discorda dos sensores vizinhos, que continuam
  coerentes entre si.

Os detectores nunca leem o gabarito: a conexão é aberta sem a tabela ``incidentes``.
"""

import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb

from isoterma.dados import conectar, ler_manifesto

FOLGA_CAUSA = timedelta(minutes=30)

# Alcances testados para a média do ar de retorno (em metros).
ALCANCES_M = (0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0)


@dataclass(frozen=True)
class Limiares:
    """Os parâmetros dos detectores. Os padrões foram calibrados em simulações à parte."""

    sem_leitura_fracao: float = 0.3  # fração de leituras nulas numa janela de 15 min
    congelado_min: int = 30  # minutos repetindo exatamente o mesmo valor
    pico_c: float = 5.0  # distância dos dois minutos vizinhos
    deriva_c: float = 1.0  # quanto um sensor discorda do que os vizinhos indicam
    deriva_min: int = 60
    deriva_cobertura: float = 0.6  # fração do evento em que o desvio aparece
    recirculacao_c: float = 1.5  # quanto o topo sobe em relação à base
    recirculacao_min: int = 30
    sobrecarga_razao: float = 1.3  # carga do rack em relação à do hall, ambas sobre o nominal
    sobrecarga_min: int = 15
    crac_c: float = 2.0  # quanto o insuflamento se afasta do normal
    zona_c: float = 0.8  # quanto a entrada dos racks da zona acompanha o CRAC
    falha_min: int = 10
    super_refrigeracao_min: int = 60


@dataclass(frozen=True)
class Deteccao:
    tipo: str
    alvo: str
    inicio: datetime
    fim: datetime
    evidencia: str
    medida: float  # o valor que mais se afastou do normal, na unidade da evidência


@dataclass
class Resultado:
    deteccoes: list[Deteccao]
    limiares: Limiares
    segundos: float
    fonte: str
    etapas: dict[str, float] = field(default_factory=dict[str, float])
    parametros: dict[str, float] = field(default_factory=dict[str, float])

    def como_dict(self) -> dict[str, Any]:
        return {
            "limiares": asdict(self.limiares),
            "segundos": round(self.segundos, 2),
            "fonte": self.fonte,
            "etapas": {k: round(v, 2) for k, v in self.etapas.items()},
            "parametros_ajustados": self.parametros,
            "deteccoes": [
                {**asdict(d), "inicio": d.inicio.isoformat(), "fim": d.fim.isoformat()}
                for d in self.deteccoes
            ],
        }


def _numero(valor: float, casas: int = 1) -> str:
    return f"{valor:.{casas}f}".replace(".", ",")


def _fonte_por_minuto(conexao: duckdb.DuckDBPyConnection, intervalo_s: int) -> tuple[str, str]:
    """A consulta que entrega uma linha por sensor e minuto, da camada mais barata."""
    colunas = "sensor_id, t, media, minimo, maximo, leituras, nulos"
    if intervalo_s >= 60:
        # As leituras já são por minuto (ou mais espaçadas): cada uma vale como um minuto.
        return (
            "leituras brutas",
            """
            SELECT sensor_id, ts AS t, valor AS media, valor AS minimo, valor AS maximo,
                (valor IS NOT NULL)::INTEGER AS leituras, (valor IS NULL)::INTEGER AS nulos
            FROM leituras
        """,
        )
    tabelas = {linha[0] for linha in conexao.execute("SHOW TABLES").fetchall()}
    if "agregados_minuto" in tabelas:
        return "agregados por minuto", (
            f"SELECT {colunas.replace(' t,', ' inicio AS t,')} FROM agregados_minuto"
        )
    return (
        "leituras agrupadas por minuto",
        """
        SELECT sensor_id, time_bucket(INTERVAL 1 MINUTE, ts) AS t, avg(valor) AS media,
            min(valor) AS minimo, max(valor) AS maximo, count(valor)::INTEGER AS leituras,
            (count(*) - count(valor))::INTEGER AS nulos
        FROM leituras
        GROUP BY ALL
    """,
    )


def _ilhas(
    sinais: str,
    *,
    juntar_min: int,
    duracao_min: int,
    passo_s: int,
    recuo_min: int = 0,
    cobertura: float = 0.0,
) -> str:
    """Junta os minutos marcados de cada alvo em eventos.

    ``sinais`` precisa ter ``alvo``, ``t`` e ``v`` (a medida, maior = mais anômalo). Minutos
    separados por até ``juntar_min`` viram o mesmo evento; eventos mais curtos que
    ``duracao_min`` são descartados. ``recuo_min`` antecipa o início, para detectores que só
    marcam o fim da janela que olharam. ``cobertura`` é a fração mínima do evento com minutos
    marcados: separa um desvio contínuo de pontos soltos que só calharam de ficar perto.
    """
    return f"""
        WITH s AS (SELECT alvo, t, v FROM ({sinais})),
        n AS (
            SELECT *, CASE
                WHEN lag(t) OVER (PARTITION BY alvo ORDER BY t)
                    >= t - INTERVAL '{juntar_min} minutes' THEN 0 ELSE 1 END AS novo
            FROM s
        ),
        g AS (
            SELECT *, sum(novo) OVER (PARTITION BY alvo ORDER BY t ROWS UNBOUNDED PRECEDING)
                AS grupo
            FROM n
        )
        SELECT alvo, (min(t) - INTERVAL '{recuo_min} minutes')::TIMESTAMP AS inicio,
            (max(t) + INTERVAL '{passo_s} seconds')::TIMESTAMP AS fim, max(v) AS v,
            count(*) AS minutos
        FROM g
        GROUP BY alvo, grupo
        HAVING max(t) + INTERVAL '{passo_s} seconds' - min(t)
            >= INTERVAL '{duracao_min} minutes' - INTERVAL '{recuo_min} minutes'
            AND count(*) * {passo_s} >= {cobertura} * (
                epoch(max(t) - min(t)) + {passo_s}
            )
        ORDER BY inicio, alvo
    """


def _reta_robusta(origem: str, chave: str, y: str, x: str, rodadas: int = 2) -> str:
    """Ajusta ``y = a + b·x`` por ``chave``, ignorando os pontos que fogem muito da reta.

    Um sensor com deriva por dias entorta uma regressão comum, e a reta torta passa a acusar
    desvios fora do incidente. Aqui cada rodada descarta os pontos com resíduo acima de 4 vezes
    o resíduo mediano (o mínimo é 0,3 °C) e ajusta de novo.
    """
    sql = (
        f"SELECT {chave}, regr_intercept({y}, {x}) AS a, regr_slope({y}, {x}) AS b "
        f"FROM {origem} GROUP BY {chave}"
    )
    for _ in range(rodadas):
        sql = f"""
            SELECT {chave}, regr_intercept(y, x) AS a, regr_slope(y, x) AS b
            FROM (
                SELECT o.{chave}, o.{y} AS y, o.{x} AS x,
                    abs(o.{y} - (r.a + r.b * o.{x})) AS residuo,
                    median(abs(o.{y} - (r.a + r.b * o.{x}))) OVER (PARTITION BY o.{chave})
                        AS residuo_tipico
                FROM {origem} AS o JOIN ({sql}) AS r USING ({chave})
            )
            WHERE residuo <= greatest(4 * residuo_tipico, 0.3)
            GROUP BY {chave}
        """
    return sql


class Detector:
    """Roda todos os detectores sobre uma simulação."""

    def __init__(self, diretorio: Path, limiares: Limiares | None = None) -> None:
        self.diretorio = diretorio
        self.lim = limiares or Limiares()
        intervalo = int(ler_manifesto(diretorio)["periodo"]["intervalo_s"])
        self.passo_s = max(60, intervalo)
        self.conexao = conectar(diretorio, com_gabarito=False)
        self.nome_fonte, self.fonte = _fonte_por_minuto(self.conexao, intervalo)
        self.deteccoes: list[Deteccao] = []
        self.etapas: dict[str, float] = {}
        self.parametros: dict[str, float] = {}

    def _eventos(
        self,
        tipo: str,
        sinais: str,
        evidencia: Callable[[float, int], str],
        *,
        juntar_min: int = 30,
        duracao_min: int = 0,
        recuo_min: int = 0,
        cobertura: float = 0.0,
    ) -> None:
        sql = _ilhas(
            sinais,
            juntar_min=juntar_min,
            duracao_min=duracao_min,
            passo_s=self.passo_s,
            recuo_min=recuo_min,
            cobertura=cobertura,
        )
        for alvo, inicio, fim, v, minutos in self.conexao.execute(sql).fetchall():
            self.deteccoes.append(
                Deteccao(
                    tipo,
                    alvo,
                    inicio.replace(tzinfo=UTC),
                    fim.replace(tzinfo=UTC),
                    evidencia(float(v), int(minutos)),
                    float(v),
                )
            )

    def _linhas(self, minutos: int) -> int:
        """Quantas linhas da grade (uma por sensor e passo) cobrem tantos minutos.

        As janelas são por linhas, e não por intervalo de tempo: o simulador grava uma linha por
        sensor e passo, mesmo sem leitura, e janelas por linhas são várias vezes mais rápidas.
        """
        return max(1, round(minutos * 60 / self.passo_s))

    def _medir(self, etapa: str, funcao: Callable[[], None]) -> None:
        inicio = time.perf_counter()
        funcao()
        self.etapas[etapa] = time.perf_counter() - inicio

    # Etapa 1: o que dá para ver olhando um sensor sozinho.
    def _sensores(self) -> None:
        lim, c = self.lim, self.conexao
        meia, congelado = self._linhas(7), self._linhas(lim.congelado_min)
        c.execute(f"""
            CREATE TEMP TABLE sinais_sensor AS
            WITH f AS ({self.fonte}),
            w AS (
                SELECT f.sensor_id, f.t,
                    sum(f.nulos) OVER centro15 / nullif(sum(f.leituras + f.nulos) OVER centro15, 0)
                        AS fracao_nula,
                    max(f.maximo) OVER fim_janela - min(f.minimo) OVER fim_janela AS amplitude,
                    count(f.media) OVER fim_janela AS minutos_com_dado,
                    first(f.media) OVER fim_janela AS valor_inicial,
                    -- Um pico foge dos dois minutos vizinhos ao mesmo tempo; uma subida de
                    -- verdade (até ~2 °C por minuto numa falha de CRAC) não.
                    f.maximo - greatest(lag(f.media) OVER ordem, lead(f.media) OVER ordem)
                        AS acima,
                    least(lag(f.media) OVER ordem, lead(f.media) OVER ordem) - f.minimo
                        AS abaixo
                FROM f
                WINDOW
                    centro15 AS (PARTITION BY f.sensor_id ORDER BY f.t
                        ROWS BETWEEN {meia} PRECEDING AND {meia} FOLLOWING),
                    ordem AS (PARTITION BY f.sensor_id ORDER BY f.t),
                    fim_janela AS (PARTITION BY f.sensor_id ORDER BY f.t
                        ROWS BETWEEN {congelado - 1} PRECEDING AND CURRENT ROW)
            )
            SELECT w.*, s.codigo, s.unidade
            FROM w JOIN sensores AS s USING (sensor_id)
            WHERE w.fracao_nula >= {lim.sem_leitura_fracao}
                OR (w.amplitude = 0 AND w.minutos_com_dado >= {congelado * 2 // 3})
                OR (s.unidade = '°C' AND greatest(w.acima, w.abaixo) >= {lim.pico_c})
        """)
        self._eventos(
            "sensor_sem_leitura",
            f"SELECT codigo AS alvo, t, fracao_nula AS v FROM sinais_sensor "
            f"WHERE fracao_nula >= {lim.sem_leitura_fracao}",
            lambda v, m: f"Até {v:.0%} das leituras ausentes numa janela de 15 minutos",
            juntar_min=30,
            duracao_min=10,
        )
        self._eventos(
            "sensor_congelado",
            f"SELECT codigo AS alvo, t, valor_inicial AS v FROM sinais_sensor "
            f"WHERE amplitude = 0 AND minutos_com_dado >= {congelado * 2 // 3}",
            lambda v, m: f"Repetiu exatamente {_numero(v)} por {_numero(m / 60 + 0.5)} h",
            juntar_min=5,
            duracao_min=lim.congelado_min,
            recuo_min=lim.congelado_min - 1,
        )
        self._eventos(
            "sensor_picos",
            f"SELECT codigo AS alvo, t, greatest(acima, abaixo) AS v FROM sinais_sensor "
            f"WHERE unidade = '°C' AND greatest(acima, abaixo) >= {lim.pico_c}",
            lambda v, m: (
                f"{m} leitura{'s' if m > 1 else ''} fora da curva, "
                f"até {_numero(v)} °C longe dos minutos vizinhos"
            ),
            juntar_min=120,
        )
        # Os minutos de um sensor congelado não servem para comparar com os vizinhos.
        c.execute(f"""
            CREATE TEMP TABLE congelados AS
            SELECT s.sensor_id, timezone('UTC', e.inicio) AS inicio, timezone('UTC', e.fim) AS fim
            FROM ({
            _ilhas(
                f"SELECT sensor_id::VARCHAR AS alvo, t, 0 AS v FROM sinais_sensor "
                f"WHERE amplitude = 0 AND minutos_com_dado >= {congelado * 2 // 3}",
                juntar_min=5,
                duracao_min=lim.congelado_min,
                passo_s=self.passo_s,
                recuo_min=lim.congelado_min - 1,
            )
        }) AS e
            JOIN sensores AS s ON s.sensor_id::VARCHAR = e.alvo
        """)

    # Etapa 2: tabelas largas por rack e por CRAC, sem os minutos já explicados por defeito
    # (picos e sensores congelados) e com média móvel de 15 min para tirar o ruído.
    def _tabelas(self) -> None:
        self.conexao.execute(f"""
            CREATE TEMP TABLE por_minuto AS
            SELECT f.sensor_id, f.t, f.media
            FROM ({self.fonte}) AS f
            ANTI JOIN congelados AS c
                ON f.sensor_id = c.sensor_id AND f.t >= c.inicio AND f.t < c.fim
            ANTI JOIN (
                SELECT sensor_id, t FROM sinais_sensor
                WHERE unidade = '°C' AND greatest(acima, abaixo) >= {self.lim.pico_c}
            ) AS p ON f.sensor_id = p.sensor_id AND f.t = p.t
        """)
        meia = self._linhas(7)
        janela = f"(PARTITION BY id ORDER BY t ROWS BETWEEN {meia} PRECEDING AND {meia} FOLLOWING)"
        self.conexao.execute(f"""
            CREATE TEMP TABLE racks_min AS
            WITH largo AS (
                SELECT s.rack_id AS id, m.t,
                    avg(m.media) FILTER (s.altura = 'base') AS base,
                    avg(m.media) FILTER (s.altura = 'meio') AS meio,
                    avg(m.media) FILTER (s.altura = 'topo') AS topo,
                    avg(m.media) FILTER (s.tipo = 'temp_saida') AS saida,
                    avg(m.media) FILTER (s.tipo = 'potencia_kw') AS potencia
                FROM por_minuto AS m JOIN sensores AS s USING (sensor_id)
                WHERE s.rack_id IS NOT NULL
                GROUP BY ALL
            )
            SELECT id AS rack_id, t,
                avg(base) OVER w AS base, avg(meio) OVER w AS meio,
                avg(topo) OVER w AS topo, avg(saida) OVER w AS saida,
                avg(potencia) OVER w AS potencia
            FROM largo
            WINDOW w AS {janela}
        """)
        self.conexao.execute(f"""
            CREATE TEMP TABLE cracs_min AS
            WITH largo AS (
                SELECT s.crac_id AS id, m.t,
                    avg(m.media) FILTER (s.tipo = 'temp_insuflamento') AS insuflamento,
                    avg(m.media) FILTER (s.tipo = 'temp_retorno') AS retorno
                FROM por_minuto AS m JOIN sensores AS s USING (sensor_id)
                WHERE s.crac_id IS NOT NULL
                GROUP BY ALL
            )
            SELECT id AS crac_id, t,
                avg(insuflamento) OVER w AS insuflamento, avg(retorno) OVER w AS retorno
            FROM largo
            WINDOW w AS {janela}
        """)
        self.conexao.execute("DROP TABLE por_minuto")

    # Etapa 3: racks. As três alturas recebem o mesmo ar do CRAC; a diferença entre elas só
    # muda com recirculação (padrão 0,15 / 0,5 / 1,0) ou com um sensor com defeito.
    def _racks(self) -> None:
        lim, c = self.lim, self.conexao
        c.execute(f"""
            CREATE TEMP TABLE racks_res AS
            WITH b AS (
                SELECT r.*, base + meio + topo - greatest(base, meio, topo)
                    - least(base, meio, topo) AS entrada,
                    potencia / k.potencia_nominal_kw AS carga
                FROM racks_min AS r JOIN racks AS k USING (rack_id)
            ),
            d AS (
                SELECT *,
                    meio - base AS mb, topo - base AS tb,
                    base - (meio + topo) / 2 AS e_base, meio - (base + topo) / 2 AS e_meio,
                    topo - (base + meio) / 2 AS e_topo,
                    saida - entrada AS delta, carga / median(carga) OVER (PARTITION BY t) AS razao
                FROM b
            ),
            -- A referência é o hall no mesmo minuto, e não o histórico do próprio rack: um
            -- incidente que ocupa boa parte do período viraria o "normal" do histórico.
            hall AS (
                SELECT t, median(mb) AS mb0, median(tb) AS tb0, median(e_base) AS eb0,
                    median(e_meio) AS em0, median(e_topo) AS et0
                FROM d GROUP BY t
            ),
            -- A saída é a entrada mais um aquecimento proporcional à carga.
            reta AS ({_reta_robusta("d", "rack_id", "delta", "potencia")})
            SELECT d.rack_id, d.t, d.razao,
                d.mb - a.mb0 AS mb, d.tb - a.tb0 AS tb,
                d.e_base - a.eb0 AS e_base, d.e_meio - a.em0 AS e_meio, d.e_topo - a.et0 AS e_topo,
                d.delta - (r.a + r.b * d.potencia) AS e_saida
            FROM d JOIN hall AS a USING (t) JOIN reta AS r USING (rack_id)
        """)
        recirculacao = f"""tb >= {lim.recirculacao_c}
            AND mb BETWEEN 0.2 * tb AND 0.65 * tb"""
        self._eventos(
            "recirculacao",
            f"SELECT rack_id AS alvo, t, tb AS v FROM racks_res WHERE {recirculacao}",
            lambda v, m: (
                f"Topo até {_numero(v)} °C mais quente que o normal em relação à base, "
                "com o meio subindo menos: ar quente voltando por cima"
            ),
            duracao_min=lim.recirculacao_min,
        )
        self._eventos(
            "rack_sobrecarregado",
            f"SELECT rack_id AS alvo, t, razao AS v FROM racks_res "
            f"WHERE razao >= {lim.sobrecarga_razao}",
            lambda v, m: f"Consumo até {v:.0%} do esperado para o horário, em relação ao hall",
            duracao_min=lim.sobrecarga_min,
        )
        # Um sensor de entrada com defeito discorda sozinho das outras duas alturas: o desvio
        # dele é o dobro do que aparece nas outras, e não segue o padrão da recirculação.
        alturas = ("base", "meio", "topo")
        partes = []
        for h in alturas:
            outras = [f"abs(e_{o})" for o in alturas if o != h]
            partes.append(f"""
                SELECT rack_id || '/entrada-{h}' AS alvo, t, abs(e_{h}) AS v FROM racks_res
                WHERE abs(e_{h}) >= {lim.deriva_c}
                    AND abs(e_{h}) >= 1.5 * greatest({", ".join(outras)})
                    AND NOT ({recirculacao})
            """)
        partes.append(f"""
            SELECT rack_id || '/saida' AS alvo, t, abs(e_saida) AS v FROM racks_res
            WHERE abs(e_saida) >= {lim.deriva_c}
        """)
        self._eventos(
            "sensor_deriva",
            " UNION ALL ".join(partes),
            lambda v, m: f"Discorda até {_numero(v)} °C do que os sensores vizinhos indicam",
            duracao_min=lim.deriva_min,
            juntar_min=60,
            cobertura=lim.deriva_cobertura,
        )

    # Etapa 4: CRACs. Uma falha de verdade aquece também a entrada dos racks da zona; um sensor
    # de insuflamento com defeito sobe sozinho.
    def _pesos_retorno(self, alcance_m: float) -> None:
        self.conexao.execute(f"""
            CREATE OR REPLACE TEMP TABLE pesos_retorno AS
            SELECT c.crac_id, r.rack_id,
                exp(-sqrt((c.x_m - r.x_m) ** 2 + (c.y_m - r.y_m) ** 2) / {alcance_m}) AS peso
            FROM cracs AS c CROSS JOIN racks AS r
        """)

    def _ajustar_alcance(self) -> float:
        """O ar que volta a um CRAC é uma média das saídas dos racks, pesada pela distância.

        O alcance dessa média (quanto o peso cai com a distância) é escolhido pelos próprios
        dados: o que melhor explica o retorno nos primeiros dias, sem olhar o gabarito.
        """
        erros: dict[float, float] = {}
        for alcance in ALCANCES_M:
            self._pesos_retorno(alcance)
            linha = self.conexao.execute("""
                WITH inicio AS (SELECT min(t) + INTERVAL 3 DAYS AS limite FROM cracs_min),
                ref AS (
                    SELECT p.crac_id, r.t, sum(p.peso * r.saida) / sum(p.peso) AS ref
                    FROM racks_min AS r JOIN pesos_retorno AS p USING (rack_id)
                    WHERE r.saida IS NOT NULL AND r.t < (SELECT limite FROM inicio)
                    GROUP BY ALL
                ),
                j AS (SELECT c.crac_id, c.retorno, ref.ref FROM cracs_min AS c
                    JOIN ref USING (crac_id, t) WHERE c.retorno IS NOT NULL),
                e AS (
                    SELECT retorno - (regr_intercept(retorno, ref) OVER p
                        + regr_slope(retorno, ref) OVER p * ref) AS erro
                    FROM j WINDOW p AS (PARTITION BY crac_id)
                )
                SELECT avg(erro * erro) FROM e
            """).fetchone()
            if linha and linha[0] is not None:
                erros[alcance] = float(linha[0])
        melhor = min(erros, key=erros.__getitem__) if erros else 1.5
        self._pesos_retorno(melhor)
        return melhor

    def _saidas_suspeitas(self) -> None:
        """Saídas de rack já acusadas de defeito não servem de referência para o retorno."""
        self.conexao.execute(
            "CREATE TEMP TABLE saidas_suspeitas (rack_id VARCHAR, inicio TIMESTAMPTZ, "
            "fim TIMESTAMPTZ)"
        )
        suspeitas = [
            (d.alvo.removesuffix("/saida"), d.inicio, d.fim)
            for d in self.deteccoes
            if d.tipo.startswith("sensor_") and d.alvo.endswith("/saida")
        ]
        if suspeitas:
            self.conexao.executemany("INSERT INTO saidas_suspeitas VALUES (?, ?, ?)", suspeitas)

    def _cracs(self) -> None:
        lim, c = self.lim, self.conexao
        self._saidas_suspeitas()
        self.parametros["alcance_retorno_m"] = self._ajustar_alcance()
        c.execute(f"""
            CREATE TEMP TABLE cracs_res AS
            WITH entradas AS (
                SELECT r.rack_id, k.zona_crac, r.t,
                    r.base + r.meio + r.topo - greatest(r.base, r.meio, r.topo)
                        - least(r.base, r.meio, r.topo) AS entrada
                FROM racks_min AS r JOIN racks AS k USING (rack_id)
            ),
            -- A zona é comparada com o hall inteiro no mesmo minuto.
            hall AS (SELECT t, median(entrada) AS entrada_hall FROM entradas GROUP BY t),
            zona AS (
                SELECT e.zona_crac AS crac_id, e.t, median(e.entrada) - h.entrada_hall AS entrada
                FROM entradas AS e JOIN hall AS h USING (t)
                GROUP BY e.zona_crac, e.t, h.entrada_hall
            ),
            saida_perto AS (
                SELECT p.crac_id, r.t, sum(p.peso * r.saida) / sum(p.peso) AS saida_perto
                FROM racks_min AS r JOIN pesos_retorno AS p USING (rack_id)
                ANTI JOIN saidas_suspeitas AS x
                    ON r.rack_id = x.rack_id AND r.t >= x.inicio AND r.t < x.fim
                WHERE r.saida IS NOT NULL
                GROUP BY ALL
            ),
            j AS (SELECT * FROM cracs_min JOIN zona USING (crac_id, t)
                JOIN saida_perto USING (crac_id, t)),
            reta AS ({_reta_robusta("j", "crac_id", "retorno", "saida_perto")})
            -- O insuflamento deveria estar no setpoint configurado no CRAC.
            SELECT j.crac_id, j.t, j.insuflamento - a.setpoint_c AS ins, j.entrada AS zona,
                j.retorno - (r.a + r.b * j.saida_perto) AS e_retorno
            FROM j JOIN cracs AS a USING (crac_id) JOIN reta AS r USING (crac_id)
        """)
        self._eventos(
            "falha_crac",
            f"SELECT crac_id AS alvo, t, ins AS v FROM cracs_res "
            f"WHERE ins >= {lim.crac_c} AND zona >= {lim.zona_c}",
            lambda v, m: (
                f"Insuflamento até {_numero(v)} °C acima do normal, "
                "com a entrada dos racks da zona subindo junto"
            ),
            duracao_min=lim.falha_min,
            juntar_min=15,
        )
        self._eventos(
            "super_refrigeracao",
            f"SELECT crac_id AS alvo, t, -ins AS v FROM cracs_res "
            f"WHERE ins <= -{lim.crac_c} AND zona <= -{lim.zona_c / 2}",
            lambda v, m: (
                f"Insuflamento até {_numero(v)} °C abaixo do normal por "
                f"{_numero(m / 60)} h, esfriando a zona"
            ),
            duracao_min=lim.super_refrigeracao_min,
            juntar_min=120,
        )
        self._eventos(
            "sensor_deriva",
            f"""
            SELECT crac_id || '/insuflamento' AS alvo, t, abs(ins) AS v FROM cracs_res
            WHERE abs(ins) >= {lim.deriva_c} AND abs(zona) < {lim.zona_c / 2}
            UNION ALL
            SELECT crac_id || '/retorno' AS alvo, t, abs(e_retorno) AS v FROM cracs_res
            WHERE abs(e_retorno) >= {lim.deriva_c}
            """,
            lambda v, m: f"Discorda até {_numero(v)} °C do que os racks da zona indicam",
            duracao_min=lim.deriva_min,
            juntar_min=60,
            cobertura=lim.deriva_cobertura,
        )

    def _preferir_causa_fisica(self) -> None:
        """Descarta a deriva de um sensor de CRAC quando o próprio CRAC tem um evento físico.

        Com dois eventos ao mesmo tempo (um CRAC super-refrigerando enquanto o vizinho falha),
        a zona pode esquentar pelo vizinho e o insuflamento frio parecer defeito do sensor. A
        explicação física, que envolve vários sensores, tem preferência.
        """
        fisicos = [d for d in self.deteccoes if d.tipo in ("falha_crac", "super_refrigeracao")]

        def explicado(d: Deteccao) -> bool:
            crac = d.alvo.split("/")[0]
            return any(
                f.alvo == crac and f.inicio < d.fim + FOLGA_CAUSA and d.inicio < f.fim + FOLGA_CAUSA
                for f in fisicos
            )

        self.deteccoes = [
            d
            for d in self.deteccoes
            if not (d.tipo == "sensor_deriva" and d.alvo.startswith("CRAC-") and explicado(d))
        ]

    def rodar(self) -> Resultado:
        inicio = time.perf_counter()
        try:
            self._medir("sensores", self._sensores)
            self._medir("tabelas", self._tabelas)
            self._medir("racks", self._racks)
            self._medir("cracs", self._cracs)
            self._preferir_causa_fisica()
        finally:
            self.conexao.close()
        deteccoes = sorted(self.deteccoes, key=lambda d: (d.inicio, d.tipo, d.alvo))
        return Resultado(
            deteccoes,
            self.lim,
            time.perf_counter() - inicio,
            self.nome_fonte,
            self.etapas,
            self.parametros,
        )


def detectar(diretorio: Path, limiares: Limiares | None = None) -> Resultado:
    """Procura anomalias na simulação, sem olhar o gabarito."""
    return Detector(diretorio, limiares).rodar()
