"""
database.py
-----------
Setup e queries do banco. Funciona com SQLite (dev local) ou
PostgreSQL/Supabase (produção) via camada `db.py`. A escolha é
feita pela variável de ambiente DATABASE_URL.
"""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, date
from pathlib import Path
from typing import Iterable, Optional

from config import DATABASE_PATH
from db import get_connection, is_postgres


# =====================================================
# CONEXÃO
# =====================================================
@contextmanager
def get_conn():
    """Yields a connection. In dev = SQLite, in prod = Postgres.
    Auto-commits ao sair sem erro, rollback em caso de exceção.
    """
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()


# =====================================================
# CRIAÇÃO DAS TABELAS
# =====================================================
DDL = [
    # Empresas atendidas
    """
    CREATE TABLE IF NOT EXISTS empresas (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        razao_social    TEXT NOT NULL,
        cnpj            TEXT UNIQUE,
        endereco        TEXT,
        municipio       TEXT,
        uf              TEXT,
        responsavel     TEXT,
        criado_em       TEXT DEFAULT (datetime('now', 'localtime'))
    );
    """,
    # Processos REDESIM
    """
    CREATE TABLE IF NOT EXISTS processos (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        empresa_id      INTEGER NOT NULL,
        protocolo       TEXT,
        tipo            TEXT,                        -- Abertura, Alteração, Baixa, Renovação
        status          TEXT NOT NULL DEFAULT 'Em análise',
        risco           TEXT,                        -- Baixo / Médio / Alto
        exige_sanitaria INTEGER DEFAULT 0,           -- 0 = NÃO, 1 = SIM
        observacoes     TEXT,
        ultima_movimentacao TEXT DEFAULT (date('now', 'localtime')),
        criado_em       TEXT DEFAULT (datetime('now', 'localtime')),
        FOREIGN KEY(empresa_id) REFERENCES empresas(id) ON DELETE CASCADE
    );
    """,
    # CNAEs por processo
    """
    CREATE TABLE IF NOT EXISTS processo_cnaes (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        processo_id     INTEGER NOT NULL,
        cnae            TEXT NOT NULL,
        descricao       TEXT,
        principal       INTEGER DEFAULT 0,
        FOREIGN KEY(processo_id) REFERENCES processos(id) ON DELETE CASCADE
    );
    """,
    # Matriz oficial de risco do CNAE (NR-04, CGSIM 51/2019 e municipais)
    """
    CREATE TABLE IF NOT EXISTS cnae_risco (
        cnae            TEXT PRIMARY KEY,            -- subclasse (9999-9/99) ou classe (99.99-9)
        descricao       TEXT,
        risco           TEXT NOT NULL,               -- Baixo / Médio / Alto
        grau_risco      INTEGER,                     -- 1..4 (NR-04)
        fonte           TEXT,                        -- NR-04 / CGSIM-51 / Municipal
        observacoes     TEXT,
        atualizado_em   TEXT DEFAULT (datetime('now', 'localtime'))
    );
    """,
    # Tabela de regras da Vigilância Sanitária
    """
    CREATE TABLE IF NOT EXISTS vigilancia_sanitaria (
        cnae             TEXT PRIMARY KEY,
        descricao        TEXT,
        exige_licenca    INTEGER NOT NULL DEFAULT 0,  -- 0/1
        risco_sanitario  TEXT,                         -- Alto/Médio/Baixo
        nivel            TEXT,                         -- Estadual/Municipal/Federal
        fonte            TEXT,
        atualizado_em    TEXT DEFAULT (datetime('now', 'localtime'))
    );
    """,
    # Histórico de movimentações
    """
    CREATE TABLE IF NOT EXISTS movimentacoes (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        processo_id     INTEGER NOT NULL,
        de_status       TEXT,
        para_status     TEXT,
        usuario         TEXT,
        comentario      TEXT,
        criado_em       TEXT DEFAULT (datetime('now', 'localtime')),
        FOREIGN KEY(processo_id) REFERENCES processos(id) ON DELETE CASCADE
    );
    """,
    # Log de notificações enviadas
    """
    CREATE TABLE IF NOT EXISTS notificacoes (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        processo_id     INTEGER,
        canal           TEXT,                        -- telegram/sms/email
        mensagem        TEXT,
        sucesso         INTEGER DEFAULT 0,
        erro            TEXT,
        criado_em       TEXT DEFAULT (datetime('now', 'localtime'))
    );
    """,
    # Alvará / Auto de Vistoria do Corpo de Bombeiros (AVCB/CLCB)
    """
    CREATE TABLE IF NOT EXISTS alvaras_bombeiros (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        empresa_id       INTEGER NOT NULL,
        tipo             TEXT,                       -- AVCB / CLCB / Projeto
        numero           TEXT,
        data_emissao     TEXT,
        data_vencimento  TEXT NOT NULL,
        arquivo_pdf      TEXT,                       -- caminho do PDF salvo
        ocupacao         TEXT,                       -- ex: F-3, A-2
        area_construida  REAL,
        observacoes      TEXT,
        alertado_30d     INTEGER DEFAULT 0,
        alertado_60d     INTEGER DEFAULT 0,
        alertado_vencido INTEGER DEFAULT 0,
        criado_em        TEXT DEFAULT (datetime('now', 'localtime')),
        FOREIGN KEY(empresa_id) REFERENCES empresas(id) ON DELETE CASCADE
    );
    """,
    # Classificação técnica CNAE → Corpo de Bombeiros (IT-01 CBPMESP)
    # Determina se o CNAE exige AVCB/CLCB e qual o grau de risco de incêndio.
    """
    CREATE TABLE IF NOT EXISTS bombeiros_cnae (
        cnae             TEXT PRIMARY KEY,              -- subclasse 9999-9/99
        descricao        TEXT,
        exige_avcb       INTEGER NOT NULL DEFAULT 1,    -- 0/1
        grau_risco       TEXT,                          -- Baixo/Médio/Alto
        ocupacao_it01    TEXT,                          -- ex: F-3, A-2, C-1
        area_limite_m2   REAL,                          -- abaixo disso pode CLCB
        observacao       TEXT,
        fonte            TEXT DEFAULT 'IT-01/CBPMESP',
        atualizado_em    TEXT DEFAULT (datetime('now', 'localtime'))
    );
    """,
    # Registro das atualizações das matrizes/normas oficiais
    # (NR-04, CVS-SP, IT-01 CBPMESP, CGSIM, CONCLA).
    # Cada linha = um import/atualização de uma base.
    """
    CREATE TABLE IF NOT EXISTS normas_atualizacao (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        base            TEXT NOT NULL,         -- 'nr04', 'cvs_sp', 'it01_cbpmesp', 'cgsim', 'concla'
        orgao           TEXT,                  -- 'Ministério do Trabalho', 'CVS-SP', etc.
        versao          TEXT,                  -- ex: 'Portaria 25/2017', 'Portaria CVS-SP 1/2024'
        arquivo_origem  TEXT,                  -- nome do arquivo subido
        hash_arquivo    TEXT,                  -- sha256 pra detectar mudanças
        registros       INTEGER,               -- qtde de linhas importadas
        observacoes     TEXT,
        atualizado_por  TEXT,                  -- quem fez o import
        criado_em       TEXT DEFAULT (datetime('now', 'localtime'))
    );
    """,
    # Tabela mestra de CNAEs (CONCLA / IBGE) — versão 2.3.
    # Contém todos os níveis hierárquicos: seção, divisão, grupo, classe,
    # subclasse. Usada pra validar/descrever qualquer CNAE do sistema.
    """
    CREATE TABLE IF NOT EXISTS cnae_concla (
        codigo         TEXT PRIMARY KEY,           -- ex '0111-3/01' ou 'A' ou '01' ou '01.1' ou '01.11-3'
        nivel          TEXT NOT NULL,              -- secao | divisao | grupo | classe | subclasse
        denominacao    TEXT NOT NULL,
        secao          TEXT,                       -- letra A-U (quando aplicável)
        divisao        TEXT,                       -- '01' a '99' (quando aplicável)
        grupo          TEXT,                       -- 'XX.X'
        classe         TEXT,                       -- 'XX.XX-X'
        atualizado_em  TEXT DEFAULT (datetime('now', 'localtime'))
    );
    """,
    # Lista de CNAEs classificados como baixo risco pela CGSIM (Resolução
    # 59/2020 ou similar). Cada entrada indica se a atividade dispensa
    # licenciamento prévio (baixo risco A) ou tem restrições (baixo risco B).
    """
    CREATE TABLE IF NOT EXISTS cgsim_cnae (
        codigo         TEXT PRIMARY KEY,           -- ex '0111-3/01'
        denominacao    TEXT,
        nivel_risco    TEXT,                       -- 'Baixo Risco A' | 'Baixo Risco B' | 'Alto Risco'
        orgao          TEXT,                       -- órgão licenciador responsável
        observacoes    TEXT,
        fonte          TEXT DEFAULT 'CGSIM 59/2020',
        atualizado_em  TEXT DEFAULT (datetime('now', 'localtime'))
    );
    """,
    # Documentos diversos com validade (CND, FGTS, CNDT, Alvará Municipal,
    # Licença Funcionamento, Contratos, etc.). Complementa a tabela de
    # alvaras_bombeiros, que é específica do CB. Dispara alerta quando
    # faltarem <= dias_alerta dias para o vencimento (default 45).
    """
    CREATE TABLE IF NOT EXISTS documentos_vencimento (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        empresa_id        INTEGER NOT NULL,
        tipo              TEXT NOT NULL,            -- CND, FGTS, CNDT, Alvará Municipal…
        numero            TEXT,
        descricao         TEXT,
        data_emissao      TEXT,
        data_vencimento   TEXT NOT NULL,
        dias_alerta       INTEGER DEFAULT 45,
        arquivo_pdf       TEXT,
        status            TEXT DEFAULT 'Vigente',   -- Vigente / Vencido / Renovado / Cancelado
        observacoes       TEXT,
        renovado_para_id  INTEGER,                  -- id do doc que renovou esse
        criado_em         TEXT DEFAULT (datetime('now', 'localtime')),
        atualizado_em     TEXT DEFAULT (datetime('now', 'localtime')),
        FOREIGN KEY(empresa_id) REFERENCES empresas(id) ON DELETE CASCADE,
        FOREIGN KEY(renovado_para_id) REFERENCES documentos_vencimento(id)
    );
    """,
    # Protocolos REDESIM (Viabilidade / Licenciamento) por empresa.
    # Uma empresa pode ter N protocolos ao longo do tempo — cada tentativa
    # cancelada/indeferida gera linha nova; a empresa NÃO é duplicada.
    # Após a viabilidade ser aprovada, inicia-se o licenciamento (outro
    # protocolo vinculado à mesma empresa).
    """
    CREATE TABLE IF NOT EXISTS protocolos_redesim (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        empresa_id          INTEGER NOT NULL,
        tipo                TEXT NOT NULL,           -- 'Viabilidade' | 'Licenciamento'
        numero_protocolo    TEXT NOT NULL,           -- ex: SPM2630216399
        numero_solicitacao  TEXT,                    -- nº interno (ex: 5218890)
        data_solicitacao    TEXT,                    -- YYYY-MM-DD
        evento              TEXT,                    -- ex: '999 - Regularização de Empresa'
        orgao_registro      TEXT,                    -- Junta Comercial / Prefeitura / ...
        status              TEXT NOT NULL,           -- Aprovada / Cancelada / Pendente / Indeferida / Concluída / Inativa / Em análise
        observacoes         TEXT,
        substituido_por_id  INTEGER,                 -- id do protocolo que substituiu este (mantém histórico)
        criado_em           TEXT DEFAULT (datetime('now', 'localtime')),
        atualizado_em       TEXT DEFAULT (datetime('now', 'localtime')),
        FOREIGN KEY(empresa_id) REFERENCES empresas(id) ON DELETE CASCADE,
        FOREIGN KEY(substituido_por_id) REFERENCES protocolos_redesim(id) ON DELETE SET NULL
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_protocolos_empresa
    ON protocolos_redesim(empresa_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_protocolos_numero
    ON protocolos_redesim(numero_protocolo);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_protocolos_status
    ON protocolos_redesim(status);
    """,
    """
    CREATE TABLE IF NOT EXISTS tarefas_gestta (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        gestta_id           TEXT,                    -- _id no GESTTA (chave da API)
        gestta_customer_id  TEXT,
        gestta_owner_id     TEXT,
        tarefa_nome         TEXT NOT NULL,
        cliente_nome        TEXT NOT NULL,
        cliente_norm        TEXT NOT NULL,
        responsavel         TEXT,
        atrasada            TEXT,
        status_gestta       TEXT,
        departamento        TEXT,
        subtype             TEXT,
        due_date            TEXT,                    -- ISO date
        competence_date     TEXT,
        created_at          TEXT,
        legal_date          TEXT,
        total_step          INTEGER,
        done_step           INTEGER,
        overdue             INTEGER,                 -- 0/1
        fine                INTEGER,
        done_overdue        INTEGER,
        done_fine           INTEGER,
        risco               TEXT,
        motivo_risco        TEXT,
        tipo                TEXT,                    -- categoria pra filtros: LICENCA_FUNCIONAMENTO / ALVARA_SANITARIO / BOMBEIROS / DEVOLUCAO / ABERTURA / ALTERACAO / BAIXA / CONSELHO / OUTROS
        empresa_id          INTEGER,
        protocolo_id        INTEGER,
        resolvida           INTEGER DEFAULT 0,
        data_import         TEXT DEFAULT (datetime('now', 'localtime')),
        origem_arquivo      TEXT,
        criado_em           TEXT DEFAULT (datetime('now', 'localtime')),
        atualizado_em       TEXT DEFAULT (datetime('now', 'localtime')),
        FOREIGN KEY(empresa_id) REFERENCES empresas(id) ON DELETE SET NULL,
        FOREIGN KEY(protocolo_id) REFERENCES protocolos_redesim(id) ON DELETE SET NULL
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_gestta_cliente_norm
    ON tarefas_gestta(cliente_norm);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_gestta_resolvida
    ON tarefas_gestta(resolvida);
    """,
    """
    ALTER TABLE tarefas_gestta ADD COLUMN IF NOT EXISTS tipo TEXT;
    """,
    """
    ALTER TABLE tarefas_gestta ADD COLUMN IF NOT EXISTS pulado INTEGER DEFAULT 0;
    """,
    """
    ALTER TABLE tarefas_gestta ADD COLUMN IF NOT EXISTS motivo_pulado TEXT;
    """,
    """
    ALTER TABLE tarefas_gestta ADD COLUMN IF NOT EXISTS pulado_em TEXT;
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_gestta_tipo
    ON tarefas_gestta(tipo);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_gestta_risco
    ON tarefas_gestta(risco);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_gestta_responsavel
    ON tarefas_gestta(responsavel);
    """,
    # Histórico LOCAL de anotações em tarefas GESTTA — não substitui as
    # do GESTTA, é uma camada nossa que persiste mesmo se a sincronização
    # apagar/recriar a tarefa. Tipo: 'NOTA', 'STATUS_CHANGE', 'CONCLUSAO'.
    """
    CREATE TABLE IF NOT EXISTS gestta_anotacao_local (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        gestta_id     TEXT NOT NULL,         -- _id da tarefa no GESTTA
        tipo          TEXT NOT NULL DEFAULT 'NOTA',
        texto         TEXT NOT NULL,
        replicado     INTEGER NOT NULL DEFAULT 0,  -- 0/1 — foi enviado pro GESTTA?
        replicado_em  TEXT,
        erro_replicar TEXT,
        criado_em     TEXT DEFAULT (datetime('now', 'localtime')),
        usuario       TEXT
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_anotacao_gestta_id
    ON gestta_anotacao_local(gestta_id);
    """,
    """
    CREATE TABLE IF NOT EXISTS pendencias (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        empresa_id          INTEGER,                           -- nullable: serviço avulso fica NULL
        cliente_avulso      TEXT,                              -- nome do cliente quando empresa_id IS NULL
        assunto             TEXT NOT NULL,
        descricao           TEXT,
        prioridade          TEXT NOT NULL DEFAULT 'Média',     -- Alta / Média / Baixa
        status              TEXT NOT NULL DEFAULT 'Aberta',    -- Aberta / Em andamento / Aguardando terceiro / Resolvida / Cancelada
        data_inicio         TEXT NOT NULL DEFAULT (date('now', 'localtime')),
        data_limite         TEXT,                              -- prazo final (opcional)
        dias_alerta         INTEGER NOT NULL DEFAULT 7,        -- alerta a cada X dias parados
        ultima_atualizacao  TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
        resolvida           INTEGER NOT NULL DEFAULT 0,        -- 0/1 (cache para queries)
        criado_em           TEXT DEFAULT (datetime('now', 'localtime')),
        atualizado_em       TEXT DEFAULT (datetime('now', 'localtime')),
        FOREIGN KEY(empresa_id) REFERENCES empresas(id) ON DELETE CASCADE
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_pendencias_empresa
    ON pendencias(empresa_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_pendencias_status
    ON pendencias(status);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_pendencias_resolvida
    ON pendencias(resolvida);
    """,
    """
    CREATE TABLE IF NOT EXISTS pendencia_movimentos (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        pendencia_id  INTEGER NOT NULL,
        tipo          TEXT NOT NULL DEFAULT 'nota',  -- nota / status / contato / retorno
        texto         TEXT NOT NULL,
        criado_em     TEXT DEFAULT (datetime('now', 'localtime')),
        FOREIGN KEY(pendencia_id) REFERENCES pendencias(id) ON DELETE CASCADE
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_pend_mov_pendencia
    ON pendencia_movimentos(pendencia_id);
    """,
    # =========================================================
    # CONSULTOR DE CNAE — bases auxiliares (Conselhos, Ambiental, ANVISA)
    # =========================================================
    """
    CREATE TABLE IF NOT EXISTS cnae_conselho (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        cnae            TEXT NOT NULL,
        conselho_sigla  TEXT NOT NULL,
        conselho_nome   TEXT,
        obrigatoriedade TEXT NOT NULL DEFAULT 'OBRIGATORIO',
        tipo_registro   TEXT,                  -- INSCRICAO_PJ / RT_OBRIGATORIO / AMBOS
        observacao      TEXT,
        fonte           TEXT,
        criado_em       TEXT DEFAULT (datetime('now', 'localtime')),
        atualizado_em   TEXT DEFAULT (datetime('now', 'localtime'))
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_cnae_conselho_cnae
    ON cnae_conselho(cnae);
    """,
    """
    CREATE TABLE IF NOT EXISTS cnae_ambiental (
        cnae            TEXT PRIMARY KEY,
        exige_licenca   INTEGER NOT NULL DEFAULT 0,  -- 0/1
        orgao           TEXT,                  -- 'CETESB', 'IBAMA', 'SECRETARIA_MUNICIPAL'
        porte_padrao    TEXT,                  -- P / M / G (ou texto livre)
        tipo_licenca    TEXT,                  -- LP / LI / LO / LP+LI+LO etc
        observacao      TEXT,
        fonte           TEXT,                  -- 'Decreto Estadual 47.397/02' / 'Resolução CONAMA 237'
        atualizado_em   TEXT DEFAULT (datetime('now', 'localtime'))
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS cnae_anvisa (
        cnae            TEXT PRIMARY KEY,
        exige_anvisa    INTEGER NOT NULL DEFAULT 0,
        categoria       TEXT,                  -- 'Alimentos', 'Cosméticos', 'Saneantes', 'Medicamentos', 'Produtos para Saúde'
        observacao      TEXT,
        fonte           TEXT,
        atualizado_em   TEXT DEFAULT (datetime('now', 'localtime'))
    );
    """,
    # Outros registros federais/setoriais (CTF/IBAMA, MAPA, INMETRO,
    # ANATEL, ANP, etc.) — tabela genérica pra expandir sem schema novo.
    """
    CREATE TABLE IF NOT EXISTS cnae_outros_registros (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        cnae            TEXT NOT NULL,
        orgao           TEXT NOT NULL,         -- CTF_IBAMA / MAPA / INMETRO / ANATEL / ANP / etc
        orgao_nome      TEXT,                  -- nome completo (ex: 'IBAMA - Cadastro Técnico Federal')
        categoria       TEXT,                  -- subdivisão dentro do órgão
        obrigatoriedade TEXT NOT NULL DEFAULT 'OBRIGATORIO', -- OBRIGATORIO / OPCIONAL / DEPENDE
        observacao      TEXT,
        fonte           TEXT,
        criado_em       TEXT DEFAULT (datetime('now', 'localtime')),
        atualizado_em   TEXT DEFAULT (datetime('now', 'localtime'))
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_outros_reg_cnae
    ON cnae_outros_registros(cnae);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_outros_reg_orgao
    ON cnae_outros_registros(orgao);
    """,
    # Habilitação profissional CONDICIONAL — casos onde o CNAE em si NÃO
    # obriga a PJ a se registrar em conselho, mas atividades exercidas
    # dentro dele exigem profissional habilitado (ex.: aplicação de botox
    # em CNAE de estética; venda de medicamentos em comércio varejista;
    # corretagem de seguros em atividades de intermediação).
    # Quem fiscaliza não é o registro da empresa — é a exigência do
    # exercício profissional pelos conselhos / leis específicas.
    """
    CREATE TABLE IF NOT EXISTS cnae_habilitacao_profissional (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        cnae              TEXT NOT NULL,
        atividade_gatilho TEXT NOT NULL,   -- 'aplicação de toxina botulínica'
        conselho_sigla    TEXT,             -- CRM / COREN / CRBM / CRF / etc
        quem_executa      TEXT NOT NULL,    -- 'médico ou enfermeiro habilitado'
        nivel_risco       TEXT NOT NULL DEFAULT 'ALTO',  -- ALTO / MEDIO / BAIXO
        fonte             TEXT,             -- 'Resolução CFM 2.219/2018'
        observacao        TEXT,
        criado_em         TEXT DEFAULT (datetime('now', 'localtime')),
        atualizado_em     TEXT DEFAULT (datetime('now', 'localtime')),
        UNIQUE(cnae, atividade_gatilho)
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_hab_prof_cnae
    ON cnae_habilitacao_profissional(cnae);
    """,
    # Solicitações de cadastro para acesso ao app (aprovação manual
    # pelo admin antes de criar usuário no Supabase Auth).
    """
    CREATE TABLE IF NOT EXISTS solicitacoes_cadastro (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        nome          TEXT NOT NULL,
        email         TEXT NOT NULL UNIQUE,
        funcao        TEXT,
        justificativa TEXT,
        status        TEXT NOT NULL DEFAULT 'pendente',
        criado_em     TEXT DEFAULT (datetime('now', 'localtime')),
        revisado_em   TEXT,
        revisado_por  TEXT,
        observacao_admin TEXT
    );
    """,
    # Telegram por usuário: cada usuário registrado pode informar o
    # próprio chat_id pra receber os alertas no Telegram dele em vez
    # de chegarem todos no admin.
    """
    CREATE TABLE IF NOT EXISTS usuarios_telegram (
        email      TEXT PRIMARY KEY,
        chat_id    TEXT NOT NULL,
        nome       TEXT,
        ativo      INTEGER NOT NULL DEFAULT 1,
        criado_em  TEXT DEFAULT (datetime('now', 'localtime')),
        atualizado_em TEXT DEFAULT (datetime('now', 'localtime'))
    );
    """,
    # Cobranças pendentes de lançamento no DOMÍNIO. Eduardo cobra
    # via Thomson Reuters DOMÍNIO mas esquece — o sistema cria a
    # cobrança automaticamente quando ele marca um protocolo como
    # Concluída/Aprovada, com valor sugerido baseado no tipo, e
    # avisa por Telegram + dashboard até ele marcar como "lançada".
    """
    CREATE TABLE IF NOT EXISTS cobrancas_dominio (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        empresa_id      INTEGER,
        protocolo_id    INTEGER,
        gestta_task_id  TEXT,
        tipo_servico    TEXT NOT NULL,   -- LICENCA_REDESIM / VISA / AVCB / OUTRO
        cliente_nome    TEXT NOT NULL,
        cliente_cnpj    TEXT,
        valor_sugerido  REAL NOT NULL DEFAULT 0,
        valor_lancado   REAL,
        descricao       TEXT,
        responsavel     TEXT,
        status          TEXT NOT NULL DEFAULT 'pendente',   -- pendente / lancada / cancelada
        criado_em       TEXT DEFAULT (datetime('now', 'localtime')),
        lancado_em      TEXT,
        lancado_por     TEXT,
        observacao      TEXT,
        comissao        REAL,
        FOREIGN KEY(empresa_id) REFERENCES empresas(id) ON DELETE SET NULL,
        FOREIGN KEY(protocolo_id) REFERENCES protocolos_redesim(id) ON DELETE SET NULL
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_cobrancas_status
    ON cobrancas_dominio(status);
    """,
    # Tabela de valores sugeridos por tipo de serviço (configurável).
    # Eduardo informou: Licença Funcionamento via REDESIM = R$ 250
    # e Vigilância Sanitária = R$ 600.
    """
    CREATE TABLE IF NOT EXISTS tabela_valores_cobranca (
        tipo_servico    TEXT PRIMARY KEY,
        descricao       TEXT,
        valor_sugerido  REAL NOT NULL,
        atualizado_em   TEXT DEFAULT (datetime('now', 'localtime')),
        atualizado_por  TEXT
    );
    """,
    # GESTTA JWT por usuário: cada usuário do REDESIM Manager pode
    # vincular o JWT do PRÓPRIO usuário GESTTA. Isso permite que
    # buscas/comentários no GESTTA respeitem as permissões da pessoa
    # logada, e que cada um veja "as próprias tarefas".
    # Cai pro GESTTA_JWT global (env) como fallback.
    """
    CREATE TABLE IF NOT EXISTS usuarios_gestta_jwt (
        email         TEXT PRIMARY KEY,
        jwt           TEXT NOT NULL,
        nome          TEXT,
        gestta_user   TEXT,
        gestta_company TEXT,
        ativo         INTEGER NOT NULL DEFAULT 1,
        criado_em     TEXT DEFAULT (datetime('now', 'localtime')),
        atualizado_em TEXT DEFAULT (datetime('now', 'localtime'))
    );
    """,
    # Cache de consulta CNPJ (BrasilAPI / ReceitaWS). Evita bater de
    # novo na API toda vez que abrir o relatório da mesma empresa.
    # TTL padrão de 30 dias — a Receita raramente muda CNAE/situação
    # mais rápido que isso.
    """
    CREATE TABLE IF NOT EXISTS consultas_cnpj_cache (
        cnpj          TEXT PRIMARY KEY,
        dados_json    TEXT NOT NULL,
        consultado_em TEXT DEFAULT (datetime('now', 'localtime')),
        fonte         TEXT
    );
    """,
    # Catálogo central de órgãos oficiais (federal/estadual/municipal)
    # com link de consulta e link de cadastro. Usado pra montar o
    # passo-a-passo "onde verificar / como se inscrever".
    """
    CREATE TABLE IF NOT EXISTS orgaos_oficiais (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        sigla         TEXT NOT NULL,
        nome          TEXT NOT NULL,
        categoria     TEXT,
        esfera        TEXT,
        uf            TEXT,
        municipio     TEXT,
        descricao     TEXT,
        link_consulta TEXT,
        link_cadastro TEXT,
        contato       TEXT,
        observacoes   TEXT,
        atualizado_em TEXT DEFAULT (datetime('now', 'localtime')),
        UNIQUE(sigla, uf)
    );
    """,
    # Base de regras OFICIAIS por CNAE × órgão.
    # Esta é a tabela que dá a CERTEZA — em vez de "provavelmente
    # precisa de CRECI", responde:
    #   - obrigatoriedade: 'sim' | 'nao' | 'condicional'
    #   - condicoes_obrigatorio: descreve QUANDO é obrigatório
    #   - condicoes_dispensa:    descreve QUANDO é dispensado
    #   - base_legal: lei/resolução com nº e data
    #   - link_lei: URL pro PDF/texto da norma
    # Toda regra é auditável (autor + data + revisão).
    """
    CREATE TABLE IF NOT EXISTS cnae_regra_oficial (
        id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        cnae                    TEXT NOT NULL,
        orgao_sigla             TEXT NOT NULL,
        orgao_uf                TEXT,
        obrigatoriedade         TEXT NOT NULL,
        condicoes_obrigatorio   TEXT,
        condicoes_dispensa      TEXT,
        observacoes             TEXT,
        base_legal              TEXT,
        link_lei                TEXT,
        autor                   TEXT,
        data_cadastro           TEXT DEFAULT (datetime('now', 'localtime')),
        data_revisao            TEXT,
        revisor                 TEXT,
        UNIQUE(cnae, orgao_sigla, orgao_uf)
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_regra_cnae
    ON cnae_regra_oficial(cnae);
    """,
    # Histórico de verificações manuais empresa × órgão.
    # Quando você (ou alguém da equipe) abre o portal oficial e
    # confirma que o cadastro/licença da empresa naquele órgão está
    # OK (ou não se aplica), salva aqui pra próxima consulta já
    # aparecer "✅ verificado em DD/MM por X".
    """
    CREATE TABLE IF NOT EXISTS empresa_orgao_verificacao (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        cnpj            TEXT NOT NULL,
        orgao_sigla     TEXT NOT NULL,
        orgao_uf        TEXT,
        status          TEXT NOT NULL,
        observacao      TEXT,
        verificado_por  TEXT,
        verificado_em   TEXT DEFAULT (datetime('now', 'localtime')),
        UNIQUE(cnpj, orgao_sigla, orgao_uf)
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_empresa_orgao_verif_cnpj
    ON empresa_orgao_verificacao(cnpj);
    """,
    """
    CREATE TABLE IF NOT EXISTS cnae_verificacao (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        cnae                TEXT NOT NULL,
        data_verificacao    TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
        resultado           TEXT NOT NULL,             -- APROVADO / DIVERGENCIA / NOVAS_INFOS
        divergencias_count  INTEGER NOT NULL DEFAULT 0,
        relatorio           TEXT,                       -- texto do relatório do sub-agente
        fonte               TEXT,                       -- 'Sub-agente Cowork', 'Manual', etc
        verificado_por      TEXT                        -- nome do usuário que validou
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_cnae_verif_cnae
    ON cnae_verificacao(cnae);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_cnae_verif_data
    ON cnae_verificacao(data_verificacao);
    """,
    # Histórico de consultas que o Eduardo faz na página (alimenta o
    # alerta semanal: prioriza verificação de CNAEs MAIS consultados).
    """
    CREATE TABLE IF NOT EXISTS cnae_consulta_log (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        cnae              TEXT NOT NULL,
        consultado_em     TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
        contexto          TEXT
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_cnae_consulta_cnae
    ON cnae_consulta_log(cnae);
    """,
]


