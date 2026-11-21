"""A API HTTP: o motor e o agente expostos para a web.

Cada rota é uma camada fina sobre o ``Hall``: as consultas, o SQL seguro e o agente são os
mesmos da CLI. O ``perguntar`` responde em streaming (SSE): cada consulta do agente chega ao
vivo, e a resposta vem no fim.
"""

import logging
import queue
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent

from isoterma import __version__
from isoterma.api import esquemas as e
from isoterma.dados import MANIFESTO, ler_manifesto
from isoterma.ia.agente import Agente, Passo, Resposta
from isoterma.ia.provedores import ErroProvedor, Provedor, criar_provedor
from isoterma.motor import Hall

log = logging.getLogger("isoterma.api")


# Parâmetros de janela de tempo, iguais em várias rotas.
Inicio = Annotated[datetime | None, Query(description="Horário local do hall se vier sem fuso")]
Fim = Annotated[datetime | None, Query(description="Fim da janela (exclusivo)")]


@dataclass(frozen=True)
class ConfigApi:
    dados: Path
    llm: str | None = None  # sem provedor, a IA fica desligada (resposta 503)
    perguntas_por_hora: int = 20  # por IP
    teto_diario_usd: float = 1.0  # custo estimado somado de todas as perguntas do dia (UTC)
    origens_cors: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
    confiar_proxy: bool = False  # usar X-Forwarded-For (atrás do Cloud Run, por exemplo)


@dataclass
class Limitador:
    """Protege a demo pública: perguntas por IP por hora e um teto de gasto por dia."""

    perguntas_por_hora: int
    teto_diario_usd: float
    _por_ip: dict[str, deque[float]] = field(default_factory=lambda: defaultdict(deque))
    _gasto: dict[date, float] = field(default_factory=lambda: defaultdict(float))
    _trava: threading.Lock = field(default_factory=threading.Lock)

    def reservar(self, ip: str) -> str | None:
        """Registra a pergunta, ou devolve o motivo da recusa."""
        agora = time.monotonic()
        with self._trava:
            if self._gasto[datetime.now(UTC).date()] >= self.teto_diario_usd:
                return "O limite de gasto diário da IA foi atingido. Tente de novo amanhã."
            historico = self._por_ip[ip]
            while historico and agora - historico[0] > 3600:
                historico.popleft()
            if len(historico) >= self.perguntas_por_hora:
                return f"Limite de {self.perguntas_por_hora} perguntas por hora atingido."
            historico.append(agora)
        return None

    def registrar_custo(self, valor_usd: float) -> None:
        with self._trava:
            self._gasto[datetime.now(UTC).date()] += valor_usd


class Catalogo:
    """As simulações da pasta de dados, abertas sob demanda e reaproveitadas entre pedidos."""

    def __init__(self, dados: Path) -> None:
        self.dados = dados.resolve()
        self._halls: dict[tuple[str, bool], Hall] = {}
        self._trava = threading.Lock()

    def nomes(self) -> list[str]:
        if not self.dados.is_dir():
            return []
        return sorted(p.name for p in self.dados.iterdir() if (p / MANIFESTO).is_file())

    def hall(self, nome: str, *, com_gabarito: bool = False) -> Hall:
        # O nome só é aceito se for uma das pastas listadas: nada de caminhos arbitrários.
        if nome not in self.nomes():
            raise HTTPException(404, f"Simulação {nome!r} não encontrada")
        chave = (nome, com_gabarito)
        with self._trava:
            if chave not in self._halls:
                self._halls[chave] = Hall(self.dados / nome, ocultar_gabarito=not com_gabarito)
            return self._halls[chave]

    def fechar(self) -> None:
        with self._trava:
            for hall in self._halls.values():
                hall.fechar()
            self._halls.clear()


def _linhas(hall: Hall, sql: str) -> list[dict[str, Any]]:
    return hall.consultar(sql, limite=1_000_000).linhas()


def _evento_passo(passo: Passo) -> e.EventoPasso:
    return e.EventoPasso(
        ferramenta=passo.chamada.nome,
        argumentos=passo.chamada.argumentos,
        segundos=round(passo.segundos, 3),
        linhas=passo.linhas,
        sql=passo.sql,
        erro=passo.resultado.erro,
        mensagem_erro=passo.resultado.conteudo if passo.resultado.erro else None,
    )


