"""Exporta o esquema OpenAPI sem subir o servidor: ``python -m isoterma.api.openapi <arquivo>``.

O front gera os tipos TypeScript a partir desse arquivo (``npm run tipos`` em ``web/``).
"""

import json
import sys
from pathlib import Path

from isoterma.api.app import ConfigApi, criar_app


def esquema() -> dict:
    return criar_app(ConfigApi(dados=Path("data"))).openapi()


def texto() -> str:
    return json.dumps(esquema(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if destino is None:
        sys.stdout.write(texto())
    else:
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(texto(), encoding="utf-8", newline="\n")
        print(f"OpenAPI gravado em {destino}")