def _migrar_postgres() -> None:
    """Migrações de coluna para Postgres (idempotente: ADD COLUMN IF NOT EXISTS).

    No Postgres o _migrar() (SQLite/PRAGMA) não roda; as colunas adicionadas
    depois da criação das tabelas precisam ser garantidas aqui.
    """
    _cols = [
        ("vigilancia_sanitaria", "risco_sanitario TEXT"),
        ("cnae_risco", "grau_risco INTEGER"),
        ("cnae_risco", "fonte TEXT"),
        ("processos", "canal_redesim TEXT DEFAULT 'Online'"),
        ("processos", "motivo_presencial TEXT"),
        ("protocolos_redesim", "substituido_por_id INTEGER"),
        ("cnae_conselho", "tipo_registro TEXT"),
        ("pendencias", "cliente_avulso TEXT"),
        ("cobrancas_dominio", "comissao REAL"),
        ("tarefas_gestta", "gestta_id TEXT"),
        ("tarefas_gestta", "gestta_customer_id TEXT"),
        ("tarefas_gestta", "gestta_owner_id TEXT"),
        ("tarefas_gestta", "subtype TEXT"),
        ("tarefas_gestta", "due_date TEXT"),
        ("tarefas_gestta", "competence_date TEXT"),
        ("tarefas_gestta", "created_at TEXT"),
        ("tarefas_gestta", "legal_date TEXT"),
        ("tarefas_gestta", "total_step INTEGER"),
        ("tarefas_gestta", "done_step INTEGER"),
        ("tarefas_gestta", "overdue INTEGER"),
        ("tarefas_gestta", "fine INTEGER"),
        ("tarefas_gestta", "done_overdue INTEGER"),
        ("tarefas_gestta", "done_fine INTEGER"),
    ]
    _ok, _fail = [], []
    for _tab, _coldef in _cols:
        _col = _coldef.split()[0]
        try:
            with get_conn() as conn:
                conn.execute(
                    f"ALTER TABLE {_tab} ADD COLUMN IF NOT EXISTS {_coldef}"
                )
            _ok.append(_col)
        except Exception as _e:
            _fail.append(f"{_tab}.{_col}: {_e}")
    print(f"[_migrar_postgres] ok={_ok} fail={_fail}", flush=True)


def init_db() -> None:
    """Cria tabelas se não existirem e popula mocks na 1ª execução."""
    with get_conn() as conn:
        for stmt in DDL:
            conn.executescript(stmt)
        # Em Postgres (produção), as migrações já foram feitas pelo
        # script `migrar_sqlite_para_supabase.py`. As funções _migrar()
        # e _popular_mocks() usam sintaxe específica do SQLite
        # (PRAGMA, OR IGNORE, sqlite3.OperationalError), então só
        # rodam em modo dev local.
        if not is_postgres():
            _migrar(conn)
            _popular_mocks(conn)

    if is_postgres():
        _migrar_postgres()


def _migrar(conn: sqlite3.Connection) -> None:
    """Adiciona colunas novas em bancos criados antes das mudanças."""
    # vigilancia_sanitaria.risco_sanitario
    cols_vig = {r["name"] for r in conn.execute("PRAGMA table_info(vigilancia_sanitaria);")}
    if "risco_sanitario" not in cols_vig:
        try:
            conn.execute("ALTER TABLE vigilancia_sanitaria ADD COLUMN risco_sanitario TEXT;")
        except Exception:
            pass

    # cnae_risco.grau_risco e cnae_risco.fonte (NR-04)
    cols_risco = {r["name"] for r in conn.execute("PRAGMA table_info(cnae_risco);")}
    if "grau_risco" not in cols_risco:
        try:
            conn.execute("ALTER TABLE cnae_risco ADD COLUMN grau_risco INTEGER;")
        except Exception:
            pass
    if "fonte" not in cols_risco:
        try:
            conn.execute("ALTER TABLE cnae_risco ADD COLUMN fonte TEXT;")
        except Exception:
            pass

    # processos.canal_redesim (Online / Presencial / Hibrido)
    cols_proc = {r["name"] for r in conn.execute("PRAGMA table_info(processos);")}
    if "canal_redesim" not in cols_proc:
        try:
            conn.execute("ALTER TABLE processos ADD COLUMN canal_redesim TEXT DEFAULT 'Online';")
        except Exception:
            pass
    if "motivo_presencial" not in cols_proc:
        try:
            conn.execute("ALTER TABLE processos ADD COLUMN motivo_presencial TEXT;")
        except Exception:
            pass

    # protocolos_redesim.substituido_por_id (rastreio de substituições)
    try:
        cols_pr = {r["name"] for r in conn.execute("PRAGMA table_info(protocolos_redesim);")}
    except Exception:
        cols_pr = set()
    if cols_pr and "substituido_por_id" not in cols_pr:
        try:
            conn.execute(
                "ALTER TABLE protocolos_redesim ADD COLUMN substituido_por_id INTEGER;"
            )
        except Exception:
            pass

    # cnae_conselho — adiciona tipo_registro em bancos antigos
    try:
        cols_conselho = {r["name"] for r in conn.execute("PRAGMA table_info(cnae_conselho);")}
    except Exception:
        cols_conselho = set()
    if cols_conselho and "tipo_registro" not in cols_conselho:
        try:
            conn.execute(
                "ALTER TABLE cnae_conselho ADD COLUMN tipo_registro TEXT;"
            )
        except Exception:
            pass

    # tarefas_gestta — campos vindos da API REST (gestta_id, due_date, etc.)
    try:
        cols_g = {r["name"] for r in conn.execute("PRAGMA table_info(tarefas_gestta);")}
    except Exception:
        cols_g = set()
    if cols_g:
        novas_g = [
            ("gestta_id", "TEXT"),         # _id da tarefa no GESTTA (chave única)
            ("gestta_customer_id", "TEXT"),
            ("gestta_owner_id", "TEXT"),
            ("subtype", "TEXT"),
            ("due_date", "TEXT"),          # ISO string
            ("competence_date", "TEXT"),
            ("created_at", "TEXT"),
            ("legal_date", "TEXT"),
            ("total_step", "INTEGER"),
            ("done_step", "INTEGER"),
            ("overdue", "INTEGER"),        # bool 0/1
            ("fine", "INTEGER"),           # bool 0/1
            ("done_overdue", "INTEGER"),
            ("done_fine", "INTEGER"),
        ]
        for col, tipo in novas_g:
            if col not in cols_g:
                try:
                    conn.execute(f"ALTER TABLE tarefas_gestta ADD COLUMN {col} {tipo};")
                except Exception:
                    pass

    # pendencias.cliente_avulso (serviço avulso sem empresa cadastrada)
    # + tornar empresa_id NULLABLE (precisa recriar tabela porque
    # SQLite não permite alterar NOT NULL via ALTER COLUMN).
    try:
        cols_pend = {r["name"] for r in conn.execute("PRAGMA table_info(pendencias);")}
    except Exception:
        cols_pend = set()
    if cols_pend and "cliente_avulso" not in cols_pend:
        try:
            conn.execute(
                "ALTER TABLE pendencias ADD COLUMN cliente_avulso TEXT;"
            )
        except Exception:
            pass
    # Recria tabela com empresa_id NULLABLE — só executa se ainda
    # estiver com NOT NULL.
    if cols_pend:
        info = conn.execute("PRAGMA table_info(pendencias);").fetchall()
        emp_col = next((r for r in info if r["name"] == "empresa_id"), None)
        if emp_col and emp_col["notnull"] == 1:
            try:
                conn.executescript("""
                    PRAGMA foreign_keys=off;
                    BEGIN TRANSACTION;
                    CREATE TABLE pendencias_new (
                        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                        empresa_id          INTEGER,
                        cliente_avulso      TEXT,
                        assunto             TEXT NOT NULL,
                        descricao           TEXT,
                        prioridade          TEXT NOT NULL DEFAULT 'Média',
                        status              TEXT NOT NULL DEFAULT 'Aberta',
                        data_inicio         TEXT NOT NULL DEFAULT (date('now', 'localtime')),
                        data_limite         TEXT,
                        dias_alerta         INTEGER NOT NULL DEFAULT 7,
                        ultima_atualizacao  TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                        resolvida           INTEGER NOT NULL DEFAULT 0,
                        criado_em           TEXT DEFAULT (datetime('now', 'localtime')),
                        atualizado_em       TEXT DEFAULT (datetime('now', 'localtime')),
                        FOREIGN KEY(empresa_id) REFERENCES empresas(id) ON DELETE CASCADE
                    );
                    INSERT INTO pendencias_new (
                        id, empresa_id, cliente_avulso, assunto, descricao,
                        prioridade, status, data_inicio, data_limite, dias_alerta,
                        ultima_atualizacao, resolvida, criado_em, atualizado_em
                    )
                    SELECT id, empresa_id, NULL, assunto, descricao,
                           prioridade, status, data_inicio, data_limite, dias_alerta,
                           ultima_atualizacao, resolvida, criado_em, atualizado_em
                      FROM pendencias;
                    DROP TABLE pendencias;
                    ALTER TABLE pendencias_new RENAME TO pendencias;
                    CREATE INDEX IF NOT EXISTS idx_pendencias_empresa ON pendencias(empresa_id);
                    CREATE INDEX IF NOT EXISTS idx_pendencias_status ON pendencias(status);
                    CREATE INDEX IF NOT EXISTS idx_pendencias_resolvida ON pendencias(resolvida);
                    COMMIT;
                    PRAGMA foreign_keys=on;
                """)
            except Exception:
                pass


# =====================================================
    # ── cobrancas_dominio.comissao — migração para bancos existentes ──
    try:
        with get_conn() as conn:
            conn.execute(
                "ALTER TABLE cobrancas_dominio ADD COLUMN comissao REAL;"
            )
    except Exception:
        pass


# DADOS MOCK PARA AS MATRIZES
# =====================================================
CNAE_RISCO_MOCK = [
    # (cnae, descricao, risco)
    ("4711-3/02", "Comércio varejista de mercadorias em geral - supermercados", "Médio"),
    ("4721-1/02", "Padaria e confeitaria com predominância de revenda", "Alto"),
    ("5611-2/01", "Restaurantes e similares", "Alto"),
    ("5611-2/03", "Lanchonetes, casas de chá, sucos e similares", "Médio"),
    ("4781-4/00", "Comércio varejista de artigos do vestuário e acessórios", "Baixo"),
    ("6920-6/01", "Atividades de contabilidade", "Baixo"),
    ("8630-5/03", "Atividade médica ambulatorial restrita a consultas", "Alto"),
    ("9602-5/01", "Cabeleireiros, manicure e pedicure", "Médio"),
    ("4530-7/03", "Comércio a varejo de peças e acessórios novos para veículos automotores", "Baixo"),
    ("8599-6/04", "Treinamento em desenvolvimento profissional e gerencial", "Baixo"),
]

VIGILANCIA_SANITARIA_MOCK = [
    # (cnae, descricao, exige_licenca, nivel)
    ("4711-3/02", "Supermercados", 1, "Municipal"),
    ("4721-1/02", "Padaria e confeitaria", 1, "Municipal"),
    ("5611-2/01", "Restaurantes e similares", 1, "Municipal"),
    ("5611-2/03", "Lanchonetes", 1, "Municipal"),
    ("8630-5/03", "Atividade médica ambulatorial", 1, "Estadual"),
    ("9602-5/01", "Salões de beleza", 1, "Municipal"),
    ("4781-4/00", "Vestuário", 0, None),
    ("6920-6/01", "Contabilidade", 0, None),
    ("4530-7/03", "Peças automotivas", 0, None),
    ("8599-6/04", "Treinamentos", 0, None),
]

# -----------------------------------------------------------
# BOMBEIROS — seed da IT-01/2019 do CBPMESP (São Paulo).
# -----------------------------------------------------------
# Interpretação da classificação de ocupação (IT-01, Tabela 1):
#   A = Residencial          (A-1 unifamiliar, A-2 multifamiliar, A-3 coletivo)
#   B = Serviços de hospedagem
#   C = Comercial            (C-1 baixa, C-2 média, C-3 grande carga incêndio)
#   D = Serviços profissionais (escritórios, consultórios, clínicas)
#   E = Educacional
#   F = Local de reunião pública
#   G = Serviço automotivo
#   H = Serviço de saúde e institucional
#   I = Industrial           (I-1 baixo, I-2 médio, I-3 alto risco)
#   J = Depósito             (J-1 baixo, J-2 médio, J-3/J-4 alto)
#   L = Explosivos
#   M = Especial (inflamáveis, silos, terminais)
#
# Regra simplificada (Decreto SP 63.911/2018 + IT-01):
#   - Edificações ≤ 250 m² e até 2 pavimentos com baixa carga de incêndio
#     dispensam AVCB (precisam só de CLCB).
#   - Acima disso, ou com alto risco, exige AVCB.
# Para efeito do seed colocamos o cenário TÍPICO (empresa comum).
# (cnae, descricao, exige_avcb, grau_risco, ocupacao, area_limite_m2, obs, fonte)
BOMBEIROS_CNAE_SEED = [
    # ---------- Escritórios / Serviços profissionais (D) ----------
    ("6920-6/01", "Atividades de contabilidade", 1, "Baixo", "D-1", 750,
     "Até 750 m² e 2 pavimentos pode ser CLCB", "IT-01/CBPMESP"),
    ("6920-6/02", "Atividades de consultoria", 1, "Baixo", "D-1", 750,
     "Até 750 m² e 2 pavimentos pode ser CLCB", "IT-01/CBPMESP"),
    ("6911-7/01", "Serviços advocatícios", 1, "Baixo", "D-1", 750,
     "Até 750 m² e 2 pavimentos pode ser CLCB", "IT-01/CBPMESP"),
    ("6911-7/03", "Agente de propriedade industrial", 1, "Baixo", "D-1", 750, None, "IT-01/CBPMESP"),
    ("7020-4/00", "Atividades de consultoria em gestão empresarial", 1, "Baixo", "D-1", 750, None, "IT-01/CBPMESP"),
    ("7490-1/04", "Atividades de intermediação e agenciamento", 1, "Baixo", "D-1", 750, None, "IT-01/CBPMESP"),
    ("8211-3/00", "Serviços combinados de escritório", 1, "Baixo", "D-1", 750, None, "IT-01/CBPMESP"),
    ("8599-6/04", "Treinamento em desenvolvimento profissional", 1, "Baixo", "E-6", 500,
     "Educacional — AVCB sempre exigido acima de 500 m²", "IT-01/CBPMESP"),
    # ---------- Software / TI ----------
    ("6201-5/01", "Desenvolvimento de programas de computador sob encomenda", 1, "Baixo", "D-1", 750, None, "IT-01/CBPMESP"),
    ("6202-3/00", "Desenvolvimento e licenciamento de software customizável", 1, "Baixo", "D-1", 750, None, "IT-01/CBPMESP"),
    ("6203-1/00", "Desenvolvimento e licenciamento de software não-customizável", 1, "Baixo", "D-1", 750, None, "IT-01/CBPMESP"),
    ("6204-0/00", "Consultoria em TI", 1, "Baixo", "D-1", 750, None, "IT-01/CBPMESP"),
    # ---------- Saúde (H-2/H-3) ----------
    ("8630-5/03", "Atividade médica ambulatorial", 1, "Médio", "H-2", None,
     "Ambulatório — AVCB exigido", "IT-01/CBPMESP"),
    ("8630-5/01", "Atividade médica com recursos de apoio diagnóstico", 1, "Médio", "H-2", None, None, "IT-01/CBPMESP"),
    ("8610-1/01", "Atividades de atendimento hospitalar (exceto pronto-socorro)", 1, "Alto", "H-3", None,
     "Hospital — alto risco, AVCB obrigatório", "IT-01/CBPMESP"),
    ("8610-1/02", "Pronto-socorro e unidades hospitalares para atendimento a urgências", 1, "Alto", "H-3", None, None, "IT-01/CBPMESP"),
    ("8630-5/02", "Atividade médica com recursos para realização de procedimentos cirúrgicos", 1, "Alto", "H-3", None, None, "IT-01/CBPMESP"),
    ("8650-0/04", "Atividades de fisioterapia", 1, "Baixo", "H-2", 750, None, "IT-01/CBPMESP"),
    ("8650-0/02", "Atividades de profissionais da nutrição", 1, "Baixo", "D-2", 750, None, "IT-01/CBPMESP"),
    ("8640-2/01", "Laboratórios de anatomia patológica e citológica", 1, "Médio", "H-2", None, None, "IT-01/CBPMESP"),
    ("8640-2/02", "Laboratórios clínicos", 1, "Médio", "H-2", None, None, "IT-01/CBPMESP"),
    ("8630-5/04", "Atividade odontológica", 1, "Baixo", "D-2", 750, None, "IT-01/CBPMESP"),
    ("7500-1/00", "Atividades veterinárias", 1, "Médio", "H-2", None, None, "IT-01/CBPMESP"),
    # ---------- Comércio varejista (C-1 / C-2) ----------
    ("4711-3/02", "Supermercados", 1, "Médio", "C-2", None,
     "Supermercado — AVCB exigido", "IT-01/CBPMESP"),
    ("4711-3/01", "Hipermercados", 1, "Alto", "C-3", None, None, "IT-01/CBPMESP"),
    ("4712-1/00", "Minimercados, mercearias e armazéns", 1, "Baixo", "C-1", 750, None, "IT-01/CBPMESP"),
    ("4721-1/02", "Padaria e confeitaria com predominância de revenda", 1, "Médio", "C-2", None,
     "Forno a lenha/elétrico exige AVCB", "IT-01/CBPMESP"),
    ("4721-1/03", "Comércio varejista de laticínios e frios", 1, "Baixo", "C-1", 750, None, "IT-01/CBPMESP"),
    ("4722-9/01", "Comércio varejista de carnes — açougues", 1, "Baixo", "C-1", 750, None, "IT-01/CBPMESP"),
    ("4761-0/01", "Comércio varejista de livros", 1, "Médio", "C-2", None,
     "Livros — alta carga de incêndio, AVCB exigido acima de 300 m²",
     "IT-01/CBPMESP"),
    ("4761-0/02", "Comércio varejista de jornais e revistas", 1, "Médio", "C-2", None, None, "IT-01/CBPMESP"),
    ("4781-4/00", "Comércio varejista de artigos do vestuário e acessórios", 1, "Baixo", "C-1", 750, None, "IT-01/CBPMESP"),
    ("4782-2/01", "Comércio varejista de calçados", 1, "Baixo", "C-1", 750, None, "IT-01/CBPMESP"),
    ("4744-0/01", "Comércio varejista de ferragens e ferramentas", 1, "Médio", "C-2", None, None, "IT-01/CBPMESP"),
    ("4744-0/05", "Comércio varejista de materiais de construção em geral", 1, "Médio", "C-2", None, None, "IT-01/CBPMESP"),
    ("4744-0/06", "Comércio varejista de pedras para revestimento", 1, "Baixo", "C-1", 750, None, "IT-01/CBPMESP"),
    ("4751-2/00", "Comércio varejista de equipamentos de informática", 1, "Médio", "C-2", None, None, "IT-01/CBPMESP"),
    ("4754-7/01", "Comércio varejista de móveis", 1, "Médio", "C-2", None,
     "Móveis — alta carga de incêndio", "IT-01/CBPMESP"),
    ("4763-6/02", "Comércio varejista de artigos esportivos", 1, "Baixo", "C-1", 750, None, "IT-01/CBPMESP"),
    ("4772-5/00", "Comércio varejista de cosméticos, perfumaria e higiene", 1, "Médio", "C-2", None,
     "Produtos inflamáveis (aerosóis) — AVCB", "IT-01/CBPMESP"),
    ("4773-3/00", "Comércio varejista de artigos médicos e ortopédicos", 1, "Baixo", "C-1", 750, None, "IT-01/CBPMESP"),
    ("4774-1/00", "Comércio varejista de artigos de óptica", 1, "Baixo", "C-1", 750, None, "IT-01/CBPMESP"),
    ("4789-0/05", "Comércio varejista de produtos saneantes domissanitários", 1, "Médio", "C-2", None, None, "IT-01/CBPMESP"),
    # ---------- Postos e automotivo ----------
    ("4731-8/00", "Comércio varejista de combustíveis para veículos automotores", 1, "Alto", "M-1", None,
     "Posto de gasolina — alto risco, AVCB obrigatório + IT específica", "IT-01/CBPMESP"),
    ("4530-7/03", "Comércio a varejo de peças e acessórios novos para veículos", 1, "Baixo", "G-2", 750, None, "IT-01/CBPMESP"),
    ("4520-0/01", "Serviços de manutenção e reparação mecânica de veículos", 1, "Médio", "G-3", None,
     "Oficina mecânica — AVCB exigido", "IT-01/CBPMESP"),
    ("4520-0/05", "Serviços de lavagem, lubrificação e polimento", 1, "Médio", "G-3", None, None, "IT-01/CBPMESP"),
    # ---------- Bares, restaurantes e reunião ----------
    ("5611-2/01", "Restaurantes e similares", 1, "Médio", "F-8", None,
     "Reunião de público — AVCB obrigatório", "IT-01/CBPMESP"),
    ("5611-2/02", "Bares e outros estabelecimentos especializados em servir bebidas", 1, "Médio", "F-8", None, None, "IT-01/CBPMESP"),
    ("5611-2/03", "Lanchonetes, casas de chá, sucos e similares", 1, "Médio", "F-8", None, None, "IT-01/CBPMESP"),
    ("5612-1/00", "Serviços ambulantes de alimentação", 0, "Baixo", None, None,
     "Ambulante — dispensado de AVCB", "IT-01/CBPMESP"),
    ("5620-1/01", "Fornecimento de alimentos preparados para empresas", 1, "Médio", "F-8", None, None, "IT-01/CBPMESP"),
    # ---------- Beleza / bem-estar ----------
    ("9602-5/01", "Cabeleireiros, manicure e pedicure", 1, "Baixo", "D-2", 750, None, "IT-01/CBPMESP"),
    ("9602-5/02", "Atividades de estética e outros serviços de cuidados com a beleza", 1, "Baixo", "D-2", 750, None, "IT-01/CBPMESP"),
    ("9313-1/00", "Atividades de condicionamento físico (academias)", 1, "Médio", "F-3", None,
     "Academia — reunião pública, AVCB exigido", "IT-01/CBPMESP"),
    # ---------- Hospedagem ----------
    ("5510-8/01", "Hotéis", 1, "Alto", "B-1", None, None, "IT-01/CBPMESP"),
    ("5510-8/02", "Apart-hotéis", 1, "Alto", "B-1", None, None, "IT-01/CBPMESP"),
    ("5510-8/03", "Motéis", 1, "Alto", "B-2", None, None, "IT-01/CBPMESP"),
    # ---------- Educacional ----------
    ("8511-2/00", "Educação infantil — creche", 1, "Alto", "E-6", None,
     "Creche — alto risco, AVCB obrigatório", "IT-01/CBPMESP"),
    ("8512-1/00", "Educação infantil — pré-escola", 1, "Alto", "E-6", None, None, "IT-01/CBPMESP"),
    ("8513-9/00", "Ensino fundamental", 1, "Médio", "E-1", None, None, "IT-01/CBPMESP"),
    ("8520-1/00", "Ensino médio", 1, "Médio", "E-1", None, None, "IT-01/CBPMESP"),
    ("8531-7/00", "Educação superior — graduação", 1, "Médio", "E-5", None, None, "IT-01/CBPMESP"),
    ("8591-1/00", "Ensino de esportes", 1, "Médio", "F-3", None, None, "IT-01/CBPMESP"),
    ("8593-7/00", "Ensino de idiomas", 1, "Baixo", "E-3", 500, None, "IT-01/CBPMESP"),
    # ---------- Depósitos / atacado ----------
    ("5211-7/01", "Armazéns gerais — emissão de warrant", 1, "Alto", "J-3", None,
     "Depósito — alto risco, AVCB", "IT-01/CBPMESP"),
    ("5211-7/02", "Guarda-móveis", 1, "Médio", "J-2", None, None, "IT-01/CBPMESP"),
    ("5211-7/99", "Depósitos de mercadorias para terceiros, exceto armazéns gerais", 1, "Médio", "J-2", None, None, "IT-01/CBPMESP"),
    ("4635-4/02", "Comércio atacadista de cerveja, chope e refrigerante", 1, "Médio", "J-2", None, None, "IT-01/CBPMESP"),
    # ---------- Indústria (I-1/I-2/I-3) — típicas ----------
    ("1091-1/01", "Fabricação de produtos de panificação industrial", 1, "Médio", "I-2", None, None, "IT-01/CBPMESP"),
    ("1412-6/02", "Confecção, sob medida, de peças do vestuário", 1, "Baixo", "I-1", 750, None, "IT-01/CBPMESP"),
    ("1813-0/99", "Impressão de material para outros usos", 1, "Médio", "I-2", None, None, "IT-01/CBPMESP"),
    ("2599-3/99", "Fabricação de produtos diversos de metal", 1, "Médio", "I-2", None, None, "IT-01/CBPMESP"),
    # ---------- Construção ----------
    ("4120-4/00", "Construção de edifícios", 0, "—", None, None,
     "Atividade de obra — AVCB é do CLIENTE final, não da construtora",
     "IT-01/CBPMESP"),
    ("4399-1/03", "Obras de alvenaria", 0, "—", None, None, None, "IT-01/CBPMESP"),
    # ---------- Logística e transporte ----------
    ("4930-2/01", "Transporte rodoviário de carga, municipal", 1, "Médio", "G-4", None, None, "IT-01/CBPMESP"),
    ("4930-2/02", "Transporte rodoviário de carga, intermunicipal", 1, "Médio", "G-4", None, None, "IT-01/CBPMESP"),
    # ---------- Atividades artísticas / eventos ----------
    ("8230-0/01", "Serviços de organização de feiras, congressos e festas", 1, "Alto", "F-6", None,
     "Eventos — reunião pública, AVCB obrigatório + AVL específico",
     "IT-01/CBPMESP"),
    ("8230-0/02", "Casas de festas e eventos", 1, "Alto", "F-6", None, None, "IT-01/CBPMESP"),
    ("9001-9/01", "Produção teatral", 1, "Alto", "F-6", None, None, "IT-01/CBPMESP"),
    ("5914-6/00", "Atividades de exibição cinematográfica", 1, "Alto", "F-5", None, None, "IT-01/CBPMESP"),
    # ---------- Edição (não é comércio, mas algumas empresas usam) ----------
    ("5811-5/00", "Edição de livros", 1, "Baixo", "D-1", 750, None, "IT-01/CBPMESP"),
    ("5812-3/00", "Edição de jornais", 1, "Baixo", "D-1", 750, None, "IT-01/CBPMESP"),
]


