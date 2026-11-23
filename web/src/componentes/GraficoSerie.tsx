// Série temporal de vários sensores numa escala só (um gráfico por unidade: nunca dois eixos).
// Linha da média por intervalo; o tooltip traz média, mínimo e máximo de cada série.
import { useMemo, useRef, useState, type PointerEvent } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { PontoSerie } from '@/api/tipos'
import { dataHora, numero, numeroCurto } from '@/lib/formato'
import { pivotar, type Linha, type SerieGrafico } from '@/lib/series'

export interface FaixaDestaque {
  inicio: string
  fim: string
  rotulo: string
  /** Padrão: cinza, como os incidentes do gabarito. */
  cor?: string
}

function Dica({
  active,
  payload,
  label,
  series,
  unidade,
  fuso,
}: {
  active?: boolean
  payload?: { payload: Linha }[]
  label?: number
  series: SerieGrafico[]
  unidade: string
  fuso: string
}) {
  if (!active || !payload?.length || label === undefined) return null
  const linha = payload[0].payload
  return (
    <div className="rounded-md border bg-popover px-3 py-2 text-xs shadow-md">
      <p className="tabular mb-1.5 font-mono text-muted-foreground">{dataHora(new Date(label).toISOString(), fuso)}</p>
      <table>
        <tbody>
          {series.map((s) => (
            <tr key={s.sensor}>
              <td className="pr-2">
                <svg width="14" height="4" aria-hidden="true">
                  <line x1="0" y1="2" x2="14" y2="2" stroke={s.cor} strokeWidth="2" />
                </svg>
              </td>
              <td className="tabular pr-2 text-right font-mono font-medium text-foreground">
                {numero(linha[s.sensor] ?? null, 1)} {unidade}
              </td>
              <td className="tabular pr-3 font-mono text-muted-foreground">
                {numero(linha[`${s.sensor}:min`] ?? null, 1)}–{numero(linha[`${s.sensor}:max`] ?? null, 1)}
              </td>
              <td className="text-muted-foreground">{s.nome}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const MARGEM = { top: 8, right: 12, bottom: 0, left: 0 }
const LARGURA_EIXO_Y = 40

export function GraficoSerie({
  titulo,
  pontos,
  series,
  unidade,
  fuso,
  referencias = [],
  faixas = [],
  altura = 240,
  sincronizar,
  aoAmpliar,
}: {
  titulo: string
  pontos: PontoSerie[]
  series: SerieGrafico[]
  unidade: string
  fuso: string
  /** Linhas horizontais de referência, como os limites da faixa ASHRAE. */
  referencias?: { valor: number; rotulo: string }[]
  /** Períodos destacados no fundo, como incidentes do gabarito. */
  faixas?: FaixaDestaque[]
  altura?: number
  /** Gráficos com o mesmo id movem a linha-guia juntos. */
  sincronizar?: string
  /** Chamado com o intervalo arrastado pelo usuário (instantes ISO). */
  aoAmpliar?: (inicio: string, fim: string) => void
}) {
  const linhas = useMemo(() => pivotar(pontos, series), [pontos, series])
  const [arraste, setArraste] = useState<{ de: number; ate: number } | null>(null)
  const area = useRef<HTMLDivElement>(null)

  // O arraste converte a posição do ponteiro em instante pela área de plotagem, que é definida
  // aqui mesmo (margens e largura do eixo y): não depende de eventos internos do Recharts.
  const instanteEm = (evento: PointerEvent<HTMLDivElement>): number | null => {
    const caixa = area.current?.getBoundingClientRect()
    if (!caixa || linhas.length < 2) return null
    const esquerda = caixa.left + MARGEM.left + LARGURA_EIXO_Y
    const direita = caixa.right - MARGEM.right
    const fracao = Math.min(1, Math.max(0, (evento.clientX - esquerda) / (direita - esquerda)))
    const [t0, t1] = [linhas[0].t, linhas[linhas.length - 1].t]
    return t0 + fracao * (t1 - t0)
  }

  const formatarEixo = (t: number) => dataHora(new Date(t).toISOString(), fuso)
  const terminarArraste = () => {
    const minimo = linhas.length > 1 ? (linhas[linhas.length - 1].t - linhas[0].t) / 100 : 0
    if (arraste && aoAmpliar && Math.abs(arraste.ate - arraste.de) > minimo) {
      const [de, ate] = [arraste.de, arraste.ate].sort((a, b) => a - b)
      aoAmpliar(new Date(de).toISOString(), new Date(ate).toISOString())
    }
    setArraste(null)
  }

  return (
    <figure className="space-y-2">
      <figcaption className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <span className="text-sm font-medium">{titulo}</span>
        {series.length > 1 && (
          <span className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
            {series.map((s) => (
              <span key={s.sensor} className="flex items-center gap-1.5">
                <svg width="16" height="4" aria-hidden="true">
                  <line x1="0" y1="2" x2="16" y2="2" stroke={s.cor} strokeWidth="2" />
                </svg>
                {s.nome}
              </span>
            ))}
          </span>
        )}
      </figcaption>

      <div
        ref={area}
        className={aoAmpliar ? 'cursor-crosshair touch-none select-none' : 'select-none'}
        style={{ height: altura }}
        aria-label={`Gráfico: ${titulo}`}
        role="img"
        onPointerDown={(e) => {
          const t = instanteEm(e)
          if (aoAmpliar && t !== null) {
            e.currentTarget.setPointerCapture(e.pointerId)
            setArraste({ de: t, ate: t })
          }
        }}
        onPointerMove={(e) => {
          const t = instanteEm(e)
          if (arraste && t !== null) setArraste({ ...arraste, ate: t })
        }}
        onPointerUp={terminarArraste}
        onPointerCancel={() => setArraste(null)}
      >
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={linhas}
            syncId={sincronizar}
            margin={MARGEM}
          >
            <CartesianGrid vertical={false} stroke="var(--border)" />
            <XAxis
              dataKey="t"
              type="number"
              scale="time"
              domain={['dataMin', 'dataMax']}
              tickFormatter={formatarEixo}
              tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
              stroke="var(--border)"
              minTickGap={48}
            />
            <YAxis
              domain={['auto', 'auto']}
              tickFormatter={(v: number) => numeroCurto(v)}
              tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
              stroke="var(--border)"
              width={LARGURA_EIXO_Y}
              unit={unidade === '°C' ? '°' : ''}
            />
            {faixas.map((f) => (
              <ReferenceArea
                key={`${f.inicio}-${f.rotulo}`}
                x1={new Date(f.inicio).getTime()}
                x2={new Date(f.fim).getTime()}
                fill={f.cor ?? 'var(--muted-foreground)'}
                fillOpacity={f.cor ? 0.16 : 0.12}
                ifOverflow="hidden"
                label={{
                  value: f.rotulo,
                  position: f.cor ? 'insideBottomLeft' : 'insideTopLeft',
                  fill: 'var(--muted-foreground)',
                  fontSize: 11,
                }}
              />
            ))}
            {referencias.map((r) => (
              <ReferenceLine
                key={r.valor}
                y={r.valor}
                stroke="var(--muted-foreground)"
                strokeDasharray="4 4"
                ifOverflow="extendDomain"
                label={{ value: r.rotulo, position: 'insideBottomRight', fill: 'var(--muted-foreground)', fontSize: 11 }}
              />
            ))}
            <Tooltip
              cursor={{ stroke: 'var(--muted-foreground)', strokeWidth: 1 }}
              content={<Dica series={series} unidade={unidade} fuso={fuso} />}
              isAnimationActive={false}
            />
            {series.map((s) => (
              <Line
                key={s.sensor}
                dataKey={s.sensor}
                name={s.nome}
                stroke={s.cor}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, strokeWidth: 2, stroke: 'var(--card)' }}
                isAnimationActive={false}
                connectNulls={false}
              />
            ))}
            {arraste && (
              <ReferenceArea x1={arraste.de} x2={arraste.ate} fill="var(--primary)" fillOpacity={0.15} />
            )}
          </LineChart>
        </ResponsiveContainer>
      </div>

      <details className="text-xs">
        <summary className="cursor-pointer text-muted-foreground hover:text-foreground">Ver como tabela</summary>
        <div className="mt-2 max-h-64 overflow-auto rounded-md border">
          <table className="tabular w-full font-mono">
            <thead className="sticky top-0 bg-card text-muted-foreground">
              <tr>
                <th className="px-2 py-1 text-left font-normal">Início</th>
                {series.map((s) => (
                  <th key={s.sensor} className="px-2 py-1 text-right font-normal">
                    {s.nome} ({unidade})
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {linhas.map((l) => (
                <tr key={l.t} className="border-t">
                  <td className="px-2 py-0.5">{formatarEixo(l.t)}</td>
                  {series.map((s) => (
                    <td key={s.sensor} className="px-2 py-0.5 text-right">
                      {numero(l[s.sensor] ?? null, 1)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  )
}
