-- Reconciliação com o cadastro: nenhuma reserva sem valor_total pode ter
-- valor_alocado > 0 (não se fabrica receita).
select e.reserva, sum(e.valor_alocado) as alocado
from {{ ref('stg_estadias') }} e
join {{ ref('stg_fato_reserva') }} f using (reserva)
where coalesce(f.valor_total, 0) = 0
group by e.reserva
having coalesce(sum(e.valor_alocado), 0) > 0
