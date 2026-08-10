"""
extrai_mapa.py — Guest Flow / ingestão dos mapas de hospedagem (2007–2017)

Lê as planilhas "Reservas <ano>" e converte o mapa visual (células mescladas)
em tabelas normalizadas, grão quarto-a-quarto.

REGRA DE DECODIFICAÇÃO DO MAPA
------------------------------
Cada dia ocupa DUAS colunas do Excel:
    coluna par   (B=2, D=4, F=6, ...) -> manhã  = lado do CHECK-OUT
    coluna ímpar (C=3, E=5, G=7, ...) -> tarde  = lado do CHECK-IN

Logo, para a coluna c:  dia = c // 2
Uma estadia é uma célula MESCLADA horizontal cujo valor é o nº da reserva:
    col_ini ímpar -> check-in  no dia (col_ini - 1) // 2
    col_ini par   -> estadia começou no mês anterior (barra cortada)
    col_fim par   -> check-out no dia col_fim // 2
    col_fim ímpar -> estadia termina no mês seguinte (barra cortada)

A noite `d` está ocupada quando:  (2d + 1) >= col_ini  e  (2d + 2) <= col_fim

SAÍDAS
------
    estadias.csv           grão: reserva x quarto
    room_nights.csv        grão: reserva x quarto x noite   (fato atômico)
    inventario_mensal.csv  grão: ano x mês x quarto         (o DENOMINADOR)
    divergencias.csv       conflitos mapa x cadastro
    resumo_mensal.csv      ocupação/room-nights por mês (sanity check)

Uso:
    python extrai_mapa.py --entrada ./planilhas --saida ./data/raw
"""

from __future__ import annotations

import argparse
import calendar
import datetime as dt
import re
import sys
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

# Janela válida: o registro manual foi descontinuado na migração para o PMS
# Hospedin. A partir de ago/2017 o mapa tem registros residuais que NÃO
# representam a realidade e precisam ficar de fora.
JANELA_INICIO = dt.date(2006, 12, 1)
JANELA_FIM = dt.date(2017, 7, 31)

# Mês em que a temporada vira. Dezembro abre a temporada seguinte.
MES_INICIO_TEMPORADA = 12

MESES = {
    "JANEIRO": 1, "FEVEREIRO": 2, "MARCO": 3, "MARÇO": 3, "ABRIL": 4,
    "MAIO": 5, "JUNHO": 6, "JULHO": 7, "AGOSTO": 8, "SETEMBRO": 9,
    "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12,
}

DIAS_SEMANA = {"SEG", "TER", "QUA", "QUI", "SEX", "SAB", "SÁB", "DOM"}

