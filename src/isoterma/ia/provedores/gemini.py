"""Adaptador do Google Gemini (SDK oficial ``google-genai``)."""

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
RECUSAS = frozenset({"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION"})


def _turno(resposta: Any) -> Turno:
    candidato = (resposta.candidates or [None])[0]
    partes = (candidato.content.parts or []) if candidato and candidato.content else []
    texto = "".join(p.text for p in partes if p.text and not p.thought)
    chamadas = tuple(
        ChamadaFerramenta(
            # Nem todo modelo devolve id na chamada; o nome e a posição bastam para casar a
            # resposta, que o Gemini associa pela ordem.
            p.function_call.id or f"{p.function_call.name}-{i}",
            p.function_call.name or "",
            dict(p.function_call.args or {}),
        )
        for i, p in enumerate(partes)
        if p.function_call
    )
    motivo = str(getattr(candidato, "finish_reason", "") or "").rsplit(".", 1)[-1]
    if motivo == "MAX_TOKENS":
        parada = Parada.LIMITE
    elif motivo in RECUSAS:
        parada = Parada.RECUSA
    else:
        parada = Parada.FERRAMENTAS if chamadas else Parada.FIM

    meta = resposta.usage_metadata
    em_cache = (meta.cached_content_token_count or 0) if meta else 0
    return Turno(
        texto=texto,
        chamadas=chamadas if parada is Parada.FERRAMENTAS else (),
        uso=Uso(
            entrada=((meta.prompt_token_count or 0) - em_cache) if meta else 0,
            saida=((meta.candidates_token_count or 0) + (meta.thoughts_token_count or 0))
            if meta
            else 0,
            cache_leitura=em_cache,
        ),
        parada=parada,
        detalhe=motivo if parada in (Parada.LIMITE, Parada.RECUSA) else "",
    )


class ConversaGemini:
    def __init__(
        self, cliente: Any, modelo: str, sistema: str, ferramentas: Sequence[DefinicaoFerramenta]
    ) -> None:
        from google.genai import types

        self._cliente = cliente
        self._modelo = modelo
        self._types = types
        self._config = types.GenerateContentConfig(
            system_instruction=sistema,
            tools=[
                types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(
                            name=f.nome,
                            description=f.descricao,
                            parameters_json_schema=f.parametros,
                        )
                        for f in ferramentas
                    ]
                )
            ],
            # O laço é do Isoterma, não do SDK: nada de chamadas automáticas.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            max_output_tokens=MAX_TOKENS,
        )
        self.conteudos: list[Any] = []

    def enviar_pergunta(self, texto: str) -> Turno:
        t = self._types
        self.conteudos.append(t.Content(role="user", parts=[t.Part(text=texto)]))
        return self._chamar()

    def enviar_resultados(self, resultados: Sequence[ResultadoFerramenta]) -> Turno:
        t = self._types
        partes = [
            t.Part(
                function_response=t.FunctionResponse(
                    id=None if r.chamada_id.startswith(f"{r.nome}-") else r.chamada_id,
                    name=r.nome,
                    response={"erro": r.conteudo} if r.erro else {"resultado": r.conteudo},
                )
            )
            for r in resultados
        ]
        self.conteudos.append(t.Content(role="user", parts=partes))
        return self._chamar()

    def _chamar(self) -> Turno:
        from google.genai import errors

        try:
            resposta = self._cliente.models.generate_content(
                model=self._modelo, contents=self.conteudos, config=self._config
            )
        except errors.ClientError as erro:
            if erro.code in (401, 403):
                raise ErroProvedor(
                    "A chave do Gemini foi recusada. Confira GEMINI_API_KEY."
                ) from erro
            if erro.code == 404:
                raise ErroProvedor(f"Modelo {self._modelo!r} não encontrado no Gemini") from erro
            if erro.code == 429:
                raise ErroProvedor("Limite de uso do Gemini atingido") from erro
            raise ErroProvedor(f"O Gemini recusou a requisição: {erro.message}") from erro
        except errors.APIError as erro:
            raise ErroProvedor(f"Erro {erro.code} no Gemini: {erro.message}") from erro

        candidato = (resposta.candidates or [None])[0]
        if candidato is not None and candidato.content is not None:
            # A resposta volta inteira para o histórico: os modelos com raciocínio dependem
            # das assinaturas de pensamento que vêm junto.
            self.conteudos.append(candidato.content)
        return _turno(resposta)


class ProvedorGemini:
    nome = "gemini"

    def __init__(self, modelo: str, *, cliente: Any = None) -> None:
        self.modelo = modelo
        if cliente is None:
            try:
                from google import genai
            except ImportError as erro:
                raise ErroProvedor("Instale o suporte ao Gemini: uv sync --extra gemini") from erro
            try:
                cliente = genai.Client()  # lê GEMINI_API_KEY (ou GOOGLE_API_KEY)
            except ValueError as erro:
                raise ErroProvedor("Defina GEMINI_API_KEY para usar o Gemini") from erro
        self._cliente = cliente

    def iniciar(self, sistema: str, ferramentas: Sequence[DefinicaoFerramenta]) -> ConversaGemini:
        return ConversaGemini(self._cliente, self.modelo, sistema, ferramentas)
