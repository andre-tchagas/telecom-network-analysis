"""
Testes da camada de limpeza.

Foco: provar que o recorte de universo e a conversão de categorias fazem
exatamente o que prometem, e que a validação detecta corrupção introduzida
pela nossa própria transformação (não pela fonte).
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.cleaning import clean_raw_data, extract_category_id, validate_clean_data
from src.data_loader import load_raw_data


# ---------------------------------------------------------------------------
# extract_category_id
# ---------------------------------------------------------------------------
def test_extrai_numero_da_categoria():
    s = pd.Series(["location 118", "location 9", "location 1126"], dtype="string")
    result = extract_category_id(s, "location")
    assert result.tolist() == [118, 9, 1126]
    assert result.dtype == "int64"


def test_prefixo_de_log_feature_e_feature_e_nao_log_feature():
    """
    Armadilha real do dataset: a coluna chama-se `log_feature`, mas os valores
    usam o prefixo "feature". Assumir o nome da coluna quebraria a conversão.
    """
    s = pd.Series(["feature 68", "feature 71"], dtype="string")
    assert extract_category_id(s, "feature").tolist() == [68, 71]
    with pytest.raises(ValueError):
        extract_category_id(s, "log_feature")


def test_rejeita_formato_invalido_em_vez_de_produzir_nan():
    """
    O ponto do teste: uma conversão ingênua com `str.extract` devolveria NaN
    silenciosamente e o incidente sumiria dos JOINs sem aviso nenhum.
    """
    s = pd.Series(["location 118", "location A"], dtype="string")
    with pytest.raises(ValueError, match="formato"):
        extract_category_id(s, "location")


def test_mensagem_de_erro_mostra_exemplos_do_problema():
    s = pd.Series(["loc 1", "location 2"], dtype="string")
    with pytest.raises(ValueError, match="loc 1"):
        extract_category_id(s, "location")


# ---------------------------------------------------------------------------
# clean_raw_data sobre o dataset real
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def clean():
    return clean_raw_data(load_raw_data())


def test_recorta_para_o_universo_rotulado(clean):
    assert len(clean["incidents"]) == 7381
    assert len(clean["incident_severity"]) == 7381


def test_satelites_ficam_restritas_aos_incidentes_rotulados(clean):
    ids = set(clean["incidents"]["incident_id"])
    for name, df in clean.items():
        assert set(df["incident_id"]) <= ids, f"{name} extrapolou o universo"


def test_recorte_reduz_as_tabelas_1_para_n(clean):
    # Valores do dataset completo (18.552 incidentes) vs universo rotulado.
    assert len(clean["incident_events"]) == 12468       # era 31.170
    assert len(clean["incident_resources"]) == 8460     # era 21.076
    assert len(clean["incident_log_features"]) == 23851  # era 58.671


def test_nao_restou_nenhuma_coluna_de_texto(clean):
    """Após a limpeza, tudo é numérico e pronto para virar chave no SQLite."""
    for name, df in clean.items():
        assert not any(str(t) == "string" for t in df.dtypes), f"{name} tem coluna textual"


def test_conteudo_bate_com_a_origem(clean):
    """A limpeza não pode alterar o valor do alvo, apenas o formato das colunas."""
    train = load_raw_data()["train"]
    assert clean["incidents"]["fault_severity"].sum() == train["fault_severity"].sum()
    expected = sorted(train["location"].str.removeprefix("location ").astype(int))
    assert sorted(clean["incidents"]["location_id"]) == expected


def test_dataset_real_passa_na_validacao(clean):
    validate_clean_data(clean)


# ---------------------------------------------------------------------------
# validate_clean_data: corrompe um aspecto de cada vez
# ---------------------------------------------------------------------------
def _minimal_clean() -> dict[str, pd.DataFrame]:
    return {
        "incidents": pd.DataFrame({
            "incident_id": [1, 2], "location_id": [10, 20], "fault_severity": [0, 2],
        }),
        "incident_severity": pd.DataFrame({"incident_id": [1, 2], "severity_type_id": [1, 2]}),
        "incident_events": pd.DataFrame({"incident_id": [1, 1, 2], "event_type_id": [11, 35, 15]}),
        "incident_resources": pd.DataFrame({"incident_id": [1, 2], "resource_type_id": [8, 2]}),
        "incident_log_features": pd.DataFrame({
            "incident_id": [1, 2], "log_feature_id": [68, 71], "volume": [6, 1],
        }),
    }


def test_conjunto_minimo_e_valido():
    validate_clean_data(_minimal_clean())


def test_detecta_incident_id_duplicado():
    c = _minimal_clean()
    c["incidents"] = pd.concat([c["incidents"], c["incidents"].iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicado"):
        validate_clean_data(c)


def test_detecta_severidade_faltando_para_um_incidente():
    c = _minimal_clean()
    c["incident_severity"] = c["incident_severity"].iloc[[0]]
    with pytest.raises(ValueError, match="1 linha por incidente"):
        validate_clean_data(c)


def test_detecta_ponte_apontando_para_incidente_inexistente():
    c = _minimal_clean()
    c["incident_events"] = pd.DataFrame({"incident_id": [1, 99], "event_type_id": [11, 35]})
    with pytest.raises(ValueError, match="inexistente"):
        validate_clean_data(c)


def test_detecta_par_duplicado_na_ponte():
    """Um par (incidente, evento) repetido inflaria qualquer contagem por evento."""
    c = _minimal_clean()
    c["incident_events"] = pd.DataFrame({"incident_id": [1, 1], "event_type_id": [11, 11]})
    with pytest.raises(ValueError, match="duplicados"):
        validate_clean_data(c)
