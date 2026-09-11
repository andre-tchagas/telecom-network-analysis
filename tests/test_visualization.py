"""Testes dos graficos.

Nao testamos a aparencia (isso e' visual), e sim que cada grafico e'
construido sem erro a partir da consulta que o alimenta.
"""

from __future__ import annotations

import plotly.graph_objects as go
import pytest

from src.database import load_named_queries, run_named_query
from src.visualization import (
    CHARTS,
    GRAY,
    LIGHT_GRAY,
    RED,
    RELIABLE_MIN_SAMPLE,
    _color_for_rate,
)


def test_todo_grafico_aponta_para_uma_consulta_existente():
    queries = load_named_queries()
    for name, (query_name, _) in CHARTS.items():
        assert query_name in queries, f"{name} usa consulta inexistente: {query_name}"


@pytest.mark.parametrize("name", list(CHARTS))
def test_grafico_e_construido_sem_erro(name):
    query_name, chart_fn = CHARTS[name]
    fig = chart_fn(run_named_query(query_name))
    assert isinstance(fig, go.Figure)
    assert fig.layout.title.text, f"{name} ficou sem titulo"


def test_amostra_pequena_recebe_cor_apagada():
    """Uma taxa alta com poucos casos nao pode chamar mais atencao que um
    achado real. O resource_type 5 (100% com 4 incidentes) e' o caso."""
    assert _color_for_rate(100.0, 4) == LIGHT_GRAY
    assert _color_for_rate(16.8, 4051) == RED   # acima da media, amostra boa
    assert _color_for_rate(3.0, 3585) == GRAY   # abaixo da media, amostra boa
    assert _color_for_rate(29.4, RELIABLE_MIN_SAMPLE - 1) == LIGHT_GRAY
