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

from src.database import consultar

TAXA_BASE = 9.84  # % de incidentes graves no dataset inteiro
VERMELHO, CINZA, CINZA_CLARO = "#dc2626", "#94a3b8", "#e2e8f0"

st.set_page_config(page_title="Telecom Network Operations Analytics",
                   page_icon="📡", layout="wide")


# ---------------------------------------------------------------------------
# Carregamento (uma vez por sessao)
# ---------------------------------------------------------------------------
@st.cache_data
def carregar_incidentes() -> pd.DataFrame:
    """Uma linha por incidente, com os nomes ja resolvidos pelos JOINs."""
    return consultar("""
        SELECT i.incident_id,
               l.location_name,
               s.severity_type_name,
               i.fault_severity
        FROM incidents i
        JOIN locations      l ON i.location_id      = l.location_id
        JOIN severity_types s ON i.severity_type_id = s.severity_type_id
    """)


@st.cache_data
def carregar_eventos() -> pd.DataFrame:
    """Uma linha por par (incidente, evento) -- relacao 1:N."""
    return consultar("""
        SELECT ie.incident_id, e.event_type_name
        FROM incident_events ie
        JOIN event_types e ON ie.event_type_id = e.event_type_id
    """)


@st.cache_data
def carregar_recursos() -> pd.DataFrame:
    return consultar("""
        SELECT ir.incident_id, r.resource_type_name
        FROM incident_resources ir
        JOIN resource_types r ON ir.resource_type_id = r.resource_type_id
    """)


def taxa_de_graves(df: pd.DataFrame, coluna: str, minimo: int) -> pd.DataFrame:
    """
    Agrupa por uma coluna e calcula quantos incidentes e qual a taxa de graves.

    `minimo` descarta grupos com poucos incidentes: com amostra pequena a taxa
    so consegue dar valores extremos (com 1 incidente, ou 0% ou 100%).
    """
    g = (df.assign(grave=(df["fault_severity"] == 2).astype(int))
           .groupby(coluna, observed=True)
           .agg(incidentes=("incident_id", "count"), graves=("grave", "sum"))
           .reset_index())
    g["taxa_graves_pct"] = (g["graves"] / g["incidentes"] * 100).round(1)
    return g[g["incidentes"] >= minimo]


def barras_horizontais(df: pd.DataFrame, coluna: str, titulo: str,
                       destacar_amostra_pequena: bool = False) -> "px.Figure":
    """Grafico de barras por taxa de gravidade, com a mesma leitura visual do README."""
    d = df.sort_values("taxa_graves_pct", ascending=False).head(10).sort_values("taxa_graves_pct")

    if destacar_amostra_pequena:
        cores = [CINZA_CLARO if n < 50 else (VERMELHO if t > TAXA_BASE else CINZA)
                 for t, n in zip(d["taxa_graves_pct"], d["incidentes"])]
    else:
        cores = [VERMELHO if t > TAXA_BASE else CINZA for t in d["taxa_graves_pct"]]

    fig = px.bar(d, x="taxa_graves_pct", y=coluna, orientation="h", title=titulo,
                 text=[f"  {t}%  ({n} inc.)"
                       for t, n in zip(d["taxa_graves_pct"], d["incidentes"])])
    fig.update_traces(marker_color=cores, textposition="outside", cliponaxis=False)
    fig.add_vline(x=TAXA_BASE, line_dash="dash", line_color=CINZA)
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

incidentes = carregar_incidentes()
eventos = carregar_eventos()
recursos = carregar_recursos()

# Calculada do proprio dado em vez de fixada na mao: evita que o numero do
# dashboard e o do banco divirjam se o dataset mudar.
# Guardada SEM arredondar: arredondar aqui faria a comparacao consigo mesma
# dar '-0.00 p.p.' quando nenhum filtro esta aplicado.
TAXA_BASE = (incidentes["fault_severity"] == 2).mean() * 100

# --- Filtros ---------------------------------------------------------------
st.sidebar.header("Filtros")

alertas = sorted(incidentes["severity_type_name"].unique())
alertas_escolhidos = st.sidebar.multiselect(
    "Tipo de alerta do log", alertas, default=alertas,
    help="É a mensagem emitida quando o problema começou — não é a gravidade.",
)

gravidades = st.sidebar.multiselect(
    "Gravidade do incidente", [0, 1, 2], default=[0, 1, 2],
    format_func=lambda v: {0: "0 — Sem falha", 1: "1 — Poucas falhas",
                           2: "2 — Muitas falhas"}[v],
)

corte = st.sidebar.slider(
    "Mínimo de incidentes por grupo", min_value=1, max_value=50, value=10,
    help="Grupos com poucos incidentes produzem taxas extremas sem significado. "
         "Experimente mover para 1 e ver o ranking encher de 100%.",
)

st.sidebar.markdown("---")
st.sidebar.caption(f"Taxa de graves no dataset completo: **{TAXA_BASE:.2f}%**")

