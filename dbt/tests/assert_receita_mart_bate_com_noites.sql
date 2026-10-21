-- Reconciliação: receita do mart mensal == soma da receita por noite, e nunca
-- maior que o valor total declarado nas reservas.
with m as (select sum(receita) as r from {{ ref('mart_ocupacao_mensal') }}),
     n as (select sum(valor_noite) as r from {{ ref('int_noites_completo') }}),
     f as (select sum(valor_total) as r from {{ ref('stg_fato_reserva') }})
select m.r as mart, n.r as noites, f.r as declarado
from m, n, f
where abs(m.r - n.r) > 1
   or m.r > f.r + 1
