"""Elasticidade-preço da demanda na baixa temporada + simulação de receita.
Modelo: room-nights ~ Poisson (PPML), offset ln(room-nights disponíveis), ln(ADR) + efeitos de mês + tendência.
Baixa temporada = abr, mai, jun, ago, set, out (definição do mart_ocupacao_mensal)."""
from pathlib import Path
import duckdb, numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import statsmodels.api as sm, statsmodels.formula.api as smf

RAIZ = Path(__file__).resolve().parents[1]; OUT = Path(__file__).resolve().parent
con = duckdb.connect(str(RAIZ / "dbt/guest_flow.duckdb"), read_only=True)
BAIXA = [4, 5, 6, 8, 9, 10]

# ---- mensal
m = con.sql("select * from main_marts.mart_ocupacao_mensal order by 1,2").df()
m["t"] = m.ano + (m.mes - 1) / 12
mb = m[m.mes.isin(BAIXA)].copy()
print(f"meses de baixa: {len(mb)} | sem nenhuma venda (sem ADR): {(mb.room_nights_vendidos == 0).sum()}")
mb = mb[mb.room_nights_vendidos > 0].assign(p=lambda d: np.log(d.adr), off=lambda d: np.log(d.disponiveis))

# ---- semanal (mais observações; mesmas armadilhas)
d = con.sql("""
  with n as (select data_noite::date ds, count(*) rn, sum(valor_noite) v from main.int_noites_completo group by 1),
  dias as (select unnest(generate_series(date '2006-12-01', date '2017-07-31', interval 1 day))::date ds),
  inv as (select ano, mes, count(distinct quarto) q from main_staging.stg_inventario_mensal group by 1,2)
  select date_trunc('week', d.ds) semana, month(any_value(d.ds)) mes, year(any_value(d.ds)) ano,
         sum(coalesce(n.rn,0)) rn, sum(coalesce(n.v,0)) v, sum(inv.q) disp
  from dias d join inv on inv.ano=year(d.ds) and inv.mes=month(d.ds) left join n using (ds) group by 1""").df()
wb = d[d.mes.isin(BAIXA) & (d.rn > 0) & (d.v > 0)].copy()
wb["p"] = np.log(wb.v / wb.rn); wb["off"] = np.log(wb.disp); wb["t"] = wb.ano + wb.semana.dt.dayofyear / 365
wb["ym"] = wb.ano * 100 + wb.mes
print(f"semanas de baixa com venda: {len(wb)}")

def ppml(df, y, form, cluster=None):
    mod = smf.glm(f"{y} ~ p + {form}", df, family=sm.families.Poisson(), offset=df.off)
    r = mod.fit(cov_type="cluster", cov_kwds={"groups": df[cluster]}) if cluster else mod.fit(cov_type="HC3")
    ci = r.conf_int().loc["p"]; return r, r.params["p"], ci[0], ci[1]

specs = []
for nome, df, y, cl in [("mensal", mb, "room_nights_vendidos", None), ("semanal", wb, "rn", "ym")]:
    for forma, lab in [("1", "sem controles"), ("C(mes)", "+ mês"), ("C(mes) + t", "+ mês + tendência"), ("C(mes) + C(ano)", "+ mês + ano")]:
        _, e, lo, hi = ppml(df, y, forma, cl); specs.append((f"{nome}: {lab}", e, lo, hi))
S = pd.DataFrame(specs, columns=["especificação", "elasticidade", "ic_inf", "ic_sup"]).set_index("especificação")
print("\nElasticidade-preço (PPML, IC 95%):\n", S.round(2).to_string()); S.round(3).to_csv(OUT / "elasticidade_especificacoes.csv")

# ---- especificação central (definida a priori): mensal, mês + tendência. Incerteza por simulação do coeficiente.
r, e0, lo0, hi0 = ppml(mb, "room_nights_vendidos", "C(mes) + t")
se = r.bse["p"]; rng = np.random.default_rng(42); draws = rng.normal(e0, se, 20000)
print(f"\nCentral: e = {e0:.2f} (EP {se:.2f}); P(e > -1) = {(draws > -1).mean():.0%}  [P(demanda inelástica)]")

# ---- simulação: últimos 12 meses de baixa (ago-out/2016 e abr-jun/2017)
base = m[((m.ano == 2016) & m.mes.isin([8, 9, 10])) | ((m.ano == 2017) & m.mes.isin([4, 5, 6]))]
Q0, P0, DISP = base.room_nights_vendidos.sum(), base.receita.sum() / base.room_nights_vendidos.sum(), base.disponiveis.sum()
print(f"\nBase (6 meses de baixa recentes): {Q0} room-nights, ADR R$ {P0:.0f}, receita R$ {Q0*P0:,.0f}, ocupação {Q0/DISP:.1%}")
delta = np.arange(-0.30, 0.401, 0.05)
cen = {"inelástica (-0,3)": -0.3, f"central ({e0:.2f})": e0, "unitária (-1,0)": -1.0, "elástica (-1,5)": -1.5}
rec = pd.DataFrame({k: Q0 * (1 + delta) ** e * P0 * (1 + delta) / (Q0 * P0) - 1 for k, e in cen.items()}, index=np.round(delta, 2))
rec["esperada (incerteza do central)"] = [np.mean(Q0 * (1 + dl) ** draws * P0 * (1 + dl)) / (Q0 * P0) - 1 for dl in delta]
rec["P(receita sobe)"] = [np.mean((1 + dl) ** (draws + 1) > 1) if dl != 0 else np.nan for dl in delta]
occ = {dl: Q0 * (1 + dl) ** e0 / DISP for dl in delta}
print("\nVariação da receita vs preço atual:\n", (rec * 100).round(1).assign(**{"P(receita sobe)": (rec["P(receita sobe)"] * 100).round(0)}).to_string())
print(f"\nOcupação no cenário central: preço +20% -> {occ[delta[10]]:.1%} | +40% -> {occ[delta[-1]]:.1%} | -20% -> {occ[delta[2]]:.1%}")
rec.round(4).to_csv(OUT / "elasticidade_simulacao.csv")

fig, ax = plt.subplots(1, 2, figsize=(13, 5))
y = np.arange(len(S)); ax[0].errorbar(S.elasticidade, y, xerr=[S.elasticidade - S.ic_inf, S.ic_sup - S.elasticidade], fmt="o", color="#2a6f97", capsize=3)
ax[0].axvline(-1, color="#e07a5f", ls="--", label="-1 (receita indiferente)"); ax[0].axvline(0, color="gray", lw=.8)
ax[0].set_yticks(y, S.index); ax[0].invert_yaxis(); ax[0].set(title="Elasticidade por especificação (IC 95%)", xlabel="elasticidade-preço"); ax[0].legend()
for k in cen: ax[1].plot(delta * 100, rec[k] * 100, label=k)
ax[1].plot(delta * 100, rec["esperada (incerteza do central)"] * 100, "k--", label="esperada (com incerteza)")
ax[1].axhline(0, color="gray", lw=.8); ax[1].set(title="Receita da baixa temporada vs variação de preço", xlabel="variação do preço (%)", ylabel="variação da receita (%)"); ax[1].legend(fontsize=8)
fig.tight_layout(); fig.savefig(OUT / "elasticidade.png", dpi=150)
