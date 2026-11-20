"""Formatação para o terminal: números no padrão brasileiro, tabelas e o mapa térmico."""

import itertools
from datetime import datetime, tzinfo
from typing import Any

import pyarrow as pa
import typer

# Escala de cores do mapa: azul (frio) → verde → amarelo → vermelho (quente).
GRADIENTE: list[tuple[float, tuple[int, int, int]]] = [
    (0.0, (49, 130, 206)),
    (0.35, (56, 178, 172)),
    (0.55, (104, 190, 95)),
    (0.75, (236, 201, 75)),
    (1.0, (229, 62, 62)),
]
# Também muda o caractere, para o mapa continuar legível sem cores.
BLOCOS = ("░░", "▒▒", "▓▓", "██")
ESCALAS: dict[str, tuple[float, float, str]] = {
    "temp_entrada": (16.0, 30.0, "°C"),
    "temp_saida": (25.0, 45.0, "°C"),
    "potencia_kw": (0.0, 16.0, "kW"),
}


def numero(n: float, casas: int = 0) -> str:
    """Formata no padrão brasileiro: 1.234.567,8."""
    return f"{n:,.{casas}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def tamanho(n_bytes: int) -> str:
    valor = float(n_bytes)
    for unidade in ("B", "KB", "MB", "GB"):
        if valor < 1024 or unidade == "GB":
            return f"{numero(valor, 1)} {unidade}"
        valor /= 1024
    raise AssertionError("inalcançável")


def _cor(fracao: float) -> tuple[int, int, int]:
    fracao = min(max(fracao, 0.0), 1.0)
    for (p0, c0), (p1, c1) in itertools.pairwise(GRADIENTE):
        if fracao <= p1:
            t = (fracao - p0) / (p1 - p0)
            r, g, b = (round(a + (z - a) * t) for a, z in zip(c0, c1, strict=True))
            return (r, g, b)
    return GRADIENTE[-1][1]


def _celula(valor: float | None, minimo: float, maximo: float) -> str:
    if valor is None:
        return "··"
    fracao = (valor - minimo) / (maximo - minimo)
    bloco = BLOCOS[min(int(max(fracao, 0) * len(BLOCOS)), len(BLOCOS) - 1)]
    return typer.style(bloco, fg=_cor(fracao))


def mapa_termico(tabela: pa.Table, tipo: str) -> list[str]:
    """Desenha a planta: uma linha por fileira, um bloco colorido por rack."""
    minimo, maximo, unidade = ESCALAS[tipo]
    racks = tabela.to_pylist()
    fileiras = sorted({r["fileira"] for r in racks})
    posicoes = max(r["posicao"] for r in racks)
    valores = {(r["fileira"], r["posicao"]): r["valor"] for r in racks}

    regua = [" "] * (posicoes * 2)
    for p in range(1, posicoes + 1):
        if p == 1 or p % 5 == 0:
            rotulo = str(p)
            regua[(p - 1) * 2 : (p - 1) * 2 + len(rotulo)] = rotulo
    linhas = ["    " + "".join(regua).rstrip()]
    for fileira in fileiras:
        celulas = "".join(
            _celula(valores.get((fileira, p)), minimo, maximo) for p in range(1, posicoes + 1)
        )
        linhas.append(f"  {fileira} {celulas}")

    legenda = "".join(
        _celula(minimo + (maximo - minimo) * i / 9, minimo, maximo) for i in range(10)
    )
    linhas.append("")
    linhas.append(
        f"    {numero(minimo)} {unidade} {legenda} {numero(maximo)} {unidade}   ·· sem leitura"
    )
    return linhas


def _texto(valor: Any, fuso: tzinfo | None) -> str:
    if valor is None:
        return ""
    if isinstance(valor, datetime):
        return f"{valor.astimezone(fuso):%Y-%m-%d %H:%M}"
    if isinstance(valor, float):
        return numero(valor, 2).rstrip("0").rstrip(",")
    if isinstance(valor, int) and not isinstance(valor, bool):
        return numero(valor)
    return str(valor)


def tabela_texto(tabela: pa.Table, fuso: tzinfo | None = None) -> list[str]:
    """Tabela alinhada em colunas. Números à direita, texto à esquerda."""
    nomes = tabela.column_names
    registros = tabela.to_pylist()
    textos = [[_texto(r[n], fuso) for n in nomes] for r in registros]
    larguras = [max([len(n)] + [len(t[i]) for t in textos]) for i, n in enumerate(nomes)]
    numericas = [pa.types.is_integer(c.type) or pa.types.is_floating(c.type) for c in tabela.schema]

    def linha(celulas: list[str]) -> str:
        return "  ".join(
            c.rjust(w) if num else c.ljust(w)
            for c, w, num in zip(celulas, larguras, numericas, strict=True)
        ).rstrip()

    return [linha(nomes), linha(["─" * w for w in larguras])] + [linha(t) for t in textos]
