-- Grão hospede_unico_id. RFM calculado a partir do fim da janela válida
-- (2017-07-31), NUNCA de current_date: a pousada fechou e o relógio de
-- hoje faria todo mundo parecer "inativo há anos".
--   R = dias desde o último check-in   -> quintil, menos dias = nota maior
--   F = nº de reservas                  -> degraus fixos (distribuição muito
--       concentrada em 1; quintil daria notas arbitrárias entre empates)
--   M = soma de valor_total (nulo = 0)  -> quintil
-- Segmento de fidelidade (F é o que define "fiel"):
--   fiel            3+ reservas e R >= 3 (ativo na parte recente da janela)
--   fiel_adormecido 3+ reservas e R <  3
--   recorrente      2 reservas
--   unica_vez       1 reserva
with base as (
    select
        r.hospede_unico_id,
        count(distinct f.reserva) as frequencia,
        coalesce(sum(f.valor_total), 0) as monetario,
        max(f.check_in) as ultima_estadia,
        datediff('day', max(f.check_in), date '2017-07-31') as recencia_dias
    from {{ ref('stg_hospede_resolvido') }} r
    join {{ ref('stg_fato_reserva') }} f using (reserva)
    group by r.hospede_unico_id
),
notas as (
    select
        *,
        6 - ntile(5) over (order by recencia_dias) as nota_r,
        case
            when frequencia >= 6 then 5
            when frequencia >= 4 then 4
            when frequencia = 3 then 3
            when frequencia = 2 then 2
            else 1
        end as nota_f,
        ntile(5) over (order by monetario) as nota_m
    from base
)
select
    *,
    cast(nota_r as varchar) || cast(nota_f as varchar) || cast(nota_m as varchar) as rfm,
    case
        when frequencia >= 3 and nota_r >= 3 then 'fiel'
        when frequencia >= 3 then 'fiel_adormecido'
        when frequencia = 2 then 'recorrente'
        else 'unica_vez'
    end as segmento
from notas
