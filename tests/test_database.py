"""Testes do banco: criacao, carga e consulta."""

from __future__ import annotations

import sqlite3

import pytest

from src.database import (
    build_database,
    load_named_queries,
    run_named_query,
    run_query,
)


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    """Cria um banco de verdade num diretorio temporario, uma vez por sessao."""
    path = tmp_path_factory.mktemp("db") / "teste.db"
    build_database(path)
    return path


def test_carrega_todos_os_incidentes(db):
    assert run_query("SELECT COUNT(*) AS n FROM incidents", db)["n"].iloc[0] == 7381


def test_distribuicao_da_gravidade_bate_com_o_dataset(db):
    r = run_query(
        "SELECT fault_severity, COUNT(*) AS total FROM incidents "
        "GROUP BY fault_severity ORDER BY fault_severity", db
    )
    assert r["total"].tolist() == [4784, 1871, 726]


def test_todas_as_tabelas_foram_criadas(db):
    names = run_query(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name", db
    )["name"].tolist()
    assert len(names) == 9
    assert "incidents" in names and "locations" in names


def test_banco_recusa_incidente_com_localidade_inexistente(db):
    """
    Prova que a FOREIGN KEY esta ativa. Sem o PRAGMA foreign_keys = ON,
    o SQLite aceitaria esta linha em silencio.
    """
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = ON")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO incidents VALUES (999999, 999999, 1, 0)"  # location 999999 nao existe
        )
    conn.close()


def test_banco_recusa_gravidade_invalida(db):
    """Prova que o CHECK (fault_severity IN (0,1,2)) esta funcionando."""
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = ON")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO incidents VALUES (999998, 1, 1, 7)")  # 7 nao e' valido
    conn.close()


# ---------------------------------------------------------------------------
# Consultas de analysis_queries.sql
# ---------------------------------------------------------------------------
def test_todas_as_consultas_sao_carregadas():
    assert len(load_named_queries()) == 8


def test_todas_as_consultas_executam_sem_erro(db):
    """Se uma consulta tiver erro de SQL, este teste quebra."""
    for name in load_named_queries():
        assert not run_named_query(name, db).empty, f"{name} devolveu vazio"


def test_consulta_de_gravidade_bate_com_o_esperado(db):
    r = run_named_query("gravidade_distribuicao", db)
    assert r["incidentes"].tolist() == [4784, 1871, 726]
    assert r["percentual"].tolist() == [64.82, 25.35, 9.84]


def test_localidades_criticas_respeita_o_corte_minimo(db):
    """O HAVING COUNT(*) >= 10 impede taxas de 100% com amostra minuscula."""
    r = run_named_query("localidades_criticas", db)
    assert r["incidentes"].min() >= 10


def test_evento_recurso_respeita_o_corte_minimo(db):
    """A analise de combinacoes so mostra pares presentes em 50+ incidentes."""
    r = run_named_query("evento_recurso", db)
    assert r["incidentes"].min() >= 50
    assert {"event_type_name", "resource_type_name", "taxa_graves_pct"} <= set(r.columns)


def test_consulta_inexistente_levanta_erro():
    with pytest.raises(KeyError):
        run_named_query("consulta_que_nao_existe")
