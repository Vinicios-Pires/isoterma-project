"""Os adaptadores traduzem certo para cada SDK. Nenhum teste usa a rede."""

from types import SimpleNamespace
from typing import Any

import pytest

from isoterma.ia.provedores import ErroProvedor, criar_provedor
from isoterma.ia.provedores.claude import ProvedorClaude
from isoterma.ia.provedores.falso import ProvedorFalso
from isoterma.ia.provedores.gemini import ProvedorGemini
from isoterma.ia.provedores.gpt import ProvedorOpenAI
from isoterma.ia.tipos import DefinicaoFerramenta, Parada, ResultadoFerramenta

FERRAMENTA = DefinicaoFerramenta(
    "resumo",
    "Resumo do hall",
    {
        "type": "object",
        "properties": {"inicio": {"anyOf": [{"type": "string"}, {"type": "null"}]}},
        "required": ["inicio"],
        "additionalProperties": False,
    },
)


class Gravador:
    """Faz o papel do método do SDK: guarda os argumentos e devolve respostas prontas."""

    def __init__(self, *respostas: Any) -> None:
        self.respostas = list(respostas)
        self.chamadas: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> Any:
        self.chamadas.append(kwargs)
        return self.respostas.pop(0)


# --- Claude --------------------------------------------------------------------------------


def _mensagem_claude(conteudo: list[dict], parada: str, **extra: Any) -> Any:
    from anthropic.types import Message

    return Message.model_validate(
        {
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "model": "claude-haiku-5-5",
            "content": conteudo,
            "stop_reason": parada,
            "stop_sequence": None,
            "usage": {
                "input_tokens": 120,
                "output_tokens": 30,
                "cache_read_input_tokens": 1_000,
                "cache_creation_input_tokens": 0,
            },
            **extra,
        }
    )


def _cliente_claude(*respostas: Any) -> Any:
    create = Gravador(*respostas)
    return SimpleNamespace(
        messages=SimpleNamespace(create=create),
        beta=SimpleNamespace(messages=SimpleNamespace(create=create)),
    ), create


def test_claude_traduz_ferramentas_e_preserva_o_raciocinio() -> None:
    pede = _mensagem_claude(
        [
            {"type": "thinking", "thinking": "", "signature": "assinatura"},
            {"type": "text", "text": "Vou ver."},
            {"type": "tool_use", "id": "toolu_1", "name": "resumo", "input": {"inicio": None}},
        ],
        "tool_use",
    )
    responde = _mensagem_claude([{"type": "text", "text": "Pronto."}], "end_turn")
    cliente, create = _cliente_claude(pede, responde)
    conversa = ProvedorClaude(cliente=cliente).iniciar("sistema", [FERRAMENTA])

    turno = conversa.enviar_pergunta("Como está o hall?")
    final = conversa.enviar_resultados(
        [ResultadoFerramenta("toolu_1", "resumo", "dados", erro=False)]
    )

    assert turno.parada is Parada.FERRAMENTAS
    assert turno.chamadas[0].argumentos == {"inicio": None}
    assert turno.uso.cache_leitura == 1_000
    assert final.texto == "Pronto." and final.parada is Parada.FIM

    primeira = create.chamadas[0]
    assert primeira["model"] == "claude-haiku-5-5"
    assert primeira["tools"][0] == {
        "name": "resumo",
        "description": "Resumo do hall",
        "input_schema": FERRAMENTA.parametros,
        "strict": True,
    }
    assert primeira["cache_control"] == {"type": "ephemeral"}
    assert primeira["output_config"] == {"effort": "medium"}
    assert "betas" not in primeira  # o Haiku 5.5 não tem fallback no servidor

    segunda = create.chamadas[1]["messages"]
    assert segunda[1]["content"] is pede.content  # o bloco de thinking volta intacto
    assert segunda[2]["content"][0] == {
        "type": "tool_result",
        "tool_use_id": "toolu_1",
        "content": "dados",
        "is_error": False,
    }


