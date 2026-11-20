"""Consultas de domínio sobre uma simulação: o que a CLI, a API e a IA vão usar."""

import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType
from typing import Any, Self
from zoneinfo import ZoneInfo

import pyarrow as pa

from isoterma.dados import GRANULARIDADES, conectar, ler_manifesto, pasta_agregados
from isoterma.motor import sql_seguro
from isoterma.motor.camadas import ESQUEMA_AGREGADOS, Camada, camada_agregada, camada_bruta
from isoterma.simulador.esquema import FAIXA_ASHRAE_C

TIPOS_DE_RACK = ("temp_entrada", "temp_saida", "potencia_kw")
ALTURAS = ("base", "meio", "topo")
BUCKETS_S = (1, 5, 10, 15, 30, 60, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400)


def _alinhado(instante: datetime, segundos: int) -> bool:
    return int(instante.timestamp()) % segundos == 0


def escolher_bucket(janela_s: float, max_pontos: int, intervalo_s: int) -> int:
    """O menor intervalo "redondo" que mostra a janela em até ``max_pontos`` pontos."""
    necessario = janela_s / max_pontos
    redondos = [b for b in BUCKETS_S if b >= intervalo_s and b % intervalo_s == 0]
    for bucket in [intervalo_s, *redondos]:
        if bucket >= necessario:
            return bucket
    return math.ceil(necessario / 86_400) * 86_400


