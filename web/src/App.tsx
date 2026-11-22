import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { lazy, Suspense } from 'react'
import { createBrowserRouter, Navigate, RouterProvider } from 'react-router'

import { useSimulacoes } from '@/api/consultas'
import { Carregando, Falha } from '@/componentes/Estado'
import { Layout } from '@/componentes/Layout'
import { TooltipProvider } from '@/components/ui/tooltip'
import { Painel } from '@/paginas/Painel'

// O mapa (e o D3 que ele usa) só é baixado quando alguém abre a página.
const Mapa = lazy(() => import('@/paginas/Mapa').then((m) => ({ default: m.Mapa })))

/** A raiz manda para a simulação de demonstração, se houver, ou para a primeira da lista. */
function Inicio() {
  const { data, error, isPending } = useSimulacoes()
  if (error) return <Falha erro={error} />
  if (isPending) return <Carregando />
  if (!data?.length) {
    return (
      <Falha
        titulo="Nenhuma simulação encontrada"
        erro="Gere uma com `uv run isoterma simular --preset demo` e reinicie o `isoterma servir`."
      />
    )
  }
  const escolhida = data.find((s) => s.nome === 'demo') ?? data[0]
  return <Navigate to={`/${escolhida.nome}`} replace />
}

const rotas = [
  {
    path: '/',
    element: <Layout />,
    children: [
      { index: true, element: <Inicio /> },
      { path: ':simulacao', element: <Painel /> },
      {
        path: ':simulacao/mapa',
        element: (
          <Suspense fallback={<Carregando />}>
            <Mapa />
          </Suspense>
        ),
      },
    ],
  },
]

const roteador = createBrowserRouter(rotas)

function criarClienteDeConsultas() {
  return new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } })
}

const consultas = criarClienteDeConsultas()

export default function App() {
  return (
    <QueryClientProvider client={consultas}>
      <TooltipProvider>
        <RouterProvider router={roteador} />
      </TooltipProvider>
    </QueryClientProvider>
  )
}
