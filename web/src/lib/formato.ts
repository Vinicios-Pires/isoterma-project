// Formatação no padrão brasileiro e no fuso do hall (não no fuso de quem abre a página).

const numeros = new Map<number, Intl.NumberFormat>()

export function numero(valor: number | null | undefined, casas = 0): string {
  if (valor === null || valor === undefined || Number.isNaN(valor)) return '—'
  let formato = numeros.get(casas)
  if (!formato) {
    formato = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas })
    numeros.set(casas, formato)
  }
  return formato.format(valor)
}

/** Até uma casa decimal, sem zeros sobrando: 2, 2,5, 18. Para eixos de gráfico. */
export function numeroCurto(valor: number): string {
  return new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 1 }).format(valor)
}

export const UNIDADES = { temp_entrada: '°C', temp_saida: '°C', potencia_kw: 'kW' } as const

export function comUnidade(valor: number | null | undefined, unidade: string, casas = 1): string {
  return valor === null || valor === undefined ? '—' : `${numero(valor, casas)} ${unidade}`
}

function formatador(fuso: string, opcoes: Intl.DateTimeFormatOptions) {
  return new Intl.DateTimeFormat('pt-BR', { timeZone: fuso, hourCycle: 'h23', ...opcoes })
}

/** "07/11 04:15" no fuso do hall. */
export function dataHora(iso: string, fuso: string): string {
  return formatador(fuso, { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
    .format(new Date(iso))
    .replace(',', '')
}

/** "07/11/2026 04:15" no fuso do hall. */
export function dataHoraCompleta(iso: string, fuso: string): string {
  return formatador(fuso, {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
    .format(new Date(iso))
    .replace(',', '')
}

/** "07/11" no fuso do hall. */
export function data(iso: string, fuso: string): string {
  return formatador(fuso, { day: '2-digit', month: '2-digit' }).format(new Date(iso))
}

/** "2 h 21 min", "45 min", "3 d 4 h". */
export function duracao(minutos: number): string {
  const total = Math.round(minutos)
  if (total < 60) return `${total} min`
  const horas = Math.floor(total / 60)
  if (horas < 48) return total % 60 ? `${horas} h ${total % 60} min` : `${horas} h`
  const dias = Math.floor(horas / 24)
  return horas % 24 ? `${dias} d ${horas % 24} h` : `${dias} d`
}

/** Abreviação do fuso, como "-03". */
export function nomeFuso(iso: string, fuso: string): string {
  const partes = formatador(fuso, { timeZoneName: 'shortOffset' }).formatToParts(new Date(iso))
  return partes.find((p) => p.type === 'timeZoneName')?.value.replace('GMT', 'UTC') ?? fuso
}
