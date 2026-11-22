import { describe, expect, it } from 'vitest'

import type { PontoSerie } from '@/api/tipos'
import { SIMULACAO } from '@/testes/dados'

import { janelaEmVolta } from './janela'
import { pivotar } from './series'

const ponto = (inicio: string, sensor: string, media: number): PontoSerie => ({
  inicio,
  sensor,
  tipo: 'temp_entrada',
  unidade: '°C',
  minimo: media - 1,
  media,
  maximo: media + 1,
  leituras: 60,
})

describe('pivotar', () => {
  it('junta os sensores numa linha por instante, em ordem', () => {
    const linhas = pivotar(
      [
        ponto('2026-11-01T01:00:00Z', 'A-01/saida', 31),
        ponto('2026-11-01T00:00:00Z', 'A-01/saida', 30),
        ponto('2026-11-01T00:00:00Z', 'A-01/entrada-topo', 21),
        ponto('2026-11-01T00:00:00Z', 'outro/sensor', 99),
      ],
      [
        { sensor: 'A-01/entrada-topo', nome: 'Topo', cor: 'x' },
        { sensor: 'A-01/saida', nome: 'Saída', cor: 'y' },
      ],
    )

    expect(linhas).toHaveLength(2)
    expect(linhas[0]).toMatchObject({ 'A-01/entrada-topo': 21, 'A-01/saida': 30, 'A-01/saida:max': 31 })
    expect(linhas[1]['A-01/saida']).toBe(31)
    expect(linhas[0]).not.toHaveProperty('outro/sensor')
  })
})

describe('janelaEmVolta', () => {
  it('abre seis horas para cada lado, sem sair da simulação', () => {
    const meio = janelaEmVolta('2026-11-01T12:00:00Z', SIMULACAO)
    const borda = janelaEmVolta('2026-11-01T02:00:00Z', SIMULACAO)

    expect(meio.get('inicio')).toBe('2026-11-01T06:00:00.000Z')
    expect(meio.get('fim')).toBe('2026-11-01T18:00:00.000Z')
    expect(borda.get('inicio')).toBe('2026-11-01T00:00:00.000Z')
  })
})
