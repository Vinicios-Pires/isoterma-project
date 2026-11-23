// Cliente da API. Em desenvolvimento, o Vite encaminha /api para o `isoterma servir` local.
import { lerEventos } from '@/lib/sse'

import type {
  Altura,
  Anomalias,
  EventoPergunta,
  Incidente,
  MapaTermico,
  Planta,
  RackForaDaFaixa,
  Resumo,
  Saude,
  Serie,
  Simulacao,
  TipoMapa,
} from './tipos'

const BASE = import.meta.env.VITE_API_URL ?? ''

export class ErroApi extends Error {
  readonly status: number

  constructor(status: number, mensagem: string) {
    super(mensagem)
    this.name = 'ErroApi'
    this.status = status
  }
}

type Parametros = Record<string, string | number | null | undefined>

export async function buscar<T>(caminho: string, parametros: Parametros = {}): Promise<T> {
  const url = new URL(`${BASE}/api${caminho}`, window.location.origin)
  for (const [chave, valor] of Object.entries(parametros)) {
    if (valor !== null && valor !== undefined && valor !== '') url.searchParams.set(chave, String(valor))
  }
  let resposta: Response
  try {
    resposta = await fetch(url)
  } catch {
    throw new ErroApi(0, 'Sem conexão com a API. Ela está rodando (`isoterma servir`)?')
  }
  if (!resposta.ok) throw await erroDaResposta(resposta)
  return (await resposta.json()) as T
}

async function erroDaResposta(resposta: Response): Promise<ErroApi> {
  const corpo = (await resposta.json().catch(() => null)) as { detail?: unknown } | null
  const detalhe = typeof corpo?.detail === 'string' ? corpo.detail : `Erro ${resposta.status} na API`
  return new ErroApi(resposta.status, detalhe)
}

/**
 * Faz uma pergunta à IA e devolve os eventos do streaming à medida que chegam: cada consulta
 * do agente (``passo``) e, no fim, a ``resposta`` ou um ``erro``.
 */
export async function* perguntar(
  nome: string,
  pergunta: string,
  sinal?: AbortSignal,
): AsyncGenerator<EventoPergunta> {
  let resposta: Response
  try {
    resposta = await fetch(`${BASE}/api/${encodeURIComponent(nome)}/perguntar`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pergunta }),
      signal: sinal,
    })
  } catch (erro) {
    if (sinal?.aborted) throw erro
    throw new ErroApi(0, 'Sem conexão com a API. Ela está rodando (`isoterma servir`)?')
  }
  if (!resposta.ok) throw await erroDaResposta(resposta)
  if (!resposta.body) throw new ErroApi(resposta.status, 'A API respondeu sem corpo')
  for await (const { evento, dados } of lerEventos(resposta.body)) {
    if (evento === 'passo' || evento === 'resposta' || evento === 'erro') {
      yield { tipo: evento, dados: JSON.parse(dados) } as EventoPergunta
    }
  }
}

export interface Janela {
  inicio?: string | null
  fim?: string | null
}

const sim = (nome: string) => `/${encodeURIComponent(nome)}`

export const api = {
  saude: () => buscar<Saude>('/saude'),
  simulacoes: () => buscar<Simulacao[]>('/simulacoes'),
  planta: (nome: string) => buscar<Planta>(`${sim(nome)}/planta`),
  resumo: (nome: string, janela: Janela = {}) =>
    buscar<Resumo>(`${sim(nome)}/resumo`, { ...janela }),
  mapa: (nome: string, instante: string | null, tipo: TipoMapa, altura: Altura | null) =>
    buscar<MapaTermico>(`${sim(nome)}/mapa`, { instante, tipo, altura }),
  foraDaFaixa: (nome: string, janela: Janela = {}) =>
    buscar<RackForaDaFaixa[]>(`${sim(nome)}/fora-da-faixa`, { ...janela }),
  serie: (nome: string, alvo: string, janela: Janela = {}, pontos = 500) =>
    buscar<Serie>(`${sim(nome)}/serie`, { alvo, pontos, ...janela }),
  gabarito: (nome: string) => buscar<Incidente[]>(`${sim(nome)}/gabarito`),
  anomalias: (nome: string) => buscar<Anomalias>(`${sim(nome)}/anomalias`),
}
