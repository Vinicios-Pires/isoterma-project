// Ajudantes para os alertas dos detectores: situação contra o gabarito, links e janelas.
import type { Alerta, Simulacao } from '@/api/tipos'

import { janelaEmVolta } from './janela'

export type Situacao = 'confirmado' | 'falso' | 'sem-gabarito'

export function situacao(alerta: Alerta): Situacao {
  if (alerta.incidentes === null || alerta.incidentes === undefined) return 'sem-gabarito'
  return alerta.incidentes.length ? 'confirmado' : 'falso'
}

export function ehCrac(equipamento: string): boolean {
  return equipamento.startsWith('CRAC')
}

/** Duração do alerta em minutos. */
export function minutos(alerta: Pick<Alerta, 'inicio' | 'fim'>): number {
  return (new Date(alerta.fim).getTime() - new Date(alerta.inicio).getTime()) / 60_000
}

/** O instante para mostrar o hall: um pouco depois do início, quando o efeito já apareceu. */
export function momento(alerta: Pick<Alerta, 'inicio' | 'fim'>): string {
  const inicio = new Date(alerta.inicio).getTime()
  const fim = new Date(alerta.fim).getTime()
  return new Date(Math.min(fim, inicio + Math.min(30 * 60_000, (fim - inicio) / 2))).toISOString()
}

/** A página do rack ou CRAC, numa janela em volta do alerta e com os alertas à mostra. */
export function linkDoDetalhe(alerta: Alerta, simulacao: Simulacao): string {
  const duracaoH = minutos(alerta) / 60
  const parametros = janelaEmVolta(momento(alerta), simulacao, Math.min(72, Math.max(6, duracaoH * 1.5)))
  parametros.set('alertas', '1')
  const tipo = ehCrac(alerta.equipamento) ? 'crac' : 'rack'
  return `/${simulacao.nome}/${tipo}/${alerta.equipamento}?${parametros}`
}

export function linkDoMapa(alerta: Alerta, simulacao: string): string {
  const parametros = new URLSearchParams({ t: momento(alerta) })
  if (!ehCrac(alerta.equipamento)) parametros.set('rack', alerta.equipamento)
  return `/${simulacao}/mapa?${parametros}`
}

/** "96,7%": porcentagem com uma casa só quando precisa. */
export function porcentagem(valor: number | null | undefined): string {
  if (valor === null || valor === undefined) return '—'
  const casas = Number.isInteger(Math.round(valor * 1000) / 10) ? 0 : 1
  return `${(valor * 100).toFixed(casas).replace('.', ',')}%`
}
