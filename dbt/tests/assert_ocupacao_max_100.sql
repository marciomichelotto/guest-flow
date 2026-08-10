-- CLAUDE.md §8, teste 3: ocupação nunca passa de 100%.
select * from {{ ref('mart_ocupacao_mensal') }}
where ocupacao_pct > 100