def _popular_mocks(conn: sqlite3.Connection) -> None:
    cur = conn.execute("SELECT COUNT(*) AS c FROM cnae_risco;")
    if cur.fetchone()["c"] == 0:
        conn.executemany(
            "INSERT OR IGNORE INTO cnae_risco (cnae, descricao, risco) VALUES (?,?,?)",
            CNAE_RISCO_MOCK,
        )
    cur = conn.execute("SELECT COUNT(*) AS c FROM vigilancia_sanitaria;")
    if cur.fetchone()["c"] == 0:
        conn.executemany(
            "INSERT OR IGNORE INTO vigilancia_sanitaria "
            "(cnae, descricao, exige_licenca, nivel) VALUES (?,?,?,?)",
            VIGILANCIA_SANITARIA_MOCK,
        )
    cur = conn.execute("SELECT COUNT(*) AS c FROM bombeiros_cnae;")
    if cur.fetchone()["c"] == 0:
        conn.executemany(
            "INSERT OR IGNORE INTO bombeiros_cnae "
            "(cnae, descricao, exige_avcb, grau_risco, ocupacao_it01, "
            " area_limite_m2, observacao, fonte) "
            "VALUES (?,?,?,?,?,?,?,?)",
            BOMBEIROS_CNAE_SEED,
        )


# =====================================================
# QUERIES DE ALTO NÍVEL
# =====================================================
STATUS_VALIDOS = [
    "Em análise",
    "Pendente de Documento",
    "Aguardando Vigilância Sanitária",
    "Aguardando Bombeiros",
    "Aguardando Prefeitura",
    "Deferido",
    "Indeferido",
    "Arquivado",
]


def listar_empresas():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM empresas ORDER BY razao_social"
        )]


def criar_empresa(razao_social, cnpj=None, endereco=None,
                  municipio=None, uf=None, responsavel=None):
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO empresas (razao_social, cnpj, endereco, municipio, uf, responsavel)
               VALUES (?,?,?,?,?,?)""",
            (razao_social, cnpj, endereco, municipio, uf, responsavel),
        )
        return cur.lastrowid


def listar_processos():
    sql = """
        SELECT p.*, e.razao_social, e.cnpj,
               julianday('now') - julianday(p.ultima_movimentacao) AS dias_parado
        FROM processos p
        JOIN empresas e ON e.id = p.empresa_id
        ORDER BY dias_parado DESC, p.id DESC
    """
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql)]


def criar_processo(empresa_id, protocolo, tipo, status="Em análise",
                   risco=None, exige_sanitaria=0, observacoes=None,
                   canal_redesim="Online", motivo_presencial=None,
                   cnaes: Optional[Iterable[dict]] = None):
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO processos
               (empresa_id, protocolo, tipo, status, risco, exige_sanitaria,
                observacoes, canal_redesim, motivo_presencial)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (empresa_id, protocolo, tipo, status, risco, exige_sanitaria,
             observacoes, canal_redesim, motivo_presencial),
        )
        proc_id = cur.lastrowid
        if cnaes:
            conn.executemany(
                """INSERT INTO processo_cnaes (processo_id, cnae, descricao, principal)
                   VALUES (?,?,?,?)""",
                [(proc_id, c["cnae"], c.get("descricao"), int(c.get("principal", 0)))
                 for c in cnaes],
            )
        return proc_id


def atualizar_status(processo_id, novo_status, comentario=None,
                      usuario="sistema",
                      *, fechar_protocolos_vinculados: bool = True):
    """Atualiza status do processo antigo.

    Se `fechar_protocolos_vinculados=True` (padrão) e o novo status é
    terminal (Deferido/Indeferido/Arquivado), também fecha automaticamente
    os protocolos REDESIM ativos da MESMA empresa — assim o Telegram
    para de mandar 'ATRASO CRÍTICO' pra protocolo que o usuário já
    considerou resolvido.

    Mapeamento: Deferido → Aprovada/Concluída · Indeferido → Indeferida ·
    Arquivado → Cancelada.

    Retorna dict com {ok, protocolos_fechados: int}.
    """
    with get_conn() as conn:
        atual = conn.execute(
            "SELECT status, empresa_id FROM processos WHERE id = ?",
            (processo_id,),
        ).fetchone()
        if not atual:
            return {"ok": False, "protocolos_fechados": 0}
        emp_id = dict(atual)["empresa_id"]
        conn.execute(
            """UPDATE processos
               SET status = ?, ultima_movimentacao = date('now','localtime')
               WHERE id = ?""",
            (novo_status, processo_id),
        )
        conn.execute(
            """INSERT INTO movimentacoes (processo_id, de_status, para_status, usuario, comentario)
               VALUES (?,?,?,?,?)""",
            (processo_id, dict(atual)["status"], novo_status, usuario,
             comentario),
        )

        # Cascata pros protocolos REDESIM da mesma empresa (se for status
        # terminal e o usuário pediu)
        fechados = 0
        if fechar_protocolos_vinculados and novo_status in (
                "Deferido", "Indeferido", "Arquivado"):
            mapa = {
                "Deferido": "Concluída",
                "Indeferido": "Indeferida",
                "Arquivado": "Cancelada",
            }
            novo_status_protocolo = mapa[novo_status]

            ativos = conn.execute(
                """SELECT id, tipo FROM protocolos_redesim
                   WHERE empresa_id = ?
                     AND status NOT IN
                       ('Aprovada','Concluída','Indeferida',
                        'Cancelada','Inativa')
                     AND substituido_por_id IS NULL""",
                (emp_id,),
            ).fetchall()

            for p in ativos:
                pid = dict(p)["id"]
                ptipo = dict(p)["tipo"]
                # Viabilidade não tem "Concluída", só "Aprovada"
                status_final = (
                    "Aprovada"
                    if (ptipo == "Viabilidade"
                        and novo_status == "Deferido")
                    else novo_status_protocolo
                )
                # Usa atualizar_status_protocolo se existir, senão
                # update direto pra não recursar
                conn.execute(
                    """UPDATE protocolos_redesim
                       SET status = ?,
                           atualizado_em = datetime('now','localtime')
                       WHERE id = ?""",
                    (status_final, pid),
                )
                fechados += 1

        return {"ok": True, "protocolos_fechados": fechados}


def cnaes_do_processo(processo_id):
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM processo_cnaes WHERE processo_id = ?", (processo_id,)
        )]


# NR-04 fallback por DIVISÃO CNAE (2 dígitos) — usado quando o CNAE
# específico não está cadastrado. Reflete a moda dentro de cada divisão
# segundo o Quadro I da NR-04 (Portaria SEPRT 8.873/2022).
# IMPORTANTE: é um chute educado. A UI marca explicitamente como
# "GRAU ESTIMADO" pra Eduardo saber que precisa confirmar nos casos
# críticos.
_NR04_FALLBACK_POR_DIVISAO = {
    "01": 3, "02": 3, "03": 3,                       # Agro / Pesca
    "05": 4, "06": 4, "07": 4, "08": 3, "09": 4,     # Extração
    "10": 3, "11": 3, "12": 3, "13": 3, "14": 3,
    "15": 3, "16": 3, "17": 3, "18": 2, "19": 3,
    "20": 3, "21": 3, "22": 3, "23": 3, "24": 4,
    "25": 3, "26": 3, "27": 3, "28": 3, "29": 3,
    "30": 3, "31": 3, "32": 3, "33": 3,              # Indústria
    "35": 3, "36": 3, "37": 3, "38": 3, "39": 3,     # Eletricidade/Água
    "41": 3, "42": 3, "43": 3,                       # Construção
    "45": 3, "46": 2, "47": 2,                       # Comércio
    "49": 3, "50": 3, "51": 3, "52": 2, "53": 2,     # Transporte
    "55": 2, "56": 2,                                # Hosp / Alim.
    "58": 1, "59": 2, "60": 2, "61": 1, "62": 1, "63": 1,  # Informação
    "64": 1, "65": 1, "66": 1,                       # Financeiro
    "68": 1,                                         # Imobiliário
    "69": 1, "70": 1, "71": 2, "72": 2, "73": 1,
    "74": 1, "75": 3,                                # Profissionais
    "77": 2, "78": 1, "79": 1, "80": 3, "81": 3, "82": 1,
    "84": 1,                                         # Adm. pública
    "85": 2,                                         # Educação
    "86": 3, "87": 3, "88": 2,                       # Saúde
    "90": 1, "91": 1, "92": 2, "93": 2,              # Cultura / Esporte
    "94": 1, "95": 2,                                # Organiz. / Reparação
    "96": 2,                                         # Serviços pessoais
    "97": 1, "99": 1,                                # Doméstico / Internac.
}


def buscar_risco_cnae(cnae):
    """Busca grau NR-04 do CNAE. Se não tiver cadastrado especificamente,
    usa fallback por DIVISÃO CNAE e marca `_inferido_por_divisao = True`.
    Sempre retorna um dict válido (nunca None), pra UI não mostrar
    "não cadastrado" — em vez disso mostra "GRAU ESTIMADO".
    """
    with get_conn() as conn:
        r = conn.execute(
            "SELECT * FROM cnae_risco WHERE cnae = ?", (cnae,)
        ).fetchone()
        if r:
            d = dict(r)
            # Se a base só tem o texto "risco" mas não grau numérico,
            # tenta derivar do texto pra não exibir "—"
            if d.get("grau_risco") is None:
                txt = (d.get("risco") or "").lower()
                if "alto" in txt:
                    d["grau_risco"] = 3
                    d["_grau_inferido_texto"] = True
                elif "médio" in txt or "medio" in txt:
                    d["grau_risco"] = 2
                    d["_grau_inferido_texto"] = True
                elif "baixo" in txt:
                    d["grau_risco"] = 1
                    d["_grau_inferido_texto"] = True
            return d

        # Não tem cadastrado — fallback por DIVISÃO
        if len(cnae) >= 2:
            div = cnae[:2]
            grau = _NR04_FALLBACK_POR_DIVISAO.get(div)
            if grau:
                txt = {1: "Baixo", 2: "Médio", 3: "Alto",
                       4: "Alto"}[grau]
                return {
                    "cnae": cnae,
                    "descricao": None,
                    "risco": txt,
                    "grau_risco": grau,
                    "fonte": (f"NR-04 — Quadro I (Portaria SEPRT 8.873/2022). "
                              f"Grau ESTIMADO pela divisão CNAE {div} — "
                              f"confirme o CNAE específico no Quadro I."),
                    "_inferido_por_divisao": True,
                }
        return None


def buscar_vigilancia(cnae):
    with get_conn() as conn:
        r = conn.execute(
            "SELECT * FROM vigilancia_sanitaria WHERE cnae = ?", (cnae,)
        ).fetchone()
        return dict(r) if r else None


def upsert_cnae_risco(cnae, descricao, risco, observacoes=None,
                      grau_risco=None, fonte=None):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO cnae_risco
               (cnae, descricao, risco, grau_risco, fonte, observacoes)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(cnae) DO UPDATE SET
                   descricao=excluded.descricao,
                   risco=excluded.risco,
                   grau_risco=excluded.grau_risco,
                   fonte=excluded.fonte,
                   observacoes=excluded.observacoes,
                   atualizado_em=datetime('now','localtime')""",
            (cnae, descricao, risco, grau_risco, fonte, observacoes),
        )


def importar_cnae_risco_em_massa(registros: list[dict]) -> dict:
    """
    Importa múltiplos CNAEs de uma vez (usado pela NR-04 e CGSIM 51).
    Cada registro deve ter: {cnae_classe, descricao, risco, grau_risco, fonte}
    ou {cnae, descricao, risco, ...}.
    Retorna {inseridos, atualizados, total}.
    """
    inseridos = 0
    atualizados = 0
    with get_conn() as conn:
        for r in registros:
            cnae = r.get("cnae") or r.get("cnae_classe")
            if not cnae:
                continue
            existente = conn.execute(
                "SELECT 1 FROM cnae_risco WHERE cnae = ?", (cnae,)
            ).fetchone()
            conn.execute(
                """INSERT INTO cnae_risco
                   (cnae, descricao, risco, grau_risco, fonte)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT(cnae) DO UPDATE SET
                       descricao=excluded.descricao,
                       risco=excluded.risco,
                       grau_risco=excluded.grau_risco,
                       fonte=excluded.fonte,
                       atualizado_em=datetime('now','localtime')""",
                (cnae, r.get("descricao"), r.get("risco"),
                 r.get("grau_risco"), r.get("fonte")),
            )
            if existente:
                atualizados += 1
            else:
                inseridos += 1
    return {"inseridos": inseridos, "atualizados": atualizados,
            "total": inseridos + atualizados}


def upsert_vigilancia(cnae, descricao, exige_licenca, nivel=None, fonte=None,
                      risco_sanitario=None):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO vigilancia_sanitaria
                   (cnae, descricao, exige_licenca, nivel, fonte, risco_sanitario)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(cnae) DO UPDATE SET
                   descricao=excluded.descricao,
                   exige_licenca=excluded.exige_licenca,
                   nivel=excluded.nivel,
                   fonte=excluded.fonte,
                   risco_sanitario=excluded.risco_sanitario,
                   atualizado_em=datetime('now','localtime')""",
            (cnae, descricao, int(exige_licenca), nivel, fonte, risco_sanitario),
        )


def excluir_vigilancia(cnae):
    """Remove um CNAE da tabela de vigilância sanitária."""
    with get_conn() as conn:
        conn.execute("DELETE FROM vigilancia_sanitaria WHERE cnae = ?", (cnae,))


def excluir_varios_vigilancia(cnaes):
    """Remove vários CNAEs de uma vez."""
    if not cnaes:
        return 0
    with get_conn() as conn:
        placeholders = ",".join("?" for _ in cnaes)
        cur = conn.execute(
            f"DELETE FROM vigilancia_sanitaria WHERE cnae IN ({placeholders})",
            tuple(cnaes),
        )
        return cur.rowcount


# =====================================================
# BOMBEIROS — Classificador técnico por CNAE (IT-01)
# =====================================================
def buscar_bombeiros_cnae(cnae):
    """Busca um CNAE na tabela de classificação de Bombeiros.

    Aceita tanto a subclasse completa (9999-9/99) quanto a classe (99.99-9),
    caindo para a classe se não encontrar a subclasse."""
    if not cnae:
        return None
    with get_conn() as conn:
        r = conn.execute(
            "SELECT * FROM bombeiros_cnae WHERE cnae = ?", (cnae,)
        ).fetchone()
        if r:
            return dict(r)
        # Fallback para classe (os primeiros 7 caracteres: 9999-9)
        classe = cnae.split("/")[0] if "/" in cnae else cnae
        r = conn.execute(
            "SELECT * FROM bombeiros_cnae WHERE cnae LIKE ? LIMIT 1",
            (f"{classe}%",),
        ).fetchone()
        return dict(r) if r else None


def listar_bombeiros_cnae():
    """Retorna todos os registros da classificação CNAE → Bombeiros."""
    with get_conn() as conn:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM bombeiros_cnae ORDER BY cnae"
            )
        ]


def upsert_bombeiros_cnae(
    cnae,
    descricao=None,
    exige_avcb=1,
    grau_risco=None,
    ocupacao_it01=None,
    area_limite_m2=None,
    observacao=None,
    fonte="IT-01/CBPMESP",
):
    """Insere ou atualiza um CNAE na classificação de Bombeiros."""
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO bombeiros_cnae
                   (cnae, descricao, exige_avcb, grau_risco, ocupacao_it01,
                    area_limite_m2, observacao, fonte, atualizado_em)
               VALUES (?,?,?,?,?,?,?,?, datetime('now','localtime'))
               ON CONFLICT(cnae) DO UPDATE SET
                   descricao      = excluded.descricao,
                   exige_avcb     = excluded.exige_avcb,
                   grau_risco     = excluded.grau_risco,
                   ocupacao_it01  = excluded.ocupacao_it01,
                   area_limite_m2 = excluded.area_limite_m2,
                   observacao     = excluded.observacao,
                   fonte          = excluded.fonte,
                   atualizado_em  = datetime('now','localtime')""",
            (
                cnae,
                descricao,
                int(exige_avcb),
                grau_risco,
                ocupacao_it01,
                area_limite_m2,
                observacao,
                fonte,
            ),
        )


def excluir_bombeiros_cnae(cnae):
    """Remove um CNAE da tabela de classificação de Bombeiros."""
    with get_conn() as conn:
        conn.execute("DELETE FROM bombeiros_cnae WHERE cnae = ?", (cnae,))


def excluir_varios_bombeiros_cnae(cnaes):
    """Remove vários CNAEs de Bombeiros de uma vez."""
    if not cnaes:
        return 0
    with get_conn() as conn:
        placeholders = ",".join("?" for _ in cnaes)
        cur = conn.execute(
            f"DELETE FROM bombeiros_cnae WHERE cnae IN ({placeholders})",
            tuple(cnaes),
        )
        return cur.rowcount


def processos_atrasados(dias):
    sql = """
        SELECT p.*, e.razao_social,
               CAST(julianday('now') - julianday(p.ultima_movimentacao) AS INTEGER) AS dias_parado
        FROM processos p
        JOIN empresas e ON e.id = p.empresa_id
        WHERE p.status NOT IN ('Deferido','Indeferido','Arquivado')
          AND julianday('now') - julianday(p.ultima_movimentacao) >= ?
        ORDER BY dias_parado DESC
    """
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, (dias,))]


