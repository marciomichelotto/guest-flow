"""
carrega_duckdb.py — carga dos CSVs de data/raw pro DuckDB local.

data/raw é gitignored (dado real de hóspede); o .duckdb também não é
versionado. Isso substitui um passo de "load" que normalmente seria feito
por dbt seeds — mas seeds são pra dado estático versionado, não pra saída
de um pipeline que roda de novo a cada extração.

Uso:
    python carrega_duckdb.py --entrada ../data/raw --saida ../dbt/guest_flow.duckdb
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entrada", default="./data/raw")
    ap.add_argument("--saida", default="./dbt/guest_flow.duckdb")
    args = ap.parse_args()

    entrada, saida = Path(args.entrada), Path(args.saida)
    saida.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(saida))
    con.execute("create schema if not exists raw")

    csvs = sorted(entrada.glob("*.csv"))
    for csv in csvs:
        tabela = csv.stem
        con.execute(f"""
            create or replace table raw.{tabela} as
            select * from read_csv_auto('{csv.as_posix()}', all_varchar=false)
        """)
        n = con.execute(f"select count(*) from raw.{tabela}").fetchone()[0]
        print(f"  raw.{tabela:<30} {n:>7} linhas")

    con.close()
    print(f"\n{len(csvs)} tabelas carregadas em {saida}")


if __name__ == "__main__":
    main()
