import type { Simulacao } from '@/api/tipos'

const HORA = 3_600_000

/** Janela de ±horas em volta de um instante, sem sair da simulação. Para links de outras telas. */
export function janelaEmVolta(instante: string, simulacao: Simulacao, horas = 6) {
  const centro = new Date(instante).getTime()
  const inicio = Math.max(new Date(simulacao.inicio).getTime(), centro - horas * HORA)
  const fim = Math.min(new Date(simulacao.fim).getTime(), centro + horas * HORA)
  return new URLSearchParams({ inicio: new Date(inicio).toISOString(), fim: new Date(fim).toISOString() })
}
