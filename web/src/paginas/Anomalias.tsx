import { ChartLine, Map as IconeMapa } from 'lucide-react'
import { useMemo } from 'react'
import { Link, useSearchParams } from 'react-router'

import { useAnomalias, useGabarito, useMapa, usePlanta } from '@/api/consultas'
import type { Alerta, Anomalias as DadosAnomalias, Incidente, Placar, Simulacao } from '@/api/tipos'
import { Carregando, Conteudo, Falha } from '@/componentes/Estado'
import { Indicador } from '@/componentes/Indicador'
import { LegendaAlertas, LinhaDoTempoAlertas } from '@/componentes/LinhaDoTempoAlertas'
import { PlantaTermica } from '@/componentes/PlantaTermica'
import { Badge } from '@/components/ui/badge'
import { buttonVariants } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useSimulacao } from '@/hooks/useSimulacao'
import { linkDoDetalhe, linkDoMapa, minutos, momento, porcentagem, situacao, type Situacao } from '@/lib/anomalias'
import { dataHora, duracao, numero } from '@/lib/formato'
import { CATEGORIAS } from '@/lib/incidentes'
import { cn } from '@/lib/utils'

const RELATORIO = 'https://github.com/Vinicios-Pires/isoterma-project/blob/main/docs/DETECCAO.md'
const METODO = 'https://github.com/Vinicios-Pires/isoterma-project/blob/main/docs/ANOMALIAS.md'

type Filtro = 'todos' | 'confirmado' | 'falso'

function atraso(minutosAte: number | null | undefined): string {
  if (minutosAte === null || minutosAte === undefined) return '—'
  return minutosAte < 1 ? '< 1 min' : duracao(minutosAte)
}

const nomeTipo = (tipo: string) => CATEGORIAS[tipo]?.nome ?? tipo
const ehDefeitoDeSensor = (tipo: string) => tipo.startsWith('sensor_')

function SeloSituacao({ alerta }: { alerta: Alerta }) {
  const s = situacao(alerta)
  if (s === 'sem-gabarito') return null
  return s === 'confirmado' ? (
    <Badge variant="secondary">confirmado</Badge>
  ) : (
    <Badge variant="destructive">falso</Badge>
  )
}

function Placares({ dados }: { dados: DadosAnomalias }) {
  const a = dados.avaliacao
  if (!a) {
    const equipamentos = new Set(dados.alertas.map((x) => x.equipamento)).size
    const sensores = dados.alertas.filter((x) => ehDefeitoDeSensor(x.tipo)).length
    return (
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Indicador rotulo="Alertas" valor={numero(dados.alertas.length)} />
        <Indicador rotulo="Equipamentos" valor={numero(equipamentos)} detalhe="com algum alerta" />
        <Indicador rotulo="Eventos físicos" valor={numero(dados.alertas.length - sensores)} />
        <Indicador rotulo="Defeitos de sensor" valor={numero(sensores)} />
      </div>
    )
  }
  const t = a.total
  const falsos = t.alertas - t.corretos
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <Indicador
        rotulo="Incidentes detectados"
        valor={`${numero(t.detectados)} de ${numero(t.incidentes)}`}
        detalhe={`recall ${porcentagem(t.recall)}${t.invisiveis ? ` · ${t.invisiveis} sem efeito nos dados` : ''}`}
      />
      <Indicador
        rotulo="Alertas corretos"
        valor={`${numero(t.corretos)} de ${numero(t.alertas)}`}
        detalhe={`precisão ${porcentagem(t.precisao)}`}
      />
      <Indicador
        rotulo="Alertas falsos"
        valor={numero(falsos)}
        detalhe={falsos ? 'sem incidente correspondente' : 'nenhum'}
        tom={falsos ? 'quente' : 'neutro'}
      />
      <Indicador
        rotulo="Atraso mediano"
        valor={atraso(t.atraso_mediano_min)}
        detalhe="do início do incidente ao alerta"
      />
    </div>
  )
}

