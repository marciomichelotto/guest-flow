select
    estadia_id,
    reserva,
    hospede_id,
    quarto,
    check_in::date as check_in,
    check_out::date as check_out,
    diarias,
    temporada,
    valor_alocado,
    metodo_alocacao,
    origem_dado,
    suspeita_num_reaproveitado
from {{ source('raw', 'estadias') }}
