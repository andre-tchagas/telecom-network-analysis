-- =============================================================
-- Consultas de analise: Telecom Network Analysis
-- =============================================================
-- Cada consulta responde UMA pergunta de negocio.
-- O marcador "-- name: xxx" permite o Python buscar a consulta pelo
-- nome, sem precisar copiar SQL para dentro do codigo.
--
-- Lembrete importante do dataset:
--   fault_severity = resultado do incidente (0 sem falha, 1 poucas, 2 muitas)
--   severity_type  = tipo do alerta do log. NAO e' gravidade.
-- =============================================================


-- name: gravidade_distribuicao
-- Pergunta: como os incidentes se distribuem por gravidade?
-- Conceitos: GROUP BY (faz pilhas), COUNT (conta cada pilha).
SELECT
    i.fault_severity,
    COUNT(*) AS incidentes,
    ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM incidents), 2) AS percentual
FROM incidents AS i
GROUP BY i.fault_severity
ORDER BY i.fault_severity;


-- name: top_localidades_volume
-- Pergunta: quais localidades tem mais incidentes no total?
-- Conceitos: JOIN (busca o nome na outra tabela), ORDER BY, LIMIT.
SELECT
    l.location_name,
    COUNT(*) AS incidentes
FROM incidents AS i
JOIN locations AS l ON i.location_id = l.location_id
GROUP BY l.location_name
ORDER BY incidentes DESC
LIMIT 10;


-- name: localidades_criticas
-- Pergunta: quais localidades tem a maior TAXA de incidentes graves?
--
-- Por que taxa e nao contagem: uma localidade grande gera muitos
-- incidentes de tudo, inclusive graves, sem que a rede ali seja pior.
--
-- Por que o HAVING COUNT(*) >= 10: com poucos incidentes a taxa so
-- consegue dar valores extremos. Uma localidade com 1 incidente grave
-- em 1 incidente total marca 100% sem significar nada.
--
-- Conceitos:
--   CASE WHEN -> conta so as linhas que atendem a condicao
--   HAVING    -> filtra DEPOIS de agrupar (WHERE filtra antes)
SELECT
    l.location_name,
    COUNT(*) AS incidentes,
    SUM(CASE WHEN i.fault_severity = 2 THEN 1 ELSE 0 END) AS graves,
    ROUND(100.0 * SUM(CASE WHEN i.fault_severity = 2 THEN 1 ELSE 0 END)
          / COUNT(*), 1) AS taxa_graves_pct
FROM incidents AS i
JOIN locations AS l ON i.location_id = l.location_id
GROUP BY l.location_name
HAVING COUNT(*) >= 10
ORDER BY taxa_graves_pct DESC
LIMIT 10;


-- name: eventos
-- Pergunta: quais tipos de evento sao mais frequentes, e quais estao
-- associados a mais gravidade?
-- Duas respostas numa consulta so: frequencia e taxa lado a lado.
SELECT
    e.event_type_name,
    COUNT(*) AS incidentes,
    ROUND(100.0 * SUM(CASE WHEN i.fault_severity = 2 THEN 1 ELSE 0 END)
          / COUNT(*), 1) AS taxa_graves_pct
FROM incident_events AS ie
JOIN incidents   AS i ON ie.incident_id   = i.incident_id
JOIN event_types AS e ON ie.event_type_id = e.event_type_id
GROUP BY e.event_type_name
HAVING COUNT(*) >= 50
ORDER BY incidentes DESC
LIMIT 10;


-- name: recursos
-- Pergunta: quais recursos aparecem em mais incidentes, e quais
-- concentram gravidade?
-- Sao apenas 10 categorias, entao mostramos todas (sem LIMIT).
SELECT
    r.resource_type_name,
    COUNT(*) AS incidentes,
    ROUND(100.0 * SUM(CASE WHEN i.fault_severity = 2 THEN 1 ELSE 0 END)
          / COUNT(*), 1) AS taxa_graves_pct
FROM incident_resources AS ir
JOIN incidents      AS i ON ir.incident_id      = i.incident_id
JOIN resource_types AS r ON ir.resource_type_id = r.resource_type_id
GROUP BY r.resource_type_name
ORDER BY incidentes DESC;


-- name: alerta_vs_gravidade
-- Pergunta: o tipo de alerta do log (severity_type) tem relacao com a
-- gravidade real do incidente?
-- Este e' o achado mais forte da exploracao.
SELECT
    s.severity_type_name,
    COUNT(*) AS incidentes,
    SUM(CASE WHEN i.fault_severity = 2 THEN 1 ELSE 0 END) AS graves,
    ROUND(100.0 * SUM(CASE WHEN i.fault_severity = 2 THEN 1 ELSE 0 END)
          / COUNT(*), 1) AS taxa_graves_pct
FROM incidents      AS i
JOIN severity_types AS s ON i.severity_type_id = s.severity_type_id
GROUP BY s.severity_type_name
ORDER BY incidentes DESC;


-- name: volume_log_vs_gravidade
-- Pergunta: incidentes com mais volume de log sao mais graves?
--
-- Precisa de duas etapas: primeiro somar o volume de cada incidente,
-- depois comparar por gravidade.
--
-- Conceito: WITH cria uma tabela temporaria que so existe durante esta
-- consulta. Deixa o SQL legivel de cima para baixo, em vez de aninhar
-- uma consulta dentro da outra.
WITH volume_por_incidente AS (
    SELECT
        i.incident_id,
        i.fault_severity,
        SUM(lf.volume) AS volume_total,
        COUNT(*)       AS qtd_features
    FROM incidents             AS i
    JOIN incident_log_features AS lf ON i.incident_id = lf.incident_id
    GROUP BY i.incident_id, i.fault_severity
)
SELECT
    fault_severity,
    COUNT(*)                     AS incidentes,
    ROUND(AVG(volume_total), 1)  AS volume_medio,
    ROUND(AVG(qtd_features), 1)  AS features_por_incidente
FROM volume_por_incidente
GROUP BY fault_severity
ORDER BY fault_severity;
