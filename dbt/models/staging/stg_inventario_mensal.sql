-- DISTINCT: o seed do proprietário duplicou mar/2013 (24 linhas pra 15
-- quartos). Sem isso o join em int_noites_completo multiplica as noites do
-- mês (+113 room-nights e receita inflada). Ver tests/assert_inventario_sem_duplicata.sql.
select distinct
    ano,
    mes,
    quarto,
    temporada,
    origem
from {{ source('raw', 'inventario_mensal') }}
