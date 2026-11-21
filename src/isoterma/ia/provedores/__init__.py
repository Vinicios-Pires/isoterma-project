"""Provedores de LLM plugáveis, escolhidos por texto: ``claude``, ``openai:<modelo>``..."""

import os

from isoterma.ia.provedores.base import ErroProvedor, Provedor, estimar_custo

VARIAVEL = "ISOTERMA_LLM"
PADRAO = "claude"
NOMES = ("claude", "openai", "gemini", "falso")


def criar_provedor(especificacao: str | None = None) -> Provedor:
    """Cria o provedor a partir de ``nome[:modelo]``; sem argumento, lê ``ISOTERMA_LLM``.

    Exemplos: ``claude`` (Claude Haiku 5.5), ``claude:claude-sonnet-5-5``,
    ``openai:<modelo>``, ``gemini:<modelo>`` e ``falso`` (demonstração sem rede).
    """
    texto = (especificacao or os.environ.get(VARIAVEL) or PADRAO).strip()
    nome, _, modelo = texto.partition(":")
    nome = nome.lower()
    match nome:
        case "claude":
            from isoterma.ia.provedores.claude import MODELO_PADRAO, ProvedorClaude

            return ProvedorClaude(modelo or MODELO_PADRAO)
        case "openai" | "gemini":
            if not modelo:
                # Os nomes dos modelos desses provedores mudam com frequência: em vez de um
                # padrão que pode ter saído do ar, o modelo é escolhido explicitamente.
                raise ErroProvedor(
                    f"Informe o modelo: {nome}:<modelo>. Veja a lista atual na documentação do "
                    f"{'OpenAI' if nome == 'openai' else 'Gemini'}."
                )
            if nome == "openai":
                from isoterma.ia.provedores.gpt import ProvedorOpenAI

                return ProvedorOpenAI(modelo)
            from isoterma.ia.provedores.gemini import ProvedorGemini

            return ProvedorGemini(modelo)
        case "falso":
            from isoterma.ia.provedores.falso import ProvedorFalso

            return ProvedorFalso()
        case _:
            raise ErroProvedor(f"Provedor {nome!r} desconhecido. Use um de: {', '.join(NOMES)}")


__all__ = ["ErroProvedor", "Provedor", "criar_provedor", "estimar_custo"]