class Hall:
    """Uma simulação aberta para consulta, sempre por uma conexão em modo seguro.

    Datas sem fuso são interpretadas no horário local do hall (o fuso da simulação).
    """

    def __init__(self, diretorio: Path) -> None:
        self.diretorio = diretorio.resolve()
        self.manifesto = ler_manifesto(self.diretorio)
        periodo = self.manifesto["periodo"]
        self.inicio = datetime.fromisoformat(periodo["inicio"]).astimezone(UTC)
        self.fim = datetime.fromisoformat(periodo["fim"]).astimezone(UTC)
        self.intervalo_s: int = periodo["intervalo_s"]
        self.fuso = ZoneInfo(self.manifesto["config"]["periodo"]["fuso"])
        self.camadas: list[Camada] = [camada_bruta(self.intervalo_s)] + [
            camada_agregada(nome)
            for nome in GRANULARIDADES
            if pasta_agregados(self.diretorio, nome).is_dir()
        ]
        self._db = conectar(self.diretorio, seguro=True)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        tipo: type[BaseException] | None,
        erro: BaseException | None,
        rastro: TracebackType | None,
    ) -> None:
        self.fechar()

    def fechar(self) -> None:
        self._db.close()

    # --- apoio -----------------------------------------------------------------------------

    def em_utc(self, instante: datetime | None, padrao: datetime) -> datetime:
        if instante is None:
            return padrao
        if instante.tzinfo is None:
            instante = instante.replace(tzinfo=self.fuso)
        return instante.astimezone(UTC)

    def _janela(self, inicio: datetime | None, fim: datetime | None) -> tuple[datetime, datetime]:
        ini, f = self.em_utc(inicio, self.inicio), self.em_utc(fim, self.fim)
        if ini >= f:
            raise ValueError("O início da janela precisa ser anterior ao fim")
        if ini >= self.fim or f <= self.inicio:
            raise ValueError(
                f"A janela fica fora da simulação, que vai de {self.inicio:%Y-%m-%d %H:%M} "
                f"a {self.fim:%Y-%m-%d %H:%M} UTC"
            )
        return max(ini, self.inicio), min(f, self.fim)

    def _camada(self, inicio: datetime, fim: datetime, granularidade_max: int | None) -> Camada:
        """A camada mais grossa que respeita a granularidade pedida e alinha com a janela.

        Um agregado por hora só serve para uma janela que começa e termina em hora cheia;
        senão, os intervalos das bordas trariam leituras de fora da janela. As bordas que
        coincidem com o começo ou o fim da simulação não precisam de alinhamento: além delas
        não há leituras.
        """

        def serve(camada: Camada) -> bool:
            g = camada.granularidade_s
            if granularidade_max is not None and (g > granularidade_max or granularidade_max % g):
                return False
            inicio_ok = inicio <= self.inicio or _alinhado(inicio, g)
            fim_ok = fim >= self.fim or _alinhado(fim, g)
            return camada.bruta or (inicio_ok and fim_ok)

        return max(filter(serve, self.camadas), key=lambda c: c.granularidade_s)

    def _tabela(self, sql: str, **parametros: Any) -> pa.Table:
        cursor = self._db.cursor()
        try:
            tabela = cursor.sql(sql, params=parametros).to_arrow_table()
        finally:
            cursor.close()
        return sql_seguro.arredondar_float32(tabela)

    def _validar_alvo(self, alvo: str) -> None:
        encontrados = self._tabela(
            "SELECT count(*) AS n FROM sensores WHERE $alvo IN (codigo, rack_id, crac_id)",
            alvo=alvo,
        )
        if encontrados.column("n")[0].as_py() == 0:
            raise ValueError(f"{alvo!r} não é um sensor, rack ou CRAC desta simulação")

    # --- consultas de domínio --------------------------------------------------------------

    def serie(
        self,
        alvo: str,
        inicio: datetime | None = None,
        fim: datetime | None = None,
        *,
        max_pontos: int = 500,
    ) -> pa.Table:
        """Série temporal de um sensor, de todos os sensores de um rack ou de um CRAC.

        O intervalo entre pontos se ajusta à janela, e a fonte (leituras brutas ou agregados)
        é escolhida sozinha.
        """
        ini, f = self._janela(inicio, fim)
        self._validar_alvo(alvo)
        bucket = escolher_bucket((f - ini).total_seconds(), max_pontos, self.intervalo_s)
        c = self._camada(ini, f, bucket)
        return self._tabela(
            f"""
            SELECT
                time_bucket(INTERVAL '{bucket} seconds', f.{c.coluna_ts}) AS inicio,
                s.codigo AS sensor,
                s.tipo,
                s.unidade,
                round(({c.minimo})::DOUBLE, 2) AS minimo,
                round(({c.media})::DOUBLE, 2) AS media,
                round(({c.maximo})::DOUBLE, 2) AS maximo,
                ({c.leituras})::BIGINT AS leituras
            FROM {c.tabela} AS f JOIN sensores AS s USING (sensor_id)
            WHERE $alvo IN (s.codigo, s.rack_id, s.crac_id)
              AND f.{c.coluna_ts} >= $inicio AND f.{c.coluna_ts} < $fim
            GROUP BY ALL
            ORDER BY sensor, inicio
            """,
            alvo=alvo,
            inicio=ini,
            fim=f,
        )

    def mapa_termico(
        self,
        instante: datetime | None = None,
        *,
        tipo: str = "temp_entrada",
        altura: str | None = None,
        janela: timedelta = timedelta(minutes=5),
    ) -> pa.Table:
        """Valor de cada rack num instante: a média dos últimos minutos de cada sensor.

        Sem ``altura``, usa a altura mais quente do rack. Para ``temp_entrada``, a coluna
        ``faixa`` diz se o rack está acima, abaixo ou dentro da faixa ASHRAE.
        """
        if tipo not in TIPOS_DE_RACK:
            raise ValueError(f"tipo deve ser um de: {', '.join(TIPOS_DE_RACK)}")
        if altura is not None and (tipo != "temp_entrada" or altura not in ALTURAS):
            raise ValueError("altura só vale para temp_entrada e deve ser base, meio ou topo")
        fim = self.em_utc(instante, self.fim)
        if not self.inicio < fim <= self.fim:
            raise ValueError(
                f"O instante fica fora da simulação ({self.inicio:%Y-%m-%d %H:%M} a "
                f"{self.fim:%Y-%m-%d %H:%M} UTC)"
            )
        minimo_c, maximo_c = FAIXA_ASHRAE_C
        return self._tabela(
            f"""
            WITH por_sensor AS (
                SELECT s.rack_id, avg(l.valor) AS valor
                FROM leituras AS l JOIN sensores AS s USING (sensor_id)
                WHERE s.tipo = $tipo
                  AND ($altura::VARCHAR IS NULL OR s.altura = $altura::VARCHAR)
                  AND l.ts > $inicio AND l.ts <= $fim
                GROUP BY s.sensor_id, s.rack_id
            )
            SELECT
                r.rack_id, r.fileira, r.posicao, r.x_m, r.y_m, r.zona_crac,
                round(max(p.valor), 1) AS valor,
                CASE
                    WHEN NOT $avaliar OR max(p.valor) IS NULL THEN NULL
                    WHEN max(p.valor) > {maximo_c} THEN 'acima'
                    WHEN min(p.valor) < {minimo_c} THEN 'abaixo'
                    ELSE 'ok'
                END AS faixa
            FROM racks AS r LEFT JOIN por_sensor AS p USING (rack_id)
            GROUP BY ALL
            ORDER BY r.fileira, r.posicao
            """,
            tipo=tipo,
            altura=altura,
            avaliar=tipo == "temp_entrada",
            inicio=max(fim - janela, self.inicio),
            fim=fim,
        )

    def fora_da_faixa(
        self, inicio: datetime | None = None, fim: datetime | None = None
    ) -> pa.Table:
        """Racks que saíram da faixa ASHRAE (18–27 °C na entrada), com a duração em minutos."""
        ini, f = self._janela(inicio, fim)
        passo = 60 if self.intervalo_s < 60 and 60 % self.intervalo_s == 0 else self.intervalo_s
        c = self._camada(ini, f, passo)
        minimo_c, maximo_c = FAIXA_ASHRAE_C
        minutos_por_passo = passo / 60
        return self._tabela(
            f"""
            WITH por_passo AS (
                SELECT
                    s.rack_id,
                    time_bucket(INTERVAL '{passo} seconds', f.{c.coluna_ts}) AS instante,
                    {c.maximo} AS pico,
                    {c.minimo} AS vale
                FROM {c.tabela} AS f JOIN sensores AS s USING (sensor_id)
                WHERE s.tipo = 'temp_entrada'
                  AND f.{c.coluna_ts} >= $inicio AND f.{c.coluna_ts} < $fim
                GROUP BY ALL
            ),
            marcado AS (
                SELECT *, pico > {maximo_c} AS acima, vale < {minimo_c} AS abaixo FROM por_passo
            )
            SELECT
                rack_id, r.fileira, r.zona_crac,
                round(count(*) FILTER (acima) * {minutos_por_passo}, 1)::DOUBLE AS minutos_acima,
                round(count(*) FILTER (abaixo) * {minutos_por_passo}, 1)::DOUBLE AS minutos_abaixo,
                round(max(pico)::DOUBLE, 1) AS pico_c,
                round(min(vale)::DOUBLE, 1) AS minimo_c,
                min(instante) FILTER (acima OR abaixo) AS primeira_vez,
                max(instante) FILTER (acima OR abaixo) + INTERVAL '{passo} seconds' AS ultima_vez
            FROM marcado JOIN racks AS r USING (rack_id)
            GROUP BY ALL
            HAVING bool_or(acima OR abaixo)
            ORDER BY minutos_acima + minutos_abaixo DESC, rack_id
            """,
            inicio=ini,
            fim=f,
        )

    def resumo(self, inicio: datetime | None = None, fim: datetime | None = None) -> dict[str, Any]:
        """Visão geral do hall numa janela: volume de dados, temperaturas, potência e alertas."""
        ini, f = self._janela(inicio, fim)
        c = self._camada(ini, f, None)
        por_tipo = self._tabela(
            f"""
            SELECT
                s.tipo,
                ({c.total})::BIGINT AS total,
                ({c.nulos})::BIGINT AS nulos,
                round(({c.minimo})::DOUBLE, 1) AS minimo,
                round(({c.media})::DOUBLE, 2) AS media,
                round(({c.maximo})::DOUBLE, 1) AS maximo
            FROM {c.tabela} AS f JOIN sensores AS s USING (sensor_id)
            WHERE f.{c.coluna_ts} >= $inicio AND f.{c.coluna_ts} < $fim
            GROUP BY ALL
            ORDER BY s.tipo
            """,
            inicio=ini,
            fim=f,
        ).to_pylist()
        contagens = self.manifesto["contagens"]
        potencia = next((t["media"] for t in por_tipo if t["tipo"] == "potencia_kw"), None)
        fora = self.fora_da_faixa(ini, f)
        return {
            "inicio": ini,
            "fim": f,
            "fonte": c.tabela,
            "racks": contagens["racks"],
            "cracs": contagens["cracs"],
            "sensores": contagens["sensores"],
            "leituras": sum(t["total"] for t in por_tipo),
            "leituras_nulas": sum(t["nulos"] for t in por_tipo),
            "potencia_media_total_kw": (
                round(potencia * contagens["racks"], 1) if potencia is not None else None
            ),
            "racks_acima_da_faixa": sum(1 for m in fora.column("minutos_acima").to_pylist() if m),
            "racks_abaixo_da_faixa": sum(1 for m in fora.column("minutos_abaixo").to_pylist() if m),
            "por_tipo": {
                t["tipo"]: {k: t[k] for k in ("minimo", "media", "maximo")} for t in por_tipo
            },
        }

    def consultar(
        self, sql: str, *, limite: int = 1_000, tempo_max_s: float = 30.0
    ) -> sql_seguro.ResultadoConsulta:
        """Executa um SELECT livre, com as proteções de ``sql_seguro``."""
        return sql_seguro.executar(self._db, sql, limite=limite, tempo_max_s=tempo_max_s)

    def esquema(self) -> dict[str, dict[str, str]]:
        """Dicionário de dados das tabelas disponíveis nesta simulação."""
        esquema = dict(self.manifesto["esquema"])
        for camada in self.camadas:
            if not camada.bruta:
                esquema[camada.tabela] = ESQUEMA_AGREGADOS
        return esquema
