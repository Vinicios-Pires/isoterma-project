import { useParams } from 'react-router'

import { useSimulacoes } from '@/api/consultas'
import type { Simulacao } from '@/api/tipos'

/** A simulação da URL (/:simulacao/...), com o estado da consulta que a carrega. */
export function useSimulacao(): {
  nome: string
  simulacao: Simulacao | undefined
  carregando: boolean
  erro: unknown
} {
  const { simulacao: nome = '' } = useParams()
  const consulta = useSimulacoes()
  const simulacao = consulta.data?.find((s) => s.nome === nome)
  const erro =
    consulta.error ?? (consulta.data && !simulacao ? new Error(`Simulação "${nome}" não encontrada.`) : null)
  return { nome, simulacao, carregando: consulta.isPending, erro }
}
