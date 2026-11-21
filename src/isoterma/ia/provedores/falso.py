"""Provedor sem rede e sem custo, com respostas roteirizadas: para testes e para a demo."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from isoterma.ia.tipos import (
    ChamadaFerramenta,
    DefinicaoFerramenta,
    Parada,
    ResultadoFerramenta,
    Turno,
    Uso,
)


@dataclass
class Historico:
    """O que a conversa falsa recebeu, para os testes conferirem."""

    sistema: str
    ferramentas: list[DefinicaoFerramenta]
    perguntas: list[str] = field(default_factory=list)
    resultados: list[ResultadoFerramenta] = field(default_factory=list)
    turnos: int = 0


Roteiro = Callable[[Historico], Turno]


def roteiro_de(turnos: Sequence[Turno]) -> Roteiro:
    """Devolve os turnos em ordem, um por chamada."""
    fila = list(turnos)

    def proximo(_: Historico) -> Turno:
        if not fila:
            raise AssertionError("O roteiro do provedor falso acabou")
        return fila.pop(0)

    return proximo


def roteiro_demonstracao(historico: Historico) -> Turno:
    """Consulta o resumo do hall e devolve o texto, como faria um modelo bem simples."""
    if historico.turnos == 1:
        return Turno(
            texto="Vou olhar o resumo do período.",
            chamadas=(ChamadaFerramenta("falso-1", "resumo", {"inicio": None, "fim": None}),),
            uso=Uso(entrada=1_000, saida=40),
            parada=Parada.FERRAMENTAS,
        )
    ultimo = historico.resultados[-1].conteudo if historico.resultados else ""
    return Turno(
        texto=(
            "Este é o provedor de demonstração (sem IA de verdade). "
            "Configure ISOTERMA_LLM para usar um modelo real. Resumo do período:\n\n" + ultimo
        ),
        uso=Uso(entrada=1_500, saida=120),
    )


class ConversaFalsa:
    def __init__(self, historico: Historico, roteiro: Roteiro) -> None:
        self.historico = historico
        self._roteiro = roteiro

    def enviar_pergunta(self, texto: str) -> Turno:
        self.historico.perguntas.append(texto)
        return self._proximo()

    def enviar_resultados(self, resultados: Sequence[ResultadoFerramenta]) -> Turno:
        self.historico.resultados.extend(resultados)
        return self._proximo()

    def _proximo(self) -> Turno:
        self.historico.turnos += 1
        return self._roteiro(self.historico)


class ProvedorFalso:
    nome = "falso"

    def __init__(
        self, roteiro: Roteiro | Sequence[Turno] | None = None, modelo: str = "roteiro"
    ) -> None:
        self.modelo = modelo
        if roteiro is None:
            self._roteiro: Roteiro = roteiro_demonstracao
        elif callable(roteiro):
            self._roteiro = roteiro
        else:
            self._roteiro = roteiro_de(roteiro)
        self.conversas: list[ConversaFalsa] = []

    def iniciar(self, sistema: str, ferramentas: Sequence[DefinicaoFerramenta]) -> ConversaFalsa:
        conversa = ConversaFalsa(Historico(sistema, list(ferramentas)), self._roteiro)
        self.conversas.append(conversa)
        return conversa
