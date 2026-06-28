# Arquitetura Técnica — CustoDoce

Este documento descreve a arquitetura de software, o fluxo de dados e as decisões de design do sistema CustoDoce.

## 1. Fluxo de Dados Global (Data Flow)

O sistema opera em um ciclo de coleta, processamento, armazenamento e consumo.

```mermaid
graph TD
    subgraph "Camada de Coleta (GitHub Actions)"
        A[Cron 2x/dia] --> B{CollectorPipeline}
        B --> C[Tier 1: PDF Scrapers]
        B --> D[Tier 2: VTEX/Web Scrapers]
        B --> E[Tier 3: Aggregators/Playwright]
        B --> F[Tier 4: Manual Import]
    end

    subgraph "Camada de Processamento (Parsers)"
        C & D & E & F --> G[Normalizer]
        G --> H[Matcher Pipeline]
        H --> I{Confidence Score}
        I -- ">= 80%" --> J[Direct Upsert RPC]
        I -- "55% - 80%" --> K[Semantic/LLM Blend]
        I -- "< 55%" --> L[Review Queue]
    end

    subgraph "Camada de Armazenamento (Supabase)"
        J & K --> M[(PostgreSQL)]
        L --> M
        M --> N[Materialized View: v_latest_prices]
        M --> O[Price History Trigger]
    end

    subgraph "Camada de Consumo"
        N --> P[Streamlit Dashboard]
        N --> Q[Telegram Bot]
        M --> R[Email Report Service]
    end
```

## 2. Pipeline de Matching (A Lógica de Confiança)

O matcher opera em cascata. Se um estágio confirma o ingrediente com alta confiança, o processo para. Caso contrário, ele desce para métodos mais complexos e computacionalmente caros.

```mermaid
graph TD
    Start[Produto Bruto] --> Exact{Match Exato?}
    Exact -- Sim (1.0) --> Success[Upsert Price]
    Exact -- Não --> Alias{Match Alias?}
    
    Alias -- Sim (1.0) --> Success
    Alias -- Não --> WordSubset{Palavras Contidas?}
    
    WordSubset -- Sim (1.0) --> Success
    WordSubset -- Não --> Fuzzy{RapidFuzz >= 80%?}
    
    Fuzzy -- Sim (0.8-1.0) --> Success
    Fuzzy -- Não --> Semantic{Semantic Blend?}
    
    Semantic -- ">= 80%" --> Success
    Semantic -- "65% - 80%" --> LLM{Groq LLM Classifier}
    Semantic -- "< 65%" --> Review[Review Queue]
    
    LLM -- "Confidence >= 85%" --> Success
    LLM -- "Falha/Baixo" --> Review
```

### Detalhes do Semantic Blend
O score semântico é calculado como:
`Score Final = (0.6 * RapidFuzz_Score) + (0.4 * Cosine_Similarity_ONNX)`

## 3. Design do Banco de Dados (Supabase)

O banco foi otimizado para leitura rápida no dashboard e integridade absoluta na escrita.

### Estratégia de Performance
- **Generated Columns**: `price_per_kg` é calculado automaticamente no banco para evitar processamento no Python.
- **Materialized View (`v_latest_prices`)**: Consolida o último preço de cada ingrediente por loja, eliminando a necessidade de queries complexas de `DISTINCT ON` em tempo real.
- **RPC (Remote Procedure Calls)**: Toda a lógica de `upsert` (inserir ou atualizar) reside no servidor via PL/pgSQL para garantir atomicidade e performance.

### Tabela de Preços vs Histórico
- **`prices`**: Mantém apenas o estado atual (última coleta válida).
- **`price_history`**: Alimentada por um `TRIGGER` automático. Sempre que um preço em `prices` é atualizado, o valor antigo é movido para o histórico.

## 4. Estratégia de Tiers (Hierarquia de Coleta)

| Tier | Definição | Método | Frequência | Impacto |
|------|-----------|---------|------------|----------|
| **1** | Atacadistas Base | PDF $\rightarrow$ OCR $\rightarrow$ Texto | Semanal | Volume massivo, alta confiança |
| **2** | E-commerce Especializados | API VTEX $\rightarrow$ JSON | Diária | Preços precisos, alta frequência |
| **3** | Agregadores | Playwright $\rightarrow$ SSR $\rightarrow$ HTML | Fallback | Cobertura de brechas, menor confiança |
| **4** | Lojas Locais | Planilha $\rightarrow$ CSV/XLSX | Mensal | Dados exclusivos de nicho |

---

## 5. Segurança e Isolamento

- **RLS (Row Level Security)**: O Dashboard acessa dados via `anon key` com permissões de leitura.
- **Service Role**: Apenas o Orquestrador (GitHub Actions) e scripts de deploy usam a `service_role` para bypass de RLS e escrita.
- **Rate Limiting**: Implementado via SQLite local nos scrapers para evitar banimentos de IP (429 Too Many Requests).
