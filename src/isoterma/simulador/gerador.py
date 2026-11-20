"""Geração das leituras em blocos independentes, em paralelo, gravadas em Parquet por dia."""

import json
import math
import os
import shutil
import time
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from isoterma import __version__
from isoterma.dados import MANIFESTO
from isoterma.simulador.config import ConfigSimulacao, TipoIncidente
from isoterma.simulador.esquema import ESQUEMA
from isoterma.simulador.fisica import PASSO_DRIVER_S, calcular_drivers
from isoterma.simulador.incidentes import Incidente, sortear_incidentes, tabela_incidentes
from isoterma.simulador.layout import (
    SENSORES_RACK,
    TIPOS_TEMPERATURA,
    Layout,
    montar_layout,
    tabelas_dimensao,
)

TIPO_TS = pa.timestamp("ms", tz="UTC")
MAGNITUDE_PICO_C = (8.0, 25.0)
TIPOS_DEFEITO_SENSOR = frozenset(
    {
        TipoIncidente.SENSOR_CONGELADO,
        TipoIncidente.SENSOR_DERIVA,
        TipoIncidente.SENSOR_PICOS,
        TipoIncidente.SENSOR_SEM_LEITURA,
    }
)

# Cada etapa sorteia de um fluxo próprio, derivado da seed. Assim o resultado não depende
# da ordem em que os blocos terminam nem de quantos processos foram usados.
FLUXO_LAYOUT, FLUXO_INCIDENTES, FLUXO_FISICA, FLUXO_BLOCOS = range(4)


def _rng(seed: int, *fluxo: int) -> np.random.Generator:
    return np.random.default_rng(np.random.SeedSequence(seed, spawn_key=fluxo))


@dataclass(frozen=True)
class Bloco:
    indice: int
    passo_inicio: int
    passo_fim: int
    dia: str  # data UTC da partição, AAAA-MM-DD


@dataclass(frozen=True)
class DefeitoSensor:
    tipo: TipoIncidente
    sensor: int
    inicio_s: int
    fim_s: int
    intensidade: float


@dataclass(frozen=True)
class _Contexto:
    """Tudo o que um processo precisa para gerar qualquer bloco."""

    drivers: np.ndarray
    intervalo_s: int
    inicio_ms: int
    ruido: np.ndarray  # desvio-padrão do ruído de cada sensor
    escala: np.ndarray  # 10 = uma casa decimal, 100 = duas
    defeitos: tuple[DefeitoSensor, ...]
    seed: int
    diretorio: Path


@dataclass(frozen=True)
class ResultadoSimulacao:
    diretorio: Path
    linhas: int
    sensores: int
    racks: int
    cracs: int
    incidentes: int
    blocos: int
    processos: int
    segundos: float
    bytes_em_disco: int

    @property
    def linhas_por_segundo(self) -> float:
        return self.linhas / self.segundos if self.segundos else 0.0


