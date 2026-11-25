"""Mann-Whitney (valor da reserva SP x PR) e IC bootstrap da diária média por temporada."""
from pathlib import Path
import numpy as np, pandas as pd
from scipy import stats

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
res = pd.read_csv(RAW / "fato_reserva.csv", parse_dates=["check_in"])
hos = pd.read_csv(RAW / "dim_hospede.csv")

# UF: coluna 'estado' normalizada; se vazia, sufixo da cidade ("Londrina-Pr")
uf = hos.estado.astype("string").str.strip().str.upper()
uf = uf.where(uf.str.fullmatch(r"[A-Z]{2}"))
suf = hos.cidade.astype("string").str.extract(r"-\s*([A-Za-z]{2})\s*$")[0].str.upper()
hos["uf"] = uf.fillna(suf)
df = res.merge(hos[["reserva", "uf"]], on="reserva")
df = df[df.valor_total > 0]
print("UF conhecida:", df.uf.notna().sum(), "de", len(df))

# ---- Mann-Whitney SP x PR
def mw(d, rotulo):
    sp, pr = d[d.uf == "SP"].valor_total, d[d.uf == "PR"].valor_total
    u, p = stats.mannwhitneyu(sp, pr, alternative="two-sided")
    cles = u / (len(sp) * len(pr))  # P(SP > PR) (+0,5 empates)
    print(f"{rotulo}: n SP={len(sp)} PR={len(pr)} | mediana SP={sp.median():.0f} PR={pr.median():.0f} "
          f"| U={u:.0f} p={p:.2e} | P(SP>PR)={cles:.3f}")
mw(df, "valor_total da reserva")
d2 = df[df.diarias_total > 0].assign(diaria=lambda x: x.valor_total / x.diarias_total)
d2 = d2.assign(valor_total=d2.diaria)
mw(d2, "valor por diária        ")

# ---- Bootstrap: diária média (valor_total / diarias_total) por temporada
a = df.check_in.dt.year - (df.check_in.dt.month < 12)
df["temporada"] = a.astype(str) + "/" + ((a + 1) % 100).astype(str).str.zfill(2)
df = df[df.diarias_total > 0].assign(diaria=lambda x: x.valor_total / x.diarias_total)
rows = []
for t, g in df.groupby("temporada"):
    x = g.diaria.to_numpy()
    r = stats.bootstrap((x,), np.mean, n_resamples=10_000, confidence_level=0.95,
                        method="percentile", random_state=42)
    rows.append((t, len(x), x.mean(), r.confidence_interval.low, r.confidence_interval.high))
out = pd.DataFrame(rows, columns=["temporada", "n", "media", "ic_inf", "ic_sup"]).round(1)
print(out.to_string(index=False))
out.to_csv(Path(__file__).parent / "ic_diaria_temporada.csv", index=False)
