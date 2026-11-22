// Séries temporais para os gráficos: uma linha por instante, uma coluna por sensor.
import type { PontoSerie } from '@/api/tipos'

export interface SerieGrafico {
  sensor: string
  nome: string
  cor: string
}

export interface Linha {
  t: number
  [chave: string]: number | null
}

/** Uma linha por instante, uma coluna por sensor (média, mínimo e máximo). */
export function pivotar(pontos: PontoSerie[], series: SerieGrafico[]): Linha[] {
  const sensores = new Set(series.map((s) => s.sensor))
  const porInstante = new Map<number, Linha>()
  for (const p of pontos) {
    if (!sensores.has(p.sensor)) continue
    const t = new Date(p.inicio).getTime()
    const linha = porInstante.get(t) ?? { t }
    linha[p.sensor] = p.media
    linha[`${p.sensor}:min`] = p.minimo
    linha[`${p.sensor}:max`] = p.maximo
    porInstante.set(t, linha)
  }
  return [...porInstante.values()].sort((a, b) => a.t - b.t)
}
