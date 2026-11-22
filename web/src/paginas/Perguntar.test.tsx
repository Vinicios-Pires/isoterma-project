import { fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { apiFalsa } from '@/testes/dados'
import { corpoEmPedacos } from '@/testes/fluxo'
import { renderizarNaRota } from '@/testes/renderizar'

import { Perguntar } from './Perguntar'

const ROTAS = [{ path: '/:simulacao/perguntar', element: <Perguntar /> }]

const PASSO = {
  ferramenta: 'consultar_sql',
  argumentos: { sql: 'SELECT count(*) FROM racks' },
  segundos: 0.02,
  linhas: 1,
  sql: 'SELECT count(*) FROM racks',
  erro: false,
  mensagem_erro: null,
}
const RESPOSTA = {
  texto: 'O hall tem **6 racks**.\n\nRESUMO',
  parada: 'fim',
  detalhe: '',
  provedor: 'claude',
  modelo: 'claude-haiku-5-5',
  turnos: 2,
  segundos: 3.2,
  tokens_entrada: 9000,
  tokens_saida: 120,
  tokens_cache: 4000,
  custo_usd: 0.0012,
}

/** A API falsa com /saude e um /perguntar que responde com os eventos dados. */
function apiComIa(eventos: string, llm: string | null = 'claude', status = 200) {
  const base = apiFalsa({ '/api/saude': { status: 'ok', versao: '0.1.0', simulacoes: 1, llm } })
  return vi.fn(async (entrada: RequestInfo | URL, opcoes?: RequestInit) => {
    if (String(entrada).endsWith('/perguntar')) {
      if (status !== 200) return new Response(JSON.stringify({ detail: 'Limite de 20 perguntas por hora atingido.' }), { status })
      expect(JSON.parse(String(opcoes?.body))).toEqual({ pergunta: 'Quantos racks?' })
      return new Response(corpoEmPedacos([eventos.slice(0, 40), eventos.slice(40)]), {
        headers: { 'Content-Type': 'text/event-stream' },
      })
    }
    return base(new URL(String(entrada), 'http://localhost'))
  })
}

function perguntarPor(texto: string) {
  fireEvent.change(screen.getByLabelText('Sua pergunta'), { target: { value: texto } })
  fireEvent.click(screen.getByRole('button', { name: 'Enviar pergunta' }))
}

afterEach(() => vi.unstubAllGlobals())

describe('Perguntar', () => {
  it('mostra as consultas, a resposta em markdown e o custo', async () => {
    const corpo = `event: passo\ndata: ${JSON.stringify(PASSO)}\n\nevent: resposta\ndata: ${JSON.stringify(RESPOSTA)}\n\n`
    vi.stubGlobal('fetch', apiComIa(corpo))
    renderizarNaRota('/demo/perguntar', ROTAS)

    perguntarPor(await screen.findByLabelText('Sua pergunta').then(() => 'Quantos racks?'))

    expect(await screen.findByText('6 racks')).toHaveProperty('tagName', 'STRONG')
    expect(screen.getByText('Quantos racks?')).toBeInTheDocument()
    expect(screen.getByText(/US\$ 0,0012/)).toBeInTheDocument()
    // Com a resposta pronta, a lista de consultas fica recolhida e pode ser aberta.
    fireEvent.click(screen.getByRole('button', { name: /1 consulta aos dados/ }))
    expect(screen.getByText(/consultar_sql/)).toBeInTheDocument()
  })

  it('mostra o erro do provedor que chega no meio do streaming', async () => {
    const corpo = `event: passo\ndata: ${JSON.stringify(PASSO)}\n\nevent: erro\ndata: {"mensagem":"A chave da API foi recusada"}\n\n`
    vi.stubGlobal('fetch', apiComIa(corpo))
    renderizarNaRota('/demo/perguntar', ROTAS)

    await screen.findByLabelText('Sua pergunta')
    perguntarPor('Quantos racks?')

    expect(await screen.findByText('A chave da API foi recusada')).toBeInTheDocument()
  })

  it('explica o limite de uso', async () => {
    vi.stubGlobal('fetch', apiComIa('', 'claude', 429))
    renderizarNaRota('/demo/perguntar', ROTAS)

    await screen.findByLabelText('Sua pergunta')
    perguntarPor('Quantos racks?')

    expect(await screen.findByText('Limite de 20 perguntas por hora atingido.')).toBeInTheDocument()
  })

  it('avisa quando a IA está desligada no servidor', async () => {
    vi.stubGlobal('fetch', apiComIa('', null))
    renderizarNaRota('/demo/perguntar', ROTAS)

    expect(await screen.findByText('A IA está desligada neste servidor')).toBeInTheDocument()
    expect(screen.queryByLabelText('Sua pergunta')).not.toBeInTheDocument()
  })
})
