import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'

import { useMapa, usePlanta } from '@/api/consultas'
import type { Altura, Simulacao, TipoMapa, ValorRack } from '@/api/tipos'
import { ControleTempo } from '@/componentes/ControleTempo'
import { Carregando, Conteudo, Falha } from '@/componentes/Estado'
import { LegendaTermica, PlantaTermica } from '@/componentes/PlantaTermica'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useSimulacao } from '@/hooks/useSimulacao'
import { comUnidade, dataHora } from '@/lib/formato'
import { janelaEmVolta } from '@/lib/janela'
import { ESCALAS, NOMES_TIPO } from '@/lib/termica'

const TIPOS: TipoMapa[] = ['temp_entrada', 'temp_saida', 'potencia_kw']
const ALTURAS: { valor: Altura | 'mais-quente'; nome: string }[] = [
  { valor: 'mais-quente', nome: 'Altura mais quente' },
  { valor: 'topo', nome: 'Topo' },
  { valor: 'meio', nome: 'Meio' },
  { valor: 'base', nome: 'Base' },
]
const INTERVALO_DO_PLAY_MS = 450

const racksTexto = (n: number) => `${n} ${n === 1 ? 'rack' : 'racks'}`

function ehTipo(valor: string | null): valor is TipoMapa {
  return TIPOS.includes(valor as TipoMapa)
}

