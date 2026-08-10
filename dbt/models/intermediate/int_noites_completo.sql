-- Noite vendida só entra se o quarto existir no inventário daquele mês
-- (CLAUDE.md §8 teste 2) — evita inflar ocupação com quarto órfão
-- (achado real: célula corrompida em mai/2015 antes de ser rejeitada).
with noites as (
    select * from {{ ref('int_noites_mapa') }}
    union all
    select * from {{ ref('int_noites_so_cadastro') }}
)
select
    n.reserva,
    n.quarto,
    n.data_noite,
    extract(year from n.data_noite) as ano,
    extract(month from n.data_noite) as mes,
    n.valor_noite
from noites n
inner join {{ ref('stg_inventario_mensal') }} inv
    on inv.ano = extract(year from n.data_noite)
   and inv.mes = extract(month from n.data_noite)
   and inv.quarto = n.quarto
