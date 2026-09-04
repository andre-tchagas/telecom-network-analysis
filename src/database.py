"""
Banco de dados: cria o SQLite, carrega as tabelas e executa consultas.

Fluxo:
    data/processed/*.parquet  ->  database/telecom.db  ->  consultas SQL
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from src.config import DATABASE_PATH, PROCESSED_DIR, SQL_DIR, get_logger

logger = get_logger("database")

# Ordem de carga: as tabelas de nomes precisam existir antes das que
# apontam para elas, senao a FOREIGN KEY reclama.
TABELAS = [
    "locations",
    "severity_types",
    "event_types",
    "resource_types",
    "log_features",
    "incidents",
    "incident_events",
    "incident_resources",
    "incident_log_features",
]


def conectar(db_path: Path = DATABASE_PATH) -> sqlite3.Connection:
    """
    Abre a conexao com o banco.

    O PRAGMA liga a checagem de FOREIGN KEY. No SQLite ela vem DESLIGADA
    por padrao -- sem esta linha, o banco aceitaria um incidente apontando
    para uma localidade inexistente sem reclamar.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def criar_banco(db_path: Path = DATABASE_PATH) -> None:
    """Cria as tabelas vazias, executando sql/schema.sql."""
    schema = (SQL_DIR / "schema.sql").read_text(encoding="utf-8")
    with conectar(db_path) as conn:
        conn.executescript(schema)
    logger.info("Banco criado em %s", db_path)


def carregar_tabelas(db_path: Path = DATABASE_PATH,
                     processed_dir: Path = PROCESSED_DIR) -> None:
    """
    Le cada arquivo Parquet e insere no banco.

    `to_sql` do pandas faz o INSERT linha a linha por baixo dos panos.
    Usamos if_exists="append" porque as tabelas ja foram criadas pelo
    schema.sql -- queremos preencher, nao recriar (o que apagaria as
    chaves e os indices).
    """
    with conectar(db_path) as conn:
        for tabela in TABELAS:
            df = pd.read_parquet(processed_dir / f"{tabela}.parquet")
            df.to_sql(tabela, conn, if_exists="append", index=False)
            logger.info("  %-22s -> %6d linhas inseridas", tabela, len(df))


def consultar(sql: str, db_path: Path = DATABASE_PATH) -> pd.DataFrame:
    """
    Executa uma consulta SQL e devolve o resultado como DataFrame.

    E' a ponte entre os dois mundos do projeto: o SQL faz o trabalho
    pesado no banco, e o resultado volta em formato Pandas para virar
    grafico ou tabela no dashboard.
    """
    with conectar(db_path) as conn:
        return pd.read_sql_query(sql, conn)


def construir_banco(db_path: Path = DATABASE_PATH,
                    processed_dir: Path = PROCESSED_DIR) -> None:
    """Cria o banco do zero e carrega todos os dados."""
    criar_banco(db_path)
    carregar_tabelas(db_path, processed_dir)

    total = consultar("SELECT COUNT(*) AS n FROM incidents", db_path)["n"].iloc[0]
    logger.info("Banco pronto: %d incidentes carregados", total)
