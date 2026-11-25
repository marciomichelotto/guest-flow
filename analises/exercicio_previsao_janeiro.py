"""Janeiro à parte. Baseline 'mesmo mês do ano anterior' x Prophet (com/sem Carnaval e Réveillon).
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

def prophet_mensal(treino_ate, teste_idx, com_feriados, modo='additive'):
    tr = diario[diario.ds <= treino_ate][["ds", "y"]]
    m = Prophet(yearly_seasonality=20, weekly_seasonality=True, daily_seasonality=False,
                holidays=feriados if com_feriados else None, seasonality_mode=modo)
    m.fit(tr)
    fim = teste_idx.max() + pd.offsets.MonthEnd(0)
    fut = pd.DataFrame({"ds": pd.date_range(teste_idx.min(), fim)})
    yhat = m.predict(fut).set_index("ds").yhat.clip(0, 1)
    return (yhat.groupby(yhat.index.to_period("M")).mean() * 100).set_axis(teste_idx)  # %


# ---- origem móvel: 5 dobras. As 2 mais antigas NÃO foram vistas ao escolher o foco em janeiro
dobras = {"2012-08-01": "nova", "2013-08-01": "nova", "2014-08-01": "vista", "2015-08-01": "vista", "2016-08-01": "vista"}
linhas = []
for ini, tipo in dobras.items():
    teste = pd.date_range(ini, periods=12, freq="MS")
    origem = teste.min() - pd.Timedelta(days=1)
    real = mensal.loc[teste, "ocupacao_pct"]
    base = pd.Series(mensal.ocupacao_pct.reindex(teste - pd.DateOffset(years=1)).values, index=teste)
    p = prophet_mensal(origem, teste, True)
    pm = prophet_mensal(origem, teste, True, "multiplicative")
    d = pd.DataFrame({"dobra": f"{teste[0]:%Y-%m}", "tipo": tipo, "real": real, "baseline": base,
                      "prophet": p, "prophet_mult": pm})
    d["hibrido_jan"] = np.where(d.index.month == 1, d.baseline, d.prophet)           # jan = baseline
    d["media_jan"] = np.where(d.index.month == 1, (d.baseline + d.prophet) / 2, d.prophet)
    d["hibrido_mult_jan"] = np.where(d.index.month == 1, d.baseline, d.prophet_mult)
    linhas.append(d)
r = pd.concat(linhas); r.index.name = "mes"
mods = ["baseline", "prophet", "prophet_mult", "hibrido_jan", "media_jan", "hibrido_mult_jan"]
mae = lambda d: pd.Series({m: (d[m] - d.real).abs().mean() for m in mods})
tab = pd.DataFrame({k: mae(g) for k, g in r.groupby("dobra")}).T
tab.loc["Dobras novas (24 m)"] = mae(r[r.tipo == "nova"])
tab.loc["Dobras vistas (36 m)"] = mae(r[r.tipo == "vista"])
tab.loc["TOTAL (60 m)"] = mae(r)
print("MAE da ocupação mensal (p.p.):"); print(tab.round(2).to_string())
j = r[r.index.month == 1]
print("\nSó janeiro (5 anos): erro absoluto por modelo")
print(pd.DataFrame({m: (j[m] - j.real).abs() for m in mods}).assign(real=j.real).round(1).to_string())
print("MAE só janeiro:", mae(j).round(1).to_dict())
print("MAE sem janeiro:", mae(r[r.index.month != 1]).round(2).to_dict())
r.round(2).to_csv("previsao_janeiro.csv"); tab.round(3).to_csv("previsao_janeiro_mae.csv")
