import { NavLink, Outlet, useNavigate, useParams } from 'react-router'

import { useSimulacoes } from '@/api/consultas'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { cn } from '@/lib/utils'
import { numero } from '@/lib/formato'

import { AlternarTema } from './Tema'

/** O símbolo: três isotermas. */
export function Marca({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <path d="M3 17c3-1 4-6 9-6s6 5 9 6" fill="none" stroke="#3f8fcf" strokeWidth="2" strokeLinecap="round" />
      <path d="M5 13c2.5-1 3-5 7-5s4.5 4 7 5" fill="none" stroke="#f0a03a" strokeWidth="2" strokeLinecap="round" />
      <path d="M8 9c1.5-.8 2-3 4-3s2.5 2.2 4 3" fill="none" stroke="#d6432a" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}

function Navegacao({ simulacao }: { simulacao: string }) {
  const itens = [
    { para: `/${simulacao}`, rotulo: 'Painel', fim: true },
    { para: `/${simulacao}/mapa`, rotulo: 'Mapa térmico', fim: false },
    { para: `/${simulacao}/perguntar`, rotulo: 'Perguntar', fim: false },
  ]
  return (
    <nav className="flex items-center gap-1" aria-label="Seções">
      {itens.map((item) => (
        <NavLink
          key={item.para}
          to={item.para}
          end={item.fim}
          className={({ isActive }) =>
            cn(
              'rounded-md px-3 py-1.5 text-sm transition-colors',
              isActive ? 'bg-accent text-accent-foreground' : 'text-muted-foreground hover:text-foreground',
            )
          }
        >
          {item.rotulo}
        </NavLink>
      ))}
    </nav>
  )
}

function SeletorSimulacao({ atual }: { atual: string }) {
  const { data } = useSimulacoes()
  const navegar = useNavigate()
  if (!data || data.length < 2) return null
  return (
    <Select value={atual} onValueChange={(valor) => valor && navegar(`/${valor}`)}>
      <SelectTrigger className="w-44" aria-label="Simulação">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {data.map((s) => (
          <SelectItem key={s.nome} value={s.nome}>
            {s.nome} <span className="text-muted-foreground">· {numero(s.racks)} racks</span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

export function Layout() {
  const { simulacao = '' } = useParams()
  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-20 border-b bg-background/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-4 px-4 sm:px-6">
          <NavLink to={`/${simulacao}`} className="flex items-center gap-2 font-semibold">
            <Marca className="size-6" />
            Isoterma
          </NavLink>
          {simulacao && <Navegacao simulacao={simulacao} />}
          <div className="ml-auto flex items-center gap-2">
            {simulacao && <SeletorSimulacao atual={simulacao} />}
            <AlternarTema />
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
        <Outlet />
      </main>
    </div>
  )
}
