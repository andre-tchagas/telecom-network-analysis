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
from src.database import executar_consulta_nomeada
from src.metrics import AMOSTRA_MINIMA_CONFIAVEL, TAXA_BASE_PCT

logger = get_logger("visualization")

# Cores fixas para o projeto inteiro, para os graficos parecerem um conjunto.
AZUL = "#2563eb"
VERMELHO = "#dc2626"
CINZA = "#94a3b8"
CORES_GRAVIDADE = ["#16a34a", "#f59e0b", "#dc2626"]  # 0 verde, 1 laranja, 2 vermelho

CINZA_CLARO = "#e2e8f0"



def _cor_por_taxa(taxa: float, incidentes: int) -> str:
    """Vermelho = acima da media. Cinza = abaixo. Apagado = amostra pequena."""
    if incidentes < AMOSTRA_MINIMA_CONFIAVEL:
        return CINZA_CLARO
    return VERMELHO if taxa > TAXA_BASE_PCT else CINZA


def _layout(fig: go.Figure, titulo: str, subtitulo: str = "") -> go.Figure:
    """Aplica o mesmo estilo em todos os graficos."""
    if subtitulo:
        titulo = f"{titulo}<br><sup style='color:#64748b'>{subtitulo}</sup>"
    fig.update_layout(
        title=dict(text=titulo, font=dict(size=17)),
        template="plotly_white",
        font=dict(family="Segoe UI, Arial", size=12),
        margin=dict(l=60, r=30, t=80, b=50),
        showlegend=False,
    )
    return fig


def grafico_gravidade(df: pd.DataFrame) -> go.Figure:
    """Pergunta: como os 7.381 incidentes se distribuem por gravidade?"""
    rotulos = ["0 - Sem falha", "1 - Poucas falhas", "2 - Muitas falhas"]

    fig = go.Figure(go.Bar(
        x=rotulos,
        y=df["incidentes"],
        marker_color=CORES_GRAVIDADE,
        text=[f"{n:,}<br>{p}%".replace(",", ".")
              for n, p in zip(df["incidentes"], df["percentual"])],
        textposition="outside",
    ))
    fig.update_yaxes(title="Incidentes", range=[0, df["incidentes"].max() * 1.18])
    return _layout(fig, "Distribuição dos incidentes por gravidade",
                   "Base desbalanceada: 2 em cada 3 incidentes não geraram falha")


def grafico_alerta_vs_gravidade(df: pd.DataFrame) -> go.Figure:
    """Pergunta: o tipo de alerta do log tem relacao com a gravidade real?"""
    d = df.sort_values("taxa_graves_pct", ascending=False)

    fig = go.Figure(go.Bar(
        x=d["severity_type_name"],
        y=d["taxa_graves_pct"],
        marker_color=[VERMELHO if t > TAXA_BASE_PCT else CINZA for t in d["taxa_graves_pct"]],
        text=[f"{t}%<br><span style='font-size:10px;color:#64748b'>{n:,} inc.</span>"
              .replace(",", ".") for t, n in zip(d["taxa_graves_pct"], d["incidentes"])],
        textposition="outside",
    ))
    # Linha da media: separa quem esta acima de quem esta abaixo.
    fig.add_hline(y=TAXA_BASE_PCT, line_dash="dash", line_color=CINZA,
                  annotation_text=f"média do dataset: {TAXA_BASE_PCT}%",
                  annotation_position="top right")
    fig.update_yaxes(title="% de incidentes graves", range=[0, 18])
    return _layout(fig, "O alerta do log antecipa a gravidade real",
                   "Alertas tipo 3, 4 e 5 nunca escalaram para falha grave")