def planejar_blocos(config: ConfigSimulacao) -> list[Bloco]:
    """Divide o período em blocos que nunca atravessam a meia-noite UTC."""
    periodo = config.periodo
    passos_por_bloco = max(1, config.linhas_por_bloco // config.total_sensores)
    blocos: list[Bloco] = []
    passo = 0
    while passo < periodo.passos:
        instante = periodo.inicio + timedelta(seconds=passo * periodo.intervalo_s)
        meia_noite = datetime.combine(instante.date() + timedelta(days=1), datetime.min.time(), UTC)
        ate_meia_noite = (meia_noite - periodo.inicio).total_seconds() / periodo.intervalo_s
        fim_dia = min(periodo.passos, math.ceil(ate_meia_noite))
        for inicio in range(passo, fim_dia, passos_por_bloco):
            fim = min(inicio + passos_por_bloco, fim_dia)
            blocos.append(Bloco(len(blocos), inicio, fim, instante.date().isoformat()))
        passo = fim_dia
    return blocos


def _interpolar(drivers: np.ndarray, tempos_s: np.ndarray) -> np.ndarray:
    posicao = tempos_s / PASSO_DRIVER_S
    anterior = posicao.astype(np.int64)
    fracao = (posicao - anterior).astype(np.float32)
    if not fracao.any():
        return drivers[anterior].copy()
    return drivers[anterior] * (1 - fracao[:, None]) + drivers[anterior + 1] * fracao[:, None]


def _aplicar_defeito(
    valores: np.ndarray,
    tempos_s: np.ndarray,
    defeito: DefeitoSensor,
    ctx: _Contexto,
    rng: np.random.Generator,
) -> None:
    linhas = np.flatnonzero((tempos_s >= defeito.inicio_s) & (tempos_s < defeito.fim_s))
    if linhas.size == 0:
        return
    s = defeito.sensor
    match defeito.tipo:
        case TipoIncidente.SENSOR_CONGELADO:
            inicio = np.array([defeito.inicio_s], dtype=np.int64)
            congelado = _interpolar(ctx.drivers[:, s : s + 1], inicio)[0, 0]
            valores[linhas, s] = congelado
        case TipoIncidente.SENSOR_DERIVA:
            horas = (tempos_s[linhas] - defeito.inicio_s) / 3600
            valores[linhas, s] += (defeito.intensidade * horas).astype(np.float32)
        case TipoIncidente.SENSOR_PICOS:
            afetadas = linhas[rng.random(linhas.size) < defeito.intensidade]
            sinais = rng.choice(np.array([-1.0, 1.0]), afetadas.size)
            valores[afetadas, s] += sinais * rng.uniform(*MAGNITUDE_PICO_C, afetadas.size)
        case TipoIncidente.SENSOR_SEM_LEITURA:
            valores[linhas[rng.random(linhas.size) < defeito.intensidade], s] = np.nan
        case _:
            raise ValueError(f"{defeito.tipo} não é um defeito de sensor")


def _gerar_bloco(ctx: _Contexto, bloco: Bloco) -> int:
    passos = np.arange(bloco.passo_inicio, bloco.passo_fim, dtype=np.int64)
    tempos_s = passos * ctx.intervalo_s
    rng = _rng(ctx.seed, FLUXO_BLOCOS, bloco.indice)

    valores = _interpolar(ctx.drivers, tempos_s)
    valores += rng.standard_normal(valores.shape, dtype=np.float32) * ctx.ruido
    for defeito in ctx.defeitos:
        if defeito.inicio_s <= tempos_s[-1] and defeito.fim_s > tempos_s[0]:
            _aplicar_defeito(valores, tempos_s, defeito, ctx, rng)
    valores = np.round(valores * ctx.escala) / ctx.escala

    n_passos, n_sensores = valores.shape
    plano = valores.ravel()
    tabela = pa.table(
        {
            "ts": pa.array(np.repeat(ctx.inicio_ms + tempos_s * 1000, n_sensores), TIPO_TS),
            "sensor_id": pa.array(np.tile(np.arange(n_sensores, dtype=np.int32), n_passos)),
            "valor": pa.array(plano, mask=np.isnan(plano)),
        }
    )
    pasta = ctx.diretorio / "leituras" / f"data={bloco.dia}"
    pasta.mkdir(parents=True, exist_ok=True)
    pq.write_table(tabela, pasta / f"parte-{bloco.indice:05d}.parquet", compression="zstd")
    return tabela.num_rows


_CONTEXTO_PROCESSO: _Contexto | None = None


def _inicializar_processo(ctx: _Contexto) -> None:
    global _CONTEXTO_PROCESSO
    _CONTEXTO_PROCESSO = ctx


def _gerar_bloco_no_processo(bloco: Bloco) -> int:
    assert _CONTEXTO_PROCESSO is not None
    return _gerar_bloco(_CONTEXTO_PROCESSO, bloco)


def _preparar_diretorio(saida: Path, sobrescrever: bool) -> None:
    if saida.exists() and any(saida.iterdir()):
        if not sobrescrever:
            raise FileExistsError(
                f"{saida} já existe. Use --sobrescrever para gerar a simulação de novo."
            )
        if not (saida / MANIFESTO).exists():
            raise FileExistsError(
                f"{saida} não parece uma simulação do Isoterma (falta {MANIFESTO}). "
                "Por segurança, nada foi apagado."
            )
        shutil.rmtree(saida)
    saida.mkdir(parents=True, exist_ok=True)


def _ruido_e_escala(config: ConfigSimulacao, layout: Layout) -> tuple[np.ndarray, np.ndarray]:
    temperatura = np.array([t in TIPOS_TEMPERATURA for t in layout.sensor_tipos])
    potencia = np.zeros(layout.total_sensores)
    potencia[
        len(SENSORES_RACK) - 1 : layout.total_racks * len(SENSORES_RACK) : len(SENSORES_RACK)
    ] = layout.potencia_nominal_kw * config.termica.ruido_potencia
    ruido = np.where(temperatura, config.termica.ruido_temperatura_c, potencia)
    escala = np.where(temperatura, 10.0, 100.0)
    return ruido.astype(np.float32), escala.astype(np.float32)


def _defeitos(incidentes: list[Incidente], layout: Layout) -> tuple[DefeitoSensor, ...]:
    return tuple(
        DefeitoSensor(
            inc.tipo, layout.indice_sensor(inc.alvo), inc.inicio_s, inc.fim_s, inc.intensidade
        )
        for inc in incidentes
        if inc.tipo in TIPOS_DEFEITO_SENSOR
    )


def simular(
    config: ConfigSimulacao,
    saida: Path,
    *,
    processos: int | None = None,
    sobrescrever: bool = False,
    progresso: Callable[[int], None] | None = None,
) -> ResultadoSimulacao:
    """Gera uma simulação completa em ``saida`` e devolve um resumo.

    ``progresso`` recebe o número de linhas de cada bloco concluído.
    """
    relogio = time.perf_counter()
    _preparar_diretorio(saida, sobrescrever)

    layout = montar_layout(config, _rng(config.seed, FLUXO_LAYOUT))
    incidentes = sortear_incidentes(config, layout, _rng(config.seed, FLUXO_INCIDENTES))
    drivers = calcular_drivers(config, layout, incidentes, _rng(config.seed, FLUXO_FISICA))

    for nome, tabela in tabelas_dimensao(layout, config.termica.setpoint_c).items():
        pq.write_table(tabela, saida / f"{nome}.parquet")
    pq.write_table(
        tabela_incidentes(incidentes, config.periodo.inicio), saida / "incidentes.parquet"
    )

    ruido, escala = _ruido_e_escala(config, layout)
    ctx = _Contexto(
        drivers=drivers,
        intervalo_s=config.periodo.intervalo_s,
        inicio_ms=int(config.periodo.inicio.timestamp() * 1000),
        ruido=ruido,
        escala=escala,
        defeitos=_defeitos(incidentes, layout),
        seed=config.seed,
        diretorio=saida,
    )
    blocos = planejar_blocos(config)
    processos = max(1, min(processos or os.cpu_count() or 1, len(blocos)))

    linhas = 0
    if processos == 1:
        resultados = (_gerar_bloco(ctx, bloco) for bloco in blocos)
        for n in resultados:
            linhas += n
            if progresso:
                progresso(n)
    else:
        with ProcessPoolExecutor(
            processos, initializer=_inicializar_processo, initargs=(ctx,)
        ) as executor:
            for n in executor.map(_gerar_bloco_no_processo, blocos):
                linhas += n
                if progresso:
                    progresso(n)

    segundos = time.perf_counter() - relogio
    resultado = ResultadoSimulacao(
        diretorio=saida,
        linhas=linhas,
        sensores=layout.total_sensores,
        racks=layout.total_racks,
        cracs=layout.total_cracs,
        incidentes=len(incidentes),
        blocos=len(blocos),
        processos=processos,
        segundos=segundos,
        bytes_em_disco=sum(f.stat().st_size for f in saida.rglob("*.parquet")),
    )
    _escrever_manifesto(config, resultado)
    return resultado


def _escrever_manifesto(config: ConfigSimulacao, resultado: ResultadoSimulacao) -> None:
    periodo = config.periodo
    manifesto = {
        "isoterma": __version__,
        "gerado_em": datetime.now(UTC).isoformat(timespec="seconds"),
        "periodo": {
            "inicio": periodo.inicio.isoformat(),
            "fim": (periodo.inicio + timedelta(seconds=periodo.duracao_s)).isoformat(),
            "intervalo_s": periodo.intervalo_s,
        },
        "contagens": {
            "linhas": resultado.linhas,
            "sensores": resultado.sensores,
            "racks": resultado.racks,
            "cracs": resultado.cracs,
            "incidentes": resultado.incidentes,
        },
        "geracao": {
            "segundos": round(resultado.segundos, 2),
            "processos": resultado.processos,
            "blocos": resultado.blocos,
            "bytes_em_disco": resultado.bytes_em_disco,
        },
        "arquivos": {
            "leituras": "leituras/data=*/*.parquet",
            **{nome: f"{nome}.parquet" for nome in ("sensores", "racks", "cracs", "incidentes")},
        },
        "config": config.model_dump(mode="json"),
        "esquema": ESQUEMA,
    }
    (resultado.diretorio / MANIFESTO).write_text(
        json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8"
    )
