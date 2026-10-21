{{ config(severity='warn') }}
-- WARN: são candidatos a revisão manual, não prova de erro. Valor nunca negativo; diária média fora de R$ 20–2.000 por quarto-noite é
-- quase certamente erro de digitação (zero/valor ausente é tratado em
-- assert_valor_ausente_limitado).
select reserva, valor_total, diarias_total, valor_total / nullif(diarias_total, 0) as valor_diaria
from {{ ref('stg_fato_reserva') }}
where valor_total < 0
   or (valor_total > 0 and valor_total / nullif(diarias_total, 0) not between 20 and 2000)
