{{ config(severity='warn') }}
-- Um quarto não vende duas vezes na mesma noite. Aparecer aqui indica nº de
-- reserva reaproveitado, erro de digitação no mapa ou cadastro x mapa em
-- conflito. WARN (não erro): é o dado real; o teste mede o tamanho do problema.
select quarto, data_noite, count(distinct reserva) as reservas
from {{ ref('int_noites_completo') }}
group by quarto, data_noite
having count(distinct reserva) > 1
