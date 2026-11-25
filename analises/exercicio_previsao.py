"""Baseline 'mesmo mês do ano anterior' x Prophet (com/sem Carnaval e Réveillon).
Alvo: ocupação mensal (%). Validação: origem móvel, 3 dobras de 12 meses (ago-jul)."""
import logging
from datetime import date, timedelta
from pathlib import Path
import duckdb, numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from dateutil.easter import easter
from prophet import Prophet

logging.getLogger("cmdstanpy").setLevel(logging.ERROR)
logging.getLogger("prophet").setLevel(logging.ERROR)
RAIZ = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent
con = duckdb.connect(str(RAIZ / "dbt" / "guest_flow.duckdb"), read_only=True)

# ---- série mensal (verdade) e diária (para o Prophet)
mensal = con.sql("select ano, mes, disponiveis, room_nights_vendidos rn, ocupacao_pct "
                 "from main_marts.mart_ocupacao_mensal order by 1,2").df()
mensal["ds"] = pd.to_datetime(dict(year=mensal.ano, month=mensal.mes, day=1))
mensal = mensal.set_index("ds")
assert len(mensal) == len(pd.date_range(mensal.index.min(), mensal.index.max(), freq="MS")), "mês faltando"

diario = con.sql("""
    with dias as (select unnest(generate_series(date '2006-12-01', date '2017-07-31', interval 1 day))::date ds),
    inv as (select ano, mes, count(distinct quarto) quartos from main_staging.stg_inventario_mensal group by 1,2),
    v as (select data_noite::date ds, count(*) rn from main_intermediate_placeholder group by 1)
    select d.ds, coalesce(v.rn,0) rn, inv.quartos from dias d
    join inv on inv.ano=year(d.ds) and inv.mes=month(d.ds) left join v using (ds)
""".replace("main_intermediate_placeholder", "main.int_noites_completo")).df()
diario["ds"] = pd.to_datetime(diario.ds)
diario["y"] = diario.rn / diario.quartos          # ocupação diária (0-1)

# ---- feriados: Carnaval (móvel, via Páscoa) e Réveillon
anos = range(2006, 2019)
carnaval = pd.DataFrame({"holiday": "carnaval",
    "ds": [pd.Timestamp(easter(a) - timedelta(days=47)) for a in anos],   # terça
    "lower_window": -3, "upper_window": 1})                               # sáb..quarta
reveillon = pd.DataFrame({"holiday": "reveillon", "ds": [pd.Timestamp(a, 12, 31) for a in anos],
    "lower_window": -5, "upper_window": 1})                               # 26/12..1/1
feriados = pd.concat([carnaval, reveillon])

def prophet_mensal(treino_ate, teste_idx, com_feriados):
    tr = diario[diario.ds <= treino_ate][["ds", "y"]]
    m = Prophet(yearly_seasonality=20, weekly_seasonality=True, daily_seasonality=False,
                holidays=feriados if com_feriados else None)
    m.fit(tr)
    fim = teste_idx.max() + pd.offsets.MonthEnd(0)
    fut = pd.DataFrame({"ds": pd.date_range(teste_idx.min(), fim)})
    yhat = m.predict(fut).set_index("ds").yhat.clip(0, 1)
    return (yhat.groupby(yhat.index.to_period("M")).mean() * 100).set_axis(teste_idx)  # %

# ---- origem móvel
linhas = []
for ini in ["2014-08-01", "2015-08-01", "2016-08-01"]:
    teste = pd.date_range(ini, periods=12, freq="MS")
    origem = teste.min() - pd.Timedelta(days=1)
    real = mensal.loc[teste, "ocupacao_pct"]
    base = pd.Series(mensal.ocupacao_pct.reindex(teste - pd.DateOffset(years=1)).values, index=teste)
    assert (teste - pd.DateOffset(years=1)).max() <= origem
    p0 = prophet_mensal(origem, teste, False)
    p1 = prophet_mensal(origem, teste, True)
    linhas.append(pd.DataFrame({"dobra": f"{teste[0]:%Y-%m}..{teste[-1]:%Y-%m}", "real": real,
        "baseline": base, "prophet": p0, "prophet_feriados": p1}))
r = pd.concat(linhas); r.index.name = "mes"
modelos = ["baseline", "prophet", "prophet_feriados"]
mae = lambda d: {m: (d[m] - d.real).abs().mean() for m in modelos}
tab = pd.DataFrame({k: mae(g) for k, g in r.groupby("dobra")}).T
tab.loc["TOTAL (36 meses)"] = mae(r)
print("MAE da ocupação mensal, em pontos percentuais:\n", tab.round(2).to_string())
print("\nganho do Prophet+feriados sobre baseline: %.0f%%" % (100 * (1 - tab.loc['TOTAL (36 meses)', 'prophet_feriados'] / tab.loc['TOTAL (36 meses)', 'baseline'])))
disp = mensal.disponiveis.reindex(r.index)
print("MAE em room-nights/mês:", {m: round(((r[m] - r.real).abs() / 100 * disp).mean(), 1) for m in modelos})
print("meses em que o Prophet+feriados vence o baseline: %d de %d" % (((r.prophet_feriados - r.real).abs() < (r.baseline - r.real).abs()).sum(), len(r)))
r["mes_nome"] = r.index.month
print(r.assign(e_base=(r.baseline - r.real).abs(), e_prop=(r.prophet_feriados - r.real).abs()).groupby("mes_nome")[["e_base", "e_prop"]].mean().round(1).T.to_string())
r.round(2).to_csv(OUT / "previsao_ocupacao.csv"); tab.round(3).to_csv(OUT / "previsao_mae.csv")

fig, ax = plt.subplots(figsize=(12, 5))
ax.plot(r.index, r.real, "k-o", label="real", lw=2)
ax.plot(r.index, r.baseline, "--", label="baseline (mesmo mês, ano anterior)", color="#e07a5f")
ax.plot(r.index, r.prophet_feriados, "-", label="Prophet + Carnaval/Réveillon", color="#2a6f97")
ax.set(ylabel="Ocupação mensal (%)", title="Previsão 12 meses à frente (3 dobras)"); ax.legend(); fig.tight_layout()
fig.savefig(OUT / "previsao_ocupacao.png", dpi=150)
