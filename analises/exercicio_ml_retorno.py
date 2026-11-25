"""Exercício 2 — o hóspede volta? Só com informações da PRIMEIRA estadia.
Rótulo: voltou = nova reserva com check-in >= 30 dias após o 1º check-out e em até 24 meses dele.
(30 dias evita contar reserva da mesma viagem; horizonte fixo e só 1ªs estadias até jul/2015 evitam censura.)
Validação temporal: 1ªs estadias < ago/2013 treinam, ago/2013..jul/2015 testam."""
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

RAIZ = Path(__file__).resolve().parents[1]; RAW = RAIZ / "data/raw"
f = pd.read_csv(RAW / "fato_reserva.csv", parse_dates=["check_in", "check_out"])
h = pd.read_csv(RAW / "hospede_resolvido.csv")[["reserva", "hospede_unico_id"]]
d = pd.read_csv(RAW / "dim_hospede.csv")
uf = d.estado.astype("string").str.strip().str.upper(); uf = uf.where(uf.str.fullmatch(r"[A-Z]{2}"))
suf = d.cidade.astype("string").str.extract(r"-\s*([A-Za-z]{2})\s*$")[0].str.upper()
d["uf"] = uf.fillna(suf).where(lambda s: s.isin(["PR", "SP", "SC", "RS", "RJ", "MG"]) | s.isna(), "outro").fillna("desconhecido")
d["tem_contato"] = d.tel_1.notna() | d.email.notna()
f = f.merge(h, on="reserva").merge(d[["reserva", "uf", "tem_contato"]], on="reserva").sort_values(["check_in", "reserva"])

primeira = f.drop_duplicates("hospede_unico_id", keep="first").copy()
def voltou(g):
    p = g.iloc[0]; resto = g.iloc[1:]
    ini, fim = p.check_out + pd.Timedelta(days=30), p.check_out + pd.DateOffset(months=24)
    return int(((resto.check_in >= ini) & (resto.check_in <= fim)).any())
rot = f.groupby("hospede_unico_id").apply(voltou, include_groups=False).rename("voltou")
p = primeira.merge(rot, left_on="hospede_unico_id", right_index=True)
p = p[p.check_out + pd.DateOffset(months=24) <= "2017-07-31"].copy()          # sem censura
p["mes"] = p.check_in.dt.month
p["temporada_ini"] = p.check_in.dt.year - (p.check_in.dt.month < 12)
p["dia_semana"] = p.check_in.dt.dayofweek
p["is_grupo"] = (p.n_quartos.fillna(1) >= 3).astype(int)
p["tem_crianca"] = ((p.pax_crianca_pag.fillna(0) + p.pax_crianca_free.fillna(0)) > 0).astype(int)
p["valor_diaria"] = p.valor_total.where(p.valor_total > 0) / p.diarias_total

NUM = ["diarias_total", "pax_total", "n_quartos", "valor_total", "valor_diaria", "mes", "dia_semana", "temporada_ini", "is_grupo", "tem_crianca"]
CAT = ["uf"]
tr = p.check_in < "2013-08-01"; te = ~tr
y = p.voltou
print(f"1ªs estadias elegíveis: {len(p)} | treino {tr.sum()} (retorno {y[tr].mean():.1%}) | teste {te.sum()} (retorno {y[te].mean():.1%})")

def pre(escala):
    num = [("imp", SimpleImputer(strategy="median"))] + ([("sc", StandardScaler())] if escala else [])
    return ColumnTransformer([("n", Pipeline(num), NUM), ("c", OneHotEncoder(handle_unknown="ignore"), CAT)])
modelos = {
  "baseline (taxa base)": lambda: DummyClassifier(strategy="prior"),
  "regressão logística": lambda: Pipeline([("p", pre(True)), ("m", LogisticRegression(max_iter=1000, class_weight="balanced", C=0.3))]),
  "random forest": lambda: Pipeline([("p", pre(False)), ("m", RandomForestClassifier(300, min_samples_leaf=10, class_weight="balanced_subsample", random_state=42, n_jobs=-1))]),
  "gradient boosting": lambda: Pipeline([("p", pre(False)), ("m", HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=150, class_weight="balanced", random_state=42))]),
}
rng = np.random.default_rng(42)
def auc_ic(real, s, n=1000):
    real, s = np.asarray(real), np.asarray(s); v = []
    for _ in range(n):
        i = rng.integers(0, len(real), len(real))
        if real[i].min() != real[i].max(): v.append(roc_auc_score(real[i], s[i]))
    return np.percentile(v, [2.5, 97.5])
linhas, probas = [], {}
for nome, mk in modelos.items():
    m = mk().fit(p[NUM + CAT][tr], y[tr]); s = m.predict_proba(p[NUM + CAT][te])[:, 1]; probas[nome] = s
    top = s >= np.quantile(s, 0.9)
    lo, hi = auc_ic(y[te], s) if nome != "baseline (taxa base)" else (np.nan, np.nan)
    linhas.append({"modelo": nome, "AUC": roc_auc_score(y[te], s), "AUC_ic_inf": lo, "AUC_ic_sup": hi,
                   "AP": average_precision_score(y[te], s), "retorno_no_top10%": y[te][top].mean()})
res = pd.DataFrame(linhas).set_index("modelo").round(3)
print(f"\nTeste temporal (taxa base de retorno = {y[te].mean():.3f}; AP do acaso = essa taxa):\n", res.to_string())
res.to_csv("ml_retorno_resultados.csv")

# o que pesa na regressão logística
m = modelos["regressão logística"]().fit(p[NUM + CAT][tr], y[tr])
nomes = m[0].get_feature_names_out(); coef = pd.Series(m[-1].coef_[0], index=[n.split("__")[1] for n in nomes])
print("\nMaiores coeficientes (variáveis padronizadas):\n", coef.reindex(coef.abs().sort_values(ascending=False).index).head(8).round(2).to_string())
print("\nTaxa de retorno por grupo/UF (treino+teste):")
print(p.groupby("is_grupo").voltou.agg(["mean", "count"]).round(3).T.to_string())
print(p.groupby("uf").voltou.agg(["mean", "count"]).round(3).T.to_string())

# armadilha: ter contato cadastrado é o que PERMITE achar o retorno (a deduplicação usa telefone/e-mail)
p["tem_contato"] = p.tem_contato.astype(int)
print("\nTaxa de retorno com/sem telefone-ou-email no cadastro:", p.groupby("tem_contato").voltou.mean().round(3).to_dict(), p.tem_contato.value_counts().to_dict())

# checagem: sem o corte temporal, existe algum sinal? (5-fold estratificado)
from sklearn.model_selection import StratifiedKFold, cross_val_predict
print("\nAUC 5-fold aleatório (todas as 1ªs estadias elegíveis):")
for nome, mk in modelos.items():
    if nome.startswith("baseline"): continue
    s = cross_val_predict(mk(), p[NUM + CAT], y, cv=StratifiedKFold(5, shuffle=True, random_state=42), method="predict_proba")[:, 1]
    print(f"  {nome:22s} {roc_auc_score(y, s):.3f}")
