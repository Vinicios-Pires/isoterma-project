import { ArrowLeft, Map as IconeMapa, ZoomOut } from 'lucide-react'
import { useMemo } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'

import { useAnomalias, useGabarito, usePlanta, useSerie } from '@/api/consultas'
import type { Alerta, Incidente, Planta, Simulacao } from '@/api/tipos'
import { Carregando, Conteudo, Falha } from '@/componentes/Estado'
import { GraficoSerie, type FaixaDestaque } from '@/componentes/GraficoSerie'
import { Badge } from '@/components/ui/badge'
import { Button, buttonVariants } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { useSimulacao } from '@/hooks/useSimulacao'
import { comUnidade, dataHoraCompleta, nomeFuso } from '@/lib/formato'
import { CATEGORIAS } from '@/lib/incidentes'
import type { SerieGrafico } from '@/lib/series'
import { FAIXA_ASHRAE } from '@/lib/termica'

export type TipoEquipamento = 'rack' | 'crac'

function seriesDoRack(rack: string): { temperatura: SerieGrafico[]; potencia: SerieGrafico[] } {
  return {
    temperatura: [
      { sensor: `${rack}/entrada-base`, nome: 'Entrada · base', cor: 'var(--serie-1)' },
      { sensor: `${rack}/entrada-meio`, nome: 'Entrada · meio', cor: 'var(--serie-2)' },
      { sensor: `${rack}/entrada-topo`, nome: 'Entrada · topo', cor: 'var(--serie-3)' },
      { sensor: `${rack}/saida`, nome: 'Saída', cor: 'var(--serie-4)' },
    ],
    potencia: [{ sensor: `${rack}/potencia`, nome: 'Potência', cor: 'var(--serie-1)' }],
  }
}

function seriesDoCrac(crac: string): SerieGrafico[] {
  return [
    { sensor: `${crac}/insuflamento`, nome: 'Insuflamento', cor: 'var(--serie-1)' },
    { sensor: `${crac}/retorno`, nome: 'Retorno', cor: 'var(--serie-2)' },
  ]
}

/** Incidentes do gabarito que tocam o equipamento: ele, os sensores dele ou o CRAC da zona. */
function incidentesDe(incidentes: Incidente[], alvo: string, zona: string | null): FaixaDestaque[] {
  return incidentes
    .filter((i) => i.alvo === alvo || i.alvo.startsWith(`${alvo}/`) || (zona !== null && i.alvo === zona))
    .map((i) => ({ inicio: i.inicio, fim: i.fim, rotulo: CATEGORIAS[i.tipo]?.nome ?? i.tipo }))
}

/** Alertas dos detectores no próprio equipamento ou num sensor dele. */
function alertasDe(alertas: Alerta[], alvo: string): FaixaDestaque[] {
  return alertas
    .filter((a) => a.equipamento === alvo)
    .map((a) => ({
      inicio: a.inicio,
      fim: a.fim,
      rotulo: `alerta: ${CATEGORIAS[a.tipo]?.nome ?? a.tipo}`,
      cor: 'var(--chart-2)',
    }))
}

