-- CLAUDE.md §8, teste 2: todo quarto vendido existe no inventário daquele
-- mês. Equivalente ao quartos_orfaos.csv do pipeline Python (hoje: 0).
select rn.reserva, rn.quarto, rn.data_noite
from {{ source('raw', 'room_nights') }} rn
left join {{ source('raw', 'inventario_mensal') }} inv
  on inv.ano = extract(year from rn.data_noite::date)
 and inv.mes = extract(month from rn.data_noite::date)
 and inv.quarto = rn.quarto
where inv.quarto is null
