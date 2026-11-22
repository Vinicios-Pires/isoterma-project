import { describe, expect, it } from 'vitest'

import type { Planta } from '@/api/tipos'
import { PLANTA } from '@/testes/dados'

import { geometria } from './planta'

describe('geometria da planta', () => {
  it('gira um hall mais fundo que largo e troca as dimensões do rack', () => {
    const g = geometria(PLANTA) // 3 racks por fileira (1,2 m) e 2 fileiras (2,4 m)

    expect(g.girado).toBe(true)
    expect(g.tela(1.2, 2.4)).toEqual([2.4, 1.2])
    expect(g.rackLargura).toBeGreaterThan(g.rackAltura)
  })

  it('não gira um hall mais largo que fundo', () => {
    const largo: Planta = {
      ...PLANTA,
      racks: PLANTA.racks.map((r) => ({ ...r, x_m: r.posicao * 3 })),
    }

    const g = geometria(largo)

    expect(g.girado).toBe(false)
    expect(g.tela(3, 0)).toEqual([3, 0])
  })

  it('afasta os CRACs da parede, para fora do hall', () => {
    const g = geometria(PLANTA)
    const [cima, baixo] = g.cracs

    // Girado, a parede fica no eixo x: -1,5 vai para -2,4 e 3,9 vai para 4,8.
    expect(cima.x).toBeCloseTo(-2.4)
    expect(baixo.x).toBeCloseTo(4.8)
    expect(g.limites.x0).toBeLessThan(cima.x)
    expect(g.limites.x1).toBeGreaterThan(baixo.x)
  })

  it('rotula as fileiras e as posições 1, 5, 10...', () => {
    const g = geometria(PLANTA)

    expect(g.fileiras.map((r) => r.texto)).toEqual(['A', 'B'])
    expect(g.posicoes.map((r) => r.texto)).toEqual(['1'])
  })
})
