# Guest Flow — briefing de ingestão

Contexto para o Claude Code. Leia antes de tocar em qualquer coisa.

## 1. O que é o projeto

Modelagem dimensional (Kimball) de 10 anos de operação de uma pousada de praia
em Matinhos/PR, a partir dos registros originais do negócio. Stack alvo:
Snowflake + dbt Core + Python, custo próximo de zero.

**A regra que não se quebra:** hospedagem, ocupação e diárias são dados REAIS e
permanecem reais. Nada de simulação, interpolação ou preenchimento de lacuna
nessas três coisas. Consumo, serviços, equipe e custos serão sintéticos —
gerados por script com seed fixa, condicionados às estadias reais, e marcados
como sintéticos no `schema.yml`.

Se em algum momento a escolha for entre "completar a série" e "manter o número
real", mantém-se o número real e documenta-se o buraco.

## 2. As fontes

| Fonte | O que tem | Confiabilidade |
|---|---|---|
| Abas `Reservas <ano>` | mapa visual de ocupação: quarto x dia | **alta** — é a fonte da verdade |
| Aba `controle hóspedes` | cadastro: nome, contato, pax, valores | média — datas e quartos com erro |

Quando as duas divergem: **mapa ganha** para quarto, check-in e check-out.
**Cadastro ganha** para identidade do hóspede, pax e valores. Toda divergência
vai para `divergencias.csv` — não se resolve silenciosamente.

## 3. Como o mapa é codificado

Cada dia ocupa **duas colunas** do Excel:

```
coluna par   (B=2, D=4, F=6, …)  ->  manhã  = lado do CHECK-OUT
coluna ímpar (C=3, E=5, G=7, …)  ->  tarde  = lado do CHECK-IN
dia = coluna // 2
```

Uma estadia é uma **célula mesclada horizontal** cujo valor é o nº da reserva.

```
col_ini ímpar  ->  check-in  no dia (col_ini - 1) // 2
col_ini par    ->  estadia começou no mês anterior (barra cortada)
col_fim par    ->  check-out no dia col_fim // 2
col_fim ímpar  ->  estadia termina no mês seguinte (barra cortada)

noite d ocupada  <=>  (2d+1) >= col_ini  e  (2d+2) <= col_fim
```

Exemplo real (linha 20 = quarto 1, janeiro/2016):

```
E20:F20 = 4570  ->  entra dia 2, sai dia 3   ->  1 diária
G20:P20 = 4490  ->  entra dia 3, sai dia 8   ->  5 diárias
B20:D20 = 4430  ->  começa em coluna par     ->  entrou em dezembro
```

**O mesmo número em várias linhas = grupo/família ocupando vários quartos.**
Cada quarto vira uma linha própria. Isso importa: achatar grupos em uma linha
só subestima as room-nights em ~15%.

Estrutura da aba: blocos empilhados verticalmente, um por mês, **começando por
dezembro do ano anterior**. Cada bloco redeclara a lista de quartos na coluna A.

## 4. Decisões já tomadas

**Janela válida: 2006-12-01 a 2017-07-31.**
Em 2017 a pousada migrou para o PMS Hospedin e o mapa manual foi abandonado.
A queda é um penhasco, não sazonalidade:

| Reservas iniciadas | jul | ago | set | out | nov |
|---|---|---|---|---|---|
| 2016 | 20 | 15 | 18 | 24 | 27 |
| 2017 | **27** | **1** | **0** | **2** | **1** |

Os registros de ago–nov/2017 são residuais e desenhariam um colapso que nunca
existiu. Ficam fora. A pousada fechou em 2020; 2018–2019 viveram só no PMS e se
perderam.

**As planilhas não são editadas.** O bloco de dezembro fica onde está; o parser
atribui `ano - 1` quando `mes == 12`. Reorganizar onze planilhas na mão é
trabalho manual com risco de corromper justamente o mês mais rentável.

**Temporada é atributo, não reescrita de data.** `dim_data` carrega
`ano_civil`, `temporada` ("2015/16", virando em dezembro) e `fase_temporada`
(alta/média/baixa). Análise de negócio usa temporada; comparação com dado
externo usa ano civil.

**O denominador vem do mapa, nunca de constante no código.** A coluna A de cada
bloco mensal declara os quartos que existiam naquele mês. O parser emite
`inventario_mensal.csv` a partir disso. A quantidade de quartos mudou ao longo
dos 10 anos — fixar em 11 para todos os anos foi o erro da primeira tentativa.

## 5. O parser

`extrai_mapa.py` — roda sobre uma pasta de planilhas:

```bash
python extrai_mapa.py --entrada ./planilhas --saida ./data/raw
```

Saídas:

| Arquivo | Grão | Papel |
|---|---|---|
| `room_nights.csv` | reserva x quarto x noite | fato atômico |
| `estadias.csv` | reserva x quarto | costura barras partidas na virada de mês |
| `inventario_mensal.csv` | ano x mês x quarto | **o denominador** |
| `divergencias.csv` | reserva | conflitos mapa x cadastro |
| `resumo_mensal.csv` | ano x mês | ocupação — sanity check |
| `quartos_orfaos.csv` | — | **tem que sair vazio** |
| `anotacoes_mapa.csv` | — | rótulos livres ("day-use", "Sanepar", eventos) |
| `descartados.csv` | — | o que caiu fora da janela |

Validado em 2016–2017: 1.815 room-nights, 797 estadias, 680 reservas, 0 órfãos.
Ocupação de jan/2016 = 87,1% e jan/2017 = 86,5%; jun/2016 = 2,4%. Sazonalidade
extrema é o achado central do projeto — a média anual (~23%) esconde isso.

