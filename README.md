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