def registrar_notificacao(processo_id, canal, mensagem, sucesso, erro=None):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO notificacoes (processo_id, canal, mensagem, sucesso, erro)
               VALUES (?,?,?,?,?)""",
            (processo_id, canal, mensagem, int(sucesso), erro),
        )


# =====================================================
# ALVARÁ DE BOMBEIROS (AVCB/CLCB)
# =====================================================
def criar_alvara_bombeiros(empresa_id, data_vencimento, tipo=None, numero=None,
                            data_emissao=None, arquivo_pdf=None, ocupacao=None,
                            area_construida=None, observacoes=None) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO alvaras_bombeiros
               (empresa_id, tipo, numero, data_emissao, data_vencimento,
                arquivo_pdf, ocupacao, area_construida, observacoes)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (empresa_id, tipo, numero, data_emissao, data_vencimento,
             arquivo_pdf, ocupacao, area_construida, observacoes),
        )
        return cur.lastrowid


def listar_alvaras_bombeiros(empresa_id=None):
    sql = """
        SELECT a.*, e.razao_social, e.cnpj,
               CAST(julianday(a.data_vencimento) - julianday('now') AS INTEGER) AS dias_para_vencer
        FROM alvaras_bombeiros a
        JOIN empresas e ON e.id = a.empresa_id
    """
    params = ()
    if empresa_id:
        sql += " WHERE a.empresa_id = ?"
        params = (empresa_id,)
    sql += " ORDER BY a.data_vencimento ASC"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, params)]


def alvaras_vencendo(dias=60):
    """AVCBs que vencem nos próximos N dias (ou já vencidos)."""
    sql = """
        SELECT a.*, e.razao_social, e.cnpj,
               CAST(julianday(a.data_vencimento) - julianday('now') AS INTEGER) AS dias_para_vencer
        FROM alvaras_bombeiros a
        JOIN empresas e ON e.id = a.empresa_id
        WHERE julianday(a.data_vencimento) - julianday('now') <= ?
        ORDER BY a.data_vencimento ASC
    """
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, (dias,))]


def excluir_alvara_bombeiros(alvara_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM alvaras_bombeiros WHERE id = ?", (alvara_id,))
        return cur.rowcount > 0


def marcar_alvara_alertado(alvara_id: int, janela: str) -> None:
    """janela = '30d', '60d' ou 'vencido'."""
    campo = {"30d": "alertado_30d", "60d": "alertado_60d",
             "vencido": "alertado_vencido"}.get(janela)
    if not campo:
        return
    with get_conn() as conn:
        conn.execute(f"UPDATE alvaras_bombeiros SET {campo} = 1 WHERE id = ?",
                     (alvara_id,))


# =====================================================
# DOCUMENTOS COM VENCIMENTO (genérico — CND, FGTS, CNDT etc.)
# =====================================================
TIPOS_DOCUMENTO_VENCIMENTO = [
    "CND Federal",
    "CND Estadual",
    "CND Municipal",
    "CND FGTS",
    "CNDT (Trabalhista)",
    "Alvará de Funcionamento",
    "Alvará Sanitário",
    "Licença Ambiental",
    "Contrato Social",
    "Procuração",
    "Certificado Digital",
    "Outro",
]


def criar_documento_vencimento(empresa_id, tipo, data_vencimento,
                                numero=None, descricao=None,
                                data_emissao=None, dias_alerta=45,
                                arquivo_pdf=None, observacoes=None,
                                status="Vigente"):
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO documentos_vencimento
               (empresa_id, tipo, numero, descricao, data_emissao,
                data_vencimento, dias_alerta, arquivo_pdf, status, observacoes)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (empresa_id, tipo, numero, descricao, data_emissao,
             data_vencimento, dias_alerta, arquivo_pdf, status, observacoes),
        )
        return cur.lastrowid


def listar_documentos_vencimento(empresa_id=None, apenas_vigentes=True):
    sql = """
        SELECT d.*, e.razao_social, e.cnpj,
               CAST(julianday(d.data_vencimento) - julianday('now') AS INTEGER)
                   AS dias_para_vencer
        FROM documentos_vencimento d
        JOIN empresas e ON e.id = d.empresa_id
    """
    params = []
    wheres = []
    if empresa_id:
        wheres.append("d.empresa_id = ?")
        params.append(empresa_id)
    if apenas_vigentes:
        wheres.append("d.status = 'Vigente'")
    if wheres:
        sql += " WHERE " + " AND ".join(wheres)
    sql += " ORDER BY d.data_vencimento ASC"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, params)]


def documentos_proximos_vencimento(dias=None):
    """
    Retorna documentos cuja `dias_para_vencer <= dias_alerta` (se dias não for
    passado) OU `dias_para_vencer <= dias` (se informado).
    Inclui já vencidos (dias_para_vencer < 0) pra cobrar renovação atrasada.
    """
    if dias is None:
        # usa o dias_alerta de cada documento
        sql = """
            SELECT d.*, e.razao_social, e.cnpj,
                   CAST(julianday(d.data_vencimento) - julianday('now') AS INTEGER)
                       AS dias_para_vencer
            FROM documentos_vencimento d
            JOIN empresas e ON e.id = d.empresa_id
            WHERE d.status = 'Vigente'
              AND julianday(d.data_vencimento) - julianday('now') <= d.dias_alerta
            ORDER BY d.data_vencimento ASC
        """
        params = ()
    else:
        sql = """
            SELECT d.*, e.razao_social, e.cnpj,
                   CAST(julianday(d.data_vencimento) - julianday('now') AS INTEGER)
                       AS dias_para_vencer
            FROM documentos_vencimento d
            JOIN empresas e ON e.id = d.empresa_id
            WHERE d.status = 'Vigente'
              AND julianday(d.data_vencimento) - julianday('now') <= ?
            ORDER BY d.data_vencimento ASC
        """
        params = (dias,)
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, params)]


def atualizar_documento_vencimento(doc_id, **campos):
    """Atualiza campos arbitrários do documento (uso pra edição/renovação)."""
    if not campos:
        return False
    campos["atualizado_em"] = None  # vai virar datetime('now') via trigger
    set_sql = ", ".join(
        f"{k} = ?" if k != "atualizado_em"
        else "atualizado_em = datetime('now', 'localtime')"
        for k in campos
    )
    values = [v for k, v in campos.items() if k != "atualizado_em"]
    values.append(doc_id)
    with get_conn() as conn:
        cur = conn.execute(
            f"UPDATE documentos_vencimento SET {set_sql} WHERE id = ?",
            values,
        )
        return cur.rowcount > 0


def excluir_documento_vencimento(doc_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM documentos_vencimento WHERE id = ?", (doc_id,)
        )
        return cur.rowcount > 0


def renovar_documento(doc_antigo_id, novo_data_vencimento,
                      novo_numero=None, novo_arquivo_pdf=None,
                      novo_data_emissao=None, observacoes=None):
    """
    Marca o documento antigo como 'Renovado' e cria um novo Vigente,
    linkando o novo ao antigo via renovado_para_id.
    """
    with get_conn() as conn:
        antigo = conn.execute(
            "SELECT * FROM documentos_vencimento WHERE id = ?",
            (doc_antigo_id,),
        ).fetchone()
        if not antigo:
            return None
        cur = conn.execute(
            """INSERT INTO documentos_vencimento
               (empresa_id, tipo, numero, descricao, data_emissao,
                data_vencimento, dias_alerta, arquivo_pdf, status, observacoes)
               VALUES (?,?,?,?,?,?,?,?,'Vigente',?)""",
            (antigo["empresa_id"], antigo["tipo"],
             novo_numero or antigo["numero"],
             antigo["descricao"], novo_data_emissao,
             novo_data_vencimento, antigo["dias_alerta"],
             novo_arquivo_pdf, observacoes),
        )
        novo_id = cur.lastrowid
        conn.execute(
            """UPDATE documentos_vencimento
               SET status = 'Renovado',
                   renovado_para_id = ?,
                   atualizado_em = datetime('now', 'localtime')
               WHERE id = ?""",
            (novo_id, doc_antigo_id),
        )
        return novo_id


# =====================================================
# PROTOCOLOS REDESIM (Viabilidade / Licenciamento)
# =====================================================
# Tipos válidos
TIPO_PROTOCOLO_VIABILIDADE = "Viabilidade"
TIPO_PROTOCOLO_LICENCIAMENTO = "Licenciamento"
TIPOS_PROTOCOLO_REDESIM = [
    TIPO_PROTOCOLO_VIABILIDADE,
    TIPO_PROTOCOLO_LICENCIAMENTO,
]

# Status válidos (reais do portal Facilita-SP/REDESIM)
STATUS_PROTOCOLO_VIABILIDADE = [
    "Em análise",
    "Aguardando Reconsideração",
    "Aprovada",
    "Indeferida",
    "Cancelada",
    "Inativa",
]
STATUS_PROTOCOLO_LICENCIAMENTO = [
    "Pendente de avaliação do risco",
    "Em análise",
    "Concluída",
    "Indeferida",
    "Cancelada",
    "Inativa",
]

# Status que disparam alerta imediato (problema)
STATUS_PROTOCOLO_PROBLEMA = {"Indeferida", "Cancelada", "Inativa"}
# Status finalizados (pro verde do semáforo / timeline)
STATUS_PROTOCOLO_OK = {"Aprovada", "Concluída"}
# Status em andamento (amarelo)
STATUS_PROTOCOLO_EM_ANDAMENTO = {"Em análise", "Pendente de avaliação do risco"}


def buscar_empresa_por_cnpj(cnpj: str) -> dict | None:
    """Retorna a empresa com CNPJ informado (ou None).
    Normaliza removendo pontuação antes de buscar.
    """
    if not cnpj:
        return None
    # Normalizar: tira tudo que não é dígito
    digitos = "".join(c for c in str(cnpj) if c.isdigit())
    if not digitos:
        return None
    with get_conn() as conn:
        # Tenta match exato primeiro
        r = conn.execute(
            "SELECT * FROM empresas WHERE cnpj = ?", (cnpj,)
        ).fetchone()
        if r:
            return dict(r)
        # Match normalizado (remove pontuação armazenada também)
        r = conn.execute(
            """SELECT * FROM empresas
               WHERE REPLACE(REPLACE(REPLACE(REPLACE(cnpj,'.',''),'/',''),'-',''),' ','') = ?""",
            (digitos,),
        ).fetchone()
        return dict(r) if r else None


def criar_protocolo_redesim(
    empresa_id: int,
    tipo: str,
    numero_protocolo: str,
    *,
    numero_solicitacao: str | None = None,
    data_solicitacao: str | None = None,
    evento: str | None = None,
    orgao_registro: str | None = None,
    status: str = "Em análise",
    observacoes: str | None = None,
) -> int:
    """Cria um protocolo vinculado a uma empresa. Retorna o ID gerado."""
    if tipo not in TIPOS_PROTOCOLO_REDESIM:
        raise ValueError(f"Tipo inválido: {tipo}. Use {TIPOS_PROTOCOLO_REDESIM}")
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO protocolos_redesim
               (empresa_id, tipo, numero_protocolo, numero_solicitacao,
                data_solicitacao, evento, orgao_registro, status, observacoes)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (empresa_id, tipo, numero_protocolo, numero_solicitacao,
             data_solicitacao, evento, orgao_registro, status, observacoes),
        )
        return cur.lastrowid


def listar_protocolos_empresa(empresa_id: int) -> list[dict]:
    """Retorna todos os protocolos REDESIM de uma empresa,
    ordenados do mais recente para o mais antigo (pela data_solicitacao)."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM protocolos_redesim
               WHERE empresa_id = ?
               ORDER BY
                 COALESCE(data_solicitacao, criado_em) DESC,
                 id DESC""",
            (empresa_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def listar_todos_protocolos(apenas_problematicos: bool = False) -> list[dict]:
    """Retorna todos os protocolos de todas as empresas (para painel geral)."""
    sql = """
        SELECT p.*, e.razao_social, e.cnpj
        FROM protocolos_redesim p
        JOIN empresas e ON e.id = p.empresa_id
    """
    params = ()
    if apenas_problematicos:
        placeholders = ",".join("?" for _ in STATUS_PROTOCOLO_PROBLEMA)
        sql += f" WHERE p.status IN ({placeholders})"
        params = tuple(STATUS_PROTOCOLO_PROBLEMA)
    sql += " ORDER BY COALESCE(p.data_solicitacao, p.criado_em) DESC, p.id DESC"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, params)]


def buscar_protocolo_redesim(protocolo_id: int) -> dict | None:
    with get_conn() as conn:
        r = conn.execute(
            """SELECT p.*, e.razao_social, e.cnpj
               FROM protocolos_redesim p
               JOIN empresas e ON e.id = p.empresa_id
               WHERE p.id = ?""",
            (protocolo_id,),
        ).fetchone()
        return dict(r) if r else None


def atualizar_status_protocolo(
    protocolo_id: int,
    novo_status: str,
    observacoes: str | None = None,
) -> dict | None:
    """Atualiza o status de um protocolo. Retorna o dict do protocolo
    atualizado (ou None se não existir). O app deve disparar alerta
    quando o novo_status estiver em STATUS_PROTOCOLO_PROBLEMA."""
    with get_conn() as conn:
        atual = conn.execute(
            "SELECT * FROM protocolos_redesim WHERE id = ?",
            (protocolo_id,),
        ).fetchone()
        if not atual:
            return None
        if observacoes is not None:
            conn.execute(
                """UPDATE protocolos_redesim
                   SET status = ?, observacoes = ?,
                       atualizado_em = datetime('now','localtime')
                   WHERE id = ?""",
                (novo_status, observacoes, protocolo_id),
            )
        else:
            conn.execute(
                """UPDATE protocolos_redesim
                   SET status = ?,
                       atualizado_em = datetime('now','localtime')
                   WHERE id = ?""",
                (novo_status, protocolo_id),
            )
        r = conn.execute(
            """SELECT p.*, e.razao_social, e.cnpj
               FROM protocolos_redesim p
               JOIN empresas e ON e.id = p.empresa_id
               WHERE p.id = ?""",
            (protocolo_id,),
        ).fetchone()
        return dict(r) if r else None


def protocolos_problematicos_ativos(
    empresa_id: int,
    tipo: str | None = None,
) -> list[dict]:
    """Retorna protocolos com status Indeferida/Cancelada/Inativa que ainda
    NÃO foram substituídos (substituido_por_id IS NULL) — candidatos a
    serem substituídos quando um novo protocolo for criado.

    Se `tipo` for informado, filtra só os daquele tipo.
    """
    with get_conn() as conn:
        placeholders = ",".join("?" for _ in STATUS_PROTOCOLO_PROBLEMA)
        params: tuple = (empresa_id, *tuple(STATUS_PROTOCOLO_PROBLEMA))
        sql = (
            "SELECT * FROM protocolos_redesim "
            f"WHERE empresa_id = ? AND status IN ({placeholders}) "
            "AND substituido_por_id IS NULL"
        )
        if tipo:
            sql += " AND tipo = ?"
            params = params + (tipo,)
        sql += " ORDER BY COALESCE(data_solicitacao, criado_em) DESC, id DESC"
        return [dict(r) for r in conn.execute(sql, params)]


def substituir_protocolos(
    empresa_id: int,
    substituto_id: int,
    *,
    tipo: str | None = None,
) -> int:
    """Marca todos os protocolos problemáticos ainda não substituídos da
    empresa como substituídos pelo `substituto_id`. Retorna o nº de linhas
    afetadas.

    Use após criar um novo protocolo, quando o Eduardo confirma que ele
    substitui os anteriores com status Indeferida/Cancelada/Inativa.
    """
    with get_conn() as conn:
        placeholders = ",".join("?" for _ in STATUS_PROTOCOLO_PROBLEMA)
        params: tuple = (
            substituto_id, empresa_id, *tuple(STATUS_PROTOCOLO_PROBLEMA),
            substituto_id,
        )
        sql = (
            "UPDATE protocolos_redesim "
            "SET substituido_por_id = ?, "
            "    atualizado_em = datetime('now','localtime') "
            f"WHERE empresa_id = ? AND status IN ({placeholders}) "
            "AND substituido_por_id IS NULL AND id != ?"
        )
        if tipo:
            sql += " AND tipo = ?"
            params = params + (tipo,)
        cur = conn.execute(sql, params)
        return cur.rowcount


def excluir_protocolo_redesim(protocolo_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM protocolos_redesim WHERE id = ?",
            (protocolo_id,),
        )
        return cur.rowcount > 0


def atualizar_empresa(empresa_id: int, **campos) -> bool:
    """Atualiza campos arbitrários de uma empresa (razao_social, endereco, etc.)."""
    permitidos = {"razao_social", "cnpj", "endereco", "municipio", "uf", "responsavel"}
    campos = {k: v for k, v in campos.items() if k in permitidos and v is not None}
    if not campos:
        return False
    set_sql = ", ".join(f"{k} = ?" for k in campos)
    values = list(campos.values())
    values.append(empresa_id)
    with get_conn() as conn:
        cur = conn.execute(
            f"UPDATE empresas SET {set_sql} WHERE id = ?",
            values,
        )
        return cur.rowcount > 0


# -----------------------------------------------------------
# Normas / bases oficiais (NR-04, CVS-SP, IT-01, CGSIM, CONCLA)
# -----------------------------------------------------------
NORMAS_META = {
    "nr04": {
        "titulo": "NR-04 — Matriz de Risco CNAE",
        "orgao": "Ministério do Trabalho / SEPRT",
        "url": "https://www.gov.br/trabalho-e-emprego/pt-br/assuntos/inspecao-do-trabalho/seguranca-e-saude-no-trabalho/normas-regulamentadoras/nr-04-atualizada-2022.pdf",
        "descricao": "Quadro I da NR-04 — enquadra CNAEs em grau de risco 1 a 4 (Baixo/Médio/Alto).",
    },
    "cvs_sp": {
        "titulo": "Vigilância Sanitária — CVS-SP",
        "orgao": "Centro de Vigilância Sanitária SP",
        "url": "https://www.cvs.saude.sp.gov.br/zip/portaria-cvs-01-de-10-01-2024-atualizada.pdf",
        "descricao": "Portaria CVS-SP 1/2024 — CNAEs que exigem licença sanitária.",
    },
    "it01_cbpmesp": {
        "titulo": "IT-01 — Bombeiros SP (CBPMESP)",
        "orgao": "Corpo de Bombeiros PMESP",
        "url": "https://www.policiamilitar.sp.gov.br/ccb/",
        "descricao": "Instrução Técnica 01 — classificação das ocupações e exigência de AVCB/CLCB.",
    },
    "cgsim": {
        "titulo": "CGSIM — Classificação de Risco",
        "orgao": "Comitê para Gestão da Rede Nacional (REDESIM)",
        "url": "https://www.gov.br/empresas-e-negocios/pt-br/redesim/legislacao/comite-para-gestao-da-rede-nacional-para-a-simplificacao-do-registro-e-da-legalizacao-de-empresas-e-negocios-cgsim",
        "descricao": "Resoluções CGSIM 59/2020 e 61/2020 — classificação de risco para viabilidade.",
    },
    "concla": {
        "titulo": "CONCLA / CNAE — Base Oficial IBGE",
        "orgao": "IBGE / CONCLA",
        "url": "https://concla.ibge.gov.br/busca-online-cnae.html",
        "descricao": "Lista mestra de CNAEs (subclasses). Atualizar quando o IBGE lançar nova versão.",
    },
}


def registrar_atualizacao_norma(base, *, orgao=None, versao=None,
                                arquivo_origem=None, hash_arquivo=None,
                                registros=None, observacoes=None,
                                atualizado_por=None):
    """Insere um registro de atualização de norma."""
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO normas_atualizacao
               (base, orgao, versao, arquivo_origem, hash_arquivo,
                registros, observacoes, atualizado_por)
               VALUES (?,?,?,?,?,?,?,?)""",
            (base, orgao, versao, arquivo_origem, hash_arquivo,
             registros, observacoes, atualizado_por),
        )
        return cur.lastrowid


def ultima_atualizacao(base: str):
    """Retorna a última atualização registrada para uma base (ou None)."""
    with get_conn() as conn:
        row = conn.execute(
            """SELECT * FROM normas_atualizacao
               WHERE base = ?
               ORDER BY datetime(criado_em) DESC, id DESC
               LIMIT 1""",
            (base,),
        ).fetchone()
        return dict(row) if row else None


def historico_atualizacoes(base: str | None = None, limite: int = 50):
    """Retorna histórico de atualizações (opcionalmente filtrado por base)."""
    with get_conn() as conn:
        if base:
            rows = conn.execute(
                """SELECT * FROM normas_atualizacao
                   WHERE base = ?
                   ORDER BY datetime(criado_em) DESC, id DESC
                   LIMIT ?""",
                (base, limite),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM normas_atualizacao
                   ORDER BY datetime(criado_em) DESC, id DESC
                   LIMIT ?""",
                (limite,),
            ).fetchall()
        return [dict(r) for r in rows]


def dias_desde_atualizacao(base: str) -> int | None:
    """Quantos dias desde a última atualização da base, ou None se nunca."""
    with get_conn() as conn:
        row = conn.execute(
            """SELECT CAST(julianday('now', 'localtime')
                        - julianday(criado_em) AS INTEGER) AS dias
               FROM normas_atualizacao
               WHERE base = ?
               ORDER BY datetime(criado_em) DESC, id DESC
               LIMIT 1""",
            (base,),
        ).fetchone()
        return int(row["dias"]) if row and row["dias"] is not None else None


def status_normas(limite_dias: int = 180):
    """
    Retorna status consolidado de cada base conhecida:
    {base, titulo, orgao, ultima_data, dias, versao, status}
    status ∈ {'nunca', 'ok', 'atencao', 'atrasado'}
    """
    resultado = []
    for base, meta in NORMAS_META.items():
        ult = ultima_atualizacao(base)
        dias = dias_desde_atualizacao(base)
        if ult is None:
            status = "nunca"
        elif dias is None:
            status = "ok"
        elif dias > limite_dias:
            status = "atrasado"
        elif dias > limite_dias * 0.66:
            status = "atencao"
        else:
            status = "ok"
        resultado.append({
            "base": base,
            "titulo": meta["titulo"],
            "orgao": meta["orgao"],
            "url": meta["url"],
            "descricao": meta["descricao"],
            "ultima_data": ult["criado_em"] if ult else None,
            "dias": dias,
            "versao": ult["versao"] if ult else None,
            "arquivo_origem": ult["arquivo_origem"] if ult else None,
            "registros": ult["registros"] if ult else None,
            "atualizado_por": ult["atualizado_por"] if ult else None,
            "status": status,
        })
    return resultado


# -----------------------------------------------------------
# CONCLA — Tabela mestra de CNAEs (IBGE)
# -----------------------------------------------------------
def importar_cnae_concla(registros: list[dict]) -> dict:
    """
    Importa a estrutura detalhada da CNAE (IBGE). Cada registro:
    {codigo, nivel, denominacao, secao, divisao, grupo, classe}

    Faz upsert (INSERT OR REPLACE). Retorna {inseridos, atualizados, total}.
    """
    inseridos = 0
    atualizados = 0
    with get_conn() as conn:
        for r in registros:
            codigo = r.get("codigo")
            if not codigo:
                continue
            ja_existe = conn.execute(
                "SELECT 1 FROM cnae_concla WHERE codigo = ?", (codigo,)
            ).fetchone()
            conn.execute(
                """INSERT OR REPLACE INTO cnae_concla
                   (codigo, nivel, denominacao, secao, divisao, grupo, classe,
                    atualizado_em)
                   VALUES (?,?,?,?,?,?,?, datetime('now','localtime'))""",
                (
                    codigo,
                    r.get("nivel"),
                    r.get("denominacao"),
                    r.get("secao"),
                    r.get("divisao"),
                    r.get("grupo"),
                    r.get("classe"),
                ),
            )
            if ja_existe:
                atualizados += 1
            else:
                inseridos += 1
    return {"inseridos": inseridos, "atualizados": atualizados,
            "total": inseridos + atualizados}


def buscar_cnae_concla(codigo: str) -> dict | None:
    """Retorna o registro CONCLA (qualquer nível) ou None."""
    if not codigo:
        return None
    with get_conn() as conn:
        r = conn.execute(
            "SELECT * FROM cnae_concla WHERE codigo = ?",
            (codigo.strip(),),
        ).fetchone()
        return dict(r) if r else None


def contar_cnae_concla() -> dict:
    """Retorna contagem por nível (secao, divisao, grupo, classe, subclasse)."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT nivel, COUNT(*) AS qtd FROM cnae_concla GROUP BY nivel"
        ).fetchall()
        return {r["nivel"]: r["qtd"] for r in rows}


# -----------------------------------------------------------
# CGSIM — CNAEs com classificação de risco
# -----------------------------------------------------------
def importar_cgsim_cnae(registros: list[dict]) -> dict:
    """
    Importa tabela CGSIM. Cada registro:
    {codigo, denominacao, nivel_risco, orgao, observacoes, fonte}
    """
    inseridos = 0
    atualizados = 0
    with get_conn() as conn:
        for r in registros:
            codigo = r.get("codigo")
            if not codigo:
                continue
            ja_existe = conn.execute(
                "SELECT 1 FROM cgsim_cnae WHERE codigo = ?", (codigo,)
            ).fetchone()
            conn.execute(
                """INSERT OR REPLACE INTO cgsim_cnae
                   (codigo, denominacao, nivel_risco, orgao, observacoes,
                    fonte, atualizado_em)
                   VALUES (?,?,?,?,?,?, datetime('now','localtime'))""",
                (
                    codigo,
                    r.get("denominacao"),
                    r.get("nivel_risco"),
                    r.get("orgao"),
                    r.get("observacoes"),
                    r.get("fonte", "CGSIM 59/2020"),
                ),
            )
            if ja_existe:
                atualizados += 1
            else:
                inseridos += 1
    return {"inseridos": inseridos, "atualizados": atualizados,
            "total": inseridos + atualizados}


def buscar_cgsim_cnae(codigo: str) -> dict | None:
    if not codigo:
        return None
    with get_conn() as conn:
        r = conn.execute(
            "SELECT * FROM cgsim_cnae WHERE codigo = ?",
            (codigo.strip(),),
        ).fetchone()
        return dict(r) if r else None


def contar_cgsim_cnae() -> int:
    with get_conn() as conn:
        r = conn.execute("SELECT COUNT(*) AS n FROM cgsim_cnae").fetchone()
        return int(r["n"]) if r else 0


# ---------------------------------------------------------------------------
# GESTTA — tarefas atrasadas importadas do relatório do escritório
# ---------------------------------------------------------------------------
import re as _re
import unicodedata as _ud

RISCOS_GESTTA = ["ALTO", "MÉDIO", "BAIXO"]

# Tipos de tarefa pra agrupamento e filtros rápidos. Identificados
# por palavras-chave no nome da tarefa GESTTA. Quando uma tarefa não
# se encaixa, vira "OUTROS" e pode ser reclassificada manualmente.
TIPO_TAREFA_LICENCA_FUNC    = "LICENCA_FUNCIONAMENTO"
TIPO_TAREFA_ALVARA_SANIT    = "ALVARA_SANITARIO"
TIPO_TAREFA_BOMBEIROS       = "BOMBEIROS"
TIPO_TAREFA_DEVOLUCAO       = "DEVOLUCAO"
TIPO_TAREFA_ABERTURA        = "ABERTURA"
TIPO_TAREFA_ALTERACAO       = "ALTERACAO"
TIPO_TAREFA_BAIXA           = "BAIXA"
TIPO_TAREFA_CONSELHO        = "CONSELHO"
TIPO_TAREFA_AMBIENTAL       = "AMBIENTAL"
TIPO_TAREFA_OUTROS          = "OUTROS"

TIPOS_TAREFA_GESTTA = [
    TIPO_TAREFA_LICENCA_FUNC,
    TIPO_TAREFA_ALVARA_SANIT,
    TIPO_TAREFA_BOMBEIROS,
    TIPO_TAREFA_DEVOLUCAO,
    TIPO_TAREFA_ABERTURA,
    TIPO_TAREFA_ALTERACAO,
    TIPO_TAREFA_BAIXA,
    TIPO_TAREFA_CONSELHO,
    TIPO_TAREFA_AMBIENTAL,
    TIPO_TAREFA_OUTROS,
]

TIPO_TAREFA_LABELS = {
    TIPO_TAREFA_LICENCA_FUNC:  "🏢 Licença de Funcionamento",
    TIPO_TAREFA_ALVARA_SANIT:  "🏥 Alvará Sanitário",
    TIPO_TAREFA_BOMBEIROS:     "🚒 Bombeiros (AVCB/CLCB)",
    TIPO_TAREFA_DEVOLUCAO:     "👋 Devolução / Distrato",
    TIPO_TAREFA_ABERTURA:      "➕ Abertura de empresa",
    TIPO_TAREFA_ALTERACAO:     "✏️ Alteração contratual",
    TIPO_TAREFA_BAIXA:         "🗑️ Baixa de empresa",
    TIPO_TAREFA_CONSELHO:      "👨‍⚕️ Conselho profissional",
    TIPO_TAREFA_AMBIENTAL:     "🌱 Licença Ambiental",
    TIPO_TAREFA_OUTROS:        "📌 Outros",
}


def classificar_tipo_tarefa_gestta(tarefa_nome: str,
                                    departamento: str | None = None) -> str:
    """Classifica a tarefa GESTTA em uma das categorias práticas
    pra que a equipe possa filtrar e atacar por bloco.

    A regra é ESTRUTURADA por palavra-chave no nome, com prioridade
    pros tipos mais específicos primeiro (bombeiros antes de licença
    genérica, alvará antes de licença, etc.).

    Retorna sempre uma string em TIPOS_TAREFA_GESTTA — nunca None.
    """
    t = (tarefa_nome or "").upper()
    d = (departamento or "").upper()

    # Descarta acentos pra ficar tolerante
    import unicodedata as _ud2
    t = _ud2.normalize("NFKD", t).encode("ASCII", "ignore").decode("ASCII")
    d = _ud2.normalize("NFKD", d).encode("ASCII", "ignore").decode("ASCII")

    # DEVOLUCAO / DISTRATO — palavra forte, identifica primeiro
    if any(k in t for k in [
        "DEVOLUCAO", "DEVOLUCÃO", "DEVOLVER",
        "DISTRATO", "ENCERR", "DESLIGAMENTO",
        "RESCIS", "DESVINCUL", "CANCELAMENTO DO CONTRATO",
        "CANCELAMENTO DE CONTRATO", "ENTREGA DE DOCUM",
        "TRANSFERENCIA PARA OUTR",
    ]):
        return TIPO_TAREFA_DEVOLUCAO

    # BOMBEIROS — AVCB, CLCB, Corpo de Bombeiros
    if any(k in t for k in [
        "AVCB", "CLCB", "BOMBEIRO", "BOMBEIROS",
        "VIA FACIL BOMBEIRO", "CB-PMESP", "CB PMESP",
    ]):
        return TIPO_TAREFA_BOMBEIROS

    # ALVARA SANITARIO / VIGILANCIA
    if ("ALVARA" in t and "SANIT" in t) or \
       "VIGILANCIA SANIT" in t or \
       "LICENCA SANIT" in t or \
       "CEVS" in t or \
       "VISA" in t.split() or \
       "COVISA" in t or \
       ("ANVISA" in t and "AFE" in t):
        return TIPO_TAREFA_ALVARA_SANIT

    # CONSELHO PROFISSIONAL
    siglas_conselho = (
        "CRM", "CRO", "CREA", "CRP", "CRC", "CRF", "CRN", "CRQ",
        "COREN", "CREFITO", "CREFSP", "CREF", "CRBM", "CRBIO",
        "CAU", "CORECON", "OAB", "ART", "RRT", "CRMV", "CFMV",
        "COFFITO", "CONFEF", "CFC", "CFM",
    )
    palavras = set(t.split())
    if (palavras & set(siglas_conselho)) or "CONSELHO" in t and "REGION" in t:
        return TIPO_TAREFA_CONSELHO

    # LICENCA AMBIENTAL
    if any(k in t for k in [
        "AMBIENT", "CETESB", "IBAMA", "CTF",
        "LICENCA AMBIENT", "OUTORGA",
    ]):
        return TIPO_TAREFA_AMBIENTAL

    # ABERTURA — se tiver "LICENÇA" no nome, vai pro bucket de Licença
    # (Eduardo: "tem licença escondida dentro de abertura/alteração")
    if "ABERTURA" in t or "CONSTITUI" in t:
        if "LICENC" in t:
            return TIPO_TAREFA_LICENCA_FUNC
        return TIPO_TAREFA_ABERTURA

    # ALTERACAO — idem: se tem licença no nome, é Licença na prática
    if "ALTERA" in t or "CONTRATO SOCIAL" in t:
        if "LICENC" in t:
            return TIPO_TAREFA_LICENCA_FUNC
        return TIPO_TAREFA_ALTERACAO

    # BAIXA fiscal
    if "BAIXA" in t and ("EMPRESA" in t or "JUNTA" in t or "RFB" in t
                          or "RECEITA" in t or "CNPJ" in t):
        return TIPO_TAREFA_BAIXA

    # LICENCA DE FUNCIONAMENTO (genérica) — vem POR ULTIMO porque é
    # a categoria mais ampla. Pega "renovação de licença", "funcionamento",
    # "alvará de funcionamento" (≠ sanitário).
    if "RENOVA" in t and "LICENC" in t:
        return TIPO_TAREFA_LICENCA_FUNC
    if "FUNCIONAMENTO" in t:
        return TIPO_TAREFA_LICENCA_FUNC
    if "ALVARA" in t:  # alvará genérico (não sanitário)
        return TIPO_TAREFA_LICENCA_FUNC
    if "LICEN" in t:
        return TIPO_TAREFA_LICENCA_FUNC

    return TIPO_TAREFA_OUTROS

_SUFIXOS_EMPRESARIAIS = (
    "LTDA", "LTDA.", "ME", "M.E.", "EPP", "E.P.P.",
    "EIRELI", "S.A.", "SA", "S/A", "CIA", "LIMITADA",
)


def normalizar_nome_cliente(nome: str) -> str:
    """Normaliza o nome do cliente para matching:
    - uppercase
    - remove acentos
    - remove pontuação
    - remove sufixos empresariais (LTDA, ME, EPP, EIRELI, SA, CIA)
    - colapsa espaços
    """
    if not nome:
        return ""
    s = _ud.normalize("NFKD", str(nome)).encode("ASCII", "ignore").decode("ASCII").upper()
    # remove pontuação
    s = _re.sub(r"[^A-Z0-9 ]", " ", s)
    # remove sufixos como palavra isolada
    tokens = [t for t in s.split() if t not in _SUFIXOS_EMPRESARIAIS]
    s = " ".join(tokens)
    # remove "- ME" "- EPP" remanescentes
    s = _re.sub(r"\s+", " ", s).strip()
    return s


def classificar_risco_tarefa_gestta(
    tarefa_nome: str, overdue: bool = False,
) -> tuple[str, str]:
    """Retorna (risco, motivo) para uma tarefa GESTTA.

    Quando `overdue=True`, eleva o risco em um nível
    (BAIXO→MÉDIO, MÉDIO→ALTO) e adiciona prefixo "🔴 ATRASADA — ".
    """
    t = (tarefa_nome or "").upper()
    if "RENOVA" in t and ("LICENC" in t or "FUNCIONAMENTO" in t):
        risco, motivo = "ALTO", "Renovação de licença — risco de operar sem licença vigente"
    elif "ALVAR" in t and "SANIT" in t:
        risco, motivo = "ALTO", "Alvará sanitário — fiscalização VISA / multa"
    elif "LICEN" in t and ("FUNCION" in t or "AMBIENT" in t or "CETESB" in t):
        risco, motivo = "ALTO", "Licença operacional — risco de autuação"
    elif "ABERTURA" in t:
        risco, motivo = "MÉDIO", "Empresa não operacional — trava faturamento"
    elif "ALTERAC" in t or "ALTERAÇ" in t:
        risco, motivo = "MÉDIO", "Alteração — cadastros desatualizados"
    elif "BAIXA" in t:
        risco, motivo = "MÉDIO", "Baixa de empresa — pendência cadastral"
    elif "INSCRI" in t and ("MUNIC" in t or "ESTAD" in t or "FEDER" in t or "CCM" in t):
        risco, motivo = "MÉDIO", "Inscrição — pendência fiscal/cadastral"
    elif any(c in t for c in ["CRMV","CRM","CREA","CRP","CRO","CRC","CRF","CRN","CRQ",
                                "COREN","CREFITO","CREFSP","CREF","CRBM","CRBio","CAU",
                                "CORECON","OAB","ART","RRT"]):
        risco, motivo = "MÉDIO", "Conselho profissional / RT — registro pendente"
    else:
        risco, motivo = "BAIXO", "Revisar manualmente"

    # Eleva risco se atrasada
    if overdue:
        prefixo = "🔴 ATRASADA — "
        if risco == "BAIXO":
            return ("MÉDIO", prefixo + motivo)
        if risco == "MÉDIO":
            return ("ALTO", prefixo + motivo)
        return ("ALTO", prefixo + motivo)
    return (risco, motivo)


def match_empresa_por_nome(nome_cliente: str) -> dict | None:
    """Procura empresa no banco pelo nome do cliente GESTTA (match por
    razao_social normalizada). Retorna dict da empresa ou None.
    """
    alvo = normalizar_nome_cliente(nome_cliente)
    if not alvo:
        return None
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM empresas").fetchall()
    for r in rows:
        if normalizar_nome_cliente(r["razao_social"]) == alvo:
            return dict(r)
    # match parcial — alvo contido na razao social (apenas se alvo > 5 chars)
    if len(alvo) > 5:
        for r in rows:
            rs = normalizar_nome_cliente(r["razao_social"])
            if rs and (alvo in rs or rs in alvo):
                return dict(r)
    return None


