"""
Ponto de entrada unico do pipeline.

Executa as etapas na ordem em que dependem umas das outras:

    data/raw  ->  carga  ->  validacao  ->  [limpeza]  ->  [transformacao]
              ->  [SQLite]  ->  [analise]  ->  [visualizacao]

As etapas entre colchetes serao adicionadas nos proximos checkpoints.
Manter um unico ponto de entrada e' o que torna o projeto reproduzivel:
quem clona o repositorio roda `python run_pipeline.py` e obtem o mesmo
resultado, sem precisar executar celulas de notebook em ordem.

Uso:
    python run_pipeline.py
"""

from __future__ import annotations

import sys

from src.config import setup_logging
from src.data_loader import load_raw_data, validate_raw_data


def main() -> int:
    logger = setup_logging()
    logger.info("=== Inicio do pipeline: Telecom Network Analysis ===")

    try:
        # Etapa 1 -- Carga do dataset bruto
        raw = load_raw_data()

        # Etapa 2 -- Validacao do contrato dos dados
        validate_raw_data(raw)

    except (FileNotFoundError, ValueError) as exc:
        # Erros esperados e acionaveis: reportamos de forma limpa, sem traceback.
        logger.error("Pipeline interrompido: %s", exc)
        return 1

    logger.info("=== Pipeline concluido com sucesso ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
