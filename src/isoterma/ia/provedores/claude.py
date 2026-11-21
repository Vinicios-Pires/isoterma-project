"""Adaptador do Claude (SDK oficial ``anthropic``)."""

from collections.abc import Sequence
from typing import Any

from isoterma.ia.provedores.base import ErroProvedor
from isoterma.ia.tipos import (
    ChamadaFerramenta,
    DefinicaoFerramenta,
    Parada,
    ResultadoFerramenta,
    Turno,
    Uso,
)

MODELO_PADRAO = "claude-haiku-5-5"
ESFORCO_PADRAO = "medium"
MAX_TOKENS = 16_000
# Modelos em que a API refaz uma resposta recusada pelo filtro de segurança em outro modelo,
# na mesma chamada. O Claude Haiku 5.5 não tem esse recurso.
COM_FALLBACK = frozenset(
    {
        "claude-opus-5-5",
        "claude-opus-5",
        "claude-sonnet-5-5",
        "claude-fable-5-2",
        "claude-fable-5-1",
    }
)
BETA_FALLBACK = "server-side-fallback-2026-07-01"

PARADAS = {
    "end_turn": Parada.FIM,
    "stop_sequence": Parada.FIM,
    "tool_use": Parada.FERRAMENTAS,
    "max_tokens": Parada.LIMITE,
    "refusal": Parada.RECUSA,
}


def _turno(resposta: Any) -> Turno:
    parada = PARADAS.get(resposta.stop_reason, Parada.FIM)
    detalhe = ""
    if parada is Parada.RECUSA and resposta.stop_details is not None:
        detalhe = resposta.stop_details.explanation or resposta.stop_details.category or ""
    texto = "".join(b.text for b in resposta.content if b.type == "text")
    chamadas = tuple(
        ChamadaFerramenta(b.id, b.name, dict(b.input))
        for b in resposta.content
        if b.type == "tool_use"
    )
    if parada is Parada.FERRAMENTAS and not chamadas:
        parada = Parada.FIM
    uso = resposta.usage
    return Turno(
        texto=texto,
        # Num turno cortado pelo limite ou recusado, a entrada de uma ferramenta pode ter
        # vindo pela metade: o agente não executa nada desse turno.
        chamadas=chamadas if parada is Parada.FERRAMENTAS else (),
        uso=Uso(
            entrada=uso.input_tokens,
            saida=uso.output_tokens,
            cache_leitura=uso.cache_read_input_tokens or 0,
            cache_escrita=uso.cache_creation_input_tokens or 0,
        ),
        parada=parada,
        detalhe=detalhe,
    )


class ConversaClaude:
    def __init__(
        self,
        cliente: Any,
        modelo: str,
        sistema: str,
        ferramentas: Sequence[DefinicaoFerramenta],
        esforco: str,
    ) -> None:
        self._cliente = cliente
        self._modelo = modelo
        self._sistema = sistema
        self._esforco = esforco
        self._ferramentas = [
            {
                "name": f.nome,
                "description": f.descricao,
                "input_schema": f.parametros,
                "strict": True,
            }
            for f in ferramentas
        ]
        self.mensagens: list[dict[str, Any]] = []

    def enviar_pergunta(self, texto: str) -> Turno:
        self.mensagens.append({"role": "user", "content": texto})
        return self._chamar()

    def enviar_resultados(self, resultados: Sequence[ResultadoFerramenta]) -> Turno:
        # Todos os resultados vão numa única mensagem, como a API espera.
        self.mensagens.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": r.chamada_id,
                        "content": r.conteudo,
                        "is_error": r.erro,
                    }
                    for r in resultados
                ],
            }
        )
        return self._chamar()

    def _chamar(self) -> Turno:
        import anthropic

        parametros: dict[str, Any] = {
            "model": self._modelo,
            "max_tokens": MAX_TOKENS,
            "system": self._sistema,
            "tools": self._ferramentas,
            "messages": self.mensagens,
            "output_config": {"effort": self._esforco},
            # Ferramentas e instruções são iguais em toda pergunta: o prefixo vai para o cache.
            "cache_control": {"type": "ephemeral"},
        }
        try:
            if self._modelo in COM_FALLBACK:
                resposta = self._cliente.beta.messages.create(
                    **parametros, betas=[BETA_FALLBACK], fallbacks="default"
                )
            else:
                resposta = self._cliente.messages.create(**parametros)
        except anthropic.AuthenticationError as erro:
            raise ErroProvedor(
                "A chave da API da Anthropic foi recusada. Confira ANTHROPIC_API_KEY "
                "(ou rode `ant auth login`)."
            ) from erro
        except anthropic.PermissionDeniedError as erro:
            raise ErroProvedor(f"A chave não tem acesso a {self._modelo}: {erro.message}") from erro
        except anthropic.NotFoundError as erro:
            raise ErroProvedor(
                f"Modelo {self._modelo!r} não encontrado na API da Anthropic"
            ) from erro
        except anthropic.BadRequestError as erro:
            raise ErroProvedor(f"A API da Anthropic recusou a requisição: {erro.message}") from erro
        except anthropic.RateLimitError as erro:
            raise ErroProvedor(
                "Limite de uso da API da Anthropic atingido (o SDK já tentou de novo). "
                "Espere um pouco ou confira os créditos no Console."
            ) from erro
        except anthropic.APIStatusError as erro:
            raise ErroProvedor(
                f"Erro {erro.status_code} na API da Anthropic: {erro.message}"
            ) from erro
        except anthropic.APIConnectionError as erro:
            raise ErroProvedor("Sem conexão com a API da Anthropic") from erro

        # O conteúdo volta para o histórico exatamente como veio, inclusive os blocos de
        # thinking: os modelos atuais exigem o raciocínio anterior intacto.
        self.mensagens.append({"role": "assistant", "content": resposta.content})
        return _turno(resposta)


class ProvedorClaude:
    nome = "claude"

    def __init__(
        self, modelo: str = MODELO_PADRAO, *, esforco: str = ESFORCO_PADRAO, cliente: Any = None
    ) -> None:
        self.modelo = modelo
        self.esforco = esforco
        if cliente is None:
            try:
                import anthropic
            except ImportError as erro:
                raise ErroProvedor("Instale o suporte ao Claude: uv sync --extra claude") from erro
            # Sem argumentos, o SDK acha a credencial sozinho: ANTHROPIC_API_KEY,
            # ANTHROPIC_AUTH_TOKEN ou um perfil de `ant auth login`.
            cliente = anthropic.Anthropic()
        self._cliente = cliente

    def iniciar(self, sistema: str, ferramentas: Sequence[DefinicaoFerramenta]) -> ConversaClaude:
        return ConversaClaude(self._cliente, self.modelo, sistema, ferramentas, self.esforco)
