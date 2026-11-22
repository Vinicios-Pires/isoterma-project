import { describe, expect, it } from 'vitest'

import { corDoTexto, ESCALAS, FAIXA_ASHRAE } from './termica'

describe('escalas térmicas', () => {
  it('a entrada destaca os limites da faixa ASHRAE', () => {
    const entrada = ESCALAS.temp_entrada

    expect(entrada.destaques).toEqual([FAIXA_ASHRAE.minimo, FAIXA_ASHRAE.maximo])
    expect(entrada.limiares).toContain(18)
    expect(entrada.limiares).toContain(27)
  })

  it('frio é azul, quente é vermelho, e fora da escala satura', () => {
    const cor = ESCALAS.temp_entrada.cor

    expect(cor(14)).toBe(cor(5))
    expect(cor(34)).toBe(cor(60))
    const [r, , b] = cor(14).match(/\d+/g)!.map(Number)
    const [r2, , b2] = cor(32).match(/\d+/g)!.map(Number)
    expect(b).toBeGreaterThan(r)
    expect(r2).toBeGreaterThan(b2)
  })

  it('escolhe o texto com contraste', () => {
    expect(corDoTexto('#e8e1c8')).toBe('#1c1f24')
    expect(corDoTexto('#24508f')).toBe('#ffffff')
  })
})
