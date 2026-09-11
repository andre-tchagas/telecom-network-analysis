"""
Testes da regra de negocio central: taxa de gravidade.

O teste mais importante deste arquivo e' o de concordancia: a mesma pergunta,
respondida em SQL e em pandas, precisa dar o mesmo numero. Sem ele, o README
poderia dizer 14,2% enquanto o dashboard diz outra coisa.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.database import run_named_query, run_query
from src.metrics import severity_rate_by


# ---------------------------------------------------------------------------
# Comportamento da funcao
# ---------------------------------------------------------------------------
def _example() -> pd.DataFrame:
    """4 incidentes em A (1 grave = 25%) e 2 em B (2 graves = 100%)."""
    return pd.DataFrame({
        "grupo": ["A", "A", "A", "A", "B", "B"],
        "fault_severity": [0, 1, 0, 2, 2, 2],
    })


def test_calcula_a_taxa_corretamente():
    r = severity_rate_by(_example(), "grupo").set_index("grupo")
    assert r.loc["A", "incidentes"] == 4
    assert r.loc["A", "graves"] == 1
    assert r.loc["A", "taxa_graves_pct"] == 25.0
    assert r.loc["B", "taxa_graves_pct"] == 100.0


def test_min_sample_descarta_grupos_pequenos():
    r = severity_rate_by(_example(), "grupo", min_sample=3)
    assert r["grupo"].tolist() == ["A"]  # B tem apenas 2 incidentes


def test_apenas_fault_severity_2_conta_como_grave():
    """Gravidade 1 ('poucas falhas') nao entra na conta de graves."""
    df = pd.DataFrame({"grupo": ["A", "A"], "fault_severity": [1, 1]})
    assert severity_rate_by(df, "grupo")["taxa_graves_pct"].iloc[0] == 0.0


# ---------------------------------------------------------------------------
# Concordancia entre SQL e pandas -- o teste que evita numeros divergentes
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def incidents():
    """Mesma consulta que o dashboard usa para carregar os dados."""
    return run_query("""
        SELECT i.incident_id, l.location_name, s.severity_type_name, i.fault_severity
        FROM incidents i
        JOIN locations      l ON i.location_id      = l.location_id
        JOIN severity_types s ON i.severity_type_id = s.severity_type_id
    """)


def test_pandas_concorda_com_sql_por_tipo_de_alerta(incidents):
    via_sql = (run_named_query("alerta_vs_gravidade")
               .set_index("severity_type_name")[["incidentes", "graves", "taxa_graves_pct"]]
               .sort_index())
    via_pandas = (severity_rate_by(incidents, "severity_type_name")
                  .set_index("severity_type_name")[["incidentes", "graves", "taxa_graves_pct"]]
                  .sort_index())
    pd.testing.assert_frame_equal(via_sql, via_pandas, check_dtype=False)


def test_pandas_concorda_com_sql_por_localidade(incidents):
    """A consulta localidades_criticas usa HAVING COUNT(*) >= 10 e LIMIT 10."""
    via_sql = run_named_query("localidades_criticas")
    via_pandas = (severity_rate_by(incidents, "location_name", min_sample=10)
                  .set_index("location_name"))

    for row in via_sql.itertuples():
        expected = via_pandas.loc[row.location_name]
        assert row.incidentes == expected["incidentes"]
        assert row.graves == expected["graves"]
        assert row.taxa_graves_pct == expected["taxa_graves_pct"]


def test_constante_de_exibicao_bate_com_o_banco(incidents):
    """
    BASE_SEVERITY_RATE_PCT e' um numero fixo usado como linha de referencia nos
    graficos. Este teste garante que ele continua correspondendo ao dado real:
    se o dataset mudar, o teste quebra em vez de o grafico mentir.
    """
    from src.metrics import BASE_SEVERITY_RATE_PCT, base_severity_rate

    assert round(base_severity_rate(incidents), 2) == BASE_SEVERITY_RATE_PCT
