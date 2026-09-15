-- Grão ano x mes. KPIs mais importantes do projeto: ocupação, RevPAR, ADR.
-- Só existe linha pro mês que tem inventário (mapa ou seed do
-- proprietário) — mês sem denominador fica de fora, não estimado.
with vendido as (
    select
        ano,
        mes,
        count(*) as room_nights_vendidos,
        sum(valor_noite) as receita
    from {{ ref('int_noites_completo') }}
    group by ano, mes
),

disponivel as (
    select
        ano,
        mes,
        count(distinct quarto) as quartos,
        max(temporada) as temporada,
        -- make_date é DuckDB; date_from_parts é Snowflake. Construção via
        -- string ISO ('AAAA-MM-01') é portável entre os dois.
        extract(day from last_day(cast(ano || '-' || lpad(cast(mes as varchar), 2, '0') || '-01' as date))) as dias_no_mes
    from {{ ref('stg_inventario_mensal') }}
    group by ano, mes
)

select
    d.ano,
    d.mes,
    d.temporada,
    case when d.mes in (12, 1, 2) then 'alta'
         when d.mes in (3, 7, 11) then 'media'
         else 'baixa' end as fase_temporada,
    d.quartos,
    d.dias_no_mes,
    d.quartos * d.dias_no_mes as disponiveis,
    coalesce(v.room_nights_vendidos, 0) as room_nights_vendidos,
    coalesce(v.receita, 0) as receita,
    round(100.0 * coalesce(v.room_nights_vendidos, 0) / (d.quartos * d.dias_no_mes), 1) as ocupacao_pct,
    round(coalesce(v.receita, 0) / (d.quartos * d.dias_no_mes), 2) as revpar,
    round(coalesce(v.receita, 0) / nullif(v.room_nights_vendidos, 0), 2) as adr
from disponivel d
left join vendido v using (ano, mes)
order by d.ano, d.mes
