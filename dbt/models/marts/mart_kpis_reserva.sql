-- Grão reserva. Lead time, LOS, grupo vs individual, origem geográfica —
-- KPIs que não precisam do denominador de inventário (ao contrário de
-- ocupação/RevPAR), então cobrem as 5.072 reservas inteiras, 2006-2017.
with base as (
    select
        f.reserva,
        f.hospede_id,
        f.check_in,
        f.check_out,
        f.diarias_total,
        f.data_reserva,
        f.valor_total,
        f.n_quartos,
        f.pax_total,
        f.pax_pagante,
        f.origem_dado,
        h.estado,
        h.cidade,
        case when extract(month from f.check_in) >= 12
             then extract(year from f.check_in)
             else extract(year from f.check_in) - 1
        end as ano_ini_temporada
    from {{ ref('stg_fato_reserva') }} f
    left join {{ ref('stg_dim_hospede') }} h using (reserva)
)
select
    reserva,
    hospede_id,
    check_in,
    check_out,
    extract(year from check_in) as ano_civil,
    extract(month from check_in) as mes_civil,
    ano_ini_temporada || '/' || right(cast(ano_ini_temporada + 1 as varchar), 2) as temporada,
    case when extract(month from check_in) in (12, 1, 2) then 'alta'
         when extract(month from check_in) in (3, 7, 11) then 'media'
         else 'baixa' end as fase_temporada,
    diarias_total,
    valor_total,
    round(valor_total / nullif(diarias_total, 0), 2) as valor_diaria_medio,
    coalesce(n_quartos, 1) > 1 as is_grupo,
    coalesce(n_quartos, 1) as n_quartos,
    pax_total,
    pax_pagante,
    estado,
    cidade,
    data_reserva,
    -- data_reserva tem artefato de parsing de data do Excel em alguns
    -- registros (ex.: reserva 607 → "0009-09-10", ano inválido), que gera
    -- lead_dias de centenas de milhares de dias. Não é uma reserva feita
    -- com séculos de antecedência — é lixo de parsing, então lead_dias e
    -- lead_faixa ficam null pra essas linhas (a reserva em si continua na
    -- mart; só a métrica derivada de lead time fica indisponível).
    case
        when data_reserva is null then null
        when datediff('day', data_reserva, check_in) not between 0 and 730 then null
        else datediff('day', data_reserva, check_in)
    end as lead_dias,
    case
        when data_reserva is null then null
        when datediff('day', data_reserva, check_in) not between 0 and 730 then null
        when datediff('day', data_reserva, check_in) <= 7 then '<=7d'
        when datediff('day', data_reserva, check_in) <= 30 then '8-30d'
        when datediff('day', data_reserva, check_in) <= 90 then '31-90d'
        else '>90d'
    end as lead_faixa,
    origem_dado
from base
