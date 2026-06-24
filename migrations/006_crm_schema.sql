-- 006_crm_schema.sql
-- Cria as 8 tabelas do módulo CRM (CRM1/CRM2/CRM3 + SKUs) no PostgreSQL.
-- Execute no Supabase SQL Editor.
-- Idempotente: dropa e recria cada tabela.

-- ─── crm_clients ──────────────────────────────────────────────────────────────
DROP TABLE IF EXISTS crm_clients CASCADE;

CREATE TABLE crm_clients (
    id                              TEXT PRIMARY KEY,
    tenant_id                       TEXT NOT NULL,
    stage                           TEXT NOT NULL DEFAULT 'prospeccao',
    nome_empresa                    TEXT NOT NULL DEFAULT '',
    cnpj                            TEXT DEFAULT '',
    cnpj_normalized                 TEXT,
    cli3                            TEXT DEFAULT '',
    cli4                            TEXT DEFAULT '',
    cli4_congelado                  BOOLEAN DEFAULT FALSE,
    canal_origem                    TEXT DEFAULT '',
    origem_lead                     TEXT DEFAULT '',
    temperatura_lead                TEXT DEFAULT 'morno',
    responsavel_comercial           TEXT DEFAULT '',
    segmento                        TEXT DEFAULT '',
    porte                           TEXT DEFAULT '',
    regiao                          TEXT DEFAULT '',
    site                            TEXT DEFAULT '',
    instagram                       TEXT DEFAULT '',
    observacoes                     TEXT DEFAULT '',
    tem_marca_propria               BOOLEAN,
    tem_anvisa                      TEXT DEFAULT '',
    volume_estimado_mensal          TEXT DEFAULT '',
    prazo_urgencia                  TEXT,
    valor_estimado_projeto          NUMERIC(16,2),
    valor_estimado_projeto_currency TEXT DEFAULT 'BRL',
    moq_negociado                   TEXT DEFAULT '',
    condicao_pagamento              TEXT DEFAULT '',
    motivo_perda                    TEXT DEFAULT '',
    data_pedido                     TEXT,
    valor_primeiro_pedido           NUMERIC(16,2),
    valor_primeiro_pedido_currency  TEXT DEFAULT 'BRL',
    previsao_segundo_pedido         TEXT,
    ultima_atualizacao_temperatura  TEXT,
    has_grau2_anvisa                BOOLEAN DEFAULT FALSE,
    created_by                      TEXT DEFAULT '',
    created_by_name                 TEXT DEFAULT '',
    created_at                      TIMESTAMPTZ DEFAULT NOW(),
    updated_at                      TIMESTAMPTZ DEFAULT NOW(),
    -- JSONB for nested / array fields
    categoria_interesse             JSONB DEFAULT '[]',
    contato_principal               JSONB DEFAULT '{}',
    contatos_adicionais             JSONB DEFAULT '[]',
    decisores                       JSONB DEFAULT '[]',
    fornecedor_atual                JSONB DEFAULT '{}',
    anvisa_necessario               JSONB DEFAULT '{}',
    concorrentes_envolvidos         JSONB DEFAULT '[]',
    skus_confirmados                JSONB DEFAULT '[]',
    amostras_aprovadas              JSONB DEFAULT '[]',
    historico_movimentacoes         JSONB DEFAULT '[]'
);

CREATE UNIQUE INDEX idx_crmcli_tenant_cli4
    ON crm_clients(tenant_id, cli4)
    WHERE cli4 IS NOT NULL AND cli4 != '';
CREATE UNIQUE INDEX idx_crmcli_tenant_cnpj
    ON crm_clients(tenant_id, cnpj_normalized)
    WHERE cnpj_normalized IS NOT NULL AND cnpj_normalized != '';
