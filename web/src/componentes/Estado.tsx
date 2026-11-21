import { AlertTriangle } from 'lucide-react'
import type { ReactNode } from 'react'

import { ErroApi } from '@/api/cliente'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

export function Carregando({ className }: { className?: string }) {
  return <Skeleton className={cn('h-40 w-full', className)} aria-label="Carregando" />
}

export function Falha({ erro, titulo = 'Não deu para carregar os dados' }: { erro: unknown; titulo?: string }) {
  const mensagem = erro instanceof ErroApi || erro instanceof Error ? erro.message : String(erro)
  return (
    <div
      role="alert"
      className="flex items-start gap-3 rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm"
    >
      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" />
      <div>
        <p className="font-medium">{titulo}</p>
        <p className="mt-1 text-muted-foreground">{mensagem}</p>
      </div>
    </div>
  )
}

/** Mostra carregamento, erro ou o conteúdo, conforme o estado da consulta. */
export function Conteudo<T>({
  consulta,
  esqueleto,
  children,
}: {
  consulta: { data: T | undefined; error: unknown; isPending: boolean }
  esqueleto?: ReactNode
  children: (dados: T) => ReactNode
}) {
  if (consulta.error) return <Falha erro={consulta.error} />
  if (consulta.isPending || consulta.data === undefined) return esqueleto ?? <Carregando />
  return children(consulta.data)
}
