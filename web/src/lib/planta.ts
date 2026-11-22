// Geometria da planta: onde cada rack, CRAC e rótulo fica na tela, em metros. Um hall mais
// fundo que largo é desenhado girado (as fileiras viram colunas), para caber na tela.
import type { Planta } from '@/api/tipos'
import type { Limites } from '@/lib/isotermas'

const MARGEM = 1.0
// As caixas dos CRACs ficam um pouco para fora da parede, para não cobrir os rótulos.
const AFASTAMENTO_CRAC = 0.9

interface Rotulo {
  texto: string
  x: number
  y: number
}

/** Tudo o que a planta desenha, já nas coordenadas de tela (girado, se for o caso). */
export function geometria(planta: Planta) {
  const larguraReal = Math.max(...planta.racks.map((r) => r.x_m)) - Math.min(...planta.racks.map((r) => r.x_m))
  const fundoReal = Math.max(...planta.racks.map((r) => r.y_m)) - Math.min(...planta.racks.map((r) => r.y_m))
  const girado = fundoReal > larguraReal
  const tela = (x: number, y: number): [number, number] => (girado ? [y, x] : [x, y])

  const racksTela = planta.racks.map((r) => tela(r.x_m, r.y_m))
  const centro = [0, 1].map((i) => racksTela.reduce((s, p) => s + p[i], 0) / racksTela.length)
  // As paredes dos CRACs ficam no eixo perpendicular às fileiras: y sem giro, x girado.
  const eixoParede = girado ? 0 : 1
  const cracs = planta.cracs.map((c) => {
    const p = tela(c.x_m, c.y_m)
    p[eixoParede] += Math.sign(p[eixoParede] - centro[eixoParede]) * AFASTAMENTO_CRAC
    return { id: c.crac_id, x: p[0], y: p[1] }
  })
  const pontos = [...racksTela, ...cracs.map((c): [number, number] => [c.x, c.y])]
  const limites: Limites = {
    x0: Math.min(...pontos.map((p) => p[0])) - MARGEM,
    y0: Math.min(...pontos.map((p) => p[1])) - MARGEM,
    x1: Math.max(...pontos.map((p) => p[0])) + MARGEM,
    y1: Math.max(...pontos.map((p) => p[1])) + MARGEM,
  }

  // Tamanho do rack: o espaçamento entre vizinhos da mesma fileira, com uma folga.
  const primeiraFileira = planta.racks.filter((r) => r.fileira === planta.racks[0]?.fileira).map((r) => r.x_m)
  const passoRack = primeiraFileira.length > 1 ? Math.abs(primeiraFileira[1] - primeiraFileira[0]) : 0.6
  const linhas = [...new Set(planta.racks.map((r) => r.y_m))].sort((a, b) => a - b)
  const passoFileira = linhas.length > 1 ? linhas[1] - linhas[0] : 2.4
  const aoLongo = passoRack * 0.86 // ao longo da fileira
  const fundo = Math.min(1.0, passoFileira * 0.42) // de frente para trás do rack

  const texto = Math.max(0.26, Math.min(0.45, (limites.x1 - limites.x0) / 55))
  // Rótulos colados nos racks: as fileiras no lado das posições 1, e as posições ao lado da
  // primeira fileira.
  const minimoTela = [0, 1].map((i) => Math.min(...racksTela.map((p) => p[i])))
  const meiaLargura = (girado ? fundo : aoLongo) / 2
  const meiaAltura = (girado ? aoLongo : fundo) / 2
  const fileiras: Rotulo[] = [...new Map(planta.racks.map((r) => [r.fileira, r.y_m])).entries()].map(
    ([fileira, y]) => {
      const [tx, ty] = girado
        ? [y, minimoTela[1] - meiaAltura - texto]
        : [minimoTela[0] - meiaLargura - texto, y]
      return { texto: fileira, x: tx, y: ty }
    },
  )
  const posicoes: Rotulo[] = [...new Map(planta.racks.map((r) => [r.posicao, r.x_m])).entries()]
    .filter(([p]) => p === 1 || p % 5 === 0)
    .map(([p, x]) => {
      const [tx, ty] = girado
        ? [minimoTela[0] - meiaLargura - texto * 1.2, x]
        : [x, minimoTela[1] - meiaAltura - texto]
      return { texto: String(p), x: tx, y: ty }
    })

  return {
    girado,
    limites,
    tela,
    cracs,
    rackLargura: girado ? fundo : aoLongo,
    rackAltura: girado ? aoLongo : fundo,
    texto,
    fileiras,
    posicoes,
  }
}

export type Geometria = ReturnType<typeof geometria>
