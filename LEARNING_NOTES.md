# Learning Notes

Documento de apoio ao desenvolvedor. Enquanto o `README.md` apresenta o projeto
para quem chega de fora, este arquivo registra **por que** cada decisão técnica
foi tomada — inclusive as alternativas descartadas.

> Escrito de forma incremental, checkpoint a checkpoint.

---

## Checkpoint 1 — Ambiente, estrutura e carga de dados

### O dataset

**Telstra Network Disruptions** (Kaggle, 2015). Sete arquivos CSV, ~3 MB.
Registra incidentes de rede de uma operadora australiana.

| Arquivo | Linhas | Chave | Relação com o incidente |
|---|---:|---|---|
| `train.csv` | 7.381 | `id` único | 1:1 — **contém o alvo** `fault_severity` |
| `test.csv` | 11.171 | `id` único | 1:1 — sem alvo, **não usado** |
| `severity_type.csv` | 18.552 | `id` único | 1:1 |
| `event_type.csv` | 31.170 | `id` repetido | 1:N (média 1,68 / máx 11) |
| `resource_type.csv` | 21.076 | `id` repetido | 1:N (média 1,14 / máx 5) |
| `log_feature.csv` | 58.671 | `id` repetido | 1:N (média 3,16 / máx 20) |
| `sample_submission.csv` | 11.171 | `id` único | template Kaggle, **não usado** |

### Decisão 1 — Universo de análise: apenas os 7.381 incidentes de `train.csv`

`fault_severity` só existe em `train.csv`. Os 11.171 incidentes de `test.csv`
nunca tiveram o gabarito publicado, porque eram o conjunto oculto de avaliação
da competição.

**Alternativas consideradas:**

1. Carregar os 18.552 e analisar severidade apenas nos rotulados.
   Mais dados para análises que não dependem do alvo, mas exige disciplina
   permanente para não misturar dois universos no mesmo gráfico.
2. Carregar os 18.552 com `fault_severity = NULL` nos de teste.
   Bom exercício de tratamento de nulos em SQL, porém um `GROUP BY` distraído
   contaria os nulos de forma errada e distorceria a conclusão.
3. **Escolhida:** usar apenas os 7.381 rotulados.

