# Learning Notes

Caderno de revisão do projeto. Cada conceito em quatro partes: **o que é**,
**como pensar nele**, **onde está no projeto** e um **exemplo**.

Para a apresentação do projeto, veja o [README](README.md).

---

## O caminho dos dados

```
CSV bruto  →  Pandas  →  Limpeza  →  Parquet  →  SQLite  →  SQL  →  Gráficos  →  Dashboard
```

Um comando refaz tudo: `python run_pipeline.py`.

| Etapa | Arquivo | O que faz |
|---|---|---|
| 1 | `src/data_loader.py` | lê os CSVs e confere se estão íntegros |
| 2 | `src/cleaning.py` | filtra os 7.381 e converte texto em número |
| 3 | `src/transformation.py` | organiza em 9 tabelas e salva em Parquet |
| 4 | `src/database.py` | cria o SQLite e carrega os dados |
| 5 | `sql/analysis_queries.sql` | 7 consultas que respondem as perguntas |
| 6 | `src/visualization.py` | transforma o resultado em gráfico |
| 7 | `dashboard/app.py` | dashboard interativo |

---

# PYTHON E PANDAS

## DataFrame

### O que é?
Uma tabela na memória do Python: linhas, colunas e nomes de coluna.

### Pense assim
É uma aba de Excel que você manipula escrevendo, em vez de clicando.

### No nosso projeto
Tudo passa por DataFrame — a leitura do CSV, a limpeza, o resultado das
consultas SQL e os dados do dashboard.

### Exemplo
```python
df = pd.read_csv("train.csv")
df.shape        # (7381, 3) -> linhas, colunas
df.head()       # primeiras 5 linhas
```

---

## Filtrar linhas

### O que é?
Ficar só com as linhas que atendem a uma condição.

### Pense assim
É o "Filtro" do Excel. A condição vira uma lista de Verdadeiro/Falso, e o pandas
mantém só as linhas Verdadeiras.

### No nosso projeto
É como os filtros do dashboard funcionam.

### Exemplo
```python
graves = df[df["fault_severity"] == 2]                 # uma condição
alguns = df[df["severity_type_name"].isin(["A", "B"])] # vários valores aceitos
```

---

## groupby

### O que é?
Agrupa linhas iguais e calcula um resumo por grupo.

### Pense assim
Você tem 7.381 fichas na mesa. `groupby("gravidade")` faz três pilhas. Aí você
conta cada pilha.

### No nosso projeto
É o coração de `src/metrics.py`, que calcula a taxa de gravidade por localidade,
por evento e por recurso.

### Exemplo
```python
df.groupby("location_name").agg(
    incidentes=("fault_severity", "size"),
    graves=("_grave", "sum"),
)
```

> É o mesmo que o `GROUP BY` do SQL. Duas linguagens, uma ideia.

---

## Tipos declarados vs inferidos

### O que é?
Dizer ao pandas qual o tipo de cada coluna, em vez de deixá-lo adivinhar.

### Pense assim
Adivinhar é silencioso. Se um `id` vier com lixo, o pandas transforma a coluna
inteira em texto sem avisar — e os JOINs quebram lá na frente, longe da causa.

### No nosso projeto
`src/data_loader.py` declara o tipo de cada coluna na leitura.

### Exemplo
```python
pd.read_csv(path, dtype={"id": "int64", "fault_severity": "int8"})
```

---

## raw vs processed

### O que é?
`data/raw` é o dado original, nunca alterado. `data/processed` é o resultado do
nosso tratamento.

### Pense assim
`raw` é o negativo da foto. `processed` é a revelação. Se a revelação sair
errada, você refaz a partir do negativo.

### No nosso projeto
`data/raw` está versionado no Git. `data/processed` está no `.gitignore` porque
é gerado — assim como `database/telecom.db`.

### Exemplo
```
data/raw/train.csv          ← nunca é escrito pelo código
data/processed/*.parquet    ← apagado e refeito a cada execução
```

---

## Parquet

### O que é?
Formato de arquivo para tabelas, que guarda os tipos junto com os dados.

### Pense assim
CSV é texto puro: o `int8` vira texto e volta como `int64`. Parquet lembra que
era `int8`.

### No nosso projeto
`data/processed/` usa Parquet. `data/raw/` continua em CSV, porque ali interessa
poder abrir e ler à mão.

### Exemplo
```python
df.to_parquet("incidents.parquet", index=False)
```

---

# SQL E BANCO DE DADOS

## Banco de dados / SQLite

