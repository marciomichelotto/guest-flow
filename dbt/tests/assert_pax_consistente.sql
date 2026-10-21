-- pax_total = adultos + crianças pagantes + crianças free; pagante nunca > total.
select reserva, pax_total, pax_pagante
from {{ ref('stg_fato_reserva') }}
where pax_total <> pax_adulto + pax_crianca_pag + pax_crianca_free
   or pax_pagante > pax_total
   or pax_total < 0
