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

# Ordem de carga: as dimensoes precisam existir antes das tabelas que apontam
# para elas, senao a FOREIGN KEY reclama.
TABLE_LOAD_ORDER = [
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


def connect(db_path: Path = DATABASE_PATH) -> sqlite3.Connection:
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


def create_schema(db_path: Path = DATABASE_PATH) -> None:
    """Cria as tabelas vazias, executando sql/schema.sql."""
    schema = (SQL_DIR / "schema.sql").read_text(encoding="utf-8")
    with connect(db_path) as conn:
        conn.executescript(schema)
    logger.info("Banco criado em %s", db_path)


def load_tables(db_path: Path = DATABASE_PATH,
                processed_dir: Path = PROCESSED_DIR) -> None:
    """
    Le cada arquivo Parquet e insere no banco.

    `to_sql` do pandas faz o INSERT por baixo dos panos. Usamos
    if_exists="append" porque as tabelas ja foram criadas pelo schema.sql --
    queremos preencher, nao recriar (o que apagaria as chaves e os indices).
    """
    with connect(db_path) as conn:
        for table in TABLE_LOAD_ORDER:
            df = pd.read_parquet(processed_dir / f"{table}.parquet")
            df.to_sql(table, conn, if_exists="append", index=False)
            logger.info("  %-22s -> %6d linhas inseridas", table, len(df))


def run_query(sql: str, db_path: Path = DATABASE_PATH) -> pd.DataFrame:
    """
    Executa uma consulta SQL e devolve o resultado como DataFrame.

    E' a ponte entre os dois mundos do projeto: o SQL faz o trabalho pesado no
    banco, e o resultado volta em Pandas para virar grafico ou tabela.
    """
    with connect(db_path) as conn:
        return pd.read_sql_query(sql, conn)


def load_named_queries() -> dict[str, str]:
    """
    Le sql/analysis_queries.sql e devolve {nome: consulta}.

    As consultas ficam no arquivo .sql em vez de coladas dentro do Python por
    dois motivos: o GitHub colore a sintaxe, e da' para testar a consulta direto
    num cliente de banco sem rodar o projeto. O corte e' feito pelos marcadores
    "-- name: xxx".
    """
    text = (SQL_DIR / "analysis_queries.sql").read_text(encoding="utf-8")
    queries: dict[str, str] = {}
    name, lines = None, []

    for line in text.splitlines():
        if line.strip().startswith("-- name:"):
            if name:
                queries[name] = "\n".join(lines).strip()
            name, lines = line.split("-- name:")[1].strip(), []
        elif name:
            lines.append(line)

    if name:
        queries[name] = "\n".join(lines).strip()
    return queries


def run_named_query(name: str, db_path: Path = DATABASE_PATH) -> pd.DataFrame:
    """Roda uma consulta de analysis_queries.sql pelo nome."""
    queries = load_named_queries()
    if name not in queries:
        raise KeyError(f"Consulta {name!r} nao existe. Disponiveis: {sorted(queries)}")
    return run_query(queries[name], db_path)


def build_database(db_path: Path = DATABASE_PATH,
                   processed_dir: Path = PROCESSED_DIR) -> None:
    """Cria o banco do zero e carrega todos os dados."""
    create_schema(db_path)
    load_tables(db_path, processed_dir)

    total = run_query("SELECT COUNT(*) AS n FROM incidents", db_path)["n"].iloc[0]
    logger.info("Banco pronto: %d incidentes carregados", total)
