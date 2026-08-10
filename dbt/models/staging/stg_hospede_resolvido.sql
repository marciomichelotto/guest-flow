select
    reserva,
    hospede_unico_id,
    metodo_match,
    n_reservas_do_hospede
from {{ source('raw', 'hospede_resolvido') }}