ABA_CADASTRO = "controle hóspedes"
# aceita "Reservas 2016", "reservas-2012" (hífen, minúsculo) e "Reservas 2013 (2)"
# (sufixo "(N)" do Excel ao duplicar aba) — três variações reais encontradas
# nas planilhas que a versão original (só "reservas 2016") deixava passar batido.
RE_ABA_MAPA = re.compile(r"^\s*reservas[\s\-]+(\d{4})\s*(?:\(\d+\))?\s*$", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def temporada(data: dt.date) -> str:
    """dez/2015 e jan/2016 pertencem ambos à temporada '2015/16'."""
    ano_ini = data.year if data.month >= MES_INICIO_TEMPORADA else data.year - 1
    return f"{ano_ini}/{str(ano_ini + 1)[-2:]}"


def fase_temporada(mes: int) -> str:
    if mes in (12, 1, 2):
        return "alta"
    if mes in (3, 7, 11):
        return "media"
    return "baixa"


RE_QUARTO_VALIDO = re.compile(r"^[A-Z0-9]{1,10}$")


def normaliza_quarto(v) -> str | None:
    """
    Coluna A do mapa. Aceita 1, '01', 'K3', 'Sobrado'.

    Rejeita (None, com aviso) em vez de aceitar célula com caractere de
    controle/lixo de encoding — já vimos isso acontecer (maio/2015, quarto
    virou um blob ilegível). Melhor um quarto "sumido" e visível no
    cruzamento com o inventário do que um rótulo inventado.
    """
    if v is None:
        return None
    s = str(v).strip()
    if not s or s.upper() in DIAS_SEMANA:
        return None
    if isinstance(v, float) and v.is_integer():
        s = str(int(v))
    m = re.fullmatch(r"0*(\d+)", s)
    if m:
        return m.group(1)
    s = s.upper()
    if RE_QUARTO_VALIDO.fullmatch(s):
        return s
    print(f"  ! célula de quarto rejeitada (não parece rótulo válido): {s[:40]!r}",
          file=sys.stderr, flush=True)
    return None


def extrai_num_reserva(v) -> int | None:
    """O mapa às vezes traz '4490', 4490 ou '4490 GRUPO'."""
    if v is None:
        return None
    m = re.match(r"^\s*(\d{2,6})", str(v))
    return int(m.group(1)) if m else None


def rotulo_livre(v) -> str | None:
    """Anotações não-numéricas do mapa (evento, bloqueio, 'REFORMA')."""
    if v is None:
        return None
    s = str(v).strip()
    return s if s and extrai_num_reserva(v) is None else None


# ---------------------------------------------------------------------------
# Leitura de um bloco de mês
# ---------------------------------------------------------------------------

def _mes_espacado(ws, rr: int, max_c: int) -> int | None:
    """
    Alguns blocos (ex.: aba 'Reservas 2013') estilizam o título do mês com
    uma letra por célula ('D'|'E'|'Z'|'E'|'M'|'B'|'R'|'O'). O match direto
    de célula nunca bate; reconstrói o texto juntando letras consecutivas.
    """
    c = 1
    while c <= max_c:
        v = ws.cell(rr, c).value
        if isinstance(v, str) and len(v.strip()) == 1 and v.strip().isalpha():
            letras = []
            while c <= max_c:
                v = ws.cell(rr, c).value
                if isinstance(v, str) and len(v.strip()) == 1 and v.strip().isalpha():
                    letras.append(v.strip())
                    c += 1
                else:
                    break
            palavra = "".join(letras).upper()
            if palavra in MESES:
                return MESES[palavra]
        else:
            c += 1
    return None


def localiza_blocos(ws) -> list[dict]:
    """
    Um bloco = um mês. Identificado pela linha-cabeçalho de dias, onde as
    colunas B, D, F trazem 1, 2, 3. O nome do mês está nas linhas acima;
    as linhas de quarto vêm logo abaixo, enquanto a coluna A tiver conteúdo.
    """
    blocos = []
    for r in range(1, ws.max_row + 1):
        if [ws.cell(r, c).value for c in (2, 4, 6)] != [1, 2, 3]:
            continue

        max_c = min(ws.max_column, 120)
        mes = None
        for rr in (r - 1, r - 2, r - 3):
            if rr < 1:
                continue
            for c in range(1, max_c + 1):
                v = ws.cell(rr, c).value
                if isinstance(v, str) and v.strip().upper() in MESES:
                    mes = MESES[v.strip().upper()]
                    break
            if mes is None:
                mes = _mes_espacado(ws, rr, max_c)
            if mes:
                break
        if mes is None:
            print(f"  ! [{ws.title}] bloco na linha {r} sem nome de mês — ignorado",
                  file=sys.stderr, flush=True)
            continue

        quartos: dict[int, str] = {}
        rr = r + 1
        while rr <= ws.max_row:
            q = normaliza_quarto(ws.cell(rr, 1).value)
            if q is None:
                break
            quartos[rr] = q
            rr += 1

        # último dia declarado no cabeçalho: valida contra o calendário
        dias = [ws.cell(r, c).value for c in range(2, ws.max_column + 1, 2)]
        dias = [d for d in dias if isinstance(d, int)]
        blocos.append({
            "linha_dias": r,
            "mes": mes,
            "quartos": quartos,
            "ultimo_dia_no_mapa": max(dias) if dias else None,
        })
    return blocos


def le_aba(ws, ano_aba: int) -> tuple[list[dict], list[dict]]:
    """Devolve (barras, inventario) de uma aba de mapa."""
    merges = [m for m in ws.merged_cells.ranges if m.min_row == m.max_row]
    idx_merge: dict[tuple[int, int], object] = {}
    for m in merges:
        for c in range(m.min_col, m.max_col + 1):
            idx_merge[(m.min_row, c)] = m

    barras, inventario = [], []

    for bloco in localiza_blocos(ws):
        mes = bloco["mes"]
        ano = ano_aba - 1 if mes == MES_INICIO_TEMPORADA else ano_aba
        dias_no_mes = calendar.monthrange(ano, mes)[1]

        if bloco["ultimo_dia_no_mapa"] not in (None, dias_no_mes):
            print(
                f"  ! [{ws.title}] {mes:02d}/{ano}: mapa vai até o dia "
                f"{bloco['ultimo_dia_no_mapa']}, calendário tem {dias_no_mes}",
                file=sys.stderr, flush=True,
            )

        for linha, quarto in bloco["quartos"].items():
            # O inventário sai da coluna A: se o quarto está listado no bloco,
            # ele existia naquele mês. É daqui que vem o denominador de
            # ocupação e RevPAR — nunca de um número fixo no código.
            inventario.append({"ano": ano, "mes": mes, "quarto": quarto})

            vistos: set[int] = set()
            for c in range(2, ws.max_column + 1):
                if c in vistos:
                    continue
                m = idx_merge.get((linha, c))
                if m is not None:
                    col_ini, col_fim = m.min_col, m.max_col
                    valor = ws.cell(linha, col_ini).value
                    vistos.update(range(col_ini, col_fim + 1))
                else:
                    col_ini = col_fim = c
                    valor = ws.cell(linha, c).value
                    vistos.add(c)
                if valor is None:
                    continue

                barras.append({
                    "aba": ws.title,
                    "ano": ano,
                    "mes": mes,
                    "quarto": quarto,
                    "reserva": extrai_num_reserva(valor),
                    "rotulo": rotulo_livre(valor),
                    "col_ini": col_ini,
                    "col_fim": col_fim,
                    "dia_checkin": (col_ini - 1) // 2 if col_ini % 2 else None,
                    "dia_checkout": col_fim // 2 if col_fim % 2 == 0 else None,
                    "dias_no_mes": dias_no_mes,
                })

    return barras, inventario


# ---------------------------------------------------------------------------
# Transformações
# ---------------------------------------------------------------------------

def explode_noites(barras: pd.DataFrame) -> pd.DataFrame:
    """Barra -> uma linha por noite ocupada. Este é o fato atômico."""
    linhas = []
    for b in barras.itertuples(index=False):
        for d in range(1, b.dias_no_mes + 1):
            if (2 * d + 1) >= b.col_ini and (2 * d + 2) <= b.col_fim:
                linhas.append({
                    "reserva": b.reserva,
                    "quarto": b.quarto,
                    "data_noite": dt.date(b.ano, b.mes, d),
                    "aba": b.aba,
                })
    df = pd.DataFrame(linhas).drop_duplicates(subset=["reserva", "quarto", "data_noite"])
    df["temporada"] = df["data_noite"].map(temporada)
    df["fase_temporada"] = df["data_noite"].map(lambda x: fase_temporada(x.month))
    return df.sort_values(["data_noite", "quarto"]).reset_index(drop=True)


def monta_estadias(rn: pd.DataFrame) -> pd.DataFrame:
    """
    Grão reserva x quarto. Costura automaticamente as barras partidas na
    virada de mês, porque trabalha em cima das noites já explodidas.
    """
    g = (
        rn.groupby(["reserva", "quarto"], dropna=False)
        .agg(
            primeira_noite=("data_noite", "min"),
            ultima_noite=("data_noite", "max"),
            diarias=("data_noite", "nunique"),
        )
        .reset_index()
    )
    g["check_in"] = g["primeira_noite"]
    g["check_out"] = g["ultima_noite"] + pd.Timedelta(days=1)
    g["temporada"] = g["check_in"].map(temporada)
    # buracos no meio => nº de reserva provavelmente reaproveitado em outra data
    g["suspeita_num_reaproveitado"] = (
        (g["ultima_noite"] - g["primeira_noite"]).dt.days + 1
    ) != g["diarias"]
    return g.drop(columns=["primeira_noite", "ultima_noite"])


def expande_quartos_cadastro(v) -> list[str] | None:
    """'todos' / '1 a 3' / '5 e 7' / 'K3/K4' -> lista de quartos."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip().lower()
    if not s or s == "nan":
        return None
    if "todos" in s:
        return ["*TODOS*"]
    achados: set[str] = set()
    for parte in re.split(r"[,;/+]|\se\s|\bao?\b(?!\w)", s):
        parte = parte.strip()
        if not parte:
            continue
        faixa = re.fullmatch(r"(\d+)\s*[-–]\s*(\d+)", parte)
        if faixa:
            achados.update(str(n) for n in range(int(faixa.group(1)), int(faixa.group(2)) + 1))
            continue
        simples = re.fullmatch(r"0*(\d+)", parte)
        if simples:
            achados.add(simples.group(1))
            continue
        kit = re.fullmatch(r"k\s*0*(\d+)", parte)
        if kit:
            achados.add(f"K{kit.group(1)}")
            continue
        if parte == "sobrado":
            achados.add("SOBRADO")
    return sorted(achados) or None


RE_PAX = re.compile(r"(?:(\d+)\s*x\s*)?(\d+)\s*(AD|AT|A|C|c)", re.VERBOSE)


def parse_pax(v) -> dict:
    """
    A  = adulto            AD = adulto double     AT = adulto twin
    C  = criança 6–12 (pagante)                   c  = criança 0–6 (não paga)
    'Nx...' multiplica o bloco (N quartos iguais).
    """
    vazio = {"pax_adulto": None, "pax_crianca_pag": None,
             "pax_crianca_free": None, "config_cama": None, "pax_bruto": None}
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return vazio
    s = str(v).strip()
    if not s or s.lower() == "nan":
        return vazio

    adultos = cri_pag = cri_free = 0
    config = set()
    achou = False
    for mult, qtd, tipo in RE_PAX.findall(s.replace(" ", "")):
        achou = True
        n = int(qtd) * (int(mult) if mult else 1)
        if tipo in ("A", "AD", "AT"):
            adultos += n
            if tipo in ("AD", "AT"):
                config.add(tipo)
        elif tipo == "C":
            cri_pag += n
        elif tipo == "c":
            cri_free += n
    if not achou:
        return {**vazio, "pax_bruto": s}
    return {
        "pax_adulto": adultos,
        "pax_crianca_pag": cri_pag,
        "pax_crianca_free": cri_free,
        "config_cama": "/".join(sorted(config)) or None,
        "pax_bruto": s,
    }


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def processa_arquivo(caminho: Path) -> dict[str, pd.DataFrame]:
    print(f"\n>> {caminho.name}")
    wb = load_workbook(caminho, data_only=True)

    barras, inventario = [], []
    for aba in wb.sheetnames:
        m = RE_ABA_MAPA.match(aba)
        if not m:
            continue
        ano_aba = int(m.group(1))
        b, i = le_aba(wb[aba], ano_aba)
        print(f"   {aba}: {len(b)} barras, {len({(x['ano'], x['mes']) for x in i})} blocos")
        barras += b
        inventario += i

    cadastro = pd.DataFrame()
    if ABA_CADASTRO in wb.sheetnames:
        cadastro = pd.read_excel(caminho, sheet_name=ABA_CADASTRO)
        cadastro.columns = [str(c).strip() for c in cadastro.columns]

    return {
        "barras": pd.DataFrame(barras),
        "inventario": pd.DataFrame(inventario).drop_duplicates(),
        "cadastro": cadastro,
    }


def aplica_janela(df: pd.DataFrame, col: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    d = pd.to_datetime(df[col]).dt.date
    dentro = (d >= JANELA_INICIO) & (d <= JANELA_FIM)
    return df[dentro].copy(), df[~dentro].copy()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entrada", required=True, help="pasta com as planilhas .xlsx")
    ap.add_argument("--saida", default="./data/raw")
    args = ap.parse_args()

    entrada, saida = Path(args.entrada), Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)

    arquivos = sorted(p for p in entrada.glob("*.xlsx") if not p.name.startswith("~$"))
    if not arquivos:
        sys.exit(f"nenhum .xlsx em {entrada}")

    partes = [processa_arquivo(p) for p in arquivos]
    barras = pd.concat([p["barras"] for p in partes], ignore_index=True)
    inventario = pd.concat([p["inventario"] for p in partes], ignore_index=True).drop_duplicates()
    cadastro = pd.concat([p["cadastro"] for p in partes], ignore_index=True)

    anotacoes = barras[barras["reserva"].isna()].copy()
    barras = barras[barras["reserva"].notna()].copy()
    barras["reserva"] = barras["reserva"].astype(int)

    room_nights = explode_noites(barras)
    room_nights["data_noite"] = pd.to_datetime(room_nights["data_noite"])
    room_nights, fora = aplica_janela(room_nights, "data_noite")
    if len(fora):
        print(f"\n! {len(fora)} room-nights fora da janela "
              f"{JANELA_INICIO}..{JANELA_FIM} — descartadas (ver descartados.csv)")
        fora.to_csv(saida / "descartados.csv", index=False)

    estadias = monta_estadias(room_nights)

    # ---- inventário: o denominador -----------------------------------------
    inventario["data_ref"] = pd.to_datetime(
        dict(year=inventario.ano, month=inventario.mes, day=1)
    )
    inventario = inventario[
        (inventario.data_ref.dt.date >= JANELA_INICIO.replace(day=1))
        & (inventario.data_ref.dt.date <= JANELA_FIM)
    ]
    inventario["temporada"] = inventario["data_ref"].dt.date.map(temporada)
    qtd_quartos = inventario.groupby(["ano", "mes"]).quarto.nunique()

    # ---- integridade: quarto vendido tem que existir no inventário ----------
    rn = room_nights.copy()
    rn["ano"], rn["mes"] = rn.data_noite.dt.year, rn.data_noite.dt.month
    orfaos = rn.merge(inventario[["ano", "mes", "quarto"]].assign(_ok=1),
                      on=["ano", "mes", "quarto"], how="left")
    orfaos = orfaos[orfaos._ok.isna()]

    # ---- divergências mapa x cadastro --------------------------------------
    divergencias = pd.DataFrame()
    if not cadastro.empty and "n°" in cadastro.columns:
        cad = cadastro.copy()
        cad["n°"] = pd.to_numeric(cad["n°"], errors="coerce")
        cad = cad.dropna(subset=["n°"]).drop_duplicates(subset=["n°"])
        mapa = (
            estadias.groupby("reserva")
            .agg(quartos_mapa=("quarto", lambda s: sorted(set(s))),
                 check_in_mapa=("check_in", "min"),
                 check_out_mapa=("check_out", "max"),
                 diarias_mapa=("diarias", "max"))
            .reset_index()
        )
        j = mapa.merge(cad, left_on="reserva", right_on="n°", how="left")
        if "Quarto" in j.columns:
            j["quartos_cadastro"] = j["Quarto"].map(expande_quartos_cadastro)
        for origem, destino in (("check-in", "check_in_cad"), ("check-out", "check_out_cad")):
            if origem in j.columns:
                j[destino] = pd.to_datetime(j[origem], errors="coerce")
        j["sem_cadastro"] = j["n°"].isna()
        j["conflito_quarto"] = j.apply(
            lambda r: (r.get("quartos_cadastro") is not None
                       and r["quartos_cadastro"] != ["*TODOS*"]
                       and r["quartos_cadastro"] != r["quartos_mapa"]),
            axis=1,
        )
        j["conflito_checkin"] = j.get("check_in_cad", pd.NaT) != j["check_in_mapa"]
        divergencias = j[j.sem_cadastro | j.conflito_quarto | j.conflito_checkin]

    # ---- resumo mensal ------------------------------------------------------
    resumo = rn.groupby(["ano", "mes"]).size().rename("room_nights").reset_index()
    resumo["quartos"] = resumo.set_index(["ano", "mes"]).index.map(qtd_quartos)
    resumo["dias"] = resumo.apply(lambda r: calendar.monthrange(int(r.ano), int(r.mes))[1], axis=1)
    resumo["disponiveis"] = resumo.quartos * resumo.dias
    resumo["ocupacao_pct"] = (100 * resumo.room_nights / resumo.disponiveis).round(1)
    resumo["temporada"] = resumo.apply(
        lambda r: temporada(dt.date(int(r.ano), int(r.mes), 1)), axis=1
    )

    for nome, df in [
        ("room_nights", room_nights), ("estadias", estadias),
        ("inventario_mensal", inventario.drop(columns=["data_ref"])),
        ("divergencias", divergencias), ("resumo_mensal", resumo),
        ("anotacoes_mapa", anotacoes), ("quartos_orfaos", orfaos),
    ]:
        df.to_csv(saida / f"{nome}.csv", index=False)

    print(f"""
{'='*62}
  janela            {JANELA_INICIO} .. {JANELA_FIM}
  room-nights       {len(room_nights):>7}
  estadias          {len(estadias):>7}   (grão reserva x quarto)
  reservas          {estadias.reserva.nunique():>7}
  meses c/ dado     {len(resumo):>7}
  quartos (min-máx) {qtd_quartos.min():>7} a {qtd_quartos.max()}
  divergências      {len(divergencias):>7}   <- revisar
  quartos órfãos    {len(orfaos):>7}   <- tem que ser 0
  anotações livres  {len(anotacoes):>7}
{'='*62}
  saída em {saida.resolve()}
""")


if __name__ == "__main__":
    main()
