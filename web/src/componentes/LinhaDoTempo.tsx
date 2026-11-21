// Os incidentes injetados pela simulação ao longo do período, um tipo por linha.
import { scaleTime } from 'd3-scale'

import type { Incidente } from '@/api/tipos'
import { data, dataHora } from '@/lib/formato'
import { CATEGORIAS } from '@/lib/incidentes'

const LARGURA = 1000
const ALTURA_LINHA = 26
const ROTULOS = 170
const EIXO = 24

export function LinhaDoTempo({
  incidentes,
  inicio,
  fim,
  fuso,
  aoEscolher,
}: {
  incidentes: Incidente[]
  inicio: string
  fim: string
  fuso: string
  aoEscolher?: (incidente: Incidente) => void
}) {
  const tipos = Object.keys(CATEGORIAS).filter((t) => incidentes.some((i) => i.tipo === t))
  const x = scaleTime()
    .domain([new Date(inicio), new Date(fim)])
    .range([ROTULOS, LARGURA - 8])
  const altura = tipos.length * ALTURA_LINHA + EIXO
  const marcas = x.ticks(8)

  if (incidentes.length === 0) {
    return <p className="text-sm text-muted-foreground">Nenhum incidente nesta simulação.</p>
  }
  return (
    <svg viewBox={`0 0 ${LARGURA} ${altura}`} className="h-auto w-full" role="img" aria-label="Linha do tempo dos incidentes">
      {marcas.map((m) => (
        <g key={m.toISOString()}>
          <line x1={x(m)} x2={x(m)} y1={0} y2={altura - EIXO} className="stroke-border" />
          <text x={x(m)} y={altura - 6} fontSize={11} textAnchor="middle" className="fill-muted-foreground font-mono">
            {data(m.toISOString(), fuso)}
          </text>
        </g>
      ))}
      {tipos.map((tipo, linha) => {
        const y = linha * ALTURA_LINHA
        return (
          <g key={tipo}>
            <text x={0} y={y + ALTURA_LINHA / 2} fontSize={12} dominantBaseline="middle" className="fill-foreground">
              {CATEGORIAS[tipo].nome}
            </text>
            {incidentes
              .filter((i) => i.tipo === tipo)
              .map((i) => {
                const x0 = x(new Date(i.inicio))
                const largura = Math.max(4, x(new Date(i.fim)) - x0)
                return (
                  <rect
                    key={i.incidente_id}
                    x={x0}
                    y={y + 6}
                    width={largura}
                    height={ALTURA_LINHA - 12}
                    rx={3}
                    fill={CATEGORIAS[tipo].cor}
                    className="cursor-pointer opacity-85 hover:opacity-100"
                    onClick={() => aoEscolher?.(i)}
                  >
                    <title>{`${i.descricao}\n${dataHora(i.inicio, fuso)} a ${dataHora(i.fim, fuso)}`}</title>
                  </rect>
                )
              })}
          </g>
        )
      })}
    </svg>
  )
}
