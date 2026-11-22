import { Pause, Play, SkipBack, SkipForward } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Slider } from '@/components/ui/slider'
import { dataHoraCompleta, nomeFuso } from '@/lib/formato'

const MINUTO = 60_000

/**
 * Linha do tempo da simulação: arrastar, avançar de passo em passo ou dar play. O valor é um
 * instante ISO em UTC; a exibição é no fuso do hall.
 */
export function ControleTempo({
  inicio,
  fim,
  valor,
  passoMin,
  fuso,
  tocando,
  carregando,
  aoMudar,
  aoTocar,
}: {
  inicio: string
  fim: string
  valor: string
  passoMin: number
  fuso: string
  tocando: boolean
  carregando: boolean
  aoMudar: (iso: string) => void
  aoTocar: (tocando: boolean) => void
}) {
  const t0 = new Date(inicio).getTime()
  const t1 = new Date(fim).getTime()
  const total = Math.floor((t1 - t0) / MINUTO / passoMin)
  const atual = Math.round((new Date(valor).getTime() - t0) / MINUTO / passoMin)
  const umaHora = Math.max(1, Math.round(60 / passoMin))

  const ir = (passos: number) => {
    const alvo = Math.min(total, Math.max(1, passos))
    aoMudar(new Date(t0 + alvo * passoMin * MINUTO).toISOString())
  }

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-3 rounded-lg border bg-card px-4 py-3">
      <div className="flex items-center gap-1">
        <Button variant="ghost" size="icon" onClick={() => ir(atual - umaHora)} aria-label="Voltar 1 hora" title="Voltar 1 hora">
          <SkipBack className="size-4" />
        </Button>
        <Button
          variant="secondary"
          size="icon"
          onClick={() => aoTocar(!tocando)}
          aria-label={tocando ? 'Pausar' : 'Reproduzir'}
          title={tocando ? 'Pausar' : 'Reproduzir'}
        >
          {tocando ? <Pause className="size-4" /> : <Play className="size-4" />}
        </Button>
        <Button variant="ghost" size="icon" onClick={() => ir(atual + umaHora)} aria-label="Avançar 1 hora" title="Avançar 1 hora">
          <SkipForward className="size-4" />
        </Button>
      </div>
      <div className="min-w-48 flex-1" role="group" aria-label="Instante do mapa">
        <Slider
          value={[atual]}
          min={1}
          max={total}
          step={1}
          onValueChange={(v) => ir(Array.isArray(v) ? (v[0] ?? atual) : v)}
        />
      </div>
      <p className="tabular w-52 text-right font-mono text-sm">
        {dataHoraCompleta(valor, fuso)}{' '}
        <span className="text-muted-foreground">{nomeFuso(valor, fuso)}</span>
        {carregando && <span className="sr-only"> carregando</span>}
      </p>
    </div>
  )
}
