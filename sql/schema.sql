-- =============================================================
-- Estrutura do banco: Telecom Network Analysis
-- =============================================================
-- CREATE TABLE = "crie uma tabela com estas colunas e estes tipos".
-- Rodamos este arquivo uma vez, antes de inserir qualquer dado.
--
-- Dois conceitos aparecem aqui:
--   PRIMARY KEY  -> coluna que identifica a linha de forma unica.
--                   O banco impede dois incidentes com o mesmo id.
--   FOREIGN KEY  -> "esta coluna aponta para outra tabela".
--                   O banco impede um incidente apontar para uma
--                   localidade que nao existe.
-- =============================================================

-- Apaga tudo antes de recriar, para o pipeline poder rodar varias vezes
-- sempre com o mesmo resultado.
DROP TABLE IF EXISTS incident_log_features;
DROP TABLE IF EXISTS incident_resources;
DROP TABLE IF EXISTS incident_events;
DROP TABLE IF EXISTS incidents;
DROP TABLE IF EXISTS log_features;
DROP TABLE IF EXISTS resource_types;
DROP TABLE IF EXISTS event_types;
DROP TABLE IF EXISTS severity_types;
DROP TABLE IF EXISTS locations;


-- -------------------------------------------------------------
-- TABELAS DE NOMES
-- Guardam o rotulo original do dataset: 118 -> "location 118".
-- -------------------------------------------------------------
CREATE TABLE locations (
    location_id   INTEGER PRIMARY KEY,
    location_name TEXT NOT NULL
);

CREATE TABLE severity_types (
    severity_type_id   INTEGER PRIMARY KEY,
    severity_type_name TEXT NOT NULL
);

CREATE TABLE event_types (
    event_type_id   INTEGER PRIMARY KEY,
    event_type_name TEXT NOT NULL
);

CREATE TABLE resource_types (
    resource_type_id   INTEGER PRIMARY KEY,
    resource_type_name TEXT NOT NULL
);

CREATE TABLE log_features (
    log_feature_id   INTEGER PRIMARY KEY,
    log_feature_name TEXT NOT NULL
);


-- -------------------------------------------------------------
-- TABELA PRINCIPAL
-- Um incidente por linha.
--
-- fault_severity e' o resultado do incidente:
--   0 = sem falha | 1 = poucas falhas | 2 = muitas falhas
-- O CHECK abaixo faz o banco recusar qualquer outro valor.
-- -------------------------------------------------------------
CREATE TABLE incidents (
    incident_id      INTEGER PRIMARY KEY,
    location_id      INTEGER NOT NULL,
    severity_type_id INTEGER NOT NULL,
    fault_severity   INTEGER NOT NULL CHECK (fault_severity IN (0, 1, 2)),

    FOREIGN KEY (location_id)      REFERENCES locations (location_id),
    FOREIGN KEY (severity_type_id) REFERENCES severity_types (severity_type_id)
);


-- -------------------------------------------------------------
-- TABELAS DE LIGACAO
-- Um incidente pode ter varios eventos, varios recursos e varias
-- features de log. Isso nao cabe em uma coluna, entao vira tabela:
-- uma linha para cada par (incidente, categoria).
-- -------------------------------------------------------------
CREATE TABLE incident_events (
    incident_id   INTEGER NOT NULL,
    event_type_id INTEGER NOT NULL,

    PRIMARY KEY (incident_id, event_type_id),
    FOREIGN KEY (incident_id)   REFERENCES incidents (incident_id),
    FOREIGN KEY (event_type_id) REFERENCES event_types (event_type_id)
);

CREATE TABLE incident_resources (
    incident_id      INTEGER NOT NULL,
    resource_type_id INTEGER NOT NULL,

    PRIMARY KEY (incident_id, resource_type_id),
    FOREIGN KEY (incident_id)      REFERENCES incidents (incident_id),
    FOREIGN KEY (resource_type_id) REFERENCES resource_types (resource_type_id)
);

CREATE TABLE incident_log_features (
    incident_id    INTEGER NOT NULL,
    log_feature_id INTEGER NOT NULL,
    volume         INTEGER NOT NULL,

    PRIMARY KEY (incident_id, log_feature_id),
    FOREIGN KEY (incident_id)    REFERENCES incidents (incident_id),
    FOREIGN KEY (log_feature_id) REFERENCES log_features (log_feature_id)
);


-- -------------------------------------------------------------
-- INDICES
-- Um indice e' como o indice remissivo de um livro: acelera a busca
-- por uma coluna. Criamos nas colunas mais usadas em JOIN e filtro.
-- Com 7.381 linhas a diferenca e' pequena, mas e' a pratica correta.
-- -------------------------------------------------------------
CREATE INDEX idx_incidents_location ON incidents (location_id);
CREATE INDEX idx_incidents_severity ON incidents (fault_severity);
CREATE INDEX idx_events_type        ON incident_events (event_type_id);
CREATE INDEX idx_resources_type     ON incident_resources (resource_type_id);
