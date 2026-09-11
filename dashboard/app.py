"""
Dashboard: Telecom Network Operations Analytics

Como executar:
    streamlit run dashboard/app.py

Como funciona:
    1. carrega os dados do SQLite UMA vez (guardados em cache);
    2. aplica os filtros da barra lateral com pandas;
    3. recalcula KPIs e graficos a cada mudanca.

O Streamlit reexecuta este arquivo inteiro a cada interacao. Por isso o
@st.cache_data no carregamento: sem ele, o banco seria lido de novo a cada
clique em um filtro.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Permite `from src...` ao rodar via `streamlit run dashboard/app.py`
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import plotly.express as px
import streamlit as st

from src.database import run_query
from src.metrics import RELIABLE_MIN_SAMPLE, base_severity_rate, severity_rate_by

RED, GRAY, LIGHT_GRAY = "#dc2626", "#94a3b8", "#e2e8f0"

st.set_page_config(page_title="Telecom Network Operations Analytics",
                   page_icon="📡", layout="wide")


# ---------------------------------------------------------------------------
# Carregamento (uma vez por sessao)
# ---------------------------------------------------------------------------
@st.cache_data
def load_incidents() -> pd.DataFrame:
    """Uma linha por incidente, com os nomes ja resolvidos pelos JOINs."""
    return run_query("""
        SELECT i.incident_id,
               l.location_name,
               s.severity_type_name,
               i.fault_severity
        FROM incidents i
        JOIN locations      l ON i.location_id      = l.location_id
        JOIN severity_types s ON i.severity_type_id = s.severity_type_id
    """)


@st.cache_data
def load_events() -> pd.DataFrame:
    """Uma linha por par (incidente, evento) -- relacao 1:N."""
    return run_query("""
        SELECT ie.incident_id, e.event_type_name
        FROM incident_events ie
        JOIN event_types e ON ie.event_type_id = e.event_type_id
    """)


@st.cache_data
def load_resources() -> pd.DataFrame:
    return run_query("""
        SELECT ir.incident_id, r.resource_type_name
        FROM incident_resources ir
        JOIN resource_types r ON ir.resource_type_id = r.resource_type_id
    """)


def horizontal_bar_chart(df: pd.DataFrame, column: str, title: str,
                         dim_small_samples: bool = False) -> "px.Figure":
    """Grafico de barras por taxa de gravidade, com a mesma leitura visual do README."""
    d = df.sort_values("taxa_graves_pct", ascending=False).head(10).sort_values("taxa_graves_pct")

    if dim_small_samples:
        colors = [LIGHT_GRAY if n < RELIABLE_MIN_SAMPLE
                  else (RED if t > base_rate else GRAY)
                  for t, n in zip(d["taxa_graves_pct"], d["incidentes"])]
    else:
        colors = [RED if t > base_rate else GRAY for t in d["taxa_graves_pct"]]

    fig = px.bar(d, x="taxa_graves_pct", y=column, orientation="h", title=title,
                 text=[f"  {t}%  ({n} inc.)"
                       for t, n in zip(d["taxa_graves_pct"], d["incidentes"])])
    fig.update_traces(marker_color=colors, textposition="outside", cliponaxis=False)
    fig.add_vline(x=base_rate, line_dash="dash", line_color=GRAY)
    fig.update_layout(template="plotly_white", showlegend=False, height=400,
                      xaxis_title="% de incidentes graves", yaxis_title="",
                      margin=dict(l=10, r=90, t=50, b=10))
    return fig


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------
st.title("📡 Telecom Network Operations Analytics")
st.caption(
    "Análise de 7.381 incidentes de rede — dataset Telstra Network Disruptions. "
    "**Gravidade** (`fault_severity`) é o resultado do incidente; "
    "**tipo de alerta** (`severity_type`) é a mensagem que o log emitiu."
)

incidents = load_incidents()
events = load_events()
resources = load_resources()

# Valor exato (sem arredondar) vindo de src/metrics.py. Arredondar aqui faria a
# comparacao consigo mesma exibir "-0,00 p.p." sem nenhum filtro aplicado.
base_rate = base_severity_rate(incidents)

# --- Filtros ---------------------------------------------------------------
st.sidebar.header("Filtros")

alerts = sorted(incidents["severity_type_name"].unique())
selected_alerts = st.sidebar.multiselect(
    "Tipo de alerta do log", alerts, default=alerts,
    help="É a mensagem emitida quando o problema começou — não é a gravidade.",
)

severities = st.sidebar.multiselect(
    "Gravidade do incidente", [0, 1, 2], default=[0, 1, 2],
    format_func=lambda v: {0: "0 — Sem falha", 1: "1 — Poucas falhas",
                           2: "2 — Muitas falhas"}[v],
)

min_sample = st.sidebar.slider(
    "Mínimo de incidentes por grupo", min_value=1, max_value=50, value=10,
    help="Grupos com poucos incidentes produzem taxas extremas sem significado. "
         "Experimente mover para 1 e ver o ranking encher de 100%.",
)

st.sidebar.markdown("---")
st.sidebar.caption(f"Taxa de graves no dataset completo: **{base_rate:.2f}%**")

# --- Aplicacao dos filtros (pandas) ----------------------------------------
filtered = incidents[
    incidents["severity_type_name"].isin(selected_alerts)
    & incidents["fault_severity"].isin(severities)
]

if filtered.empty:
    st.warning("Nenhum incidente corresponde aos filtros selecionados.")
    st.stop()

ids = set(filtered["incident_id"])
events_f = events[events["incident_id"].isin(ids)].merge(filtered, on="incident_id")
resources_f = resources[resources["incident_id"].isin(ids)].merge(filtered, on="incident_id")

# --- KPIs ------------------------------------------------------------------
total = len(filtered)
severe = int((filtered["fault_severity"] == 2).sum())

# Em duas linhas de tres, e nao uma de cinco: com cinco colunas os nomes das
# categorias ficam truncados ("locatio...") em telas menores.
c1, c2, c3 = st.columns(3)
c1.metric("Incidentes", f"{total:,}".replace(",", "."))
# delta_color="inverse": mais incidentes graves e' piora, nao melhora. Sem isso
# o Streamlit desenha uma seta verde para cima, sugerindo o contrario.
c2.metric("Incidentes graves", f"{severe:,}".replace(",", "."),
          f"{severe / total * 100:.1f}% do total", delta_color="inverse")
c3.metric("Taxa de gravidade", f"{severe / total * 100:.2f}%",
          f"{severe / total * 100 - base_rate:+.2f} p.p. vs. dataset completo",
          delta_color="inverse")

c4, c5, c6 = st.columns(3)
c4.metric("Localidade mais afetada", filtered["location_name"].mode().iloc[0])
c5.metric("Evento mais frequente",
          events_f["event_type_name"].mode().iloc[0] if not events_f.empty else "—")
c6.metric("Recurso mais frequente",
          resources_f["resource_type_name"].mode().iloc[0] if not resources_f.empty else "—")

st.markdown("---")

# --- Visao geral -----------------------------------------------------------
left, right = st.columns(2)

with left:
    st.subheader("Distribuição por gravidade")
    dist = (filtered["fault_severity"].value_counts().sort_index()
            .rename_axis("gravidade").reset_index(name="incidentes"))
    dist["rotulo"] = dist["gravidade"].map(
        {0: "0 — Sem falha", 1: "1 — Poucas falhas", 2: "2 — Muitas falhas"})
    fig = px.bar(dist, x="rotulo", y="incidentes", text="incidentes",
                 color="rotulo",
                 color_discrete_map={"0 — Sem falha": "#16a34a",
                                     "1 — Poucas falhas": "#f59e0b",
                                     "2 — Muitas falhas": "#dc2626"})
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_layout(template="plotly_white", showlegend=False, height=380,
                      xaxis_title="", yaxis_title="Incidentes")
    st.plotly_chart(fig, width='stretch')

with right:
    st.subheader("O alerta do log antecipa a gravidade?")
    by_alert = severity_rate_by(filtered, "severity_type_name", min_sample=1)
    by_alert = by_alert.sort_values("incidentes", ascending=False)
    fig = px.bar(by_alert, x="severity_type_name", y="taxa_graves_pct",
                 text=[f"{t}%" for t in by_alert["taxa_graves_pct"]])
    fig.update_traces(
        marker_color=[RED if t > base_rate else GRAY for t in by_alert["taxa_graves_pct"]],
        textposition="outside", cliponaxis=False)
    fig.add_hline(y=base_rate, line_dash="dash", line_color=GRAY)
    fig.update_layout(template="plotly_white", showlegend=False, height=380,
                      xaxis_title="", yaxis_title="% de graves")
    st.plotly_chart(fig, width='stretch')

st.markdown("---")

# --- Rankings --------------------------------------------------------------
tab_location, tab_event, tab_resource = st.tabs(
    ["🗺️ Localidades", "⚡ Eventos", "🔧 Recursos"])

with tab_location:
    by_location = severity_rate_by(filtered, "location_name", min_sample=min_sample)
    if by_location.empty:
        st.info(f"Nenhuma localidade possui {min_sample} incidentes ou mais com estes filtros.")
    else:
        st.plotly_chart(
            horizontal_bar_chart(by_location, "location_name",
                                 f"Top 10 localidades por taxa de gravidade "
                                 f"(mínimo {min_sample} incidentes)"),
            width='stretch')
        st.caption(f"{len(by_location)} localidades atendem ao mínimo de {min_sample} incidentes.")

with tab_event:
    by_event = severity_rate_by(events_f, "event_type_name", min_sample=min_sample)
    if by_event.empty:
        st.info("Nenhum tipo de evento atende ao mínimo com estes filtros.")
    else:
        st.plotly_chart(
            horizontal_bar_chart(by_event, "event_type_name",
                                 "Top 10 tipos de evento por taxa de gravidade",
                                 dim_small_samples=True),
            width='stretch')

with tab_resource:
    by_resource = severity_rate_by(resources_f, "resource_type_name", min_sample=1)
    st.plotly_chart(
        horizontal_bar_chart(by_resource, "resource_type_name",
                             "Recursos por taxa de gravidade",
                             dim_small_samples=True),
        width='stretch')
    st.caption("Barras apagadas têm menos de 50 incidentes: a taxa existe, "
               "mas não é confiável.")

st.markdown("---")
st.caption(
    "As categorias do dataset são anonimizadas — sabemos que o `event_type 11` "
    "aparece em milhares de incidentes, mas não o que ele representa fisicamente. "
    "As conclusões são padrões estatísticos, não relações de causa."
)
