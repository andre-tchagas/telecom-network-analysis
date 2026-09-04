"""
Camada de limpeza: aplica as regras de negócio sobre o dado bruto.

Enquanto `data_loader.py` apenas lê e valida o arquivo como ele é, este módulo
toma as **decisões analíticas** do projeto:

    1. recortar o universo para os 7.381 incidentes rotulados;
    2. converter as categorias de texto ("location 118") para inteiro (118).

Nota de honestidade
-------------------
Este módulo é pequeno de propósito. O dataset Telstra chega sem valores
ausentes, sem duplicatas e sem inconsistências de tipo -- verificado no
Checkpoint 2. Escrever tratamento de nulos onde não há nulos produziria código
que nunca executa e daria a falsa impressão de um pipeline mais robusto do que
ele é. A limpeza real deste dataset é a conversão de tipos e o recorte de
universo, e é exatamente isso que está aqui.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.config import get_logger
from src.data_loader import RawData

logger = get_logger("cleaning")

# Prefixo textual de cada coluna categórica, confirmado no dado real.
# Atenção: a coluna se chama `log_feature`, mas os valores usam o prefixo
# "feature" -- assumir o nome da coluna aqui produziria erro silencioso.
CATEGORY_PREFIXES = {
    "location": "location",
    "severity_type": "severity_type",
    "event_type": "event_type",
    "resource_type": "resource_type",
    "log_feature": "feature",
}


@dataclass(frozen=True)
class CleanData:
    """
    Dataset recortado no universo rotulado, com categorias já numéricas.

    Todas as tabelas usam `incident_id` como chave, e os identificadores de
    categoria são inteiros -- prontos para virar chave estrangeira no SQLite.
    """

    incidents: pd.DataFrame      # incident_id, location_id, fault_severity
    incident_severity: pd.DataFrame   # incident_id, severity_type_id
    incident_events: pd.DataFrame     # incident_id, event_type_id
    incident_resources: pd.DataFrame  # incident_id, resource_type_id
    incident_log_features: pd.DataFrame  # incident_id, log_feature_id, volume

    def as_dict(self) -> dict[str, pd.DataFrame]:
        return {
            "incidents": self.incidents,
            "incident_severity": self.incident_severity,
            "incident_events": self.incident_events,
            "incident_resources": self.incident_resources,
            "incident_log_features": self.incident_log_features,
        }


def extract_category_id(series: pd.Series, prefix: str) -> pd.Series:
    """
    Converte uma coluna categórica textual em inteiro.

        "location 118"  ->  118
        "feature 68"    ->  68

    Por que converter:
        O valor útil já é o número; o prefixo é constante e se repete em todas
        as linhas. Guardar 7.381 cópias da palavra "location" custa memória e
        espaço em disco, e impede ordenação correta -- em texto, "location 9"
        vem depois de "location 100".

    Por que validar o formato antes:
        Se uma linha viesse como "location A" ou "loc 118", a conversão
        produziria NaN silenciosamente e o incidente sumiria dos JOINs sem
        nenhum aviso. A validação transforma esse caso em erro imediato.
    """
    padrao = rf"^{prefix} \d+$"
    invalidas = ~series.str.fullmatch(padrao)
    if invalidas.any():
        exemplos = series[invalidas].unique()[:5].tolist()
        raise ValueError(
            f"{int(invalidas.sum())} valor(es) fora do formato '{prefix} <numero>'. "
            f"Exemplos: {exemplos}"
        )
    return series.str.removeprefix(f"{prefix} ").astype("int64")


def clean_raw_data(raw: RawData) -> CleanData:
    """
    Aplica o recorte de universo e a conversão de categorias.

    Recorte: apenas os 7.381 incidentes de `train.csv`.
        `fault_severity` -- a variável que o projeto se propõe a explicar --
        existe somente ali. Os 11.171 incidentes de `test.csv` eram o conjunto
        oculto de avaliação da competição Kaggle e nunca tiveram o gabarito
        publicado, portanto não respondem nenhuma das perguntas de negócio.
    """
    train_ids = set(raw.train["id"])
    logger.info("Recortando universo para os %d incidentes rotulados", len(train_ids))

    # --- Fato: um registro por incidente -------------------------------------
    incidents = pd.DataFrame({
        "incident_id": raw.train["id"],
        "location_id": extract_category_id(raw.train["location"], CATEGORY_PREFIXES["location"]),
        "fault_severity": raw.train["fault_severity"],
    })

    # --- Severidade do alerta: 1:1 com o incidente ---------------------------
    sev = raw.severity_type[raw.severity_type["id"].isin(train_ids)]
    incident_severity = pd.DataFrame({
        "incident_id": sev["id"].to_numpy(),
        "severity_type_id": extract_category_id(
            sev["severity_type"], CATEGORY_PREFIXES["severity_type"]
        ).to_numpy(),
    })

    # --- Relações 1:N --------------------------------------------------------
    ev = raw.event_type[raw.event_type["id"].isin(train_ids)]
    incident_events = pd.DataFrame({
        "incident_id": ev["id"].to_numpy(),
        "event_type_id": extract_category_id(
            ev["event_type"], CATEGORY_PREFIXES["event_type"]
        ).to_numpy(),
    })

    res = raw.resource_type[raw.resource_type["id"].isin(train_ids)]
    incident_resources = pd.DataFrame({
        "incident_id": res["id"].to_numpy(),
        "resource_type_id": extract_category_id(
            res["resource_type"], CATEGORY_PREFIXES["resource_type"]
        ).to_numpy(),
    })

    log = raw.log_feature[raw.log_feature["id"].isin(train_ids)]
    incident_log_features = pd.DataFrame({
        "incident_id": log["id"].to_numpy(),
        "log_feature_id": extract_category_id(
            log["log_feature"], CATEGORY_PREFIXES["log_feature"]
        ).to_numpy(),
        "volume": log["volume"].to_numpy(),
    })

    clean = CleanData(
        incidents=incidents.reset_index(drop=True),
        incident_severity=incident_severity,
        incident_events=incident_events,
        incident_resources=incident_resources,
        incident_log_features=incident_log_features,
    )

    for nome, df in clean.as_dict().items():
        logger.info("  %-22s -> %6d linhas", nome, len(df))

    return clean


def validate_clean_data(clean: CleanData) -> None:
    """
    Verifica que a limpeza não corrompeu nem perdeu dado.

    Diferente da validação do loader -- que checa o *arquivo de origem* --,
    esta checa o *resultado da nossa transformação*. É a diferença entre
    "o dado que recebi está íntegro?" e "eu estraguei o dado?".
    """
    n_incidentes = len(clean.incidents)

    if clean.incidents["incident_id"].duplicated().any():
        raise ValueError("incidents possui incident_id duplicado.")

    if len(clean.incident_severity) != n_incidentes:
        raise ValueError(
            f"incident_severity deveria ter 1 linha por incidente "
            f"({n_incidentes}), tem {len(clean.incident_severity)}."
        )

    ids = set(clean.incidents["incident_id"])
    pontes = {
        "incident_events": clean.incident_events,
        "incident_resources": clean.incident_resources,
        "incident_log_features": clean.incident_log_features,
    }
    for nome, df in pontes.items():
        orfaos = set(df["incident_id"]) - ids
        if orfaos:
            raise ValueError(f"{nome} referencia {len(orfaos)} incidente(s) inexistente(s).")
        # As pontes existem para representar relações N:N; um par repetido
        # significaria dado duplicado e inflaria qualquer contagem.
        chave = [c for c in df.columns if c != "volume"]
        if df.duplicated(subset=chave).any():
            raise ValueError(f"{nome} possui pares {chave} duplicados.")

    for nome, df in clean.as_dict().items():
        if df.isna().any().any():
            raise ValueError(f"{nome} contém valores nulos após a limpeza.")

    logger.info("Validação da limpeza OK: %d incidentes, sem órfãos e sem duplicatas",
                n_incidentes)
