"""
Graficos do projeto.

Cada funcao recebe o resultado de uma consulta SQL (um DataFrame) e devolve
um grafico Plotly. Nenhum calculo acontece aqui -- os numeros ja vieram
prontos do banco. Isso mantem uma fonte unica de verdade: se um numero
mudar, ele muda na consulta, e o grafico acompanha.

Os graficos sao salvos como PNG em reports/figures/ para aparecerem no
README (o GitHub so mostra imagem, nao grafico interativo).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from src.config import FIGURES_DIR, get_logger
from src.database import run_named_query
from src.metrics import BASE_SEVERITY_RATE_PCT, RELIABLE_MIN_SAMPLE

logger = get_logger("visualization")

# Cores fixas para o projeto inteiro, para os graficos parecerem um conjunto.
BLUE = "#2563eb"
RED = "#dc2626"
GRAY = "#94a3b8"
LIGHT_GRAY = "#e2e8f0"
SEVERITY_COLORS = ["#16a34a", "#f59e0b", "#dc2626"]  # 0 verde, 1 laranja, 2 vermelho


def _color_for_rate(rate: float, incidents: int) -> str:
    """Vermelho = acima da media. Cinza = abaixo. Apagado = amostra pequena."""
    if incidents < RELIABLE_MIN_SAMPLE:
        return LIGHT_GRAY
    return RED if rate > BASE_SEVERITY_RATE_PCT else GRAY


def _layout(fig: go.Figure, title: str, subtitle: str = "") -> go.Figure:
    """Aplica o mesmo estilo em todos os graficos."""
    if subtitle:
        title = f"{title}<br><sup style='color:#64748b'>{subtitle}</sup>"
    fig.update_layout(
        title=dict(text=title, font=dict(size=17)),
        template="plotly_white",
        font=dict(family="Segoe UI, Arial", size=12),
        margin=dict(l=60, r=30, t=80, b=50),
        showlegend=False,
    )
    return fig


def chart_severity_distribution(df: pd.DataFrame) -> go.Figure:
    """Pergunta: como os 7.381 incidentes se distribuem por gravidade?"""
    labels = ["0 - Sem falha", "1 - Poucas falhas", "2 - Muitas falhas"]

    fig = go.Figure(go.Bar(
        x=labels,
        y=df["incidentes"],
        marker_color=SEVERITY_COLORS,
        text=[f"{n:,}<br>{p}%".replace(",", ".")
              for n, p in zip(df["incidentes"], df["percentual"])],
        textposition="outside",
    ))
    fig.update_yaxes(title="Incidentes", range=[0, df["incidentes"].max() * 1.18])
    return _layout(fig, "Distribuição dos incidentes por gravidade",
                   "Base desbalanceada: 2 em cada 3 incidentes não geraram falha")


def chart_alert_vs_severity(df: pd.DataFrame) -> go.Figure:
    """Pergunta: o tipo de alerta do log tem relacao com a gravidade real?"""
    d = df.sort_values("taxa_graves_pct", ascending=False)

    fig = go.Figure(go.Bar(
        x=d["severity_type_name"],
        y=d["taxa_graves_pct"],
        marker_color=[RED if t > BASE_SEVERITY_RATE_PCT else GRAY for t in d["taxa_graves_pct"]],
        text=[f"{t}%<br><span style='font-size:10px;color:#64748b'>{n:,} inc.</span>"
              .replace(",", ".") for t, n in zip(d["taxa_graves_pct"], d["incidentes"])],
        textposition="outside",
    ))
    # Linha da media: separa quem esta acima de quem esta abaixo.
    fig.add_hline(y=BASE_SEVERITY_RATE_PCT, line_dash="dash", line_color=GRAY,
                  annotation_text=f"média do dataset: {BASE_SEVERITY_RATE_PCT}%",
                  annotation_position="top right")
    fig.update_yaxes(title="% de incidentes graves", range=[0, 18])
    return _layout(fig, "O alerta do log antecipa a gravidade real",
                   "Alertas tipo 3, 4 e 5 nunca escalaram para falha grave")


def chart_events(df: pd.DataFrame) -> go.Figure:
    """Pergunta: quais tipos de evento levam a mais incidentes graves?"""
    d = df.sort_values("taxa_graves_pct")  # crescente: o maior fica no topo

    fig = go.Figure(go.Bar(
        x=d["taxa_graves_pct"],
        y=d["event_type_name"],
        orientation="h",
        marker_color=[RED if t > BASE_SEVERITY_RATE_PCT else GRAY for t in d["taxa_graves_pct"]],
        text=[f"  {t}%  ({n:,} inc.)".replace(",", ".")
              for t, n in zip(d["taxa_graves_pct"], d["incidentes"])],
        textposition="outside",
    ))
    fig.add_vline(x=BASE_SEVERITY_RATE_PCT, line_dash="dash", line_color=GRAY)
    fig.update_xaxes(title="% de incidentes graves",
                     range=[0, d["taxa_graves_pct"].max() * 1.45])
    fig.update_layout(height=460)
    return _layout(fig, "Tipos de evento com maior taxa de gravidade",
                   f"Linha tracejada = média do dataset ({BASE_SEVERITY_RATE_PCT}%). "
                   "Apenas eventos com 50+ incidentes")


def chart_resources(df: pd.DataFrame) -> go.Figure:
    """Pergunta: quais recursos concentram incidentes graves?"""
    d = df.sort_values("taxa_graves_pct")

    fig = go.Figure(go.Bar(
        x=d["taxa_graves_pct"],
        y=d["resource_type_name"],
        orientation="h",
        marker_color=[_color_for_rate(t, n)
                      for t, n in zip(d["taxa_graves_pct"], d["incidentes"])],
        text=[f"  {t}%  ({n:,} inc.)".replace(",", ".")
              for t, n in zip(d["taxa_graves_pct"], d["incidentes"])],
        textposition="outside",
    ))
    fig.add_vline(x=BASE_SEVERITY_RATE_PCT, line_dash="dash", line_color=GRAY)
    fig.update_xaxes(title="% de incidentes graves", range=[0, 125])
    fig.update_layout(height=460)
    return _layout(fig, "Recursos por taxa de gravidade",
                   "Barras apagadas têm menos de 50 incidentes: a taxa existe, "
                   "mas não é confiável")


def chart_locations(df: pd.DataFrame) -> go.Figure:
    """Pergunta: quais localidades tem a pior taxa de incidentes graves?"""
    d = df.sort_values("taxa_graves_pct")

    fig = go.Figure(go.Bar(
        x=d["taxa_graves_pct"],
        y=d["location_name"],
        orientation="h",
        marker_color=BLUE,
        text=[f"  {t}%  ({g}/{n})"
              for t, g, n in zip(d["taxa_graves_pct"], d["graves"], d["incidentes"])],
        textposition="outside",
    ))
    fig.add_vline(x=BASE_SEVERITY_RATE_PCT, line_dash="dash", line_color=GRAY)
    fig.update_xaxes(title="% de incidentes graves", range=[0, 100])
    fig.update_layout(height=460)
    return _layout(fig, "Localidades mais críticas da rede",
                   "Apenas localidades com 10+ incidentes, para evitar taxas "
                   "extremas por amostra pequena")


def chart_event_resource(df: pd.DataFrame) -> go.Figure:
    """Pergunta: quais combinacoes de evento + recurso concentram gravidade?"""
    d = df.copy()
    d["combinacao"] = d["event_type_name"] + "  +  " + d["resource_type_name"]
    d = d.sort_values("taxa_graves_pct")

    fig = go.Figure(go.Bar(
        x=d["taxa_graves_pct"],
        y=d["combinacao"],
        orientation="h",
        marker_color=[RED if t > BASE_SEVERITY_RATE_PCT else GRAY for t in d["taxa_graves_pct"]],
        text=[f"  {t}%  ({n:,} inc.)".replace(",", ".")
              for t, n in zip(d["taxa_graves_pct"], d["incidentes"])],
        textposition="outside",
    ))
    fig.add_vline(x=BASE_SEVERITY_RATE_PCT, line_dash="dash", line_color=GRAY)
    fig.update_xaxes(title="% de incidentes graves",
                     range=[0, d["taxa_graves_pct"].max() * 1.4])
    fig.update_layout(height=460, margin=dict(l=60, r=30, t=80, b=50))
    return _layout(fig, "Combinações evento + recurso com maior gravidade",
                   "Apenas combinações presentes em 50+ incidentes")


# Liga cada grafico a consulta que o alimenta e ao arquivo de saida.
# Chave = nome do arquivo PNG; valor = (nome da consulta SQL, funcao do grafico).
CHARTS = {
    "01_gravidade": ("gravidade_distribuicao", chart_severity_distribution),
    "02_alerta_vs_gravidade": ("alerta_vs_gravidade", chart_alert_vs_severity),
    "03_eventos": ("eventos", chart_events),
    "04_recursos": ("recursos", chart_resources),
    "05_localidades": ("localidades_criticas", chart_locations),
    "06_evento_recurso": ("evento_recurso", chart_event_resource),
}


def generate_figures(output_dir: Path = FIGURES_DIR) -> None:
    """Roda as consultas, monta os graficos e salva os PNG."""
    output_dir.mkdir(parents=True, exist_ok=True)

    for name, (query_name, chart_fn) in CHARTS.items():
        df = run_named_query(query_name)
        fig = chart_fn(df)
        path = output_dir / f"{name}.png"
        fig.write_image(str(path), width=900, height=fig.layout.height or 500, scale=2)
        logger.info("  %-24s -> %s", name, path.name)

    logger.info("%d figuras geradas em %s", len(CHARTS), output_dir)
