"""
consolida_fontes.py — Guest Flow / consolidação das 24 planilhas

Roda ANTES (ou junto com) a extração. Resolve o problema de ter o mesmo
período registrado em vários arquivos.

ESTRATÉGIA: união primeiro, precedência só no conflito
------------------------------------------------------
1. Extrai as barras de TODOS os arquivos-mapa.
2. Une tudo. Uma estadia que aparece em qualquer arquivo é recuperada —
   é isso que faz a redundância virar cobertura.
3. Conflito = mesma (reserva, quarto) com conjuntos de noites DIFERENTES
   em arquivos diferentes. Só aí a precedência é acionada.
4. A precedência premia CONTEMPORANEIDADE, não recência.

POR QUE NÃO "O ARQUIVO MAIS RECENTE GANHA"
-------------------------------------------
Os arquivos com data de modificação de 2026 são derivados de tentativas
anteriores de limpeza — são justamente os que distorceram os números. Os
arquivos de 2011–2019 foram escritos DURANTE a operação: são registro
primário. Um mapa de 2013 salvo em 2013 vale mais que o mesmo mapa
copiado para um arquivo mexido em 2026.

    score = 0    arquivo salvo no mesmo ano do bloco (registro vivo)
    score = n    arquivo salvo n anos depois do bloco
    score = 500  arquivo salvo ANTES do bloco (impossível: dado importado)
    score = 900  arquivo pós-operação (>= CORTE_DERIVADO)

Menor score vence. Empate: quem tiver mais barras no bloco.

Uso:
    python consolida_fontes.py --entrada ./fontes --saida ./data/raw
    python consolida_fontes.py --entrada ./fontes --apenas-catalogo
"""

from __future__ import annotations

import argparse
import calendar
import datetime as dt
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pandas as pd
from openpyxl import load_workbook

from extrai_mapa import (
    ABA_CADASTRO, JANELA_FIM, JANELA_INICIO, RE_ABA_MAPA,
    expande_quartos_cadastro, explode_noites, le_aba, monta_estadias, parse_pax, temporada,
)

# Arquivos gerados por limpezas anteriores. NÃO são fonte primária: entram
# só como referência opcional, nunca como origem de hospedagem.
RE_DERIVADO = re.compile(r"(limpo|geo|padronizado|consolidad)", re.IGNORECASE)

# A pousada encerrou em 2020. Arquivo tocado depois disso é pós-operação.
CORTE_DERIVADO = 2020

# Reservas confirmadas manualmente (pelo proprietário) como não pertencentes
# à pousada — não são erro de parsing, são registro de outro negócio que
# parou no cadastro por engano. Excluídas na origem, antes de qualquer
# processamento, pra não aparecer em nenhuma tabela derivada.
#   614: "Sobrado", 2009-02-14/15 — hospedagem que não foi da pousada.
RESERVAS_EXCLUIDAS_MANUALMENTE = {614}

# Quantidade e numeração de quartos por período, informada diretamente pelo
# proprietário (não é dado extraído das planilhas) — cobre exatamente o
# buraco de 2006-2008, onde nenhum arquivo tem aba de mapa. Cruzado contra
# o inventário extraído dos mapas: 88/102 meses batem exatamente; as
# divergências viram conflitos_inventario_seed.csv, não são sobrescritas
# silenciosamente (podem ser transição em data levemente diferente da
# memória, ou quarto fechado temporariamente — ex.: K1 sumiu do mapa de
# set/2010 a mai/2011).
QUARTOS_POR_PERIODO = [
    ("2006-10-01", "2007-12-01", [str(n) for n in range(1, 7)]),
    ("2007-12-01", "2009-01-11", [str(n) for n in range(1, 8)]),
    ("2009-01-11", "2010-04-01", [str(n) for n in range(1, 10)]),
    ("2010-04-01", "2013-03-29", [str(n) for n in range(1, 10)] + [f"K{k}" for k in range(1, 7)]),
    ("2013-03-29", "2015-01-19", [str(n) for n in range(1, 10)]),
    ("2015-01-19", "2017-07-29", [str(n) for n in range(1, 12)]),
]


def quartos_vigentes(data: pd.Timestamp | dt.date) -> list[str] | None:
    """Lista de quartos que existiam na pousada numa data, segundo o
    proprietário. None se a data está fora de qualquer período informado."""
    d = pd.Timestamp(data)
    for ini, fim, quartos in QUARTOS_POR_PERIODO:
        if pd.Timestamp(ini) <= d < pd.Timestamp(fim):
            return quartos
    return None

NS_CORE = {"dcterms": "http://purl.org/dc/terms/"}


def data_interna_xlsx(p: Path) -> dt.date | None:
    """
    Data de modificação gravada DENTRO do .xlsx (docProps/core.xml), escrita
    pelo Excel no momento do save — sobrevive a cópias, sync do OneDrive e
    reorganização de pastas, ao contrário de st_mtime do sistema de arquivos.

    Sem isso, todo arquivo copiado para uma pasta nova carimba a mesma data
    de hoje e a precedência por contemporaneidade (score_fonte) não tem mais
    como distinguir registro vivo de cópia de segunda mão.
    """
    try:
        with zipfile.ZipFile(p) as z:
            core = ET.fromstring(z.read("docProps/core.xml"))
    except (KeyError, zipfile.BadZipFile, ET.ParseError):
        return None
    for tag in ("modified", "created"):
        el = core.find(f"dcterms:{tag}", NS_CORE)
        if el is not None and el.text:
            try:
                return dt.datetime.fromisoformat(el.text.replace("Z", "+00:00")).date()
            except ValueError:
                continue
    return None


