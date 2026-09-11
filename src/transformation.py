"""
Camada de transformação: monta o modelo dimensional que será carregado no SQLite.

Modelo adotado: **star schema** (esquema estrela) leve.

    Uma tabela FATO no centro -- `incidents`, um registro por incidente --
    cercada por tabelas DIMENSÃO que descrevem cada atributo categórico.
    Como três relações são 1:N (um incidente tem vários eventos, recursos e
    features de log), elas passam por tabelas-PONTE.

                        locations        severity_types
                             \\                /
        event_types --- [incident_events] --- INCIDENTS --- [incident_resources] --- resource_types
                                                  |
                                        [incident_log_features]
                                                  |
                                             log_features

O modelo trafega como um `dict[str, pd.DataFrame]`. A ORDEM das chaves importa:
dimensões antes do fato, fato antes das pontes -- é a ordem em que o SQLite
precisa receber os INSERTs para que as chaves estrangeiras já tenham alvo.
Dicionários preservam a ordem de inserção, então construir o dict na ordem certa
basta.

Por que dimensões, se elas são finas?
    As categorias do dataset são anonimizadas ("location 118"), então as
    dimensões carregam apenas id e rótulo. Elas ainda assim se justificam:
    servem de alvo para as chaves estrangeiras, e com `PRAGMA foreign_keys=ON`
    o SQLite passa a **rejeitar** um incidente que referencie uma categoria
    inexistente. O domínio válido deixa de ser convenção e vira restrição.

Por que NÃO pré-calcular agregados no fato:
    Volume total de log, número de eventos e número de recursos por incidente
    são deriváveis por JOIN + GROUP BY. Guardá-los como coluna criaria dado
    redundante que pode dessincronizar das pontes. Com 7.381 incidentes, o
    custo de recalcular é irrelevante.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.config import PROCESSED_DIR, get_logger

logger = get_logger("transformation")


def _build_dimension(ids: pd.Series, id_col: str, name_col: str, prefix: str) -> pd.DataFrame:
    """
    Monta uma dimensão a partir dos valores que realmente ocorrem no universo.

    O rótulo original é reconstruído ("location " + 118 -> "location 118") para
    que nada da fonte se perca: relatórios e o dashboard podem exibir o texto
    como ele aparece no dataset da Telstra.
    """
    unique_ids = pd.Series(sorted(ids.unique()), dtype="int64")
    return pd.DataFrame({
        id_col: unique_ids,
        name_col: (prefix + " " + unique_ids.astype("string")).astype("string"),
    })


def build_star_schema(clean: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """
    Converte o dado limpo no modelo dimensional (9 tabelas).

    Devolve o dict já na ordem de carga: 5 dimensões, o fato, 3 pontes.
    """
    logger.info("Montando star schema")

    # --- FATO ----------------------------------------------------------------
    # `severity_type` é 1:1 com o incidente, então pertence ao fato, não a uma
    # ponte. Uma ponte com exatamente uma linha por incidente seria um JOIN a
    # mais sem nenhum ganho de expressividade.
    incidents = clean["incidents"].merge(
        clean["incident_severity"], on="incident_id", validate="one_to_one"
    )[["incident_id", "location_id", "severity_type_id", "fault_severity"]]

    # --- DIMENSÕES -----------------------------------------------------------
    locations = _build_dimension(
        incidents["location_id"], "location_id", "location_name", "location")
    severity_types = _build_dimension(
        incidents["severity_type_id"], "severity_type_id", "severity_type_name", "severity_type")
    event_types = _build_dimension(
        clean["incident_events"]["event_type_id"], "event_type_id", "event_type_name", "event_type")
    resource_types = _build_dimension(
        clean["incident_resources"]["resource_type_id"], "resource_type_id",
        "resource_type_name", "resource_type")
    log_features = _build_dimension(
        clean["incident_log_features"]["log_feature_id"], "log_feature_id",
        "log_feature_name", "feature")

    # Ordem de carga garantida pela ordem de inserção no dict.
    star = {
        "locations": locations,
        "severity_types": severity_types,
        "event_types": event_types,
        "resource_types": resource_types,
        "log_features": log_features,
        "incidents": incidents,
        "incident_events": clean["incident_events"],
        "incident_resources": clean["incident_resources"],
        "incident_log_features": clean["incident_log_features"],
    }

    for name, df in star.items():
        logger.info("  %-22s -> %6d linhas x %d colunas", name, len(df), df.shape[1])

    return star


def validate_star_schema(star: dict[str, pd.DataFrame]) -> None:
    """
    Verifica a integridade referencial do modelo ANTES da carga no banco.

    O SQLite também vai checar isso via FOREIGN KEY, mas falhar aqui produz uma
    mensagem apontando a tabela e a quantidade de órfãos, em vez de um
    `IntegrityError` genérico no meio de um INSERT em lote.
    """
    references = [
        ("incidents.location_id", star["incidents"]["location_id"],
         star["locations"]["location_id"]),
        ("incidents.severity_type_id", star["incidents"]["severity_type_id"],
         star["severity_types"]["severity_type_id"]),
        ("incident_events.event_type_id", star["incident_events"]["event_type_id"],
         star["event_types"]["event_type_id"]),
        ("incident_resources.resource_type_id", star["incident_resources"]["resource_type_id"],
         star["resource_types"]["resource_type_id"]),
        ("incident_log_features.log_feature_id", star["incident_log_features"]["log_feature_id"],
         star["log_features"]["log_feature_id"]),
    ]
    for label, child, parent in references:
        orphans = set(child) - set(parent)
        if orphans:
            raise ValueError(
                f"{label} referencia {len(orphans)} valor(es) fora da dimensão. "
                f"Exemplos: {sorted(orphans)[:5]}"
            )

    ids = set(star["incidents"]["incident_id"])
    for name in ("incident_events", "incident_resources", "incident_log_features"):
        orphans = set(star[name]["incident_id"]) - ids
        if orphans:
            raise ValueError(f"{name} referencia {len(orphans)} incidente(s) inexistente(s).")

    logger.info("Integridade do star schema OK: %d incidentes, 5 dimensões, 3 pontes", len(ids))


def save_processed(star: dict[str, pd.DataFrame], output_dir: Path = PROCESSED_DIR) -> None:
    """
    Grava o modelo dimensional em Parquet.

    Por que Parquet e não CSV:
        - preserva os tipos. Um `int8` volta como `int8`; em CSV, todo número
          é texto e vira `int64` na releitura, exigindo redeclarar o schema;
        - é colunar e comprimido, ocupando uma fração do espaço.

        O custo é não ser legível em editor de texto -- aceitável aqui porque
        `data/processed/` é artefato intermediário, gerado e descartável. A
        fonte inspecionável à mão continua sendo `data/raw/`.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    total = 0
    for name, df in star.items():
        path = output_dir / f"{name}.parquet"
        df.to_parquet(path, index=False)
        total += path.stat().st_size
    logger.info("Gravadas %d tabelas em %s (%.1f KB no total)",
                len(star), output_dir, total / 1024)
