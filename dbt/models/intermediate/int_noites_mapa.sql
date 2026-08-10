-- Grão reserva x quarto x noite, só mapa_confirmado. Vem de room_nights
-- (fato atômico) — NUNCA reconstruído a partir de check_in/check_out de
-- estadias, porque pra reserva com suspeita_num_reaproveitado esse
-- intervalo é uma "caixa" que cobre da primeira à última aparição do
-- número reaproveitado, não uma estadia contínua (achado real: 120
-- estadias, 701 noites-fantasma se explodidas ingenuamente).
select
    rn.reserva,
    rn.quarto,
    rn.data_noite,
    e.valor_alocado / nullif(e.diarias, 0) as valor_noite
from {{ ref('stg_room_nights') }} rn
left join {{ ref('stg_estadias') }} e
    on e.reserva = rn.reserva and e.quarto = rn.quarto
