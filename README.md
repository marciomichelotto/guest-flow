# 🏨 Guest Flow — Data Warehouse para Hospitalidade

> *De 11 quartos na praia do Paraná a um modelo dimensional completo: dados reais de pousada transformados em inteligência de negócio.*

---

## 📌 Sobre o Projeto

O **Guest Flow** é um Data Warehouse construído sobre dados históricos reais de uma pousada familiar operada entre **2006 e 2018** no litoral do Paraná. O projeto cobre o ciclo completo de dados em hospitalidade: da reserva ao checkout, do consumo de produtos ao pagamento — tudo modelado segundo a metodologia **Kimball (Star Schema)**.

O objetivo é duplo:
- Demonstrar como pequenas propriedades podem transformar dados operacionais em decisões estratégicas
- Servir como referência técnica de engenharia e análise de dados aplicada ao setor hoteleiro

---

## 🏗️ Arquitetura

```
Fonte de Dados (CSV históricos 2006–2018)
        │
        ▼
   [Python / SQL]
   Ingestão e limpeza
        │
        ▼
   [dbt Core]
   Transformações e modelagem dimensional
        │
        ▼
   [SQL Server]
   Data Warehouse — Star Schema (Kimball)
        │
        ▼
   [Power BI]
   Dashboards com KPIs de hospitalidade
```

---

## 📐 Modelo Dimensional

### Dimensões (8)

| Tabela | Descrição |
|--------|-----------|
| `dim_hospede` | Perfil dos hóspedes: origem, recorrência, segmento |
| `dim_unidade_habitacional` | Quartos e suítes: tipo, capacidade, categoria |
| `dim_tempo` | Calendário analítico com sazonalidade, feriados e temporadas |
| `dim_funcionario` | Equipe envolvida nos atendimentos |
| `dim_canal_venda` | Canal de aquisição: balcão, OTA, telefone, indicação |
| `dim_forma_pagamento` | PIX, cartão, dinheiro, transferência |
| `dim_produtos` | Produtos do café da manhã e loja |
| `dim_servico_adicional` | Serviços extras: lavanderia, passeios, transfers |

### Fatos (5)

| Tabela | Grão | Métricas principais |
|--------|------|---------------------|
| `fato_reserva` | 1 linha por reserva | diárias, valor total, antecedência da reserva |
| `fato_ocupacao_diaria` | 1 linha por UH por dia | ocupação, RevPAR, ADR |
| `fato_pagamento` | 1 linha por transação | valor pago, forma, parcelamento |
| `fato_consumo_produto` | 1 linha por item consumido | quantidade, receita por produto |
| `fato_servico_consumido` | 1 linha por serviço contratado | receita de serviços extras |

---

## 📊 KPIs de Negócio

Os dashboards cobrem os principais indicadores do setor hoteleiro:

- **RevPAR** — Revenue per Available Room
- **ADR** — Average Daily Rate (Diária Média)
- **Taxa de Ocupação** — por período, UH e temporada
- **Taxa de Retorno de Hóspedes** — fidelização
- **Receita por Canal de Venda** — eficiência de aquisição
- **Ticket Médio por Serviço** — margem em produtos e extras
- **Sazonalidade** — comparativo entre alta e baixa temporada no litoral paranaense

---

## 🛠️ Stack Técnica

| Camada | Tecnologia |
|--------|------------|
| Linguagem principal | Python, SQL |
| Transformações | dbt Core |
| Banco de dados | SQL Server |
| Visualização | Power BI |
| Versionamento | Git + GitHub |

---

## 📁 Estrutura do Repositório

```
guest-flow/
│
├── data/
│   └── raw/                    # CSVs históricos originais (2006–2018)
│
├── dbt/
│   ├── models/
│   │   ├── staging/            # Camada de staging — limpeza e tipagem
│   │   ├── dimensions/         # 8 tabelas dimensão
│   │   └── facts/              # 5 tabelas fato
│   ├── seeds/                  # Dados de referência estáticos
│   ├── tests/                  # Testes de qualidade (not_null, unique, etc.)
│   └── dbt_project.yml
│
├── scripts/
│   └── ingestion/              # Scripts Python de carga inicial
│
├── docs/
│   └── modelo_dimensional.png  # Diagrama do Star Schema
│
└── README.md
```

---

## 🚀 Como Executar

```bash
# 1. Clone o repositório
git clone https://github.com/seu-usuario/guest-flow.git
cd guest-flow

# 2. Instale as dependências Python
pip install -r requirements.txt

# 3. Configure o profiles.yml do dbt apontando para seu SQL Server
# Referência: https://docs.getdbt.com/docs/core/connect-data-platform/mssql-setup

# 4. Execute os modelos dbt
cd dbt
dbt deps
dbt run
dbt test
```

> **Nota:** Os dados utilizados são históricos reais de uma propriedade familiar, anonimizados para preservar a privacidade dos hóspedes.

---

## 💡 Contexto de Negócio

A Pousada Luar de Caiobá operou de 2000 a 2020 em Matinhos, PR — uma das praias mais movimentadas do litoral paranaense. Com 11 unidades habitacionais e operação familiar, o negócio enfrentou os desafios clássicos de pequenas propriedades: sazonalidade intensa, dependência de canais de venda tradicionais e ausência de inteligência sobre o comportamento dos hóspedes.

Este projeto nasce da vivência direta nessa operação e da convicção de que **dados acessíveis podem transformar a gestão de pequenas pousadas e hotéis** — elevando decisões antes tomadas por intuição ao nível da análise estruturada.

---

## 🔮 Próximas Etapas

- [ ] Publicação dos dashboards Power BI (embed público)
- [ ] Aplicação de modelos de Data Science para previsão de ocupação e RevPAR
- [ ] Documentação completa no dbt Docs

---

## 👤 Autor

**Márcio** — Engenheiro de Dados | Analytics Engineer  
Especialização em Análise de Dados — PUC-PR  
20 anos em gestão hoteleira + stack moderna de dados

[![LinkedIn](https://img.shields.io/badge/LinkedIn-conecte--se-blue)](https://linkedin.com/in/seu-perfil)
[![GitHub](https://img.shields.io/badge/GitHub-portfólio-black)](https://github.com/seu-usuario)

---

*Este projeto faz parte de um portfólio de soluções de dados aplicadas ao setor de hospitalidade.*
