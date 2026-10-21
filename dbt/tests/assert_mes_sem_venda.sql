{{ config(severity='warn') }}
-- Volume mínimo: mês com inventário e zero noite vendida em alta temporada
-- (dez–fev) é suspeito de lacuna de dados, não de demanda zero.
select ano, mes
from {{ ref('mart_ocupacao_mensal') }}
where room_nights_vendidos = 0 and fase_temporada = 'alta'
