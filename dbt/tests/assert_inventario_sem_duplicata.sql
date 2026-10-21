-- Inventário tem que ser único por ano x mes x quarto. Duplicata multiplica
-- noites no join com o inventário (achado real: mar/2013, +113 room-nights).
select ano, mes, quarto, count(*) as n
from {{ ref('stg_inventario_mensal') }}
group by ano, mes, quarto
having count(*) > 1