function Ficha({ tipo, alvo, planta, simulacao }: { tipo: TipoEquipamento; alvo: string; planta: Planta; simulacao: string }) {
  if (tipo === 'crac') {
    const crac = planta.cracs.find((c) => c.crac_id === alvo)
    const zona = planta.racks.filter((r) => r.zona_crac === alvo)
    if (!crac) return <Falha erro={`O CRAC ${alvo} não existe nesta simulação.`} />
    return (
      <div className="space-y-3 text-sm">
        <p>
          Setpoint de insuflamento: <span className="tabular font-mono">{comUnidade(crac.setpoint_c, '°C')}</span>
        </p>
        <div>
          <p className="text-xs text-muted-foreground">Racks da zona ({zona.length})</p>
          <div className="mt-1.5 flex flex-wrap gap-1">
            {zona.map((r) => (
              <Link
                key={r.rack_id}
                to={`/${simulacao}/rack/${r.rack_id}`}
                className="rounded border px-1.5 py-0.5 font-mono text-xs hover:bg-accent"
              >
                {r.rack_id}
              </Link>
            ))}
          </div>
        </div>
      </div>
    )
  }
  const rack = planta.racks.find((r) => r.rack_id === alvo)
  if (!rack) return <Falha erro={`O rack ${alvo} não existe nesta simulação.`} />
  return (
    <dl className="grid grid-cols-2 gap-3 text-sm">
      <div>
        <dt className="text-xs text-muted-foreground">Fileira, posição</dt>
        <dd className="font-mono">
          {rack.fileira}, {rack.posicao}
        </dd>
      </div>
      <div>
        <dt className="text-xs text-muted-foreground">Zona</dt>
        <dd>
          <Link to={`/${simulacao}/crac/${rack.zona_crac}`} className="font-mono text-primary hover:underline">
            {rack.zona_crac}
          </Link>
        </dd>
      </div>
      <div>
        <dt className="text-xs text-muted-foreground">Potência nominal</dt>
        <dd className="tabular font-mono">{comUnidade(rack.potencia_nominal_kw, 'kW', 2)}</dd>
      </div>
      <div>
        <dt className="text-xs text-muted-foreground">Perfil</dt>
        <dd>{rack.perfil === 'denso' ? 'Denso (ex.: GPU)' : 'Padrão'}</dd>
      </div>
    </dl>
  )
}

