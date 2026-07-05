# ADR 001: Escolha da Stack Tecnológica (Infraestrutura Zero-Cost)
> Última revisão: 2026-07-05 14:03 UTC

**Status**: Aceito
**Data**: 27/06/2026
**Contexto**: O projeto necessitava de uma solução de coleta e análise de preços que pudesse operar sem custos mensais (R$ 0,00), escalando para centenas de produtos e dezenas de lojas.

## Decisão
A stack foi definida como:
- **Banco de Dados & API**: Supabase (PostgreSQL).
- **Orquestração de Coleta**: GitHub Actions (Cron).
- **Interface de Usuário**: Streamlit Cloud.
- **Comunicação**: Telegram Bot API & Gmail SMTP.

## Rationale
1. **Supabase**: Oferece PostgreSQL real com PostgREST (API REST automática), o que elimina a necessidade de um servidor backend dedicado (FastAPI/Flask), reduzindo a superfície de ataque e a complexidade de deploy.
2. **GitHub Actions**: Permite rodar scripts de coleta em containers Linux efêmeros, com 2000 minutos gratuitos/mês, suficiente para rodar scrapers 2x ao dia.
3. **Streamlit Cloud**: Deploy instantâneo a partir do GitHub, ideal para dashboards de dados, com hospedagem gratuita para apps privados.
4. **Free Tier Synergy**: Todas as ferramentas escolhidas possuem camadas gratuitas generosas que, combinadas, suportam a carga de trabalho do CustoDoce sem custo.

## Consequências
- **Positivas**: Custo zero, manutenção mínima, deploy simplificado (Git-push).
- **Negativas**: Dependência de limites de cota (ex: 500MB de DB). Exige monitoramento de uso de minutos no GitHub Actions.
