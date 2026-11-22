/** Um corpo de resposta que entrega o texto nos pedaços dados (como a rede faz). */
export function corpoEmPedacos(pedacos: string[]): ReadableStream<Uint8Array> {
  const codificador = new TextEncoder()
  return new ReadableStream({
    start(controle) {
      for (const p of pedacos) controle.enqueue(codificador.encode(p))
      controle.close()
    },
  })
}
