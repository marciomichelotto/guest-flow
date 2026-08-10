-- Grão hospede_unico_id. Taxa de retorno = hóspede único resolvido por
-- telefone/e-mail normalizado (CLAUDE.md original não tem ID estável de
-- hóspede entre reservas — ver stg_hospede_resolvido). Aproximação, não
-- identidade garantida: telefone compartilhado pode gerar falso positivo,
-- troca de número ao longo dos 10 anos pode gerar falso negativo.
select
    r.hospede_unico_id,
    max(r.n_reservas_do_hospede) as n_reservas,
    max(r.n_reservas_do_hospede) > 1 as retornou,
    max_by(h.nome, f.check_in) as nome_mais_recente,
    max_by(h.estado, f.check_in) as estado_mais_recente,
    min(f.check_in) as primeira_reserva,
    max(f.check_in) as ultima_reserva,
    datediff('day', min(f.check_in), max(f.check_in)) as dias_entre_primeira_ultima,
    sum(f.valor_total) as receita_total_hospede
from {{ ref('stg_hospede_resolvido') }} r
join {{ ref('stg_fato_reserva') }} f using (reserva)
left join {{ ref('stg_dim_hospede') }} h using (reserva)
group by r.hospede_unico_id
