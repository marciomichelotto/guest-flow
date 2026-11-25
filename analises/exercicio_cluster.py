"""K-Means de reservas: perfis de hóspede descobertos sem rótulo."""
from pathlib import Path
import numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.preprocessing import StandardScaler

RAIZ = Path(__file__).resolve().parents[1]
f = pd.read_csv(RAIZ / "data/raw/fato_reserva.csv", parse_dates=["check_in", "check_out"])
f["noites"] = (f.check_out - f.check_in).dt.days.clip(lower=1)
f["n_quartos"] = f.n_quartos.fillna(1)
f["pax_total"] = f.pax_total.fillna(f.pax_total.median())
f["crianca"] = ((f.pax_crianca_pag.fillna(0) + f.pax_crianca_free.fillna(0)) > 0).astype(int)
f["mes"] = f.check_in.dt.month
f["temporada_ini"] = f.check_in.dt.year - (f.check_in.dt.month < 12)
f["fds"] = f.check_in.dt.dayofweek.isin([4, 5]).astype(int)                 # entra sexta/sábado
vd = (f.valor_total.where(f.valor_total > 0) / f.diarias_total)
f["preco_rel"] = vd / vd.groupby(f.temporada_ini).transform("median")      # preço relativo à temporada (tira a inflação)
f["preco_rel"] = f.preco_rel.fillna(1.0).clip(upper=5)
f["alta"] = f.mes.isin([12, 1, 2]).astype(int)

X = pd.DataFrame({"log_noites": np.log1p(f.noites), "log_quartos": np.log1p(f.n_quartos),
                  "log_pax": np.log1p(f.pax_total), "crianca": f.crianca, "fds": f.fds,
                  "alta": f.alta, "preco_rel": np.log(f.preco_rel)})
Z = StandardScaler().fit_transform(X)
print(f"{len(f)} reservas, {X.shape[1]} variáveis")

print("\n k  silhouette  inércia")
res = {}
for k in range(2, 9):
    km = KMeans(k, n_init=20, random_state=42).fit(Z)
    res[k] = km; print(f"{k:2d}   {silhouette_score(Z, km.labels_, sample_size=3000, random_state=42):.3f}     {km.inertia_:8.0f}")

K = 5
km = res[K]; f["cluster"] = km.labels_
# estabilidade: mesmos grupos com outras sementes e com reamostragem?
aris = [adjusted_rand_score(km.labels_, KMeans(K, n_init=20, random_state=s).fit_predict(Z)) for s in range(1, 6)]
rng = np.random.default_rng(0); bs = []
for _ in range(5):
    i = rng.integers(0, len(Z), len(Z)); b = KMeans(K, n_init=10, random_state=0).fit(Z[i])
    bs.append(adjusted_rand_score(km.labels_, b.predict(Z)))
print(f"\nEstabilidade (ARI) k={K}: sementes {np.mean(aris):.2f} | bootstrap {np.mean(bs):.2f}")

perfil = f.groupby("cluster").agg(reservas=("reserva", "size"), noites=("noites", "median"), quartos=("n_quartos", "median"),
    pax=("pax_total", "median"), crianca=("crianca", "mean"), fds=("fds", "mean"), alta=("alta", "mean"),
    preco_rel=("preco_rel", "median"), valor_mediano=("valor_total", "median"), receita=("valor_total", "sum"))
perfil["pct_reservas"] = 100 * perfil.reservas / len(f); perfil["pct_receita"] = 100 * perfil.receita / f.valor_total.sum()
print("\nPerfil dos clusters:\n", perfil.drop(columns="receita").round(2).to_string())
print("\nMeses mais comuns por cluster:")
for c, g in f.groupby("cluster"): print(f"  {c}: ", g.mes.value_counts(normalize=True).head(3).round(2).to_dict())
perfil.round(3).to_csv("cluster_perfil.csv"); f[["reserva", "cluster"]].to_csv("cluster_reservas.csv", index=False)

P = PCA(2, random_state=0).fit(Z); xy = P.transform(Z)
fig, ax = plt.subplots(figsize=(9, 6))
for c in range(K):
    m = f.cluster == c; ax.scatter(xy[m, 0], xy[m, 1], s=6, alpha=.5, label=f"cluster {c} (n={m.sum()})")
ax.set(title=f"K-Means (k={K}) projetado em 2 componentes ({P.explained_variance_ratio_.sum():.0%} da variância)", xlabel="PC1", ylabel="PC2")
ax.legend(markerscale=3); fig.tight_layout(); fig.savefig("cluster_pca.png", dpi=150)