# --- Aplicacao dos filtros (pandas) ----------------------------------------
filtrado = incidentes[
    incidentes["severity_type_name"].isin(alertas_escolhidos)
    & incidentes["fault_severity"].isin(gravidades)
]

if filtrado.empty:
    st.warning("Nenhum incidente corresponde aos filtros selecionados.")
    st.stop()

ids = set(filtrado["incident_id"])
eventos_f = eventos[eventos["incident_id"].isin(ids)].merge(filtrado, on="incident_id")
recursos_f = recursos[recursos["incident_id"].isin(ids)].merge(filtrado, on="incident_id")

# --- KPIs ------------------------------------------------------------------
total = len(filtrado)
graves = int((filtrado["fault_severity"] == 2).sum())

# Em duas linhas de tres, e nao uma de cinco: com cinco colunas os nomes das
# categorias ficam truncados ("locatio...") em telas menores.
c1, c2, c3 = st.columns(3)
c1.metric("Incidentes", f"{total:,}".replace(",", "."))
# delta_color="inverse": mais incidentes graves e' piora, nao melhora. Sem isso
# o Streamlit desenha uma seta verde para cima, sugerindo o contrario.
c2.metric("Incidentes graves", f"{graves:,}".replace(",", "."),
          f"{graves / total * 100:.1f}% do total", delta_color="inverse")
c3.metric("Taxa de gravidade", f"{graves / total * 100:.2f}%",
          f"{graves / total * 100 - TAXA_BASE:+.2f} p.p. vs. dataset completo",
          delta_color="inverse")

c4, c5, c6 = st.columns(3)
c4.metric("Localidade mais afetada", filtrado["location_name"].mode().iloc[0])
c5.metric("Evento mais frequente",
          eventos_f["event_type_name"].mode().iloc[0] if not eventos_f.empty else "—")
c6.metric("Recurso mais frequente",
          recursos_f["resource_type_name"].mode().iloc[0] if not recursos_f.empty else "—")

st.markdown("---")

# --- Visao geral -----------------------------------------------------------
esquerda, direita = st.columns(2)

with esquerda:
    st.subheader("Distribuição por gravidade")
    dist = (filtrado["fault_severity"].value_counts().sort_index()
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

with direita:
    st.subheader("O alerta do log antecipa a gravidade?")
    por_alerta = taxa_de_graves(filtrado, "severity_type_name", minimo=1)
    fig = px.bar(por_alerta.sort_values("incidentes", ascending=False),
                 x="severity_type_name", y="taxa_graves_pct",
                 text=[f"{t}%" for t in
                       por_alerta.sort_values("incidentes", ascending=False)["taxa_graves_pct"]])
    fig.update_traces(
        marker_color=[VERMELHO if t > TAXA_BASE else CINZA for t in
                      por_alerta.sort_values("incidentes", ascending=False)["taxa_graves_pct"]],
        textposition="outside", cliponaxis=False)
    fig.add_hline(y=TAXA_BASE, line_dash="dash", line_color=CINZA)
    fig.update_layout(template="plotly_white", showlegend=False, height=380,
                      xaxis_title="", yaxis_title="% de graves")
    st.plotly_chart(fig, width='stretch')

st.markdown("---")

# --- Rankings --------------------------------------------------------------
aba_local, aba_evento, aba_recurso = st.tabs(
    ["🗺️ Localidades", "⚡ Eventos", "🔧 Recursos"])

with aba_local:
    por_local = taxa_de_graves(filtrado, "location_name", minimo=corte)
    if por_local.empty:
        st.info(f"Nenhuma localidade possui {corte} incidentes ou mais com estes filtros.")
    else:
        st.plotly_chart(
            barras_horizontais(por_local, "location_name",
                               f"Top 10 localidades por taxa de gravidade "
                               f"(mínimo {corte} incidentes)"),
            width='stretch')
        st.caption(f"{len(por_local)} localidades atendem ao mínimo de {corte} incidentes.")

with aba_evento:
    por_evento = taxa_de_graves(eventos_f, "event_type_name", minimo=corte)
    if por_evento.empty:
        st.info("Nenhum tipo de evento atende ao mínimo com estes filtros.")
    else:
        st.plotly_chart(
            barras_horizontais(por_evento, "event_type_name",
                               "Top 10 tipos de evento por taxa de gravidade",
                               destacar_amostra_pequena=True),
            width='stretch')

with aba_recurso:
    por_recurso = taxa_de_graves(recursos_f, "resource_type_name", minimo=1)
    st.plotly_chart(
        barras_horizontais(por_recurso, "resource_type_name",
                           "Recursos por taxa de gravidade",
                           destacar_amostra_pequena=True),
        width='stretch')
    st.caption("Barras apagadas têm menos de 50 incidentes: a taxa existe, "
               "mas não é confiável.")

st.markdown("---")
st.caption(
    "As categorias do dataset são anonimizadas — sabemos que o `event_type 11` "
    "aparece em milhares de incidentes, mas não o que ele representa fisicamente. "
    "As conclusões são padrões estatísticos, não relações de causa."
)
