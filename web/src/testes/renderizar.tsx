import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import type { ReactNode } from 'react'
import { createMemoryRouter, RouterProvider } from 'react-router'

/** Renderiza uma página numa rota, com o React Query e o roteador como no app. */
export function renderizarNaRota(caminho: string, rotas: { path: string; element: ReactNode }[]) {
  const consultas = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const roteador = createMemoryRouter(rotas, { initialEntries: [caminho] })
  return render(
    <QueryClientProvider client={consultas}>
      <RouterProvider router={roteador} />
    </QueryClientProvider>,
  )
}
