import { describe, expect, it } from 'vitest'

import { interpolar, isotermas, passoDaGrade, type PontoValor } from './isotermas'

const LIMITES = { x0: 0, y0: 0, x1: 4, y1: 2 }

describe('interpolar', () => {
  it('reproduz o valor exato em cima de um rack', () => {
    const pontos: PontoValor[] = [
      { x: 0, y: 0, valor: 20 },
      { x: 4, y: 2, valor: 30 },
    ]

    const grade = interpolar(pontos, LIMITES, 0.5, 10)

    expect(grade.valores[0]).toBe(20)
    expect(grade.valores[grade.valores.length - 1]).toBe(30)
  })

  it('fica entre os vizinhos no meio do caminho', () => {
    const pontos: PontoValor[] = [
      { x: 0, y: 1, valor: 20 },
      { x: 4, y: 1, valor: 30 },
    ]

    const grade = interpolar(pontos, LIMITES, 1, 10)
    const meio = grade.valores[2 * grade.nx + 2] // x = 2, y = 2: equidistante dos dois

    expect(meio).toBeCloseTo(25)
  })

  it('deixa NaN longe de qualquer rack', () => {
    const grade = interpolar([{ x: 0, y: 0, valor: 20 }], { x0: 0, y0: 0, x1: 10, y1: 0 }, 1, 2)

    expect(grade.valores[0]).toBe(20)
    expect(Number.isNaN(grade.valores[10])).toBe(true)
  })
})

describe('isotermas', () => {
  it('traça uma curva para cada limiar presente nos dados', () => {
    const pontos: PontoValor[] = [
      { x: 0, y: 0, valor: 18 },
      { x: 4, y: 0, valor: 30 },
      { x: 0, y: 2, valor: 18 },
      { x: 4, y: 2, valor: 30 },
    ]
    const grade = interpolar(pontos, LIMITES, 0.25, 10)

    const curvas = isotermas(grade, [20, 25, 40])

    expect(curvas.map((c) => c.valor)).toEqual([20, 25])
    expect(curvas.every((c) => c.caminho.startsWith('M'))).toBe(true)
  })

  it('usa as coordenadas da planta, em metros', () => {
    const grade = interpolar([{ x: 10, y: 5, valor: 30 }], { x0: 9, y0: 4, x1: 11, y1: 6 }, 0.5, 2)

    const [curva] = isotermas(grade, [25])
    const numeros = (curva?.caminho.match(/-?\d+(\.\d+)?/g) ?? []).map(Number)

    expect(Math.min(...numeros)).toBeGreaterThanOrEqual(3.7)
    expect(Math.max(...numeros)).toBeLessThanOrEqual(11.3)
  })
})

describe('passoDaGrade', () => {
  it('aumenta a célula em halls grandes e respeita o mínimo nos pequenos', () => {
    expect(passoDaGrade({ x0: 0, y0: 0, x1: 2, y1: 2 })).toBe(0.15)
    expect(passoDaGrade({ x0: 0, y0: 0, x1: 100, y1: 200 })).toBeCloseTo(1, 5)
  })
})
