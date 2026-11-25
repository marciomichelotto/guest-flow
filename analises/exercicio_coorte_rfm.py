"""Heatmap de coorte (mart_coorte_hospede) e resumo RFM (mart_hospede_rfm)."""
from pathlib import Path
import duckdb, matplotlib, seaborn as sns
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RAIZ = Path(__file__).resolve().parents[1]
con = duckdb.connect(str(RAIZ / "dbt" / "guest_flow.duckdb"), read_only=True)
c = con.sql("select * from main_marts.mart_coorte_hospede").df()

n = c.pivot(index="coorte_ano", columns="anos_depois", values="hospedes_ativos")
pct = c.pivot(index="coorte_ano", columns="anos_depois", values="pct_da_coorte")
tam = c.drop_duplicates("coorte_ano").set_index("coorte_ano").tamanho_coorte
# só anos_depois >= 1: a coluna 0 é sempre 100% e apagaria a escala
n, pct = n.drop(columns=0), pct.drop(columns=0)
anot = n.map(lambda v: "" if v != v else f"{int(v)}") + "\n" + pct.map(lambda v: "" if v != v else f"{v:.0%}")
fig, ax = plt.subplots(figsize=(11, 6))
sns.heatmap(pct * 100, annot=anot, fmt="", cmap="Blues", cbar_kws={"label": "% da coorte que voltou"}, ax=ax, linewidths=.5)
ax.set_yticklabels([f"{a}  (n={tam[a]})" for a in pct.index], rotation=0)
ax.set(title="Retenção de hóspedes por ano da primeira estadia", xlabel="Anos depois da primeira estadia", ylabel="Coorte")
fig.tight_layout(); fig.savefig(Path(__file__).parent / "heatmap_coorte.png", dpi=150)
print(con.sql("select coorte_ano, tamanho_coorte, max(case when anos_depois=1 then pct_da_coorte end) a1, max(case when anos_depois=2 then pct_da_coorte end) a2 from main_marts.mart_coorte_hospede group by 1,2 order by 1").df().to_string())

print(con.sql("""select segmento, count(*) hospedes, round(100.0*count(*)/sum(count(*)) over(),1) pct,
  round(sum(monetario)) receita, round(100.0*sum(monetario)/sum(sum(monetario)) over(),1) pct_receita, round(avg(frequencia),1) freq_media
  from main_marts.mart_hospede_rfm group by 1 order by 2 desc""").df().to_string())
print(con.sql("select frequencia, count(*) n from main_marts.mart_hospede_rfm group by 1 order by 1").df().T.to_string())
print(con.sql("select rfm, count(*) n from main_marts.mart_hospede_rfm group by 1 order by 2 desc limit 5").df().to_string())
print(con.sql("select count(*), sum(case when frequencia>=2 then 1 end) from main_marts.mart_hospede_rfm").fetchall())
