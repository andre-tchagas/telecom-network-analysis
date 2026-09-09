"""
Testes da regra de negocio central: taxa de gravidade.

O teste mais importante deste arquivo e' o de concordancia: a mesma pergunta,
respondida em SQL e em pandas, precisa dar o mesmo numero. Sem ele, o README
poderia dizer 14,2% enquanto o dashboard diz outra coisa.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.database import consultar, executar_consulta_nomeada
from src.metrics import taxa_de_gravidade


# ---------------------------------------------------------------------------
# Comportamento da funcao
# ---------------------------------------------------------------------------
def _exemplo() -> pd.DataFrame:
    """4 incidentes em A (1 grave = 25%) e 2 em B (2 graves = 100%)."""
    return pd.DataFrame({
        "grupo": ["A", "A", "A", "A", "B", "B"],
        "fault_severity": [0, 1, 0, 2, 2, 2],
    })


def test_calcula_a_taxa_corretamente():
    r = taxa_de_gravidade(_exemplo(), "grupo").set_index("grupo")
    assert r.loc["A", "incidentes"] == 4
    assert r.loc["A", "graves"] == 1
    assert r.loc["A", "taxa_graves_pct"] == 25.0
    assert r.loc["B", "taxa_graves_pct"] == 100.0


def test_minimo_descarta_grupos_pequenos():
    r = taxa_de_gravidade(_exemplo(), "grupo", minimo=3)
    assert r["grupo"].tolist() == ["A"]  # B tem apenas 2 incidentes


def test_apenas_fault_severity_2_conta_como_grave():
    """Gravidade 1 ('poucas falhas') nao entra na conta de graves."""
    df = pd.DataFrame({"grupo": ["A", "A"], "fault_severity": [1, 1]})
    assert taxa_de_gravidade(df, "grupo")["taxa_graves_pct"].iloc[0] == 0.0


# ---------------------------------------------------------------------------
# Concordancia entre SQL e pandas -- o teste que evita numeros divergentes
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def incidentes():
    """Mesma consulta que o dashboard usa para carregar os dados."""
    return consultar("""
        SELECT i.incident_id, l.location_name, s.severity_type_name, i.fault_severity
        FROM incidents i
        JOIN locations      l ON i.location_id      = l.location_id
        JOIN severity_types s ON i.severity_type_id = s.severity_type_id
    """)


def test_pandas_concorda_com_sql_por_tipo_de_alerta(incidentes):
    via_sql = (executar_consulta_nomeada("alerta_vs_gravidade")
               .set_index("severity_type_name")[["incidentes", "graves", "taxa_graves_pct"]]
               .sort_index())
    via_pandas = (taxa_de_gravidade(incidentes, "severity_type_name")
                  .set_index("severity_type_name")[["incidentes", "graves", "taxa_graves_pct"]]
                  .sort_index())
    pd.testing.assert_frame_equal(via_sql, via_pandas, check_dtype=False)


def test_pandas_concorda_com_sql_por_localidade(incidentes):
    """A consulta localidades_criticas usa HAVING COUNT(*) >= 10 e LIMIT 10."""
    via_sql = executar_consulta_nomeada("localidades_criticas")
    via_pandas = (taxa_de_gravidade(incidentes, "location_name", minimo=10)
                  .set_index("location_name"))

    for linha in via_sql.itertuples():
        esperado = via_pandas.loc[linha.location_name]
        assert linha.incidentes == esperado["incidentes"]
        assert linha.graves == esperado["graves"]
        assert linha.taxa_graves_pct == esperado["taxa_graves_pct"]
