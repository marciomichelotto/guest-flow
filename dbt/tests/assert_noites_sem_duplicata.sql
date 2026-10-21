-- Nenhuma (reserva, quarto, noite) pode aparecer duas vezes no fato de noites.
select reserva, quarto, data_noite, count(*) as n
from {{ ref('int_noites_completo') }}
group by reserva, quarto, data_noite
having count(*) > 1