CREATE INDEX idx_crmcli_tenant_stage      ON crm_clients(tenant_id, stage);
CREATE INDEX idx_crmcli_tenant_created    ON crm_clients(tenant_id, created_at DESC);
CREATE INDEX idx_crmcli_resp_comercial    ON crm_clients(tenant_id, responsavel_comercial);

-- ─── crm_projects ─────────────────────────────────────────────────────────────
DROP TABLE IF EXISTS crm_projects CASCADE;

CREATE TABLE crm_projects (
    id                              TEXT PRIMARY KEY,
    tenant_id                       TEXT NOT NULL,
    cliente_id                      TEXT NOT NULL,
    cliente_nome                    TEXT DEFAULT '',
    stage                           TEXT NOT NULL DEFAULT 'projeto_em_discussao',
    nome_projeto                    TEXT NOT NULL DEFAULT '',
    categoria                       TEXT DEFAULT '',
    briefing_tecnico                TEXT DEFAULT '',
    responsavel_comercial           TEXT DEFAULT '',
    responsavel_interno             TEXT DEFAULT '',
    ideia_conceito                  TEXT DEFAULT '',
    referencia_mercado              TEXT DEFAULT '',
    publico_alvo                    TEXT DEFAULT '',
    posicionamento                  TEXT DEFAULT '',
    faixa_preco_venda               NUMERIC(16,2),
    volume_estimado_pedido          INTEGER,
    tipo_servico                    TEXT DEFAULT '',
    sensorial_desejado              TEXT DEFAULT '',
    claims_desejados                TEXT DEFAULT '',
    prazo_desejado_amostra          TEXT DEFAULT '',
    prazo_prometido_cliente         TEXT,
    observacoes_livres              TEXT DEFAULT '',
    data_inicio_desenvolvimento     TEXT,
    data_ultima_amostra_enviada     TEXT,
    numero_amostras_solicitadas     INTEGER DEFAULT 0,
    motivo_arquivamento             TEXT DEFAULT '',
    created_by                      TEXT DEFAULT '',
    created_by_name                 TEXT DEFAULT '',
    created_at                      TIMESTAMPTZ DEFAULT NOW(),
    updated_at                      TIMESTAMPTZ DEFAULT NOW(),
    -- JSONB
    restricoes_tecnicas             JSONB DEFAULT '[]',
    historico_movimentacoes         JSONB DEFAULT '[]'
);

CREATE INDEX idx_crmprj_tenant_cliente    ON crm_projects(tenant_id, cliente_id);
CREATE INDEX idx_crmprj_tenant_stage      ON crm_projects(tenant_id, stage);
CREATE INDEX idx_crmprj_tenant_created    ON crm_projects(tenant_id, created_at DESC);

-- ─── crm_samples ──────────────────────────────────────────────────────────────
DROP TABLE IF EXISTS crm_samples CASCADE;

