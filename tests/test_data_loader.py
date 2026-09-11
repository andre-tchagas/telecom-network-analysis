"""
Testes da camada de carga.

Estrategia: os testes de leitura usam o dataset real (ele esta versionado no
repositorio, entao sempre existe). Ja os testes de validacao usam DataFrames
minimos construidos na hora -- porque para provar que o validador detecta um
dado corrompido, e' preciso corromper o dado de proposito, e nunca queremos
fazer isso no arquivo original.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.data_loader import load_raw_data, load_raw_table, validate_raw_data


# ---------------------------------------------------------------------------
# Leitura do dataset real
# ---------------------------------------------------------------------------
def test_carrega_todas_as_tabelas():
    raw = load_raw_data()
    assert set(raw) == {
        "train", "severity_type", "event_type", "resource_type", "log_feature"
    }


def test_train_tem_o_numero_esperado_de_incidentes():
    # 7.381 e' o total de incidentes rotulados do Telstra Network Disruptions.
    # Se este numero mudar, o dataset foi trocado e as conclusoes do README
    # deixam de valer -- por isso o valor esta fixado no teste.
    assert len(load_raw_table("train")) == 7381


def test_tipos_sao_declarados_e_nao_inferidos():
    train = load_raw_table("train")
    assert train["id"].dtype == "int64"
    assert train["fault_severity"].dtype == "int8"
    assert train["location"].dtype == "string"


def test_tabela_desconhecida_levanta_erro():
    with pytest.raises(KeyError):
        load_raw_table("tabela_que_nao_existe")


def test_dataset_real_passa_na_validacao():
    validate_raw_data(load_raw_data())


# ---------------------------------------------------------------------------
# Validacao: cada teste corrompe UMA coisa e exige que o validador reclame
# ---------------------------------------------------------------------------
def _minimal_raw() -> dict[str, pd.DataFrame]:
    """Conjunto valido minimo: 2 incidentes com todas as satelites preenchidas."""
    return {
        "train": pd.DataFrame({
            "id": pd.Series([1, 2], dtype="int64"),
            "location": pd.Series(["location 1", "location 2"], dtype="string"),
            "fault_severity": pd.Series([0, 2], dtype="int8"),
        }),
        "severity_type": pd.DataFrame({
            "id": pd.Series([1, 2], dtype="int64"),
            "severity_type": pd.Series(["severity_type 1", "severity_type 2"], dtype="string"),
        }),
        "event_type": pd.DataFrame({
            "id": pd.Series([1, 2], dtype="int64"),
            "event_type": pd.Series(["event_type 11", "event_type 35"], dtype="string"),
        }),
        "resource_type": pd.DataFrame({
            "id": pd.Series([1, 2], dtype="int64"),
            "resource_type": pd.Series(["resource_type 8", "resource_type 2"], dtype="string"),
        }),
        "log_feature": pd.DataFrame({
            "id": pd.Series([1, 2], dtype="int64"),
            "log_feature": pd.Series(["feature 68", "feature 71"], dtype="string"),
            "volume": pd.Series([6, 1], dtype="int64"),
        }),
    }


def test_conjunto_minimo_e_valido():
    validate_raw_data(_minimal_raw())


def test_detecta_id_duplicado_em_train():
    raw = _minimal_raw()
    raw["train"] = pd.concat([raw["train"], raw["train"].iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicado"):
        validate_raw_data(raw)


def test_detecta_incidente_orfao():
    """Um incidente de train sem registro em event_type deve quebrar o pipeline."""
    raw = _minimal_raw()
    raw["event_type"] = raw["event_type"][raw["event_type"]["id"] != 2]
    with pytest.raises(ValueError, match="event_type"):
        validate_raw_data(raw)


def test_detecta_volume_invalido():
    raw = _minimal_raw()
    raw["log_feature"] = raw["log_feature"].assign(volume=pd.Series([6, 0], dtype="int64"))
    with pytest.raises(ValueError, match="volume"):
        validate_raw_data(raw)


def test_detecta_fault_severity_fora_do_dominio():
    raw = _minimal_raw()
    raw["train"] = raw["train"].assign(fault_severity=pd.Series([0, 7], dtype="int8"))
    with pytest.raises(ValueError, match="fault_severity"):
        validate_raw_data(raw)


def test_detecta_valor_nulo():
    raw = _minimal_raw()
    raw["train"] = raw["train"].assign(location=pd.Series(["location 1", None], dtype="string"))
    with pytest.raises(ValueError, match="[Nn]ulos"):
        validate_raw_data(raw)
