"""
Configuracao central do projeto: caminhos, constantes de dominio e logging.

Por que este modulo existe:
    Todos os demais modulos (loader, cleaning, database, dashboard, testes)
    precisam saber onde os dados estao. Centralizar isso aqui evita repeticao
    e garante que nenhum caminho absoluto seja escrito no codigo -- os caminhos
    sao derivados da localizacao deste arquivo, entao o projeto funciona em
    qualquer maquina apos um `git clone`.
"""

from __future__ import annotations

import logging
from pathlib import Path

# ---------------------------------------------------------------------------
# Caminhos
# ---------------------------------------------------------------------------
# parents[0] = src/ ; parents[1] = raiz do projeto
PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

DATABASE_DIR = PROJECT_ROOT / "database"
DATABASE_PATH = DATABASE_DIR / "telecom.db"

SQL_DIR = PROJECT_ROOT / "sql"
REPORTS_DIR = PROJECT_ROOT / "reports"
FIGURES_DIR = REPORTS_DIR / "figures"

# ---------------------------------------------------------------------------
# Constantes de dominio
# ---------------------------------------------------------------------------
# Rotulo legivel para fault_severity. Este e' o ALVO: o desfecho do incidente.
# Fonte: descricao oficial da competicao Telstra Network Disruptions (Kaggle).
FAULT_SEVERITY_LABELS = {
    0: "Sem falha reportada",
    1: "Poucas falhas",
    2: "Muitas falhas",
}

# ATENCAO: `severity_type` NAO e' a mesma coisa que `fault_severity`.
# - fault_severity : desfecho do incidente (0/1/2). Existe apenas em train.csv.
# - severity_type  : tipo da mensagem de alerta emitida pelo log. E' um atributo
#                    de entrada, disponivel para todos os incidentes.
# Confundir os dois invalida qualquer analise. Ver LEARNING_NOTES.md.

# Arquivos brutos efetivamente usados pelo pipeline.
# test.csv e sample_submission.csv permanecem em data/raw/ (raw nunca e' alterado),
# mas nao entram na analise: test.csv nao possui fault_severity e o gabarito da
# competicao nunca foi publicado.
RAW_FILES = {
    "train": "train.csv",
    "severity_type": "severity_type.csv",
    "event_type": "event_type.csv",
    "resource_type": "resource_type.csv",
    "log_feature": "log_feature.csv",
}


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """
    Configura o logging da aplicacao e devolve o logger raiz do projeto.

    Usamos logging em vez de print() porque o pipeline precisa registrar
    etapas, avisos e erros de forma consistente -- e porque em producao
    print() nao tem nivel, nao tem timestamp e nao pode ser redirecionado.
    """
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)-22s | %(message)s",
        datefmt="%H:%M:%S",
    )
    return logging.getLogger("telecom")


def get_logger(name: str) -> logging.Logger:
    """Logger filho, para que cada modulo se identifique nas mensagens."""
    return logging.getLogger(f"telecom.{name}")
