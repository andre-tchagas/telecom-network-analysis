"""Testes dos graficos.

Nao testamos a aparencia (isso e' visual), e sim que cada grafico e'
construido sem erro a partir da consulta que o alimenta.
"""

from __future__ import annotations

import plotly.graph_objects as go
import pytest

from src.database import carregar_consultas
from src.visualization import (
    AMOSTRA_MINIMA_CONFIAVEL,
    CINZA,
    CINZA_CLARO,
    VERMELHO,
    GRAFICOS,
    _cor_por_taxa,
)


def test_todo_grafico_aponta_para_uma_consulta_existente():
    consultas = carregar_consultas()
    for nome, (consulta, _) in GRAFICOS.items():
        assert consulta in consultas, f"{nome} usa consulta inexistente: {consulta}"


@pytest.mark.parametrize("nome", list(GRAFICOS))
def test_grafico_e_construido_sem_erro(nome):
    from src.database import executar_consulta_nomeada

    consulta, funcao = GRAFICOS[nome]
    fig = funcao(executar_consulta_nomeada(consulta))
    assert isinstance(fig, go.Figure)
    assert fig.layout.title.text, f"{nome} ficou sem titulo"


def test_amostra_pequena_recebe_cor_apagada():
    """Uma taxa alta com poucos casos nao pode chamar mais atencao que um
    achado real. O resource_type 5 (100% com 4 incidentes) e' o caso."""
    assert _cor_por_taxa(100.0, 4) == CINZA_CLARO
    assert _cor_por_taxa(16.8, 4051) == VERMELHO   # acima da media, amostra boa
    assert _cor_por_taxa(3.0, 3585) == CINZA       # abaixo da media, amostra boa
    assert _cor_por_taxa(29.4, AMOSTRA_MINIMA_CONFIAVEL - 1) == CINZA_CLARO
