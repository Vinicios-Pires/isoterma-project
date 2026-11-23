// Dados de exemplo para os testes: um hall de 2 fileiras com 3 racks e 2 CRACs.
import type { Anomalias, Incidente, MapaTermico, Planta, RackForaDaFaixa, Resumo, Simulacao, ValorRack } from '@/api/tipos'

export const SIMULACAO: Simulacao = {
  nome: 'demo',
  racks: 6,
  cracs: 2,
  sensores: 34,
  leituras: 43_718_400,
  inicio: '2026-11-01T00:00:00Z',
  fim: '2026-11-02T00:00:00Z',
  intervalo_s: 60,
  fuso: 'America/Sao_Paulo',
  camadas: ['leituras', 'agregados_hora'],
}

const racks = ['A', 'B'].flatMap((fileira, f) =>
  [1, 2, 3].map((posicao) => ({
    rack_id: `${fileira}-0${posicao}`,
    fileira,
    posicao,
    x_m: (posicao - 1) * 0.6,
    y_m: f * 2.4,
    potencia_nominal_kw: 5,
    perfil: 'padrao',
    zona_crac: f === 0 ? 'CRAC-01' : 'CRAC-02',
  })),
)

export const PLANTA: Planta = {
  racks,
  cracs: [
    { crac_id: 'CRAC-01', x_m: 0.6, y_m: -1.5, setpoint_c: 19.5 },
    { crac_id: 'CRAC-02', x_m: 0.6, y_m: 3.9, setpoint_c: 19.5 },
  ],
  largura_m: 1.2,
  profundidade_m: 5.4,
}

/** A fileira A acima de 27 °C (o CRAC-01 falhou); a B normal. */
export const VALORES: ValorRack[] = racks.map((r) => ({
  rack_id: r.rack_id,
  fileira: r.fileira,
  posicao: r.posicao,
  x_m: r.x_m,
  y_m: r.y_m,
  zona_crac: r.zona_crac,
  valor: r.fileira === 'A' ? 29 + r.posicao * 0.4 : 20.5,
  faixa: r.fileira === 'A' ? 'acima' : 'ok',
}))

export const MAPA: MapaTermico = {
  instante: '2026-11-01T03:50:00Z',
  tipo: 'temp_entrada',
  altura: null,
  racks: VALORES,
}

export const RESUMO: Resumo = {
  inicio: SIMULACAO.inicio,
  fim: SIMULACAO.fim,
  fonte: 'agregados_hora',
  racks: 6,
  cracs: 2,
  sensores: 34,
  leituras: 43_718_400,
  leituras_nulas: 240,
  potencia_media_total_kw: 1020,
  racks_acima_da_faixa: 3,
  racks_abaixo_da_faixa: 0,
  por_tipo: {
    temp_entrada: { minimo: 19.1, media: 20.21, maximo: 30.5 },
    potencia_kw: { minimo: 1.8, media: 5.1, maximo: 16.5 },
  },
}

export const FORA: RackForaDaFaixa[] = [
  {
    rack_id: 'A-03',
    fileira: 'A',
    zona_crac: 'CRAC-01',
    minutos_acima: 141,
    minutos_abaixo: 0,
    pico_c: 30.5,
    minimo_c: 19.7,
    primeira_vez: '2026-11-01T02:11:00Z',
    ultima_vez: '2026-11-01T04:32:00Z',
  },
]

export const GABARITO: Incidente[] = [
  {
    incidente_id: 1,
    tipo: 'falha_crac',
    alvo_tipo: 'crac',
    alvo: 'CRAC-01',
    inicio: '2026-11-01T02:00:00Z',
    fim: '2026-11-01T04:00:00Z',
    intensidade: 1,
    descricao: 'CRAC-01 perdeu 100% da refrigeração; a zona aquece',
  },
]

const PLACAR_VAZIO = {
  incidentes: 0,
  invisiveis: 0,
  detectados: 0,
  alertas: 0,
  corretos: 0,
  precisao: null,
  recall: null,
  f1: null,
  atraso_mediano_min: null,
}

/** Um alerta que acertou a falha do CRAC-01 e um falso na saída do B-02. */
export const ANOMALIAS: Anomalias = {
  alertas: [
    {
      alerta_id: 1,
      tipo: 'falha_crac',
      alvo: 'CRAC-01',
      equipamento: 'CRAC-01',
      inicio: '2026-11-01T02:04:00Z',
      fim: '2026-11-01T04:10:00Z',
      evidencia: 'Insuflamento até 9,5 °C acima do normal, com a entrada dos racks da zona subindo junto.',
      medida: 9.5,
      incidentes: [1],
    },
    {
      alerta_id: 2,
      tipo: 'sensor_deriva',
      alvo: 'B-02/saida',
      equipamento: 'B-02',
      inicio: '2026-11-01T10:00:00Z',
      fim: '2026-11-01T12:30:00Z',
      evidencia: 'A saída discorda 1,4 °C do esperado pela entrada e pela carga.',
      medida: 1.4,
      incidentes: [],
    },
  ],
  fonte: 'leituras brutas',
  segundos: 2.31,
  alcance_retorno_m: 1.5,
  avaliacao: {
    total: { ...PLACAR_VAZIO, incidentes: 1, detectados: 1, alertas: 2, corretos: 1, precisao: 0.5, recall: 1, f1: 0.667, atraso_mediano_min: 4 },
    por_tipo: {
      falha_crac: { ...PLACAR_VAZIO, incidentes: 1, detectados: 1, alertas: 1, corretos: 1, precisao: 1, recall: 1, f1: 1, atraso_mediano_min: 4 },
      sensor_deriva: { ...PLACAR_VAZIO, alertas: 1, precisao: 0 },
      sensor_picos: PLACAR_VAZIO,
    },
    perdidos: [],
    invisiveis: [],
  },
}

/** Um fetch falso que responde cada rota da API com os dados acima. */
export function apiFalsa(respostas: Record<string, unknown> = {}, falhar: string[] = []) {
  const tabela: Record<string, unknown> = {
    '/api/simulacoes': [SIMULACAO],
    '/api/demo/planta': PLANTA,
    '/api/demo/resumo': RESUMO,
    '/api/demo/mapa': MAPA,
    '/api/demo/fora-da-faixa': FORA,
    '/api/demo/gabarito': GABARITO,
    '/api/demo/anomalias': ANOMALIAS,
    ...respostas,
  }
  return async (entrada: RequestInfo | URL) => {
    const caminho = new URL(String(entrada)).pathname
    if (falhar.includes(caminho)) {
      return new Response(JSON.stringify({ detail: 'A janela fica fora da simulação' }), { status: 400 })
    }
    if (!(caminho in tabela)) return new Response(JSON.stringify({ detail: 'não encontrado' }), { status: 404 })
    return new Response(JSON.stringify(tabela[caminho]), { status: 200 })
  }
}
