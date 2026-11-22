"""Roda os detectores num conjunto de simulações e gera o relatório em Markdown."""

import json
import platform
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from isoterma import __version__
from isoterma.anomalias.avaliacao import TIPOS, PlacarTipo, avaliar, ler_gabarito
from isoterma.anomalias.detectores import Limiares, detectar
from isoterma.dados import ler_manifesto

TITULOS_GRUPOS = {"calibracao": "Calibração", "validacao": "Validação", "teste": "Teste"}
DESCRICAO_GRUPOS = {
    "calibracao": "usadas para escolher os limiares",
    "validacao": "usadas para achar defeitos dos detectores, depois corrigidos",
    "teste": "rodadas uma única vez, com tudo congelado",
}


def avaliar_conjunto(
    diretorios: list[Path],
    grupo: str,
    limiares: Limiares | None = None,
    aviso: Callable[[str], None] = lambda _: None,
) -> dict[str, Any]:
    """Detecta e mede cada simulação; devolve o JSON do conjunto."""
    simulacoes: list[dict[str, Any]] = []
    por_tipo = {t: PlacarTipo() for t in TIPOS}
    for diretorio in diretorios:
        manifesto = ler_manifesto(diretorio)
        resultado = detectar(diretorio, limiares)
        avaliacao = avaliar(diretorio.name, resultado, ler_gabarito(diretorio))
        for tipo, placar in avaliacao.por_tipo.items():
            por_tipo.setdefault(tipo, PlacarTipo()).somar(placar)
        total = avaliacao.total
        aviso(
            f"{diretorio.name}: {total.detectados}/{total.incidentes} incidentes, "
            f"{total.corretas}/{total.deteccoes} alertas corretos, {resultado.segundos:.1f} s"
        )
        simulacoes.append(
            {
                **avaliacao.como_dict(),
                "seed": manifesto["config"]["seed"],
                "leituras": manifesto["contagens"]["linhas"],
                "sensores": manifesto["contagens"]["sensores"],
                "dias": round(
                    (
                        datetime.fromisoformat(manifesto["periodo"]["fim"])
                        - datetime.fromisoformat(manifesto["periodo"]["inicio"])
                    ).total_seconds()
                    / 86400,
                    1,
                ),
                "intervalo_s": manifesto["periodo"]["intervalo_s"],
                "parametros_ajustados": resultado.parametros,
            }
        )
    total = PlacarTipo()
    for placar in por_tipo.values():
        total.somar(placar)
    return {
        "grupo": grupo,
        "isoterma": __version__,
        "gerado_em": datetime.now(UTC).isoformat(timespec="seconds"),
        "maquina": {"sistema": platform.system(), "processador": platform.processor()},
        "limiares": (limiares or Limiares()).__dict__,
        "total": total.como_dict(),
        "por_tipo": {t: p.como_dict() for t, p in por_tipo.items()},
        "simulacoes": simulacoes,
    }


