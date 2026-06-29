# Guia de Deployment — CustoDoce

Este guia fornece todas as instruções necessárias para configurar e implantar o ecossistema CustoDoce do zero.

## 📋 Pré-requisitos

Para operar o sistema, você precisará de contas gratuitas nas seguintes plataformas:
- [GitHub](https://github.com)
- [Supabase](https://supabase.com)
- [Streamlit Cloud](https://streamlit.io/cloud)
- [Gmail](https://gmail.com)
- [Telegram](https://telegram.org)

---

## 🛠️ Passo a Passo de Configuração

### 1. Banco de Dados (Supabase)
1. Crie um novo projeto no Supabase chamado `custodoce`.
2. Escolha a região **South America (São Paulo)**.
3. Vá ao **SQL Editor** e execute o arquivo `supabase/consolidated_migration.sql`. Isso criará:
   - Tabelas: `prices`, `price_history`, `review_queue`, `stores`, `scraping_logs`, `ingredients`, `scrape_frequencies`, `feature_flags`, `alert_rules`, `alert_recipients`, `flyers`, `schedules`, `recipes`, `recipe_items`, `llm_match_cache`.
   - Functions RPC: `upsert_price_rpc`, `cleanup_old_prices`, `exec_sql_query`, etc.
   - Triggers: `update_history_from_prices`.
4. Em **Settings $\rightarrow$ API**, anote:
   - `Project URL`
   - `anon public` (chave anônima)
   - `service_role secret` (chave administrativa)

### 2. Bot do Telegram
1. Converse com o **@BotFather** e use o comando `/newbot` para criar o bot.
2. Copie o **API Token** gerado.
3. Envie `/setprivacy` $\rightarrow$ `Disable` para que o bot possa ler mensagens em grupos, se necessário.
4. Configure os comandos via `/setcommands`:
   - `preco <ingrediente> - Buscar preços`
   - `lista - Listar ingredientes`
   - `status - Status do sistema`
   - `ajuda - Ajuda`
5. Para obter seu `CHAT_ID` (necessário para notificações), envie `/start` para o bot **@userinfobot**.

### 3. Notificações por Email (Gmail)
1. Acesse a conta Google $\rightarrow$ **Segurança**.
2. Ative a **Verificação em duas etapas**.
3. Procure por **Senhas de App** (App Passwords).
4. Crie uma senha para "CustoDoce Bot" e anote a senha de 16 caracteres.

### 4. Secrets do GitHub (GitHub Actions)
No seu repositório GitHub, vá em **Settings $\rightarrow$ Secrets and variables $\rightarrow$ Actions** e adicione as seguintes `Repository Secrets`:

| Chave | Origem | Descrição |
|-------|---------|------------|
| `SUPABASE_URL` | Supabase | URL do projeto |
| `SUPABASE_ANON_KEY` | Supabase | Chave `anon public` |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase | Chave `service_role secret` |
| `TELEGRAM_TOKEN` | BotFather | Token do Bot |
| `TELEGRAM_CHAT_ID` | userinfobot | Seu ID de usuário |
| `GMAIL_USER` | Gmail | Seu endereço de email |
| `GMAIL_APP_PASSWORD` | Gmail | Senha de App (16 chars) |
| `ALERT_EMAIL_TO` | Gmail | Email que receberá os relatórios |
| `GROQ_API_KEY` | Groq | Chave para o LLM Classifier |
| `GH_PAT` | GitHub | Token de Acesso Pessoal (escopo `repo`) |

### 5. Deploy do Dashboard (Streamlit Cloud)
1. Conecte sua conta GitHub ao Streamlit Cloud.
2. Clique em **"New App"** $\rightarrow$ Selecione o repositório `CustoDoce`.
3. Configurações:
   - Branch: `main`
   - Main file path: `admin/app.py`
4. Em **Settings $\rightarrow$ Secrets**, cole o seguinte formato TOML:
   ```toml
   SUPABASE_URL = "https://xxxx.supabase.co"
   SUPABASE_ANON_KEY = "eyJxxxx"
   ADMIN_PASSWORD = "escolha_uma_senha_forte"
   ```
 
---
 
## 🧪 Ambiente de Staging (Testes)
Para evitar quebras em produção, o sistema possui um ambiente de Staging. 
Siga as instruções em [docs/deployment-staging.md](deployment-staging.md) para configurar o segundo projeto Supabase e os secrets de teste.
 
---
 
## 🚀 Verificação de Funcionamento

Após concluir o setup, siga esta sequência para validar o sistema:

1. **Coleta**: Vá em **Actions** $\rightarrow$ **CustoDoce - Coleta Diária** $\rightarrow$ **Run workflow**.
2. **Banco**: Verifique no Supabase Table Editor se a tabela `prices` contém dados.
3. **Bot**: Envie `/status` para o seu bot no Telegram.
4. **Dashboard**: Acesse a URL do Streamlit e faça login com a `ADMIN_PASSWORD`.

## ⚠️ Notas Importantes
- **Sincronização de Schema**: Sempre que alterar migrations (arquivos `supabase/`), execute a migração via `scripts/deploy_database.py --execute`. Use `--dry-run` primeiro para validar.
- **Tiers de Lojas**: Se adicionar uma loja nova ao `stores.yaml`, execute `python scripts/sync_all_store_fields.py` para atualizar o banco de dados.
