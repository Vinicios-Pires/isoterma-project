"""A API HTTP do Isoterma (FastAPI). Instale com ``uv sync --extra api``."""

from isoterma.api.app import ConfigApi, criar_app

__all__ = ["ConfigApi", "criar_app"]
