// Escalas de cor dos dados térmicos. As cores são as mesmas nos temas claro e escuro: são dado,
// não interface.
import { scaleLinear } from 'd3-scale'

import type { TipoMapa } from '@/api/tipos'

/** Faixa recomendada pela ASHRAE para a entrada dos servidores (classe A1). */
export const FAIXA_ASHRAE = { minimo: 18, maximo: 27 } as const

export interface EscalaTermica {
  minimo: number
  maximo: number
  unidade: string
  /** Valores das isotermas desenhadas. */
  limiares: number[]
  /** Isotermas com traço forte: os limites da faixa ASHRAE. */
  destaques: number[]
  cor: (valor: number) => string
}

// Frio (azul) → faixa confortável (areia) → quente (âmbar, vermelho).
const AZUL_FUNDO = '#24508f'
const AZUL = '#3f8fcf'
const AREIA = '#e8e1c8'
const AMBAR = '#f0a03a'
const VERMELHO = '#d6432a'
const VINHO = '#86182b'

function escala(
  paradas: number[],
  cores: string[],
  passo: number,
  destaques: number[],
  unidade: string,
): EscalaTermica {
  const minimo = paradas[0]
  const maximo = paradas[paradas.length - 1]
  const cor = scaleLinear<string>().domain(paradas).range(cores).clamp(true)
  const limiares: number[] = []
  for (let v = Math.ceil(minimo / passo) * passo + passo; v < maximo; v += passo) limiares.push(v)
  return { minimo, maximo, unidade, limiares, destaques, cor: (v) => cor(v) }
}

export const ESCALAS: Record<TipoMapa, EscalaTermica> = {
  temp_entrada: escala(
    [14, FAIXA_ASHRAE.minimo, 21, FAIXA_ASHRAE.maximo, 31, 34],
    [AZUL_FUNDO, AZUL, AREIA, AMBAR, VERMELHO, VINHO],
    1,
    [FAIXA_ASHRAE.minimo, FAIXA_ASHRAE.maximo],
    '°C',
  ),
  temp_saida: escala([22, 30, 36, 42, 48], [AZUL, AREIA, AMBAR, VERMELHO, VINHO], 2, [], '°C'),
  potencia_kw: escala([0, 5, 10, 15, 18], [AREIA, AMBAR, VERMELHO, VINHO, VINHO], 1, [], 'kW'),
}

/** Texto escuro sobre cores claras e claro sobre as escuras. */
export function corDoTexto(fundo: string): string {
  const hex = fundo.startsWith('#') ? fundo.slice(1) : ''
  if (hex.length !== 6) return '#111'
  const [r, g, b] = [0, 2, 4].map((i) => Number.parseInt(hex.slice(i, i + 2), 16) / 255)
  const luminancia = 0.2126 * r + 0.7152 * g + 0.0722 * b
  return luminancia > 0.55 ? '#1c1f24' : '#ffffff'
}

export const NOMES_TIPO: Record<TipoMapa, string> = {
  temp_entrada: 'Entrada',
  temp_saida: 'Saída',
  potencia_kw: 'Potência',
}
