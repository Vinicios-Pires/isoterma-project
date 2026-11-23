import { describe, expect, it } from 'vitest'

import { ANOMALIAS, SIMULACAO } from '@/testes/dados'

import { linkDoDetalhe, linkDoMapa, momento, porcentagem, situacao } from './anomalias'

const [certo, falso] = ANOMALIAS.alertas

describe('anomalias', () => {
  it('classifica o alerta contra o gabarito', () => {
    expect(situacao(certo)).toBe('confirmado')
    expect(situacao(falso)).toBe('falso')
    expect(situacao({ ...certo, incidentes: null })).toBe('sem-gabarito')
  })

  it('mostra o hall meia hora depois do início, ou no meio de um alerta curto', () => {
    expect(momento(certo)).toBe('2026-11-01T02:34:00.000Z')
    expect(momento({ inicio: '2026-11-01T02:00:00Z', fim: '2026-11-01T02:20:00Z' })).toBe('2026-11-01T02:10:00.000Z')
  })

  it('monta os links do detalhe e do mapa', () => {
    const detalhe = new URL(linkDoDetalhe(falso, SIMULACAO), 'http://x')
    expect(detalhe.pathname).toBe('/demo/rack/B-02')
    expect(detalhe.searchParams.get('alertas')).toBe('1')
    expect(detalhe.searchParams.get('fim')).toBe('2026-11-01T16:30:00.000Z')
    expect(linkDoMapa(certo, 'demo')).toBe('/demo/mapa?t=2026-11-01T02%3A34%3A00.000Z')
  })

  it('formata porcentagens no padrão brasileiro', () => {
    expect(porcentagem(1)).toBe('100%')
    expect(porcentagem(0.967)).toBe('96,7%')
    expect(porcentagem(null)).toBe('—')
  })
})
