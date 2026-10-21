{{ config(severity='warn') }}
-- WARN: as 271 reservas só-cadastro sem quarto não têm estadia (pendência conhecida).
-- Toda reserva do mart_kpis tem pelo menos uma estadia (reserva x quarto).
select k.reserva
from {{ ref('mart_kpis_reserva') }} k
left join {{ ref('stg_estadias') }} e using (reserva)
where e.reserva is null
