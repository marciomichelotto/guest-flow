select reserva, check_in, check_out
from {{ ref('stg_fato_reserva') }}
where check_out <= check_in
union all
select reserva, check_in, check_out
from {{ ref('stg_estadias') }}
where check_out <= check_in
