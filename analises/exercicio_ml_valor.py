"""Exercício 1 — prever o valor da reserva: regressão linear x LightGBM.
Features (todas conhecidas na hora da reserva): diárias, pessoas, quartos, mês, temporada.
Validação: (a) temporal — treina até jul/2015, testa ago/2015+; (b) 5-fold aleatório, para contraste."""
from pathlib import Path
import numpy as np, pandas as pd, lightgbm as lgb
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, r2_score, root_mean_squared_error
from sklearn.model_selection import KFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder

RAIZ = Path(__file__).resolve().parents[1]
f = pd.read_csv(RAIZ / "data/raw/fato_reserva.csv", parse_dates=["check_in"])
f = f[f.valor_total > 0].copy()                      # sem valor no cadastro não entra
f["mes"] = f.check_in.dt.month
f["temporada_ini"] = f.check_in.dt.year - (f.check_in.dt.month < 12)   # 2015 = temporada 2015/16
X_COLS = ["diarias_total", "pax_total", "n_quartos", "mes", "temporada_ini"]
X, y = f[X_COLS], f.valor_total
tr = f.check_in < "2015-08-01"; te = ~tr
print(f"reservas: {len(f)} | treino {tr.sum()} | teste {te.sum()} | mediana teste R$ {y[te].median():.0f}")

def linear(log=False):
    # modelo em log: alvo e variáveis de tamanho em log1p (senão exp(coef*57 diárias) explode)
    tam = [("imp", SimpleImputer(strategy="median"))] + ([("log", FunctionTransformer(np.log1p))] if log else [])
    pre = ColumnTransformer([
        ("tam", Pipeline(tam), ["diarias_total", "pax_total", "n_quartos"]),
        ("temp", "passthrough", ["temporada_ini"]),
        ("mes", OneHotEncoder(handle_unknown="ignore"), ["mes"])])
    return Pipeline([("pre", pre), ("lr", LinearRegression())])

def lgbm():
    return lgb.LGBMRegressor(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=20,
                             subsample=0.8, subsample_freq=1, colsample_bytree=0.8, random_state=42, verbose=-1)

class LogWrap:                                    # treina em log1p(valor), devolve em R$
    def __init__(self, m): self.m = m
    def fit(self, X, y): self.m.fit(X, np.log1p(y)); return self
    def predict(self, X): return np.expm1(self.m.predict(X))
    def get_params(self, deep=False): return {"m": self.m}
    def set_params(self, **p): return self

modelos = {"baseline (mediana)": lambda: DummyRegressor(strategy="median"),
           "linear": linear, "linear (log)": lambda: LogWrap(linear(log=True)),
           "LightGBM": lgbm, "LightGBM (log)": lambda: LogWrap(lgbm())}

def metricas(real, pred):
    return {"MAE": mean_absolute_error(real, pred), "RMSE": root_mean_squared_error(real, pred), "R2": r2_score(real, pred)}

res_t, res_k, pred_t = {}, {}, {}
for nome, mk in modelos.items():
    m = mk().fit(X[tr], y[tr]); p = m.predict(X[te]); pred_t[nome] = p; res_t[nome] = metricas(y[te], p)
    pk = np.zeros(len(f))
    for a, b in KFold(5, shuffle=True, random_state=42).split(X):
        pk[b] = mk().fit(X.iloc[a], y.iloc[a]).predict(X.iloc[b])
    res_k[nome] = metricas(y, pk)
print("\nValidação TEMPORAL (teste = ago/2015 em diante):\n", pd.DataFrame(res_t).T.round(2).to_string())
print("\nValidação ALEATÓRIA 5-fold:\n", pd.DataFrame(res_k).T.round(2).to_string())

# MAE por tipo de reserva (grupo = 3+ quartos) no teste temporal
grupo = (f.n_quartos.fillna(1) >= 3)[te].to_numpy()
print(f"\nMAE no teste por tipo (grupo n={grupo.sum()}, individual n={(~grupo).sum()}):")
for nome, p in pred_t.items():
    e = np.abs(y[te].to_numpy() - p)
    print(f"  {nome:20s} individual R$ {e[~grupo].mean():6.0f} | grupo R$ {e[grupo].mean():6.0f}")

# o que o modelo aprendeu
m = lgbm().fit(X[tr], y[tr])
print("\nImportância LightGBM (ganho):", dict(zip(X_COLS, (m.booster_.feature_importance('gain') / m.booster_.feature_importance('gain').sum()).round(2))))
lin = linear().fit(X[tr], y[tr]); nomes = lin[:-1].get_feature_names_out()
print("Coeficientes linear:", {n.split('__')[1]: round(c, 1) for n, c in zip(nomes, lin[-1].coef_) if not n.startswith('mes')})
# viés no tempo: previsto/real médio por temporada no teste
d = pd.DataFrame({"t": f.temporada_ini[te].to_numpy(), "real": y[te].to_numpy(), "lin": pred_t["linear"], "lgbm": pred_t["LightGBM"]})
print("\nMédia real x prevista por temporada (teste):\n", d.groupby("t").mean().round(0).to_string())
pd.DataFrame(res_t).T.round(3).to_csv("ml_valor_temporal.csv"); pd.DataFrame(res_k).T.round(3).to_csv("ml_valor_kfold.csv")