def importar_tarefas_gestta(
    registros: list[dict],
    *,
    origem_arquivo: str | None = None,
    substituir_existentes: bool = True,
) -> dict:
    """Importa uma leva de tarefas GESTTA.

    Cada registro deve ter pelo menos `tarefa_nome` e `cliente_nome`.
    Se `substituir_existentes` e já houver uma tarefa (tarefa_nome +
    cliente_norm + responsavel) NÃO resolvida, atualiza em vez de duplicar.

    Retorna contadores {'inseridos': n, 'atualizados': n, 'matched': n}.
    """
    inseridos = atualizados = matched = 0
    with get_conn() as conn:
        for reg in registros:
            tarefa_nome = (reg.get("tarefa_nome") or "").strip()
            cliente_nome = (reg.get("cliente_nome") or "").strip()
            if not tarefa_nome or not cliente_nome:
                continue
            cliente_norm = normalizar_nome_cliente(cliente_nome)
            responsavel = (reg.get("responsavel") or "").strip() or None
            atrasada = (reg.get("atrasada") or "").strip() or None
            status_gestta = (reg.get("status_gestta") or "").strip() or None
            departamento = (reg.get("departamento") or "").strip() or None
            risco, motivo = classificar_risco_tarefa_gestta(tarefa_nome)
            tipo = classificar_tipo_tarefa_gestta(tarefa_nome, departamento)
            # tentar matching automático
            emp = match_empresa_por_nome(cliente_nome)
            empresa_id = emp["id"] if emp else None
            if empresa_id:
                matched += 1

            existente = None
            if substituir_existentes:
                existente = conn.execute(
                    """SELECT id FROM tarefas_gestta
                       WHERE tarefa_nome = ? AND cliente_norm = ?
                         AND IFNULL(responsavel, '') = IFNULL(?, '')
                         AND resolvida = 0
                       LIMIT 1""",
                    (tarefa_nome, cliente_norm, responsavel),
                ).fetchone()

            if existente:
                conn.execute(
                    """UPDATE tarefas_gestta SET
                         cliente_nome=?, atrasada=?, status_gestta=?,
                         departamento=?, risco=?, motivo_risco=?, tipo=?,
                         empresa_id = COALESCE(empresa_id, ?),
                         origem_arquivo = COALESCE(?, origem_arquivo),
                         atualizado_em = datetime('now', 'localtime')
                       WHERE id = ?""",
                    (cliente_nome, atrasada, status_gestta, departamento,
                     risco, motivo, tipo,
                     empresa_id, origem_arquivo, existente["id"]),
                )
                atualizados += 1
            else:
                conn.execute(
                    """INSERT INTO tarefas_gestta (
                         tarefa_nome, cliente_nome, cliente_norm, responsavel,
                         atrasada, status_gestta, departamento,
                         risco, motivo_risco, tipo,
                         empresa_id, origem_arquivo
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (tarefa_nome, cliente_nome, cliente_norm, responsavel,
                     atrasada, status_gestta, departamento,
                     risco, motivo, tipo,
                     empresa_id, origem_arquivo),
                )
                inseridos += 1
        conn.commit()
    return {"inseridos": inseridos, "atualizados": atualizados, "matched": matched}


def upsert_tarefas_gestta_api(tarefas_api: list[dict]) -> dict:
    """Recebe a lista crua vinda de `GesttaClient.iter_tarefas()` (cada item é
    um dict com `_id`, `name`, `customer{}`, `owner{}`, `due_date`, `status`,
    `overdue`, `total_step`, `done_step`, etc.) e faz UPSERT na tabela
    `tarefas_gestta` usando `gestta_id` como chave única.

    Retorna {'inseridas', 'atualizadas', 'matched_empresa'}.
    """
    inseridas = atualizadas = matched = 0
    with get_conn() as conn:
        for t in tarefas_api:
            gestta_id = t.get("_id")
            if not gestta_id:
                continue
            tarefa_nome = (t.get("name") or "").strip()
            cust = t.get("customer") or {}
            owner = t.get("owner") or {}
            cliente_nome = (cust.get("name") or "").strip()
            cliente_norm = normalizar_nome_cliente(cliente_nome)
            responsavel = (owner.get("name") or "").strip() or None
            status_gestta = (t.get("status") or "").strip() or None
            is_overdue = bool(t.get("overdue"))
            atrasada = "Sim" if is_overdue else "Não"
            risco, motivo = classificar_risco_tarefa_gestta(
                tarefa_nome, overdue=is_overdue,
            )
            tipo_tarefa = classificar_tipo_tarefa_gestta(tarefa_nome)
            emp = match_empresa_por_nome(cliente_nome) if cliente_nome else None
            empresa_id = emp["id"] if emp else None
            if empresa_id:
                matched += 1

            existente = conn.execute(
                "SELECT id FROM tarefas_gestta WHERE gestta_id = ?",
                (gestta_id,),
            ).fetchone()

            campos = {
                "gestta_id": gestta_id,
                "gestta_customer_id": cust.get("_id"),
                "gestta_owner_id": owner.get("_id"),
                "tarefa_nome": tarefa_nome,
                "cliente_nome": cliente_nome,
                "cliente_norm": cliente_norm,
                "responsavel": responsavel,
                "atrasada": atrasada,
                "status_gestta": status_gestta,
                "departamento": None,  # API não retorna nesse endpoint
                "subtype": t.get("subtype"),
                "due_date": t.get("due_date"),
                "competence_date": t.get("competence_date"),
                "created_at": t.get("created_at"),
                "legal_date": t.get("legal_date"),
                "total_step": t.get("total_step"),
                "done_step": t.get("done_step"),
                "overdue": 1 if t.get("overdue") else 0,
                "fine": 1 if t.get("fine") else 0,
                "done_overdue": 1 if t.get("done_overdue") else 0,
                "done_fine": 1 if t.get("done_fine") else 0,
                "risco": risco,
                "motivo_risco": motivo,
                "tipo": tipo_tarefa,
                "origem_arquivo": "API GESTTA",
            }

            if existente:
                # mantém empresa_id/protocolo_id/resolvida que o usuário possa ter setado
                set_clause = ", ".join(f"{k} = ?" for k in campos)
                params = list(campos.values()) + [existente["id"]]
                conn.execute(
                    f"UPDATE tarefas_gestta SET {set_clause}, "
                    f"atualizado_em = datetime('now','localtime') WHERE id = ?",
                    params,
                )
                # Tenta vincular empresa se ainda não tem
                if empresa_id:
                    conn.execute(
                        "UPDATE tarefas_gestta SET empresa_id = COALESCE(empresa_id, ?) WHERE id = ?",
                        (empresa_id, existente["id"]),
                    )
                atualizadas += 1
            else:
                campos["empresa_id"] = empresa_id
                cols = ", ".join(campos.keys())
                placeholders = ", ".join("?" for _ in campos)
                conn.execute(
                    f"INSERT INTO tarefas_gestta ({cols}) VALUES ({placeholders})",
                    list(campos.values()),
                )
                inseridas += 1
        conn.commit()
    return {
        "inseridas": inseridas,
        "atualizadas": atualizadas,
        "matched_empresa": matched,
    }


def listar_tarefas_gestta(
    *,
    apenas_pendentes: bool = True,
    risco: str | None = None,
    responsavel: str | None = None,
    somente_sem_empresa: bool = False,
    somente_sem_protocolo: bool = False,
    tipo: str | list[str] | None = None,
    apenas_atrasadas: bool = False,
) -> list[dict]:
    """Lista tarefas GESTTA com filtros opcionais.

    Novos filtros:
      - `tipo`: string ou lista de tipos (LICENCA_FUNCIONAMENTO,
        ALVARA_SANITARIO, BOMBEIROS, DEVOLUCAO, etc.)
      - `apenas_atrasadas`: True só traz overdue=1 OU atrasada='Sim'.
    """
    sql = """
        SELECT t.*,
               e.razao_social AS empresa_razao_social,
               e.cnpj AS empresa_cnpj,
               pr.numero_protocolo AS protocolo_numero,
               pr.status AS protocolo_status
          FROM tarefas_gestta t
          LEFT JOIN empresas e ON e.id = t.empresa_id
          LEFT JOIN protocolos_redesim pr ON pr.id = t.protocolo_id
         WHERE 1=1
    """
    params: list = []
    if apenas_pendentes:
        sql += " AND t.resolvida = 0"
    if risco:
        sql += " AND t.risco = ?"
        params.append(risco)
    if responsavel:
        sql += " AND t.responsavel = ?"
        params.append(responsavel)
    if somente_sem_empresa:
        sql += " AND t.empresa_id IS NULL"
    if somente_sem_protocolo:
        sql += " AND t.protocolo_id IS NULL"
    if tipo:
        if isinstance(tipo, str):
            tipo = [tipo]
        placeholders = ",".join("?" * len(tipo))
        sql += f" AND COALESCE(t.tipo, '') IN ({placeholders})"
        params.extend(tipo)
    if apenas_atrasadas:
        # overdue=1 OU campo atrasada com texto positivo
        sql += (" AND (t.overdue = 1 OR "
                "UPPER(COALESCE(t.atrasada, '')) IN "
                "('SIM','YES','TRUE','1'))")
    sql += """
        ORDER BY CASE WHEN t.overdue = 1 THEN 0 ELSE 1 END,
                 CASE t.risco
                   WHEN 'ALTO' THEN 0
                   WHEN 'MÉDIO' THEN 1
                   WHEN 'BAIXO' THEN 2
                   ELSE 3
                 END,
                 COALESCE(t.due_date, '9999-12-31'),
                 t.responsavel,
                 t.cliente_nome
    """
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def pular_tarefa_gestta(tarefa_id: int, motivo: str | None = None) -> None:
    """Marca a tarefa como 'pulada' — não aparece mais na Fila de
    Renovação. Útil quando a tarefa está errada (cliente já fechou,
    duplicada, etc.). Pode ser despulada depois.
    """
    with get_conn() as conn:
        conn.execute(
            "UPDATE tarefas_gestta SET pulado = 1, "
            "motivo_pulado = COALESCE(?, motivo_pulado), "
            "pulado_em = datetime('now', 'localtime') "
            "WHERE id = ?",
            (motivo, tarefa_id),
        )


def despular_tarefa_gestta(tarefa_id: int) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE tarefas_gestta SET pulado = 0, "
            "motivo_pulado = NULL, pulado_em = NULL WHERE id = ?",
            (tarefa_id,),
        )


def fila_renovacao_licencas(
    *, incluir_pulados: bool = False,
    incluir_protocolados: bool = False,
) -> list[dict]:
    """Devolve a fila de renovações de Licença/VISA — tarefas GESTTA
    pendentes ordenadas pela mais antiga primeiro.

    Filtros:
      - apenas pendentes (resolvida=0)
      - tipo in (LICENCA_FUNCIONAMENTO, ALVARA_SANITARIO)
      - pulado = 0 (se incluir_pulados=False)
      - protocolo_id IS NULL (se incluir_protocolados=False)
    """
    sql = """
        SELECT t.*,
               e.razao_social AS empresa_razao_social,
               e.cnpj AS empresa_cnpj,
               e.municipio AS empresa_municipio,
               e.uf AS empresa_uf,
               pr.numero_protocolo AS protocolo_numero,
               pr.status AS protocolo_status
          FROM tarefas_gestta t
          LEFT JOIN empresas e ON e.id = t.empresa_id
          LEFT JOIN protocolos_redesim pr ON pr.id = t.protocolo_id
         WHERE t.resolvida = 0
           AND t.tipo IN ('LICENCA_FUNCIONAMENTO', 'ALVARA_SANITARIO')
    """
    if not incluir_pulados:
        sql += " AND COALESCE(t.pulado, 0) = 0"
    if not incluir_protocolados:
        sql += " AND t.protocolo_id IS NULL"
    sql += """
        ORDER BY CASE
                   WHEN t.tipo = 'ALVARA_SANITARIO' THEN 0
                   ELSE 1
                 END,
                 COALESCE(t.due_date, '9999-12-31') ASC,
                 t.cliente_nome
    """
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql).fetchall()]


def iniciar_protocolo_da_tarefa(
    *, tarefa_id: int, numero_protocolo: str,
    tipo_protocolo: str = "Viabilidade",
    status_inicial: str = "Em análise",
    data_solicitacao: str | None = None,
    observacoes: str | None = None,
    responsavel: str | None = None,
) -> int:
    """Cria um protocolo REDESIM a partir de uma tarefa GESTTA, e
    vincula automaticamente os dois pelo `tarefas_gestta.protocolo_id`.

    Retorna o ID do protocolo criado.
    """
    from datetime import date as _date
    if not data_solicitacao:
        data_solicitacao = _date.today().isoformat()

    with get_conn() as conn:
        # Pega dados da tarefa
        r = conn.execute(
            "SELECT * FROM tarefas_gestta WHERE id = ?", (tarefa_id,),
        ).fetchone()
        if not r:
            raise ValueError(f"Tarefa GESTTA {tarefa_id} não encontrada.")
        tarefa = dict(r)
        emp_id = tarefa.get("empresa_id")
        if not emp_id:
            raise ValueError(
                "Tarefa não está vinculada a uma empresa cadastrada. "
                "Vincule primeiro pelo botão na lista de Tarefas GESTTA."
            )

        # Cria o protocolo
        cur = conn.execute(
            """INSERT INTO protocolos_redesim
                 (empresa_id, tipo, numero_protocolo, status,
                  data_solicitacao, observacoes)
                 VALUES (?, ?, ?, ?, ?, ?)""",
            (emp_id, tipo_protocolo, numero_protocolo, status_inicial,
             data_solicitacao, observacoes),
        )
        protocolo_id = cur.lastrowid

        # Vincula a tarefa GESTTA ao protocolo
        conn.execute(
            "UPDATE tarefas_gestta SET protocolo_id = ?, "
            "atualizado_em = datetime('now', 'localtime') WHERE id = ?",
            (protocolo_id, tarefa_id),
        )
        return protocolo_id


def contar_tarefas_por_tipo(
    *, apenas_pendentes: bool = True,
) -> dict:
    """Retorna contagem de tarefas por tipo + sub-contagem de atrasadas.

    Output:
      {
        "LICENCA_FUNCIONAMENTO": {"total": 12, "atrasadas": 5},
        "ALVARA_SANITARIO": {"total": 8, "atrasadas": 3},
        ...
        "_SEM_TIPO": {"total": 0, "atrasadas": 0}  # ainda não classificadas
      }
    """
    sql = """
        SELECT COALESCE(tipo, '_SEM_TIPO') AS tipo,
               COUNT(*) AS total,
               SUM(CASE WHEN overdue = 1 OR
                            UPPER(COALESCE(atrasada,'')) IN
                              ('SIM','YES','TRUE','1') THEN 1 ELSE 0 END)
                 AS atrasadas
          FROM tarefas_gestta
    """
    if apenas_pendentes:
        sql += " WHERE resolvida = 0 "
    sql += " GROUP BY COALESCE(tipo, '_SEM_TIPO')"
    with get_conn() as conn:
        rows = conn.execute(sql).fetchall()
    out = {}
    for r in rows:
        d = dict(r)
        out[d["tipo"]] = {
            "total": int(d.get("total") or 0),
            "atrasadas": int(d.get("atrasadas") or 0),
        }
    return out


def reclassificar_tipos_tarefas(forcar: bool = False) -> int:
    """Aplica classificar_tipo_tarefa_gestta em todas as tarefas que
    ainda não têm `tipo` setado (ou todas, se forcar=True).

    Retorna o número de tarefas reclassificadas.
    """
    with get_conn() as conn:
        sql_sel = "SELECT id, tarefa_nome, departamento FROM tarefas_gestta"
        if not forcar:
            sql_sel += " WHERE tipo IS NULL OR tipo = ''"
        rows = conn.execute(sql_sel).fetchall()
        n = 0
        for r in rows:
            d = dict(r)
            tipo = classificar_tipo_tarefa_gestta(
                d.get("tarefa_nome", ""),
                d.get("departamento", ""),
            )
            conn.execute(
                "UPDATE tarefas_gestta SET tipo = ? WHERE id = ?",
                (tipo, d["id"]),
            )
            n += 1
        return n


def atualizar_tarefa_gestta(tarefa_id: int, **campos) -> bool:
    """Atualiza campos arbitrários de uma tarefa GESTTA.
    Campos permitidos: empresa_id, protocolo_id, resolvida, risco,
    motivo_risco, responsavel, status_gestta, observacoes (não existe — ignora).
    """
    permitidos = {
        "empresa_id", "protocolo_id", "resolvida",
        "risco", "motivo_risco", "responsavel", "status_gestta",
        "atrasada", "departamento",
    }
    sets = {k: v for k, v in campos.items() if k in permitidos}
    if not sets:
        return False
    sql = ", ".join(f"{k} = ?" for k in sets)
    params = list(sets.values()) + [tarefa_id]
    with get_conn() as conn:
        cur = conn.execute(
            f"UPDATE tarefas_gestta SET {sql}, atualizado_em = datetime('now','localtime') WHERE id = ?",
            params,
        )
        conn.commit()
        return cur.rowcount > 0


def marcar_tarefa_resolvida(tarefa_id: int, resolvida: bool = True) -> bool:
    return atualizar_tarefa_gestta(tarefa_id, resolvida=1 if resolvida else 0)


def excluir_tarefa_gestta(tarefa_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM tarefas_gestta WHERE id = ?", (tarefa_id,))
        conn.commit()
        return cur.rowcount > 0


def estatisticas_tarefas_gestta() -> dict:
    """Retorna estatísticas agregadas para o painel."""
    with get_conn() as conn:
        total = conn.execute(
            "SELECT COUNT(*) AS n FROM tarefas_gestta WHERE resolvida = 0"
        ).fetchone()["n"]
        resolvidas = conn.execute(
            "SELECT COUNT(*) AS n FROM tarefas_gestta WHERE resolvida = 1"
        ).fetchone()["n"]
        por_risco = {
            r["risco"]: r["n"] for r in conn.execute(
                """SELECT risco, COUNT(*) AS n FROM tarefas_gestta
                   WHERE resolvida = 0 GROUP BY risco"""
            ).fetchall()
        }
        por_resp = {
            (r["responsavel"] or "—"): r["n"] for r in conn.execute(
                """SELECT responsavel, COUNT(*) AS n FROM tarefas_gestta
                   WHERE resolvida = 0 GROUP BY responsavel"""
            ).fetchall()
        }
        sem_empresa = conn.execute(
            """SELECT COUNT(*) AS n FROM tarefas_gestta
               WHERE resolvida = 0 AND empresa_id IS NULL"""
        ).fetchone()["n"]
        sem_protocolo = conn.execute(
            """SELECT COUNT(*) AS n FROM tarefas_gestta
               WHERE resolvida = 0 AND protocolo_id IS NULL"""
        ).fetchone()["n"]
    return {
        "total_pendentes": total,
        "total_resolvidas": resolvidas,
        "por_risco": por_risco,
        "por_responsavel": por_resp,
        "sem_empresa": sem_empresa,
        "sem_protocolo": sem_protocolo,
    }


def listar_responsaveis_gestta() -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT DISTINCT responsavel FROM tarefas_gestta
               WHERE responsavel IS NOT NULL AND responsavel <> ''
               ORDER BY responsavel"""
        ).fetchall()
    return [r["responsavel"] for r in rows]


def buscar_tarefa_gestta(tarefa_id: int) -> dict | None:
    with get_conn() as conn:
        r = conn.execute(
            "SELECT * FROM tarefas_gestta WHERE id = ?", (tarefa_id,)
        ).fetchone()
        return dict(r) if r else None


# ---------------------------------------------------------------------------
# Anotações locais em tarefas GESTTA — histórico permanente
# ---------------------------------------------------------------------------
def adicionar_anotacao_local_gestta(
    gestta_id: str, texto: str,
    *, tipo: str = "NOTA", usuario: str | None = None,
) -> int:
    """Adiciona uma anotação no histórico LOCAL (não envia pro GESTTA)."""
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO gestta_anotacao_local
                 (gestta_id, tipo, texto, usuario, replicado)
               VALUES (?, ?, ?, ?, 0)""",
            (gestta_id, tipo, texto.strip(), usuario),
        )
        conn.commit()
        return cur.lastrowid


def marcar_anotacao_replicada(
    anotacao_id: int, *, sucesso: bool, erro: str | None = None,
) -> None:
    """Marca que tentou (ou não) replicar a anotação no GESTTA."""
    with get_conn() as conn:
        conn.execute(
            """UPDATE gestta_anotacao_local SET
                 replicado = ?,
                 replicado_em = CASE WHEN ? = 1 THEN datetime('now','localtime') ELSE replicado_em END,
                 erro_replicar = ?
               WHERE id = ?""",
            (1 if sucesso else 0, 1 if sucesso else 0, erro, anotacao_id),
        )
        conn.commit()


def listar_anotacoes_locais_gestta(gestta_id: str) -> list[dict]:
    """Lista o histórico local de anotações de uma tarefa GESTTA."""
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            """SELECT * FROM gestta_anotacao_local
                WHERE gestta_id = ?
                ORDER BY id DESC""",
            (gestta_id,),
        ).fetchall()]


# ---------------------------------------------------------------------------
# Playbooks — sugestão de próximo passo por tipo de tarefa
# ---------------------------------------------------------------------------
PLAYBOOKS_GESTTA = {
    "ABERTURA": {
        "padroes": ["ABERTURA"],
        "etapas": [
            ("Viabilidade", "Conferir protocolo no Facilita-SP / vreredesim.sp.gov.br"),
            ("Coletor Nacional", "Acessar redesim.gov.br → Coletor Nacional"),
            ("Registro JUCESP", "Junta Comercial — protocolo + DARE pago"),
            ("Inscrição Municipal", "Prefeitura — CCM/CNPJ municipal"),
            ("Licenciamento", "Vigilância/Bombeiros/Ambiental conforme CNAE"),
        ],
        "primeira_acao": (
            "Verifique se a Viabilidade já está aprovada. "
            "Se NÃO, ligue pro cliente e entenda em que ponto travou. "
            "Se SIM, avance pro Coletor Nacional."
        ),
    },
    "ALTERACAO": {
        "padroes": ["ALTERAC", "ALTERAÇ"],
        "etapas": [
            ("Identificar mudança", "Contrato social novo / alteração de endereço / inclusão CNAE"),
            ("Viabilidade (se mudou endereço/CNAE)", "Facilita-SP"),
            ("Coletor Nacional", "Atualização cadastral"),
            ("Junta Comercial", "Registro da alteração"),
            ("Comunicar municípios", "Inscrição Municipal atualizada"),
        ],
        "primeira_acao": (
            "Identifique QUE alteração é. Pegue o contrato/aditivo do cliente. "
            "Se mudou endereço ou CNAE, precisa de nova Viabilidade."
        ),
    },
    "RENOVACAO_LICENCA": {
        "padroes": ["RENOVA", "LICENC"],
        "etapas": [
            ("Conferir validade atual", "Documento físico ou Cevs/Sivisa"),
            ("Pagar taxa", "Boleto Prefeitura/Estado"),
            ("Solicitar renovação", "Sistema do município ou Sivisa"),
            ("Acompanhar processo", "Aguardar liberação ou inspeção"),
            ("Receber documento novo", "Anexar no sistema interno"),
        ],
        "primeira_acao": (
            "Pegue a licença atual e veja a data de vencimento. "
            "Se já venceu, urgência alta — pode estar gerando multa."
        ),
    },
    "ALVARA_SANITARIO": {
        "padroes": ["ALVAR", "SANIT", "VIGIL"],
        "etapas": [
            ("Conferir CEVS", "Sistema Sivisa - número do CEVS atual"),
            ("Avaliar nova classificação", "CVS 13/2025 isenta atividades de baixo risco"),
            ("Solicitar nova vistoria", "Se não isento, agendar VISA"),
            ("Acompanhar processo", "Sistema Sivisa"),
            ("Receber alvará", "Anexar no sistema"),
        ],
        "primeira_acao": (
            "Verifique no Consultor de CNAE se o CNAE está ISENTO pela CVS 13/2025. "
            "Se sim, basta protocolar dispensa. Se não, agendar VISA."
        ),
    },
    "BAIXA": {
        "padroes": ["BAIXA"],
        "etapas": [
            ("Pegar CND", "Federal, Estadual, Municipal, FGTS, CNDT"),
            ("Distrato/Encerramento", "Documento societário"),
            ("Receita Federal", "Baixa CNPJ via redesim.gov.br"),
            ("Junta Comercial", "Arquivamento da extinção"),
            ("Municípios e Estado", "Encerrar IM e IE"),
        ],
        "primeira_acao": (
            "Cliente trouxe distrato? Tem CNDs em dia? "
            "Sem CND não consegue baixar — primeiro regularize débitos."
        ),
    },
    "INSCRICAO": {
        "padroes": ["INSCRI"],
        "etapas": [
            ("Conferir CNPJ ativo", "Cartão CNPJ"),
            ("Solicitar IM/CCM", "Prefeitura competente"),
            ("Acompanhar deferimento", "Sistema do município"),
            ("Confirmar com cliente", "Comprovante de inscrição"),
        ],
        "primeira_acao": (
            "Veja se o CNPJ está ativo na Receita. Pegue o cartão CNPJ atualizado. "
            "Cada município tem seu sistema — verifique qual é o do cliente."
        ),
    },
    "DEFAULT": {
        "padroes": [],
        "etapas": [
            ("Identificar pé atual", "Conversar com cliente / verificar histórico"),
            ("Listar pendências", "Documentos faltantes / órgãos a contatar"),
            ("Definir próximo passo", "Ação concreta com prazo"),
        ],
        "primeira_acao": (
            "Tarefa genérica. Anote o que descobrir agora pra não perder o fio."
        ),
    },
}


def sugerir_proximo_passo(tarefa_nome: str) -> dict:
    """Retorna o playbook adequado pra um nome de tarefa."""
    nome = (tarefa_nome or "").upper()
    for chave, pb in PLAYBOOKS_GESTTA.items():
        if chave == "DEFAULT":
            continue
        for padrao in pb["padroes"]:
            if padrao in nome:
                return {"chave": chave, **pb}
    return {"chave": "DEFAULT", **PLAYBOOKS_GESTTA["DEFAULT"]}


def rematch_empresas_gestta() -> int:
    """Re-tenta o matching empresa↔tarefa para tarefas sem empresa_id.
    Retorna quantas foram vinculadas.
    """
    vinculadas = 0
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, cliente_nome FROM tarefas_gestta WHERE empresa_id IS NULL"
        ).fetchall()
    for r in rows:
        emp = match_empresa_por_nome(r["cliente_nome"])
        if emp:
            with get_conn() as conn:
                conn.execute(
                    "UPDATE tarefas_gestta SET empresa_id = ?, atualizado_em = datetime('now','localtime') WHERE id = ?",
                    (emp["id"], r["id"]),
                )
                conn.commit()
            vinculadas += 1
    return vinculadas


# ---------------------------------------------------------------------------
# PENDÊNCIAS GERAIS — qualquer assunto que precisa de acompanhamento
# (malha fina, retorno de órgão, follow-up com cliente, etc.)
# ---------------------------------------------------------------------------
STATUS_PENDENCIA = [
    "Aberta", "Em andamento", "Aguardando terceiro",
    "Resolvida", "Cancelada",
]
STATUS_PENDENCIA_FECHADA = {"Resolvida", "Cancelada"}
PRIORIDADES_PENDENCIA = ["Alta", "Média", "Baixa"]
TIPOS_MOVIMENTO_PENDENCIA = ["nota", "status", "contato", "retorno"]


def criar_pendencia(
    empresa_id: int | None,
    assunto: str,
    *,
    cliente_avulso: str | None = None,
    descricao: str | None = None,
    prioridade: str = "Média",
    status: str = "Aberta",
    data_inicio: str | None = None,
    data_limite: str | None = None,
    dias_alerta: int = 7,
) -> int:
    """Cria uma pendência. Retorna o id.

    `empresa_id` é opcional — se for None, deve-se informar
    `cliente_avulso` (nome livre do cliente, ex.: pessoa física ou
    serviço avulso sem CNPJ).
    """
    if prioridade not in PRIORIDADES_PENDENCIA:
        raise ValueError(f"prioridade inválida: {prioridade}")
    if status not in STATUS_PENDENCIA:
        raise ValueError(f"status inválido: {status}")
    if not empresa_id and not (cliente_avulso or "").strip():
        raise ValueError("informe empresa_id OU cliente_avulso")
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO pendencias (
                 empresa_id, cliente_avulso, assunto, descricao,
                 prioridade, status,
                 data_inicio, data_limite, dias_alerta, resolvida
               ) VALUES (?, ?, ?, ?, ?, ?,
                         COALESCE(?, date('now','localtime')),
                         ?, ?, ?)""",
            (empresa_id,
             (cliente_avulso or "").strip() or None,
             assunto.strip(),
             (descricao or "").strip() or None,
             prioridade, status,
             data_inicio, data_limite, int(dias_alerta),
             1 if status in STATUS_PENDENCIA_FECHADA else 0),
        )
        pid = cur.lastrowid
        conn.execute(
            """INSERT INTO pendencia_movimentos (pendencia_id, tipo, texto)
               VALUES (?, 'status', ?)""",
            (pid, f"Pendência aberta como {status}."),
        )
        conn.commit()
    return pid


