-- CLAUDE.md §8, teste 1: nenhum fato fora da janela válida (2006-12-01 a
-- 2017-07-31). Falha (retorna linha) = tem dado fora da janela.
select reserva, check_in
from {{ source('raw', 'fato_reserva') }}
where check_in::date not between date '2006-12-01' and date '2017-07-31'

union all

select reserva, data_noite
from {{ source('raw', 'room_nights') }}
where data_noite::date not between date '2006-12-01' and date '2017-07-31'