def test_claude_em_modelo_com_fallback_usa_o_beta() -> None:
    cliente, create = _cliente_claude(
        _mensagem_claude([{"type": "text", "text": "oi"}], "end_turn")
    )

    ProvedorClaude("claude-opus-5-5", cliente=cliente).iniciar("s", []).enviar_pergunta("oi")

    assert create.chamadas[0]["betas"] == ["server-side-fallback-2026-07-01"]
    assert create.chamadas[0]["fallbacks"] == "default"


def test_claude_recusa_e_limite() -> None:
    recusa = _mensagem_claude(
        [], "refusal", stop_details={"type": "refusal", "category": "cyber", "explanation": None}
    )
    cortado = _mensagem_claude(
        [{"type": "tool_use", "id": "t", "name": "resumo", "input": {}}], "max_tokens"
    )
    cliente, _ = _cliente_claude(recusa, cortado)
    provedor = ProvedorClaude(cliente=cliente)

    turno_recusa = provedor.iniciar("s", []).enviar_pergunta("x")
    turno_cortado = provedor.iniciar("s", []).enviar_pergunta("x")

    assert turno_recusa.parada is Parada.RECUSA and turno_recusa.detalhe == "cyber"
    assert turno_cortado.parada is Parada.LIMITE
    assert turno_cortado.chamadas == ()  # entrada possivelmente truncada: nada é executado


def test_claude_traduz_erro_de_autenticacao() -> None:
    import anthropic
    import httpx2

    def recusar(**_: Any) -> Any:
        resposta = httpx2.Response(401, request=httpx2.Request("POST", "https://api.anthropic.com"))
        raise anthropic.AuthenticationError("chave inválida", response=resposta, body=None)

    cliente = SimpleNamespace(messages=SimpleNamespace(create=recusar))

    with pytest.raises(ErroProvedor, match="ANTHROPIC_API_KEY"):
        ProvedorClaude(cliente=cliente).iniciar("s", []).enviar_pergunta("x")


# --- OpenAI --------------------------------------------------------------------------------


def _resposta_openai(
    itens: list[dict], status: str = "completed", motivo: str | None = None
) -> Any:
    from openai.types.responses import (
        Response,
        ResponseFunctionToolCall,
        ResponseOutputMessage,
        ResponseUsage,
    )

    saida = [
        ResponseFunctionToolCall.model_validate(i)
        if i["type"] == "function_call"
        else ResponseOutputMessage.model_validate(i)
        for i in itens
    ]
    return Response.model_construct(
        output=saida,
        status=status,
        incomplete_details=SimpleNamespace(reason=motivo) if motivo else None,
        usage=ResponseUsage.model_validate(
            {
                "input_tokens": 500,
                "input_tokens_details": {"cached_tokens": 400, "cache_write_tokens": 0},
                "output_tokens": 20,
                "output_tokens_details": {"reasoning_tokens": 0},
                "total_tokens": 520,
            }
        ),
    )


def test_openai_traduz_ferramentas_e_mantem_o_historico_local() -> None:
    pede = _resposta_openai(
        [
            {
                "type": "function_call",
                "call_id": "call_1",
                "name": "resumo",
                "arguments": '{"inicio": null}',
            }
        ]
    )
    responde = _resposta_openai(
        [
            {
                "type": "message",
                "id": "msg_1",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": "Pronto.", "annotations": []}],
            }
        ]
    )
    create = Gravador(pede, responde)
    conversa = ProvedorOpenAI(
        "modelo-x", cliente=SimpleNamespace(responses=SimpleNamespace(create=create))
    ).iniciar("sistema", [FERRAMENTA])

    turno = conversa.enviar_pergunta("Como está?")
    final = conversa.enviar_resultados(
        [ResultadoFerramenta("call_1", "resumo", "falhou", erro=True)]
    )

    assert turno.chamadas[0].argumentos == {"inicio": None}
    assert turno.uso.entrada == 100 and turno.uso.cache_leitura == 400
    assert final.texto == "Pronto." and final.parada is Parada.FIM
    primeira = create.chamadas[0]
    assert primeira["store"] is False
    assert primeira["instructions"] == "sistema"
    assert primeira["tools"][0]["strict"] is True
    entrada = create.chamadas[1]["input"]
    assert entrada[1]["type"] == "function_call" and entrada[1]["call_id"] == "call_1"
    assert entrada[2] == {
        "type": "function_call_output",
        "call_id": "call_1",
        "output": "ERRO: falhou",
    }


