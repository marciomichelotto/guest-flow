"""
carrega_snowflake.py — espelha o schema raw do DuckDB local pro Snowflake.

DuckDB é o alvo de dev (custo zero, iteração rápida); Snowflake é o alvo de
consumo — é nele que o Power BI e qualquer BI tool se conectam. Este script
não reprocessa nada: só copia as tabelas raw já validadas (saída de
consolida_fontes.py, carregada por carrega_duckdb.py) pra um schema RAW no
Snowflake, de onde os models de staging em diante rodam via
`dbt run --target snowflake`.

Uso:
    python carrega_snowflake.py --duckdb ../dbt/guest_flow.duckdb
"""

from __future__ import annotations

import argparse
import os

import duckdb
import pandas as pd
import snowflake.connector
from snowflake.connector.pandas_tools import write_pandas

SNOWFLAKE_CONN = dict(
    account="RZFQSVC-JX11949",
    user="MARCIOMICHELOTTO",
    password=os.environ["SNOWFLAKE_PASSWORD"],
    role="ACCOUNTADMIN",
    warehouse="COMPUTE_WH",
    database="GUEST_FLOW",
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--duckdb", default="./guest_flow.duckdb")
    ap.add_argument("--schema", default="RAW")
    args = ap.parse_args()

    con = duckdb.connect(args.duckdb, read_only=True)
    tabelas = con.execute(
        "select table_name from information_schema.tables where table_schema = 'raw' order by 1"
    ).fetchall()

    sf = snowflake.connector.connect(**SNOWFLAKE_CONN)
    sf.cursor().execute(f"create schema if not exists {args.schema}")

    for (tabela,) in tabelas:
        df = con.execute(f"select * from raw.{tabela}").fetchdf()
        # Snowflake dobra identificador sem aspas pra maiúsculo; write_pandas
        # preserva o case exato da coluna entre aspas. Sem isso, o SQL do dbt
        # (sem aspas) não encontra a coluna.
        df.columns = [c.upper() for c in df.columns]
        # datetime64[us] (padrão do duckdb) confunde a inferência de tipo do
        # write_pandas, que às vezes cria a coluna como NUMBER em vez de
        # TIMESTAMP; datetime64[ns] resolve.
        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                df[col] = df[col].astype("datetime64[ns]")
        success, _, nrows, _ = write_pandas(
            sf,
            df,
            table_name=tabela.upper(),
            schema=args.schema,
            auto_create_table=True,
            overwrite=True,
            use_logical_type=True,
        )
        print(f"  {args.schema}.{tabela.upper():<30} {nrows:>7} linhas  ok={success}")

    sf.close()
    con.close()
    print(f"\n{len(tabelas)} tabelas espelhadas em {SNOWFLAKE_CONN['database']}.{args.schema}")


if __name__ == "__main__":
    main()
