select
    ano,
    mes,
    quarto,
    temporada,
    origem
from {{ source('raw', 'inventario_mensal') }}