def _evento_resposta(resposta: Resposta) -> e.EventoResposta:
    return e.EventoResposta(
        texto=resposta.texto,
        parada=resposta.parada.value,
        detalhe=resposta.detalhe,
        provedor=resposta.provedor,
        modelo=resposta.modelo,
        turnos=resposta.turnos,
        segundos=round(resposta.segundos, 2),
        tokens_entrada=resposta.uso.entrada + resposta.uso.cache_leitura,
        tokens_saida=resposta.uso.saida,
        tokens_cache=resposta.uso.cache_leitura,
        custo_usd=resposta.custo_usd,
    )


def criar_app(
    config: ConfigApi, *, fabrica_provedor: Callable[[str], Provedor] = criar_provedor
) -> FastAPI:
    """Monta a aplicação. ``fabrica_provedor`` existe para os testes injetarem um provedor."""
    catalogo = Catalogo(config.dados)
    limitador = Limitador(config.perguntas_por_hora, config.teto_diario_usd)
    app = FastAPI(
        title="Isoterma",
        version=__version__,
        description="Inteligência térmica para data centers: veja, entenda e pergunte.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.origens_cors),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.state.catalogo = catalogo
    app.state.limitador = limitador

    @app.exception_handler(ValueError)
    def _valor_invalido(_: Request, erro: ValueError) -> JSONResponse:
        # Erros de domínio do motor (janela fora da simulação, alvo inexistente...) viram 400.
        return JSONResponse({"detail": str(erro)}, status_code=400)

    @app.get("/", include_in_schema=False)
    def raiz() -> RedirectResponse:
        return RedirectResponse("/docs")

    api = APIRouter(prefix="/api")

    @api.get("/saude")
    def saude() -> e.Saude:
        return e.Saude(
            status="ok", versao=__version__, simulacoes=len(catalogo.nomes()), llm=config.llm
        )

    @api.get("/simulacoes")
    def simulacoes() -> list[e.Simulacao]:
        resultado = []
        for nome in catalogo.nomes():
            hall = catalogo.hall(nome)
            manifesto = ler_manifesto(hall.diretorio)
            contagens = manifesto["contagens"]
            resultado.append(
                e.Simulacao(
                    nome=nome,
                    racks=contagens["racks"],
                    cracs=contagens["cracs"],
                    sensores=contagens["sensores"],
                    leituras=contagens["linhas"],
                    inicio=hall.inicio,
                    fim=hall.fim,
                    intervalo_s=hall.intervalo_s,
                    fuso=hall.fuso.key,
                    camadas=[c.tabela for c in hall.camadas],
                )
            )
        return resultado

    @api.get("/{simulacao}/planta")
    def planta(simulacao: str) -> e.Planta:
        hall = catalogo.hall(simulacao)
        racks = [e.RackPlanta(**r) for r in _linhas(hall, "SELECT * FROM racks ORDER BY rack_id")]
        cracs = [e.CracPlanta(**c) for c in _linhas(hall, "SELECT * FROM cracs ORDER BY crac_id")]
        xs = [r.x_m for r in racks] + [c.x_m for c in cracs]
        ys = [r.y_m for r in racks] + [c.y_m for c in cracs]
        return e.Planta(
            racks=racks,
            cracs=cracs,
            largura_m=round(max(xs) - min(xs), 2),
            profundidade_m=round(max(ys) - min(ys), 2),
        )

    @api.get("/{simulacao}/resumo")
    def resumo(simulacao: str, inicio: Inicio = None, fim: Fim = None) -> e.Resumo:
        return e.Resumo(**catalogo.hall(simulacao).resumo(inicio, fim))

    @api.get("/{simulacao}/mapa")
    def mapa(
        simulacao: str,
        instante: Annotated[
            datetime | None, Query(description="Padrão: o fim da simulação")
        ] = None,
        tipo: e.TipoSensorRack = "temp_entrada",
        altura: Annotated[e.Altura | None, Query(description="Só para temp_entrada")] = None,
    ) -> e.MapaTermico:
        hall = catalogo.hall(simulacao)
        tabela = hall.mapa_termico(instante, tipo=tipo, altura=altura)
        return e.MapaTermico(
            instante=hall.em_utc(instante, hall.fim),
            tipo=tipo,
            altura=altura,
            racks=[e.ValorRack(**r) for r in tabela.to_pylist()],
        )

    @api.get("/{simulacao}/fora-da-faixa")
    def fora_da_faixa(
        simulacao: str, inicio: Inicio = None, fim: Fim = None
    ) -> list[e.RackForaDaFaixa]:
        tabela = catalogo.hall(simulacao).fora_da_faixa(inicio, fim)
        return [e.RackForaDaFaixa(**r) for r in tabela.to_pylist()]

    @api.get("/{simulacao}/serie")
    def serie(
        simulacao: str,
        alvo: Annotated[str, Query(description="Sensor, rack ou CRAC, ex.: C-07")],
        inicio: Inicio = None,
        fim: Fim = None,
        pontos: Annotated[int, Query(ge=2, le=2_000)] = 500,
    ) -> e.Serie:
        tabela = catalogo.hall(simulacao).serie(alvo, inicio, fim, max_pontos=pontos)
        return e.Serie(alvo=alvo, pontos=[e.PontoSerie(**p) for p in tabela.to_pylist()])

    @api.get(
        "/{simulacao}/gabarito",
        description="Os incidentes injetados pelo simulador. Só existe porque os dados são "
        "simulados: serve para comparar o que aconteceu com o que o produto detectou. A IA não "
        "tem acesso a ele.",
    )
    def gabarito(simulacao: str) -> list[e.Incidente]:
        hall = catalogo.hall(simulacao, com_gabarito=True)
        return [e.Incidente(**i) for i in _linhas(hall, "SELECT * FROM incidentes ORDER BY inicio")]

    def preparar_pergunta(simulacao: str, request: Request) -> tuple[Hall, Provedor]:
        """Valida tudo antes de abrir o streaming, para os erros saírem como HTTP comum."""
        if config.llm is None:
            raise HTTPException(503, "A IA está desligada neste servidor (falta configurar o LLM)")
        hall = catalogo.hall(simulacao)
        try:
            provedor = fabrica_provedor(config.llm)
        except ErroProvedor as erro:
            raise HTTPException(503, str(erro)) from erro
        ip = request.client.host if request.client else "desconhecido"
        encaminhado = request.headers.get("x-forwarded-for")
        if config.confiar_proxy and encaminhado:
            ip = encaminhado.split(",")[0].strip()
        if motivo := limitador.reservar(ip):
            raise HTTPException(429, motivo)
        return hall, provedor

    @api.post(
        "/{simulacao}/perguntar",
        response_class=EventSourceResponse,
        description="Eventos SSE: `passo` (cada consulta do agente, ao vivo), `resposta` "
        "(o texto final, com uso e custo) ou `erro`.",
    )
    def perguntar(
        corpo: e.Pergunta,
        contexto: Annotated[tuple[Hall, Provedor], Depends(preparar_pergunta)],
    ) -> Iterator[ServerSentEvent]:
        hall, provedor = contexto
        fila: queue.Queue[ServerSentEvent | None] = queue.Queue()

        def rodar() -> None:
            try:
                resposta = Agente(hall, provedor).perguntar(
                    corpo.pergunta,
                    ao_passo=lambda p: fila.put(
                        ServerSentEvent(event="passo", data=_evento_passo(p))
                    ),
                )
                limitador.registrar_custo(resposta.custo_usd or 0.0)
                fila.put(ServerSentEvent(event="resposta", data=_evento_resposta(resposta)))
            except ErroProvedor as erro:
                fila.put(ServerSentEvent(event="erro", data=e.EventoErro(mensagem=str(erro))))
            except Exception:
                log.exception("Falha inesperada ao responder")
                mensagem = "Falha inesperada ao responder. Veja o log do servidor."
                fila.put(ServerSentEvent(event="erro", data=e.EventoErro(mensagem=mensagem)))
            finally:
                fila.put(None)

        threading.Thread(target=rodar, daemon=True).start()
        while (evento := fila.get()) is not None:
            yield evento

    app.include_router(api)
    return app
