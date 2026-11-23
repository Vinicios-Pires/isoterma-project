import { fireEvent, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ANOMALIAS, apiFalsa } from '@/testes/dados'
import { renderizarNaRota } from '@/testes/renderizar'

import { Anomalias } from './Anomalias'

const ROTAS = [{ path: '/:simulacao/anomalias', element: <Anomalias /> }]

afterEach(() => vi.unstubAllGlobals())

describe('Anomalias', () => {
  it('mostra o placar contra o gabarito e os alertas', async () => {
    vi.stubGlobal('fetch', vi.fn(apiFalsa()))

    renderizarNaRota('/demo/anomalias', ROTAS)

    expect(await screen.findByText('recall 100%')).toBeInTheDocument()
    expect(screen.getByText('recall 100%').previousSibling).toHaveTextContent('1 de 1')
    expect(screen.getByText('precisão 50%').previousSibling).toHaveTextContent('1 de 2')
    expect(screen.getByText('precisão 50%')).toBeInTheDocument()
    expect(screen.getByText(/Rodaram em/)).toHaveTextContent('2,3 s sobre leituras brutas')
    expect(await screen.findByRole('img', { name: 'Linha do tempo: 2 alertas e 1 incidentes' })).toBeInTheDocument()
    // Tipos sem nenhum incidente nem alerta ficam fora da tabela por tipo.
    expect(screen.queryByRole('cell', { name: 'Sensor com picos' })).not.toBeInTheDocument()
  })

  it('o primeiro alerta já vem aberto, com a evidência e o incidente que ele acertou', async () => {
    vi.stubGlobal('fetch', vi.fn(apiFalsa()))

    renderizarNaRota('/demo/anomalias', ROTAS)

    expect(await screen.findByText(ANOMALIAS.alertas[0].evidencia)).toBeInTheDocument()
    expect(await screen.findByText(/No gabarito: CRAC-01 perdeu 100%/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Série de CRAC-01/ }).getAttribute('href')).toMatch(
      /^\/demo\/crac\/CRAC-01\?inicio=.*&alertas=1$/,
    )
  })

  it('filtra os falsos e abre o alerta escolhido', async () => {
    vi.stubGlobal('fetch', vi.fn(apiFalsa()))

    renderizarNaRota('/demo/anomalias', ROTAS)

    fireEvent.click(await screen.findByRole('button', { name: 'Falsos' }))
    const linhas = screen.getAllByRole('row').filter((r) => within(r).queryByText('B-02/saida'))
    expect(linhas).toHaveLength(1)
    expect(screen.queryByRole('cell', { name: 'CRAC-01' })).not.toBeInTheDocument()

    fireEvent.click(linhas[0])
    expect(await screen.findByText(ANOMALIAS.alertas[1].evidencia)).toBeInTheDocument()
    expect(screen.getByText(/Nenhum incidente do gabarito/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'No mapa' }).getAttribute('href')).toContain('rack=B-02')
  })

  it('sem gabarito, mostra só os alertas', async () => {
    const semGabarito = {
      ...ANOMALIAS,
      avaliacao: null,
      alertas: ANOMALIAS.alertas.map((a) => ({ ...a, incidentes: null })),
    }
    const fetch = vi.fn(apiFalsa({ '/api/demo/anomalias': semGabarito }))
    vi.stubGlobal('fetch', fetch)

    renderizarNaRota('/demo/anomalias', ROTAS)

    expect(await screen.findByText('Eventos físicos')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Falsos' })).not.toBeInTheDocument()
    expect(screen.queryByText('confirmado')).not.toBeInTheDocument()
    expect(fetch.mock.calls.some(([url]) => String(url).includes('/gabarito'))).toBe(false)
  })

  it('explica a espera e os erros', async () => {
    vi.stubGlobal('fetch', vi.fn(apiFalsa({}, ['/api/demo/anomalias'])))

    renderizarNaRota('/demo/anomalias', ROTAS)

    expect(screen.queryByText(/Rodando os detectores/) ?? (await screen.findByText(/Rodando os detectores/))).toBeTruthy()
    expect(await screen.findByText('A janela fica fora da simulação')).toBeInTheDocument()
  })
})