# ---------------------------------------------------------------------------
# Catálogo
# ---------------------------------------------------------------------------

def cataloga(pasta: Path) -> pd.DataFrame:
    """Varre a pasta e diz o que cada arquivo contém, sem extrair nada."""
    linhas = []
    for p in sorted(pasta.rglob("*")):
        if p.name.startswith("~$") or not p.is_file():
            continue
        data_interna = data_interna_xlsx(p) if p.suffix.lower() in (".xlsx", ".xlsm") else None
        if data_interna is not None:
            data_ref, origem_data = data_interna, "interno"
        else:
            data_ref = dt.datetime.fromtimestamp(p.stat().st_mtime).date()
            origem_data = "sistema_arquivos"
        base = {
            "arquivo": p.name,
            "caminho": str(p),
            "modificado_em": data_ref,
            "origem_data": origem_data,
            "kb": round(p.stat().st_size / 1024),
            "derivado_por_nome": bool(RE_DERIVADO.search(p.name)),
            "pos_operacao": data_ref.year >= CORTE_DERIVADO,
        }
        if p.suffix.lower() == ".csv":
            linhas.append({**base, "tipo": "csv", "abas_mapa": "", "tem_cadastro": None})
            continue
        if p.suffix.lower() not in (".xlsx", ".xlsm"):
            continue
        try:
            wb = load_workbook(p, read_only=True)
            abas = [a for a in wb.sheetnames if RE_ABA_MAPA.match(a)]
            linhas.append({
                **base,
                "tipo": "mapa" if abas else "planilha_sem_mapa",
                "abas_mapa": " | ".join(abas),
                "tem_cadastro": ABA_CADASTRO in wb.sheetnames,
            })
            wb.close()
        except Exception as e:  # arquivo corrompido, protegido por senha, etc.
            linhas.append({**base, "tipo": f"erro: {type(e).__name__}",
                           "abas_mapa": "", "tem_cadastro": None})
    return pd.DataFrame(linhas)


# ---------------------------------------------------------------------------
# Precedência
# ---------------------------------------------------------------------------

def score_fonte(ano_bloco: int, ano_arquivo: int) -> int:
    if ano_arquivo >= CORTE_DERIVADO:
        return 900
    if ano_arquivo < ano_bloco:
        return 500
    return ano_arquivo - ano_bloco


# ---------------------------------------------------------------------------
# Extração multi-arquivo
# ---------------------------------------------------------------------------

