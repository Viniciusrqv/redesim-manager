# REDESIM Manager

Sistema local para gerenciar e automatizar pedidos de **Licença de Funcionamento via Redesim**,
com classificação de risco por CNAE, cruzamento com Vigilância Sanitária e lembretes no Telegram.

---

## 🗂️ Estrutura do Projeto

```
redesim_manager/
├── app.py                    # Interface Streamlit (rodar com `streamlit run app.py`)
├── config.py                 # Carrega variáveis do .env
├── database.py               # Setup do SQLite + queries
├── scheduler.py              # Loop que envia lembretes diários
├── requirements.txt
├── .env.example              # Copie para .env e preencha
├── utils/
│   ├── cnae_tools.py         # Classificador de risco + extração de PDF
│   └── notifier.py           # Telegram + SMS (Twilio opcional)
└── data/
    ├── matriz_risco_exemplo.csv
    ├── vigilancia_sanitaria_exemplo.csv
    └── redesim.db            # Criado automaticamente na 1ª execução
```

---

## 🚀 Como rodar pela PRIMEIRA vez

### 1. Pré-requisitos
- **Python 3.10 ou superior** instalado.
- Terminal/Prompt de Comando aberto na pasta `redesim_manager`.

### 2. Criar o ambiente virtual (recomendado)

```bash
# Linux/Mac
python3 -m venv .venv
source .venv/bin/activate

# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Instalar dependências

```bash
pip install -r requirements.txt
```

### 4. Configurar variáveis de ambiente

```bash
cp .env.example .env     # Linux/Mac
copy .env.example .env   # Windows
```

Depois abra o `.env` e preencha `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`
(veja o passo a passo abaixo para obtê-los).

### 5. Inicializar o banco (opcional — o app já faz automaticamente)

```bash
python database.py
```

### 6. Subir a aplicação

```bash
streamlit run app.py
```

Abra no navegador: **http://localhost:8501**

### 7. Ativar os lembretes automáticos (em outro terminal)

```bash
python scheduler.py
```

Deixe essa janela aberta. Ela verifica diariamente, no horário configurado,
processos parados há mais de `DIAS_ALERTA` dias e dispara notificações.

---

## 📲 Configurando o Telegram (2 minutos)

### Passo 1 – Criar o bot
1. Abra o Telegram e procure **@BotFather**.
2. Envie `/newbot`.
3. Dê um **nome** (ex: "Contabil CSM Alerts") e um **username** terminando em `bot`
   (ex: `csm_redesim_bot`).
4. O BotFather enviará um **TOKEN** parecido com:
   `123456789:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`

### Passo 2 – Descobrir seu CHAT ID
1. Procure **@userinfobot** no Telegram.
2. Envie `/start`.
3. Ele responderá com `Id: 987654321`. Esse número é o seu CHAT ID.

### Passo 3 – Abrir conversa com o seu bot
1. Procure pelo bot que você criou (pelo username) e envie qualquer mensagem (ex: `oi`).
   Isso é **obrigatório** — o bot só consegue te enviar mensagens depois que você
   iniciou a conversa.

### Passo 4 – Colocar no .env
```env
TELEGRAM_BOT_TOKEN=123456789:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_CHAT_ID=987654321
```

### Passo 5 – Testar
- Reinicie o Streamlit.
- Vá em **📲 Configurar Telegram** → clique em **Enviar mensagem de teste**.
- Você deve receber a mensagem no celular em até 2 segundos.

---

## 📬 Configurando SMS via Twilio (opcional)

Se preferir SMS no lugar do (ou além do) Telegram:

1. Crie conta em https://www.twilio.com/ e pegue `Account SID` + `Auth Token`.
2. Compre (ou ative a trial de) um número de envio.
3. Preencha no `.env`:
   ```env
   TWILIO_ACCOUNT_SID=AC...
   TWILIO_AUTH_TOKEN=...
   TWILIO_FROM_NUMBER=+1...
   TWILIO_TO_NUMBER=+5511999999999
   ```

---

## 🔧 Funcionalidades

### 1. Dashboard / Kanban
- Tabela com todos os processos, **linhas em vermelho** quando estão atrasadas.
- Visão Kanban com colunas por status (Em análise, Pendente de Documento, Deferido, etc.).
- Permite mover o processo de status diretamente pelo painel.

### 2. Classificador de CNAE
- Digite CNAEs ou **faça upload do Cartão CNPJ em PDF** — o sistema extrai
  automaticamente (via `pdfplumber`/`PyMuPDF`).
- Mostra risco individual e o **risco consolidado** (o maior entre todos).

### 3. Cruzamento com Vigilância Sanitária
- Indica **SIM / NÃO** para obrigatoriedade de licenciamento sanitário.
- Permite **upload de CSV/Excel** com a tabela atualizada da Vigilância.

### 4. Matriz de risco CNAE (CGSIM)
- Banco com risco Baixo/Médio/Alto por CNAE.
- Pode ser populado em massa via CSV/Excel ou manualmente.
- Já vem com exemplos em `data/matriz_risco_exemplo.csv`.

### 5. Lembretes no celular
- Scheduler roda diariamente no horário configurado (padrão 09:00).
- Envia **resumo consolidado** + um alerta individual por processo atrasado.
- Canais: Telegram (padrão) e/ou SMS Twilio.

---

## 🧪 Testando os lembretes sem esperar

1. Na aba **⏰ Lembretes / Testes**, use o botão **Disparar alerta agora**.
2. Ou rode `python scheduler.py` — ele executa uma verificação imediata ao iniciar.
3. Para simular atraso: cadastre um processo e edite manualmente a tabela
   `processos` no SQLite, alterando `ultima_movimentacao` para uma data passada:
   ```sql
   UPDATE processos SET ultima_movimentacao = '2026-04-01' WHERE id = 1;
   ```

---

## 🆘 Problemas comuns

- **"Telegram não configurado"** → confira o `.env` e reinicie o Streamlit.
- **Bot não envia mensagem** → você precisa ter enviado uma mensagem PARA o bot
  pelo menos uma vez (o bot não pode iniciar conversas).
- **Erro ao ler PDF** → alguns PDFs são "imagem". Nesse caso, rode OCR externamente
  (p. ex. `ocrmypdf`) antes de fazer o upload.
- **Scheduler não dispara** → confirme o horário do sistema e o formato de
  `HORARIO_LEMBRETE` (HH:MM em 24 horas).

---

## 📌 Próximos passos sugeridos

- Integração direta com a API do REDESIM (quando disponível).
- Multi-usuário com autenticação (Streamlit-Authenticator).
- Exportação mensal em PDF/Excel.
- Backup automático do SQLite para nuvem.