CREATE TABLE crm_samples (
    id                              TEXT PRIMARY KEY,
    tenant_id                       TEXT NOT NULL,
    projeto_id                      TEXT NOT NULL,
    projeto_nome                    TEXT DEFAULT '',
    cliente_id                      TEXT DEFAULT '',
    cliente_nome                    TEXT DEFAULT '',
    numero_amostra                  TEXT DEFAULT '',
    nome_produto                    TEXT DEFAULT '',
    nome_amostra                    TEXT DEFAULT '',
    categoria                       TEXT DEFAULT '',
    stage                           TEXT NOT NULL DEFAULT 'solicitada',
    rework_de_amostra_id            TEXT,
    rework_motivo                   TEXT DEFAULT '',
    responsavel_pd                  TEXT DEFAULT '',
    parametro_variacao              TEXT DEFAULT '',
    tipo_amostra                    TEXT DEFAULT '',
    referencia_formula              TEXT DEFAULT '',
    quantidade_por_variacao         NUMERIC(12,4),
    unidade_quantidade              TEXT DEFAULT 'g',
    prazo_entrega_cliente           TEXT DEFAULT '',
    briefing_base                   TEXT DEFAULT '',
    briefing_especifico             TEXT DEFAULT '',
    feedback_cliente                TEXT DEFAULT '',
    direcoes_retrabalho             TEXT DEFAULT '',
    resultado                       TEXT DEFAULT '',
    aprovacao_interna               BOOLEAN DEFAULT FALSE,
    aprovacao_externa               BOOLEAN DEFAULT FALSE,
    data_envio                      TEXT,
    enviado_comercial_em            TEXT,
    aprovado_cliente_em             TEXT,
    reprovacao_motivo               TEXT DEFAULT '',
    tem_variacoes                   BOOLEAN DEFAULT FALSE,
    produto                         TEXT DEFAULT '',
    objetivo_projeto                TEXT DEFAULT '',
    aplicacoes_desenvolver          TEXT DEFAULT '',
    ativos_claims                   TEXT DEFAULT '',
    referencias                     TEXT DEFAULT '',
    orcamento_projeto               TEXT DEFAULT '',
    textura_esperada                TEXT DEFAULT '',
    aplicacao                       TEXT DEFAULT '',
    sensorial                       TEXT DEFAULT '',
    ph                              TEXT DEFAULT '',
    observacao_tecnica              TEXT DEFAULT '',
    created_by                      TEXT DEFAULT '',
    created_by_name                 TEXT DEFAULT '',
    created_at                      TIMESTAMPTZ DEFAULT NOW(),
    updated_at                      TIMESTAMPTZ DEFAULT NOW(),
    -- JSONB
    variacoes                       JSONB DEFAULT '[]',
    projeto_briefing                JSONB DEFAULT '{}',
    referencias_fotos               JSONB DEFAULT '[]',
    historico_movimentacoes         JSONB DEFAULT '[]'
);

CREATE INDEX idx_crmsmp_tenant_projeto    ON crm_samples(tenant_id, projeto_id);
CREATE INDEX idx_crmsmp_tenant_cliente    ON crm_samples(tenant_id, cliente_id);
CREATE INDEX idx_crmsmp_tenant_stage      ON crm_samples(tenant_id, stage);
CREATE INDEX idx_crmsmp_tenant_created    ON crm_samples(tenant_id, created_at DESC);
CREATE INDEX idx_crmsmp_variacoes         ON crm_samples USING GIN(variacoes);

-- ─── skus ─────────────────────────────────────────────────────────────────────
DROP TABLE IF EXISTS skus CASCADE;

CREATE TABLE skus (
    id                              TEXT PRIMARY KEY,
    tenant_id                       TEXT NOT NULL,
    codigo_interno                  TEXT NOT NULL DEFAULT '',
    cat2                            TEXT DEFAULT '',
    cat3                            TEXT DEFAULT '',
    cli3                            TEXT DEFAULT '',
    cli4                            TEXT DEFAULT '',
    nome_produto                    TEXT NOT NULL DEFAULT '',
    categoria                       TEXT DEFAULT '',
    formula_vinculada               TEXT DEFAULT '',
    cliente_id                      TEXT DEFAULT '',
    cliente_nome                    TEXT DEFAULT '',
    projeto_id                      TEXT DEFAULT '',
    projeto_nome                    TEXT DEFAULT '',
    amostra_id                      TEXT DEFAULT '',
    amostra_variacao_id             TEXT DEFAULT '',
    produto_pai_id                  TEXT,
    descricao_aplicacao             TEXT DEFAULT '',
    preco_unitario                  NUMERIC(16,6) DEFAULT 0.0,
    preco_unitario_currency         TEXT DEFAULT 'BRL',
    moq                             INTEGER DEFAULT 0,
    status                          TEXT DEFAULT 'ativo',
    descontinuado_motivo            TEXT,
    descontinuado_em                TEXT,
    descontinuado_por               TEXT,
    data_ultimo_pedido              TEXT,
    frequencia_media_recompra_dias  INTEGER DEFAULT 0,
    created_at                      TIMESTAMPTZ DEFAULT NOW(),
    updated_at                      TIMESTAMPTZ DEFAULT NOW(),
    -- JSONB
    anvisa                          JSONB DEFAULT '{"numero": "", "validade": null}',
    medias_producao                 JSONB DEFAULT '{}',
    historico_pedidos               JSONB DEFAULT '[]'
);

