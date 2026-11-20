"""Planta do data hall: racks, CRACs, sensores e a influência de cada CRAC sobre cada rack."""

import string
from dataclasses import dataclass

import numpy as np
import pyarrow as pa

from isoterma.simulador.config import ConfigSimulacao

ALTURAS = ("base", "meio", "topo")
# Ordem dos sensores de cada rack e de cada CRAC. Ela define o sensor_id e as colunas da física.
SENSORES_RACK = (
    ("temp_entrada", "base"),
    ("temp_entrada", "meio"),
    ("temp_entrada", "topo"),
    ("temp_saida", None),
    ("potencia_kw", None),
)
SENSORES_CRAC = ("temp_insuflamento", "temp_retorno")
TIPOS_TEMPERATURA = frozenset({"temp_entrada", "temp_saida", "temp_insuflamento", "temp_retorno"})

# Recirculação de ar quente (°C somados à entrada): maior no topo e nas pontas das fileiras.
RECIRCULACAO_ALTURA_C = np.array([0.0, 0.4, 1.0])
RECIRCULACAO_PONTA_C = 1.2
DISTANCIA_PAREDE_CRAC_M = 1.5


@dataclass(frozen=True)
class Layout:
    rack_ids: list[str]
    rack_fileira: list[str]
    rack_posicao: np.ndarray
    rack_xy: np.ndarray  # (R, 2)
    potencia_nominal_kw: np.ndarray  # (R,)
    rack_denso: np.ndarray  # (R,) bool
    recirculacao_base_c: np.ndarray  # (R, 3) por altura
    crac_ids: list[str]
    crac_xy: np.ndarray  # (Z, 2)
    pesos: np.ndarray  # (R, Z): fração do ar de entrada de cada rack vinda de cada CRAC
    pesos_retorno: np.ndarray  # (Z, R): de quais racks vem o ar que volta a cada CRAC
    sensor_codigos: list[str]
    sensor_tipos: list[str]
    sensor_alturas: list[str | None]
    sensor_racks: list[str | None]
    sensor_cracs: list[str | None]
    sensor_xy: np.ndarray  # (S, 2)

    @property
    def total_racks(self) -> int:
        return len(self.rack_ids)

    @property
    def total_cracs(self) -> int:
        return len(self.crac_ids)

    @property
    def total_sensores(self) -> int:
        return len(self.sensor_codigos)

    @property
    def zona_crac(self) -> list[str]:
        """CRAC que mais influencia cada rack."""
        return [self.crac_ids[i] for i in self.pesos.argmax(axis=1)]

    def indice_sensor(self, codigo: str) -> int:
        return self.sensor_codigos.index(codigo)


def _posicoes_cracs(config: ConfigSimulacao) -> np.ndarray:
    """Metade dos CRACs na parede de cima e metade na de baixo, espaçados ao longo do hall."""
    hall = config.hall
    comprimento = (hall.racks_por_fileira - 1) * hall.passo_rack_m
    y_cima = -DISTANCIA_PAREDE_CRAC_M
    y_baixo = (hall.fileiras - 1) * hall.passo_fileira_m + DISTANCIA_PAREDE_CRAC_M
    n_cima = (hall.cracs + 1) // 2
    n_baixo = hall.cracs - n_cima
    posicoes: list[tuple[float, float]] = []
    for quantidade, y in ((n_cima, y_cima), (n_baixo, y_baixo)):
        for i in range(quantidade):
            posicoes.append(((i + 0.5) * comprimento / quantidade, y))
    return np.array(posicoes)


