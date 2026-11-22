// Isotermas: linhas que ligam pontos de mesma temperatura sobre a planta do hall.
//
// Os sensores ficam nos racks, então a temperatura entre eles é estimada: os valores dos racks
// são interpolados numa grade fina (inverso da distância ao quadrado, só com os racks próximos)
// e o d3-contour traça as curvas de nível dessa grade.
import { contours } from 'd3-contour'
import { geoIdentity, geoPath } from 'd3-geo'

export interface PontoValor {
  x: number
  y: number
  valor: number
}

export interface Limites {
  x0: number
  y0: number
  x1: number
  y1: number
}

export interface Grade {
  x0: number
  y0: number
  passo: number
  nx: number
  ny: number
  /** Linha a linha (y), da esquerda para a direita (x). NaN onde não há rack por perto. */
  valores: Float64Array
}

/** Tamanho da célula para a grade ter perto de ``celulas`` células, nunca abaixo de ``minimo``. */
export function passoDaGrade(limites: Limites, celulas = 20_000, minimo = 0.15): number {
  const area = (limites.x1 - limites.x0) * (limites.y1 - limites.y0)
  return Math.max(minimo, Math.sqrt(area / celulas))
}

export function interpolar(pontos: PontoValor[], limites: Limites, passo: number, raio: number): Grade {
  const nx = Math.max(2, Math.ceil((limites.x1 - limites.x0) / passo) + 1)
  const ny = Math.max(2, Math.ceil((limites.y1 - limites.y0) / passo) + 1)
  const valores = new Float64Array(nx * ny)
  const raio2 = raio * raio

  // Baldes espaciais de tamanho ``raio``: cada célula só olha os racks dos baldes vizinhos.
  const baldes = new Map<string, PontoValor[]>()
  const chave = (bx: number, by: number) => `${bx},${by}`
  for (const p of pontos) {
    const k = chave(Math.floor((p.x - limites.x0) / raio), Math.floor((p.y - limites.y0) / raio))
    const balde = baldes.get(k)
    if (balde) balde.push(p)
    else baldes.set(k, [p])
  }

  for (let j = 0; j < ny; j++) {
    const y = limites.y0 + j * passo
    const by = Math.floor((y - limites.y0) / raio)
    for (let i = 0; i < nx; i++) {
      const x = limites.x0 + i * passo
      const bx = Math.floor((x - limites.x0) / raio)
      let soma = 0
      let pesos = 0
      let exato: number | null = null
      for (let dy = -1; dy <= 1 && exato === null; dy++) {
        for (let dx = -1; dx <= 1 && exato === null; dx++) {
          for (const p of baldes.get(chave(bx + dx, by + dy)) ?? []) {
            const d2 = (p.x - x) ** 2 + (p.y - y) ** 2
            if (d2 > raio2) continue
            if (d2 < 1e-9) {
              exato = p.valor
              break
            }
            const peso = 1 / d2
            soma += peso * p.valor
            pesos += peso
          }
        }
      }
      valores[j * nx + i] = exato ?? (pesos > 0 ? soma / pesos : Number.NaN)
    }
  }
  return { x0: limites.x0, y0: limites.y0, passo, nx, ny, valores }
}

export interface Isoterma {
  valor: number
  /** Caminho SVG em metros (mesmo sistema de coordenadas da planta). */
  caminho: string
}

/**
 * As regiões com valor ≥ cada limiar, como caminhos SVG. Pintadas em ordem crescente, formam
 * faixas de cor; o contorno de cada uma é a isoterma daquele valor.
 */
export function isotermas(grade: Grade, limiares: number[]): Isoterma[] {
  const gerador = contours().size([grade.nx, grade.ny]).thresholds(limiares)
  // O d3-contour usa a célula (i, j) como o quadrado [i, i+1] × [j, j+1]; o centro dela é o
  // ponto amostrado em x0 + i·passo. Daí o meio passo de deslocamento.
  const projecao = geoIdentity()
    .scale(grade.passo)
    .translate([grade.x0 - grade.passo / 2, grade.y0 - grade.passo / 2])
  const caminho = geoPath(projecao)
  return gerador(Array.from(grade.valores))
    .filter((c) => c.coordinates.length > 0)
    .map((c) => ({ valor: c.value, caminho: caminho(c) ?? '' }))
}