CREATE UNIQUE INDEX idx_skus_tenant_codigo ON skus(tenant_id, codigo_interno);
CREATE INDEX idx_skus_tenant_cliente       ON skus(tenant_id, cliente_id);
CREATE INDEX idx_skus_tenant_status        ON skus(tenant_id, status);
CREATE INDEX idx_skus_tenant_created       ON skus(tenant_id, created_at DESC);
CREATE INDEX idx_skus_amostra_id           ON skus(amostra_id) WHERE amostra_id != '';

-- ─── crm_alerts ───────────────────────────────────────────────────────────────
DROP TABLE IF EXISTS crm_alerts CASCADE;

CREATE TABLE crm_alerts (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    tipo            TEXT NOT NULL DEFAULT '',
    entidade_ref    TEXT DEFAULT '',
    entidade_tipo   TEXT DEFAULT '',
    entidade_nome   TEXT DEFAULT '',
    mensagem        TEXT DEFAULT '',
    data_criacao    TEXT DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'pendente',
    responsavel     TEXT DEFAULT '',
    resolved_at     TEXT,
    resolved_by     TEXT,
    resolved_comment TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_crmalert_tenant_status   ON crm_alerts(tenant_id, status);
CREATE INDEX idx_crmalert_tenant_tipo     ON crm_alerts(tenant_id, tipo);
CREATE INDEX idx_crmalert_entidade_ref    ON crm_alerts(tenant_id, entidade_ref);
CREATE INDEX idx_crmalert_tenant_created  ON crm_alerts(tenant_id, created_at DESC);

-- ─── crm_column_configs ───────────────────────────────────────────────────────
DROP TABLE IF EXISTS crm_column_configs CASCADE;

CREATE TABLE crm_column_configs (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    crm_type    TEXT NOT NULL,
    key         TEXT NOT NULL DEFAULT '',
    label       TEXT NOT NULL DEFAULT '',
    color       TEXT DEFAULT '',
    "order"     INTEGER DEFAULT 0,
    is_system   BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_crmcol_tenant_type   ON crm_column_configs(tenant_id, crm_type);
CREATE INDEX idx_crmcol_tenant_order  ON crm_column_configs(tenant_id, crm_type, "order");

-- ─── crm_field_configs ────────────────────────────────────────────────────────
DROP TABLE IF EXISTS crm_field_configs CASCADE;

CREATE TABLE crm_field_configs (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    column_id   TEXT NOT NULL,
    label       TEXT NOT NULL DEFAULT '',
    type        TEXT NOT NULL DEFAULT '',
    required    BOOLEAN DEFAULT FALSE,
    "order"     INTEGER DEFAULT 0,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    options     JSONB DEFAULT '[]'
);

CREATE INDEX idx_crmfld_column_id     ON crm_field_configs(column_id);
CREATE INDEX idx_crmfld_tenant        ON crm_field_configs(tenant_id);
CREATE INDEX idx_crmfld_column_order  ON crm_field_configs(column_id, "order");

-- ─── lead_sources ─────────────────────────────────────────────────────────────
DROP TABLE IF EXISTS lead_sources CASCADE;

CREATE TABLE lead_sources (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    valor       TEXT NOT NULL DEFAULT '',
    nome        TEXT NOT NULL DEFAULT '',
    grupo       TEXT DEFAULT '',
    ativo       BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_leadsrc_tenant_valor ON lead_sources(tenant_id, valor);
CREATE INDEX idx_leadsrc_tenant_ativo        ON lead_sources(tenant_id, ativo);
