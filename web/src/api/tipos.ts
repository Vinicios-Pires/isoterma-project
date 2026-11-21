// Tipos das respostas, derivados do OpenAPI da API (esquema.ts é gerado por `npm run tipos`).
import type { components } from './esquema'

type Esquemas = components['schemas']

export type Simulacao = Esquemas['Simulacao']
export type Planta = Esquemas['Planta']
export type RackPlanta = Esquemas['RackPlanta']
export type CracPlanta = Esquemas['CracPlanta']
export type Resumo = Esquemas['Resumo']
export type Estatistica = Esquemas['Estatistica']
export type MapaTermico = Esquemas['MapaTermico']
export type ValorRack = Esquemas['ValorRack']
export type RackForaDaFaixa = Esquemas['RackForaDaFaixa']
export type Serie = Esquemas['Serie']
export type PontoSerie = Esquemas['PontoSerie']
export type Incidente = Esquemas['Incidente']

export type TipoMapa = MapaTermico['tipo']
export type Altura = NonNullable<MapaTermico['altura']>