def test_openai_resposta_incompleta() -> None:
    create = Gravador(_resposta_openai([], status="incomplete", motivo="max_output_tokens"))
    conversa = ProvedorOpenAI(
        "m", cliente=SimpleNamespace(responses=SimpleNamespace(create=create))
    ).iniciar("s", [])

    assert conversa.enviar_pergunta("x").parada is Parada.LIMITE


# --- Gemini --------------------------------------------------------------------------------


def _resposta_gemini(partes: list[dict], motivo: str = "STOP") -> Any:
    from google.genai import types

    return types.GenerateContentResponse.model_validate(
        {
            "candidates": [
                {"content": {"role": "model", "parts": partes}, "finish_reason": motivo}
            ],
            "usage_metadata": {
                "prompt_token_count": 300,
                "cached_content_token_count": 100,
                "candidates_token_count": 20,
                "thoughts_token_count": 5,
            },
        }
    )


def test_gemini_traduz_ferramentas_e_resultados() -> None:
    pede = _resposta_gemini([{"function_call": {"name": "resumo", "args": {"inicio": None}}}])
    responde = _resposta_gemini([{"text": "pensando", "thought": True}, {"text": "Pronto."}])
    gerar = Gravador(pede, responde)
    cliente = SimpleNamespace(models=SimpleNamespace(generate_content=gerar))
    conversa = ProvedorGemini("modelo-g", cliente=cliente).iniciar("sistema", [FERRAMENTA])

    turno = conversa.enviar_pergunta("Como está?")
    final = conversa.enviar_resultados(
        [ResultadoFerramenta(turno.chamadas[0].id, "resumo", "dados")]
    )

    assert turno.parada is Parada.FERRAMENTAS
    assert turno.chamadas[0].nome == "resumo"
    assert turno.uso.entrada == 200 and turno.uso.saida == 25 and turno.uso.cache_leitura == 100
    assert final.texto == "Pronto."  # o pensamento não entra no texto
    config = gerar.chamadas[0]["config"]
    assert config.automatic_function_calling.disable is True
    assert config.tools[0].function_declarations[0].parameters_json_schema == FERRAMENTA.parametros
    conteudos = gerar.chamadas[1]["contents"]
    resposta_ferramenta = conteudos[2].parts[0].function_response
    assert resposta_ferramenta.name == "resumo" and resposta_ferramenta.response == {
        "resultado": "dados"
    }


def test_gemini_recusa_por_seguranca() -> None:
    gerar = Gravador(_resposta_gemini([], motivo="SAFETY"))
    cliente = SimpleNamespace(models=SimpleNamespace(generate_content=gerar))

    assert (
        ProvedorGemini("m", cliente=cliente).iniciar("s", []).enviar_pergunta("x").parada
        is Parada.RECUSA
    )


# --- escolha do provedor ---------------------------------------------------------------------


def test_claude_e_o_padrao(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ISOTERMA_LLM", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "chave-de-teste")

    provedor = criar_provedor()

    assert provedor.nome == "claude" and provedor.modelo == "claude-haiku-5-5"


def test_variavel_de_ambiente_escolhe_o_provedor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ISOTERMA_LLM", "falso")

    assert isinstance(criar_provedor(), ProvedorFalso)


def test_modelo_explicito_no_claude(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "chave-de-teste")

    assert criar_provedor("claude:claude-sonnet-5-5").modelo == "claude-sonnet-5-5"


@pytest.mark.parametrize("nome", ["openai", "gemini"])
def test_openai_e_gemini_exigem_o_modelo(nome: str) -> None:
    with pytest.raises(ErroProvedor, match=f"{nome}:<modelo>"):
        criar_provedor(nome)


def test_provedor_desconhecido() -> None:
    with pytest.raises(ErroProvedor, match="desconhecido"):
        criar_provedor("llama")
