"""Histograma de diárias por estadia + boxplot de valor da reserva por temporada."""
from pathlib import Path
import pandas as pd, seaborn as sns, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
OUT = Path(__file__).resolve().parent

est = pd.read_csv(RAW / "estadias.csv")
res = pd.read_csv(RAW / "fato_reserva.csv", parse_dates=["check_in"])

# temporada pelo check-in (vira em dezembro), igual à dim_data do projeto
a = res.check_in.dt.year - (res.check_in.dt.month < 12)
res["temporada"] = a.astype(str) + "/" + ((a + 1) % 100).astype(str).str.zfill(2)
val = res[res.valor_total > 0]   # exclui valor 0/NaN (sem valor no cadastro)
print("reservas sem valor positivo excluídas:", len(res) - len(val))

sns.set_theme(style="whitegrid")

fig, ax = plt.subplots(figsize=(9, 5))
d = est.diarias.clip(upper=15)
sns.histplot(d, bins=range(1, 17), discrete=True, ax=ax, color="#2a6f97")
ax.set(title="Diárias por estadia (reserva x quarto)", xlabel="Diárias (15 = 15 ou mais)", ylabel="Estadias")
fig.tight_layout(); fig.savefig(OUT / "hist_diarias.png", dpi=150)

fig, ax = plt.subplots(figsize=(11, 5.5))
ordem = sorted(val.temporada.unique())
sns.boxplot(data=val, x="temporada", y="valor_total", order=ordem, ax=ax, color="#8ecae6", fliersize=2)
ax.set(title="Valor total da reserva por temporada", xlabel="Temporada", ylabel="Valor (R$)")
fig.tight_layout(); fig.savefig(OUT / "boxplot_valor_temporada.png", dpi=150)

print(est.diarias.describe().round(2)); print((est.diarias == 1).mean(), (est.diarias <= 3).mean(), (est.diarias >= 7).mean())
g = val.groupby("temporada").valor_total.agg(["count", "median", "mean", lambda s: s.quantile(.9)]).round(0)
print(g)
print("sem 2006/07 e 2016/17 (parciais) n:", g["count"].to_dict())
