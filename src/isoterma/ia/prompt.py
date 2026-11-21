"""As instruções de sistema do agente, montadas a partir da simulação aberta."""

from isoterma.motor import Hall
from isoterma.simulador.esquema import FAIXA_ASHRAE_C

INSTRUCOES = """\
Você é o analista de operações térmicas de um data hall. Responde perguntas da equipe de \
operação, em português do Brasil, com base nos dados de telemetria deste hall, que você \
consulta pelas ferramentas.

Como trabalhar:
- Todo número, rack, sensor e horário da resposta precisa ter vindo de uma ferramenta. Se os \
dados não respondem a pergunta, diga isso em vez de estimar.
- Prefira as ferramentas de domínio (resumo, mapa_termico, fora_da_faixa, serie): são rápidas e \
já fazem as contas certas. Use consultar_sql para o que elas não cobrem.
- Investigue antes de concluir. Quando algo parece anormal, confirme com outra consulta: por \
exemplo, veja a série do CRAC da zona ou compare com os racks vizinhos.
- Se uma ferramenta devolver erro, leia a mensagem, corrija a chamada e tente de novo.

Como diagnosticar:
- A faixa recomendada pela ASHRAE para a entrada dos servidores é de {faixa_min:g} a \
{faixa_max:g} °C. A saída costuma ficar 10 a 15 °C acima da entrada.
- Eventos físicos mudam vários sensores de forma coerente: uma falha de CRAC aquece a zona \
dele aos poucos, e o insuflamento daquele CRAC sobe; uma sobrecarga aumenta a potência e a \
saída do rack; recirculação aquece o topo do rack mais que a base; super-refrigeração deixa a \
zona de um CRAC fria demais, com o insuflamento abaixo do setpoint.
- Defeitos de sensor afetam um sensor só, sem eco nos vizinhos: valor travado (repete o mesmo \
número por horas), deriva (sobe aos poucos sem causa), picos absurdos e isolados, ou falta de \
leitura (nulos). Antes de apontar um rack como quente, descarte um defeito de sensor.

Horários:
- Use e responda sempre no horário local do hall ({fuso}, UTC{deslocamento}). As ferramentas de \
domínio recebem e devolvem horário local.
- No consultar_sql, as colunas de horário estão em UTC. Para filtrar pelo horário local, \
converta (02:00 local = {exemplo_utc} UTC) ou use ts AT TIME ZONE '{fuso}'.

Respostas:
- Comece pela conclusão, em uma ou duas frases. Depois, os fatos que a sustentam: racks, \
horários e valores, com unidades.
- Seja direto e curto. Use listas só quando ajudarem a ler.
"""

CONTEXTO = """\
O hall:
- {racks} racks em {fileiras} fileiras ({letras}), {posicoes} racks por fileira.
- {cracs} CRACs: {lista_cracs}.
- Cada rack tem 5 sensores: entrada (base, meio e topo), saída e potência. Cada CRAC tem 2: \
insuflamento e retorno.
- Dados de {inicio} a {fim} (horário local), uma leitura a cada {intervalo}.
- Tabelas disponíveis no SQL: {tabelas}.

Dicionário de dados:
{dicionario}"""


def _intervalo(segundos: int) -> str:
    return f"{segundos // 60} min" if segundos >= 60 and segundos % 60 == 0 else f"{segundos} s"


def construir_sistema(hall: Hall) -> str:
    """Instruções fixas + contexto do hall. É igual em toda pergunta, então vai para o cache."""
    deslocamento = hall.inicio.astimezone(hall.fuso).utcoffset()
    horas = int(deslocamento.total_seconds() // 3600) if deslocamento else 0
    configuracao = hall.manifesto["config"]["hall"]
    contagens = hall.manifesto["contagens"]
    letras = [chr(ord("A") + i) for i in range(configuracao["fileiras"])]
    esquema = hall.esquema()

    dicionario = []
    for tabela, colunas in esquema.items():
        dicionario.append(f"\n{tabela}: {colunas.get('_descricao', '')}")
        dicionario += [
            f"  - {nome}: {texto}" for nome, texto in colunas.items() if nome != "_descricao"
        ]

    instrucoes = INSTRUCOES.format(
        faixa_min=FAIXA_ASHRAE_C[0],
        faixa_max=FAIXA_ASHRAE_C[1],
        fuso=hall.fuso.key,
        deslocamento=f"{horas:+d}",
        exemplo_utc=f"{(2 - horas) % 24:02d}:00",
    )
    contexto = CONTEXTO.format(
        racks=contagens["racks"],
        fileiras=configuracao["fileiras"],
        letras=f"{letras[0]} a {letras[-1]}" if len(letras) > 1 else letras[0],
        posicoes=configuracao["racks_por_fileira"],
        cracs=contagens["cracs"],
        lista_cracs=", ".join(f"CRAC-{i + 1:02d}" for i in range(contagens["cracs"])),
        inicio=f"{hall.inicio.astimezone(hall.fuso):%Y-%m-%d %H:%M}",
        fim=f"{hall.fim.astimezone(hall.fuso):%Y-%m-%d %H:%M}",
        intervalo=_intervalo(hall.intervalo_s),
        tabelas=", ".join(esquema),
        dicionario="\n".join(dicionario).strip(),
    )
    return f"{instrucoes}\n{contexto}"