## 6. Legenda do Pax

```
A   adulto
AD  adulto double  }  contam 1 adulto cada; a sigla informa o arranjo de cama
AT  adulto twin    }
C   criança 6–12   -> pagante
c   criança 0–6    -> não pagante
Nx  multiplicador (N quartos com a mesma composição)

pax_total   = A + AD + AT + C + c
pax_pagante = A + AD + AT + C
```

O `Nx` precisa ser validado contra a quantidade de quartos que o mapa mostra
para aquela reserva. Não bateu, vai para `divergencias.csv`.

## 7. Modelo alvo

**Duas fatos, não uma** — é o que impede a receita de se deturpar:

- `fato_reserva` — grão reserva. Guarda o valor total **original, intocado**.
- `fato_hospedagem_diaria` — grão reserva x quarto x noite. Guarda
  `valor_alocado` + `metodo_alocacao` ('rateio_igual', 'rateio_por_categoria').

Reservas de grupo trazem um valor único para vários quartos (ex.: 11 quartos,
R$ 11.000 no réveillon). O rateio é coluna derivada e auditável; o número real
continua consultável na `fato_reserva`.

- `fato_disponibilidade_diaria` — grão quarto x dia, derivado de
  `inventario_mensal`. É o denominador de ocupação e RevPAR, materializado como
  tabela inspecionável.

Dimensões: `dim_data` (com temporada), `dim_quarto` (SCD2 — categorias `std`,
`ar`, `hidro` aparecem no cadastro), `dim_hospede`, `dim_canal`.

Métricas: `ocupacao = room_nights / disponíveis`, `ADR = receita / room_nights`,
`RevPAR = receita / disponíveis`.

## 8. Testes que precisam existir

```sql
-- 1. nenhum fato fora da janela válida
select * from {{ ref('fato_hospedagem_diaria') }}
where data_noite not between '2006-12-01' and '2017-07-31'

-- 2. todo quarto vendido existe no inventário daquele mês
select h.* from {{ ref('fato_hospedagem_diaria') }} h
left join {{ ref('dim_inventario_mensal') }} i using (ano, mes, quarto)
where i.quarto is null

-- 3. ocupação nunca passa de 100%
select * from {{ ref('mart_ocupacao_mensal') }} where ocupacao_pct > 100

-- 4. o derivado bate com o declarado à mão
--    (seed quartos_por_ano.csv, preenchido olhando as planilhas)
```

O teste 4 é o que teria pego o erro original. Vale o esforço.

## 9. Consolidação das 24 fontes

`consolida_fontes.py` — união primeiro, precedência só no conflito.

```bash
python consolida_fontes.py --entrada ./fontes --apenas-catalogo   # recon
python consolida_fontes.py --entrada ./fontes --saida ./data/raw  # consolida
```

**A precedência premia contemporaneidade, não recência.** Arquivos com data de
modificação a partir de 2020 são pós-operação — derivados de tentativas
anteriores de limpeza, que são justamente o que distorceu os números. Um mapa
de 2013 salvo em 2013 é registro vivo; o mesmo mapa dentro de um arquivo mexido
em 2026 é cópia de segunda mão.

```
score 0    arquivo salvo no mesmo ano do bloco
score n    salvo n anos depois
score 500  salvo ANTES do bloco (dado importado — suspeito)
score 900  pós-operação (>= 2020)
```

Menor vence; empate por número de barras. Arquivos com `LIMPO`, `GEO`,
`PADRONIZADO` ou `CONSOLIDAD` no nome não entram como fonte de hospedagem.

Conflito = mesma `(reserva, quarto)` com noites diferentes entre arquivos. Fora
disso é união simples — toda estadia presente em qualquer arquivo é recuperada.
`cobertura_por_arquivo.csv` mostra quantas noites cada arquivo trouxe de
exclusivo: é o que prova quais das 24 planilhas importam.

## 10. Divergências entram com flag

Reserva em conflito com o cadastro **entra** na tabela nova, com o valor do
mapa, mais `flag_divergencia` e `tipo_divergencia` ('quarto' | 'data' |
'sem_cadastro'). Não se exclui — são 14% das reservas e a hospedagem aconteceu.

## 11. Rateio de valor em grupo

Proporcional às **diárias**, não ao número de quartos (numa mesma reserva os
quartos podem ter durações diferentes):

```
valor_alocado = valor_total * diarias_do_quarto / total_diarias_da_reserva
```

Aloque em centavos inteiros e jogue a sobra no quarto de maior diária.
Teste obrigatório: `sum(valor_alocado)` por reserva == `fato_reserva.valor_total`.

## 12. Pendências

- [ ] Rodar o parser sobre 2007–2015 e conferir se o layout se manteve. Mudanças
      esperadas: quantidade de quartos, e possivelmente kitnets (`K1`–`K6`) e
      `Sobrado`, que aparecem no cadastro mas não nos mapas de 2016–17.
- [ ] Conferir se a última semana de julho/2017 está preenchida. Se estiver
      ralinha, mover `JANELA_FIM` para 2017-06-30.
- [ ] Revisar as ~98 divergências e as 21 estadias com
      `suspeita_num_reaproveitado` (nº de reserva usado em datas distantes).
- [ ] Períodos de bloqueio (reforma, quarto fechado) não são recuperáveis do
      mapa — se houver memória deles, criar `bloqueios.csv` manual.
- [ ] Só depois disso: carga no Snowflake e camada dbt.
