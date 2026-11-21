"""Tipos neutros de provedor: o que o agente troca com qualquer LLM."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Parada(StrEnum):
    """Por que o modelo parou de gerar neste turno."""

    FIM = "fim"  # respondeu
    FERRAMENTAS = "ferramentas"  # pediu para chamar ferramentas
    LIMITE = "limite"  # bateu no máximo de tokens
    RECUSA = "recusa"  # o filtro de segurança do provedor recusou


@dataclass(frozen=True)
class DefinicaoFerramenta:
    nome: str
    descricao: str
    parametros: dict[str, Any]  # JSON Schema estrito: todos os campos obrigatórios, sem extras


@dataclass(frozen=True)
class ChamadaFerramenta:
    id: str
    nome: str
    argumentos: dict[str, Any]


@dataclass(frozen=True)
class ResultadoFerramenta:
    chamada_id: str
    nome: str
    conteudo: str
    erro: bool = False


@dataclass(frozen=True)
class Uso:
    entrada: int = 0
    saida: int = 0
    cache_leitura: int = 0
    cache_escrita: int = 0

    def __add__(self, outro: Uso) -> Uso:
        return Uso(
            self.entrada + outro.entrada,
            self.saida + outro.saida,
            self.cache_leitura + outro.cache_leitura,
            self.cache_escrita + outro.cache_escrita,
        )


@dataclass(frozen=True)
class Turno:
    texto: str
    chamadas: tuple[ChamadaFerramenta, ...] = ()
    uso: Uso = field(default_factory=Uso)
    parada: Parada = Parada.FIM
    detalhe: str = ""  # motivo de uma recusa ou de um limite, quando o provedor informa