def adicionar_movimento_pendencia(
    pendencia_id: int,
    texto: str,
    *,
    tipo: str = "nota",
) -> int:
    """Adiciona uma movimentação (nota/status/contato/retorno) e atualiza
    `ultima_atualizacao` da pendência. Retorna o id do movimento."""
    if tipo not in TIPOS_MOVIMENTO_PENDENCIA:
        raise ValueError(f"tipo inválido: {tipo}")
    if not (texto or "").strip():
        raise ValueError("texto vazio")
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO pendencia_movimentos (pendencia_id, tipo, texto)
               VALUES (?, ?, ?)""",
            (pendencia_id, tipo, texto.strip()),
        )
        mid = cur.lastrowid
        conn.execute(
            """UPDATE pendencias
                  SET ultima_atualizacao = datetime('now','localtime'),
                      atualizado_em = datetime('now','localtime')
                WHERE id = ?""",
            (pendencia_id,),
        )
        conn.commit()
    return mid


def atualizar_status_pendencia(
    pendencia_id: int,
    novo_status: str,
    *,
    observacao: str | None = None,
) -> bool:
    if novo_status not in STATUS_PENDENCIA:
        raise ValueError(f"status inválido: {novo_status}")
    fechada = 1 if novo_status in STATUS_PENDENCIA_FECHADA else 0
    with get_conn() as conn:
        cur = conn.execute(
            """UPDATE pendencias
                  SET status = ?, resolvida = ?,
                      ultima_atualizacao = datetime('now','localtime'),
                      atualizado_em = datetime('now','localtime')
                WHERE id = ?""",
            (novo_status, fechada, pendencia_id),
        )
        if cur.rowcount > 0:
            txt = f"Status: {novo_status}"
            if observacao:
                txt += f" — {observacao.strip()}"
            conn.execute(
                """INSERT INTO pendencia_movimentos (pendencia_id, tipo, texto)
                   VALUES (?, 'status', ?)""",
                (pendencia_id, txt),
            )
        conn.commit()
        return cur.rowcount > 0


def resolver_pendencia(pendencia_id: int, observacao: str | None = None) -> bool:
    return atualizar_status_pendencia(
        pendencia_id, "Resolvida", observacao=observacao
    )


def excluir_pendencia(pendencia_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM pendencias WHERE id = ?", (pendencia_id,))
        conn.commit()
        return cur.rowcount > 0


def atualizar_pendencia(pendencia_id: int, **campos) -> bool:
    """Atualiza campos arbitrários (assunto, descricao, prioridade,
    data_limite, dias_alerta)."""
    permitidos = {"assunto", "descricao", "prioridade",
                  "data_limite", "dias_alerta"}
    sets = {k: v for k, v in campos.items() if k in permitidos}
    if not sets:
        return False
    if "prioridade" in sets and sets["prioridade"] not in PRIORIDADES_PENDENCIA:
        raise ValueError(f"prioridade inválida: {sets['prioridade']}")
    sql = ", ".join(f"{k} = ?" for k in sets)
    params = list(sets.values()) + [pendencia_id]
    with get_conn() as conn:
        cur = conn.execute(
            f"UPDATE pendencias SET {sql}, "
            f"atualizado_em = datetime('now','localtime') WHERE id = ?",
            params,
        )
        conn.commit()
        return cur.rowcount > 0


def listar_pendencias(
    *,
    apenas_abertas: bool = True,
    status: str | None = None,
    prioridade: str | None = None,
    empresa_id: int | None = None,
    somente_atrasadas: bool = False,
) -> list[dict]:
    """Lista pendências enriquecidas com:
    - razao_social
    - dias_parado (julian agora - ultima_atualizacao)
    - dias_para_prazo (julian data_limite - agora; negativo = vencido)
    - alerta ('🟢' | '🟡' | '🔴')
    """
    sql = """
        SELECT p.*,
               COALESCE(e.razao_social, p.cliente_avulso) AS razao_social,
               e.cnpj,
               CASE WHEN p.empresa_id IS NULL THEN 1 ELSE 0 END AS is_avulso,
               CAST(julianday('now') - julianday(p.ultima_atualizacao) AS INTEGER) AS dias_parado,
               CASE WHEN p.data_limite IS NULL THEN NULL
                    ELSE CAST(julianday(p.data_limite) - julianday('now') AS INTEGER)
               END AS dias_para_prazo
          FROM pendencias p
          LEFT JOIN empresas e ON e.id = p.empresa_id
         WHERE 1=1
    """
    params: list = []
    if apenas_abertas:
        sql += " AND p.resolvida = 0"
    if status:
        sql += " AND p.status = ?"
        params.append(status)
    if prioridade:
        sql += " AND p.prioridade = ?"
        params.append(prioridade)
    if empresa_id:
        sql += " AND p.empresa_id = ?"
        params.append(empresa_id)
    sql += """
        ORDER BY CASE p.prioridade
                   WHEN 'Alta' THEN 0
                   WHEN 'Média' THEN 1
                   WHEN 'Baixa' THEN 2
                   ELSE 3
                 END,
                 dias_parado DESC
    """
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    out = []
    for r in rows:
        atrasada = (r["dias_para_prazo"] is not None and r["dias_para_prazo"] < 0)
        parada = r["dias_parado"] >= r["dias_alerta"]
        if somente_atrasadas and not (atrasada or parada):
            continue
        if atrasada or parada:
            r["alerta"] = "🔴" if atrasada else "🟡"
        else:
            r["alerta"] = "🟢"
        out.append(r)
    return out


def buscar_pendencia(pendencia_id: int) -> dict | None:
    with get_conn() as conn:
        r = conn.execute(
            """SELECT p.*,
                      COALESCE(e.razao_social, p.cliente_avulso) AS razao_social,
                      e.cnpj
                 FROM pendencias p
                 LEFT JOIN empresas e ON e.id = p.empresa_id
                WHERE p.id = ?""",
            (pendencia_id,),
        ).fetchone()
        return dict(r) if r else None


def listar_movimentos_pendencia(pendencia_id: int) -> list[dict]:
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            """SELECT * FROM pendencia_movimentos
                WHERE pendencia_id = ?
                ORDER BY id DESC""",
            (pendencia_id,),
        ).fetchall()]


def pendencias_em_alerta() -> list[dict]:
    """Retorna pendências abertas que merecem alerta:
    - prazo vencido (data_limite < hoje), OU
    - paradas há mais que dias_alerta (sem movimento).
    """
    return listar_pendencias(apenas_abertas=True, somente_atrasadas=True)


def estatisticas_pendencias() -> dict:
    with get_conn() as conn:
        total_aberta = conn.execute(
            "SELECT COUNT(*) AS n FROM pendencias WHERE resolvida = 0"
        ).fetchone()["n"]
        total_resolv = conn.execute(
            "SELECT COUNT(*) AS n FROM pendencias WHERE resolvida = 1"
        ).fetchone()["n"]
        por_prio = {
            r["prioridade"]: r["n"] for r in conn.execute(
                """SELECT prioridade, COUNT(*) AS n FROM pendencias
                   WHERE resolvida = 0 GROUP BY prioridade"""
            ).fetchall()
        }
        por_status = {
            r["status"]: r["n"] for r in conn.execute(
                """SELECT status, COUNT(*) AS n FROM pendencias
                   WHERE resolvida = 0 GROUP BY status"""
            ).fetchall()
        }
    return {
        "abertas": total_aberta,
        "resolvidas": total_resolv,
        "por_prioridade": por_prio,
        "por_status": por_status,
    }


# ---------------------------------------------------------------------------
# CONSULTOR DE CNAE — helpers das bases auxiliares
# ---------------------------------------------------------------------------
def upsert_cnae_conselho(
    cnae: str, conselho_sigla: str, *,
    conselho_nome: str | None = None,
    obrigatoriedade: str = "OBRIGATORIO",
    tipo_registro: str | None = None,  # INSCRICAO_PJ / RT_OBRIGATORIO / AMBOS
    observacao: str | None = None,
    fonte: str | None = None,
) -> None:
    with get_conn() as conn:
        existente = conn.execute(
            "SELECT id FROM cnae_conselho WHERE cnae=? AND conselho_sigla=?",
            (cnae, conselho_sigla),
        ).fetchone()
        if existente:
            conn.execute(
                """UPDATE cnae_conselho SET
                     conselho_nome = COALESCE(?, conselho_nome),
                     obrigatoriedade = ?,
                     tipo_registro = COALESCE(?, tipo_registro),
                     observacao = COALESCE(?, observacao),
                     fonte = COALESCE(?, fonte),
                     atualizado_em = datetime('now','localtime')
                   WHERE id = ?""",
                (conselho_nome, obrigatoriedade, tipo_registro,
                 observacao, fonte, existente["id"]),
            )
        else:
            conn.execute(
                """INSERT INTO cnae_conselho
                     (cnae, conselho_sigla, conselho_nome, obrigatoriedade,
                      tipo_registro, observacao, fonte)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (cnae, conselho_sigla, conselho_nome, obrigatoriedade,
                 tipo_registro, observacao, fonte),
            )
        conn.commit()


# ---- Outros registros (CTF/IBAMA, MAPA, INMETRO, etc.) ----
def upsert_cnae_outro_registro(
    cnae: str, orgao: str, *,
    orgao_nome: str | None = None,
    categoria: str | None = None,
    obrigatoriedade: str = "OBRIGATORIO",
    observacao: str | None = None,
    fonte: str | None = None,
) -> None:
    with get_conn() as conn:
        existente = conn.execute(
            "SELECT id FROM cnae_outros_registros WHERE cnae=? AND orgao=?",
            (cnae, orgao),
        ).fetchone()
        if existente:
            conn.execute(
                """UPDATE cnae_outros_registros SET
                     orgao_nome = COALESCE(?, orgao_nome),
                     categoria = COALESCE(?, categoria),
                     obrigatoriedade = ?,
                     observacao = COALESCE(?, observacao),
                     fonte = COALESCE(?, fonte),
                     atualizado_em = datetime('now','localtime')
                   WHERE id = ?""",
                (orgao_nome, categoria, obrigatoriedade,
                 observacao, fonte, existente["id"]),
            )
        else:
            conn.execute(
                """INSERT INTO cnae_outros_registros
                     (cnae, orgao, orgao_nome, categoria, obrigatoriedade,
                      observacao, fonte)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (cnae, orgao, orgao_nome, categoria, obrigatoriedade,
                 observacao, fonte),
            )
        conn.commit()


def listar_outros_registros_cnae(cnae: str) -> list[dict]:
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM cnae_outros_registros WHERE cnae = ? ORDER BY orgao",
            (cnae,),
        ).fetchall()]


def upsert_cnae_habilitacao_profissional(
    cnae: str,
    atividade_gatilho: str,
    quem_executa: str,
    *,
    conselho_sigla: str | None = None,
    nivel_risco: str = "ALTO",
    fonte: str | None = None,
    observacao: str | None = None,
) -> None:
    """Registra que CERTA atividade dentro do CNAE exige profissional
    habilitado, mesmo que o CNAE em si não obrigue registro da PJ.

    Exemplo:
        upsert_cnae_habilitacao_profissional(
            cnae="9602-5/02",
            atividade_gatilho="aplicação de toxina botulínica e preenchimento",
            quem_executa="médico (CRM); enfermeiro habilitado (COREN); "
                         "odontólogo (CRO) em região buco-maxilo-facial; "
                         "biomédico esteta (CRBM) com habilitação específica",
            conselho_sigla="CRM",
            nivel_risco="ALTO",
            fonte="CFM Resolução 2.219/2018; Lei 12.842/2013",
            observacao="A clínica não precisa ter inscrição PJ em conselho, "
                       "mas o procedimento só pode ser executado por "
                       "profissional habilitado.",
        )
    """
    cnae = (cnae or "").strip()
    with get_conn() as conn:
        existente = conn.execute(
            """SELECT id FROM cnae_habilitacao_profissional
                WHERE cnae = ? AND atividade_gatilho = ?""",
            (cnae, atividade_gatilho),
        ).fetchone()
        if existente:
            conn.execute(
                """UPDATE cnae_habilitacao_profissional SET
                     conselho_sigla = COALESCE(?, conselho_sigla),
                     quem_executa = ?,
                     nivel_risco = ?,
                     fonte = COALESCE(?, fonte),
                     observacao = COALESCE(?, observacao),
                     atualizado_em = datetime('now', 'localtime')
                   WHERE id = ?""",
                (conselho_sigla, quem_executa, nivel_risco,
                 fonte, observacao, existente["id"]),
            )
        else:
            conn.execute(
                """INSERT INTO cnae_habilitacao_profissional
                     (cnae, atividade_gatilho, conselho_sigla,
                      quem_executa, nivel_risco, fonte, observacao)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (cnae, atividade_gatilho, conselho_sigla,
                 quem_executa, nivel_risco, fonte, observacao),
            )
        conn.commit()


def listar_habilitacoes_cnae(cnae: str) -> list[dict]:
    """Retorna lista de atividades CONDICIONAIS que exigem profissional
    habilitado para este CNAE.
    """
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            """SELECT * FROM cnae_habilitacao_profissional
                WHERE cnae = ?
                ORDER BY CASE nivel_risco
                              WHEN 'ALTO' THEN 0
                              WHEN 'MEDIO' THEN 1
                              ELSE 2
                         END,
                         atividade_gatilho""",
            (cnae,),
        ).fetchall()]


# =====================================================================
# SOLICITAÇÕES DE CADASTRO (aprovação manual antes de criar no Supabase)
# =====================================================================
def criar_solicitacao_cadastro(
    nome: str, email: str,
    *, funcao: str | None = None,
    justificativa: str | None = None,
) -> int:
    """Salva uma solicitação de cadastro. Retorna o id da solicitação.
    Levanta ValueError se já existe solicitação ativa pro mesmo email.
    """
    email = email.strip().lower()
    nome = nome.strip()
    if not nome or not email:
        raise ValueError("Nome e email são obrigatórios.")
    with get_conn() as conn:
        existe = conn.execute(
            "SELECT id, status FROM solicitacoes_cadastro WHERE email = ?",
            (email,),
        ).fetchone()
        if existe:
            if existe["status"] == "pendente":
                raise ValueError(
                    "Já existe uma solicitação pendente para este email."
                )
            if existe["status"] == "aprovada":
                raise ValueError(
                    "Este email já foi aprovado. Tente fazer login ou "
                    "use 'Esqueci a senha'."
                )
            # rejeitada → permite tentar de novo (apaga a antiga)
            conn.execute(
                "DELETE FROM solicitacoes_cadastro WHERE id = ?",
                (existe["id"],),
            )
        cur = conn.execute(
            """INSERT INTO solicitacoes_cadastro
                 (nome, email, funcao, justificativa, status)
                 VALUES (?, ?, ?, ?, 'pendente')""",
            (nome, email, funcao, justificativa),
        )
        return cur.lastrowid


def listar_solicitacoes_cadastro(
    status: str | None = "pendente",
) -> list[dict]:
    """Lista solicitações de cadastro. status=None retorna todas."""
    sql = "SELECT * FROM solicitacoes_cadastro"
    params: tuple = ()
    if status:
        sql += " WHERE status = ?"
        params = (status,)
    sql += " ORDER BY criado_em DESC"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def atualizar_solicitacao_cadastro(
    solicitacao_id: int, novo_status: str,
    *, revisado_por: str | None = None,
    observacao: str | None = None,
) -> None:
    """Atualiza status da solicitação (aprovada/rejeitada/criada)."""
    if novo_status not in {"pendente", "aprovada", "rejeitada", "criada"}:
        raise ValueError(f"Status inválido: {novo_status}")
    with get_conn() as conn:
        conn.execute(
            """UPDATE solicitacoes_cadastro SET
                 status = ?,
                 revisado_em = datetime('now', 'localtime'),
                 revisado_por = COALESCE(?, revisado_por),
                 observacao_admin = COALESCE(?, observacao_admin)
                WHERE id = ?""",
            (novo_status, revisado_por, observacao, solicitacao_id),
        )


def contar_solicitacoes_pendentes() -> int:
    with get_conn() as conn:
        r = conn.execute(
            "SELECT COUNT(*) AS c FROM solicitacoes_cadastro "
            "WHERE status = 'pendente'"
        ).fetchone()
        return int(dict(r)["c"]) if r else 0


# ====================================================================
# Telegram por usuário
# ====================================================================
def definir_telegram_usuario(
    email: str, chat_id: str, *, nome: str | None = None,
    ativo: bool = True,
) -> None:
    """Upsert do chat_id do Telegram para o email do usuário logado.

    Se o usuário já existir, atualiza chat_id/nome/ativo.
    O `email` é a chave primária e bate com o email do Supabase Auth.
    """
    email = (email or "").strip().lower()
    chat_id = (chat_id or "").strip()
    if not email or not chat_id:
        raise ValueError("Email e chat_id são obrigatórios.")
    with get_conn() as conn:
        existe = conn.execute(
            "SELECT email FROM usuarios_telegram WHERE email = ?",
            (email,),
        ).fetchone()
        if existe:
            conn.execute(
                """UPDATE usuarios_telegram SET
                       chat_id = ?,
                       nome = COALESCE(?, nome),
                       ativo = ?,
                       atualizado_em = datetime('now', 'localtime')
                     WHERE email = ?""",
                (chat_id, nome, 1 if ativo else 0, email),
            )
        else:
            conn.execute(
                """INSERT INTO usuarios_telegram
                     (email, chat_id, nome, ativo)
                     VALUES (?, ?, ?, ?)""",
                (email, chat_id, nome, 1 if ativo else 0),
            )


def buscar_telegram_usuario(email: str) -> dict | None:
    email = (email or "").strip().lower()
    if not email:
        return None
    with get_conn() as conn:
        r = conn.execute(
            "SELECT * FROM usuarios_telegram WHERE email = ?",
            (email,),
        ).fetchone()
        return dict(r) if r else None


def desativar_telegram_usuario(email: str) -> None:
    email = (email or "").strip().lower()
    if not email:
        return
    with get_conn() as conn:
        conn.execute(
            "UPDATE usuarios_telegram SET ativo = 0, "
            "atualizado_em = datetime('now', 'localtime') "
            "WHERE email = ?",
            (email,),
        )


def listar_telegrams_ativos() -> list[dict]:
    """Devolve a lista de usuários ativos com chat_id configurado.

    Usado pelo notifier pra fazer broadcast: cada usuário ativo recebe
    os alertas no Telegram dele.
    """
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT email, chat_id, nome FROM usuarios_telegram "
            "WHERE ativo = 1 AND chat_id IS NOT NULL AND chat_id <> '' "
            "ORDER BY email"
        ).fetchall()
        return [dict(r) for r in rows]


# ====================================================================
# GESTTA JWT por usuário
# ====================================================================
def definir_gestta_jwt_usuario(
    email: str, jwt: str, *,
    nome: str | None = None,
    gestta_user: str | None = None,
    gestta_company: str | None = None,
    ativo: bool = True,
) -> None:
    """Upsert do JWT GESTTA para o email do usuário logado.

    O `email` é a chave primária e bate com o email do Supabase Auth.
    Os campos `gestta_user`/`gestta_company` são metadados extraídos do
    payload do JWT (via jwt_info), úteis pra mostrar na UI quem é a
    pessoa "dentro do GESTTA" sem decodificar de novo.
    """
    email = (email or "").strip().lower()
    jwt = (jwt or "").strip()
    if not email or not jwt:
        raise ValueError("Email e JWT são obrigatórios.")
    with get_conn() as conn:
        existe = conn.execute(
            "SELECT email FROM usuarios_gestta_jwt WHERE email = ?",
            (email,),
        ).fetchone()
        if existe:
            conn.execute(
                """UPDATE usuarios_gestta_jwt SET
                       jwt = ?,
                       nome = COALESCE(?, nome),
                       gestta_user = COALESCE(?, gestta_user),
                       gestta_company = COALESCE(?, gestta_company),
                       ativo = ?,
                       atualizado_em = datetime('now', 'localtime')
                     WHERE email = ?""",
                (jwt, nome, gestta_user, gestta_company,
                 1 if ativo else 0, email),
            )
        else:
            conn.execute(
                """INSERT INTO usuarios_gestta_jwt
                     (email, jwt, nome, gestta_user, gestta_company, ativo)
                     VALUES (?, ?, ?, ?, ?, ?)""",
                (email, jwt, nome, gestta_user, gestta_company,
                 1 if ativo else 0),
            )


def buscar_gestta_jwt_usuario(email: str) -> dict | None:
    email = (email or "").strip().lower()
    if not email:
        return None
    with get_conn() as conn:
        r = conn.execute(
            "SELECT * FROM usuarios_gestta_jwt WHERE email = ?",
            (email,),
        ).fetchone()
        return dict(r) if r else None


def desativar_gestta_jwt_usuario(email: str) -> None:
    email = (email or "").strip().lower()
    if not email:
        return
    with get_conn() as conn:
        conn.execute(
            "UPDATE usuarios_gestta_jwt SET ativo = 0, "
            "atualizado_em = datetime('now', 'localtime') "
            "WHERE email = ?",
            (email,),
        )


def listar_jwts_gestta_ativos() -> list[dict]:
    """Lista todos os JWTs ativos. Usado pra mostrar no painel quem
    está com GESTTA pessoal configurado."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT email, nome, gestta_user, gestta_company, "
            "atualizado_em FROM usuarios_gestta_jwt "
            "WHERE ativo = 1 ORDER BY email"
        ).fetchall()
        return [dict(r) for r in rows]


# ====================================================================
# Cache de consulta CNPJ
# ====================================================================
def cache_cnpj_get(cnpj: str, max_idade_dias: int = 30) -> dict | None:
    """Lê o cache de CNPJ se for recente. Retorna None se não houver."""
    import json
    cnpj = "".join(c for c in (cnpj or "") if c.isdigit())
    if not cnpj:
        return None
    with get_conn() as conn:
        r = conn.execute(
            "SELECT dados_json, consultado_em FROM consultas_cnpj_cache "
            "WHERE cnpj = ?",
            (cnpj,),
        ).fetchone()
        if not r:
            return None
        # Checa idade
        from datetime import datetime, timedelta
        try:
            quando = datetime.fromisoformat(
                str(dict(r)["consultado_em"]).replace(" ", "T"))
        except Exception:
            return None
        if datetime.now() - quando > timedelta(days=max_idade_dias):
            return None
        try:
            return json.loads(dict(r)["dados_json"])
        except Exception:
            return None


def cache_cnpj_set(cnpj: str, dados: dict) -> None:
    """Grava/atualiza o cache de uma consulta CNPJ."""
    import json
    cnpj = "".join(c for c in (cnpj or "") if c.isdigit())
    if not cnpj or not dados:
        return
    payload = json.dumps(dados, ensure_ascii=False)
    fonte = dados.get("fonte", "")
    with get_conn() as conn:
        existe = conn.execute(
            "SELECT cnpj FROM consultas_cnpj_cache WHERE cnpj = ?",
            (cnpj,),
        ).fetchone()
        if existe:
            conn.execute(
                "UPDATE consultas_cnpj_cache SET dados_json = ?, "
                "consultado_em = datetime('now', 'localtime'), fonte = ? "
                "WHERE cnpj = ?",
                (payload, fonte, cnpj),
            )
        else:
            conn.execute(
                "INSERT INTO consultas_cnpj_cache (cnpj, dados_json, fonte) "
                "VALUES (?, ?, ?)",
                (cnpj, payload, fonte),
            )


# ====================================================================
# Catálogo de órgãos oficiais
# ====================================================================
def upsert_orgao_oficial(
    sigla: str, nome: str, *,
    categoria: str | None = None,
    esfera: str | None = None,
    uf: str | None = None,
    municipio: str | None = None,
    descricao: str | None = None,
    link_consulta: str | None = None,
    link_cadastro: str | None = None,
    contato: str | None = None,
    observacoes: str | None = None,
) -> None:
    """Insere ou atualiza um órgão no catálogo (chave: sigla + uf)."""
    sigla = (sigla or "").strip().upper()
    uf_norm = (uf or "").strip().upper() or None
    if not sigla or not nome:
        raise ValueError("Sigla e nome são obrigatórios.")
    with get_conn() as conn:
        existe = conn.execute(
            "SELECT id FROM orgaos_oficiais WHERE sigla = ? AND "
            "COALESCE(uf, '') = COALESCE(?, '')",
            (sigla, uf_norm),
        ).fetchone()
        if existe:
            conn.execute(
                """UPDATE orgaos_oficiais SET
                       nome = ?, categoria = ?, esfera = ?,
                       municipio = ?, descricao = ?,
                       link_consulta = ?, link_cadastro = ?,
                       contato = ?, observacoes = ?,
                       atualizado_em = datetime('now', 'localtime')
                     WHERE id = ?""",
                (nome, categoria, esfera, municipio, descricao,
                 link_consulta, link_cadastro, contato, observacoes,
                 dict(existe)["id"]),
            )
        else:
            conn.execute(
                """INSERT INTO orgaos_oficiais
                     (sigla, nome, categoria, esfera, uf, municipio,
                      descricao, link_consulta, link_cadastro, contato,
                      observacoes)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (sigla, nome, categoria, esfera, uf_norm, municipio,
                 descricao, link_consulta, link_cadastro, contato,
                 observacoes),
            )


def buscar_orgao(sigla: str, uf: str | None = None) -> dict | None:
    sigla = (sigla or "").strip().upper()
    uf_norm = (uf or "").strip().upper() or None
    if not sigla:
        return None
    with get_conn() as conn:
        r = conn.execute(
            "SELECT * FROM orgaos_oficiais WHERE sigla = ? AND "
            "COALESCE(uf, '') = COALESCE(?, '')",
            (sigla, uf_norm),
        ).fetchone()
        if r:
            return dict(r)
        # Fallback: busca sem UF (versão federal genérica)
        if uf_norm:
            r2 = conn.execute(
                "SELECT * FROM orgaos_oficiais WHERE sigla = ? AND "
                "uf IS NULL LIMIT 1",
                (sigla,),
            ).fetchone()
            return dict(r2) if r2 else None
        return None


# ====================================================================
# Base de regras oficiais (resposta determinística por CNAE × órgão)
# ====================================================================
OBRIGATORIEDADE_SIM = "sim"
OBRIGATORIEDADE_NAO = "nao"
OBRIGATORIEDADE_CONDICIONAL = "condicional"

OBRIGATORIEDADE_VALORES = {
    OBRIGATORIEDADE_SIM,
    OBRIGATORIEDADE_NAO,
    OBRIGATORIEDADE_CONDICIONAL,
}


