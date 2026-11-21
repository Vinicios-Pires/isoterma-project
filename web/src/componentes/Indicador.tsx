import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

type Tom = 'neutro' | 'quente' | 'frio'

const TONS: Record<Tom, string> = {
  neutro: 'border-l-border',
  quente: 'border-l-quente',
  frio: 'border-l-frio',
}

export function Indicador({
  rotulo,
  valor,
  detalhe,
  tom = 'neutro',
}: {
  rotulo: string
  valor: ReactNode
  detalhe?: ReactNode
  tom?: Tom
}) {
  return (
    <div className={cn('rounded-lg border border-l-4 bg-card px-4 py-3', TONS[tom])}>
      <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{rotulo}</p>
      <p className="tabular mt-1 font-mono text-2xl font-medium">{valor}</p>
      {detalhe && <p className="tabular mt-0.5 text-xs text-muted-foreground">{detalhe}</p>}
    </div>
  )
}
