-- Grão coorte_ano x anos_depois. Coorte = ano civil do primeiro check-in do
-- hóspede ÚNICO (stg_hospede_resolvido: telefone + e-mail + nome completo).
-- `hospedes_ativos` = quantos da coorte tiveram ao menos uma estadia naquele
-- ano; anos_depois = 0 é a própria coorte (100%), anos_depois > 0 são os que
-- voltaram. Ano civil porque a pergunta é "em que ano voltou"; para análise
-- por temporada, trocar year(check_in) por stg_estadias.temporada.
-- Bordas parciais: 2006 tem só dezembro e 2017 vai até julho (janela válida,
-- CLAUDE.md §4) — `ano_parcial` marca as células afetadas.
with reservas as (
    select r.hospede_unico_id, year(f.check_in) as ano
    from {{ ref('stg_hospede_resolvido') }} r
    join {{ ref('stg_fato_reserva') }} f using (reserva)
),
primeira as (
    select hospede_unico_id, min(ano) as coorte_ano
    from reservas
    group by hospede_unico_id
),
tamanho as (
    select coorte_ano, count(*) as tamanho_coorte
    from primeira
    group by coorte_ano
),
atividade as (
    select distinct hospede_unico_id, ano
    from reservas
)
select
    p.coorte_ano,
    a.ano - p.coorte_ano as anos_depois,
    a.ano as ano_calendario,
    count(*) as hospedes_ativos,
    t.tamanho_coorte,
    round(count(*) * 1.0 / t.tamanho_coorte, 4) as pct_da_coorte,
    (p.coorte_ano = 2006 or a.ano = 2017) as ano_parcial
from primeira p
join atividade a using (hospede_unico_id)
join tamanho t using (coorte_ano)
group by p.coorte_ano, a.ano, t.tamanho_coorte
