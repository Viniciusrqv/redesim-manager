# Deploy do REDESIM Manager — Online via Streamlit Cloud + Supabase

Guia passo a passo para colocar o app online (acessível de qualquer lugar)
usando GitHub + Supabase + Streamlit Cloud (tudo grátis).

---

## 📋 Resumo da arquitetura

```
   ┌─────────────────────┐
   │  Você + equipe      │
   │  (qualquer device)  │
   └──────────┬──────────┘
              │ HTTPS
              ▼
   ┌─────────────────────┐
   │  Streamlit Cloud    │ ← Roda o app.py 24/7 (grátis)
   │  (puxa do GitHub)   │
   └──────────┬──────────┘
              │
              ├──► Supabase Postgres (banco de dados)
              ├──► Supabase Auth (login email/senha)
              └──► Supabase Storage (PDFs de AVCB, alvarás, etc.)
```

---

## ✅ Já feito (Claude fez pra você)

- ✅ Repositório GitHub criado: `Viniciusrqv/redesim-manager` (Private)
- ✅ Projeto Supabase criado: `redesim-csm` em São Paulo
- ✅ Adaptação do código pra Postgres (`db.py`)
- ✅ Tela de login (`auth.py`)
- ✅ Página `⚙️ Configurações` dentro do app
- ✅ Script de migração SQLite → Postgres
- ✅ `.gitignore` configurado pra não vazar segredos
- ✅ `requirements.txt` com todas as deps de produção

---

## 🔑 Variáveis que você precisa coletar

### 1. **DATABASE_URL** (já pré-montada — só falta a senha)

A connection string base é:
```
postgresql://postgres.ghftrapzckxhikyxahrr:[SENHA]@aws-1-sa-east-1.pooler.supabase.com:6543/postgres
```

Substitua `[SENHA]` pela senha URL-encoded:
- Senha original: `Csm2026-Rdsm-K7p4qW9xT2vY6jLh!`
- URL-encoded (substitui `!` por `%21`): `Csm2026-Rdsm-K7p4qW9xT2vY6jLh%21`

**DATABASE_URL final:**
```
postgresql://postgres.ghftrapzckxhikyxahrr:Csm2026-Rdsm-K7p4qW9xT2vY6jLh%21@aws-1-sa-east-1.pooler.supabase.com:6543/postgres
```

### 2. **SUPABASE_URL**
```
https://ghftrapzckxhikyxahrr.supabase.co
```

### 3. **SUPABASE_ANON_KEY** (você copia manualmente)
1. Abre https://supabase.com/dashboard/project/ghftrapzckxhikyxahrr/settings/api-keys/legacy
2. Na seção **"anon public"**, clica no botão **Copy** ao lado da chave
3. Cola aqui em algum lugar seguro

### 4. **SUPABASE_SERVICE_KEY** (você copia manualmente — só pra migração)
1. Mesma página
2. Seção **"service_role secret"** → clica **Reveal** → clica **Copy**
3. ⚠️ NUNCA coloque esta chave em código público — só nos secrets do Streamlit

### 5. **GESTTA_JWT** (igual hoje — copia do navegador)
Atualize uma vez por dia pelo painel `⚙️ Configurações` dentro do app.

---

## 🚀 Passos no PowerShell (na sua máquina)

### Passo 1 — Atualizar `.env` local com a DATABASE_URL

Abra `redesim_manager\.env` e adicione no final:
```ini
DATABASE_URL=postgresql://postgres.ghftrapzckxhikyxahrr:Csm2026-Rdsm-K7p4qW9xT2vY6jLh%21@aws-1-sa-east-1.pooler.supabase.com:6543/postgres
SUPABASE_URL=https://ghftrapzckxhikyxahrr.supabase.co
SUPABASE_ANON_KEY=<COLE_AQUI_a_anon_key>
SUPABASE_SERVICE_KEY=<COLE_AQUI_a_service_role_key>
```

### Passo 2 — Instalar as novas dependências

```powershell
cd "C:\Users\User\Documents\CLAUDE CSM\CSM CONTABILIDADE\LICENÇA\LICENÇAS"
.\redesim_manager\.venv\Scripts\pip.exe install -r redesim_manager\requirements.txt
```