### O que é?
Um arquivo que guarda tabelas e responde perguntas escritas em SQL.

### Pense assim
PostgreSQL e MySQL são restaurantes: precisam de cozinha, funcionário, estar
abertos. SQLite é uma marmita — você abre e come. Para 7.381 linhas, marmita
resolve.

### No nosso projeto
`database/telecom.db`. O Python já vem com `sqlite3`, então não instalamos nada.

### Exemplo
```python
import sqlite3
conn = sqlite3.connect("telecom.db")
conn.execute("PRAGMA foreign_keys = ON")   # no SQLite isso vem DESLIGADO
```

---

## PRIMARY KEY e FOREIGN KEY

### O que é?
`PRIMARY KEY` identifica a linha de forma única. `FOREIGN KEY` diz que uma
coluna aponta para outra tabela.

### Pense assim
A primary key é o CPF: não existem dois iguais. A foreign key é o banco recusando
um endereço de cidade que não existe.

### No nosso projeto
`incident_id` é primary key. `location_id` é foreign key para `locations` — o
banco recusa um incidente numa localidade inexistente.

### Exemplo
```sql
CREATE TABLE incidents (
    incident_id INTEGER PRIMARY KEY,
    location_id INTEGER NOT NULL,
    FOREIGN KEY (location_id) REFERENCES locations (location_id)
);
```

---

## Star schema: fato, dimensão e ponte

### O que é?
Uma forma de organizar tabelas. No centro, a tabela **fato** (o que aconteceu).
Em volta, as **dimensões** (o contexto). Quando a relação é "um para muitos",
entra uma tabela **ponte**.

### Pense assim
- **Fato** = a nota fiscal.
- **Dimensão** = o cadastro do cliente, o cadastro do produto.
- **Ponte** = a lista de itens da nota, porque uma nota tem vários produtos.

### No nosso projeto
`incidents` é o fato. Um incidente pode ter até 9 eventos — por isso existe
`incident_events` em vez de nove colunas.

### Exemplo
```
incidents (7.381)  ← 1 linha por incidente
   ↓
incident_events (12.468)  ← 1 linha por par (incidente, evento)
   ↓
event_types (49)  ← 1 linha por tipo de evento
```

> **Por que `severity_type` fica no fato e não numa ponte?** Porque é 1:1 —
> cada incidente tem exatamente um. Ponte só se justifica em 1:N.

---

## SELECT, WHERE, GROUP BY, ORDER BY

### O que é?
As quatro palavras que resolvem a maioria das consultas.

### Pense assim
`SELECT` = o que mostrar. `FROM` = de onde. `WHERE` = quais linhas.
`GROUP BY` = juntar em pilhas. `ORDER BY` = em que ordem.

### No nosso projeto
`sql/analysis_queries.sql`, consulta `gravidade_distribuicao`.

### Exemplo
```sql
SELECT fault_severity, COUNT(*) AS total
FROM incidents
GROUP BY fault_severity
ORDER BY fault_severity;
```

---

## JOIN

### O que é?
Combina duas tabelas usando uma coluna em comum.

### Pense assim
Uma lista de chamados tem o código do técnico (`T07`). Outra lista diz
`T07 = Maria`. O JOIN junta as duas para o relatório mostrar "Maria".

### No nosso projeto
O banco guarda `location_id = 118`; o JOIN traz `"location 118"` da tabela
`locations`.

### Exemplo
```sql
SELECT i.incident_id, l.location_name
FROM incidents AS i
JOIN locations AS l ON i.location_id = l.location_id;
```

> Cada JOIN **acrescenta colunas** à tabela que está sendo montada.

---

## HAVING vs WHERE

### O que é?
`WHERE` filtra **linhas**, antes de agrupar. `HAVING` filtra **grupos**, depois.

### Pense assim
`WHERE` escolhe quais fichas vão para a mesa. `HAVING` escolhe quais **pilhas**
ficam na mesa.

### No nosso projeto
Descartar localidades com menos de 10 incidentes só é possível depois de contar
— e contar só acontece no `GROUP BY`. Por isso `HAVING`.

### Exemplo
```sql
GROUP BY l.location_name
HAVING COUNT(*) >= 10
```

---

## CASE WHEN

### O que é?
Um "se… então" dentro do SQL.

### Pense assim
Transforma cada linha em 1 ou 0. Somando os 1s, você conta só o subconjunto que
interessa — enquanto `COUNT(*)` conta tudo.

### No nosso projeto
É assim que a taxa de gravidade é calculada em SQL.

