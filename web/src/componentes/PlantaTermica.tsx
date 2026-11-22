// A planta do hall com o mapa térmico: faixas de cor interpoladas, isotermas e os racks por cima.
// O SVG trabalha em metros (ver lib/planta.ts para a geometria).
import { useMemo, useRef, useState, type PointerEvent } from 'react'

import type { Planta, TipoMapa, ValorRack } from '@/api/tipos'
import { comUnidade } from '@/lib/formato'
import { interpolar, isotermas, passoDaGrade } from '@/lib/isotermas'
import { geometria } from '@/lib/planta'
import { ESCALAS } from '@/lib/termica'

const RAIO_INTERPOLACAO = 2.6

interface Dica {
  rack: ValorRack
  x: number
  y: number
}

export function PlantaTermica({
  planta,
  racks,
  tipo,
  selecionado,
  aoSelecionar,
}: {
  planta: Planta
  racks: ValorRack[]
  tipo: TipoMapa
  selecionado?: string | null
  aoSelecionar?: (rackId: string) => void
}) {
  const g = useMemo(() => geometria(planta), [planta])
  const escala = ESCALAS[tipo]
  const caixa = useRef<HTMLDivElement>(null)
  const [dica, setDica] = useState<Dica | null>(null)

  const faixas = useMemo(() => {
    const pontos = racks
      .filter((r) => r.valor !== null)
      .map((r) => {
        const [x, y] = g.tela(r.x_m, r.y_m)
        return { x, y, valor: r.valor as number }
      })
    if (pontos.length === 0) return []
    const grade = interpolar(pontos, g.limites, passoDaGrade(g.limites), RAIO_INTERPOLACAO)
    return isotermas(grade, escala.limiares)
  }, [racks, g, escala])

  function mostrar(evento: PointerEvent, rack: ValorRack) {
    const area = caixa.current?.getBoundingClientRect()
    if (!area) return
    setDica({ rack, x: evento.clientX - area.left, y: evento.clientY - area.top })
  }

  const { x0, y0, x1, y1 } = g.limites
  return (
    <div ref={caixa} className="relative">
      <svg
        viewBox={`${x0} ${y0} ${x1 - x0} ${y1 - y0}`}
        className="h-auto max-h-[72vh] w-full rounded-lg bg-planta"
        role="img"
        aria-label={`Mapa térmico do hall: ${racks.length} racks`}
        onPointerLeave={() => setDica(null)}
      >
        <g opacity={0.85}>
          {faixas.map((f) => (
            <path key={`faixa-${f.valor}`} d={f.caminho} fill={escala.cor(f.valor)} />
          ))}
        </g>
        {faixas.map((f) => {
          const destaque = escala.destaques.includes(f.valor)
          return (
            <path
              key={`linha-${f.valor}`}
              d={f.caminho}
              fill="none"
              stroke={destaque ? (f.valor === escala.destaques.at(-1) ? '#b3261e' : '#1f4f8f') : '#000'}
              strokeOpacity={destaque ? 0.95 : 0.16}
              strokeWidth={destaque ? 2 : 0.8}
              strokeDasharray={destaque ? '6 3' : undefined}
              vectorEffect="non-scaling-stroke"
              data-isoterma={f.valor}
            />
          )
        })}

        {[...g.fileiras.map((r) => ({ ...r, tamanho: g.texto * 1.3 })), ...g.posicoes.map((r) => ({ ...r, tamanho: g.texto }))].map(
          (r) => (
            <text
              key={`${r.texto}-${r.x}-${r.y}`}
              x={r.x}
              y={r.y}
              fontSize={r.tamanho}
              textAnchor="middle"
              dominantBaseline="middle"
              className="fill-muted-foreground font-mono"
            >
              {r.texto}
            </text>
          ),
        )}

        {g.cracs.map(({ id, x, y }) => {
          return (
            <g key={id}>
              <rect
                x={x - g.texto * 2.1}
                y={y - g.texto * 0.85}
                width={g.texto * 4.2}
                height={g.texto * 1.7}
                rx={0.1}
                className="fill-card stroke-planta-linha"
                strokeWidth={1}
                vectorEffect="non-scaling-stroke"
              />
              <text
                x={x}
                y={y}
                fontSize={g.texto * 0.85}
                textAnchor="middle"
                dominantBaseline="middle"
                className="fill-foreground font-mono"
              >
                {id}
              </text>
            </g>
          )
        })}

        {racks.map((r) => {
          const [x, y] = g.tela(r.x_m, r.y_m)
          const fora = r.faixa === 'acima' || r.faixa === 'abaixo'
          const ativo = r.rack_id === selecionado
          return (
            <rect
              key={r.rack_id}
              x={x - g.rackLargura / 2}
              y={y - g.rackAltura / 2}
              width={g.rackLargura}
              height={g.rackAltura}
              rx={0.05}
              fill={r.valor === null ? 'transparent' : escala.cor(r.valor)}
              stroke={ativo ? 'currentColor' : fora ? (r.faixa === 'acima' ? '#b3261e' : '#1f4f8f') : 'rgb(0 0 0 / 0.35)'}
              strokeWidth={ativo ? 3 : fora ? 2 : 0.6}
              vectorEffect="non-scaling-stroke"
              className="cursor-pointer text-foreground"
              data-rack={r.rack_id}
              onPointerMove={(e) => mostrar(e, r)}
              onClick={() => aoSelecionar?.(r.rack_id)}
            />
          )
        })}
      </svg>

      {dica && (
        <div
          className="pointer-events-none absolute z-10 rounded-md border bg-popover px-3 py-2 text-xs shadow-md"
          style={{ left: dica.x + 14, top: dica.y + 14 }}
        >
          <p className="font-mono font-medium">{dica.rack.rack_id}</p>
          <p className="tabular">{comUnidade(dica.rack.valor, escala.unidade)}</p>
          <p className="text-muted-foreground">zona do {dica.rack.zona_crac}</p>
          {dica.rack.faixa && dica.rack.faixa !== 'ok' && (
            <p className={dica.rack.faixa === 'acima' ? 'text-quente' : 'text-frio'}>
              {dica.rack.faixa === 'acima' ? 'acima de 27 °C' : 'abaixo de 18 °C'}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

export function LegendaTermica({ tipo }: { tipo: TipoMapa }) {
  const escala = ESCALAS[tipo]
  const amostras = Array.from({ length: 24 }, (_, i) => escala.minimo + ((escala.maximo - escala.minimo) * i) / 23)
  const gradiente = `linear-gradient(to right, ${amostras.map((v) => escala.cor(v)).join(', ')})`
  const marcas = [escala.minimo, ...escala.destaques, escala.maximo]
  const posicao = (v: number) => `${((v - escala.minimo) / (escala.maximo - escala.minimo)) * 100}%`
  return (
    <div className="flex flex-wrap items-end gap-x-6 gap-y-2 text-xs text-muted-foreground">
      <div className="w-64">
        <div className="h-2.5 rounded-sm" style={{ background: gradiente }} />
        <div className="relative mt-1 h-4 font-mono">
          {marcas.map((v) => (
            <span key={v} className="absolute -translate-x-1/2" style={{ left: posicao(v) }}>
              {v}
            </span>
          ))}
        </div>
      </div>
      <span>{escala.unidade} · linhas finas a cada {escala.limiares[1] - escala.limiares[0]} {escala.unidade}</span>
      {escala.destaques.length > 0 && (
        <span className="flex items-center gap-1.5">
          <svg width="22" height="6" aria-hidden="true">
            <line x1="0" y1="3" x2="22" y2="3" stroke="#b3261e" strokeWidth="2" strokeDasharray="6 3" />
          </svg>
          faixa ASHRAE (18–27 °C)
        </span>
      )}
      <span>Entre os racks, valores interpolados</span>
    </div>
  )
}
