// Nome e cor de cada tipo de incidente da simulação.
export const CATEGORIAS: Record<string, { nome: string; cor: string }> = {
  falha_crac: { nome: 'Falha de CRAC', cor: 'var(--quente)' },
  super_refrigeracao: { nome: 'Super-refrigeração', cor: 'var(--frio)' },
  rack_sobrecarregado: { nome: 'Sobrecarga de rack', cor: 'var(--chart-2)' },
  recirculacao: { nome: 'Recirculação', cor: 'var(--chart-5)' },
  sensor_congelado: { nome: 'Sensor travado', cor: 'var(--muted-foreground)' },
  sensor_deriva: { nome: 'Sensor com deriva', cor: 'var(--muted-foreground)' },
  sensor_picos: { nome: 'Sensor com picos', cor: 'var(--muted-foreground)' },
  sensor_sem_leitura: { nome: 'Sensor sem leitura', cor: 'var(--muted-foreground)' },
}
