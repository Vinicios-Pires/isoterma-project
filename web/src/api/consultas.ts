// Hooks do React Query sobre o cliente: cache, carregamento e erro de graça.
import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { api, type Janela } from './cliente'
import type { Altura, TipoMapa } from './tipos'

// Os dados de uma simulação não mudam enquanto a página está aberta.
const PARA_SEMPRE = Number.POSITIVE_INFINITY

export function useSimulacoes() {
  return useQuery({ queryKey: ['simulacoes'], queryFn: api.simulacoes, staleTime: 60_000 })
}

export function usePlanta(nome: string) {
  return useQuery({ queryKey: ['planta', nome], queryFn: () => api.planta(nome), staleTime: PARA_SEMPRE })
}

export function useResumo(nome: string, janela: Janela = {}) {
  return useQuery({
    queryKey: ['resumo', nome, janela],
    queryFn: () => api.resumo(nome, janela),
    staleTime: PARA_SEMPRE,
  })
}

export function useMapa(nome: string, instante: string | null, tipo: TipoMapa, altura: Altura | null) {
  return useQuery({
    queryKey: ['mapa', nome, instante, tipo, altura],
    queryFn: () => api.mapa(nome, instante, tipo, altura),
    staleTime: PARA_SEMPRE,
    // Ao arrastar o tempo, o mapa anterior fica na tela até o próximo chegar: sem piscar.
    placeholderData: keepPreviousData,
  })
}

export function useForaDaFaixa(nome: string, janela: Janela = {}) {
  return useQuery({
    queryKey: ['fora-da-faixa', nome, janela],
    queryFn: () => api.foraDaFaixa(nome, janela),
    staleTime: PARA_SEMPRE,
  })
}

export function useGabarito(nome: string, ativo = true) {
  return useQuery({
    queryKey: ['gabarito', nome],
    queryFn: () => api.gabarito(nome),
    staleTime: PARA_SEMPRE,
    enabled: ativo,
  })
}

/** Os alertas dos detectores. Na primeira visita a uma simulação, a API leva alguns segundos. */
export function useAnomalias(nome: string, ativo = true) {
  return useQuery({
    queryKey: ['anomalias', nome],
    queryFn: () => api.anomalias(nome),
    staleTime: PARA_SEMPRE,
    enabled: ativo,
  })
}

export function useSaude() {
  return useQuery({ queryKey: ['saude'], queryFn: api.saude, staleTime: 60_000 })
}

export function useSerie(nome: string, alvo: string, janela: Janela = {}, pontos = 400) {
  return useQuery({
    queryKey: ['serie', nome, alvo, janela, pontos],
    queryFn: () => api.serie(nome, alvo, janela, pontos),
    staleTime: PARA_SEMPRE,
    placeholderData: keepPreviousData,
  })
}
