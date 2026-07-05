# ADR 005: Gestão de Limites do Free Tier
> Última revisão: 2026-07-05 14:55 UTC

**Status**: Aceito
**Data**: 27/06/2026
**Contexto**: O projeto deve operar rigorosamente dentro dos limites gratuitos das plataformas escolhidas.

## Decisão
Implementação de travas e otimizações para evitar a cobrança ou suspensão de contas:

- **DB (500MB)**: `cleanup_old_prices` remove registros com mais de 90 dias. `cleanup_old_logs` remove logs com mais de 30 dias.
- **Actions (2000 min)**: Uso de ONNX para reduzir cold start do modelo de ML de 2min para 10s. Cache de ETag para evitar downloads redundantes de PDFs.
- **Email (500/dia)**: Relatórios diários consolidados em um único e-mail HTML, em vez de notificações individuais por preço.
- **Supabase API**: Implementação de `rate_limiter.py` local para evitar erro `429 Too Many Requests`.

## Rationale
- Garante a sustentabilidade do projeto a longo prazo sem investimento financeiro.
- Maximiza a eficiência de cada recurso disponível.

## Consequências
- **Positivas**: Risco zero de custos inesperados.
- **Negativas**: Necessidade de políticas agressivas de limpeza de dados (retention policy).
