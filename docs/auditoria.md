# Auditoria dos dados — Guest Flow

Gerado por `scripts/auditoria.py` em 21/10/2026. Recalcula os números por caminho independente do dbt e do parser e compara.

**Resultado:** 22 OK · 2 avisos · 0 falhas

| Bloco | Verificação | Status | Detalhe |
|---|---|---|---|
| Fonte | toda noite do room_nights existe na célula de origem | OK | 9,949 noites conferidas, 0 sem correspondência |
| Fonte | nenhuma noite da planilha sumiu no caminho | OK | 0 noites das planilhas, dentro da janela, sem destino |
| Cifras | disponíveis (quarto-dias) = mart | OK | independente 41,668 · mart 41,668 |
| Cifras | room-nights vendidos = mart | OK | independente 12,160 · mart 12,160 |
| Cifras | receita de hospedagem = mart | OK | independente R$ 2,204,453.90 · mart R$ 2,204,453.90 |
| Cifras | pico mensal = mart | OK | independente 93.3% (01/2012) · mart 93.3% |
| Cifras | nº de reservas = fato_reserva | OK | 5,072 · 5,072 |
| Cifras | valor declarado total = mart_kpis | OK | R$ 2,334,611.99 · R$ 2,334,611.99 |
| Cifras | ticket médio = mart_kpis | OK | R$ 460.48 · R$ 460.48 |
| Cifras | ocupação sem contar a mesma noite duas vezes | AVISO | 425 room-nights (3.5%) repetem quarto+noite; ocupação 29.18% → 28.16% se contar distintas |
| Cifras | ADR só sobre noites com valor | OK | ADR atual R$ 181.29 · só noites com valor R$ 185.37 (268 noites sem valor) |
| Reconciliação | reservas raw → staging → mart | OK | 5,072 · 5,072 |
| Reconciliação | room_nights raw → staging | OK | 9,949 · 9,949 |
| Reconciliação | estadias raw → staging | OK | 5,487 · 5,487 |
| Reconciliação | hóspede raw → staging | OK | 5,072 · 5,072 |
| Reconciliação | valor_total raw → staging | OK | 2,334,611.99 · 2,334,611.99 |
| Reconciliação | noites completo ≤ mapa + só-cadastro (join com inventário só remove) | OK | mapa 9,949 + cadastro 2,218 = 12,167 · completo 12,160 · removidas por não estarem no inventário: 7 |
| Reconciliação | receita declarada x receita nos marts | OK | declarado R$ 2,334,611.99 · nos marts R$ 2,204,453.90 · diferença R$ 130,158.09 (5.6%), dos quais R$ 129,088.09 são reservas só-cadastro sem quarto (fora do mart de ocupação por falta de quarto) |
| Reconciliação | rateio: sum(valor_alocado) = valor_total por reserva | OK | 0 reservas com diferença |
| Reconciliação | inventário único por ano x mês x quarto | OK | 0 duplicatas |
| Reconciliação | nenhuma noite fora da janela 2006-12-01..2017-07-31 | OK | 0 |
| Reconciliação | ocupação máxima ≤ 100% | OK | 93.3% |
| Reconciliação | reservas sem valor (nulo ou 0) | AVISO | 110 de 5.072 — noites entram no denominador do ADR sem receita |
| Reconciliação | cobertura de meses por ano (denominador) | OK | 2007: 6.0% (12 meses), 2008: 21.2% (12 meses), 2009: 29.4% (12 meses), 2010: 22.2% (12 meses), 2011: 30.6% (12 meses), 2012: 38.2% (12 meses), 2013: 38.5% (12 meses), 2014: 36.7% (12 meses), 2015: 27.0% (12 meses), 2016: 24.8% (12 meses), 2017: 35.3% (7 meses) |
