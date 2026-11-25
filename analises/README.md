# Análises exploratórias — Guest Flow

Exercícios de análise de dados sobre o histórico real da pousada (dez/2006 a jul/2017).
Cada linha abaixo resume um exercício: o que foi feito, o resultado e o principal cuidado.

| # | Exercício | Script | Resultado | Cuidado |
|---|---|---|---|---|
| 1 | Histograma de diárias e boxplot do valor por temporada | `exercicio_eda.py` | 49% das estadias têm 1 diária e 85% têm até 3. A mediana do valor da reserva foi de R$ 150–300 até 2013/14 e chegou a R$ 430 em 2016/17. | Valor em R$ nominais (inclui inflação). 110 reservas sem valor ficaram de fora. |
| 2 | Mann-Whitney SP × PR e IC bootstrap da diária por temporada | `exercicio_inferencia.py` | Reserva de SP vale mais (mediana R$ 336 × R$ 236, p < 0,001), mas por diária a diferença some (R$ 158 × R$ 153). A diária média subiu de R$ 120 (2007/08) para R$ 254 (2016/17). | Estado conhecido em 4.198 de 4.962 reservas. |
| 3 | Coorte, RFM e deduplicação de hóspedes | `exercicio_coorte_rfm.py` | 4.547 → 4.385 hóspedes únicos com o nome como terceira chave. Só 2–6% voltam no ano seguinte. 104 hóspedes fiéis (2,4%) geram 11,7% da receita. | Deduplicação é aproximação: homônimos e troca de contato. |
| 4 | Previsão de ocupação: baseline × Prophet | `exercicio_previsao.py`, `exercicio_previsao_janeiro.py` | Baseline "mesmo mês do ano anterior": MAE 10,3 p.p. Prophet com Carnaval e Réveillon: 9,6. Com sazonalidade multiplicativa: 8,5 contra 10,8 da baseline em 60 meses (−22%). | Janeiro continua com erro alto em qualquer modelo. |
| 5 | Prever o valor da reserva | `exercicio_ml_valor.py` | MAE: mediana R$ 463, linear R$ 255, linear em log R$ 173, **LightGBM R$ 164** (R² 0,81). | LightGBM subestima as temporadas mais novas (não extrapola a alta de preços). |
| 6 | Prever se o hóspede volta | `exercicio_ml_retorno.py` | AUC de 0,47 a 0,49: nenhum modelo supera o acaso. | O rótulo depende da deduplicação. Resultado negativo registrado. |
| 7 | Clusterização K-Means de reservas | `exercicio_cluster.py` | 5 perfis estáveis: família com criança (35% da receita), casal no verão (33%), escapada de fim de semana, casal no meio da semana, grupo grande (1,7% das reservas, 10% da receita). | Silhouette fraca (0,28). "Casal" é inferência. |
| 8 | Elasticidade-preço e simulação na baixa temporada | `exercicio_elasticidade.py` | Elasticidade entre +0,16 e −0,90 conforme o modelo. A receita varia só ±3% para preços de −30% a +40% no cenário central. | Não identificável com dados históricos. Só um teste real resolveria. |

## Como reproduzir

Os scripts leem `data/raw/` e `dbt/guest_flow.duckdb`, que **não são versionados** (dados reais de hóspedes).
Para gerar esses dados:

```bash
python scripts/consolida_fontes.py --entrada ./fontes --saida ./data/raw
python scripts/carrega_duckdb.py --entrada data/raw --saida dbt/guest_flow.duckdb
cd dbt && dbt run && dbt test
python analises/exercicio_eda.py        # e assim por diante
```

Bibliotecas: pandas, seaborn, matplotlib, scipy, scikit-learn, lightgbm, prophet, statsmodels, duckdb.
Não rode o Prophet com `python -X utf8` no Windows: o cmdstanpy quebra ao ler a saída do `where.exe`.

Os models dbt relacionados estão em `dbt/models/marts/`: `mart_coorte_hospede` e `mart_hospede_rfm`.
