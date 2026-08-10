select
    reserva,
    quarto,
    data_noite,
    temporada,
    fase_temporada
from {{ source('raw', 'room_nights') }}
