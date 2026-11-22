import { describe, expect, it } from 'vitest'

import { comUnidade, dataHora, dataHoraCompleta, duracao, nomeFuso, numero } from './formato'

describe('números', () => {
  it('usam o padrão brasileiro', () => {
    expect(numero(43718400)).toBe('43.718.400')
    expect(numero(20.21, 1)).toBe('20,2')
    expect(numero(null)).toBe('—')
    expect(comUnidade(30.46, '°C')).toBe('30,5 °C')
  })
})

describe('datas', () => {
  it('aparecem no fuso do hall, não no de quem abre a página', () => {
    expect(dataHora('2026-11-07T05:11:00Z', 'America/Sao_Paulo')).toBe('07/11 02:11')
    expect(dataHoraCompleta('2026-11-07T05:11:00Z', 'UTC')).toBe('07/11/2026 05:11')
    expect(nomeFuso('2026-11-07T05:11:00Z', 'America/Sao_Paulo')).toBe('UTC-3')
  })
})

describe('duracao', () => {
  it('escolhe a unidade pelo tamanho', () => {
    expect(duracao(45)).toBe('45 min')
    expect(duracao(141)).toBe('2 h 21 min')
    expect(duracao(120)).toBe('2 h')
    expect(duracao(60 * 76)).toBe('3 d 4 h')
  })
})
