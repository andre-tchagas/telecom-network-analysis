"""Testes do banco: criacao, carga e consulta."""

from __future__ import annotations

import sqlite3

import pytest

from src.database import construir_banco, consultar


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    """Cria um banco de verdade num diretorio temporario, uma vez por sessao."""
    caminho = tmp_path_factory.mktemp("db") / "teste.db"
    construir_banco(caminho)
    return caminho


def test_carrega_todos_os_incidentes(db):
    assert consultar("SELECT COUNT(*) AS n FROM incidents", db)["n"].iloc[0] == 7381


def test_distribuicao_da_gravidade_bate_com_o_dataset(db):
    r = consultar(
        "SELECT fault_severity, COUNT(*) AS total FROM incidents "
        "GROUP BY fault_severity ORDER BY fault_severity", db
    )
    assert r["total"].tolist() == [4784, 1871, 726]


def test_todas_as_tabelas_foram_criadas(db):
    nomes = consultar(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name", db
    )["name"].tolist()
    assert len(nomes) == 9
    assert "incidents" in nomes and "locations" in nomes


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