function DetalheDaSimulacao({ simulacao, tipo }: { simulacao: Simulacao; tipo: TipoEquipamento }) {
  const { alvo = '' } = useParams()
  const [parametros, setParametros] = useSearchParams()
  const inicio = parametros.get('inicio')
  const fim = parametros.get('fim')
  const mostrarGabarito = parametros.get('gabarito') === '1'
  const mostrarAlertas = parametros.get('alertas') === '1'
  const janela = useMemo(() => ({ inicio, fim }), [inicio, fim])

  const planta = usePlanta(simulacao.nome)
  const serie = useSerie(simulacao.nome, alvo, janela)
  const gabarito = useGabarito(simulacao.nome)
  const anomalias = useAnomalias(simulacao.nome, mostrarAlertas)
  const fuso = simulacao.fuso

  const zona = tipo === 'rack' ? (planta.data?.racks.find((r) => r.rack_id === alvo)?.zona_crac ?? null) : null
  const faixas = [
    ...(mostrarGabarito && gabarito.data ? incidentesDe(gabarito.data, alvo, zona) : []),
    ...(mostrarAlertas && anomalias.data ? alertasDe(anomalias.data.alertas, alvo) : []),
  ]

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

  const t0 = new Date(inicio ?? simulacao.inicio).getTime()
  const t1 = new Date(fim ?? simulacao.fim).getTime()
  const afastar = () => {
    const centro = (t0 + t1) / 2
    const metade = (t1 - t0) * 2
    const novoInicio = Math.max(new Date(simulacao.inicio).getTime(), centro - metade)
    const novoFim = Math.min(new Date(simulacao.fim).getTime(), centro + metade)
    const inteiro = novoInicio <= new Date(simulacao.inicio).getTime() && novoFim >= new Date(simulacao.fim).getTime()
    alterar(
      inteiro
        ? { inicio: null, fim: null }
        : { inicio: new Date(novoInicio).toISOString(), fim: new Date(novoFim).toISOString() },
    )
  }
  const instanteNoMapa = new Date((t0 + t1) / 2).toISOString()

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <Link
            to={`/${simulacao.nome}/mapa`}
            className="mb-1 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="size-3" /> Mapa térmico
          </Link>
          <h1 className="flex items-center gap-2 text-2xl font-semibold">
            <span className="font-mono">{alvo}</span>
            <Badge variant="outline">{tipo === 'rack' ? 'rack' : 'CRAC'}</Badge>
          </h1>
          <p className="tabular mt-1 font-mono text-sm text-muted-foreground">
            {dataHoraCompleta(new Date(t0).toISOString(), fuso)} a {dataHoraCompleta(new Date(t1).toISOString(), fuso)}{' '}
            ({nomeFuso(new Date(t0).toISOString(), fuso)})
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-sm">
            <Switch
              checked={mostrarGabarito}
              onCheckedChange={(ligado: boolean) => alterar({ gabarito: ligado ? '1' : null })}
              aria-label="Mostrar incidentes da simulação"
            />
            Incidentes da simulação
          </label>
          <label className="flex items-center gap-2 text-sm">
            <Switch
              checked={mostrarAlertas}
              onCheckedChange={(ligado: boolean) => alterar({ alertas: ligado ? '1' : null })}
              aria-label="Mostrar alertas dos detectores"
            />
            Alertas {mostrarAlertas && anomalias.isPending && <span className="text-xs text-muted-foreground">(calculando…)</span>}
          </label>
          <Button variant="outline" size="sm" onClick={afastar} disabled={!inicio && !fim}>
            <ZoomOut className="size-4" /> Afastar
          </Button>
          <Button variant="outline" size="sm" onClick={() => alterar({ inicio: null, fim: null })} disabled={!inicio && !fim}>
            Período inteiro
          </Button>
          <Link
            to={`/${simulacao.nome}/mapa?t=${encodeURIComponent(instanteNoMapa)}${tipo === 'rack' ? `&rack=${alvo}` : ''}`}
            className={buttonVariants({ variant: 'outline', size: 'sm' })}
          >
            <IconeMapa className="size-4" /> No mapa
          </Link>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_17rem]">
        <Card className="min-w-0">
          <CardContent className="space-y-6">
            <Conteudo consulta={serie} esqueleto={<Carregando className="h-72" />}>
              {(s) => {
                const comum = {
                  pontos: s.pontos,
                  fuso,
                  faixas,
                  sincronizar: 'detalhe',
                  aoAmpliar: (de: string, ate: string) => alterar({ inicio: de, fim: ate }),
                }
                if (tipo === 'crac') {
                  const setpoint = planta.data?.cracs.find((c) => c.crac_id === alvo)?.setpoint_c
                  return (
                    <GraficoSerie
                      titulo="Temperatura do ar"
                      series={seriesDoCrac(alvo)}
                      unidade="°C"
                      referencias={setpoint ? [{ valor: setpoint, rotulo: `setpoint ${setpoint} °C` }] : []}
                      altura={300}
                      {...comum}
                    />
                  )
                }
                const series = seriesDoRack(alvo)
                return (
                  <>
                    <GraficoSerie
                      titulo="Temperatura"
                      series={series.temperatura}
                      unidade="°C"
                      referencias={[
                        { valor: FAIXA_ASHRAE.maximo, rotulo: '27 °C' },
                        { valor: FAIXA_ASHRAE.minimo, rotulo: '18 °C' },
                      ]}
                      {...comum}
                    />
                    <GraficoSerie titulo="Potência" series={series.potencia} unidade="kW" altura={160} {...comum} />
                  </>
                )
              }}
            </Conteudo>
            <p className="text-xs text-muted-foreground">
              Cada ponto é a média do intervalo; o tooltip mostra também o mínimo e o máximo. Arraste no gráfico para
              ampliar um trecho.
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{tipo === 'rack' ? 'Rack' : 'CRAC'}</CardTitle>
          </CardHeader>
          <CardContent>
            <Conteudo consulta={planta}>
              {(p) => <Ficha tipo={tipo} alvo={alvo} planta={p} simulacao={simulacao.nome} />}
            </Conteudo>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

export function Detalhe({ tipo }: { tipo: TipoEquipamento }) {
  const { simulacao, carregando, erro } = useSimulacao()
  if (erro) return <Falha erro={erro} />
  if (carregando || !simulacao) return <Carregando />
  return <DetalheDaSimulacao simulacao={simulacao} tipo={tipo} />
}
