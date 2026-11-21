from pathlib import Path

from isoterma.api.openapi import texto

ARQUIVO = Path(__file__).parents[2] / "web" / "src" / "api" / "openapi.json"


def test_tipos_do_front_estao_em_dia_com_a_api() -> None:
    # Se falhar, rode `npm run tipos` em web/ e commite o openapi.json e o esquema.ts gerados.
    assert ARQUIVO.read_text(encoding="utf-8") == texto()
