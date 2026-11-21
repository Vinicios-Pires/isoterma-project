import { fireEvent, render } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { PLANTA, VALORES } from '@/testes/dados'

import { PlantaTermica } from './PlantaTermica'

function renderizar(aoSelecionar = vi.fn(), selecionado: string | null = null) {
  const resultado = render(
    <PlantaTermica
      planta={PLANTA}
      racks={VALORES}
      tipo="temp_entrada"
      selecionado={selecionado}
      aoSelecionar={aoSelecionar}
    />,
  )
  return { ...resultado, aoSelecionar }
}

describe('PlantaTermica', () => {
  it('desenha um bloco por rack e um rótulo por CRAC', () => {
    const { container, getByText } = renderizar()

    expect(container.querySelectorAll('[data-rack]')).toHaveLength(6)
    expect(getByText('CRAC-01')).toBeInTheDocument()
  })

  it('traça a isoterma de 27 °C quando uma zona passa do limite', () => {
    const { container } = renderizar()

    const limite = container.querySelector('[data-isoterma="27"]')
    expect(limite).not.toBeNull()
    expect(limite?.getAttribute('stroke-dasharray')).toBe('6 3')
  })

  it('contorna em vermelho os racks acima da faixa', () => {
    const { container } = renderizar()

    expect(container.querySelector('[data-rack="A-01"]')?.getAttribute('stroke')).toBe('#b3261e')
    expect(container.querySelector('[data-rack="B-01"]')?.getAttribute('stroke')).not.toBe('#b3261e')
  })

  it('seleciona um rack ao clicar e mostra a dica ao passar o mouse', () => {
    const { container, aoSelecionar, getByText } = renderizar()
    const rack = container.querySelector('[data-rack="A-03"]')!

    fireEvent.click(rack)
    fireEvent.pointerMove(rack, { clientX: 10, clientY: 10 })

    expect(aoSelecionar).toHaveBeenCalledWith('A-03')
    expect(getByText('acima de 27 °C')).toBeInTheDocument()
  })
})