### Exemplo
```sql
SUM(CASE WHEN fault_severity = 2 THEN 1 ELSE 0 END) AS graves
```

> **Cuidado:** use `100.0`, não `100`. Com inteiros, o SQLite trunca a divisão e
> devolve `0` em vez de `13.3`.

---

## WITH (CTE)

### O que é?
Uma tabela temporária que existe só durante a consulta.

### Pense assim
"Primeiro calcule isso, depois use o resultado." Deixa a consulta legível de cima
para baixo, em vez de aninhada.

### No nosso projeto
`volume_log_vs_gravidade` soma o volume por incidente e só depois compara por
gravidade.

### Exemplo
```sql
WITH volume_por_incidente AS (
    SELECT incident_id, SUM(volume) AS volume_total
    FROM incident_log_features
    GROUP BY incident_id
)
SELECT AVG(volume_total) FROM volume_por_incidente;
```

---

# ANÁLISE

## Taxa vs contagem

### O que é?
Contagem responde "onde acontece mais coisa?". Taxa responde "onde a coisa que
acontece é pior?". São perguntas diferentes.

### Pense assim
Um hospital grande tem mais óbitos que um pequeno. Isso não o torna pior — ele
atende mais gente.

### No nosso projeto
A localidade com **mais** incidentes (`location 821`, 85) **não** é a de pior
taxa (`location 1100`, 73,3%).

### Exemplo
```
location 821   85 incidentes,  taxa média   → grande, não problemática
location 1100  45 incidentes,  73,3% graves → menor, mas crítica
```

---

## Amostra mínima

### O que é?
Exigir um número mínimo de casos antes de confiar numa taxa.

### Pense assim
Jogue uma moeda **uma vez** e dê cara: taxa de 100%. Isso não é moeda viciada, é
pouca jogada. Com denominador 1, os únicos resultados possíveis são 0% ou 100%.

### No nosso projeto
Sem corte, 14 localidades marcam 100% de gravidade — 10 delas com **um único
incidente**. Com corte de 10, o topo vira `location 1100` (33 graves em 45).

O mesmo vale para gráficos: barras com menos de 50 incidentes ficam com cor
apagada, para o olho não dar a elas peso que não merecem.

### Exemplo
```sql
HAVING COUNT(*) >= 10
```

> **Bônus para entrevista:** o top 5 é idêntico com corte 10 e com corte 30. Isso
> se chama **análise de sensibilidade** — se a conclusão não muda quando você
> mexe num parâmetro arbitrário, ela é robusta.

---

## As duas armadilhas deste dataset

**1. `severity_type` não é `fault_severity`.**

| | `fault_severity` | `severity_type` |
|---|---|---|
| O que é | o **resultado** do incidente | o **alerta** que o log emitiu |
| Quando | depois | no começo |
| Papel | o que queremos explicar | o que usamos para explicar |

É a diferença entre "o alarme tocou" e "a casa pegou fogo". Reportar um como o
outro produz números que somam 100% e conclusões inteiramente falsas.

**2. As categorias são anonimizadas.** Sabemos que `event_type 11` aparece em
3.068 incidentes, mas não o que ele é fisicamente. Logo: padrões estatísticos,
nunca relações de causa.

---

# DASHBOARD

## Streamlit

### O que é?
Uma biblioteca que transforma um script Python em site, sem HTML nem JavaScript.

### Pense assim
É Python rodando dentro de uma página. Ao mexer num filtro, o Streamlit
**executa o script inteiro de novo** com o novo valor.

### No nosso projeto
`dashboard/app.py`. Os dados vêm do SQLite via `src/database.py`.

### Exemplo
```python
st.title("Telecom Network Operations Analytics")
opcao = st.sidebar.multiselect("Gravidade", [0, 1, 2])
st.plotly_chart(fig)
```

---

## @st.cache_data

### O que é?
Guarda o resultado de uma função para não recalculá-la.

### Pense assim
Como o Streamlit roda o script inteiro a cada clique, sem cache o banco seria
lido de novo toda vez que você mexesse num filtro.

### No nosso projeto
As três funções de carregamento do dashboard. SQL faz a junção pesada uma vez;
pandas cuida da interação.

### Exemplo
```python
@st.cache_data
def load_incidents():
    return run_query("SELECT ...")
```

---

# QUALIDADE

## Validação em camadas

### O que é?
Duas verificações que fazem perguntas diferentes.

### Pense assim
- `validate_raw_data()` pergunta: **"o dado que recebi está íntegro?"**
- `validate_clean_data()` pergunta: **"eu estraguei o dado?"**

