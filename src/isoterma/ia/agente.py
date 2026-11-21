"""O laço do agente: pergunta → chamadas de ferramenta → resposta, com qualquer provedor.

O laço é do Isoterma, e não do SDK de um provedor, para ser o mesmo com Claude, GPT ou Gemini:
cada adaptador só traduz mensagens e ferramentas para o formato nativo.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from isoterma.ia.ferramentas import CaixaDeFerramentas
from isoterma.ia.prompt import construir_sistema
from isoterma.ia.provedores.base import Provedor, estimar_custo
from isoterma.ia.tipos import ChamadaFerramenta, Parada, ResultadoFerramenta, Uso
from isoterma.motor import Hall

MAX_TURNOS = 12


@dataclass(frozen=True)
class Passo:
    """Uma ferramenta que o agente chamou: o que pediu, o que recebeu e quanto levou."""

    chamada: ChamadaFerramenta
    resultado: ResultadoFerramenta
    segundos: float
    linhas: int | None = None
    sql: str | None = None


@dataclass
class Resposta:
    pergunta: str
    texto: str
    provedor: str
    modelo: str
    parada: Parada
    passos: list[Passo] = field(default_factory=list)
    uso: Uso = field(default_factory=Uso)
    turnos: int = 0
    segundos: float = 0.0
    detalhe: str = ""

    @property
    def custo_usd(self) -> float | None:
        return estimar_custo(self.modelo, self.uso)

    @property
    def concluida(self) -> bool:
        return self.parada is Parada.FIM


class Agente:
    def __init__(self, hall: Hall, provedor: Provedor, *, max_turnos: int = MAX_TURNOS) -> None:
        if not hall.ocultar_gabarito:
            raise ValueError("O agente precisa de um Hall com ocultar_gabarito=True")
        self.hall = hall
        self.provedor = provedor
        self.max_turnos = max_turnos
        self.ferramentas = CaixaDeFerramentas(hall)
        self.sistema = construir_sistema(hall)

    def perguntar(
        self,
        pergunta: str,
        *,
        instrucao_extra: str = "",
        ao_passo: Callable[[Passo], None] | None = None,
    ) -> Resposta:
        relogio = time.perf_counter()
        sistema = f"{self.sistema}\n\n{instrucao_extra}" if instrucao_extra else self.sistema
        conversa = self.provedor.iniciar(sistema, self.ferramentas.definicoes())
        resposta = Resposta(pergunta, "", self.provedor.nome, self.provedor.modelo, Parada.FIM)

        turno = conversa.enviar_pergunta(pergunta)
        resposta.turnos, resposta.uso = 1, turno.uso
        textos = [turno.texto] if turno.texto else []
        while turno.parada is Parada.FERRAMENTAS and resposta.turnos < self.max_turnos:
            resultados: list[ResultadoFerramenta] = []
            for chamada in turno.chamadas:
                inicio = time.perf_counter()
                resultado, execucao = self.ferramentas.executar(chamada)
                passo = Passo(
                    chamada,
                    resultado,
                    time.perf_counter() - inicio,
                    execucao.linhas if execucao else None,
                    execucao.sql if execucao else chamada.argumentos.get("sql"),
                )
                resposta.passos.append(passo)
                resultados.append(resultado)
                if ao_passo:
                    ao_passo(passo)
            turno = conversa.enviar_resultados(resultados)
            resposta.turnos += 1
            resposta.uso = resposta.uso + turno.uso
            if turno.texto:
                textos.append(turno.texto)

        resposta.parada = turno.parada
        resposta.detalhe = turno.detalhe
        # A resposta final é o último texto; os anteriores costumam ser só "vou consultar...".
        resposta.texto = turno.texto or (textos[-1] if textos else "")
        if turno.parada is Parada.FERRAMENTAS:
            resposta.parada = Parada.LIMITE
            resposta.detalhe = f"o agente não concluiu em {self.max_turnos} turnos"
        resposta.segundos = time.perf_counter() - relogio
        return resposta
