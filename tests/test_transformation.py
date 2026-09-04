"""
Testes da camada de transformação (star schema + persistência em Parquet).
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.cleaning import CleanData, clean_raw_data
from src.data_loader import load_raw_data
from src.transformation import (
    StarSchema,
    build_star_schema,
    save_processed,
    validate_star_schema,
)


@pytest.fixture(scope="module")
def star():
    return build_star_schema(clean_raw_data(load_raw_data()))


# ---------------------------------------------------------------------------
# Estrutura do modelo dimensional
# ---------------------------------------------------------------------------
def test_modelo_tem_nove_tabelas(star):
    assert len(star.as_dict()) == 9


def test_dimensoes_contem_apenas_valores_observados(star):
    """
    As dimensões são construídas a partir do que ocorre no universo rotulado.
    Os ids não são densos: `location` vai até 1126, mas só 929 existem aqui.
    """
    assert len(star.locations) == 929
    assert len(star.severity_types) == 5
    assert len(star.event_types) == 49
    assert len(star.resource_types) == 10
    assert len(star.log_features) == 331


def test_fato_tem_uma_linha_por_incidente(star):
    assert len(star.incidents) == 7381
    assert not star.incidents["incident_id"].duplicated().any()


def test_severity_type_fica_no_fato_e_nao_em_uma_ponte(star):
    """
    `severity_type` é 1:1 com o incidente. Uma ponte com exatamente uma linha
    por incidente seria um JOIN a mais sem ganho de expressividade.
    """
    assert list(star.incidents.columns) == [
        "incident_id", "location_id", "severity_type_id", "fault_severity",
    ]


def test_dimensao_preserva_o_rotulo_original(star):
    """Nada da fonte se perde: o texto da Telstra é reconstruível."""
    loc = star.locations.set_index("location_id")["location_name"]
    assert loc.loc[118] == "location 118"
    feat = star.log_features.set_index("log_feature_id")["log_feature_name"]
    assert feat.loc[68] == "feature 68"  # prefixo "feature", não "log_feature"


def test_ordem_das_tabelas_respeita_as_chaves_estrangeiras(star):
    """
    O SQLite verifica FK no momento do INSERT, então as dimensões precisam
    ser carregadas antes do fato, e o fato antes das pontes.
    """
    ordem = list(star.as_dict())
    assert ordem.index("locations") < ordem.index("incidents")
    assert ordem.index("severity_types") < ordem.index("incidents")
    assert ordem.index("incidents") < ordem.index("incident_events")
    assert ordem.index("event_types") < ordem.index("incident_events")


def test_dataset_real_passa_na_validacao(star):
    validate_star_schema(star)


# ---------------------------------------------------------------------------
# validate_star_schema
# ---------------------------------------------------------------------------
def _star_minimo() -> StarSchema:
    clean = CleanData(
        incidents=pd.DataFrame({
            "incident_id": [1, 2], "location_id": [10, 20], "fault_severity": [0, 2],
        }),
        incident_severity=pd.DataFrame({"incident_id": [1, 2], "severity_type_id": [1, 2]}),
        incident_events=pd.DataFrame({"incident_id": [1, 2], "event_type_id": [11, 35]}),
        incident_resources=pd.DataFrame({"incident_id": [1, 2], "resource_type_id": [8, 2]}),
        incident_log_features=pd.DataFrame({
            "incident_id": [1, 2], "log_feature_id": [68, 71], "volume": [6, 1],
        }),
    )
    return build_star_schema(clean)


def test_star_minimo_e_valido():
    validate_star_schema(_star_minimo())


def test_detecta_fk_apontando_para_fora_da_dimensao():
    s = _star_minimo()
    # location 99 não existe na dimensão locations (que só tem 10 e 20)
    incidents = s.incidents.assign(location_id=[10, 99])
    quebrado = StarSchema(**{**s.as_dict(), "incidents": incidents})
    with pytest.raises(ValueError, match="fora da dimensão"):
        validate_star_schema(quebrado)


def test_detecta_ponte_com_incidente_inexistente():
    s = _star_minimo()
    ev = pd.DataFrame({"incident_id": [1, 99], "event_type_id": [11, 35]})
    quebrado = StarSchema(**{**s.as_dict(), "incident_events": ev})
    with pytest.raises(ValueError, match="inexistente"):
        validate_star_schema(quebrado)


# ---------------------------------------------------------------------------
# Persistência em Parquet
# ---------------------------------------------------------------------------
def test_parquet_preserva_os_tipos(star, tmp_path):
    """
    O motivo de escolher Parquet em vez de CSV: em CSV, `int8` volta como
    `int64` e o schema precisa ser redeclarado a cada leitura.
    """
    save_processed(star, tmp_path)

    incidents = pd.read_parquet(tmp_path / "incidents.parquet")
    assert incidents["fault_severity"].dtype == "int8"
    assert incidents["incident_id"].dtype == "int64"

    locations = pd.read_parquet(tmp_path / "locations.parquet")
    assert locations["location_name"].dtype == "string"


def test_grava_uma_tabela_por_arquivo(star, tmp_path):
    save_processed(star, tmp_path)
    arquivos = {p.stem for p in tmp_path.glob("*.parquet")}
    assert arquivos == set(star.as_dict())


def test_ida_e_volta_nao_altera_o_conteudo(star, tmp_path):
    save_processed(star, tmp_path)
    volta = pd.read_parquet(tmp_path / "incidents.parquet")
    pd.testing.assert_frame_equal(volta, star.incidents.reset_index(drop=True))
