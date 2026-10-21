{{ config(severity='warn') }}
-- Reserva sem valor (nulo ou 0) puxa ADR/RevPAR pra baixo, porque as noites
-- entram no denominador sem receita. WARN se passar de 3% das reservas.
select count(*) as sem_valor, (select count(*) from {{ ref('stg_fato_reserva') }}) as total
from {{ ref('stg_fato_reserva') }}
where coalesce(valor_total, 0) = 0
having count(*) > 0.03 * (select count(*) from {{ ref('stg_fato_reserva') }})
