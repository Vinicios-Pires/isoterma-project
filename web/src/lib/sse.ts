// Leitor de Server-Sent Events sobre um corpo de resposta do fetch.
//
// O ``EventSource`` do navegador só faz GET, e o ``perguntar`` é um POST, então o fluxo é lido
// à mão: os bytes chegam em pedaços arbitrários, que podem cortar uma linha ou um evento ao meio.

export interface EventoSSE {
  evento: string
  dados: string
}

/** Interpreta um bloco de texto já completo (um evento) no formato SSE. */
export function interpretarBloco(bloco: string): EventoSSE | null {
  let evento = 'message'
  const dados: string[] = []
  for (const linha of bloco.split(/\r?\n/)) {
    if (linha === '' || linha.startsWith(':')) continue // comentários servem de keep-alive
    const separador = linha.indexOf(':')
    const campo = separador === -1 ? linha : linha.slice(0, separador)
    let valor = separador === -1 ? '' : linha.slice(separador + 1)
    if (valor.startsWith(' ')) valor = valor.slice(1)
    if (campo === 'event') evento = valor
    else if (campo === 'data') dados.push(valor)
  }
  return dados.length ? { evento, dados: dados.join('\n') } : null
}

/** Os eventos do fluxo, um a um, à medida que chegam. */
export async function* lerEventos(corpo: ReadableStream<Uint8Array>): AsyncGenerator<EventoSSE> {
  const leitor = corpo.getReader()
  // stream: true guarda um caractere UTF-8 cortado entre dois pedaços até o próximo chegar.
  const decodificador = new TextDecoder()
  let pendente = ''
  try {
    while (true) {
      const { value, done } = await leitor.read()
      if (done) break
      pendente += decodificador.decode(value, { stream: true })
      // Um evento termina numa linha em branco.
      let fim = pendente.search(/\r?\n\r?\n/)
      while (fim !== -1) {
        const bloco = pendente.slice(0, fim)
        pendente = pendente.slice(fim).replace(/^\r?\n\r?\n/, '')
        const evento = interpretarBloco(bloco)
        if (evento) yield evento
        fim = pendente.search(/\r?\n\r?\n/)
      }
    }
    const ultimo = interpretarBloco(pendente + decodificador.decode())
    if (ultimo) yield ultimo
  } finally {
    leitor.releaseLock()
  }
}
