// Cliente da API. Em desenvolvimento, o Vite encaminha /api para o `isoterma servir` local.
import type {
  Altura,
  Incidente,
  MapaTermico,
  Planta,
  RackForaDaFaixa,
  Resumo,
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
  if (!resposta.ok) {
    const corpo = (await resposta.json().catch(() => null)) as { detail?: unknown } | null
    const detalhe = typeof corpo?.detail === 'string' ? corpo.detail : `Erro ${resposta.status} na API`
    throw new ErroApi(resposta.status, detalhe)
  }
  return (await resposta.json()) as T
}

export interface Janela {
  inicio?: string | null
  fim?: string | null
}

const sim = (nome: string) => `/${encodeURIComponent(nome)}`

export const api = {
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
}
