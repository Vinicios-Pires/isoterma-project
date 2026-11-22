import { fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { PontoSerie } from '@/api/tipos'
import { apiFalsa } from '@/testes/dados'
import { renderizarNaRota } from '@/testes/renderizar'

import { Detalhe } from './Detalhe'

const ROTAS = [
  { path: '/:simulacao/rack/:alvo', element: <Detalhe tipo="rack" /> },
  { path: '/:simulacao/crac/:alvo', element: <Detalhe tipo="crac" /> },
]

function serie(alvo: string, sufixos: string[]): { alvo: string; pontos: PontoSerie[] } {
  const pontos = sufixos.flatMap((s, i) =>
    [0, 1, 2].map((h) => ({
      inicio: `2026-11-01T0${h}:00:00Z`,
      sensor: `${alvo}/${s}`,
      tipo: s.startsWith('entrada') ? 'temp_entrada' : s,
      unidade: s === 'potencia' ? 'kW' : '°C',
      minimo: 19 + i,
      media: 20 + i,
      maximo: 21 + i,
      leituras: 60,
    })),
  )
  return { alvo, pontos }
}

afterEach(() => vi.unstubAllGlobals())

describe('Detalhe', () => {
  it('mostra a ficha do rack e os gráficos de temperatura e potência', async () => {
    const api = apiFalsa({
      '/api/demo/serie': serie('A-02', ['entrada-base', 'entrada-meio', 'entrada-topo', 'saida', 'potencia']),
    })
    vi.stubGlobal('fetch', vi.fn(api))

    renderizarNaRota('/demo/rack/A-02', ROTAS)

    expect(await screen.findByRole('img', { name: 'Gráfico: Temperatura' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Gráfico: Potência' })).toBeInTheDocument()
    expect(screen.getByText('Entrada · topo')).toBeInTheDocument()
    expect(await screen.findByRole('link', { name: 'CRAC-01' })).toHaveAttribute('href', '/demo/crac/CRAC-01')
  })

  it('pede a série do alvo com a janela da URL', async () => {
    const chamadas: string[] = []
    const api = apiFalsa({ '/api/demo/serie': serie('CRAC-01', ['insuflamento', 'retorno']) })
    vi.stubGlobal(
      'fetch',
      vi.fn((entrada: RequestInfo | URL) => {
        chamadas.push(String(entrada))
        return api(entrada)
      }),
    )

    renderizarNaRota('/demo/crac/CRAC-01?inicio=2026-11-01T01:00:00Z&fim=2026-11-01T02:00:00Z', ROTAS)

    expect(await screen.findByRole('img', { name: 'Gráfico: Temperatura do ar' })).toBeInTheDocument()
    const pedido = new URL(chamadas.find((c) => c.includes('/serie'))!)
    expect(pedido.searchParams.get('alvo')).toBe('CRAC-01')
    expect(pedido.searchParams.get('inicio')).toBe('2026-11-01T01:00:00Z')
    expect(screen.getByText('Racks da zona (3)')).toBeInTheDocument()
  })

  it('oferece a visão em tabela dos dados do gráfico', async () => {
    vi.stubGlobal('fetch', vi.fn(apiFalsa({ '/api/demo/serie': serie('CRAC-01', ['insuflamento', 'retorno']) })))

    renderizarNaRota('/demo/crac/CRAC-01', ROTAS)

    fireEvent.click(await screen.findByText('Ver como tabela'))
    expect(screen.getByRole('columnheader', { name: 'Insuflamento (°C)' })).toBeInTheDocument()
    expect(screen.getAllByRole('row')).toHaveLength(4) // cabeçalho + 3 instantes
  })
})
