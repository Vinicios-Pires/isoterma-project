import { useNavigate } from 'react-router'

import { useForaDaFaixa, useGabarito, useResumo } from '@/api/consultas'
import type { Incidente, Simulacao } from '@/api/tipos'
import { Carregando, Conteudo, Falha } from '@/componentes/Estado'
import { Indicador } from '@/componentes/Indicador'
import { LinhaDoTempo } from '@/componentes/LinhaDoTempo'
import { TabelaForaDaFaixa } from '@/componentes/TabelaForaDaFaixa'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useSimulacao } from '@/hooks/useSimulacao'
import { comUnidade, dataHoraCompleta, nomeFuso, numero } from '@/lib/formato'

const NOMES_SENSOR: Record<string, string> = {
  temp_entrada: 'Entrada dos racks',
  temp_saida: 'Saída dos racks',
  potencia_kw: 'Potência por rack',
  temp_insuflamento: 'Insuflamento dos CRACs',
  temp_retorno: 'Retorno dos CRACs',
}
const UNIDADE_SENSOR = (tipo: string) => (tipo === 'potencia_kw' ? 'kW' : '°C')

/** Um momento representativo de um incidente para abrir no mapa: o efeito leva um tempo. */
function momentoDoIncidente(incidente: Incidente): string {
  const inicio = new Date(incidente.inicio).getTime()
  const fim = new Date(incidente.fim).getTime()
  return new Date(Math.min(fim, inicio + Math.min(60, (fim - inicio) / 60_000 / 2) * 60_000)).toISOString()
}

function Cabecalho({ simulacao }: { simulacao: Simulacao }) {
  const fuso = simulacao.fuso
  return (
    <div className="mb-6">
      <h1 className="text-2xl font-semibold">Painel</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        <span className="tabular font-mono">
          {dataHoraCompleta(simulacao.inicio, fuso)} a {dataHoraCompleta(simulacao.fim, fuso)}
        </span>{' '}
        ({nomeFuso(simulacao.inicio, fuso)}) · {numero(simulacao.racks)} racks, {numero(simulacao.cracs)} CRACs,{' '}
        {numero(simulacao.sensores)} sensores
      </p>
    </div>
  )
}

function Conteudos({ simulacao }: { simulacao: Simulacao }) {
  const navegar = useNavigate()
  const resumo = useResumo(simulacao.nome)
  const fora = useForaDaFaixa(simulacao.nome)
  const gabarito = useGabarito(simulacao.nome)
  const fuso = simulacao.fuso

  return (
    <div className="space-y-6">
      <Conteudo consulta={resumo} esqueleto={<Carregando className="h-24" />}>
        {(r) => {
          const entrada = r.por_tipo.temp_entrada
          return (
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
              <Indicador rotulo="Leituras" valor={numero(r.leituras)} detalhe={`${numero(r.leituras_nulas)} ausentes`} />
              <Indicador
                rotulo="Potência média"
                valor={comUnidade(r.potencia_media_total_kw, 'kW')}
                detalhe="soma de todos os racks"
              />
              <Indicador
                rotulo="Entrada média"
                valor={comUnidade(entrada?.media, '°C')}
                detalhe={`de ${comUnidade(entrada?.minimo, '°C')} a ${comUnidade(entrada?.maximo, '°C')}`}
              />
              <Indicador
                rotulo="Acima de 27 °C"
                valor={numero(r.racks_acima_da_faixa)}
                detalhe="racks em algum momento"
                tom={r.racks_acima_da_faixa ? 'quente' : 'neutro'}
              />
              <Indicador
                rotulo="Abaixo de 18 °C"
                valor={numero(r.racks_abaixo_da_faixa)}
                detalhe="racks em algum momento"
                tom={r.racks_abaixo_da_faixa ? 'frio' : 'neutro'}
              />
            </div>
          )
        }}
      </Conteudo>

      <div className="grid gap-6 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle>Fora da faixa ASHRAE</CardTitle>
            <CardDescription>
              Racks com a entrada fora de 18 a 27 °C, os mais afetados primeiro. O horário abre o mapa naquele
              momento.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Conteudo consulta={fora}>
              {(racks) => <TabelaForaDaFaixa racks={racks} simulacao={simulacao.nome} fuso={fuso} />}
            </Conteudo>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Por tipo de sensor</CardTitle>
            <CardDescription>Mínimo, média e máximo no período inteiro.</CardDescription>
          </CardHeader>
          <CardContent>
            <Conteudo consulta={resumo}>
              {(r) => (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Sensor</TableHead>
                      <TableHead className="text-right">Mín.</TableHead>
                      <TableHead className="text-right">Média</TableHead>
                      <TableHead className="text-right">Máx.</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {Object.entries(r.por_tipo).map(([tipo, e]) => (
                      <TableRow key={tipo}>
                        <TableCell>{NOMES_SENSOR[tipo] ?? tipo}</TableCell>
                        <TableCell className="tabular text-right">{comUnidade(e.minimo, UNIDADE_SENSOR(tipo))}</TableCell>
                        <TableCell className="tabular text-right">{comUnidade(e.media, UNIDADE_SENSOR(tipo))}</TableCell>
                        <TableCell className="tabular text-right">{comUnidade(e.maximo, UNIDADE_SENSOR(tipo))}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </Conteudo>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            Incidentes da simulação <Badge variant="outline">gabarito</Badge>
          </CardTitle>
          <CardDescription>
            O que o simulador injetou de propósito. Num data center real isso não existiria: serve para comparar o
            que aconteceu com o que o Isoterma mostra. Clique num incidente para vê-lo no mapa.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Conteudo consulta={gabarito}>
            {(incidentes) => (
              <LinhaDoTempo
                incidentes={incidentes}
                inicio={simulacao.inicio}
                fim={simulacao.fim}
                fuso={fuso}
                aoEscolher={(i) => {
                  const rack = i.alvo_tipo === 'rack' ? i.alvo : i.alvo_tipo === 'sensor' ? i.alvo.split('/')[0] : ''
                  const parametros = new URLSearchParams({ t: momentoDoIncidente(i) })
                  if (rack && !rack.startsWith('CRAC')) parametros.set('rack', rack)
                  navegar(`/${simulacao.nome}/mapa?${parametros}`)
                }}
              />
            )}
          </Conteudo>
        </CardContent>
      </Card>
    </div>
  )
}

export function Painel() {
  const { simulacao, carregando, erro } = useSimulacao()
  if (erro) return <Falha erro={erro} />
  if (carregando || !simulacao) return <Carregando />
  return (
    <>
      <Cabecalho simulacao={simulacao} />
      <Conteudos simulacao={simulacao} />
    </>
  )
}
