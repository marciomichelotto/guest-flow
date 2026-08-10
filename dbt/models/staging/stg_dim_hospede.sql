select
    hospede_id,
    reserva,
    nome,
    cidade,
    estado,
    sem_cadastro
from {{ source('raw', 'dim_hospede') }}
