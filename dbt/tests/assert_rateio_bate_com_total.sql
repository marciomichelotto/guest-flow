-- CLAUDE.md §11: sum(valor_alocado) por reserva == fato_reserva.valor_total.
-- Só compara reserva com valor_total preenchido (não fabrica pra quem não tem).
select
    e.reserva,
    round(sum(e.valor_alocado), 2) as alocado,
    round(f.valor_total, 2) as valor_total
from {{ source('raw', 'estadias') }} e
join {{ source('raw', 'fato_reserva') }} f using (reserva)
where e.valor_alocado is not null
group by e.reserva, f.valor_total
having round(sum(e.valor_alocado), 2) != round(f.valor_total, 2)
