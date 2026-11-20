"""Dicionário de dados da simulação.

Vai no manifesto de cada simulação e, na fase 2, será o contexto que a IA recebe para gerar SQL.
"""

ESQUEMA: dict[str, dict[str, str]] = {
    "leituras": {
        "_descricao": "Uma linha por leitura de sensor. É a tabela grande (até bilhões de linhas).",
        "ts": "Instante da leitura, em UTC",
        "sensor_id": "Sensor que fez a leitura (chave para sensores.sensor_id)",
        "valor": "Valor lido, na unidade do sensor (°C ou kW). Nulo quando não houve leitura",
    },
    "sensores": {
        "_descricao": "Cadastro dos sensores. Cada rack tem 5 e cada CRAC tem 2.",
        "sensor_id": "Identificador numérico do sensor",
        "codigo": "Código legível, por exemplo 'C-07/entrada-topo' ou 'CRAC-02/retorno'",
        "tipo": (
            "temp_entrada (ar frio na frente do rack), temp_saida (ar quente atrás do rack), "
            "potencia_kw (consumo do rack), temp_insuflamento (ar que sai do CRAC) ou "
            "temp_retorno (ar que volta ao CRAC)"
        ),
        "unidade": "°C ou kW",
        "altura": "base, meio ou topo (só para temp_entrada)",
        "rack_id": "Rack do sensor (nulo para sensores de CRAC)",
        "crac_id": "CRAC do sensor (nulo para sensores de rack)",
        "x_m": "Posição no hall, em metros, ao longo da fileira",
        "y_m": "Posição no hall, em metros, entre as fileiras",
    },
    "racks": {
        "_descricao": "Cadastro dos racks, organizados em fileiras (A, B, C...).",
        "rack_id": "Identificador, por exemplo 'C-07' (fileira C, posição 7)",
        "fileira": "Letra da fileira",
        "posicao": "Posição do rack na fileira, começando em 1",
        "x_m": "Posição no hall, em metros, ao longo da fileira",
        "y_m": "Posição no hall, em metros, entre as fileiras",
        "potencia_nominal_kw": "Consumo típico do rack",
        "perfil": "padrao ou denso (por exemplo, racks de GPU)",
        "zona_crac": "CRAC que mais refrigera o rack",
    },
    "cracs": {
        "_descricao": "Unidades de ar-condicionado de precisão (CRAC).",
        "crac_id": "Identificador, por exemplo 'CRAC-02'",
        "x_m": "Posição no hall, em metros",
        "y_m": "Posição no hall, em metros",
        "setpoint_c": "Temperatura de insuflamento configurada",
    },
    "incidentes": {
        "_descricao": (
            "Gabarito dos incidentes injetados pelo simulador. Serve para avaliar a detecção "
            "de anomalias e não existiria num data center real."
        ),
        "incidente_id": "Identificador do incidente",
        "tipo": (
            "falha_crac, rack_sobrecarregado, recirculacao, super_refrigeracao, "
            "sensor_congelado, sensor_deriva, sensor_picos ou sensor_sem_leitura"
        ),
        "alvo_tipo": "crac, rack ou sensor",
        "alvo": "crac_id, rack_id ou código do sensor afetado",
        "inicio": "Início do incidente, em UTC",
        "fim": "Fim do incidente, em UTC",
        "intensidade": "Força do incidente; o significado depende do tipo",
        "descricao": "Explicação em português",
    },
}

FAIXA_ASHRAE_C = (18.0, 27.0)
"""Faixa recomendada pela ASHRAE para a temperatura de entrada dos servidores (classe A1)."""