def extrai_todos(catalogo: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """
    Lê barras, inventário (coluna A) e cadastro de todo arquivo-mapa, com o
    mesmo score de contemporaneidade anexado às três coisas — é o que deixa
    inventário e cadastro passarem pela mesma arbitragem que já vale para as
    room-nights, em vez de virarem uma concatenação ingênua dos 24 arquivos.
    """
    barras, inventario, cadastros = [], [], []
    mapas = catalogo[(catalogo.tipo == "mapa") & (~catalogo.derivado_por_nome)]
    if mapas.empty:
        sys.exit("nenhum arquivo com abas de mapa encontrado")

    for r in mapas.itertuples(index=False):
        print(f"\n>> {r.arquivo}  ({r.modificado_em}, {r.kb} KB)", flush=True)
        wb = load_workbook(r.caminho, data_only=True)
        for aba in wb.sheetnames:
            m = RE_ABA_MAPA.match(aba)
            if not m:
                continue
            b, inv = le_aba(wb[aba], int(m.group(1)))
            for x in b:
                x["arquivo"] = r.arquivo
                x["ano_arquivo"] = r.modificado_em.year
                x["score"] = score_fonte(x["ano"], r.modificado_em.year)
            for x in inv:
                x["arquivo"] = r.arquivo
                x["score"] = score_fonte(x["ano"], r.modificado_em.year)
            print(f"   {aba}: {len(b)} barras", flush=True)
            barras += b
            inventario += inv
        if r.tem_cadastro:
            cad = pd.read_excel(r.caminho, sheet_name=ABA_CADASTRO)
            cad.columns = [str(c).strip() for c in cad.columns]
            cad["arquivo"] = r.arquivo
            cad["pos_operacao"] = r.pos_operacao
            cad["kb"] = r.kb
            cadastros.append(cad)
        wb.close()

    barras_df = pd.DataFrame(barras)
    anotacoes = barras_df[barras_df["reserva"].isna()].drop_duplicates(
        subset=["ano", "mes", "quarto", "rotulo", "col_ini", "col_fim"]
    )
    barras_df = barras_df[barras_df["reserva"].notna()].copy()
    barras_df["reserva"] = barras_df["reserva"].astype(int)

    return {
        "barras": barras_df,
        "inventario": pd.DataFrame(inventario),
        "anotacoes": anotacoes,
        "cadastro": pd.concat(cadastros, ignore_index=True) if cadastros else pd.DataFrame(),
    }


def consolida(barras: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Devolve (room_nights_consolidado, conflitos, cobertura_por_arquivo).
    """
    # noites por arquivo
    pedacos = []
    for arquivo, g in barras.groupby("arquivo"):
        rn = explode_noites(g)
        rn["arquivo"] = arquivo
        rn["score"] = g["score"].min()
        pedacos.append(rn)
    todas = pd.concat(pedacos, ignore_index=True)
    todas["data_noite"] = pd.to_datetime(todas["data_noite"])

    # assinatura da estadia dentro de cada arquivo
    assin = (
        todas.groupby(["arquivo", "reserva", "quarto"])
        .agg(noites=("data_noite", lambda s: tuple(sorted(s.dt.date))),
             score=("score", "min"))
        .reset_index()
    )
    assin["n_noites"] = assin.noites.map(len)

    # conflito = mesma (reserva, quarto) com assinaturas diferentes
    variantes = assin.groupby(["reserva", "quarto"]).noites.nunique()
    chaves_conflito = set(variantes[variantes > 1].index)

    conflitos = assin[
        assin.set_index(["reserva", "quarto"]).index.isin(chaves_conflito)
    ].copy()
    conflitos["primeira_noite"] = conflitos.noites.map(lambda t: t[0])
    conflitos["ultima_noite"] = conflitos.noites.map(lambda t: t[-1])

    # vencedor: menor score, desempate por mais noites
    vencedores = (
        conflitos.sort_values(["reserva", "quarto", "score", "n_noites"],
                              ascending=[True, True, True, False])
        .drop_duplicates(subset=["reserva", "quarto"])[["arquivo", "reserva", "quarto"]]
        .assign(_venceu=1)
    )
    conflitos = conflitos.merge(vencedores, on=["arquivo", "reserva", "quarto"], how="left")
    conflitos["venceu"] = conflitos._venceu.fillna(0).astype(bool)
    conflitos = conflitos.drop(columns=["_venceu", "noites"])

    # consolidação: fora do conflito, união simples; no conflito, só o vencedor
    tem_conflito = todas.set_index(["reserva", "quarto"]).index.isin(chaves_conflito)
    limpo = todas[~tem_conflito]
    resolvido = todas[tem_conflito].merge(vencedores, on=["arquivo", "reserva", "quarto"])
    consolidado = pd.concat([limpo, resolvido.drop(columns=["_venceu"])], ignore_index=True)
    consolidado = consolidado.drop_duplicates(subset=["reserva", "quarto", "data_noite"])

    # quanto cada arquivo contribuiu de exclusivo
    contagem = todas.groupby(["reserva", "quarto", "data_noite"]).arquivo.nunique()
    unicas = contagem[contagem == 1].index
    exclusivo = (
        todas.set_index(["reserva", "quarto", "data_noite"])
        .loc[todas.set_index(["reserva", "quarto", "data_noite"]).index.isin(unicas)]
        .groupby("arquivo").size().rename("noites_exclusivas")
    )
    cobertura = (
        todas.groupby("arquivo")
        .agg(noites=("data_noite", "size"),
             primeiro=("data_noite", "min"), ultimo=("data_noite", "max"))
        .join(exclusivo).fillna({"noites_exclusivas": 0}).reset_index()
    )
    cobertura["noites_exclusivas"] = cobertura.noites_exclusivas.astype(int)

    return consolidado, conflitos, cobertura.sort_values("noites_exclusivas", ascending=False)


def consolida_inventario(inventario: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Denominador = união dos quartos que QUALQUER arquivo-mapa declara para o
    mês, não o vencedor por score. Testado contra os dados reais: toda
    divergência encontrada era um arquivo com uma coluna A mais curta que a
    de outro (cópia antiga que não foi atualizada quando um quarto/kitnet
    entrou em operação) — nunca dois arquivos com listas contraditórias.
    Arbitrar por contemporaneidade aqui teria o efeito oposto do pretendido:
    um quarto com reserva real vendida (prova positiva de que existia) saía
    do inventário só porque a cópia "vencedora" esqueceu de listá-lo —
    exatamente o quartos_orfaos que o teste de integridade existe para pegar.
    conflitos_inventario.csv guarda as divergências para auditoria, mas não
    impede a união (mesma filosofia de "união primeiro" das room-nights).
    """
    por_arquivo = (
        inventario.groupby(["ano", "mes", "arquivo"])
        .agg(quartos=("quarto", lambda s: tuple(sorted(set(s), key=str))),
             score=("score", "min"))
        .reset_index()
    )
    variantes = por_arquivo.groupby(["ano", "mes"]).quartos.nunique()
    chaves_conflito = set(variantes[variantes > 1].index)
    conflitos = por_arquivo[
        por_arquivo.set_index(["ano", "mes"]).index.isin(chaves_conflito)
    ].copy()
    if not conflitos.empty:
        conflitos["quartos"] = conflitos["quartos"].map(lambda t: "|".join(t))

    resolvido = (
        inventario[["ano", "mes", "quarto"]]
        .drop_duplicates()
        .sort_values(["ano", "mes", "quarto"])
        .reset_index(drop=True)
    )
    return resolvido, conflitos


def monta_fato_reserva(
    estadias: pd.DataFrame, cadastro: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Devolve (fato_reserva, dim_hospede, divergencias). Grão reserva.

    Regra do CLAUDE.md §10: mapa vence quarto/check-in/check-out (fonte
    "alta" — é o mapa visual de ocupação); cadastro vence identidade do
    hóspede, pax e valor (fonte "média" — datas e quartos com erro, mas é
    a única origem desses campos). Reserva divergente NÃO é excluída: entra
    com flag_divergencia + tipo_divergencia, valor do mapa preservado.

    dim_hospede é grão reserva x hóspede (uma linha por reserva) — a fonte
    não tem identificador estável de hóspede entre reservas diferentes, e
    tentar casar por nome+telefone arriscaria juntar duas pessoas por
    coincidência de forma silenciosa.
    """
    mapa = (
        estadias.groupby("reserva")
        .agg(quartos_mapa=("quarto", lambda s: sorted(set(s))),
             check_in_mapa=("check_in", "min"),
             check_out_mapa=("check_out", "max"),
             diarias_total_mapa=("diarias", "sum"))
        .reset_index()
    )

    tem_cadastro = not cadastro.empty and "n°" in cadastro.columns
    j = (
        mapa.merge(cadastro, left_on="reserva", right_on="n°", how="left")
        if tem_cadastro else mapa.assign(**{"n°": pd.NA})
    )

    j["quartos_cadastro"] = j["Quarto"].map(expande_quartos_cadastro) if "Quarto" in j.columns else None
    for origem, destino in (("check-in", "check_in_cad"), ("check-out", "check_out_cad")):
        j[destino] = pd.to_datetime(j[origem], errors="coerce") if origem in j.columns else pd.NaT

    j["sem_cadastro"] = j["n°"].isna()
    j["conflito_quarto"] = j.apply(
        lambda r: (r.get("quartos_cadastro") is not None
                   and r["quartos_cadastro"] != ["*TODOS*"]
                   and r["quartos_cadastro"] != r["quartos_mapa"]),
        axis=1,
    )
    # NaT (cadastro sem check-in) não é "conflito de data" — já cai em
    # sem_cadastro ou fica sem informação; só compara quando os dois existem.
    j["conflito_checkin"] = j["check_in_cad"].notna() & (j["check_in_cad"] != j["check_in_mapa"])

    def _tipo(r):
        t = []
        if r.sem_cadastro:
            t.append("sem_cadastro")
        if r.conflito_quarto:
            t.append("quarto")
        if r.conflito_checkin:
            t.append("data")
        return "|".join(t) or None

    j["tipo_divergencia"] = j.apply(_tipo, axis=1)
    j["flag_divergencia"] = j.sem_cadastro | j.conflito_quarto | j.conflito_checkin
    divergencias = j[j.flag_divergencia].copy()

    pax = (
        j["Pax"].map(parse_pax).apply(pd.Series) if "Pax" in j.columns
        else pd.DataFrame(index=j.index)
    )
    for col in ("pax_adulto", "pax_crianca_pag", "pax_crianca_free", "config_cama", "pax_bruto"):
        if col not in pax.columns:
            pax[col] = None

    fato_reserva = pd.DataFrame({
        "reserva": j["reserva"],
        "hospede_id": j["reserva"],
        "check_in": j["check_in_mapa"],
        "check_out": j["check_out_mapa"],
        "quartos": j["quartos_mapa"].map(lambda q: "|".join(q)),
        "n_quartos": j["quartos_mapa"].map(len),
        "diarias_total": j["diarias_total_mapa"],
        "data_reserva": pd.to_datetime(j.get("data/reserva"), errors="coerce"),
        "valor_total": j.get("Valor total"),
        "valor_diaria_cadastro": j.get("Valor diária"),
        "n_diarias_cadastro": j.get("nº diárias"),
        "pax_adulto": pax["pax_adulto"],
        "pax_crianca_pag": pax["pax_crianca_pag"],
        "pax_crianca_free": pax["pax_crianca_free"],
        "pax_total": pax[["pax_adulto", "pax_crianca_pag", "pax_crianca_free"]].sum(axis=1, min_count=1),
        "pax_pagante": pax[["pax_adulto", "pax_crianca_pag"]].sum(axis=1, min_count=1),
        "config_cama": pax["config_cama"],
        "flag_divergencia": j["flag_divergencia"],
        "tipo_divergencia": j["tipo_divergencia"],
    })

    dim_hospede = pd.DataFrame({
        "hospede_id": j["reserva"],
        "reserva": j["reserva"],
        "nome": j.get("Hóspede"),
        "tel_1": j.get("Tel 1"),
        "tel_2": j.get("Tel 2"),
        "email": j.get("E-mail"),
        "cidade": j.get("Cidade"),
        "estado": j.get("Estado"),
        "aniversario": pd.to_datetime(j.get("Aniversário"), errors="coerce"),
        "acompanhantes": j.get("Acompanhantes"),
        "motivo_viagem": j.get("Motivo da viagem"),
        "sem_cadastro": j["sem_cadastro"],
    })

    return fato_reserva, dim_hospede, divergencias


def rateia_valor_por_quarto(estadias: pd.DataFrame, fato_reserva: pd.DataFrame) -> pd.DataFrame:
    """
    Enriquece estadias (grão reserva x quarto) com valor_alocado. Regra do
    CLAUDE.md §11: proporcional às DIÁRIAS de cada quarto, nunca ao número
    de quartos — numa reserva de grupo os quartos podem durar dias
    diferentes. fato_reserva.valor_total continua intocado; isto é só a
    quebra por quarto.

    Aloca em centavos inteiros; a sobra do arredondamento vai para o quarto
    de maior diária (empate: o de menor número, primeiro na ordenação).
    estadia_id é o id por linha que faltava para separar quartos de uma
    mesma reserva; hospede_id repete entre eles de propósito (mesmo
    hóspede/reserva, quartos diferentes).
    """
    e = estadias.sort_values(["reserva", "quarto"]).reset_index(drop=True)
    e["estadia_id"] = e.index + 1
    e["hospede_id"] = e["reserva"]

    valor_total = fato_reserva.set_index("reserva")["valor_total"]
    diarias_total = fato_reserva.set_index("reserva")["diarias_total"]

    def _aloca(grupo: pd.DataFrame) -> pd.Series:
        total = valor_total.get(grupo.name)
        total_diarias = diarias_total.get(grupo.name)
        if pd.isna(total) or not total_diarias:
            return pd.Series(pd.NA, index=grupo.index, dtype="object")
        total_centavos = round(total * 100)
        centavos = (grupo["diarias"] / total_diarias * total_centavos).apply(
            lambda x: int(x // 1)
        )
        sobra = total_centavos - centavos.sum()
        if sobra:
            alvo = grupo["diarias"].idxmax()
            centavos[alvo] += sobra
        return centavos / 100

    e["valor_alocado"] = e.groupby("reserva", group_keys=False).apply(_aloca)
    e["metodo_alocacao"] = e["valor_alocado"].notna().map(
        {True: "rateio_por_diarias", False: None}
    )
    return e


def monta_reservas_so_cadastro(
    cadastro: pd.DataFrame, reservas_cobertas: set[int]
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Reservas com registro em `controle hóspedes` mas sem nenhuma aba de
    mapa cobrindo o período (ex.: 2006-2008, antes do primeiro arquivo-mapa
    disponível — não é conflito, é ausência total). Sem mapa, quarto/
    check-in/check-out vêm só do cadastro: confiabilidade "média"
    (CLAUDE.md §2), nunca "alta". Marcadas com origem_dado='so_cadastro'
    para não se confundir com reserva confirmada pelo mapa
    (origem_dado='mapa_confirmado').

    Devolve (fato_reserva, estadias, dim_hospede, sem_quarto). `Quarto`
    vazio ou não interpretável ("todos", texto livre) não vira estadia —
    não se inventa quarto; a reserva ainda entra em fato_reserva
    (quartos=None) e a linha crua vai para `sem_quarto`, pendência de
    revisão manual.
    """
    vazio = pd.DataFrame()
    if cadastro.empty or "n°" not in cadastro.columns:
        return vazio, vazio, vazio, vazio

    c = cadastro.copy()
    c["n°"] = pd.to_numeric(c["n°"], errors="coerce")
    c = c.dropna(subset=["n°"])
    c["n°"] = c["n°"].astype(int)
    c = c[~c["n°"].isin(reservas_cobertas)]

    c["check_in"] = pd.to_datetime(c.get("check-in"), errors="coerce")
    c["check_out"] = pd.to_datetime(c.get("check-out"), errors="coerce")
    c = c[c["check_in"].notna() & c["check_out"].notna()]
    d = c["check_in"].dt.date
    c = c[(d >= JANELA_INICIO) & (d <= JANELA_FIM)]
    c["diarias"] = (c["check_out"] - c["check_in"]).dt.days
    c = c[c["diarias"] > 0]
    if c.empty:
        return vazio, vazio, vazio, vazio

    c["quartos_list"] = (
        c["Quarto"].map(expande_quartos_cadastro) if "Quarto" in c.columns else None
    )
    # "todos os quartos": expande pra lista real vigente naquela data (dado
    # do proprietário), em vez de deixar como pendência sem quarto — só
    # quando o CHECK_IN cai dentro de um período conhecido.
    e_todos = c["quartos_list"].map(lambda q: q == ["*TODOS*"])
    c.loc[e_todos, "quartos_list"] = c.loc[e_todos, "check_in"].map(quartos_vigentes)
    quarto_ok = c["quartos_list"].map(lambda q: bool(q))

    pax = (
        c["Pax"].map(parse_pax).apply(pd.Series) if "Pax" in c.columns
        else pd.DataFrame(index=c.index)
    )
    for col in ("pax_adulto", "pax_crianca_pag", "pax_crianca_free", "config_cama", "pax_bruto"):
        if col not in pax.columns:
            pax[col] = None

    fato = pd.DataFrame({
        "reserva": c["n°"],
        "hospede_id": c["n°"],
        "check_in": c["check_in"],
        "check_out": c["check_out"],
        "quartos": c["quartos_list"].map(lambda q: "|".join(q) if q else None),
        "n_quartos": c["quartos_list"].map(lambda q: len(q) if q and q != ["*TODOS*"] else None),
        # cadastro só dá UM intervalo de datas pra reserva inteira, mesmo
        # quando tem vários quartos — então diarias_total (usado no rateio
        # da §11) tem que multiplicar pelos quartos, senão cada quarto
        # herda 100% do valor e o rateio.py estraga (achado real: reserva
        # 157, quarto 1 saiu com R$0 e quarto 2 com o valor inteiro).
        "diarias_total": c["diarias"] * c["quartos_list"].map(lambda q: len(q) if q else 1),
        "data_reserva": pd.to_datetime(c.get("data/reserva"), errors="coerce"),
        "valor_total": c.get("Valor total"),
        "valor_diaria_cadastro": c.get("Valor diária"),
        "n_diarias_cadastro": c.get("nº diárias"),
        "pax_adulto": pax["pax_adulto"],
        "pax_crianca_pag": pax["pax_crianca_pag"],
        "pax_crianca_free": pax["pax_crianca_free"],
        "pax_total": pax[["pax_adulto", "pax_crianca_pag", "pax_crianca_free"]].sum(axis=1, min_count=1),
        "pax_pagante": pax[["pax_adulto", "pax_crianca_pag"]].sum(axis=1, min_count=1),
        "config_cama": pax["config_cama"],
        "flag_divergencia": False,
        "tipo_divergencia": None,
        "origem_dado": "so_cadastro",
    })

    exp = c[quarto_ok].explode("quartos_list").rename(columns={"quartos_list": "quarto"})
    estadias = pd.DataFrame({
        "reserva": exp["n°"],
        "quarto": exp["quarto"],
        "diarias": exp["diarias"],
        "check_in": exp["check_in"],
        "check_out": exp["check_out"],
        "temporada": exp["check_in"].map(temporada),
        "suspeita_num_reaproveitado": False,
        "origem_dado": "so_cadastro",
    })

    dim_hospede = pd.DataFrame({
        "hospede_id": c["n°"],
        "reserva": c["n°"],
        "nome": c.get("Hóspede"),
        "tel_1": c.get("Tel 1"),
        "tel_2": c.get("Tel 2"),
        "email": c.get("E-mail"),
        "cidade": c.get("Cidade"),
        "estado": c.get("Estado"),
        "aniversario": pd.to_datetime(c.get("Aniversário"), errors="coerce"),
        "acompanhantes": c.get("Acompanhantes"),
        "motivo_viagem": c.get("Motivo da viagem"),
        "sem_cadastro": False,
    })

    sem_quarto = c.loc[~quarto_ok, ["n°", "Hóspede", "Quarto", "check_in", "check_out"]].rename(
        columns={"n°": "reserva", "Hóspede": "hospede"}
    )

    return fato, estadias, dim_hospede, sem_quarto


def resolve_hospedes(dim_hospede: pd.DataFrame) -> pd.DataFrame:
    """
    Resolve hóspede único entre reservas diferentes, por telefone/e-mail
    normalizado — nunca por nome sozinho (risco de juntar duas pessoas
    homônimas silenciosamente, o mesmo motivo pelo qual dim_hospede é
    grão reserva). Não altera dim_hospede; isto é uma camada de
    resolução à parte, com o método de match explícito por reserva, para
    permitir métricas como taxa de retorno sem comprometer a decisão
    original.

    Aproximação, não identidade garantida: telefone compartilhado (casal,
    terceiro que reserva pra outros) pode gerar falso positivo; troca de
    número ao longo dos 10 anos pode gerar falso negativo.
    """
    dh = dim_hospede[["hospede_id", "reserva", "tel_1", "tel_2", "email"]].copy()

    def norm_tel(t):
        if pd.isna(t):
            return None
        d = re.sub(r"\D", "", str(t))
        return d if len(d) >= 8 else None

    def norm_email(e):
        if pd.isna(e):
            return None
        e = str(e).strip().lower().rstrip(";").strip()
        return e if "@" in e and "." in e.split("@")[-1] else None

    dh["tel1_n"] = dh["tel_1"].map(norm_tel)
    dh["tel2_n"] = dh["tel_2"].map(norm_tel)
    dh["email_n"] = dh["email"].map(norm_email)

    pai: dict[int, int] = {r: r for r in dh["reserva"]}

    def raiz(x: int) -> int:
        while pai[x] != x:
            pai[x] = pai[pai[x]]
            x = pai[x]
        return x

    def uniao(a: int, b: int) -> None:
        ra, rb = raiz(a), raiz(b)
        if ra != rb:
            pai[max(ra, rb)] = min(ra, rb)

    for chave in ("tel1_n", "tel2_n", "email_n"):
        for _, grupo in dh.dropna(subset=[chave]).groupby(chave)["reserva"]:
            base = grupo.iloc[0]
            for r in grupo.iloc[1:]:
                uniao(base, r)

    dh["hospede_unico_id"] = dh["reserva"].map(raiz)

    def metodo_do_grupo(g: pd.DataFrame) -> str:
        if len(g) == 1:
            return "sem_match"
        tels = pd.concat([g["tel1_n"], g["tel2_n"]]).dropna()
        tem_tel = tels.duplicated().any()
        tem_email = g["email_n"].dropna().duplicated().any()
        if tem_tel and tem_email:
            return "telefone+email"
        return "telefone" if tem_tel else ("email" if tem_email else "sem_match")

    metodo_por_grupo = dh.groupby("hospede_unico_id").apply(
        metodo_do_grupo, include_groups=False
    )
    dh["metodo_match"] = dh["hospede_unico_id"].map(metodo_por_grupo)
    dh["n_reservas_do_hospede"] = dh.groupby("hospede_unico_id")["reserva"].transform("nunique")

    return dh[["reserva", "hospede_unico_id", "metodo_match", "n_reservas_do_hospede"]]


def consolida_cadastro(cadastro: pd.DataFrame) -> pd.DataFrame:
    """
    Cadastro se repete quase igual entre cópias do mesmo arquivo. No mesmo
    nº de reserva duplicado entre arquivos, prefere o não-pós-operação;
    empate, o maior (mais completo) — mesma lógica de contemporaneidade,
    só que sem um "ano de bloco" para comparar, então usa o arquivo inteiro.
    """
    if cadastro.empty or "n°" not in cadastro.columns:
        return pd.DataFrame()
    cad = cadastro.copy()
    cad["n°"] = pd.to_numeric(cad["n°"], errors="coerce")
    cad = cad.dropna(subset=["n°"])
    cad = cad.sort_values(["pos_operacao", "kb"], ascending=[True, False])
    return cad.drop_duplicates(subset=["n°"])


# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entrada", required=True)
    ap.add_argument("--saida", default="./data/raw")
    ap.add_argument("--apenas-catalogo", action="store_true")
    args = ap.parse_args()

    entrada, saida = Path(args.entrada), Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)

    catalogo = cataloga(entrada)
    catalogo.to_csv(saida / "catalogo_fontes.csv", index=False)
    print(catalogo[["arquivo", "modificado_em", "origem_data", "kb", "tipo",
                    "tem_cadastro", "pos_operacao"]].to_string(index=False))
    if args.apenas_catalogo:
        print(f"\ncatálogo em {saida/'catalogo_fontes.csv'}")
        return

    partes = extrai_todos(catalogo)
    consolidado, conflitos, cobertura = consolida(partes["barras"])
    inventario, conflitos_inventario = consolida_inventario(partes["inventario"])
    cadastro = consolida_cadastro(partes["cadastro"])

    consolidado = consolidado[~consolidado["reserva"].isin(RESERVAS_EXCLUIDAS_MANUALMENTE)]
    if "n°" in cadastro.columns:
        cadastro = cadastro[~cadastro["n°"].isin(RESERVAS_EXCLUIDAS_MANUALMENTE)]

    d = consolidado.data_noite.dt.date
    fora = consolidado[(d < JANELA_INICIO) | (d > JANELA_FIM)]
    consolidado = consolidado[(d >= JANELA_INICIO) & (d <= JANELA_FIM)]

    inventario["data_ref"] = pd.to_datetime(
        dict(year=inventario.ano, month=inventario.mes, day=1)
    )
    inventario = inventario[
        (inventario.data_ref.dt.date >= JANELA_INICIO.replace(day=1))
        & (inventario.data_ref.dt.date <= JANELA_FIM)
    ].drop(columns=["data_ref"])
    inventario["temporada"] = inventario.apply(
        lambda r: temporada(dt.date(int(r.ano), int(r.mes), 1)), axis=1
    )
    inventario["origem"] = "mapa"

    # ---- cruza com o seed do proprietário (QUARTOS_POR_PERIODO) -------------
    # 1) meses sem NENHUM mapa (2006-2008): preenche a partir do seed — não
    #    é sobrescrita, é o único denominador que existe pra esse trecho.
    # 2) meses com mapa E seed: compara; divergência vira review, o mapa
    #    (mais granular, mês a mês real) continua sendo o que fica em
    #    inventario_mensal.csv.
    meses_com_mapa = set(zip(inventario.ano, inventario.mes))
    linhas_seed, linhas_conflito = [], []
    for ini, fim, quartos_periodo in QUARTOS_POR_PERIODO:
        for p in pd.period_range(ini, pd.Timestamp(fim) - pd.Timedelta(days=1), freq="M"):
            ano_p, mes_p = p.year, p.month
            if not (JANELA_INICIO.replace(day=1) <= dt.date(ano_p, mes_p, 1) <= JANELA_FIM):
                continue
            if (ano_p, mes_p) not in meses_com_mapa:
                linhas_seed += [
                    {"ano": ano_p, "mes": mes_p, "quarto": q,
                     "temporada": temporada(dt.date(ano_p, mes_p, 1)), "origem": "seed_proprietario"}
                    for q in quartos_periodo
                ]
            else:
                extraido = set(inventario[(inventario.ano == ano_p) & (inventario.mes == mes_p)].quarto.astype(str))
                if extraido != set(quartos_periodo):
                    linhas_conflito.append({
                        "ano": ano_p, "mes": mes_p,
                        "quartos_mapa": "|".join(sorted(extraido)),
                        "quartos_seed": "|".join(sorted(quartos_periodo)),
                        "n_mapa": len(extraido), "n_seed": len(quartos_periodo),
                    })
    seed_df = pd.DataFrame(linhas_seed)
    n_meses_seed = seed_df[["ano", "mes"]].drop_duplicates().shape[0] if not seed_df.empty else 0
    inventario = pd.concat([inventario, seed_df], ignore_index=True)
    conflitos_inventario_seed = pd.DataFrame(linhas_conflito)

    qtd_quartos = inventario.groupby(["ano", "mes"]).quarto.nunique()

    estadias = monta_estadias(consolidado)
    estadias["temporada"] = estadias.check_in.map(temporada)

    # ---- integridade: quarto vendido tem que existir no inventário ----------
    rn = consolidado.copy()
    rn["ano"], rn["mes"] = rn.data_noite.dt.year, rn.data_noite.dt.month
    orfaos = rn.merge(inventario[["ano", "mes", "quarto"]].assign(_ok=1),
                      on=["ano", "mes", "quarto"], how="left")
    orfaos = orfaos[orfaos._ok.isna()].drop(columns=["_ok"])

    # ---- fato_reserva, dim_hospede, divergências mapa x cadastro -----------
    fato_reserva, dim_hospede, divergencias = monta_fato_reserva(estadias, cadastro)
    fato_reserva["origem_dado"] = "mapa_confirmado"
    estadias["origem_dado"] = "mapa_confirmado"

    # ---- reservas que só existem no cadastro, sem nenhuma aba de mapa -------
    # (ex.: 2006-2008 — nenhum arquivo tem "Reservas 2007/2008"). Confiabilidade
    # menor (cadastro, não mapa), por isso a flag origem_dado separada.
    reservas_cobertas = set(fato_reserva["reserva"])
    fato_so_cad, estadias_so_cad, dim_hospede_so_cad, sem_quarto = monta_reservas_so_cadastro(
        cadastro, reservas_cobertas
    )
    fato_reserva = pd.concat([fato_reserva, fato_so_cad], ignore_index=True)
    estadias = pd.concat([estadias, estadias_so_cad], ignore_index=True)
    dim_hospede = pd.concat([dim_hospede, dim_hospede_so_cad], ignore_index=True)

    # ---- valor por quarto (reserva de grupo = 1 valor, N quartos) -----------
    estadias = rateia_valor_por_quarto(estadias, fato_reserva)

    # ---- resumo mensal ------------------------------------------------------
    resumo = rn.groupby(["ano", "mes"]).size().rename("room_nights").reset_index()
    resumo["quartos"] = resumo.set_index(["ano", "mes"]).index.map(qtd_quartos)
    resumo["dias"] = resumo.apply(lambda r: calendar.monthrange(int(r.ano), int(r.mes))[1], axis=1)
    resumo["disponiveis"] = resumo.quartos * resumo.dias
    resumo["ocupacao_pct"] = (100 * resumo.room_nights / resumo.disponiveis).round(1)
    resumo["temporada"] = resumo.apply(
        lambda r: temporada(dt.date(int(r.ano), int(r.mes), 1)), axis=1
    )

    # ---- hóspede único entre reservas (telefone/e-mail) ---------------------
    hospede_resolvido = resolve_hospedes(dim_hospede)

    consolidado.to_csv(saida / "room_nights.csv", index=False)
    estadias.to_csv(saida / "estadias.csv", index=False)
    conflitos.to_csv(saida / "conflitos_entre_arquivos.csv", index=False)
    cobertura.to_csv(saida / "cobertura_por_arquivo.csv", index=False)
    fora.to_csv(saida / "descartados_fora_janela.csv", index=False)
    inventario.to_csv(saida / "inventario_mensal.csv", index=False)
    conflitos_inventario.to_csv(saida / "conflitos_inventario.csv", index=False)
    conflitos_inventario_seed.to_csv(saida / "conflitos_inventario_seed.csv", index=False)
    divergencias.to_csv(saida / "divergencias.csv", index=False)
    resumo.to_csv(saida / "resumo_mensal.csv", index=False)
    orfaos.to_csv(saida / "quartos_orfaos.csv", index=False)
    partes["anotacoes"].to_csv(saida / "anotacoes_mapa.csv", index=False)
    fato_reserva.to_csv(saida / "fato_reserva.csv", index=False)
    dim_hospede.to_csv(saida / "dim_hospede.csv", index=False)
    sem_quarto.to_csv(saida / "so_cadastro_sem_quarto.csv", index=False)
    hospede_resolvido.to_csv(saida / "hospede_resolvido.csv", index=False)

    n_conflitos_inv = (conflitos_inventario[["ano", "mes"]].drop_duplicates().shape[0]
                        if not conflitos_inventario.empty else 0)
    rateio_check = (
        estadias.dropna(subset=["valor_alocado"])
        .groupby("reserva")["valor_alocado"].sum()
        .round(2)
        .rename("alocado")
        .to_frame()
        .join(fato_reserva.set_index("reserva")["valor_total"].round(2))
    )
    n_rateio_ok = (rateio_check["alocado"] == rateio_check["valor_total"]).sum()
    n_rateio_total = len(rateio_check)
    n_hospedes_unicos = hospede_resolvido["hospede_unico_id"].nunique()
    n_hospedes_retornaram = (
        hospede_resolvido.drop_duplicates("hospede_unico_id")["n_reservas_do_hospede"] > 1
    ).sum()
    print(f"""
{'='*66}
  arquivos-mapa lidos       {partes['barras'].arquivo.nunique():>7}
  room-nights               {len(consolidado):>7}
  estadias                  {len(estadias):>7}
  reservas                  {estadias.reserva.nunique():>7}
  período (mapa)            {consolidado.data_noite.min().date()} .. {consolidado.data_noite.max().date()}
  período (mapa+cadastro)   {estadias.check_in.min().date()} .. {estadias.check_in.max().date()}
  quartos (min-máx)         {qtd_quartos.min():>7} a {qtd_quartos.max()}
  fato_reserva              {len(fato_reserva):>7}
  dim_hospede               {len(dim_hospede):>7}
  conflitos room-nights     {conflitos[['reserva','quarto']].drop_duplicates().shape[0]:>7}  <- revisar
  conflitos inventário      {n_conflitos_inv:>7}  <- revisar
  conflitos inventário x seed{len(conflitos_inventario_seed):>6}  <- revisar (proprietário x mapa)
  meses preenchidos pelo seed{n_meses_seed:>6}  (2006-2008, sem mapa)
  divergências mapa/cadastro{len(divergencias):>7}  <- revisar ({100*len(divergencias)/len(fato_reserva):.1f}%)
  quartos órfãos            {len(orfaos):>7}  <- tem que ser 0
  rateio valor/quarto bate  {n_rateio_ok:>7} / {n_rateio_total}  <- tem que ser igual
  reservas só cadastro      {len(fato_so_cad):>7}  (sem nenhuma aba de mapa no período)
  ...sem quarto identificável{len(sem_quarto):>6}  <- revisar (Quarto vazio/"todos")
  hóspedes únicos (tel/email){n_hospedes_unicos:>6}
  ...retornaram (>1 reserva) {n_hospedes_retornaram:>6}  ({100*n_hospedes_retornaram/n_hospedes_unicos:.1f}%)
  anotações livres          {len(partes['anotacoes']):>7}
  fora da janela            {len(fora):>7}
{'='*66}""")
    print("\ncontribuição exclusiva de cada arquivo:")
    print(cobertura.to_string(index=False))


if __name__ == "__main__":
    main()
