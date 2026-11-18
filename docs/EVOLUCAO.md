# Evolução do projeto

Este documento registra o que o projeto era na origem e no que ele está se transformando.

---

## Antes: One Billion Row Challenge (versão da aula)

Projeto didático usado em um curso de Python, inspirado no
[The One Billion Row Challenge](https://github.com/gunnarmorling/1brc).

**Objetivo:** ler um arquivo com até 1 bilhão de linhas no formato
`<estação>;<temperatura>` e calcular o mínimo, a média e o máximo por estação,
comparando diferentes ferramentas do ecossistema Python.

**Implementações (tempos do README original, Apple M1, 8GB RAM):**

| Implementação | Tempo |
|---|---|
| Bash + awk | 25 min |
| Python puro | 20 min |
| Pandas | 263 s |
| Dask | 155.6 s |
| Polars | 33.9 s |
| DuckDB | 15.0 s |

**Contribuições da turma:** correção `next` → `continue`, arquivo temporário
(`--temp`), expiração automática em 24h e limpeza via Supabase Storage.

### Diagnóstico (análise de 17/11/2026)

Problemas encontrados no estado original:

- O gerador cria 1 milhão de linhas, não 1 bilhão (valor fixo em `src/create_measurements.py`; `check_args` nunca é chamada).
- As temperaturas são `uniform(-99.9, 99.9)` para todas as estações, então os resultados não têm significado estatístico.
- `exit()` no nível do módulo encerra quem importar o gerador.
- O caminho do arquivo em `src/using_pandas.py` está incorreto quando o script é executado da raiz do repositório.
- Python fixo em `3.12.1`; `supabase` e `python-dotenv` não declarados; `modin` declarado sem uso.
- `src/using_python.py` abre o arquivo sem `encoding="utf-8"` (cp1252 no Windows).
- O multiprocessing do Pandas faz o parsing no processo principal e serializa chunks de 100M linhas.
- Cada engine imprime num formato diferente, sem validação cruzada dos resultados.
- Código duplicado, documentação espalhada e nenhum teste.

---

## Depois: Isoterma *(em definição)*

> **Isoterma**: inteligência térmica para data centers. Veja, entenda e pergunte.
>
> *Isoterma é a linha que liga pontos de mesma temperatura num mapa.*

**Decidido (18/11/2026):** nome Isoterma (repositório `isoterma-project`), projeto de
portfólio, nicho de **data centers** (simulador de data hall com incidentes injetados,
núcleo genérico), IA com Claude como padrão e provedores plugáveis (OpenAI, Gemini,
Ollama), interface em camadas (pacote + CLI Typer + API FastAPI + web React/Vite/TypeScript)
e Python 3.14.

**Decidido (18/11/2026, parte 2):**
- **Gerenciador:** uv, com ruff, pyright, pytest, pre-commit e CI no GitHub Actions
  (3.14 obrigatório, 3.15 experimental).
- **Deploy em dois modos.** A demo pública gratuita usa React no Cloudflare Pages, DuckDB-WASM
  no navegador lendo Parquet do Cloudflare R2, uma API FastAPI leve só para a IA no Google
  Cloud Run e um pipeline diário no GitHub Actions. O custo da IA é controlado com BYOK, cota
  gratuita com modelo barato, rate limit e limite de gasto. O outro modo é self-host via
  `docker compose`.
- **Legado:** o projeto original foi movido intocado para `legacy/`. O benchmark novo
  reimplementa Python, pandas, Polars e DuckDB.
- **Licença:** MIT para o código do Isoterma. `legacy/` mantém os créditos dos autores originais.

**Ideia:** transformar o benchmark em um produto que ingere grandes volumes de
leituras de sensores (temperatura e, futuramente, outros), agrega com alta
performance e permite **fazer perguntas em português**, com a IA traduzindo a
pergunta para SQL e explicando os resultados e as anomalias.

```
Pergunta em PT-BR → LLM gera SQL → DuckDB sobre Parquet → resultado + anomalias → LLM explica
```

O modelo de IA vê apenas o schema e os resultados agregados, nunca os dados brutos.

### Fases planejadas

1. **Núcleo:** atualização do Python (alvo 3.14, testando também a 3.15) e de todas as dependências (DuckDB 2.x, Polars 2.x, pandas 3.x), correção dos bugs, gerador realista em Parquet, motor de agregação com DuckDB, benchmark com validação cruzada entre engines e testes.
2. **Camada de IA:** texto → SQL com validação (somente leitura), detecção de anomalias, relatórios explicados, API FastAPI e web React com o mapa térmico.
3. **Dados reais:** ingestão de fontes como INMET ou Open-Meteo, histórico particionado e alertas.

### Decisões em aberto

- Desenho do simulador de data hall (tamanho do hall, sensores por rack, tipos de incidente)

O projeto original da aula está preservado em [`legacy/`](../legacy/) como referência do
ponto de partida.
