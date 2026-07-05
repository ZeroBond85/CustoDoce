# ADR 004: Design do Banco de Dados e Otimização de Query
> Última revisão: 2026-07-05 13:32 UTC

**Status**: Aceito
**Data**: 27/06/2026
**Contexto**: O dashboard precisava de respostas instantâneas mesmo com milhares de linhas de histórico de preços.

## Decisão
Adoção de três pilares de otimização:

1. **Generated Columns**: Criação da coluna `price_per_kg` como `GENERATED ALWAYS` no PostgreSQL. O cálculo é feito no banco, eliminando processamento no Python.
2. **Materialized View (`v_latest_prices`)**: Criação de uma view materializada que armazena apenas o preço mais recente de cada ingrediente por loja.
3. **RPC (Remote Procedure Calls)**: Implementação de toda a lógica de `upsert` no servidor via PL/pgSQL (`upsert_price_rpc`), reduzindo o número de requests entre o Python e o Supabase.

## Rationale
- **Performance**: Consultas que levavam segundos agora respondem em milissegundos.
- **Integridade**: O uso de RPCs garante que a deduplicação de preços ocorra atomicamente no banco.
- **Simplicidade**: O Dashboard consome a View Materializada como se fosse uma tabela simples.

## Consequências
- **Positivas**: Dashboard extremamente fluido, redução de carga no servidor Supabase.
- **Negativas**: Necessidade de atualizar a View (`REFRESH MATERIALIZED VIEW`) após coletas massivas.