**Motivo:** todas as perguntas de negócio do projeto envolvem severidade
("que localidade concentra incidentes graves?", "que recurso está associado a
mais falhas?"). Sem o alvo, os 11.171 registros restantes não respondem nenhuma
delas. Restringir o universo torna cada número do projeto interpretável sem
ressalva — e a frase "analiso incidentes com desfecho conhecido" é defensável
em entrevista, enquanto "às vezes uso 18 mil, às vezes 7 mil" não é.

**Custo assumido:** descartamos 60% das linhas. Está registrado no README como
limitação explícita, não escondido.

### Decisão 2 — `severity_type` não é `fault_severity`

A armadilha central do dataset. São duas colunas com nomes parecidos e
significados diferentes:

| | `fault_severity` | `severity_type` |
|---|---|---|
| O que é | **resultado** do incidente | tipo da mensagem de alerta do log |
| Valores | 0, 1, 2 | 5 categorias |
| Disponível para | só `train` (7.381) | todos (18.552) |
| Papel na análise | variável-alvo | atributo de entrada |

Tratar `severity_type` como gravidade invalidaria todas as conclusões. O aviso
está registrado em `src/config.py`, junto das constantes.

### Decisão 3 — Distribuição do alvo é desbalanceada

```
fault_severity = 0 (sem falha)      4.784   64,82%
fault_severity = 1 (poucas falhas)  1.871   25,35%
fault_severity = 2 (muitas falhas)    726    9,84%
```

Consequência prática: ranking de localidade por *contagem absoluta* de
incidentes graves vai apenas reproduzir o ranking de localidades com mais
incidentes no total. Para responder "onde a rede é pior?" será preciso usar
**taxa** (graves ÷ total) e aplicar um **corte mínimo de incidentes** — das 929
localidades, 241 aparecem uma única vez, e uma localidade com 1 incidente grave
em 1 incidente total tem taxa de 100% sem significar nada.

### Decisão 4 — Não há análise temporal

Nenhum dos sete arquivos possui coluna de data ou hora. O `id` não tem
semântica documentada de ordem. Portanto o projeto **não** terá séries
temporais, e isso está declarado no README como limitação do dataset em vez de
ser simulado a partir do `id`.

### Decisão 5 — Ambiente e dependências

- **`venv` em vez de conda/poetry:** faz parte da biblioteca padrão, não exige
  instalação extra de quem clonar o repositório.
- **Versões fixadas** (`pandas==3.0.5`, etc.) em vez de `>=`: garante que o
  pipeline rode hoje igual ao que rodou quando os números do README foram
  gerados. Reprodutibilidade é o requisito, não estar na última versão.
- **SQLite:** biblioteca padrão do Python (`sqlite3`), zero dependência e zero
  servidor. Para 7.381 linhas, um PostgreSQL seria infraestrutura sem benefício.
- **Plotly em vez de Matplotlib:** o dashboard é Streamlit, e Plotly já entrega
  gráficos interativos (hover, zoom) nativamente integrados ao Streamlit.
  Usar Matplotlib exigiria uma segunda biblioteca só para o dashboard.
- **pandas 3.0** introduz Copy-on-Write por padrão. Por isso o código evita
  `inplace=True` e encadeamentos que dependam de *view*, usando atribuição
  explícita (`df = df.assign(...)`).

### Decisão 6 — `src/config.py` (fora da estrutura originalmente sugerida)

Todos os módulos precisam saber onde estão os dados. Centralizar caminhos
resolve dois problemas de uma vez: elimina repetição e garante que **nenhum
caminho absoluto** apareça no código — os caminhos derivam de
`Path(__file__).resolve().parents[1]`, então funcionam em qualquer máquina.

### Decisão 7 — O loader não toma decisões analíticas

`src/data_loader.py` apenas lê `data/raw/` e valida. Ele **não** filtra para os
7.381 — esse recorte é uma regra de negócio e vive em `cleaning.py`.

**Por que separar:** quando o pipeline quebra, a camada em que ele quebrou já
diz que tipo de problema é. Falha no loader significa que o arquivo de origem
mudou. Falha depois significa que a nossa regra está errada. Sem essa
separação, todo erro exige investigação do zero.

### Decisão 8 — Tipos declarados, não inferidos

```python
RAW_DTYPES = {"train": {"id": "int64", "location": "string", "fault_severity": "int8"}}
```

Se um `id` vier corrompido, o pandas silenciosamente converteria a coluna para
`object` e todos os JOINs a jusante falhariam de um jeito difícil de rastrear.
Declarar o tipo transforma esse cenário em erro imediato, no ponto de entrada.

### Decisão 9 — Validação como barreira de regressão

`validate_raw_data()` verifica nulos, unicidade da chave, integridade
referencial e domínio de valores. O dataset atual passa em tudo — **é dado
limpo de verdade**, sem nulos e sem duplicatas.

Isso poderia sugerir que a validação é inútil. É o contrário: ela documenta
executavelmente as premissas em que as conclusões do projeto se apoiam. Se
alguém trocar o dataset, o pipeline para em vez de produzir números errados
em silêncio.

**Nota de honestidade:** por esse mesmo motivo, o `cleaning.py` deste projeto
será pequeno. Inventar tratamento de nulos onde não há nulos seria teatro.

---

## Perguntas de entrevista — Checkpoint 1

**Por que você usou um ambiente virtual?**
Para isolar as dependências do projeto do Python do sistema. Sem isso, duas
aplicações que precisam de versões diferentes de pandas entram em conflito, e
o `requirements.txt` deixa de refletir o que o projeto realmente usa.

**Por que fixar versões exatas no `requirements.txt`?**
Porque os números publicados no README foram gerados com essas versões.
Com `>=`, uma mudança de comportamento em uma versão futura poderia alterar
resultados sem que ninguém percebesse. Em biblioteca eu usaria faixas; em
aplicação reproduzível, fixo.

**Por que separou `data/raw` de `data/processed`?**
`raw` é a fonte da verdade e nunca é modificada. Se uma transformação estiver
errada, basta reprocessar a partir do raw. Se o script escrevesse por cima do
original, um bug destruiria o dado permanentemente. É também o que torna o
pipeline reproduzível: qualquer pessoa parte exatamente do mesmo ponto.

**Por que uma `dataclass` em vez de um dicionário para agrupar as tabelas?**
Os nomes dos campos passam a ser verificados pelo interpretador em vez de
existirem só como string. E `frozen=True` impede que uma etapa posterior
substitua uma tabela por engano, o que quebraria a reprodutibilidade.

**Por que `logging` em vez de `print()`?**
`print` não tem nível de severidade, não tem timestamp e não pode ser
redirecionado ou filtrado. Com `logging`, a mesma execução pode ser silenciosa
em uso normal e detalhada em depuração, sem alterar o código.

**Como você garantiria que o pipeline é reproduzível?**
Quatro elementos: versões fixadas, `data/raw` imutável e versionada, ponto de
entrada único (`run_pipeline.py`) em vez de células de notebook executadas fora
de ordem, e validação de contrato que falha alto se o dado de entrada mudar.

**O que aconteceria se o volume de dados aumentasse 100 vezes?**
Seriam ~740 mil incidentes e ~5,8 milhões de linhas em `log_feature`. Pandas
ainda aguentaria em memória, mas ficaria desconfortável. As mudanças seriam:
ler em *chunks* ou migrar para PyArrow/Polars, carregar no banco em lotes, e
mover as agregações para SQL em vez de fazê-las em memória. Acima disso, trocar
SQLite por PostgreSQL — não por limite de tamanho, mas por concorrência de
escrita e por planos de execução melhores em agregação.

---

## Checkpoint 2 — Exploração

Entregável: `notebooks/exploratory_analysis.ipynb`, 44 células (20 de código),
versionado **com as saídas executadas**.

### Decisão 10 — Notebook sem gráficos

O GitHub não renderiza saídas de Plotly no preview de `.ipynb`. Um notebook de
portfólio cujos gráficos aparecem como blocos vazios comunica menos do que um
notebook honestamente tabular.

**Escolha:** a exploração fica com tabelas e narrativa — que renderizam
perfeitamente no GitHub. As visualizações vão para `reports/figures/` e para o
dashboard Streamlit, no Checkpoint 5, onde de fato aparecem.

Isso também reflete a divisão real de propósito: exploração serve para *entender
estrutura e números*; visualização serve para *comunicar um resultado já
entendido*.

### Decisão 11 — Notebook versionado com saídas

O padrão em times de engenharia é limpar as saídas antes de commitar (evita
conflito de merge e inchaço do diff). Aqui a escolha é a oposta.

**Motivo:** o público deste repositório é um recrutador que vai abrir o notebook
no navegador do GitHub e não vai executá-lo. Notebook sem saída é uma página em
branco. O custo — diffs grandes — é irrelevante em um projeto de um
desenvolvedor só, sem merges concorrentes.

**Como é gerado:** o notebook é executado de ponta a ponta com
`jupyter nbconvert --to notebook --execute --inplace`. Isso garante que as
saídas correspondam ao código commitado e que a ordem de execução seja linear —
o contrário do notebook editado à mão, em que a célula 3 pode ter rodado depois
da célula 12.

### Achados do Checkpoint 2

**1. Qualidade: dado já tratado.** Zero nulos, zero duplicatas, integridade
referencial perfeita. Confirma que `cleaning.py` será pequeno.

**2. `severity_type` carrega sinal real sobre a gravidade.** Cruzando as duas
colunas (taxa média de graves = 9,84%):

| `severity_type` | incidentes | % graves |
|---|---:|---:|
| 1 | 3.375 | **14,2%** |
| 2 | 3.591 | 6,9% |
| 4 | 388 | **0,0%** |
| 5 | 23 | 0,0% |
| 3 | 4 | 0,0% |

O caso do tipo 4 é o mais forte: **388 incidentes, nenhum grave**. Na taxa base
esperaríamos ~38. Zero em 388 não é acaso de amostra pequena — é sinal.

Leitura operacional: o tipo de alarme emitido pelo log tem valor preditivo.
Alarmes tipo 1 merecem prioridade maior que tipo 2; tipos 3/4/5 aparentemente
nunca escalam para falha grave.

**3. Concentração das categorias determina o gráfico adequado.**

| variável | categorias | top 10 cobre |
|---|---:|---:|
| `resource_type` | 10 | 100% |
| `event_type` | 49 | 92,4% |
| `log_feature` | 331 | **45,4%** |

Consequência: um gráfico "top 10" funciona para evento e recurso, mas para
`log_feature` **esconderia mais da metade dos dados**. Essa variável precisa ser
tratada por agregação (soma de volume por incidente), não por ranking.

**4. `volume` é fortemente assimétrico.** Assimetria (*skew*) = 10,05; média
9,85 contra mediana 2; máximo 877 contra p95 de 42; 81% das linhas com volume
≤ 10. Portanto: descrever com **mediana**, não média, e usar **escala
logarítmica** nos gráficos.

**5. O ranking de localidades exige corte mínimo.** Sem corte, 14 localidades
têm taxa de 100% de gravidade — 10 delas com **um único incidente**, e nenhuma
com 5 ou mais. Com corte de 20 incidentes sobram 102 das 929, e o topo passa a
ser `location 1100` com 33 graves em 45 (73,3%), mais de 7× a taxa base.

O corte de 20 é uma **decisão analítica declarada**, não um detalhe de
implementação. Alternativa mais correta estatisticamente — *shrinkage*, puxar
cada taxa em direção à média geral proporcionalmente ao tamanho da amostra —
fica registrada como Future Improvement por ser difícil de explicar num README.

### Limitações registradas

1. **Sem dimensão temporal** — nenhum arquivo tem data/hora.
2. **Categorias anonimizadas** — sabemos que `resource_type 8` é o mais
   frequente, mas não o que ele é. Conclusões ficam no nível de padrão
   estatístico, nunca de causa física.
3. **60% dos incidentes sem rótulo** — descartados.
4. **Sem duração, custo ou clientes afetados** — impossível priorizar por
   impacto financeiro.

---

## Perguntas de entrevista — Checkpoint 2

**O que é cardinalidade e por que ela importa aqui?**
É a quantidade de valores distintos de uma coluna. Importa porque muda o
tratamento: `resource_type` tem 10 categorias e cabe inteiro num gráfico de
barras; `log_feature` tem 331 e precisa de agregação, porque qualquer top-N
esconderia a maior parte da distribuição.

**Por que a média de `volume` não descreve bem os dados?**
Porque a distribuição é fortemente assimétrica à direita — assimetria 10,05.
A média (9,85) é quase 5× a mediana (2), puxada por uma minoria de valores
extremos até 877. A mediana representa o caso típico; a média representa o
efeito dos outliers.

**Por que ranquear localidades por taxa sem corte mínimo dá errado?**
Porque taxa é uma divisão e o denominador pequeno só permite valores extremos:
com 1 incidente, os resultados possíveis são 0% ou 100%. O ranking passa a medir
tamanho de amostra em vez de qualidade da rede. Com 929 localidades avaliadas ao
mesmo tempo, extremos por acaso são praticamente garantidos — é o problema das
comparações múltiplas. A correção é exigir amostra mínima e declarar o corte.

**Volume de incidentes e taxa de gravidade medem a mesma coisa?**
Não. A localidade com mais incidentes no total (85) não aparece no topo do
ranking por taxa. Uma localidade grande gera muitos incidentes de tudo,
inclusive graves, sem que a rede ali seja pior. São perguntas diferentes:
"onde acontece mais coisa?" e "onde a coisa que acontece é pior?".

**Você encontrou algum viés ou limitação que impediria uma conclusão?**
Sim, quatro. A mais importante é a ausência de tempo: sem data não há como
medir tendência, sazonalidade ou tempo de reparo, então qualquer afirmação
sobre "a rede está piorando" seria inventada. E as categorias são anonimizadas,
então nenhuma conclusão causal é possível — só padrão estatístico.
