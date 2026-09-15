-- so_cadastro: sem stitching por min/max (check_in/check_out vêm direto de
-- uma linha só do cadastro), então diarias == (check_out - check_in)
-- sempre — explodir o intervalo aqui é seguro, ao contrário do mapa.
--
-- CTE recursiva em vez de generate_series/unnest: generate_series de DATE é
-- sintaxe do DuckDB, não roda no Snowflake. Recursão dia a dia é portável
-- entre os dois e o volume (subconjunto so_cadastro de ~5.500 estadias) não
-- justifica uma tabela calendário só pra isso.
with recursive noites as (
    select
        e.reserva,
        e.quarto,
        e.check_in as data_noite,
        e.check_out,
        e.valor_alocado,
        e.diarias
    from {{ ref('stg_estadias') }} e
    where e.origem_dado = 'so_cadastro'

    union all

    select
        n.reserva,
        n.quarto,
        n.data_noite + interval '1 day',
        n.check_out,
        n.valor_alocado,
        n.diarias
    from noites n
    where n.data_noite + interval '1 day' < n.check_out
)
select
    reserva,
    quarto,
    data_noite,
    valor_alocado / nullif(diarias, 0) as valor_noite
from noites