Um bug na minha conversão passaria tranquilamente pela primeira.

### No nosso projeto
O dataset chega sem nulos e sem duplicatas — a validação sempre passa. Ela existe
como rede de segurança: se alguém trocar o dataset, o pipeline **para** em vez de
produzir número errado em silêncio.

---

## Testes

### O que é?
Código que verifica o código. `pytest` roda tudo e diz o que quebrou.

### Pense assim
Um validador que nunca foi testado no caminho de falha é decorativo. Por isso
vários testes **corrompem o dado de propósito** e exigem que o programa reclame.

### No nosso projeto
61 testes. Os mais importantes:

| Teste | O que protege |
|---|---|
| `test_pandas_concorda_com_sql_*` | README e dashboard darem números diferentes |
| `test_banco_recusa_*` | o banco aceitar dado inválido |
| `test_detecta_*` | a validação deixar passar dado corrompido |

### Exemplo
```bash
pytest
```

---

# PERGUNTAS DE ENTREVISTA

**Por que SQLite e não PostgreSQL?**
São 7.381 linhas, um usuário, sem escrita concorrente. SQLite é um arquivo, vem
com o Python e roda em qualquer máquina após um clone. PostgreSQL exigiria
servidor sem trazer nenhum benefício. Migraria se houvesse muitos usuários
escrevendo ao mesmo tempo ou volume muito maior.

**Por que `data/raw` está no Git e `database/telecom.db` não?**
`raw` é a fonte; o `.db` é gerado a partir dela pelo `run_pipeline.py`. Versionar
um artefato gerado cria risco de ele divergir da fonte, e como é binário o Git
guardaria uma cópia inteira a cada mudança.

**Qual a diferença entre `WHERE` e `HAVING`?**
`WHERE` filtra linhas antes do agrupamento; `HAVING` filtra grupos depois.
`COUNT(*)` só existe após o `GROUP BY`, então filtrar por contagem exige `HAVING`.

**Por que usar taxa em vez de contagem no ranking de localidades?**
Porque a base é desbalanceada — só 9,84% dos incidentes são graves. Um ranking
por contagem apenas reproduziria o ranking de volume total. Mas taxa exige
amostra mínima, senão uma localidade com 1 incidente grave em 1 marca 100%.

**Como você garante que o pipeline é reproduzível?**
Versões fixadas no `requirements.txt`, `data/raw` versionado e imutável, um único
ponto de entrada (`run_pipeline.py`) em vez de células de notebook em ordem
imprevisível, e validação que falha alto se o dado de entrada mudar.

**O README e o dashboard mostram o mesmo número. Como você garante isso?**
A regra vive em `src/metrics.py`, e há teste comparando o resultado em pandas
com o resultado da consulta SQL. Se alguém alterar um dos dois, o teste quebra.

**O que aconteceria se o volume crescesse 100 vezes?**
Seriam ~740 mil incidentes e ~5,8 milhões de linhas na maior ponte. Pandas ainda
aguentaria, mas com folga curta. Eu leria em blocos, carregaria no banco em lotes
e moveria as agregações para SQL. Acima disso, trocaria o SQLite — não por
tamanho, mas por concorrência de escrita.

**Que limitação do dataset te impediu de fazer alguma análise?**
Não existe data nem hora em nenhum arquivo. Isso elimina tendência, sazonalidade
e tempo de reparo. Preferi declarar a limitação no README a inventar uma linha do
tempo a partir do `id`, que não tem ordem documentada.

---

# ERROS QUE COMETI (e o que aprendi)

**Nomeei um script de `inspect.py`.** O Python coloca a pasta do script no início
do caminho de busca, então `import inspect` achou o meu arquivo em vez do módulo
da biblioteca padrão, e o numpy quebrou. Nunca dar a um arquivo o nome de um
módulo da stdlib.

**Um gráfico que mentia visualmente.** No ranking de recursos, `resource_type 5`
(100% de graves, **4 incidentes**) virou a maior barra do gráfico. O aviso no
subtítulo não resolvia — o olho lê a barra antes do texto. Solução: cor apagada
para amostras pequenas.

**Seta verde para "incidentes graves".** O Streamlit desenha variação positiva em
verde por padrão, sugerindo melhora. Corrigido com `delta_color="inverse"`.

**Arredondar antes de comparar.** Guardei a taxa base como `9.84` e comparei com
o valor real `9.8362`, exibindo `-0.00 p.p.` sem filtro nenhum aplicado.
Arredondar é para exibição, não para cálculo.
