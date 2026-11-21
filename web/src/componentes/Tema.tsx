import { Moon, Sun } from 'lucide-react'
import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'

type Tema = 'claro' | 'escuro'
const CHAVE = 'isoterma:tema'

function temaInicial(): Tema {
  try {
    const salvo = localStorage.getItem(CHAVE)
    if (salvo === 'claro' || salvo === 'escuro') return salvo
  } catch {
    // Sem acesso ao armazenamento (janela anônima, por exemplo): segue o sistema.
  }
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'escuro' : 'claro'
}

export function AlternarTema() {
  const [tema, setTema] = useState<Tema>(temaInicial)

  useEffect(() => {
    document.documentElement.classList.toggle('dark', tema === 'escuro')
    try {
      localStorage.setItem(CHAVE, tema)
    } catch {
      // Ignora: o tema só não fica lembrado.
    }
  }, [tema])

  const proximo = tema === 'escuro' ? 'claro' : 'escuro'
  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={() => setTema(proximo)}
      aria-label={`Mudar para o tema ${proximo}`}
      title={`Tema ${proximo}`}
    >
      {tema === 'escuro' ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </Button>
  )
}
