import { describe, expect, it } from 'vitest'

import { corpoEmPedacos } from '@/testes/fluxo'

import { interpretarBloco, lerEventos } from './sse'

async function todos(corpo: ReadableStream<Uint8Array>) {
  const eventos = []
  for await (const e of lerEventos(corpo)) eventos.push(e)
  return eventos
}

describe('interpretarBloco', () => {
  it('lê o nome do evento e junta as linhas de dados', () => {
    expect(interpretarBloco('event: passo\ndata: {"a":1}')).toEqual({ evento: 'passo', dados: '{"a":1}' })
    expect(interpretarBloco('data: linha 1\ndata: linha 2')).toEqual({ evento: 'message', dados: 'linha 1\nlinha 2' })
  })

  it('ignora comentários de keep-alive', () => {
    expect(interpretarBloco(': ping')).toBeNull()
  })
})

describe('lerEventos', () => {
  it('remonta eventos cortados no meio entre pedaços', async () => {
    const eventos = await todos(
      corpoEmPedacos(['event: pas', 'so\ndata: {"x"', ':1}\n\nevent: resp', 'osta\r\ndata: {"y":2}\r\n\r\n']),
    )

    expect(eventos).toEqual([
      { evento: 'passo', dados: '{"x":1}' },
      { evento: 'resposta', dados: '{"y":2}' },
    ])
  })

  it('não quebra um caractere acentuado dividido entre pedaços', async () => {
    const bytes = new TextEncoder().encode('data: "está"\n\n')
    const corte = bytes.indexOf(0xc3) + 1 // no meio do "á" (dois bytes em UTF-8)
    const corpo = new ReadableStream<Uint8Array>({
      start(controle) {
        controle.enqueue(bytes.slice(0, corte))
        controle.enqueue(bytes.slice(corte))
        controle.close()
      },
    })

    expect(await todos(corpo)).toEqual([{ evento: 'message', dados: '"está"' }])
  })

  it('entrega o último evento mesmo sem linha em branco no fim', async () => {
    expect(await todos(corpoEmPedacos(['event: erro\ndata: {}']))).toEqual([{ evento: 'erro', dados: '{}' }])
  })
})
