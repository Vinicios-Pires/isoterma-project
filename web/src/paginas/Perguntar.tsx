import { ArrowUp, ChevronRight, Loader2, Square } from 'lucide-react'
import { useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import { ErroApi, perguntar } from '@/api/cliente'
import { useSaude } from '@/api/consultas'
import type { EventoPasso, EventoResposta, Simulacao } from '@/api/tipos'
import { Carregando, Falha } from '@/componentes/Estado'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { useSimulacao } from '@/hooks/useSimulacao'
import { numero } from '@/lib/formato'
import { cn } from '@/lib/utils'

const SUGESTOES = [
  'Como está o hall no fim do período?',
  'Algum CRAC teve problema? Quando?',
  'Quais racks passaram de 27 °C, e por quê?',
  'Há sensores com defeito?',
]

interface Troca {
  id: number
  pergunta: string
  passos: EventoPasso[]
  resposta?: EventoResposta
  erro?: string
  estado: 'pensando' | 'pronta' | 'erro' | 'interrompida'
}

function Passo({ passo }: { passo: EventoPasso }) {
  const argumentos = Object.entries(passo.argumentos)
    .filter(([chave, valor]) => valor !== null && chave !== 'sql')
    .map(([chave, valor]) => `${chave}=${JSON.stringify(valor)}`)
    .join(', ')
  return (
    <li className="text-xs">
      <div className="flex flex-wrap items-baseline gap-x-2 font-mono">
        <span className="text-muted-foreground">→</span>
        <span>
          {passo.ferramenta}({argumentos})
        </span>
        <span className="tabular text-muted-foreground">
          {numero(passo.segundos, 2)} s · {passo.erro ? 'erro' : `${numero(passo.linhas)} linhas`}
        </span>
      </div>
      {passo.sql && (
        <details className="mt-1 ml-4">
          <summary className="cursor-pointer text-muted-foreground hover:text-foreground">SQL</summary>
          <pre className="mt-1 rounded-md bg-muted px-3 py-2 font-mono text-[0.7rem] leading-relaxed break-words whitespace-pre-wrap">
            {passo.sql.trim()}
          </pre>
        </details>
      )}
      {passo.erro && passo.mensagem_erro && (
        <p className="mt-1 ml-4 text-amber-700 dark:text-amber-400">{passo.mensagem_erro}</p>
      )}
    </li>
  )
}

/** Markdown da resposta com o estilo do app (sem plugin de tipografia). */
function TextoDaResposta({ texto }: { texto: string }) {
  return (
    <div className="space-y-3 text-sm leading-relaxed">
      <Markdown
        remarkPlugins={[remarkGfm]}
        components={{
          ul: (p) => <ul className="ml-5 list-disc space-y-1" {...p} />,
          ol: (p) => <ol className="ml-5 list-decimal space-y-1" {...p} />,
          strong: (p) => <strong className="font-semibold" {...p} />,
          code: (p) => <code className="rounded bg-muted px-1 py-0.5 font-mono text-[0.8em]" {...p} />,
          table: (p) => (
            <div className="overflow-x-auto">
              <table className="tabular w-full text-xs" {...p} />
            </div>
          ),
          th: (p) => <th className="border-b px-2 py-1 text-left font-medium" {...p} />,
          td: (p) => <td className="border-b px-2 py-1" {...p} />,
          a: (p) => <a className="text-primary underline underline-offset-4" target="_blank" rel="noreferrer" {...p} />,
        }}
      >
        {texto}
      </Markdown>
    </div>
  )
}

function Rodape({ resposta }: { resposta: EventoResposta }) {
  const custo = resposta.custo_usd !== null ? `US$ ${numero(resposta.custo_usd, 4)}` : 'custo não estimado'
  return (
    <p className="tabular text-xs text-muted-foreground">
      {resposta.provedor} · <span className="font-mono">{resposta.modelo}</span> · {numero(resposta.segundos, 1)} s ·{' '}
      {numero(resposta.tokens_entrada)} tokens de entrada ({numero(resposta.tokens_cache)} do cache),{' '}
      {numero(resposta.tokens_saida)} de saída · {custo}
    </p>
  )
}

function CartaoDaTroca({ troca }: { troca: Troca }) {
  // Aberta enquanto o agente trabalha; recolhida quando a resposta chega, salvo escolha explícita.
  const [escolha, setEscolha] = useState<boolean | null>(null)
  const abertos = escolha ?? troca.estado === 'pensando'
  const setAbertos = (valor: boolean) => setEscolha(valor)
  return (
    <article className="space-y-3" aria-busy={troca.estado === 'pensando'}>
      <p className="ml-auto w-fit max-w-[85%] rounded-lg bg-accent px-4 py-2 text-sm text-accent-foreground">
        {troca.pergunta}
      </p>
      <Card>
        <CardContent className="space-y-4">
          {(troca.passos.length > 0 || troca.estado === 'pensando') && (
            <div>
              <button
                type="button"
                onClick={() => setAbertos(!abertos)}
                className="flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground"
                aria-expanded={abertos}
              >
                <ChevronRight className={cn('size-3.5 transition-transform', abertos && 'rotate-90')} />
                {troca.passos.length === 1 ? '1 consulta' : `${troca.passos.length} consultas`} aos dados
              </button>
              {abertos && (
                <ol className="mt-2 space-y-2" aria-live="polite">
                  {troca.passos.map((passo, i) => (
                    <Passo key={i} passo={passo} />
                  ))}
                </ol>
              )}
            </div>
          )}
          {troca.estado === 'pensando' && (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" /> Investigando os dados…
            </p>
          )}
          {troca.resposta && <TextoDaResposta texto={troca.resposta.texto} />}
          {troca.resposta && troca.resposta.parada !== 'fim' && (
            <p className="text-xs text-amber-700 dark:text-amber-400">
              A resposta ficou incompleta ({troca.resposta.parada}). {troca.resposta.detalhe}
            </p>
          )}
          {troca.erro && <Falha erro={troca.erro} titulo="A pergunta não pôde ser respondida" />}
          {troca.estado === 'interrompida' && <p className="text-xs text-muted-foreground">Interrompida.</p>}
          {troca.resposta && <Rodape resposta={troca.resposta} />}
        </CardContent>
      </Card>
    </article>
  )
}

function Conversa({ simulacao, llm }: { simulacao: Simulacao; llm: string }) {
  const [trocas, setTrocas] = useState<Troca[]>([])
  const [texto, setTexto] = useState('')
  const controle = useRef<AbortController | null>(null)
  const proximoId = useRef(1)
  const ocupado = trocas.some((t) => t.estado === 'pensando')

  const atualizar = (id: number, mudanca: (t: Troca) => Troca) =>
    setTrocas((atuais) => atuais.map((t) => (t.id === id ? mudanca(t) : t)))

  async function enviar(pergunta: string) {
    const limpa = pergunta.trim()
    if (!limpa || ocupado) return
    const id = proximoId.current++
    setTrocas((atuais) => [...atuais, { id, pergunta: limpa, passos: [], estado: 'pensando' }])
    setTexto('')
    controle.current = new AbortController()
    try {
      for await (const evento of perguntar(simulacao.nome, limpa, controle.current.signal)) {
        if (evento.tipo === 'passo') atualizar(id, (t) => ({ ...t, passos: [...t.passos, evento.dados] }))
        else if (evento.tipo === 'resposta') atualizar(id, (t) => ({ ...t, resposta: evento.dados, estado: 'pronta' }))
        else atualizar(id, (t) => ({ ...t, erro: evento.dados.mensagem, estado: 'erro' }))
      }
      atualizar(id, (t) => (t.estado === 'pensando' ? { ...t, estado: 'erro', erro: 'A conexão terminou sem resposta.' } : t))
    } catch (erro) {
      if (controle.current?.signal.aborted) atualizar(id, (t) => ({ ...t, estado: 'interrompida' }))
      else atualizar(id, (t) => ({ ...t, estado: 'erro', erro: erro instanceof Error ? erro.message : String(erro) }))
    }
  }

  const aoEnviar = (evento: FormEvent) => {
    evento.preventDefault()
    void enviar(texto)
  }
  const aoTeclar = (evento: KeyboardEvent<HTMLTextAreaElement>) => {
    if (evento.key === 'Enter' && !evento.shiftKey) {
      evento.preventDefault()
      void enviar(texto)
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Perguntar</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          A IA consulta os dados do hall para responder e mostra cada consulta que fez. Cada pergunta é respondida do
          zero, sem lembrar das anteriores. Modelo: <span className="font-mono">{llm}</span>.
        </p>
      </div>

      {trocas.length === 0 && (
        <div className="flex flex-wrap gap-2">
          {SUGESTOES.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => void enviar(s)}
              className="rounded-full border px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      <div className="space-y-6">
        {trocas.map((t) => (
          <CartaoDaTroca key={t.id} troca={t} />
        ))}
      </div>

      <form onSubmit={aoEnviar} className="sticky bottom-4 flex items-end gap-2 rounded-xl border bg-card p-2 shadow-sm">
        <textarea
          id="pergunta"
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          onKeyDown={aoTeclar}
          rows={2}
          maxLength={2000}
          placeholder="Pergunte sobre o hall, por exemplo: o que aconteceu na fileira A no dia 7 de madrugada?"
          aria-label="Sua pergunta"
          className="min-h-11 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm outline-none placeholder:text-muted-foreground"
        />
        {ocupado ? (
          <Button type="button" variant="secondary" size="icon" onClick={() => controle.current?.abort()} aria-label="Interromper">
            <Square className="size-4" />
          </Button>
        ) : (
          <Button type="submit" size="icon" disabled={!texto.trim()} aria-label="Enviar pergunta">
            <ArrowUp className="size-4" />
          </Button>
        )}
      </form>
    </div>
  )
}

export function Perguntar() {
  const { simulacao, carregando, erro } = useSimulacao()
  const saude = useSaude()
  if (erro) return <Falha erro={erro} />
  if (carregando || !simulacao || saude.isPending) return <Carregando />
  if (saude.error) return <Falha erro={saude.error} />
  if (!saude.data?.llm) {
    return (
      <div className="mx-auto max-w-2xl">
        <Falha
          titulo="A IA está desligada neste servidor"
          erro={new ErroApi(
            503,
            'Suba a API com um provedor configurado, por exemplo: uv run isoterma servir data --llm claude (com ANTHROPIC_API_KEY definida).',
          )}
        />
      </div>
    )
  }
  return <Conversa simulacao={simulacao} llm={saude.data.llm} />
}
