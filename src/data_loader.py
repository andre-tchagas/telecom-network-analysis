"""
Camada de entrada do pipeline: le os CSVs brutos e valida a integridade deles.

Principio adotado: este modulo NAO toma decisoes analiticas.
    Ele apenas le `data/raw/` como o arquivo realmente e', declara os tipos
    esperados e falha alto se o dado nao corresponder ao contrato.
    Qualquer filtro, recorte ou regra de negocio pertence a cleaning.py.

    Essa separacao existe para que uma falha possa ser localizada: se o
    pipeline quebra aqui, o problema e' o arquivo de origem; se quebra
    depois, o problema e' a nossa regra.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.config import RAW_DIR, RAW_FILES, get_logger

logger = get_logger("data_loader")

# Tipos declarados explicitamente em vez de deixar o pandas inferir.
# Motivo: inferencia e' silenciosa. Se um dia um `id` vier com valor invalido,
# o pandas transformaria a coluna inteira em `object` sem avisar, e todos os
# JOINs a jusante falhariam de forma dificil de rastrear. Declarar o tipo
# transforma esse cenario em um erro imediato e explicito.
RAW_DTYPES: dict[str, dict[str, str]] = {
    "train": {"id": "int64", "location": "string", "fault_severity": "int8"},
    "severity_type": {"id": "int64", "severity_type": "string"},
    "event_type": {"id": "int64", "event_type": "string"},
    "resource_type": {"id": "int64", "resource_type": "string"},
    "log_feature": {"id": "int64", "log_feature": "string", "volume": "int64"},
}


@dataclass(frozen=True)
class RawData:
    """
    Agrupa as cinco tabelas brutas usadas pelo pipeline.

    Por que uma dataclass em vez de um dict:
        - os nomes dos campos sao verificados pelo editor e pelo interpretador;
        - `frozen=True` impede que uma etapa posterior substitua uma tabela
          por engano, o que tornaria o pipeline nao reproduzivel;
        - fica explicito, na assinatura das funcoes, o que entra e o que sai.
    """

    train: pd.DataFrame
    severity_type: pd.DataFrame
    event_type: pd.DataFrame
    resource_type: pd.DataFrame
    log_feature: pd.DataFrame

    def as_dict(self) -> dict[str, pd.DataFrame]:
        """Util para iterar sobre todas as tabelas (validacao, logging, testes)."""
        return {
            "train": self.train,
            "severity_type": self.severity_type,
            "event_type": self.event_type,
            "resource_type": self.resource_type,
            "log_feature": self.log_feature,
        }


def load_raw_table(name: str, raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    """
    Le uma unica tabela bruta pelo nome logico (ex.: "train").

    Levanta FileNotFoundError com uma mensagem acionavel caso o dataset
    nao tenha sido baixado -- e' o erro mais provavel para quem clona o repo.
    """
    if name not in RAW_FILES:
        raise KeyError(f"Tabela desconhecida: {name!r}. Validas: {sorted(RAW_FILES)}")

    path = raw_dir / RAW_FILES[name]
    if not path.exists():
        raise FileNotFoundError(
            f"Arquivo bruto nao encontrado: {path}\n"
            f"Verifique se os CSVs do dataset estao em {raw_dir}/ "
            f"(ver secao 'Dataset' do README)."
        )

    df = pd.read_csv(path, dtype=RAW_DTYPES[name])
    logger.info("Carregado %-18s -> %6d linhas x %d colunas",
                RAW_FILES[name], len(df), df.shape[1])
    return df


def load_raw_data(raw_dir: Path = RAW_DIR) -> RawData:
    """Le as cinco tabelas usadas pelo pipeline e devolve o conjunto agrupado."""
    logger.info("Lendo dataset bruto de %s", raw_dir)
    tables = {name: load_raw_table(name, raw_dir) for name in RAW_FILES}
    return RawData(**tables)


def validate_raw_data(raw: RawData) -> None:
    """
    Verifica o contrato do dataset bruto. Levanta ValueError na primeira violacao.

    O que e' verificado e por que:
        1. Ausencia de nulos    -> a analise atual assume dado completo.
        2. `id` unico em train  -> e' a chave primaria do incidente.
        3. Integridade referencial -> todo `id` das tabelas satelite precisa
           existir em train OU em test. Como test nao e' carregado, checamos
           o caso mais forte que ainda faz sentido: nenhum id de train pode
           ficar sem correspondencia nas satelites.
        4. `volume` positivo    -> volume zero ou negativo nao tem significado.

    Isto e' uma barreira de regressao: se o dataset for substituido por uma
    versao diferente, o pipeline para aqui em vez de produzir numeros errados.
    """
    logger.info("Validando integridade do dataset bruto")

    # 1. Nulos
    for name, df in raw.as_dict().items():
        nulls = df.isna().sum()
        if nulls.any():
            offenders = nulls[nulls > 0].to_dict()
            raise ValueError(f"Valores nulos encontrados em {name!r}: {offenders}")

    # 2. Chave primaria de train
    if raw.train["id"].duplicated().any():
        n = int(raw.train["id"].duplicated().sum())
        raise ValueError(f"train.csv possui {n} id(s) duplicado(s); id deve ser unico.")

    # 2b. severity_type e' 1:1 com o incidente
    if raw.severity_type["id"].duplicated().any():
        raise ValueError("severity_type.csv deveria ter um unico registro por id.")

    # 3. Integridade referencial: todo incidente de train aparece nas satelites
    train_ids = set(raw.train["id"])
    satellites = {
        "severity_type": raw.severity_type,
        "event_type": raw.event_type,
        "resource_type": raw.resource_type,
        "log_feature": raw.log_feature,
    }
    for name, df in satellites.items():
        missing = train_ids - set(df["id"])
        if missing:
            raise ValueError(
                f"{len(missing)} incidente(s) de train sem registro em {name!r}. "
                f"Exemplos: {sorted(missing)[:5]}"
            )

    # 4. Dominio de valores
    invalid_volume = int((raw.log_feature["volume"] <= 0).sum())
    if invalid_volume:
        raise ValueError(f"log_feature.csv possui {invalid_volume} linha(s) com volume <= 0.")

    valid_targets = {0, 1, 2}
    found_targets = set(raw.train["fault_severity"].unique().tolist())
    if not found_targets <= valid_targets:
        raise ValueError(
            f"fault_severity fora do dominio esperado {valid_targets}: {found_targets}"
        )

    logger.info("Validacao concluida: %d incidentes rotulados, integridade referencial OK",
                len(train_ids))