### Passo 3 — Migrar dados do SQLite local para o Supabase

```powershell
.\redesim_manager\.venv\Scripts\python.exe redesim_manager\migrar_sqlite_para_supabase.py
```

Você verá um relatório de quantas linhas foram migradas por tabela.
Se algo der errado, rode com `--dry-run` antes pra simular.

### Passo 4 — Testar localmente apontando pro Supabase

```powershell
.\redesim_manager\.venv\Scripts\streamlit.exe run redesim_manager\app.py
```

No app, abra `⚙️ Configurações` — o banco deve mostrar
**🟢 PostgreSQL (Supabase) · aws-1-sa-east-1.pooler.supabase.com**.

### Passo 5 — Subir o código pro GitHub

```powershell
cd "C:\Users\User\Documents\CLAUDE CSM\CSM CONTABILIDADE\LICENÇA\LICENÇAS\redesim_manager"
git init
git add .
git commit -m "Primeira versao - deploy pronto"
git branch -M main
git remote add origin https://github.com/Viniciusrqv/redesim-manager.git
git push -u origin main
```

Vai pedir login no GitHub na primeira vez (autorize pelo navegador).

### Passo 6 — Configurar Streamlit Cloud

1. Vai em https://streamlit.io/cloud
2. Login com o **mesmo email do GitHub** (Viniciusrqv)
3. **New app** → escolhe o repo `Viniciusrqv/redesim-manager`
4. Branch: `main`
5. Main file path: `app.py`
6. **Advanced settings** → cola os seguintes secrets no formato TOML:

```toml
DATABASE_URL = "postgresql://postgres.ghftrapzckxhikyxahrr:Csm2026-Rdsm-K7p4qW9xT2vY6jLh%21@aws-1-sa-east-1.pooler.supabase.com:6543/postgres"
SUPABASE_URL = "https://ghftrapzckxhikyxahrr.supabase.co"
SUPABASE_ANON_KEY = "<COLE_AQUI>"
SUPABASE_SERVICE_KEY = "<COLE_AQUI>"
GESTTA_JWT = "<COLE_AQUI_o_JWT_atual>"

DIAS_AMARELO = "3"
DIAS_VERMELHO = "4"
HORARIO_LEMBRETE = "10:00,15:00"
RESPONSAVEL_PADRAO = "Vinicius"

# Opcional — Telegram
TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID = ""
```

7. **Deploy!** — Em 2-3 minutos, o app está no ar em uma URL tipo:
   ```
   https://redesim-manager.streamlit.app
   ```

### Passo 7 — Criar conta de usuário no Supabase Auth

Pra você (e a equipe) conseguir entrar:

1. Vai em https://supabase.com/dashboard/project/ghftrapzckxhikyxahrr/auth/users
2. Clica em **"Add user"** → **"Create new user"**
3. Email + senha forte → **Auto Confirm User** ✓
4. Repetir pra cada membro da equipe que vai acessar

---

## 🔄 Como atualizar depois (dia-a-dia)

Quando Claude/você modificar o código localmente:

```powershell
git add .
git commit -m "Descricao da mudanca"
git push
```

O Streamlit Cloud detecta o push e re-deploya em ~30 segundos
automaticamente. Não precisa fazer mais nada.

---

## 🆘 Troubleshooting

**Erro de conexão com Postgres**
- Verifique se a senha está URL-encoded (`!` vira `%21`)
- Confirme que está usando `:6543` (Transaction Pooler) e não `:5432` (Direct)

**Erro "Module not found: psycopg2"**
- Rode `pip install -r requirements.txt` de novo

**Login falhando**
- Verifique se o email confirmado no Supabase Auth
- Tente "Esqueci a senha" → email do Supabase chega na sua caixa

**JWT do GESTTA expirado**
- Página `⚙️ Configurações` dentro do app
- Cole o novo token e salva

**Banco SQLite local não migrando direito**
- Rode com `--dry-run` primeiro
- Se ficar travado, rode com `--reset` (CUIDADO! Apaga tudo do Postgres)