def salvar(conjunto: dict[str, Any], destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(conjunto, ensure_ascii=False, indent=2) + "\n"
    destino.write_text(texto, encoding="utf-8", newline="\n")


def carregar(arquivo: Path) -> dict[str, Any]:
    return json.loads(arquivo.read_text(encoding="utf-8"))


# --- Markdown -------------------------------------------------------------------------------

NOMES = {
    "falha_crac": "Falha de CRAC",
    "super_refrigeracao": "Super-refrigeração",
    "rack_sobrecarregado": "Rack sobrecarregado",
    "recirculacao": "Recirculação",
    "sensor_congelado": "Sensor congelado",
    "sensor_deriva": "Sensor com deriva",
    "sensor_picos": "Sensor com picos",
    "sensor_sem_leitura": "Sensor sem leitura",
}


def _pct(valor: float | None) -> str:
    if valor is None:
        return "—"
    casas = 0 if round(valor * 100, 1).is_integer() else 1
    return f"{valor:.{casas}%}".replace(".", ",")


def _minutos(valor: float | None) -> str:
    if valor is None:
        return "—"
    if valor >= 90:
        return f"{valor / 60:.1f} h".replace(".", ",")
    return f"{valor:.0f} min"


def _milhoes(n: int) -> str:
    if n >= 1_000_000_000:
        return f"{n / 1e9:.1f} bi".replace(".", ",")
    return f"{n / 1e6:.0f} mi"


def _tabela_tipos(conjunto: dict[str, Any]) -> list[str]:
    linhas = [
        "| Tipo | Incidentes | Detectados | Alertas corretos | Precisão | Recall | F1 "
        "| Atraso mediano |",
        "|---|--:|--:|--:|--:|--:|--:|--:|",
    ]
    itens = [(NOMES.get(t, t), p) for t, p in conjunto["por_tipo"].items()]
    itens.append(("**Total**", conjunto["total"]))
    for nome, p in itens:
        if not p["incidentes"] and not p["deteccoes"] and not p["invisiveis"]:
            continue
        n = p["invisiveis"]
        invisiveis = f" (+{n} invisíve{'is' if n > 1 else 'l'})" if n else ""
        linhas.append(
            f"| {nome} | {p['incidentes']}{invisiveis} | {p['detectados']} "
            f"| {p['corretas']} de {p['deteccoes']} | {_pct(p['precisao'])} "
            f"| {_pct(p['recall'])} | {_pct(p['f1'])} | {_minutos(p['atraso_mediano_min'])} |"
        )
    return linhas


def _tabela_simulacoes(conjunto: dict[str, Any]) -> list[str]:
    linhas = [
        "| Simulação | Seed | Leituras | Período | Incidentes | Precisão | Recall | Tempo |",
        "|---|--:|--:|--:|--:|--:|--:|--:|",
    ]
    for s in conjunto["simulacoes"]:
        t = s["total"]
        periodo = f"{s['dias']:g} d a cada {s['intervalo_s']} s".replace(".", ",")
        linhas.append(
            f"| `{s['simulacao']}` | {s['seed']} | {_milhoes(s['leituras'])} | {periodo} "
            f"| {t['incidentes']} | {_pct(t['precisao'])} | {_pct(t['recall'])} "
            f"| {s['segundos']:.0f} s |".replace(".", ",")
        )
    return linhas


def _erros(conjunto: dict[str, Any]) -> list[str]:
    linhas: list[str] = []
    for s in conjunto["simulacoes"]:
        for i in s["perdidos"]:
            linhas.append(
                f"- **Perdido** em `{s['simulacao']}`: {NOMES.get(i['tipo'], i['tipo'])} "
                f"em `{i['alvo']}` ({i['descricao']})"
            )
        # Alertas falsos repetidos no mesmo sensor viram uma linha só.
        grupos: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for d in s["falsos"]:
            grupos.setdefault((d["tipo"], d["alvo"]), []).append(d)
        for (tipo, alvo), falsos in grupos.items():
            vezes = f"{len(falsos)} alertas falsos" if len(falsos) > 1 else "Alerta falso"
            linhas.append(
                f"- **{vezes}** em `{s['simulacao']}`: {NOMES.get(tipo, tipo)} em `{alvo}`, "
                f"a partir de {falsos[0]['inicio'][:16]} UTC ({falsos[0]['evidencia']})"
            )
        for i in s.get("invisiveis", []):
            linhas.append(
                f"- **Invisível** em `{s['simulacao']}`: {NOMES.get(i['tipo'], i['tipo'])} "
                f"em `{i['alvo']}`. O defeito não chegou a afetar nenhuma leitura."
            )
    return linhas or ["Nenhum incidente perdido e nenhum alerta falso."]


def gerar_relatorio(conjuntos: list[dict[str, Any]]) -> str:
    ordem = list(DESCRICAO_GRUPOS)
    conjuntos = sorted(
        conjuntos, key=lambda c: ordem.index(c["grupo"]) if c["grupo"] in ordem else 99
    )
    teste = next((c for c in conjuntos if c["grupo"] == "teste"), conjuntos[-1])
    t = teste["total"]
    partes = [
        "# Detecção de anomalias: resultados",
        "",
        "> Gerado por `isoterma relatorio-deteccao` a partir dos JSONs em `docs/deteccao/`. "
        "O método está em [ANOMALIAS.md](ANOMALIAS.md).",
        "",
        f"No conjunto de **{teste['grupo']}**, os detectores acharam **{t['detectados']} de "
        f"{t['incidentes']}** incidentes (recall {_pct(t['recall'])}), e **{t['corretas']} de "
        f"{t['deteccoes']}** alertas correspondiam a um incidente real (precisão "
        f"{_pct(t['precisao'])}).",
        "",
        "Uma detecção conta como certa quando tem o mesmo tipo e o mesmo alvo de um incidente do "
        "gabarito, e o período dela encosta no dele (folga de 30 min). O atraso é o tempo entre "
        "o início do incidente e o primeiro alerta. Incidentes **invisíveis** são os que não "
        "afetaram nenhuma leitura (um defeito de picos que, no sorteio, não gerou pico) e ficam "
        "fora do recall.",
        "",
    ]
    for conjunto in conjuntos:
        descricao = DESCRICAO_GRUPOS.get(conjunto["grupo"], "")
        partes += [
            f"## {TITULOS_GRUPOS.get(conjunto['grupo'], conjunto['grupo'])}"
            + (f": {descricao}" if descricao else ""),
            "",
            *_tabela_tipos(conjunto),
            "",
            *_tabela_simulacoes(conjunto),
            "",
            "**Erros:**",
            "",
            *_erros(conjunto),
            "",
        ]
    maquina = teste["maquina"]
    partes += [
        f"Medido com o Isoterma {teste['isoterma']} em {teste['gerado_em'][:10]}, "
        f"{maquina['sistema']} ({maquina['processador'] or 'processador não informado'}). "
        "O tempo inclui ler os dados, rodar todos os detectores e ajustar o modelo do retorno.",
        "",
    ]
    return "\n".join(partes)