def grafico_eventos(df: pd.DataFrame) -> go.Figure:
    """Pergunta: quais tipos de evento levam a mais incidentes graves?"""
    d = df.sort_values("taxa_graves_pct")  # crescente: o maior fica no topo

    fig = go.Figure(go.Bar(
        x=d["taxa_graves_pct"],
        y=d["event_type_name"],
        orientation="h",
        marker_color=[VERMELHO if t > TAXA_BASE_PCT else CINZA for t in d["taxa_graves_pct"]],
        text=[f"  {t}%  ({n:,} inc.)".replace(",", ".")
              for t, n in zip(d["taxa_graves_pct"], d["incidentes"])],
        textposition="outside",
    ))
    fig.add_vline(x=TAXA_BASE_PCT, line_dash="dash", line_color=CINZA)
    fig.update_xaxes(title="% de incidentes graves",
                     range=[0, d["taxa_graves_pct"].max() * 1.45])
    fig.update_layout(height=460)
    return _layout(fig, "Tipos de evento com maior taxa de gravidade",
                   f"Linha tracejada = média do dataset ({TAXA_BASE_PCT}%). "
                   "Apenas eventos com 50+ incidentes")


def grafico_recursos(df: pd.DataFrame) -> go.Figure:
    """Pergunta: quais recursos concentram incidentes graves?"""
    d = df.sort_values("taxa_graves_pct")

    fig = go.Figure(go.Bar(
        x=d["taxa_graves_pct"],
        y=d["resource_type_name"],
        orientation="h",
        marker_color=[_cor_por_taxa(t, n)
                      for t, n in zip(d["taxa_graves_pct"], d["incidentes"])],
        text=[f"  {t}%  ({n:,} inc.)".replace(",", ".")
              for t, n in zip(d["taxa_graves_pct"], d["incidentes"])],
        textposition="outside",
    ))
    fig.add_vline(x=TAXA_BASE_PCT, line_dash="dash", line_color=CINZA)
    fig.update_xaxes(title="% de incidentes graves", range=[0, 125])
    fig.update_layout(height=460)
    return _layout(fig, "Recursos por taxa de gravidade",
                   "Barras apagadas têm menos de 50 incidentes: a taxa existe, "
                   "mas não é confiável")


def grafico_localidades(df: pd.DataFrame) -> go.Figure:
    """Pergunta: quais localidades tem a pior taxa de incidentes graves?"""
    d = df.sort_values("taxa_graves_pct")

    fig = go.Figure(go.Bar(
        x=d["taxa_graves_pct"],
        y=d["location_name"],
        orientation="h",
        marker_color=AZUL,
        text=[f"  {t}%  ({g}/{n})"
              for t, g, n in zip(d["taxa_graves_pct"], d["graves"], d["incidentes"])],
        textposition="outside",
    ))
    fig.add_vline(x=TAXA_BASE_PCT, line_dash="dash", line_color=CINZA)
    fig.update_xaxes(title="% de incidentes graves", range=[0, 100])
    fig.update_layout(height=460)
    return _layout(fig, "Localidades mais críticas da rede",
                   "Apenas localidades com 10+ incidentes, para evitar taxas "
                   "extremas por amostra pequena")


# Liga cada grafico a consulta que o alimenta e ao arquivo de saida.
GRAFICOS = {
    "01_gravidade": ("gravidade_distribuicao", grafico_gravidade),
    "02_alerta_vs_gravidade": ("alerta_vs_gravidade", grafico_alerta_vs_gravidade),
    "03_eventos": ("eventos", grafico_eventos),
    "04_recursos": ("recursos", grafico_recursos),
    "05_localidades": ("localidades_criticas", grafico_localidades),
}


def gerar_figuras(output_dir: Path = FIGURES_DIR) -> None:
    """Roda as consultas, monta os graficos e salva os PNG."""
    output_dir.mkdir(parents=True, exist_ok=True)

    for nome, (consulta, funcao) in GRAFICOS.items():
        df = executar_consulta_nomeada(consulta)
        fig = funcao(df)
        caminho = output_dir / f"{nome}.png"
        fig.write_image(str(caminho), width=900, height=fig.layout.height or 500, scale=2)
        logger.info("  %-24s -> %s", nome, caminho.name)

    logger.info("%d figuras geradas em %s", len(GRAFICOS), output_dir)
