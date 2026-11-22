import { Link } from 'react-router'

import type { RackForaDaFaixa } from '@/api/tipos'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { comUnidade, dataHora, duracao } from '@/lib/formato'

export function TabelaForaDaFaixa({
  racks,
  simulacao,
  fuso,
  limite = 8,
  janela,
}: {
  racks: RackForaDaFaixa[]
  simulacao: string
  fuso: string
  limite?: number
  /** Monta a janela de tempo do detalhe a partir de um instante. */
  janela?: (instante: string) => URLSearchParams
}) {
  if (racks.length === 0) {
    return <p className="text-sm text-muted-foreground">Nenhum rack saiu da faixa de 18 a 27 °C.</p>
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Rack</TableHead>
          <TableHead className="text-right">Acima de 27 °C</TableHead>
          <TableHead className="text-right">Abaixo de 18 °C</TableHead>
          <TableHead className="text-right">Pico</TableHead>
          <TableHead>Primeira vez</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {racks.slice(0, limite).map((r) => (
          <TableRow key={r.rack_id}>
            <TableCell className="font-mono">
              <Link
                to={`/${simulacao}/rack/${r.rack_id}${r.primeira_vez && janela ? `?${janela(r.primeira_vez)}` : ''}`}
                className="text-primary underline-offset-4 hover:underline"
              >
                {r.rack_id}
              </Link>{' '}
              <span className="text-xs text-muted-foreground">{r.zona_crac}</span>
            </TableCell>
            <TableCell className="tabular text-right">{r.minutos_acima ? duracao(r.minutos_acima) : '—'}</TableCell>
            <TableCell className="tabular text-right">{r.minutos_abaixo ? duracao(r.minutos_abaixo) : '—'}</TableCell>
            <TableCell className="tabular text-right">{comUnidade(r.pico_c, '°C')}</TableCell>
            <TableCell>
              {r.primeira_vez ? (
                <Link
                  to={`/${simulacao}/mapa?t=${encodeURIComponent(r.primeira_vez)}&rack=${r.rack_id}`}
                  className="tabular font-mono text-primary underline-offset-4 hover:underline"
                >
                  {dataHora(r.primeira_vez, fuso)}
                </Link>
              ) : (
                '—'
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
