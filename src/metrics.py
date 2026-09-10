"""
A regra de negocio central do projeto, em um lugar so.

"Taxa de gravidade" = quantos por cento dos incidentes de um grupo foram
graves (fault_severity = 2).

Por que este modulo existe:
    O README usa essa conta em SQL (sql/analysis_queries.sql) e o dashboard
    precisa da mesma conta em pandas, porque filtra em memoria. Sem um lugar
    unico, seriam duas implementacoes da mesma regra -- e um dia o numero do
    dashboard diria uma coisa e o do README outra.

    Aqui fica a versao pandas, e tests/test_metrics.py garante que ela
    concorda com a versao SQL.
"""

from __future__ import annotations

import pandas as pd

# Abaixo deste numero de incidentes a taxa e' pouco confiavel: com poucos casos
# ela so consegue dar valores extremos (com 4 incidentes, os unicos resultados
# possiveis sao 0%, 25%, 50%, 75% e 100%).
AMOSTRA_MINIMA_CONFIAVEL = 50

GRAVE = 2  # valor de fault_severity que representa "muitas falhas"

# Percentual de incidentes graves no dataset completo. Serve de linha de
# referencia nos graficos: acima dela, o grupo esta pior que a media.
# O valor mora aqui e tests/test_metrics.py confere que continua batendo com o
# banco -- se o dataset mudar, o teste quebra em vez de o grafico mentir.
TAXA_BASE_PCT = 9.84


def taxa_base(df: pd.DataFrame) -> float:
    """
    Percentual exato de incidentes graves em `df`, SEM arredondar.

    Use este valor para calculo (comparacoes, deltas) e TAXA_BASE_PCT para
    exibicao. Arredondar antes de comparar produz resultados como "-0,00".
    """
    return (df["fault_severity"] == GRAVE).mean() * 100


def taxa_de_gravidade(df: pd.DataFrame, coluna: str, minimo: int = 1) -> pd.DataFrame:
    """
    Agrupa por `coluna` e devolve incidentes, graves e a taxa de graves (%).

    `minimo` descarta grupos pequenos demais para a taxa significar algo.

    Exemplo:
        >>> taxa_de_gravidade(incidentes, "location_name", minimo=10)
           location_name  incidentes  graves  taxa_graves_pct
            location 1100          45      33             73.3
    """
    resumo = (
        df.assign(_grave=(df["fault_severity"] == GRAVE).astype(int))
          .groupby(coluna, observed=True)
          .agg(incidentes=("fault_severity", "size"), graves=("_grave", "sum"))
          .reset_index()
    )
    resumo["taxa_graves_pct"] = (resumo["graves"] / resumo["incidentes"] * 100).round(1)
    return resumo[resumo["incidentes"] >= minimo]
