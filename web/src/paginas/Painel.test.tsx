import { screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { apiFalsa } from '@/testes/dados'
import { renderizarNaRota } from '@/testes/renderizar'

import { Mapa } from './Mapa'
import { Painel } from './Painel'

const ROTAS = [
  { path: '/:simulacao', element: <Painel /> },
  { path: '/:simulacao/mapa', element: <Mapa /> },
]

afterEach(() => vi.unstubAllGlobals())

describe('Painel', () => {
  it('mostra os indicadores, os racks fora da faixa e os incidentes', async () => {
    vi.stubGlobal('fetch', vi.fn(apiFalsa()))

    renderizarNaRota('/demo', ROTAS)

    expect(await screen.findByText('43.718.400')).toBeInTheDocument()
    expect(screen.getByText('1.020,0 kW')).toBeInTheDocument()
    expect(await screen.findByText('A-03')).toBeInTheDocument()
    expect(screen.getByText('2 h 21 min')).toBeInTheDocument()
    // 02:11 UTC são 23:11 em Brasília, no dia anterior.
    expect(screen.getByRole('link', { name: '31/10 23:11' })).toHaveAttribute(
      'href',
      '/demo/mapa?t=2026-11-01T02%3A11%3A00Z&rack=A-03',
    )
    expect(await screen.findByText('Falha de CRAC')).toBeInTheDocument()
  })

  it('explica o erro quando a API falha', async () => {
    vi.stubGlobal('fetch', vi.fn(apiFalsa({}, ['/api/demo/resumo'])))

    renderizarNaRota('/demo', ROTAS)

    expect(await screen.findAllByText('A janela fica fora da simulação')).not.toHaveLength(0)
  })

  it('avisa quando a simulação não existe', async () => {
    vi.stubGlobal('fetch', vi.fn(apiFalsa()))

    renderizarNaRota('/nada', ROTAS)

    expect(await screen.findByText('Simulação "nada" não encontrada.')).toBeInTheDocument()
  })
})

describe('Mapa', () => {
  it('desenha a planta e resume o instante', async () => {
    vi.stubGlobal('fetch', vi.fn(apiFalsa()))

    renderizarNaRota('/demo/mapa?t=2026-11-01T03:50:00Z', ROTAS)

    expect(await screen.findByRole('img', { name: /Mapa térmico do hall: 6 racks/ })).toBeInTheDocument()
    expect(screen.getByText('3 racks')).toBeInTheDocument()
    expect(screen.getByText('0 racks')).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Instante do mapa' })).toBeInTheDocument()
    expect(screen.getByText('01/11/2026 00:50')).toBeInTheDocument() // 03:50 UTC no fuso do hall
  })
})
