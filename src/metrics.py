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

Nota sobre idioma: as FUNCOES estao em ingles (padrao de mercado), mas as
COLUNAS de dados que elas produzem ("incidentes", "graves", "taxa_graves_pct")
seguem os nomes definidos no SQL, em portugues -- o codigo e' ingles, o dado e'
portugues.
"""

from __future__ import annotations

import pandas as pd

# Abaixo deste numero de incidentes a taxa e' pouco confiavel: com poucos casos
# ela so consegue dar valores extremos (com 4 incidentes, os unicos resultados
# possiveis sao 0%, 25%, 50%, 75% e 100%).
RELIABLE_MIN_SAMPLE = 50

SEVERE = 2  # valor de fault_severity que representa "muitas falhas"

# Percentual de incidentes graves no dataset completo. Serve de linha de
# referencia nos graficos: acima dela, o grupo esta pior que a media.
# O valor mora aqui e tests/test_metrics.py confere que continua batendo com o
# banco -- se o dataset mudar, o teste quebra em vez de o grafico mentir.
BASE_SEVERITY_RATE_PCT = 9.84


def base_severity_rate(df: pd.DataFrame) -> float:
    """
    Percentual exato de incidentes graves em `df`, SEM arredondar.

    Use este valor para calculo (comparacoes, deltas) e BASE_SEVERITY_RATE_PCT
    para exibicao. Arredondar antes de comparar produz resultados como "-0,00".
    """
    return (df["fault_severity"] == SEVERE).mean() * 100


def severity_rate_by(df: pd.DataFrame, column: str, min_sample: int = 1) -> pd.DataFrame:
    """
    Agrupa por `column` e devolve incidentes, graves e a taxa de graves (%).

    `min_sample` descarta grupos pequenos demais para a taxa significar algo.

    Exemplo:
        >>> severity_rate_by(incidents, "location_name", min_sample=10)
           location_name  incidentes  graves  taxa_graves_pct
            location 1100          45      33             73.3
    """
    summary = (
        df.assign(_severe=(df["fault_severity"] == SEVERE).astype(int))
          .groupby(column, observed=True)
          .agg(incidentes=("fault_severity", "size"), graves=("_severe", "sum"))
          .reset_index()
    )
    summary["taxa_graves_pct"] = (summary["graves"] / summary["incidentes"] * 100).round(1)
    return summary[summary["incidentes"] >= min_sample]
