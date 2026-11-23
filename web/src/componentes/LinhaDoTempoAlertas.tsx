// Alertas e incidentes do gabarito no mesmo eixo: em cada tipo, o que aconteceu (em cima) e o
// que os detectores viram (embaixo). Um alerta sem par no gabarito é falso; um incidente sem
// alerta embaixo foi perdido.
import { scaleTime } from 'd3-scale'

import type { Alerta, Incidente } from '@/api/tipos'
import { data, dataHora } from '@/lib/formato'
import { CATEGORIAS } from '@/lib/incidentes'
import { situacao } from '@/lib/anomalias'

const LARGURA = 1000
const ALTURA_LINHA = 34
const ROTULOS = 170
const EIXO = 24

export function LinhaDoTempoAlertas({
  alertas,
  incidentes,
  perdidos = [],
  inicio,
  fim,
  fuso,
  selecionado,
  aoEscolher,
}: {
  alertas: Alerta[]
  incidentes: Incidente[]
  perdidos?: number[]
  inicio: string
  fim: string
  fuso: string
  selecionado?: number | null
  aoEscolher?: (alerta: Alerta) => void
}) {
  const tipos = Object.keys(CATEGORIAS).filter(
    (t) => alertas.some((a) => a.tipo === t) || incidentes.some((i) => i.tipo === t),
  )
  const x = scaleTime()
    .domain([new Date(inicio), new Date(fim)])
    .range([ROTULOS, LARGURA - 8])
  const altura = tipos.length * ALTURA_LINHA + EIXO
  const largura = (de: string, ate: string) => Math.max(3, x(new Date(ate)) - x(new Date(de)))
  const temGabarito = incidentes.length > 0

  if (tipos.length === 0) return <p className="text-sm text-muted-foreground">Nenhum alerta nesta simulação.</p>
  return (
    <svg
      viewBox={`0 0 ${LARGURA} ${altura}`}
      className="h-auto w-full"
      role="img"
      aria-label={`Linha do tempo: ${alertas.length} alertas${temGabarito ? ` e ${incidentes.length} incidentes` : ''}`}
    >
      {x.ticks(8).map((m) => (
        <g key={m.toISOString()}>
          <line x1={x(m)} x2={x(m)} y1={0} y2={altura - EIXO} className="stroke-border" />
          <text x={x(m)} y={altura - 6} fontSize={11} textAnchor="middle" className="fill-muted-foreground font-mono">
            {data(m.toISOString(), fuso)}
          </text>
        </g>
      ))}
      {tipos.map((tipo, linha) => {
        const y = linha * ALTURA_LINHA
        const cor = CATEGORIAS[tipo].cor
        return (
          <g key={tipo}>
            <text x={0} y={y + ALTURA_LINHA / 2} fontSize={12} dominantBaseline="middle" className="fill-foreground">
              {CATEGORIAS[tipo].nome}
            </text>
            {incidentes
              .filter((i) => i.tipo === tipo)
              .map((i) => {
                const perdido = perdidos.includes(i.incidente_id)
                return (
                  <rect
                    key={`i-${i.incidente_id}`}
                    x={x(new Date(i.inicio))}
                    y={y + 5}
                    width={largura(i.inicio, i.fim)}
                    height={8}
                    rx={2}
                    fill={cor}
                    fillOpacity={0.35}
                    stroke={perdido ? 'var(--destructive)' : 'none'}
                    strokeWidth={perdido ? 1.5 : 0}
                    strokeDasharray={perdido ? '3 2' : undefined}
                    data-incidente={i.incidente_id}
                  >
                    <title>{`${perdido ? 'Perdido: ' : 'Gabarito: '}${i.descricao}\n${dataHora(i.inicio, fuso)} a ${dataHora(i.fim, fuso)}`}</title>
                  </rect>
                )
              })}
            {alertas
              .filter((a) => a.tipo === tipo)
              .map((a) => {
                const falso = situacao(a) === 'falso'
                const ativo = a.alerta_id === selecionado
                return (
                  <g key={`a-${a.alerta_id}`} className="cursor-pointer" onClick={() => aoEscolher?.(a)}>
                    {/* Área de clique maior que a marca, para os alertas curtos. */}
                    <rect x={x(new Date(a.inicio)) - 4} y={y + 13} width={largura(a.inicio, a.fim) + 8} height={18} fill="transparent" />
                    <rect
                      x={x(new Date(a.inicio))}
                      y={y + 16}
                      width={largura(a.inicio, a.fim)}
                      height={12}
                      rx={3}
                      fill={falso ? 'var(--card)' : cor}
                      stroke={ativo ? 'var(--foreground)' : falso ? 'var(--destructive)' : 'none'}
                      strokeWidth={ativo ? 2 : 1.5}
                      className="hover:opacity-80"
                      data-alerta={a.alerta_id}
                    >
                      <title>{`${falso ? 'Alerta falso: ' : ''}${a.alvo}: ${a.evidencia}\n${dataHora(a.inicio, fuso)} a ${dataHora(a.fim, fuso)}`}</title>
                    </rect>
                  </g>
                )
              })}
          </g>
        )
      })}
    </svg>
  )
}

export function LegendaAlertas({ comGabarito }: { comGabarito: boolean }) {
  return (
    <div className="flex flex-wrap gap-x-5 gap-y-1.5 text-xs text-muted-foreground">
      {comGabarito && (
        <span className="flex items-center gap-1.5">
          <svg width="22" height="8" aria-hidden="true">
            <rect width="22" height="8" rx="2" fill="var(--chart-1)" fillOpacity="0.35" />
          </svg>
          incidente do gabarito (em cima)
        </span>
      )}
      <span className="flex items-center gap-1.5">
        <svg width="22" height="12" aria-hidden="true">
          <rect width="22" height="12" rx="3" fill="var(--chart-1)" />
        </svg>
        alerta do Isoterma (embaixo)
      </span>
      {comGabarito && (
        <>
          <span className="flex items-center gap-1.5">
            <svg width="22" height="12" aria-hidden="true">
              <rect x="1" y="1" width="20" height="10" rx="3" fill="var(--card)" stroke="var(--destructive)" strokeWidth="1.5" />
            </svg>
            alerta falso
          </span>
          <span className="flex items-center gap-1.5">
            <svg width="22" height="8" aria-hidden="true">
              <rect x="1" y="1" width="20" height="6" rx="2" fill="var(--chart-1)" fillOpacity="0.35" stroke="var(--destructive)" strokeDasharray="3 2" />
            </svg>
            incidente perdido
          </span>
        </>
      )}
      <span>Clique num alerta para ver os detalhes</span>
    </div>
  )
}
