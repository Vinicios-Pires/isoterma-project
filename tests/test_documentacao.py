"""A documentação dos comandos acompanha a CLI."""

import re
from pathlib import Path

import typer.main

from isoterma.cli import app

COMANDOS_MD = Path(__file__).parents[1] / "docs" / "COMANDOS.md"


def _comandos() -> dict[str, list[str]]:
    """Cada comando da CLI e as opções longas que ele aceita."""
    grupo = typer.main.get_command(app)
    comandos = getattr(grupo, "commands", {})
    return {
        nome: [o for p in comando.params for o in p.opts if o.startswith("--")]
        for nome, comando in comandos.items()
    }


def test_todo_comando_tem_secao_no_guia() -> None:
    texto = COMANDOS_MD.read_text(encoding="utf-8")
    secoes = set(re.findall(r"^### `([a-z0-9-]+)`", texto, re.MULTILINE))

    assert secoes == set(_comandos())


def test_toda_opcao_aparece_no_guia() -> None:
    texto = COMANDOS_MD.read_text(encoding="utf-8")
    faltando = {
        f"{comando} {opcao}"
        for comando, opcoes in _comandos().items()
        for opcao in opcoes
        if opcao != "--help" and f"`{opcao}" not in texto
    }

    assert not faltando, f"Documente em docs/COMANDOS.md: {sorted(faltando)}"
