"""Adaptador da OpenAI (SDK oficial ``openai``, Responses API)."""

import json
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

MAX_TOKENS = 16_000


def _turno(resposta: Any) -> Turno:
    texto = "".join(
        parte.text
        for item in resposta.output
        if item.type == "message"
        for parte in item.content
        if parte.type == "output_text"
    )
    chamadas: list[ChamadaFerramenta] = []
    for item in resposta.output:
        if item.type == "function_call":
            try:
                argumentos = json.loads(item.arguments or "{}")
            except json.JSONDecodeError:
                argumentos = {"_json_invalido": item.arguments}
            chamadas.append(ChamadaFerramenta(item.call_id, item.name, argumentos))

    parada = Parada.FERRAMENTAS if chamadas else Parada.FIM
    detalhe = ""
    if resposta.status == "incomplete":
        motivo = getattr(resposta.incomplete_details, "reason", None) or ""
        parada = Parada.RECUSA if motivo == "content_filter" else Parada.LIMITE
        detalhe = motivo

    uso = resposta.usage
    em_cache = 0
    if uso is not None and uso.input_tokens_details is not None:
        em_cache = uso.input_tokens_details.cached_tokens or 0
    return Turno(
        texto=texto,
        chamadas=tuple(chamadas) if parada is Parada.FERRAMENTAS else (),
        uso=Uso(
            # Normaliza para o formato da Anthropic: entrada sem os tokens que vieram do cache.
            entrada=(uso.input_tokens - em_cache) if uso else 0,
            saida=uso.output_tokens if uso else 0,
            cache_leitura=em_cache,
        ),
        parada=parada,
        detalhe=detalhe,
    )


class ConversaOpenAI:
    def __init__(
        self,
        cliente: Any,
        modelo: str,
        sistema: str,
        ferramentas: Sequence[DefinicaoFerramenta],
        esforco: str | None,
    ) -> None:
        self._cliente = cliente
        self._modelo = modelo
        self._sistema = sistema
        self._esforco = esforco
        self._ferramentas = [
            {
                "type": "function",
                "name": f.nome,
                "description": f.descricao,
                "parameters": f.parametros,
                "strict": True,
            }
            for f in ferramentas
        ]
        self.entrada: list[dict[str, Any]] = []

    def enviar_pergunta(self, texto: str) -> Turno:
        self.entrada.append({"role": "user", "content": texto})
        return self._chamar()

    def enviar_resultados(self, resultados: Sequence[ResultadoFerramenta]) -> Turno:
        for r in resultados:
            saida = f"ERRO: {r.conteudo}" if r.erro else r.conteudo
            self.entrada.append(
                {"type": "function_call_output", "call_id": r.chamada_id, "output": saida}
            )
        return self._chamar()

    def _chamar(self) -> Turno:
        import openai

        parametros: dict[str, Any] = {
            "model": self._modelo,
            "instructions": self._sistema,
            "input": self.entrada,
            "tools": self._ferramentas,
            "max_output_tokens": MAX_TOKENS,
            # Nada fica guardado na OpenAI: o histórico, inclusive o raciocínio cifrado do
            # modelo, é mantido aqui e reenviado a cada turno.
            "store": False,
            "include": ["reasoning.encrypted_content"],
        }
        if self._esforco:
            parametros["reasoning"] = {"effort": self._esforco}
        try:
            resposta = self._cliente.responses.create(**parametros)
        except openai.AuthenticationError as erro:
            raise ErroProvedor("A chave da OpenAI foi recusada. Confira OPENAI_API_KEY.") from erro
        except openai.NotFoundError as erro:
            raise ErroProvedor(f"Modelo {self._modelo!r} não encontrado na OpenAI") from erro
        except openai.BadRequestError as erro:
            raise ErroProvedor(f"A OpenAI recusou a requisição: {erro.message}") from erro
        except openai.RateLimitError as erro:
            raise ErroProvedor("Limite de uso ou créditos da OpenAI esgotados") from erro
        except openai.APIStatusError as erro:
            raise ErroProvedor(f"Erro {erro.status_code} na OpenAI: {erro.message}") from erro
        except openai.APIConnectionError as erro:
            raise ErroProvedor("Sem conexão com a OpenAI") from erro

        for item in resposta.output:
            self.entrada.append(item.model_dump(by_alias=True, exclude_none=True))
        return _turno(resposta)


class ProvedorOpenAI:
    nome = "openai"

    def __init__(self, modelo: str, *, esforco: str | None = None, cliente: Any = None) -> None:
        self.modelo = modelo
        self.esforco = esforco
        if cliente is None:
            try:
                import openai
            except ImportError as erro:
                raise ErroProvedor("Instale o suporte à OpenAI: uv sync --extra openai") from erro
            try:
                cliente = openai.OpenAI()  # lê OPENAI_API_KEY
            except openai.OpenAIError as erro:
                raise ErroProvedor("Defina OPENAI_API_KEY para usar a OpenAI") from erro
        self._cliente = cliente

    def iniciar(self, sistema: str, ferramentas: Sequence[DefinicaoFerramenta]) -> ConversaOpenAI:
        return ConversaOpenAI(self._cliente, self.modelo, sistema, ferramentas, self.esforco)