def upsert_regra_oficial(
    cnae: str, orgao_sigla: str, obrigatoriedade: str,
    *, orgao_uf: str | None = None,
    condicoes_obrigatorio: str | None = None,
    condicoes_dispensa: str | None = None,
    observacoes: str | None = None,
    base_legal: str | None = None,
    link_lei: str | None = None,
    autor: str | None = None,
    revisor: str | None = None,
) -> None:
    """Cadastra/atualiza a regra OFICIAL de um CNAE pra um órgão.

    Esta tabela é o que dá CERTEZA ao sistema. Sem entrada aqui, o
    checklist mostra apenas "verificar manualmente". Com entrada,
    mostra a resposta determinística com base legal.
    """
    cnae_norm = _normalizar_cnae(cnae)
    sig = (orgao_sigla or "").strip().upper()
    uf_norm = (orgao_uf or "").strip().upper() or None
    obg = (obrigatoriedade or "").strip().lower()
    if not cnae_norm or not sig:
        raise ValueError("CNAE e órgão são obrigatórios.")
    if obg not in OBRIGATORIEDADE_VALORES:
        raise ValueError(
            f"obrigatoriedade deve ser 'sim'|'nao'|'condicional', "
            f"recebido: {obg!r}"
        )
    if obg == OBRIGATORIEDADE_CONDICIONAL and not (
            condicoes_obrigatorio or condicoes_dispensa):
        raise ValueError(
            "Regra condicional precisa descrever pelo menos uma das "
            "condições (obrigatório ou dispensa)."
        )
    with get_conn() as conn:
        existe = conn.execute(
            "SELECT id FROM cnae_regra_oficial WHERE "
            "cnae = ? AND orgao_sigla = ? AND "
            "COALESCE(orgao_uf, '') = COALESCE(?, '')",
            (cnae_norm, sig, uf_norm),
        ).fetchone()
        if existe:
            conn.execute(
                """UPDATE cnae_regra_oficial SET
                       obrigatoriedade = ?,
                       condicoes_obrigatorio = ?,
                       condicoes_dispensa = ?,
                       observacoes = ?,
                       base_legal = ?,
                       link_lei = ?,
                       data_revisao = datetime('now', 'localtime'),
                       revisor = COALESCE(?, revisor)
                     WHERE id = ?""",
                (obg, condicoes_obrigatorio, condicoes_dispensa,
                 observacoes, base_legal, link_lei,
                 revisor or autor, dict(existe)["id"]),
            )
        else:
            conn.execute(
                """INSERT INTO cnae_regra_oficial
                     (cnae, orgao_sigla, orgao_uf, obrigatoriedade,
                      condicoes_obrigatorio, condicoes_dispensa,
                      observacoes, base_legal, link_lei, autor)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (cnae_norm, sig, uf_norm, obg,
                 condicoes_obrigatorio, condicoes_dispensa,
                 observacoes, base_legal, link_lei, autor),
            )


def buscar_regras_cnae(cnae: str) -> list[dict]:
    """Lista todas as regras oficiais cadastradas pra um CNAE."""
    cnae_norm = _normalizar_cnae(cnae)
    if not cnae_norm:
        return []
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM cnae_regra_oficial WHERE cnae = ? "
            "ORDER BY orgao_sigla, COALESCE(orgao_uf, '')",
            (cnae_norm,),
        ).fetchall()
        return [dict(r) for r in rows]


def buscar_regra_especifica(
    cnae: str, orgao_sigla: str,
    *, orgao_uf: str | None = None,
) -> dict | None:
    cnae_norm = _normalizar_cnae(cnae)
    sig = (orgao_sigla or "").strip().upper()
    uf_norm = (orgao_uf or "").strip().upper() or None
    if not cnae_norm or not sig:
        return None
    with get_conn() as conn:
        r = conn.execute(
            "SELECT * FROM cnae_regra_oficial WHERE "
            "cnae = ? AND orgao_sigla = ? AND "
            "COALESCE(orgao_uf, '') = COALESCE(?, '')",
            (cnae_norm, sig, uf_norm),
        ).fetchone()
        if r:
            return dict(r)
        # Fallback: regra federal (sem UF) quando UF específica não existe
        if uf_norm:
            r2 = conn.execute(
                "SELECT * FROM cnae_regra_oficial WHERE "
                "cnae = ? AND orgao_sigla = ? AND orgao_uf IS NULL",
                (cnae_norm, sig),
            ).fetchone()
            return dict(r2) if r2 else None
        return None


def remover_regra_oficial(
    cnae: str, orgao_sigla: str,
    *, orgao_uf: str | None = None,
) -> None:
    cnae_norm = _normalizar_cnae(cnae)
    sig = (orgao_sigla or "").strip().upper()
    uf_norm = (orgao_uf or "").strip().upper() or None
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM cnae_regra_oficial WHERE "
            "cnae = ? AND orgao_sigla = ? AND "
            "COALESCE(orgao_uf, '') = COALESCE(?, '')",
            (cnae_norm, sig, uf_norm),
        )


def extrair_cnaes_da_carteira() -> list[dict]:
    """Escaneia toda a base local procurando CNAEs reais da carteira
    e devolve ranking por frequência. Fontes:

      1. processo_cnaes  → CNAEs vinculados a processos REDESIM
      2. consultas_cnpj_cache → CNAEs vindos da Receita (BrasilAPI)

    Retorna:
      [
        {"cnae": "4711-3/02", "ocorrencias": 17,
         "exemplos_cnpj": ["12345678000190", ...]},
        ...
      ]
    """
    import json
    contagem: dict[str, dict] = {}

    with get_conn() as conn:
        # Fonte 1: CNAEs dos processos REDESIM
        try:
            rows = conn.execute(
                "SELECT cnae, COUNT(*) AS n FROM processo_cnaes "
                "GROUP BY cnae"
            ).fetchall()
            for r in rows:
                c = _normalizar_cnae(dict(r)["cnae"])
                if not c:
                    continue
                contagem.setdefault(c, {
                    "cnae": c, "ocorrencias": 0,
                    "exemplos_cnpj": [], "fontes": set()
                })
                contagem[c]["ocorrencias"] += int(dict(r)["n"])
                contagem[c]["fontes"].add("processo_redesim")
        except Exception:
            pass

        # Fonte 2: CNAEs do cache de consultas CNPJ
        try:
            rows = conn.execute(
                "SELECT cnpj, dados_json FROM consultas_cnpj_cache"
            ).fetchall()
            for r in rows:
                d = dict(r)
                cnpj = d.get("cnpj", "")
                try:
                    dados = json.loads(d.get("dados_json") or "{}")
                except Exception:
                    continue
                cnaes_aqui = []
                pr = (dados.get("cnae_principal") or {}).get("codigo")
                if pr:
                    cnaes_aqui.append(_normalizar_cnae(pr))
                for sec in (dados.get("cnaes_secundarios") or []):
                    c = _normalizar_cnae(sec.get("codigo") or "")
                    if c:
                        cnaes_aqui.append(c)
                for c in cnaes_aqui:
                    if not c:
                        continue
                    contagem.setdefault(c, {
                        "cnae": c, "ocorrencias": 0,
                        "exemplos_cnpj": [], "fontes": set()
                    })
                    contagem[c]["ocorrencias"] += 1
                    if (cnpj and
                            cnpj not in contagem[c]["exemplos_cnpj"] and
                            len(contagem[c]["exemplos_cnpj"]) < 5):
                        contagem[c]["exemplos_cnpj"].append(cnpj)
                    contagem[c]["fontes"].add("consulta_cnpj")
        except Exception:
            pass

    # Ordena por ocorrências desc
    resultado = sorted(
        contagem.values(),
        key=lambda x: (-x["ocorrencias"], x["cnae"]),
    )
    # Converte sets em listas (json-friendly)
    for r in resultado:
        r["fontes"] = sorted(r["fontes"])
    return resultado


def listar_cnaes_sem_regra(
    limite: int = 50, ranqueio: list[str] | None = None,
) -> list[dict]:
    """Lista CNAEs SEM regra cadastrada.

    Se `ranqueio` for fornecido (lista de CNAEs ordenada por
    importância), os primeiros aparecem primeiro. Caso contrário,
    ordena por código.
    """
    with get_conn() as conn:
        # Cnaes em alguma base regulatória local mas SEM regra oficial
        rows = conn.execute(
            """
            SELECT DISTINCT cnae FROM (
              SELECT cnae FROM cnae_conselho
              UNION SELECT cnae FROM cnae_anvisa
              UNION SELECT cnae FROM cnae_ambiental
              UNION SELECT cnae FROM cnae_outro_registro
              UNION SELECT cnae FROM cnae_habilitacao_profissional
            ) src
            WHERE cnae NOT IN (SELECT cnae FROM cnae_regra_oficial)
            """
        ).fetchall()
        candidatos = [dict(r)["cnae"] for r in rows]

    if ranqueio:
        # Coloca os ranqueados primeiro (na ordem), depois o resto
        seti = set(candidatos)
        ordenado = [c for c in ranqueio if c in seti]
        resto = sorted([c for c in candidatos if c not in set(ranqueio)])
        candidatos = ordenado + resto
    else:
        candidatos = sorted(candidatos)

    return [{"cnae": c} for c in candidatos[:limite]]


STATUS_VERIFICACAO_OK = "verificado"
STATUS_VERIFICACAO_NA = "nao_se_aplica"
STATUS_VERIFICACAO_PENDENTE = "pendente"
STATUS_VERIFICACAO_PROBLEMA = "problema"

STATUS_VERIFICACAO_VALIDOS = {
    STATUS_VERIFICACAO_OK,
    STATUS_VERIFICACAO_NA,
    STATUS_VERIFICACAO_PENDENTE,
    STATUS_VERIFICACAO_PROBLEMA,
}


def registrar_verificacao_orgao(
    cnpj: str, orgao_sigla: str, status: str,
    *, orgao_uf: str | None = None,
    verificado_por: str | None = None,
    observacao: str | None = None,
) -> None:
    """Marca/atualiza o status de verificação da empresa em um órgão.

    status:
      - 'verificado'    → está OK no órgão (cadastro/licença ativo)
      - 'nao_se_aplica' → confirmamos que não precisa pra essa empresa
      - 'problema'      → encontramos pendência/irregularidade
      - 'pendente'      → reset (volta a aparecer no checklist)
    """
    cnpj_norm = "".join(c for c in (cnpj or "") if c.isdigit())
    sig = (orgao_sigla or "").strip().upper()
    uf_norm = (orgao_uf or "").strip().upper() or None
    if not cnpj_norm or not sig:
        raise ValueError("CNPJ e órgão são obrigatórios.")
    if status not in STATUS_VERIFICACAO_VALIDOS:
        raise ValueError(f"Status inválido: {status}")
    with get_conn() as conn:
        existe = conn.execute(
            "SELECT id FROM empresa_orgao_verificacao WHERE "
            "cnpj = ? AND orgao_sigla = ? AND "
            "COALESCE(orgao_uf, '') = COALESCE(?, '')",
            (cnpj_norm, sig, uf_norm),
        ).fetchone()
        if existe:
            conn.execute(
                """UPDATE empresa_orgao_verificacao SET
                       status = ?, observacao = ?,
                       verificado_por = COALESCE(?, verificado_por),
                       verificado_em = datetime('now', 'localtime')
                     WHERE id = ?""",
                (status, observacao, verificado_por,
                 dict(existe)["id"]),
            )
        else:
            conn.execute(
                """INSERT INTO empresa_orgao_verificacao
                     (cnpj, orgao_sigla, orgao_uf, status, observacao,
                      verificado_por)
                     VALUES (?, ?, ?, ?, ?, ?)""",
                (cnpj_norm, sig, uf_norm, status, observacao,
                 verificado_por),
            )


def buscar_verificacao_orgao(
    cnpj: str, orgao_sigla: str,
    *, orgao_uf: str | None = None,
) -> dict | None:
    """Retorna a última verificação registrada (ou None)."""
    cnpj_norm = "".join(c for c in (cnpj or "") if c.isdigit())
    sig = (orgao_sigla or "").strip().upper()
    uf_norm = (orgao_uf or "").strip().upper() or None
    if not cnpj_norm or not sig:
        return None
    with get_conn() as conn:
        r = conn.execute(
            "SELECT * FROM empresa_orgao_verificacao WHERE "
            "cnpj = ? AND orgao_sigla = ? AND "
            "COALESCE(orgao_uf, '') = COALESCE(?, '')",
            (cnpj_norm, sig, uf_norm),
        ).fetchone()
        return dict(r) if r else None


def listar_verificacoes_empresa(cnpj: str) -> dict[str, dict]:
    """Retorna mapa {orgao_sigla: dados_verificacao} pra essa empresa.

    Útil pra enriquecer o checklist sem fazer N queries (uma por item).
    """
    cnpj_norm = "".join(c for c in (cnpj or "") if c.isdigit())
    if not cnpj_norm:
        return {}
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM empresa_orgao_verificacao WHERE cnpj = ?",
            (cnpj_norm,),
        ).fetchall()
        return {dict(r)["orgao_sigla"]: dict(r) for r in rows}


def remover_verificacao_orgao(
    cnpj: str, orgao_sigla: str,
    *, orgao_uf: str | None = None,
) -> None:
    """Reseta a verificação (volta o item pra 'pendente' no checklist)."""
    cnpj_norm = "".join(c for c in (cnpj or "") if c.isdigit())
    sig = (orgao_sigla or "").strip().upper()
    uf_norm = (orgao_uf or "").strip().upper() or None
    if not cnpj_norm or not sig:
        return
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM empresa_orgao_verificacao WHERE "
            "cnpj = ? AND orgao_sigla = ? AND "
            "COALESCE(orgao_uf, '') = COALESCE(?, '')",
            (cnpj_norm, sig, uf_norm),
        )


def listar_orgaos(categoria: str | None = None,
                  esfera: str | None = None) -> list[dict]:
    sql = "SELECT * FROM orgaos_oficiais WHERE 1=1"
    params: list = []
    if categoria:
        sql += " AND categoria = ?"
        params.append(categoria)
    if esfera:
        sql += " AND esfera = ?"
        params.append(esfera)
    sql += " ORDER BY categoria, esfera, sigla, COALESCE(uf, '')"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]


# ====================================================================
# Cobranças DOMÍNIO (Thomson Reuters)
# ====================================================================
TIPO_COB_LICENCA_REDESIM = "LICENCA_REDESIM"
TIPO_COB_VISA            = "VISA"
TIPO_COB_AVCB            = "AVCB"
TIPO_COB_OUTRO           = "OUTRO"

# Valores informados pelo Eduardo (01/06/2026) — podem ser ajustados
# pela UI em ⚙️ Configurações
VALORES_COBRANCA_PADRAO = {
    TIPO_COB_LICENCA_REDESIM: ("Licença de Funcionamento via REDESIM", 250.0),
    TIPO_COB_VISA:            ("Vigilância Sanitária (renovação)",     600.0),
    TIPO_COB_AVCB:            ("AVCB / CLCB — Bombeiros",              500.0),
    TIPO_COB_OUTRO:           ("Outro serviço de regularização",       300.0),
}


def garantir_valores_cobranca_padrao() -> None:
    """Garante que a tabela tem os valores default. Idempotente."""
    with get_conn() as conn:
        for tipo, (desc, valor) in VALORES_COBRANCA_PADRAO.items():
            ja = conn.execute(
                "SELECT tipo_servico FROM tabela_valores_cobranca "
                "WHERE tipo_servico = ?",
                (tipo,),
            ).fetchone()
            if not ja:
                conn.execute(
                    "INSERT INTO tabela_valores_cobranca "
                    "(tipo_servico, descricao, valor_sugerido) "
                    "VALUES (?, ?, ?)",
                    (tipo, desc, valor),
                )


def listar_valores_cobranca() -> list[dict]:
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM tabela_valores_cobranca ORDER BY tipo_servico"
        ).fetchall()]


def atualizar_valor_cobranca(
    tipo: str, valor: float, *, descricao: str | None = None,
    atualizado_por: str | None = None,
) -> None:
    with get_conn() as conn:
        existe = conn.execute(
            "SELECT tipo_servico FROM tabela_valores_cobranca "
            "WHERE tipo_servico = ?",
            (tipo,),
        ).fetchone()
        if existe:
            conn.execute(
                "UPDATE tabela_valores_cobranca SET valor_sugerido = ?, "
                "descricao = COALESCE(?, descricao), "
                "atualizado_em = datetime('now','localtime'), "
                "atualizado_por = ? WHERE tipo_servico = ?",
                (valor, descricao, atualizado_por, tipo),
            )
        else:
            conn.execute(
                "INSERT INTO tabela_valores_cobranca "
                "(tipo_servico, descricao, valor_sugerido, atualizado_por) "
                "VALUES (?, ?, ?, ?)",
                (tipo, descricao or tipo, valor, atualizado_por),
            )


def _classificar_tipo_cobranca(
    protocolo: dict, gestta_task_nome: str | None = None,
) -> str:
    """Decide qual tipo de cobrança usar baseado no protocolo + tarefa."""
    nome = (gestta_task_nome or "").upper()
    tipo_prot = (protocolo.get("tipo") or "").upper()

    if "BOMBEIRO" in nome or "AVCB" in nome or "CLCB" in nome:
        return TIPO_COB_AVCB
    if "SANIT" in nome or "VISA" in nome or "VIGILANCIA" in nome:
        return TIPO_COB_VISA
    if "LICEN" in nome or "FUNCIONAMENTO" in nome or "REDESIM" in tipo_prot:
        return TIPO_COB_LICENCA_REDESIM
    return TIPO_COB_OUTRO


def criar_cobranca_pendente(
    *,
    cliente_nome: str,
    tipo_servico: str = TIPO_COB_LICENCA_REDESIM,
    empresa_id: int | None = None,
    protocolo_id: int | None = None,
    gestta_task_id: str | None = None,
    cliente_cnpj: str | None = None,
    descricao: str | None = None,
    valor_override: float | None = None,
    responsavel: str | None = None,
) -> int:
    """Cria uma cobrança pendente. Usa valor da tabela_valores se não
    foi passado override. Retorna o id da cobrança criada."""
    # Pega valor sugerido
    valor = valor_override
    if valor is None:
        with get_conn() as conn:
            r = conn.execute(
                "SELECT valor_sugerido FROM tabela_valores_cobranca "
                "WHERE tipo_servico = ?",
                (tipo_servico,),
            ).fetchone()
            if r:
                valor = float(dict(r)["valor_sugerido"])
        if valor is None:
            valor = VALORES_COBRANCA_PADRAO.get(
                tipo_servico,
                ("Outro", 300.0),
            )[1]

    with get_conn() as conn:
        # Anti-duplicação: se já existe cobrança pendente pra mesmo
        # protocolo, retorna o id existente
        if protocolo_id:
            ja = conn.execute(
                "SELECT id FROM cobrancas_dominio WHERE "
                "protocolo_id = ? AND status = 'pendente'",
                (protocolo_id,),
            ).fetchone()
            if ja:
                return int(dict(ja)["id"])
        if gestta_task_id:
            ja = conn.execute(
                "SELECT id FROM cobrancas_dominio WHERE "
                "gestta_task_id = ? AND status = 'pendente'",
                (gestta_task_id,),
            ).fetchone()
            if ja:
                return int(dict(ja)["id"])

        cur = conn.execute(
            """INSERT INTO cobrancas_dominio
                 (empresa_id, protocolo_id, gestta_task_id,
                  tipo_servico, cliente_nome, cliente_cnpj,
                  valor_sugerido, descricao, responsavel)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (empresa_id, protocolo_id, gestta_task_id,
             tipo_servico, cliente_nome, cliente_cnpj,
             valor, descricao, responsavel),
        )
        return cur.lastrowid


def listar_cobrancas_por_mes() -> list[dict]:
    """Agrupa cobranças lançadas por mês.

    Agregação feita em Python para funcionar igual em SQLite (dev) e
    PostgreSQL (prod), sem depender de strftime/to_char (dialeto-específicos).
    """
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT lancado_em, valor_lancado, comissao
            FROM cobrancas_dominio
            WHERE status = 'lancada'
              AND lancado_em IS NOT NULL
            """
        ).fetchall()

    grupos: dict[str, dict] = {}
    for r in rows:
        d = dict(r)
        le = d.get("lancado_em")
        if le is None:
            continue
        if hasattr(le, "year") and hasattr(le, "month"):
            ano, mes_num = le.year, le.month
        else:
            s = str(le)
            ano, mes_num = int(s[0:4]), int(s[5:7])
        mes_sort = f"{ano:04d}{mes_num:02d}"
        g = grupos.setdefault(
            mes_sort,
            {
                "mes": f"{mes_num:02d}/{ano:04d}",
                "mes_sort": mes_sort,
                "qtd": 0,
                "total_lancado": 0.0,
                "total_comissao": 0.0,
            },
        )
        g["qtd"] += 1
        g["total_lancado"] += float(d.get("valor_lancado") or 0)
        g["total_comissao"] += float(d.get("comissao") or 0)

    return sorted(
        grupos.values(), key=lambda x: x["mes_sort"], reverse=True
    )


def listar_cobrancas_pendentes(
    *, status: str | None = "pendente",
    responsavel: str | None = None,
) -> list[dict]:
    sql = "SELECT * FROM cobrancas_dominio WHERE 1=1"
    params: list = []
    if status:
        sql += " AND status = ?"
        params.append(status)
    if responsavel:
        sql += " AND responsavel = ?"
        params.append(responsavel)
    sql += " ORDER BY criado_em DESC"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]


def marcar_cobranca_lancada(
    cobranca_id: int,
    *, valor_lancado: float | None = None,
    lancado_por: str | None = None,
    observacao: str | None = None,
    comissao: float | None = None,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """UPDATE cobrancas_dominio SET
                 status = 'lancada',
                 valor_lancado = COALESCE(?, valor_sugerido),
                 lancado_em = datetime('now', 'localtime'),
                 lancado_por = ?,
                 observacao = COALESCE(?, observacao),
                 comissao = ?
               WHERE id = ?""",
            (valor_lancado, lancado_por, observacao, comissao, cobranca_id),
        )


def atualizar_comissao(cobranca_id: int, comissao) -> None:
    """Atualiza apenas a comissão de uma cobrança já lançada."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE cobrancas_dominio SET comissao = ? WHERE id = ?",
            (comissao, cobranca_id),
        )


def cancelar_cobranca(cobranca_id: int, motivo: str | None = None) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE cobrancas_dominio SET status = 'cancelada', "
            "observacao = COALESCE(?, observacao) WHERE id = ?",
            (motivo, cobranca_id),
        )


def contar_cobrancas_pendentes() -> int:
    with get_conn() as conn:
        r = conn.execute(
            "SELECT COUNT(*) AS c FROM cobrancas_dominio "
            "WHERE status = 'pendente'"
        ).fetchone()
        return int(dict(r)["c"]) if r else 0


def total_pendente_cobranca() -> float:
    with get_conn() as conn:
        r = conn.execute(
            "SELECT COALESCE(SUM(valor_sugerido), 0) AS total "
            "FROM cobrancas_dominio WHERE status = 'pendente'"
        ).fetchone()
        return float(dict(r)["total"]) if r else 0.0


def obter_jwt_gestta_efetivo(email: str | None = None) -> str:
    """Devolve o JWT GESTTA mais apropriado.

    Ordem de preferência:
      1. JWT pessoal do `email` (se ativo) — uso interativo no app
      2. Override de sessão (st.session_state["GESTTA_JWT_OVERRIDE"]) —
         útil quando o admin cola um token novo na UI sem alterar segredo
      3. Variável de ambiente GESTTA_JWT — fallback (cron diário)

    Retorna string vazia se nada estiver configurado.
    """
    # 1) JWT pessoal
    if email:
        u = buscar_gestta_jwt_usuario(email)
        if u and u.get("ativo") and (u.get("jwt") or "").strip():
            return u["jwt"].strip()

    # 2) Override de sessão (Streamlit)
    try:
        import streamlit as st
        ov = (st.session_state.get("GESTTA_JWT_OVERRIDE") or "").strip()
        if ov:
            return ov
    except Exception:
        pass

    # 3) Variável de ambiente
    import os as _os
    return (_os.getenv("GESTTA_JWT") or "").strip()


def listar_conselhos_cnae(cnae: str) -> list[dict]:
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM cnae_conselho WHERE cnae = ? ORDER BY conselho_sigla",
            (cnae,),
        ).fetchall()]


def upsert_cnae_ambiental(
    cnae: str, *,
    exige_licenca: bool,
    orgao: str | None = None,
    porte_padrao: str | None = None,
    tipo_licenca: str | None = None,
    observacao: str | None = None,
    fonte: str | None = None,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO cnae_ambiental
                 (cnae, exige_licenca, orgao, porte_padrao, tipo_licenca,
                  observacao, fonte)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(cnae) DO UPDATE SET
                 exige_licenca = excluded.exige_licenca,
                 orgao = excluded.orgao,
                 porte_padrao = excluded.porte_padrao,
                 tipo_licenca = excluded.tipo_licenca,
                 observacao = excluded.observacao,
                 fonte = excluded.fonte,
                 atualizado_em = datetime('now','localtime')""",
            (cnae, int(exige_licenca), orgao, porte_padrao, tipo_licenca,
             observacao, fonte),
        )
        conn.commit()


def buscar_cnae_ambiental(cnae: str) -> dict | None:
    with get_conn() as conn:
        r = conn.execute(
            "SELECT * FROM cnae_ambiental WHERE cnae = ?", (cnae,),
        ).fetchone()
        return dict(r) if r else None


def upsert_cnae_anvisa(
    cnae: str, *,
    exige_anvisa: bool,
    categoria: str | None = None,
    observacao: str | None = None,
    fonte: str | None = None,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO cnae_anvisa
                 (cnae, exige_anvisa, categoria, observacao, fonte)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(cnae) DO UPDATE SET
                 exige_anvisa = excluded.exige_anvisa,
                 categoria = excluded.categoria,
                 observacao = excluded.observacao,
                 fonte = excluded.fonte,
                 atualizado_em = datetime('now','localtime')""",
            (cnae, int(exige_anvisa), categoria, observacao, fonte),
        )
        conn.commit()


def buscar_cnae_anvisa(cnae: str) -> dict | None:
    with get_conn() as conn:
        r = conn.execute(
            "SELECT * FROM cnae_anvisa WHERE cnae = ?", (cnae,),
        ).fetchone()
        return dict(r) if r else None


# ---------------------------------------------------------------------------
# CONSULTOR DE CNAE — função consolidada
# ---------------------------------------------------------------------------
def _normalizar_cnae(codigo: str) -> str:
    """Aceita 4729601, 4729-6/01, 4729-601, 47.296.01 etc → '4729-6/01'."""
    digitos = "".join(c for c in str(codigo or "") if c.isdigit())
    if len(digitos) == 7:
        return f"{digitos[:4]}-{digitos[4]}/{digitos[5:]}"
    return str(codigo or "").strip()


# ---------------------------------------------------------------------------
# REGRAS SETORIAIS — protege contra falsos negativos quando a base local
# está incompleta. Aplicada ao final de `analisar_cnae`.
# ---------------------------------------------------------------------------

# Procedimentos estéticos invasivos que tornam licença sanitária OBRIGATÓRIA
# mesmo quando a Portaria CVS 13/2025 listaria o CNAE como isento.
PROCEDIMENTOS_INVASIVOS_SAUDE = [
    "Toxina botulínica (Botox)",
    "Preenchimento facial (ácido hialurônico, polilático, PMMA)",
    "Harmonização orofacial / facial",
    "Bioestimuladores de colágeno injetáveis",
    "Microagulhamento profundo / drug delivery",
    "Peelings médios e profundos",
    "Fios de sustentação / bioestimuladores",
    "Lipoescultura, lipoaspiração",
    "Carboxiterapia, intradermoterapia, mesoterapia",
    "Aplicação de PMMA, hidroxiapatita de cálcio",
    "Plasma rico em plaquetas (PRP)",
    "Procedimentos com laser ablativo",
]

# Conselhos potencialmente aplicáveis para CNAEs genéricos da saúde
# (8650-0/99, 8690-9/01, etc.). O conselho efetivo depende da formação
# do RT (Responsável Técnico) e dos profissionais que atuam na clínica.
CONSELHOS_SAUDE_GENERICOS = [
    ("CRM", "Conselho Regional de Medicina",
     "Médicos — única classe com atuação irrestrita em estética invasiva (CFM 2.628/2022)"),
    ("CRO", "Conselho Regional de Odontologia",
     "Cirurgiões-dentistas — autorizados em harmonização orofacial (CFO 198/2019)"),
    ("CRBM", "Conselho Regional de Biomedicina",
     "Biomédicos com habilitação em estética (CFBM 241/2014); sob disputa judicial"),
    ("COREN", "Conselho Regional de Enfermagem",
     "Enfermeiros — protocolos COFEN 689/2022"),
    ("CREFITO", "Conselho Regional de Fisioterapia e Terapia Ocupacional",
     "Fisioterapeutas dermatofuncionais"),
    ("CFFa", "Conselho Regional de Fonoaudiologia",
     "Fonoaudiólogos com pós em estética orofacial"),
    ("CRP", "Conselho Regional de Psicologia",
     "Psicólogos"),
    ("CRN", "Conselho Regional de Nutricionistas",
     "Nutricionistas"),
]