function TabelaPorTipo({ porTipo }: { porTipo: Record<string, Placar> }) {
  const linhas = Object.entries(porTipo).filter(([, p]) => p.incidentes || p.alertas || p.invisiveis)
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Tipo</TableHead>
          <TableHead className="text-right">Detectados</TableHead>
          <TableHead className="text-right">Alertas corretos</TableHead>
          <TableHead className="text-right">Precisão</TableHead>
          <TableHead className="text-right">Recall</TableHead>
          <TableHead className="text-right">Atraso mediano</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {linhas.map(([tipo, p]) => (
          <TableRow key={tipo}>
            <TableCell>{nomeTipo(tipo)}</TableCell>
            <TableCell className="tabular text-right">
              {p.detectados} de {p.incidentes}
            </TableCell>
            <TableCell className="tabular text-right">
              {p.corretos} de {p.alertas}
            </TableCell>
            <TableCell className="tabular text-right">{porcentagem(p.precisao)}</TableCell>
            <TableCell className="tabular text-right">{porcentagem(p.recall)}</TableCell>
            <TableCell className="tabular text-right">
              {atraso(p.atraso_mediano_min)}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

function ListaDeAlertas({
  alertas,
  fuso,
  selecionado,
  aoEscolher,
}: {
  alertas: Alerta[]
  fuso: string
  selecionado: number | null
  aoEscolher: (alerta: Alerta) => void
}) {
  if (alertas.length === 0) return <p className="text-sm text-muted-foreground">Nenhum alerta com esse filtro.</p>
  return (
    <div className="max-h-[28rem] overflow-y-auto">
      <Table>
        <TableHeader className="sticky top-0 bg-card">
          <TableRow>
            <TableHead>Início</TableHead>
            <TableHead>Tipo</TableHead>
            <TableHead>Alvo</TableHead>
            <TableHead className="text-right">Duração</TableHead>
            <TableHead className="text-right">Situação</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {alertas.map((a) => (
            <TableRow
              key={a.alerta_id}
              aria-selected={a.alerta_id === selecionado}
              className={cn('cursor-pointer', a.alerta_id === selecionado && 'bg-accent')}
              onClick={() => aoEscolher(a)}
            >
              <TableCell className="tabular font-mono">
                <button type="button" className="text-left" onClick={() => aoEscolher(a)}>
                  {dataHora(a.inicio, fuso)}
                </button>
              </TableCell>
              <TableCell>{nomeTipo(a.tipo)}</TableCell>
              <TableCell className="font-mono">{a.alvo}</TableCell>
              <TableCell className="tabular text-right">{duracao(minutos(a))}</TableCell>
              <TableCell className="text-right">
                <SeloSituacao alerta={a} />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

function DetalheDoAlerta({
  alerta,
  simulacao,
  incidentes,
}: {
  alerta: Alerta
  simulacao: Simulacao
  incidentes: Incidente[]
}) {
  const fuso = simulacao.fuso
  const instante = momento(alerta)
  const planta = usePlanta(simulacao.nome)
  const mapa = useMapa(simulacao.nome, instante, 'temp_entrada', null)
  const acertos = incidentes.filter((i) => alerta.incidentes?.includes(i.incidente_id))
  const s: Situacao = situacao(alerta)

  return (
    <div className="space-y-4">
      <div>
        <p className="flex flex-wrap items-center gap-2 font-medium">
          {nomeTipo(alerta.tipo)} <span className="font-mono">{alerta.alvo}</span> <SeloSituacao alerta={alerta} />
        </p>
        <p className="tabular mt-0.5 font-mono text-xs text-muted-foreground">
          {dataHora(alerta.inicio, fuso)} a {dataHora(alerta.fim, fuso)} · {duracao(minutos(alerta))}
        </p>
      </div>
      <blockquote className="border-l-2 pl-3 text-sm">{alerta.evidencia}</blockquote>
      {s === 'confirmado' &&
        acertos.map((i) => (
          <p key={i.incidente_id} className="text-xs text-muted-foreground">
            No gabarito: {i.descricao}.
          </p>
        ))}
      {s === 'falso' && (
        <p className="text-xs text-muted-foreground">
          Nenhum incidente do gabarito com esse tipo e alvo nesse período.
        </p>
      )}
      <div>
        <p className="mb-1.5 text-xs text-muted-foreground">
          Entrada dos racks em <span className="tabular font-mono">{dataHora(instante, fuso)}</span>
        </p>
        {planta.data && mapa.data ? (
          <PlantaTermica
            planta={planta.data}
            racks={mapa.data.racks}
            tipo="temp_entrada"
            selecionado={alerta.equipamento}
          />
        ) : planta.error || mapa.error ? (
          <Falha erro={planta.error ?? mapa.error} />
        ) : (
          <Carregando className="h-48" />
        )}
      </div>
      <div className="flex flex-wrap gap-2">
        <Link to={linkDoDetalhe(alerta, simulacao)} className={buttonVariants({ variant: 'outline', size: 'sm' })}>
          <ChartLine className="size-4" /> Série de {alerta.equipamento}
        </Link>
        <Link to={linkDoMapa(alerta, simulacao.nome)} className={buttonVariants({ variant: 'outline', size: 'sm' })}>
          <IconeMapa className="size-4" /> No mapa
        </Link>
      </div>
    </div>
  )
}

function ConteudoDaPagina({ simulacao, dados }: { simulacao: Simulacao; dados: DadosAnomalias }) {
  const [parametros, setParametros] = useSearchParams()
  const comGabarito = dados.avaliacao !== null && dados.avaliacao !== undefined
  const gabarito = useGabarito(simulacao.nome, comGabarito)
  const incidentes = gabarito.data ?? []
  const fuso = simulacao.fuso

  const tipo = parametros.get('tipo') ?? 'todos'
  const filtro = (parametros.get('ver') as Filtro | null) ?? 'todos'
  const filtrados = useMemo(
    () =>
      dados.alertas.filter(
        (a) => (tipo === 'todos' || a.tipo === tipo) && (filtro === 'todos' || situacao(a) === filtro),
      ),
    [dados.alertas, tipo, filtro],
  )
  const idSelecionado = Number(parametros.get('alerta')) || null
  const selecionado =
    dados.alertas.find((a) => a.alerta_id === idSelecionado) ??
    filtrados[0] ??
    null

  const alterar = (mudancas: Record<string, string | null>) =>
    setParametros(
      (atuais) => {
        const novos = new URLSearchParams(atuais)
        for (const [chave, valor] of Object.entries(mudancas)) {
          if (valor === null) novos.delete(chave)
          else novos.set(chave, valor)
        }
        return novos
      },
      { replace: true },
    )
  const escolher = (a: Alerta) => alterar({ alerta: String(a.alerta_id) })
  const tiposPresentes = Object.keys(CATEGORIAS).filter((t) => dados.alertas.some((a) => a.tipo === t))

  return (
    <div className="space-y-6">
      <Placares dados={dados} />

      <Card>
        <CardHeader>
          <CardTitle>No tempo</CardTitle>
          <CardDescription>
            {comGabarito
              ? 'Em cada tipo, o que o simulador injetou (em cima) e o que os detectores viram sem olhar o gabarito (embaixo).'
              : 'Os alertas ao longo do período, um tipo por linha.'}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <LinhaDoTempoAlertas
            alertas={dados.alertas}
            incidentes={incidentes}
            perdidos={dados.avaliacao?.perdidos}
            inicio={simulacao.inicio}
            fim={simulacao.fim}
            fuso={fuso}
            selecionado={selecionado?.alerta_id}
            aoEscolher={escolher}
          />
          <LegendaAlertas comGabarito={comGabarito} />
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-5">
        <Card className="min-w-0 lg:col-span-3">
          <CardHeader>
            <CardTitle>Alertas</CardTitle>
            <CardDescription>
              {numero(filtrados.length)} de {numero(dados.alertas.length)} · cada um explica o que foi visto.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <Select
                items={[
                  { value: 'todos', label: 'Todos os tipos' },
                  ...tiposPresentes.map((t) => ({ value: t, label: nomeTipo(t) })),
                ]}
                value={tipo}
                onValueChange={(v) => alterar({ tipo: !v || v === 'todos' ? null : String(v), alerta: null })}
              >
                <SelectTrigger className="w-52" aria-label="Tipo de alerta">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="todos">Todos os tipos</SelectItem>
                  {tiposPresentes.map((t) => (
                    <SelectItem key={t} value={t}>
                      {nomeTipo(t)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {comGabarito && (
                <ToggleGroup
                  variant="outline"
                  value={[filtro]}
                  aria-label="Situação dos alertas"
                  onValueChange={(valores: unknown[]) => {
                    const novo = valores.find((v) => typeof v === 'string') as Filtro | undefined
                    if (novo) alterar({ ver: novo === 'todos' ? null : novo, alerta: null })
                  }}
                >
                  <ToggleGroupItem value="todos">Todos</ToggleGroupItem>
                  <ToggleGroupItem value="confirmado">Confirmados</ToggleGroupItem>
                  <ToggleGroupItem value="falso">Falsos</ToggleGroupItem>
                </ToggleGroup>
              )}
            </div>
            <ListaDeAlertas
              alertas={filtrados}
              fuso={fuso}
              selecionado={selecionado?.alerta_id ?? null}
              aoEscolher={escolher}
            />
          </CardContent>
        </Card>

        <Card className="min-w-0 lg:col-span-2">
          <CardHeader>
            <CardTitle>Alerta</CardTitle>
          </CardHeader>
          <CardContent>
            {selecionado ? (
              <DetalheDoAlerta alerta={selecionado} simulacao={simulacao} incidentes={incidentes} />
            ) : (
              <p className="text-sm text-muted-foreground">Escolha um alerta na lista ou na linha do tempo.</p>
            )}
          </CardContent>
        </Card>
      </div>

      {dados.avaliacao && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              Por tipo <Badge variant="outline">gabarito</Badge>
            </CardTitle>
            <CardDescription>
              Só nesta simulação. Um alerta conta como correto quando tem o tipo e o alvo de um incidente e o
              período encosta no dele (30 min de folga). O placar em simulações nunca vistas pelos detectores
              está no{' '}
              <a href={RELATORIO} target="_blank" rel="noreferrer" className="text-primary hover:underline">
                relatório de detecção
              </a>
              .
            </CardDescription>
          </CardHeader>
          <CardContent>
            <TabelaPorTipo porTipo={dados.avaliacao.por_tipo} />
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function Cabecalho({ dados }: { dados?: DadosAnomalias }) {
  return (
    <div className="mb-6">
      <h1 className="text-2xl font-semibold">Anomalias</h1>
      <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
        Regras explicáveis que separam evento físico de defeito de sensor pela coerência entre sensores vizinhos.
        Elas não leem o gabarito.{' '}
        {dados && (
          <>
            Rodaram em <span className="tabular">{numero(dados.segundos, 1)} s</span> sobre {dados.fonte}.{' '}
          </>
        )}
        <a href={METODO} target="_blank" rel="noreferrer" className="text-primary hover:underline">
          Como funcionam
        </a>
      </p>
    </div>
  )
}

function PaginaDaSimulacao({ simulacao }: { simulacao: Simulacao }) {
  const anomalias = useAnomalias(simulacao.nome)
  return (
    <>
      <Cabecalho dados={anomalias.data} />
      <Conteudo
        consulta={anomalias}
        esqueleto={
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Rodando os detectores sobre a simulação inteira. Na primeira visita isso leva alguns segundos.
            </p>
            <Carregando className="h-24" />
            <Carregando className="h-64" />
          </div>
        }
      >
        {(dados) => <ConteudoDaPagina simulacao={simulacao} dados={dados} />}
      </Conteudo>
    </>
  )
}

export function Anomalias() {
  const { simulacao, carregando, erro } = useSimulacao()
  if (erro) return <Falha erro={erro} />
  if (carregando || !simulacao) return <Carregando />
  return <PaginaDaSimulacao simulacao={simulacao} />
}