function Resumo({ racks, tipo }: { racks: ValorRack[]; tipo: TipoMapa }) {
  const valores = racks.map((r) => r.valor).filter((v): v is number => v !== null)
  const acima = racks.filter((r) => r.faixa === 'acima')
  const abaixo = racks.filter((r) => r.faixa === 'abaixo')
  const unidade = ESCALAS[tipo].unidade
  const quentes = [...acima].sort((a, b) => (b.valor ?? 0) - (a.valor ?? 0)).slice(0, 5)
  return (
    <div className="space-y-4 text-sm">
      <dl className="grid grid-cols-2 gap-3">
        <div>
          <dt className="text-xs text-muted-foreground">Mínimo</dt>
          <dd className="tabular font-mono">{comUnidade(valores.length ? Math.min(...valores) : null, unidade)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Máximo</dt>
          <dd className="tabular font-mono">{comUnidade(valores.length ? Math.max(...valores) : null, unidade)}</dd>
        </div>
        {tipo === 'temp_entrada' && (
          <>
            <div>
              <dt className="text-xs text-muted-foreground">Acima de 27 °C</dt>
              <dd className={`tabular font-mono ${acima.length ? 'text-quente' : ''}`}>{racksTexto(acima.length)}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Abaixo de 18 °C</dt>
              <dd className={`tabular font-mono ${abaixo.length ? 'text-frio' : ''}`}>{racksTexto(abaixo.length)}</dd>
            </div>
          </>
        )}
      </dl>
      {quentes.length > 0 && (
        <div>
          <p className="text-xs text-muted-foreground">Mais quentes</p>
          <ul className="mt-1 space-y-0.5">
            {quentes.map((r) => (
              <li key={r.rack_id} className="tabular flex justify-between font-mono">
                <span>{r.rack_id}</span>
                <span>{comUnidade(r.valor, unidade)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function DetalheRack({
  rack,
  tipo,
  simulacao,
  instante,
}: {
  rack: ValorRack | undefined
  tipo: TipoMapa
  simulacao: Simulacao
  instante: string
}) {
  if (!rack) {
    return <p className="text-sm text-muted-foreground">Clique num rack para ver os detalhes.</p>
  }
  return (
    <dl className="grid grid-cols-2 gap-3 text-sm">
      <div>
        <dt className="text-xs text-muted-foreground">Rack</dt>
        <dd className="font-mono">{rack.rack_id}</dd>
      </div>
      <div>
        <dt className="text-xs text-muted-foreground">{NOMES_TIPO[tipo]}</dt>
        <dd className="tabular font-mono">{comUnidade(rack.valor, ESCALAS[tipo].unidade)}</dd>
      </div>
      <div>
        <dt className="text-xs text-muted-foreground">Fileira, posição</dt>
        <dd className="font-mono">
          {rack.fileira}, {rack.posicao}
        </dd>
      </div>
      <div>
        <dt className="text-xs text-muted-foreground">Zona</dt>
        <dd className="font-mono">{rack.zona_crac}</dd>
      </div>
      <Link
        to={`/${simulacao.nome}/rack/${rack.rack_id}?${janelaEmVolta(instante, simulacao)}`}
        className="col-span-2 text-sm text-primary underline-offset-4 hover:underline"
      >
        Ver as séries de {rack.rack_id} →
      </Link>
    </dl>
  )
}

function MapaDaSimulacao({ simulacao }: { simulacao: Simulacao }) {
  const [parametros, setParametros] = useSearchParams()
  const [tocando, setTocando] = useState(false)
  const navegar = useNavigate()
  const tipo: TipoMapa = ehTipo(parametros.get('tipo')) ? (parametros.get('tipo') as TipoMapa) : 'temp_entrada'
  const altura = (parametros.get('altura') as Altura | null) ?? null
  const instante = parametros.get('t') ?? simulacao.fim
  const rackSelecionado = parametros.get('rack')
  // Passos de 5 minutos (ou o intervalo das leituras, se for maior).
  const passoMin = Math.max(5, Math.round(simulacao.intervalo_s / 60))

  const planta = usePlanta(simulacao.nome)
  const mapa = useMapa(simulacao.nome, instante, tipo, tipo === 'temp_entrada' ? altura : null)

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

  // O play avança um passo por vez, e só quando o mapa anterior já chegou.
  useEffect(() => {
    if (!tocando || mapa.isFetching) return
    const proximo = new Date(new Date(instante).getTime() + passoMin * 60_000)
    if (proximo > new Date(simulacao.fim)) {
      setTocando(false)
      return
    }
    const espera = setTimeout(() => alterar({ t: proximo.toISOString() }), INTERVALO_DO_PLAY_MS)
    return () => clearTimeout(espera)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tocando, mapa.isFetching, instante])

  const racks = mapa.data?.racks
  const selecionado = useMemo(() => racks?.find((r) => r.rack_id === rackSelecionado), [racks, rackSelecionado])

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Mapa térmico</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Média dos 5 minutos anteriores ao instante, em cada rack · {dataHora(instante, simulacao.fuso)}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <ToggleGroup
            variant="outline"
            value={[tipo]}
            onValueChange={(valores: unknown[]) => {
              const novo = valores.find((v) => typeof v === 'string' && ehTipo(v)) as TipoMapa | undefined
              if (novo) alterar({ tipo: novo, altura: novo === 'temp_entrada' ? altura : null })
            }}
            aria-label="O que medir"
          >
            {TIPOS.map((t) => (
              <ToggleGroupItem key={t} value={t}>
                {NOMES_TIPO[t]}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
          {tipo === 'temp_entrada' && (
            <Select
              items={ALTURAS.map((a) => ({ value: a.valor, label: a.nome }))}
              value={altura ?? 'mais-quente'}
              onValueChange={(v) => alterar({ altura: v === 'mais-quente' || !v ? null : String(v) })}
            >
              <SelectTrigger className="w-44" aria-label="Altura do sensor">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ALTURAS.map((a) => (
                  <SelectItem key={a.valor} value={a.valor}>
                    {a.nome}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_17rem]">
        <Card className="min-w-0">
          <CardContent className="space-y-3">
            {mapa.error ? (
              <Falha erro={mapa.error} />
            ) : planta.data && racks ? (
              <PlantaTermica
                planta={planta.data}
                racks={racks}
                tipo={tipo}
                selecionado={rackSelecionado}
                aoSelecionar={(rack) => alterar({ rack: rack === rackSelecionado ? null : rack })}
                aoSelecionarCrac={(crac) => navegar(`/${simulacao.nome}/crac/${crac}?${janelaEmVolta(instante, simulacao)}`)}
              />
            ) : (
              <Carregando className="aspect-[2/3] h-auto max-h-[70vh]" />
            )}
            <LegendaTermica tipo={tipo} />
          </CardContent>
        </Card>
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Neste instante</CardTitle>
            </CardHeader>
            <CardContent>
              <Conteudo consulta={mapa}>{(m) => <Resumo racks={m.racks} tipo={tipo} />}</Conteudo>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Rack</CardTitle>
              <CardDescription>Clique num CRAC para ver as séries dele.</CardDescription>
            </CardHeader>
            <CardContent>
              <DetalheRack rack={selecionado} tipo={tipo} simulacao={simulacao} instante={instante} />
            </CardContent>
          </Card>
        </div>
      </div>

      <ControleTempo
        inicio={simulacao.inicio}
        fim={simulacao.fim}
        valor={instante}
        passoMin={passoMin}
        fuso={simulacao.fuso}
        tocando={tocando}
        carregando={mapa.isFetching}
        aoMudar={(t) => alterar({ t })}
        aoTocar={setTocando}
      />
    </div>
  )
}

export function Mapa() {
  const { simulacao, carregando, erro } = useSimulacao()
  if (erro) return <Falha erro={erro} />
  if (carregando || !simulacao) return <Carregando />
  return <MapaDaSimulacao simulacao={simulacao} />
}