def montar_layout(config: ConfigSimulacao, rng: np.random.Generator) -> Layout:
    hall = config.hall
    termica = config.termica
    letras = string.ascii_uppercase

    rack_ids: list[str] = []
    rack_fileira: list[str] = []
    posicao: list[int] = []
    xy: list[tuple[float, float]] = []
    for f in range(hall.fileiras):
        for p in range(hall.racks_por_fileira):
            rack_ids.append(f"{letras[f]}-{p + 1:02d}")
            rack_fileira.append(letras[f])
            posicao.append(p + 1)
            xy.append((round(p * hall.passo_rack_m, 2), round(f * hall.passo_fileira_m, 2)))
    rack_xy = np.array(xy)
    rack_posicao = np.array(posicao)
    total_racks = len(rack_ids)

    rack_denso = rng.random(total_racks) < termica.fracao_racks_densos
    potencia_nominal = np.where(
        rack_denso,
        rng.uniform(*termica.potencia_densa_kw, total_racks),
        rng.uniform(*termica.potencia_padrao_kw, total_racks),
    )

    ponta = (rack_posicao == 1) | (rack_posicao == hall.racks_por_fileira)
    recirculacao = (
        RECIRCULACAO_ALTURA_C[None, :]
        + np.where(ponta, RECIRCULACAO_PONTA_C, 0.0)[:, None]
        + rng.uniform(0.0, 0.5, total_racks)[:, None]
    )

    crac_xy = _posicoes_cracs(config)
    crac_ids = [f"CRAC-{i + 1:02d}" for i in range(len(crac_xy))]
    distancias = np.linalg.norm(rack_xy[:, None, :] - crac_xy[None, :, :], axis=2)
    influencia = np.exp(-distancias / termica.alcance_crac_m)
    pesos = influencia / influencia.sum(axis=1, keepdims=True)
    pesos_retorno = (influencia / influencia.sum(axis=0, keepdims=True)).T

    codigos: list[str] = []
    tipos: list[str] = []
    alturas: list[str | None] = []
    racks_sensor: list[str | None] = []
    cracs_sensor: list[str | None] = []
    sensor_xy: list[np.ndarray] = []
    for r, rack in enumerate(rack_ids):
        for tipo, altura in SENSORES_RACK:
            sufixo = {"temp_entrada": f"entrada-{altura}", "temp_saida": "saida"}.get(
                tipo, "potencia"
            )
            codigos.append(f"{rack}/{sufixo}")
            tipos.append(tipo)
            alturas.append(altura)
            racks_sensor.append(rack)
            cracs_sensor.append(None)
            sensor_xy.append(rack_xy[r])
    for z, crac in enumerate(crac_ids):
        for tipo in SENSORES_CRAC:
            codigos.append(f"{crac}/{tipo.removeprefix('temp_')}")
            tipos.append(tipo)
            alturas.append(None)
            racks_sensor.append(None)
            cracs_sensor.append(crac)
            sensor_xy.append(crac_xy[z])

    return Layout(
        rack_ids=rack_ids,
        rack_fileira=rack_fileira,
        rack_posicao=rack_posicao,
        rack_xy=rack_xy,
        potencia_nominal_kw=potencia_nominal,
        rack_denso=rack_denso,
        recirculacao_base_c=recirculacao,
        crac_ids=crac_ids,
        crac_xy=crac_xy,
        pesos=pesos,
        pesos_retorno=pesos_retorno,
        sensor_codigos=codigos,
        sensor_tipos=tipos,
        sensor_alturas=alturas,
        sensor_racks=racks_sensor,
        sensor_cracs=cracs_sensor,
        sensor_xy=np.array(sensor_xy),
    )


def tabelas_dimensao(layout: Layout, setpoint_c: float) -> dict[str, pa.Table]:
    """Tabelas de apoio (racks, cracs e sensores) que acompanham as leituras."""
    racks = pa.table(
        {
            "rack_id": layout.rack_ids,
            "fileira": layout.rack_fileira,
            "posicao": pa.array(layout.rack_posicao, pa.int16()),
            "x_m": layout.rack_xy[:, 0],
            "y_m": layout.rack_xy[:, 1],
            "potencia_nominal_kw": np.round(layout.potencia_nominal_kw, 2),
            "perfil": ["denso" if d else "padrao" for d in layout.rack_denso],
            "zona_crac": layout.zona_crac,
        }
    )
    cracs = pa.table(
        {
            "crac_id": layout.crac_ids,
            "x_m": layout.crac_xy[:, 0],
            "y_m": layout.crac_xy[:, 1],
            "setpoint_c": [setpoint_c] * layout.total_cracs,
        }
    )
    sensores = pa.table(
        {
            "sensor_id": pa.array(range(layout.total_sensores), pa.int32()),
            "codigo": layout.sensor_codigos,
            "tipo": layout.sensor_tipos,
            "unidade": ["°C" if t in TIPOS_TEMPERATURA else "kW" for t in layout.sensor_tipos],
            "altura": layout.sensor_alturas,
            "rack_id": layout.sensor_racks,
            "crac_id": layout.sensor_cracs,
            "x_m": layout.sensor_xy[:, 0],
            "y_m": layout.sensor_xy[:, 1],
        }
    )
    return {"racks": racks, "cracs": cracs, "sensores": sensores}
