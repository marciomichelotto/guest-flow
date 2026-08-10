-- so_cadastro: sem stitching por min/max (check_in/check_out vêm direto de
-- uma linha só do cadastro), então diarias == (check_out - check_in)
-- sempre — explodir o intervalo aqui é seguro, ao contrário do mapa.
select
    e.reserva,
    e.quarto,
    unnest(generate_series(e.check_in, e.check_out - interval 1 day, interval 1 day)) as data_noite,
    e.valor_alocado / nullif(e.diarias, 0) as valor_noite
from {{ ref('stg_estadias') }} e
where e.origem_dado = 'so_cadastro'
