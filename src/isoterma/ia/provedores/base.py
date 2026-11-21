"""A interface que cada provedor de LLM implementa, e a estimativa de custo."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from isoterma.ia.tipos import DefinicaoFerramenta, ResultadoFerramenta, Turno, Uso


class ErroProvedor(RuntimeError):
    """Falha de configuração ou de chamada ao provedor, com uma mensagem acionável."""


class Conversa(Protocol):
    """Uma conversa em andamento. Guarda o histórico no formato nativo do provedor.

    Manter o formato nativo importa: alguns modelos exigem que o raciocínio que eles
    devolveram (blocos de thinking, assinaturas) volte intacto no turno seguinte.
    """

    def enviar_pergunta(self, texto: str) -> Turno: ...

    def enviar_resultados(self, resultados: Sequence[ResultadoFerramenta]) -> Turno: ...


class Provedor(Protocol):
    nome: str
    modelo: str

    def iniciar(self, sistema: str, ferramentas: Sequence[DefinicaoFerramenta]) -> Conversa: ...


@dataclass(frozen=True)
class Preco:
    """Dólares por milhão de tokens."""

    entrada: float
    saida: float
    cache_leitura: float
    cache_escrita: float


# Tabela da Anthropic (cache de leitura e escrita a 0,1× e 1,25× da entrada, salvo indicação).
# Os preços de OpenAI e Gemini mudam com frequência e não foram confirmados: sem preço, o custo
# aparece como "não estimado" em vez de um número inventado.
PRECOS: dict[str, Preco] = {
    "claude-haiku-5-5": Preco(0.10, 0.50, 0.01, 0.125),
    "claude-sonnet-5-5": Preco(2.00, 10.00, 0.10, 2.50),
    "claude-opus-5-5": Preco(4.00, 20.00, 0.20, 5.00),
}


def estimar_custo(modelo: str, uso: Uso) -> float | None:
    preco = PRECOS.get(modelo)
    if preco is None:
        return None
    # Nas três APIs, os tokens lidos do cache também aparecem na contagem de entrada da
    # OpenAI e do Gemini, mas não na da Anthropic; os adaptadores normalizam para o formato
    # da Anthropic (entrada = só o que não veio do cache).
    return (
        uso.entrada * preco.entrada
        + uso.saida * preco.saida
        + uso.cache_leitura * preco.cache_leitura
        + uso.cache_escrita * preco.cache_escrita
    ) / 1_000_000