def _aplicar_regras_setoriais(out: dict, cnae: str) -> None:
    """Aplica regras de fallback por prefixo CNAE pra evitar falso negativo
    crítico. Modifica `out` in-place: pode adicionar conselhos sugeridos,
    elevar nível da vigilância, e empilhar alertas em vermelho.

    Diretriz: na dúvida, ALERTAR. É melhor o usuário se incomodar com um
    aviso a mais do que orientar errado e o cliente tomar multa.
    """
    secao = cnae[:2] if len(cnae) >= 2 else ""

    # ============ SAÚDE HUMANA — Seções 86, 87, 88 (parcial) ============
    if secao in ("86", "87"):
        # Lista de CNAEs que são SEMPRE consultórios sem invasivo
        # (puramente psicoterapia, ergonomia, etc.) — apenas alerta leve
        cnaes_baixo_risco = {"8650-0/03", "8650-0/05"}  # psicologia / práticas alternativas

        if cnae not in cnaes_baixo_risco:
            # 1) Vigilância: força CONDICIONAL se hoje vier como ISENTO/OK
            vig = out.get("vigilancia") or {}
            era_isento = (
                not vig.get("exige_licenca")
                and not vig.get("_aviso_invasivo_aplicado")
            )
            if era_isento:
                vig["_aviso_invasivo_aplicado"] = True
                vig["nivel"] = vig.get("nivel") or "ISENCAO_CONDICIONAL"
                vig["descricao"] = (
                    (vig.get("descricao") or "")
                    + " | ⚠️ ATENÇÃO: a isenção da Portaria CVS 13/2025 vale "
                    "APENAS para atendimentos sem procedimentos invasivos. "
                    "Botox, harmonização, preenchimento, peelings médios/"
                    "profundos, microagulhamento profundo, laser ablativo "
                    "ou qualquer aplicação de produto injetável OBRIGAM "
                    "licença sanitária."
                ).strip(" |")
                vig["risco_sanitario"] = (
                    vig.get("risco_sanitario") or "BAIXO_CONDICIONAL"
                )
                out["vigilancia"] = vig

            # 2) Conselhos: se nenhum cadastrado, sugerir os 5 mais comuns
            if not out.get("conselhos"):
                out["conselhos"] = [
                    {
                        "conselho_sigla": s,
                        "conselho_nome": n,
                        "tipo_registro": "AMBOS",
                        "exige_rt": 1,
                        "fonte": f"Inferido por prefixo CNAE {secao} (saúde) — {obs}",
                        "_inferido_setorial": True,
                    }
                    for s, n, obs in CONSELHOS_SAUDE_GENERICOS[:5]
                ]
                out["fontes"].append(
                    "⚠️ Conselhos profissionais inferidos por prefixo CNAE "
                    "(base local não tinha cadastro). Confirme com o RT."
                )

            # 3) Alerta crítico em vermelho
            out["alertas"].insert(0,
                "🚨 **ATENÇÃO CRÍTICA — CNAE de saúde humana.** "
                "Profissionais que atuam neste CNAE DEVEM ter registro no "
                "respectivo conselho de classe (CRM/CRO/CRBM/COREN/CREFITO/"
                "CFFa/CRP/CRN conforme formação) e a clínica/PJ DEVE ter "
                "inscrição PJ no conselho do RT. **Procedimentos invasivos** "
                "(botox, harmonização, preenchimento, peelings profundos, "
                "microagulhamento profundo, laser ablativo, plasma rico em "
                "plaquetas, etc.) **OBRIGAM licença sanitária**, mesmo que "
                "a Portaria CVS 13/2025 isente o CNAE em si."
            )

            # 4) Lista de procedimentos invasivos pra UI
            out["procedimentos_invasivos_alerta"] = PROCEDIMENTOS_INVASIVOS_SAUDE

    # ============ EDUCAÇÃO INFANTIL / CRECHE — 8511, 8512 ============
    if secao == "85" and cnae[:4] in ("8511", "8512"):
        out["alertas"].append(
            "🚨 Educação infantil — exige autorização do Conselho Estadual/"
            "Municipal de Educação + alvará sanitário + AVCB + adequação NR-"
            "específica (espaços para crianças). Verifique a Resolução "
            "CME local."
        )

    # ============ ALIMENTOS — 1011-1099, 5611, 5620 ============
    if cnae[:2] == "10" or cnae[:4] in ("5611", "5620"):
        if not (out.get("vigilancia") or {}).get("exige_licenca"):
            out["alertas"].append(
                "⚠️ CNAE de alimentos — confirme com a Vigilância Sanitária "
                "municipal (exige Alvará Sanitário em quase todos os "
                "municípios) e RDC ANVISA 216/2004 (manipulação)."
            )


def analisar_cnae(codigo: str) -> dict:
    """Faz análise CRUZADA de um CNAE em todas as bases disponíveis.

    Retorna um dict consolidado com:
      - codigo, descricao
      - concla{}, nr04{}, vigilancia{}, bombeiros{}, ambiental{},
        anvisa{}, conselhos[], cgsim{}
      - risco_consolidado: 'BAIXO' | 'MÉDIO' | 'ALTO'
      - alertas: list[str] (avisos importantes)
      - fontes: list[str] (legislação consultada)
    """
    cnae = _normalizar_cnae(codigo)

    out: dict = {
        "codigo": cnae,
        "codigo_input": codigo,
        "descricao": None,
        "concla": None,
        "nr04": None,
        "vigilancia": None,
        "bombeiros": None,
        "ambiental": None,
        "anvisa": None,
        "conselhos": [],
        "outros_registros": [],
        "habilitacoes_profissionais": [],
        "regras_oficiais": [],   # respostas determinísticas com base legal
        "cgsim": None,
        "risco_consolidado": "INDEFINIDO",
        "alertas": [],
        "fontes": [],
    }

    # 1. CONCLA — descrição oficial
    concla = buscar_cnae_concla(cnae)
    if concla:
        out["concla"] = concla
        out["descricao"] = (
            concla.get("denominacao") or concla.get("descricao")
        )
        out["fontes"].append(
            "CONCLA / IBGE — Estrutura CNAE 2.3 (cnae_concla)"
        )
    else:
        out["alertas"].append(
            f"CNAE {cnae} não encontrado na base CONCLA. Confira o código."
        )

    # 2. NR-04 — grau de risco trabalhista
    # `buscar_risco_cnae` agora sempre retorna algo (usa fallback por
    # divisão CNAE quando o código específico não está cadastrado).
    # Só alertamos se o grau veio por inferência.
    nr04 = buscar_risco_cnae(cnae)
    if nr04:
        out["nr04"] = nr04
        if nr04.get("fonte"):
            out["fontes"].append(f"NR-04: {nr04['fonte']}")
        if nr04.get("_inferido_por_divisao"):
            out["alertas"].append(
                f"📊 Grau NR-04 ESTIMADO pela divisão CNAE "
                f"({cnae[:2]}) — para SESMT/dimensionamento, confirme "
                f"o CNAE específico no Quadro I oficial."
            )
    else:
        out["alertas"].append(
            "Grau de risco NR-04 indisponível para este CNAE — "
            "confirme manualmente no Quadro I oficial."
        )

    # 3. Vigilância Sanitária (CVS-SP)
    vig = buscar_vigilancia(cnae)
    if vig:
        out["vigilancia"] = vig
        if vig.get("fonte"):
            out["fontes"].append(f"Vigilância: {vig['fonte']}")
    else:
        out["vigilancia"] = {"exige_licenca": False, "_inferido": True}

    # 4. Bombeiros (IT-01 CBPMESP)
    bomb = buscar_bombeiros_cnae(cnae)
    if bomb:
        out["bombeiros"] = bomb
        if bomb.get("fonte"):
            out["fontes"].append(f"Bombeiros: {bomb['fonte']}")
    else:
        out["bombeiros"] = {"exige_avcb": False, "_inferido": True}

    # 5. Ambiental (CETESB/IBAMA)
    amb = buscar_cnae_ambiental(cnae)
    if amb:
        out["ambiental"] = amb
        if amb.get("fonte"):
            out["fontes"].append(f"Ambiental: {amb['fonte']}")
    else:
        out["ambiental"] = {"exige_licenca": False, "_inferido": True}

    # 6. ANVISA
    anv = buscar_cnae_anvisa(cnae)
    if anv:
        out["anvisa"] = anv
        if anv.get("fonte"):
            out["fontes"].append(f"ANVISA: {anv['fonte']}")
    else:
        out["anvisa"] = {"exige_anvisa": False, "_inferido": True}

    # 7. Conselhos profissionais
    out["conselhos"] = listar_conselhos_cnae(cnae)
    if out["conselhos"]:
        for c in out["conselhos"]:
            if c.get("fonte"):
                out["fontes"].append(f"{c['conselho_sigla']}: {c['fonte']}")

    # 7b. Outros registros federais (CTF/IBAMA, MAPA, INMETRO, etc.)
    out["outros_registros"] = listar_outros_registros_cnae(cnae)
    if out["outros_registros"]:
        for r in out["outros_registros"]:
            if r.get("fonte"):
                out["fontes"].append(f"{r['orgao']}: {r['fonte']}")

    # 7c. Habilitação profissional CONDICIONAL — atividades dentro do
    # CNAE que exigem profissional habilitado, mesmo sem registro da PJ.
    # Caso clássico: clínica de estética que aplica botox.
    out["habilitacoes_profissionais"] = listar_habilitacoes_cnae(cnae)
    if out["habilitacoes_profissionais"]:
        for h in out["habilitacoes_profissionais"]:
            if h.get("fonte"):
                out["fontes"].append(
                    f"Habilitação ({h.get('conselho_sigla') or 'profissional'}): "
                    f"{h['fonte']}"
                )

    # 7d. REGRAS OFICIAIS determinísticas (a fonte de CERTEZA do sistema).
    # Quando cadastradas pra esse CNAE, dão a resposta definitiva
    # OBRIGATÓRIO / DISPENSADO / CONDICIONAL com base legal e link.
    try:
        out["regras_oficiais"] = buscar_regras_cnae(cnae)
        for r in out["regras_oficiais"]:
            if r.get("base_legal"):
                out["fontes"].append(
                    f"Regra oficial ({r.get('orgao_sigla')}): "
                    f"{r['base_legal']}"
                )
    except Exception:
        out["regras_oficiais"] = []

    # 8. CGSIM
    try:
        cgsim = buscar_cgsim_cnae(cnae)
        if cgsim:
            out["cgsim"] = cgsim
            if cgsim.get("fonte"):
                out["fontes"].append(f"CGSIM: {cgsim['fonte']}")
    except Exception:
        pass

    # 8b. CAMADA DE REGRAS SETORIAIS
    # Garante que CNAEs de saúde/educação/etc. sempre disparam alerta
    # mesmo se a base local estiver incompleta. Esta camada existe pra
    # prevenir falsos negativos críticos (ex.: clínica de botox que
    # apareceu como "Vigilância OK" porque CVS 13/2025 lista o CNAE
    # como isento).
    _aplicar_regras_setoriais(out, cnae)

    # 9. Risco consolidado
    fatores_alto = 0
    fatores_medio = 0
    if out["vigilancia"] and out["vigilancia"].get("exige_licenca"):
        fatores_alto += 1
    if out["bombeiros"] and out["bombeiros"].get("exige_avcb"):
        fatores_alto += 1
    if out["ambiental"] and out["ambiental"].get("exige_licenca"):
        fatores_alto += 1
    if out["anvisa"] and out["anvisa"].get("exige_anvisa"):
        fatores_alto += 1
    if out["conselhos"]:
        fatores_medio += 1
    if out["nr04"] and (out["nr04"].get("grau_risco") or 0) >= 3:
        fatores_alto += 1
    if out["nr04"] and (out["nr04"].get("grau_risco") or 0) == 2:
        fatores_medio += 1
    if out.get("cgsim") and (out["cgsim"].get("risco") or "").upper() == "ALTO":
        fatores_alto += 1

    if fatores_alto >= 2:
        out["risco_consolidado"] = "ALTO"
    elif fatores_alto >= 1 or fatores_medio >= 1:
        out["risco_consolidado"] = "MÉDIO"
    else:
        out["risco_consolidado"] = "BAIXO"

    # remove duplicatas das fontes
    out["fontes"] = list(dict.fromkeys(out["fontes"]))

    # 10. Status de verificação (sub-agente Cowork)
    ult = buscar_ultima_verificacao_cnae(cnae)
    if ult:
        from datetime import datetime as _dt
        try:
            d = _dt.strptime(ult["data_verificacao"][:10], "%Y-%m-%d")
            dias = (_dt.now() - d).days
            ult["dias_desde_verificacao"] = dias
            if dias < 30:
                ult["nivel_confianca"] = "RECENTE"
            elif dias < 90:
                ult["nivel_confianca"] = "MEDIO"
            else:
                ult["nivel_confianca"] = "ANTIGO"
        except Exception:
            ult["dias_desde_verificacao"] = None
            ult["nivel_confianca"] = "DESCONHECIDO"
    else:
        ult = {
            "nivel_confianca": "NUNCA",
            "dias_desde_verificacao": None,
            "resultado": None,
        }
    out["verificacao"] = ult

    return out


def analisar_empresa_completa(
    cnpj_or_dados, *, usar_cache: bool = True,
) -> dict:
    """Análise completa de uma empresa: consulta CNPJ + roda
    analisar_cnae em cada CNAE (principal + secundários) + consolida.

    Aceita:
      - string CNPJ (vai consultar API) — usa cache local se recente
      - dict já com os dados da API (pula a consulta)

    Retorna:
      {
        "empresa": {... dados Receita ...},
        "is_nova": False,
        "cnae_principal_analise": {...},
        "cnaes_secundarios_analise": [{...}, ...],
        "risco_consolidado": "BAIXO|MÉDIO|ALTO",
        "checklist": [
            {"orgao": "ANVISA", "obrigatorio": True|False,
             "motivo": "...", "link_consulta": "...", "link_cadastro": "...",
             "status_sugerido": "OBRIGATORIO|VERIFICAR|N/A"},
            ...
        ],
        "alertas_globais": [...],
        "total_cnaes": N,
        "data_analise": "ISO",
      }
    """
    from datetime import datetime as _dt

    # 1) Consulta CNPJ (ou recebe dados prontos)
    if isinstance(cnpj_or_dados, dict):
        dados = cnpj_or_dados
        cnpj_lim = dados.get("cnpj", "")
    else:
        from utils.cnpj_api import (
            consultar_cnpj, limpar_cnpj,
        )
        cnpj_lim = limpar_cnpj(cnpj_or_dados)
        dados = None
        if usar_cache:
            dados = cache_cnpj_get(cnpj_lim)
        if not dados:
            dados = consultar_cnpj(cnpj_lim)
            cache_cnpj_set(cnpj_lim, dados)

    # 2) Roda analisar_cnae em cada CNAE
    cnae_pr = (dados.get("cnae_principal") or {}).get("codigo", "")
    cnaes_sec = [c.get("codigo", "")
                 for c in (dados.get("cnaes_secundarios") or [])
                 if c.get("codigo")]

    analise_pr = analisar_cnae(cnae_pr) if cnae_pr else None
    analises_sec = [analisar_cnae(c) for c in cnaes_sec]

    todas_analises = [analise_pr] + analises_sec
    todas_analises = [a for a in todas_analises if a]

    # 3) Consolida risco — o maior risco entre todos os CNAEs
    ordem_risco = {"BAIXO": 1, "MÉDIO": 2, "ALTO": 3}
    risco_top = "BAIXO"
    for a in todas_analises:
        if ordem_risco.get(a["risco_consolidado"], 0) > \
                ordem_risco.get(risco_top, 0):
            risco_top = a["risco_consolidado"]

    # 4) Monta checklist agregado por órgão (deduplica)
    checklist: dict[str, dict] = {}
    uf = (dados.get("endereco") or {}).get("uf", "SP") or "SP"

    def _add(sigla: str, motivo: str, *,
             obrigatorio: bool = True, uf_override: str | None = None):
        key = sigla.upper()
        if key in checklist:
            # mantém o "obrigatório" mais forte
            checklist[key]["obrigatorio"] = (
                checklist[key]["obrigatorio"] or obrigatorio
            )
            if motivo not in checklist[key]["motivos"]:
                checklist[key]["motivos"].append(motivo)
            return
        orgao = buscar_orgao(sigla, uf_override or uf)
        checklist[key] = {
            "sigla": key,
            "nome": (orgao or {}).get("nome", sigla),
            "obrigatorio": obrigatorio,
            "motivos": [motivo],
            "link_consulta": (orgao or {}).get("link_consulta") or "",
            "link_cadastro": (orgao or {}).get("link_cadastro") or "",
            "descricao": (orgao or {}).get("descricao") or "",
            "categoria": (orgao or {}).get("categoria") or "",
            "esfera": (orgao or {}).get("esfera") or "",
        }

    # Sempre presentes (cadastrais)
    _add("RFB", "CNPJ obrigatório pra qualquer PJ.")
    _add("REDESIM", "Portal único pra abertura/alteração/baixa.")

    # Por CNAE
    for a in todas_analises:
        cod_a = a.get("codigo") or "?"
        if a.get("anvisa") and a["anvisa"].get("exige_anvisa"):
            _add("ANVISA",
                 f"CNAE {cod_a} exige autorização ANVISA (AFE/AE).")
        if a.get("vigilancia") and a["vigilancia"].get("exige_licenca"):
            _add("CVS-SP",
                 f"CNAE {cod_a} exige Licença Sanitária estadual.",
                 uf_override="SP")
            _add("COVISA-SP",
                 f"CNAE {cod_a} pode exigir Licença Sanitária "
                 f"municipal (SP capital).",
                 obrigatorio=False, uf_override="SP")
        if a.get("bombeiros") and a["bombeiros"].get("exige_avcb"):
            _add("CBPMESP",
                 f"CNAE {cod_a} exige AVCB/CLCB pelo IT-01.",
                 uf_override="SP")
        if a.get("ambiental") and a["ambiental"].get("exige_licenca"):
            _add("CETESB",
                 f"CNAE {cod_a} exige licenciamento ambiental.",
                 uf_override="SP")
            _add("IBAMA",
                 f"CNAE {cod_a} pode constar no CTF/APP do IBAMA.",
                 obrigatorio=False)
        for c in (a.get("conselhos") or []):
            sigla_c = (c.get("conselho_sigla") or "").upper()
            if sigla_c:
                _add(sigla_c,
                     f"CNAE {cod_a}: PJ precisa de registro no "
                     f"{sigla_c} ({c.get('observacao') or ''}).".strip())
        for r in (a.get("outros_registros") or []):
            sigla_r = (r.get("orgao") or "").upper()
            if sigla_r:
                _add(sigla_r,
                     f"CNAE {cod_a}: {r.get('observacao') or 'registro'}.")
        for h in (a.get("habilitacoes_profissionais") or []):
            sigla_h = (h.get("conselho_sigla") or "").upper()
            if sigla_h:
                _add(sigla_h,
                     f"CNAE {cod_a}: atividade '{h.get('atividade') or '—'}'"
                     f" exige profissional habilitado.",
                     obrigatorio=False)

    # Simples Nacional — alerta se a empresa for ME/EPP e tiver CNAE
    # potencialmente vedado (alta complexidade)
    if (dados.get("porte") in {"ME", "EPP"} and
            dados.get("regime_tributario") == "SIMPLES"):
        _add("SIMPLES",
             "Empresa optante pelo Simples — confirme se TODOS os CNAEs "
             "estão na lista permitida.",
             obrigatorio=False)

    # 5) Alertas globais
    alertas = []
    if dados.get("situacao") and dados["situacao"] != "ATIVA":
        alertas.append(
            f"⚠️ Situação cadastral: {dados['situacao']} — "
            f"{dados.get('situacao_motivo', '')}"
        )
    if not todas_analises:
        alertas.append(
            "⚠️ Nenhum CNAE encontrado na consulta. Verifique no portal "
            "da Receita."
        )

    # 6) Enriquece cada item do checklist com a última verificação manual
    # (empresa existente — empresa nova não tem CNPJ ainda)
    verif_map = {}
    if cnpj_lim:
        try:
            verif_map = listar_verificacoes_empresa(cnpj_lim)
        except Exception:
            verif_map = {}

    for item in checklist.values():
        v = verif_map.get(item["sigla"])
        if v:
            item["verificacao"] = {
                "status": v.get("status"),
                "verificado_em": v.get("verificado_em"),
                "verificado_por": v.get("verificado_por"),
                "observacao": v.get("observacao"),
            }
        else:
            item["verificacao"] = None

        # 6b) Enriquece com REGRA OFICIAL determinística (se houver)
        # Procura nas regras de CADA CNAE da empresa pra esse órgão,
        # devolvendo a primeira que existir. Isso é o que dá CERTEZA
        # ao sistema — quando há regra cadastrada, o usuário vê
        # "OBRIGATÓRIO/DISPENSADO/CONDICIONAL" com base legal.
        regras_aplicaveis = []
        for a in todas_analises:
            cnae_a = a.get("codigo") or ""
            if not cnae_a:
                continue
            reg = buscar_regra_especifica(
                cnae_a, item["sigla"],
                orgao_uf=None,  # busca federal primeiro
            )
            if not reg:
                # Tenta com UF (regras estaduais)
                reg = buscar_regra_especifica(
                    cnae_a, item["sigla"], orgao_uf=uf,
                )
            if reg:
                regras_aplicaveis.append({
                    "cnae": cnae_a,
                    "obrigatoriedade": reg.get("obrigatoriedade"),
                    "condicoes_obrigatorio": reg.get(
                        "condicoes_obrigatorio"),
                    "condicoes_dispensa": reg.get(
                        "condicoes_dispensa"),
                    "observacoes": reg.get("observacoes"),
                    "base_legal": reg.get("base_legal"),
                    "link_lei": reg.get("link_lei"),
                    "data_revisao": (
                        reg.get("data_revisao")
                        or reg.get("data_cadastro")
                    ),
                })
        item["regras_oficiais"] = regras_aplicaveis

    return {
        "empresa": dados,
        "is_nova": False,
        "cnae_principal_analise": analise_pr,
        "cnaes_secundarios_analise": analises_sec,
        "risco_consolidado": risco_top,
        "checklist": sorted(
            checklist.values(),
            # Ordem: pendentes obrigatórios → verificados → N/A
            key=lambda x: (
                # 0 = pendente obrigatório, 1 = pendente opcional,
                # 2 = problema, 3 = verificado, 4 = não se aplica
                _peso_status(x.get("verificacao"), x["obrigatorio"]),
                x["categoria"], x["sigla"],
            ),
        ),
        "alertas_globais": alertas,
        "total_cnaes": len(todas_analises),
        "data_analise": _dt.now().isoformat(timespec="seconds"),
    }


def _peso_status(verif: dict | None, obrigatorio: bool) -> int:
    """Peso pra ordenar checklist (menor = aparece primeiro)."""
    if not verif or verif.get("status") == STATUS_VERIFICACAO_PENDENTE:
        return 0 if obrigatorio else 1
    if verif.get("status") == STATUS_VERIFICACAO_PROBLEMA:
        return -1   # problemas SEMPRE no topo
    if verif.get("status") == STATUS_VERIFICACAO_OK:
        return 3
    if verif.get("status") == STATUS_VERIFICACAO_NA:
        return 4
    return 2


def analisar_cnaes_pretendidos(
    cnaes: list[str], *, uf: str = "SP",
) -> dict:
    """Análise pra empresa NOVA — recebe lista de CNAEs pretendidos
    e devolve o mesmo formato de relatório, sem dados de Receita.

    Use isso pra responder "o cliente quer abrir uma empresa com esses
    CNAEs, o que precisa preparar antes?"
    """
    from datetime import datetime as _dt

    dados_fake = {
        "cnpj": "",
        "razao_social": "(empresa nova — ainda sem CNPJ)",
        "situacao": "PRÉ-ABERTURA",
        "endereco": {"uf": uf},
        "cnae_principal": ({"codigo": cnaes[0], "descricao": ""}
                            if cnaes else {}),
        "cnaes_secundarios": [
            {"codigo": c, "descricao": ""} for c in cnaes[1:]
        ],
        "porte": "ME",
        "regime_tributario": None,
    }
    # Reusa o motor
    rel = analisar_empresa_completa(dados_fake, usar_cache=False)
    rel["is_nova"] = True
    rel["data_analise"] = _dt.now().isoformat(timespec="seconds")
    return rel


# ---------------------------------------------------------------------------
# CONSULTOR DE CNAE — verificação por sub-agente Cowork
# ---------------------------------------------------------------------------
def registrar_consulta_cnae(cnae: str, contexto: str | None = None) -> None:
    """Loga que o usuário consultou esse CNAE no app. Usado pelo schedule
    semanal pra priorizar revalidação dos mais consultados."""
    cnae_norm = _normalizar_cnae(cnae)
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO cnae_consulta_log (cnae, contexto) VALUES (?, ?)",
            (cnae_norm, contexto),
        )
        conn.commit()


def registrar_verificacao_cnae(
    cnae: str,
    resultado: str,           # 'APROVADO' / 'DIVERGENCIA' / 'NOVAS_INFOS'
    *,
    divergencias_count: int = 0,
    relatorio: str | None = None,
    fonte: str = "Sub-agente Cowork",
    verificado_por: str | None = None,
) -> int:
    """Grava o resultado da verificação por sub-agente.
    Aprovação = base local está correta.
    Divergência = base local tem erros — Eduardo deve corrigir.
    Novas informações = base local está incompleta mas não errada.
    """
    if resultado not in {"APROVADO", "DIVERGENCIA", "NOVAS_INFOS"}:
        raise ValueError(f"resultado inválido: {resultado}")
    cnae_norm = _normalizar_cnae(cnae)
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO cnae_verificacao
                 (cnae, resultado, divergencias_count, relatorio, fonte, verificado_por)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (cnae_norm, resultado, divergencias_count, relatorio, fonte, verificado_por),
        )
        conn.commit()
        return cur.lastrowid


def buscar_ultima_verificacao_cnae(cnae: str) -> dict | None:
    cnae_norm = _normalizar_cnae(cnae)
    with get_conn() as conn:
        r = conn.execute(
            """SELECT * FROM cnae_verificacao
                WHERE cnae = ?
                ORDER BY id DESC
                LIMIT 1""",
            (cnae_norm,),
        ).fetchone()
        return dict(r) if r else None


def historico_verificacao_cnae(cnae: str, limite: int = 10) -> list[dict]:
    cnae_norm = _normalizar_cnae(cnae)
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            """SELECT * FROM cnae_verificacao
                WHERE cnae = ?
                ORDER BY id DESC LIMIT ?""",
            (cnae_norm, limite),
        ).fetchall()]


def cnaes_pendentes_verificacao(
    *, dias_max: int = 90, top_n: int = 20,
) -> list[dict]:
    """Retorna lista de CNAEs que MERECEM revalidação:
    (a) consultados nos últimos 30 dias E
    (b) sem verificação nos últimos `dias_max` dias.
    Ordenados por nº de consultas decrescente.
    """
    sql = f"""
      WITH consultas AS (
        SELECT cnae, COUNT(*) AS n
          FROM cnae_consulta_log
         WHERE consultado_em >= datetime('now', '-30 days')
         GROUP BY cnae
      ),
      ult_verif AS (
        SELECT cnae, MAX(data_verificacao) AS ult
          FROM cnae_verificacao
         GROUP BY cnae
      )
      SELECT c.cnae, c.n AS consultas_30d,
             u.ult AS ultima_verificacao,
             CAST(julianday('now') - julianday(u.ult) AS INTEGER) AS dias_desde_verif
        FROM consultas c
        LEFT JOIN ult_verif u ON u.cnae = c.cnae
       WHERE u.ult IS NULL
          OR julianday('now') - julianday(u.ult) >= {int(dias_max)}
       ORDER BY c.n DESC
       LIMIT ?;
    """
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, (top_n,)).fetchall()]


if __name__ == "__main__":
    init_db()
    print(f"Banco inicializado em: {DATABASE_PATH}")
