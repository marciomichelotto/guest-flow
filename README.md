# Guest Flow

Modelagem dimensional (Kimball) de 10 anos de operação real de uma pousada de
praia em Matinhos/PR (2006-2017), a partir dos registros originais do negócio
— planilhas de mapa de ocupação e cadastro de hóspedes, não dado sintético.

**A regra do projeto:** hospedagem, ocupação e diárias são dados reais e
continuam reais. Nada de simulação ou preenchimento de lacuna nessas três
coisas — quando falta dado, o buraco fica documentado, não estimado. Detalhe
completo das decisões, regras de negócio e achados: ver [CLAUDE.md](./CLAUDE.md).

Este projeto substitui uma tentativa anterior que misturava dado real com
campos fabricados (CPF, nacionalidade, endereço) sem marcação — a
reconstrução aqui prioriza rigor sobre completude aparente.

## Achados

5.072 reservas, 2006–2017. Números abaixo saem direto dos marts (`mart_ocupacao_mensal`,
`mart_kpis_reserva`, `mart_hospede_retorno`), sem arredondamento além do já
aplicado no dbt.

**A sazonalidade não é uma variação, é o negócio inteiro.**

| Fase da temporada | Ocupação | RevPAR | ADR |
|---|---|---|---|
| Alta (dez-fev) | 54,7% | R$ 131,49 | R$ 240,51 |
| Média (mar, jul, nov) | 27,5% | R$ 38,22 | R$ 139,06 |
| Baixa (demais meses) | 17,5% | R$ 21,01 | R$ 119,73 |

A diária (ADR) varia só 2x entre alta e baixa — é a ocupação que faz o RevPAR
da alta temporada ser 6,3x o da baixa. A média anual de ~23% de ocupação
esconde essa distribuição por completo.

**13,8% das reservas têm registro conflitante entre mapa e cadastro** — e
continuam na base, marcadas, em vez de excluídas.

| Tipo de divergência | Reservas |
|---|---|
| Quarto | 383 |
| Data | 249 |
| Quarto + data | 67 |
| Sem cadastro correspondente | 2 |

A hospedagem aconteceu; o que diverge é qual das duas fontes registrou o
quarto ou a data certos. Excluir essas 701 reservas subestimaria a operação
real — por isso ficam com `flag_divergencia`, não fora da base.

**Hóspede que volta gasta quase 3x mais que hóspede de primeira vez.**

| Retornou? | Hóspedes únicos | Receita média por hóspede |
|---|---|---|
| Não | 4.186 | R$ 447,55 |
| Sim | 361 (7,9%) | R$ 1.279,92 |

Só 7,9% dos hóspedes voltaram, mas cada um vale 2,9x um hóspede novo — o
segmento mais rentável da base é também o menor.

**84% das reservas se decide com até um mês de antecedência.**

| Antecedência (lead time) | Reservas |
|---|---|
| Até 7 dias | 61,4% |
| 8 a 30 dias | 22,7% |
| 31 a 90 dias | 12,7% |
| Mais de 90 dias | 3,2% |

Pousada de litoral não vive de planejamento antecipado — decisão de curto
prazo é a norma, não a exceção.

**A clientela é regional: 60% das reservas vêm do próprio Paraná.**

| Estado de origem | Reservas | Receita |
|---|---|---|
| PR | 3.029 (59,7%) | R$ 1.243.952,69 |
| SP | 265 | R$ 170.390,42 |
| SC | 121 | R$ 68.914,20 |
| RJ | 51 | R$ 32.401,31 |
| RS | 44 | R$ 17.896,00 |

Penetração fora da região Sul/Sudeste é marginal — qualquer leitura de canal
de aquisição ou campanha precisa considerar que a base histórica é, antes de
tudo, uma clientela de proximidade.

## Stack

Python (extração) → dbt Core → DuckDB local (dev, zero custo) → Snowflake
(alvo eventual). Os models dbt são portáveis entre os dois adapters.

## Estrutura

- `fontes/` — planilhas brutas originais (não versionado, dados reais de hóspedes)
- `scripts/` — parsers de ingestão (`extrai_mapa.py`, `consolida_fontes.py`) e
  carga pro DuckDB (`carrega_duckdb.py`)
- `data/raw/` — saída dos parsers: fatos, dimensões e CSVs de divergência/revisão
  (não versionado — dado real de hóspede)
- `dbt/` — projeto dbt:
  - `models/staging/` — fontes tipadas, sem lógica de negócio
  - `models/intermediate/` — noites vendidas (mapa + cadastro), sem dupla contagem
  - `models/marts/` — `mart_ocupacao_mensal` (ocupação/RevPAR/ADR),
    `mart_kpis_reserva` (lead time, LOS, grupo vs. individual, origem
    geográfica), `mart_hospede_retorno` (taxa de retorno por hóspede único)
  - `tests/` — os 4 testes obrigatórios da seção 8 do CLAUDE.md
  - `guest_flow.duckdb` — banco local (não versionado)
- `airflow/dags/` — orquestração (planejado)
