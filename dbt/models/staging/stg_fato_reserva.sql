select
    reserva,
    hospede_id,
    check_in::date as check_in,
    check_out::date as check_out,
    quartos,
    n_quartos,
    diarias_total,
    data_reserva::date as data_reserva,
    valor_total,
    pax_adulto,
    pax_crianca_pag,
    pax_crianca_free,
    pax_total,
    pax_pagante,
    flag_divergencia,
    tipo_divergencia,
    origem_dado
from {{ source('raw', 'fato_reserva') }}
