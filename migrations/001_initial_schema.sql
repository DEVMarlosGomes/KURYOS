-- ============================================================
--  KURYOS — Schema PostgreSQL (Supabase)
--  Migração: MongoDB → PostgreSQL
--  Estratégia: id TEXT (UUIDs gerados pela aplicação),
--              JSONB para arrays append-only/complexos,
--              tabelas separadas para entidades com CRUD próprio.
-- ============================================================

-- Extensão UUID (já disponível no Supabase)
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
--  SISTEMA / MULTI-TENANCY
-- ============================================================

CREATE TABLE IF NOT EXISTS tenants (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    slug        TEXT UNIQUE,
    plan        TEXT DEFAULT 'free',
    active      BOOLEAN DEFAULT TRUE,
    metadata    JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL REFERENCES tenants(id),
    email           TEXT NOT NULL,
    name            TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'vendedor',
    hashed_password TEXT,
    active          BOOLEAN DEFAULT TRUE,
    avatar_url      TEXT,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (tenant_id, email)
);

-- Sequências de IDs (substitui counters MongoDB)
CREATE TABLE IF NOT EXISTS counters (
    id          TEXT PRIMARY KEY,  -- ex: "sample:{projeto_id}:{tenant_id}"
    tenant_id   TEXT NOT NULL,
    seq         BIGINT NOT NULL DEFAULT 0,
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    user_id     TEXT,
    user_name   TEXT,
    action      TEXT NOT NULL,
    entity_type TEXT,
    entity_id   TEXT,
    before_data JSONB,
    after_data  JSONB,
    metadata    JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS notifications (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    user_id     TEXT,
    title       TEXT,
    body        TEXT,
    type        TEXT,
    read        BOOLEAN DEFAULT FALSE,
    entity_type TEXT,
    entity_id   TEXT,
    metadata    JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS email_logs (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    to_email    TEXT,
    subject     TEXT,
    body        TEXT,
    status      TEXT DEFAULT 'pending',
    error       TEXT,
    metadata    JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
--  FUNDAÇÕES / FASE 0 — Produtos, SKUs, Categorias, Materiais
-- ============================================================

CREATE TABLE IF NOT EXISTS categorias (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    nome            TEXT NOT NULL,
    codigo          TEXT,
    cat3            TEXT,
    descricao       TEXT,
    ativo           BOOLEAN DEFAULT TRUE,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS fragrancias (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    nome            TEXT NOT NULL,
    codigo          TEXT,
    fornecedor      TEXT,
    familia         TEXT,
    ativo           BOOLEAN DEFAULT TRUE,
    preco_kg        NUMERIC(12,4),
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS material_tipos (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    nome            TEXT NOT NULL,
    descricao       TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS materiais (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    nome            TEXT NOT NULL,
    codigo          TEXT,
    tipo_id         TEXT REFERENCES material_tipos(id),
    fornecedor      TEXT,
    unidade         TEXT,
    preco_unitario  NUMERIC(12,4),
    estoque_atual   NUMERIC(12,3) DEFAULT 0,
    estoque_minimo  NUMERIC(12,3) DEFAULT 0,
    ativo           BOOLEAN DEFAULT TRUE,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS graneis (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    nome            TEXT NOT NULL,
    codigo          TEXT,
    categoria_id    TEXT REFERENCES categorias(id),
    formula         JSONB DEFAULT '{}',  -- referência à fórmula P&D
    status          TEXT DEFAULT 'ativo',
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS produtos_pai (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    nome            TEXT NOT NULL,
    codigo          TEXT,
    categoria_id    TEXT REFERENCES categorias(id),
    granel_id       TEXT REFERENCES graneis(id),
    linha           TEXT,
    status          TEXT DEFAULT 'ativo',
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bom_items (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    produto_pai_id  TEXT REFERENCES produtos_pai(id),
    sku_id          TEXT,   -- FK para skus, adicionada após criar tabela skus
    material_id     TEXT REFERENCES materiais(id),
    quantidade      NUMERIC(12,4),
    unidade         TEXT,
    percentual      NUMERIC(8,4),
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
--  CRM 1 — CLIENTES
-- ============================================================

CREATE TABLE IF NOT EXISTS crm_clients (
    id                          TEXT PRIMARY KEY,
    tenant_id                   TEXT NOT NULL,
    stage                       TEXT NOT NULL DEFAULT 'prospeccao',
    -- Identificação
    nome_empresa                TEXT NOT NULL,
    cnpj                        TEXT,
    cnpj_normalized             TEXT,
    cli3                        TEXT,
    cli4                        TEXT,
    cli4_congelado              BOOLEAN DEFAULT FALSE,
    -- Contato
    contato_principal           JSONB DEFAULT '{}',
    contatos_adicionais         JSONB DEFAULT '[]',
    -- Origem
    canal_origem                TEXT,
    categoria_interesse         TEXT,
    origem_lead                 TEXT,
    lead_source_id              TEXT,
    -- Qualificação
    temperatura_lead            TEXT,
    responsavel_comercial       TEXT,
    segmento                    TEXT,
    porte                       TEXT,
    regiao                      TEXT,
    site                        TEXT,
    instagram                   TEXT,
    observacoes                 TEXT,
    has_grau2_anvisa            BOOLEAN DEFAULT FALSE,
    -- Qualificado
    decisores                   JSONB DEFAULT '[]',
    tem_marca_propria           BOOLEAN,
    tem_anvisa                  TEXT,
    volume_estimado_mensal      TEXT,
    fornecedor_atual            JSONB DEFAULT '{}',
    prazo_urgencia              TEXT,
    -- Negociação
    amostras_aprovadas          JSONB DEFAULT '[]',
    valor_estimado_projeto      NUMERIC(15,2),
    moq_negociado               TEXT,
    condicao_pagamento          TEXT,
    anvisa_necessario           JSONB DEFAULT '{}',
    concorrentes_envolvidos     JSONB DEFAULT '[]',
    -- Fechado
    data_pedido                 TIMESTAMPTZ,
    skus_confirmados            JSONB DEFAULT '[]',
    valor_primeiro_pedido       NUMERIC(15,2),
    previsao_segundo_pedido     TIMESTAMPTZ,
    -- Perdido
    motivo_perda                TEXT,
    -- Campos herdados / extras
    posicionamento              TEXT,
    tipo_servico                TEXT,
    restricoes_tecnicas         JSONB DEFAULT '[]',
    -- Meta
    historico_movimentacoes     JSONB DEFAULT '[]',
    ultima_atualizacao_temperatura TIMESTAMPTZ,
    created_by                  TEXT,
    created_by_name             TEXT,
    created_at                  TIMESTAMPTZ DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS lead_sources (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    nome        TEXT NOT NULL,
    ativo       BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
--  CRM 2 — PROJETOS
-- ============================================================

CREATE TABLE IF NOT EXISTS crm_projects (
    id                          TEXT PRIMARY KEY,
    tenant_id                   TEXT NOT NULL,
    cliente_id                  TEXT REFERENCES crm_clients(id),
    cliente_nome                TEXT,
    stage                       TEXT NOT NULL DEFAULT 'projeto_em_discussao',
    -- Brief
    nome_projeto                TEXT NOT NULL,
    categoria                   TEXT,
    briefing_tecnico            TEXT,
    responsavel_comercial       TEXT,
    responsavel_interno         TEXT,
    ideia_conceito              TEXT,
    referencia_mercado          TEXT,
    publico_alvo                TEXT,
    posicionamento              TEXT,
    faixa_preco_venda           NUMERIC(12,2),
    volume_estimado_pedido      INTEGER,
    tipo_servico                TEXT,
    sensorial_desejado          TEXT,
    restricoes_tecnicas         JSONB DEFAULT '[]',
    claims_desejados            TEXT,
    observacoes_livres          TEXT,
    -- Datas
    prazo_desejado_amostra      TEXT,
    prazo_prometido_cliente     TEXT,
    data_inicio_desenvolvimento TIMESTAMPTZ,
    data_ultima_amostra_enviada TIMESTAMPTZ,
    -- Pedido
    numero_amostras_solicitadas INTEGER DEFAULT 0,
    motivo_arquivamento         TEXT,
    -- Kickoff
    kickoff_id                  TEXT,
    kickoff_status              TEXT,
    -- Meta
    historico_movimentacoes     JSONB DEFAULT '[]',
    created_by                  TEXT,
    created_by_name             TEXT,
    created_at                  TIMESTAMPTZ DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
--  CRM 3 — AMOSTRAS + VARIAÇÕES
-- ============================================================

CREATE TABLE IF NOT EXISTS crm_samples (
    id                      TEXT PRIMARY KEY,
    tenant_id               TEXT NOT NULL,
    projeto_id              TEXT REFERENCES crm_projects(id),
    projeto_nome            TEXT,
    cliente_id              TEXT REFERENCES crm_clients(id),
    cliente_nome            TEXT,
    numero_amostra          TEXT,
    nome_produto            TEXT,
    categoria               TEXT,
    tipo_amostra            TEXT,
    parametro_variacao      TEXT,
    quantidade_por_variacao NUMERIC(12,3),
    unidade_quantidade      TEXT,
    prazo_entrega_cliente   TEXT,
    -- Briefing
    briefing_base           TEXT,
    briefing_especifico     TEXT,
    produto                 TEXT,
    objetivo_projeto        TEXT,
    aplicacoes_desenvolver  TEXT,
    ativos_claims           TEXT,
    referencias             TEXT,
    referencias_fotos       JSONB DEFAULT '[]',
    orcamento_projeto       TEXT,
    textura_esperada        TEXT,
    aplicacao               TEXT,
    sensorial               TEXT,
    ph                      TEXT,
    observacao_tecnica      TEXT,
    referencia_formula      TEXT,
    -- P&D responsável
    responsavel_pd          TEXT,
    -- Status
    stage                   TEXT DEFAULT 'solicitada',
    aprovacao_interna       BOOLEAN DEFAULT FALSE,
    aprovacao_externa       BOOLEAN DEFAULT FALSE,
    data_envio              TIMESTAMPTZ,
    enviado_comercial_em    TIMESTAMPTZ,
    aprovado_cliente_em     TIMESTAMPTZ,
    reprovacao_motivo       TEXT,
    resultado               TEXT,
    feedback_cliente        TEXT,
    direcoes_retrabalho     TEXT,
    rework_de_amostra_id    TEXT,
    rework_motivo           TEXT,
    -- Snapshot do projeto
    projeto_briefing        JSONB DEFAULT '{}',
    -- Meta
    historico_movimentacoes JSONB DEFAULT '[]',
    created_by              TEXT,
    created_by_name         TEXT,
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

-- Variações como tabela separada (atualizadas independentemente)
CREATE TABLE IF NOT EXISTS crm_sample_variacoes (
    id                      TEXT PRIMARY KEY,
    tenant_id               TEXT NOT NULL,
    sample_id               TEXT NOT NULL REFERENCES crm_samples(id) ON DELETE CASCADE,
    projeto_id              TEXT,
    cliente_id              TEXT,
    -- Identificação
    codigo                  TEXT NOT NULL,   -- ex: "2026-0042-a"
    letra                   TEXT,
    -- Briefing específico
    descricao_aplicacao     TEXT,
    percentual_fragrancia   NUMERIC(8,4),
    referencia_fragrancia   TEXT,
    fr_codigo               TEXT,
    custo_fragrancia        NUMERIC(12,4),
    observacoes_especificas TEXT,
    -- Status
    status                  TEXT DEFAULT 'solicitada',
    status_pd_raw           TEXT,
    aprovacao_interna       BOOLEAN DEFAULT FALSE,
    aprovacao_externa       BOOLEAN DEFAULT FALSE,
    motivo_retrabalho       TEXT,
    historico_retrabalhos   JSONB DEFAULT '[]',
    feedback_cliente        TEXT,
    direcoes_retrabalho     TEXT,
    resultado               TEXT,
    resultado_cliente       TEXT,
    resultado_cliente_registrado_por TEXT,
    resultado_cliente_registrado_em  TIMESTAMPTZ,
    reprovacao_motivo       TEXT,
    enviado_comercial_em    TIMESTAMPTZ,
    aprovado_cliente_em     TIMESTAMPTZ,
    -- SKU
    gera_sku                BOOLEAN DEFAULT FALSE,
    sku_id                  TEXT,
    codigo_sku              TEXT,
    -- P&D
    pd_card_id              TEXT,
    pd_request_id           TEXT,
    pd_status               TEXT,
    -- Histórico
    historico_status        JSONB DEFAULT '[]',
    -- Meta
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
--  SKUs
-- ============================================================

CREATE TABLE IF NOT EXISTS skus (
    id                          TEXT PRIMARY KEY,
    tenant_id                   TEXT NOT NULL,
    codigo_interno              TEXT,
    codigo_cliente              TEXT,
    nome_produto                TEXT,
    categoria                   TEXT,
    cliente_id                  TEXT REFERENCES crm_clients(id),
    cliente_nome                TEXT,
    projeto_id                  TEXT REFERENCES crm_projects(id),
    projeto_nome                TEXT,
    amostra_id                  TEXT REFERENCES crm_samples(id),
    amostra_variacao_id         TEXT REFERENCES crm_sample_variacoes(id),
    produto_pai_id              TEXT REFERENCES produtos_pai(id),
    descricao_aplicacao         TEXT,
    preco_unitario              NUMERIC(12,4) DEFAULT 0,
    moq                         INTEGER DEFAULT 0,
    anvisa                      JSONB DEFAULT '{}',
    status                      TEXT DEFAULT 'ativo',
    descontinuado_motivo        TEXT,
    descontinuado_em            TIMESTAMPTZ,
    descontinuado_por           TEXT,
    historico_pedidos           JSONB DEFAULT '[]',
    data_ultimo_pedido          TIMESTAMPTZ,
    frequencia_media_recompra_dias INTEGER DEFAULT 0,
    medias_producao             JSONB DEFAULT '{}',
    created_at                  TIMESTAMPTZ DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ DEFAULT NOW()
);

-- FK retroativa
ALTER TABLE bom_items ADD COLUMN IF NOT EXISTS sku_id_ref TEXT REFERENCES skus(id);

-- ============================================================
--  P&D — REQUESTS, CARDS, TESTES
-- ============================================================

CREATE TABLE IF NOT EXISTS pd_requests (
    id                  TEXT PRIMARY KEY,
    tenant_id           TEXT NOT NULL,
    numero_solicitacao  TEXT,
    titulo              TEXT,
    status              TEXT DEFAULT 'OPEN',
    prioridade          TEXT DEFAULT 'normal',
    cliente_id          TEXT,
    cliente_nome        TEXT,
    projeto_id          TEXT,
    amostra_id          TEXT,
    responsavel_pd      TEXT,
    tipo_produto        TEXT,
    categoria           TEXT,
    formula_referencia  TEXT,
    briefing            TEXT,
    especificacoes      JSONB DEFAULT '{}',
    sent_to_client      BOOLEAN DEFAULT FALSE,
    internal_approved   BOOLEAN DEFAULT FALSE,
    client_approved     BOOLEAN,
    cliente_feedback    TEXT,
    data_entrega        TIMESTAMPTZ,
    data_conclusao      TIMESTAMPTZ,
    historico_status    JSONB DEFAULT '[]',
    metadata            JSONB DEFAULT '{}',
    created_by          TEXT,
    created_by_name     TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pd_samples (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    request_id      TEXT REFERENCES pd_requests(id),
    nome            TEXT,
    status          TEXT DEFAULT 'OPEN',
    sent_to_client  BOOLEAN DEFAULT FALSE,
    internal_approved BOOLEAN DEFAULT FALSE,
    client_approved BOOLEAN,
    resultado       TEXT,
    feedback_cliente TEXT,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pd_cards (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    project_id      TEXT,
    projeto_id      TEXT,
    sample_id       TEXT,
    amostra_id      TEXT,
    variacao_id     TEXT,
    cliente_id      TEXT,
    client_name     TEXT,
    client_card_id  TEXT,
    linked_cliente_id TEXT,
    status          TEXT DEFAULT 'solicitado',
    titulo          TEXT,
    descricao       TEXT,
    responsavel     TEXT,
    responsavel_pd  TEXT,
    prioridade      TEXT DEFAULT 'normal',
    observacao      TEXT,
    data_entrega    TIMESTAMPTZ,
    metadata        JSONB DEFAULT '{}',
    historico       JSONB DEFAULT '[]',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pd_tests (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    request_id  TEXT REFERENCES pd_requests(id),
    sample_id   TEXT,
    card_id     TEXT,
    nome        TEXT NOT NULL,
    tipo        TEXT,
    resultado   TEXT DEFAULT 'PENDING',
    valor       TEXT,
    observacao  TEXT,
    realizado_por TEXT,
    realizado_em  TIMESTAMPTZ,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pd_lab_results (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    request_id      TEXT REFERENCES pd_requests(id),
    sample_id       TEXT,
    card_id         TEXT,
    estabilidade    JSONB DEFAULT '{}',
    ph              JSONB DEFAULT '{}',
    viscosidade     JSONB DEFAULT '{}',
    sensorial       JSONB DEFAULT '{}',
    compatibilidade JSONB DEFAULT '{}',
    metadata        JSONB DEFAULT '{}',
    updated_by      TEXT,
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pd_formulas (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    nome            TEXT,
    codigo          TEXT,
    request_id      TEXT,
    granel_id       TEXT,
    versao          INTEGER DEFAULT 1,
    status          TEXT DEFAULT 'rascunho',
    rendimento      NUMERIC(8,4),
    unidade_base    TEXT,
    observacoes     TEXT,
    metadata        JSONB DEFAULT '{}',
    created_by      TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pd_formula_items (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    formula_id      TEXT REFERENCES pd_formulas(id) ON DELETE CASCADE,
    material_id     TEXT REFERENCES materiais(id),
    nome_material   TEXT,
    percentual      NUMERIC(8,4),
    quantidade      NUMERIC(12,4),
    unidade         TEXT,
    fase            TEXT,
    observacao      TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pd_documents (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    request_id      TEXT,
    tipo            TEXT,
    nome            TEXT,
    url             TEXT,
    versao          INTEGER DEFAULT 1,
    status          TEXT DEFAULT 'ativo',
    metadata        JSONB DEFAULT '{}',
    created_by      TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pd_document_versions (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    document_id     TEXT REFERENCES pd_documents(id),
    versao          INTEGER,
    url             TEXT,
    metadata        JSONB DEFAULT '{}',
    created_by      TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pd_ficha_tecnica (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    sku_id          TEXT REFERENCES skus(id),
    request_id      TEXT,
    conteudo        JSONB DEFAULT '{}',
    versao          INTEGER DEFAULT 1,
    status          TEXT DEFAULT 'rascunho',
    created_by      TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pd_stability_studies (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    request_id      TEXT,
    sku_id          TEXT,
    nome            TEXT,
    tipo            TEXT,
    condicoes       JSONB DEFAULT '[]',
    status          TEXT DEFAULT 'em_andamento',
    data_inicio     TIMESTAMPTZ,
    data_fim        TIMESTAMPTZ,
    metadata        JSONB DEFAULT '{}',
    created_by      TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pd_stability_readings (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    study_id        TEXT REFERENCES pd_stability_studies(id),
    tempo           TEXT,
    condicao        TEXT,
    resultados      JSONB DEFAULT '{}',
    aprovado        BOOLEAN,
    observacoes     TEXT,
    realizado_por   TEXT,
    realizado_em    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pd_costs (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    request_id      TEXT,
    sku_id          TEXT,
    formula_id      TEXT,
    versao          INTEGER DEFAULT 1,
    custo_materias  NUMERIC(15,4),
    custo_mao_obra  NUMERIC(15,4),
    custo_overhead  NUMERIC(15,4),
    custo_total     NUMERIC(15,4),
    markup          NUMERIC(8,4),
    preco_sugerido  NUMERIC(15,4),
    detalhes        JSONB DEFAULT '{}',
    created_by      TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pd_catalog (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    sku_id          TEXT REFERENCES skus(id),
    nome            TEXT,
    descricao       TEXT,
    categoria       TEXT,
    status          TEXT DEFAULT 'ativo',
    preco_lista     NUMERIC(15,4),
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pd_catalog_price_history (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    catalog_id      TEXT REFERENCES pd_catalog(id),
    preco_anterior  NUMERIC(15,4),
    preco_novo      NUMERIC(15,4),
    motivo          TEXT,
    alterado_por    TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pd_stock_items (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    sku_id          TEXT REFERENCES skus(id),
    lote            TEXT,
    quantidade      NUMERIC(12,3),
    unidade         TEXT,
    localizacao     TEXT,
    validade        TIMESTAMPTZ,
    status          TEXT DEFAULT 'disponivel',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pd_stock_movements (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    item_id         TEXT REFERENCES pd_stock_items(id),
    tipo            TEXT,
    quantidade      NUMERIC(12,3),
    origem          TEXT,
    destino         TEXT,
    referencia_id   TEXT,
    realizado_por   TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pd_batch_orders (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    sku_id          TEXT,
    quantidade      NUMERIC(12,3),
    status          TEXT DEFAULT 'pendente',
    metadata        JSONB DEFAULT '{}',
    created_by      TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pd_sample_batches (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    request_id      TEXT,
    quantidade      NUMERIC(12,3),
    unidade         TEXT,
    status          TEXT DEFAULT 'pendente',
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pd_approvals (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    request_id      TEXT,
    tipo            TEXT,
    status          TEXT DEFAULT 'pendente',
    aprovado_por    TEXT,
    aprovado_em     TIMESTAMPTZ,
    observacao      TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pd_updates (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    request_id      TEXT,
    tipo            TEXT,
    conteudo        TEXT,
    autor_id        TEXT,
    autor_nome      TEXT,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pd_pending_items (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    request_id      TEXT,
    descricao       TEXT,
    responsavel     TEXT,
    prazo           TIMESTAMPTZ,
    resolvido       BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pd_request_status_history (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    request_id      TEXT REFERENCES pd_requests(id),
    status_anterior TEXT,
    status_novo     TEXT,
    alterado_por    TEXT,
    observacao      TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pd_developments (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    request_id      TEXT,
    etapa           TEXT,
    descricao       TEXT,
    status          TEXT DEFAULT 'pendente',
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS formula_cost_versions (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    formula_id      TEXT,
    versao          INTEGER,
    custo_total     NUMERIC(15,4),
    detalhes        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS formula_procedure_phases (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    formula_id      TEXT REFERENCES pd_formulas(id),
    fase            TEXT,
    descricao       TEXT,
    temperatura     TEXT,
    tempo           TEXT,
    ordem           INTEGER,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
--  CQ — CONTROLE DE QUALIDADE
-- ============================================================

CREATE TABLE IF NOT EXISTS cq_instrumentos (
    id                  TEXT PRIMARY KEY,
    tenant_id           TEXT NOT NULL,
    nome                TEXT NOT NULL,
    codigo              TEXT,
    tipo                TEXT,
    fabricante          TEXT,
    modelo              TEXT,
    numero_serie        TEXT,
    localizacao         TEXT,
    status              TEXT DEFAULT 'ativo',
    proxima_calibracao  TIMESTAMPTZ,
    ultima_calibracao   TIMESTAMPTZ,
    calibracao_periodicidade_dias INTEGER,
    certificado_url     TEXT,
    metadata            JSONB DEFAULT '{}',
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cq_registros_analise (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    instrumento_id  TEXT REFERENCES cq_instrumentos(id),
    sku_id          TEXT,
    lote            TEXT,
    tipo_analise    TEXT,
    resultado       TEXT,
    aprovado        BOOLEAN,
    valor_medido    TEXT,
    especificacao   TEXT,
    observacoes     TEXT,
    realizado_por   TEXT,
    realizado_em    TIMESTAMPTZ,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cq_retencoes (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    sku_id          TEXT,
    lote            TEXT,
    quantidade      NUMERIC(12,3),
    unidade         TEXT,
    localizacao     TEXT,
    validade        TIMESTAMPTZ,
    status          TEXT DEFAULT 'retido',
    motivo          TEXT,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cq_rncs (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    numero          TEXT,
    tipo            TEXT,
    descricao       TEXT,
    sku_id          TEXT,
    lote            TEXT,
    gravidade       TEXT,
    status          TEXT DEFAULT 'aberto',
    causa_raiz      TEXT,
    acao_corretiva  TEXT,
    responsavel     TEXT,
    prazo           TIMESTAMPTZ,
    fechado_em      TIMESTAMPTZ,
    metadata        JSONB DEFAULT '{}',
    created_by      TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cq_checklists (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    nome            TEXT,
    tipo            TEXT,
    itens           JSONB DEFAULT '[]',
    ativo           BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cq_status_lote (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    lote            TEXT,
    sku_id          TEXT,
    status          TEXT DEFAULT 'em_analise',
    aprovado        BOOLEAN,
    observacoes     TEXT,
    liberado_por    TEXT,
    liberado_em     TIMESTAMPTZ,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
--  COMPRAS
-- ============================================================

CREATE TABLE IF NOT EXISTS compras_fornecedores (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    nome            TEXT NOT NULL,
    cnpj            TEXT,
    contato         JSONB DEFAULT '{}',
    status          TEXT DEFAULT 'ativo',
    categoria       TEXT,
    avaliacao       JSONB DEFAULT '{}',
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS homologacao_fornecedores (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    fornecedor_id   TEXT REFERENCES compras_fornecedores(id),
    status          TEXT DEFAULT 'pendente',
    resultado       TEXT,
    checklist       JSONB DEFAULT '{}',
    avaliado_por    TEXT,
    avaliado_em     TIMESTAMPTZ,
    validade        TIMESTAMPTZ,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS homologacao_mps (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    fornecedor_id   TEXT REFERENCES compras_fornecedores(id),
    material_id     TEXT REFERENCES materiais(id),
    status          TEXT DEFAULT 'pendente',
    resultado       TEXT,
    especificacoes  JSONB DEFAULT '{}',
    avaliado_por    TEXT,
    avaliado_em     TIMESTAMPTZ,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS compras_itens (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    material_id     TEXT REFERENCES materiais(id),
    fornecedor_id   TEXT REFERENCES compras_fornecedores(id),
    quantidade      NUMERIC(12,3),
    unidade         TEXT,
    preco_unitario  NUMERIC(12,4),
    prazo_entrega   TEXT,
    status          TEXT DEFAULT 'pendente',
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS compras_pos (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    numero_po       TEXT,
    fornecedor_id   TEXT REFERENCES compras_fornecedores(id),
    itens           JSONB DEFAULT '[]',
    valor_total     NUMERIC(15,2),
    status          TEXT DEFAULT 'rascunho',
    data_emissao    TIMESTAMPTZ,
    data_entrega    TIMESTAMPTZ,
    observacoes     TEXT,
    metadata        JSONB DEFAULT '{}',
    created_by      TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ordens_compra (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    numero          TEXT,
    fornecedor_id   TEXT REFERENCES compras_fornecedores(id),
    itens           JSONB DEFAULT '[]',
    valor_total     NUMERIC(15,2),
    status          TEXT DEFAULT 'aberta',
    data_emissao    TIMESTAMPTZ,
    data_entrega    TIMESTAMPTZ,
    metadata        JSONB DEFAULT '{}',
    created_by      TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS compras_demandas (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    material_id     TEXT,
    quantidade      NUMERIC(12,3),
    prioridade      TEXT DEFAULT 'normal',
    status          TEXT DEFAULT 'pendente',
    origem          TEXT,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS compras_condicoes_comerciais (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    fornecedor_id   TEXT REFERENCES compras_fornecedores(id),
    material_id     TEXT,
    preco           NUMERIC(12,4),
    moq             NUMERIC(12,3),
    prazo_entrega   INTEGER,
    validade        TIMESTAMPTZ,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS compras_mrp_rodadas (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    status          TEXT DEFAULT 'processando',
    resultado       JSONB DEFAULT '{}',
    executado_por   TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
--  PEDIDOS / ORDERS
-- ============================================================

CREATE TABLE IF NOT EXISTS orders (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    numero_pedido   TEXT,
    cliente_id      TEXT REFERENCES crm_clients(id),
    cliente_nome    TEXT,
    status          TEXT DEFAULT 'rascunho',
    tipo            TEXT,
    itens           JSONB DEFAULT '[]',
    total_pedido    NUMERIC(15,2),
    condicao_pagamento TEXT,
    data_entrega    TIMESTAMPTZ,
    observacoes     TEXT,
    metadata        JSONB DEFAULT '{}',
    created_by      TEXT,
    created_by_name TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS order_audit_log (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    order_id        TEXT REFERENCES orders(id),
    action          TEXT,
    before_data     JSONB,
    after_data      JSONB,
    user_id         TEXT,
    user_name       TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS order_material_requirements (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    order_id        TEXT REFERENCES orders(id),
    material_id     TEXT REFERENCES materiais(id),
    quantidade      NUMERIC(12,3),
    status          TEXT DEFAULT 'pendente',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ops (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    order_id        TEXT REFERENCES orders(id),
    numero_op       TEXT,
    sku_id          TEXT REFERENCES skus(id),
    quantidade      NUMERIC(12,3),
    status          TEXT DEFAULT 'pendente',
    data_inicio     TIMESTAMPTZ,
    data_fim        TIMESTAMPTZ,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS propostas_comerciais (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    projeto_id      TEXT REFERENCES crm_projects(id),
    cliente_id      TEXT,
    tipo_proposta   TEXT,
    -- Bloco A
    tipo_produto    TEXT,
    variacao_produto TEXT,
    categoria       TEXT,
    posicionamento  TEXT,
    -- Bloco B
    items_pedido    JSONB DEFAULT '[]',
    -- Condições
    condicao_pagamento TEXT,
    prazo_entrega   TEXT,
    validade_proposta TEXT,
    moq             TEXT,
    -- Status
    status          TEXT DEFAULT 'rascunho',
    aprovado_em     TIMESTAMPTZ,
    aprovado_por    TEXT,
    observacoes     TEXT,
    metadata        JSONB DEFAULT '{}',
    created_by      TEXT,
    created_by_name TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
--  ESTOQUE
-- ============================================================

CREATE TABLE IF NOT EXISTS estoque_items (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    material_id     TEXT REFERENCES materiais(id),
    sku_id          TEXT REFERENCES skus(id),
    lote            TEXT,
    quantidade      NUMERIC(12,3) DEFAULT 0,
    unidade         TEXT,
    localizacao     TEXT,
    validade        TIMESTAMPTZ,
    status          TEXT DEFAULT 'disponivel',
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS estoque_movimentos (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    item_id         TEXT REFERENCES estoque_items(id),
    tipo            TEXT,   -- entrada, saida, ajuste
    quantidade      NUMERIC(12,3),
    referencia_id   TEXT,
    referencia_tipo TEXT,
    realizado_por   TEXT,
    observacao      TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
--  RECEBIMENTO
-- ============================================================

CREATE TABLE IF NOT EXISTS recebimentos (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    ordem_compra_id TEXT REFERENCES ordens_compra(id),
    fornecedor_id   TEXT REFERENCES compras_fornecedores(id),
    numero_nf       TEXT,
    status          TEXT DEFAULT 'pendente',
    itens_recebidos JSONB DEFAULT '[]',
    data_recebimento TIMESTAMPTZ,
    metadata        JSONB DEFAULT '{}',
    created_by      TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS recebimento_notas (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    recebimento_id  TEXT REFERENCES recebimentos(id),
    numero_nf       TEXT,
    valor           NUMERIC(15,2),
    url_xml         TEXT,
    url_pdf         TEXT,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS recebimento_sla_config (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    tipo            TEXT,
    sla_horas       INTEGER,
    metadata        JSONB DEFAULT '{}',
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
--  RETRABALHO
-- ============================================================

CREATE TABLE IF NOT EXISTS retrabalho_ordens (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    sku_id          TEXT REFERENCES skus(id),
    lote            TEXT,
    motivo          TEXT,
    status          TEXT DEFAULT 'aberta',
    quantidade      NUMERIC(12,3),
    responsavel     TEXT,
    prazo           TIMESTAMPTZ,
    fechado_em      TIMESTAMPTZ,
    metadata        JSONB DEFAULT '{}',
    created_by      TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
--  EXPEDIÇÃO
-- ============================================================

CREATE TABLE IF NOT EXISTS expedicao_ordens (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    order_id        TEXT REFERENCES orders(id),
    status          TEXT DEFAULT 'pendente',
    itens           JSONB DEFAULT '[]',
    transportadora  TEXT,
    codigo_rastreio TEXT,
    data_expedicao  TIMESTAMPTZ,
    metadata        JSONB DEFAULT '{}',
    created_by      TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
--  FATURAMENTO
-- ============================================================

CREATE TABLE IF NOT EXISTS faturamento_notas (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    order_id        TEXT REFERENCES orders(id),
    numero_nf       TEXT,
    valor           NUMERIC(15,2),
    status          TEXT DEFAULT 'pendente',
    data_emissao    TIMESTAMPTZ,
    data_vencimento TIMESTAMPTZ,
    url_xml         TEXT,
    url_pdf         TEXT,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS faturamento_duplicatas (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    nota_id         TEXT REFERENCES faturamento_notas(id),
    numero          TEXT,
    valor           NUMERIC(15,2),
    vencimento      TIMESTAMPTZ,
    status          TEXT DEFAULT 'pendente',
    pago_em         TIMESTAMPTZ,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
--  PCP — PLANEJAMENTO E CONTROLE DA PRODUÇÃO
-- ============================================================

CREATE TABLE IF NOT EXISTS pcp_linhas (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    nome            TEXT NOT NULL,
    capacidade_dia  NUMERIC(12,3),
    status          TEXT DEFAULT 'ativa',
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pcp_calendario (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    linha_id        TEXT REFERENCES pcp_linhas(id),
    data            DATE,
    disponivel      BOOLEAN DEFAULT TRUE,
    turno           TEXT,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pcp_programacao (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    op_id           TEXT REFERENCES ops(id),
    linha_id        TEXT REFERENCES pcp_linhas(id),
    data_inicio     TIMESTAMPTZ,
    data_fim        TIMESTAMPTZ,
    status          TEXT DEFAULT 'programado',
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pcp_lotes (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    programacao_id  TEXT REFERENCES pcp_programacao(id),
    sku_id          TEXT REFERENCES skus(id),
    numero_lote     TEXT,
    quantidade      NUMERIC(12,3),
    status          TEXT DEFAULT 'pendente',
    data_producao   TIMESTAMPTZ,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
--  KICKOFFS
-- ============================================================

CREATE TABLE IF NOT EXISTS kickoffs (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    numero_kickoff  TEXT,
    projeto_id      TEXT REFERENCES crm_projects(id),
    cliente_id      TEXT REFERENCES crm_clients(id),
    status          TEXT DEFAULT 'pendente',
    kickoff_status  TEXT DEFAULT 'pendente',
    bloco1          JSONB DEFAULT '{}',
    bloco2          JSONB DEFAULT '{}',
    bloco3          JSONB DEFAULT '{}',
    metadata        JSONB DEFAULT '{}',
    created_by      TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
--  CONTRATOS
-- ============================================================

CREATE TABLE IF NOT EXISTS contratos (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    cliente_id      TEXT REFERENCES crm_clients(id),
    tipo            TEXT,
    status          TEXT DEFAULT 'rascunho',
    numero          TEXT,
    valor           NUMERIC(15,2),
    data_inicio     TIMESTAMPTZ,
    data_fim        TIMESTAMPTZ,
    url_documento   TEXT,
    clausulas       JSONB DEFAULT '[]',
    metadata        JSONB DEFAULT '{}',
    created_by      TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
--  TASKS / WORKFLOW
-- ============================================================

CREATE TABLE IF NOT EXISTS tasks (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    titulo          TEXT NOT NULL,
    descricao       TEXT,
    tipo            TEXT,
    categoria       TEXT,
    status          TEXT DEFAULT 'pendente',
    blocking        BOOLEAN DEFAULT FALSE,
    entity_type     TEXT,
    entity_id       TEXT,
    responsavel_id  TEXT,
    responsavel_nome TEXT,
    prazo           TIMESTAMPTZ,
    concluido_em    TIMESTAMPTZ,
    concluido_por   TEXT,
    metadata        JSONB DEFAULT '{}',
    created_by      TEXT,
    created_by_name TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS crm_tasks (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    titulo          TEXT NOT NULL,
    descricao       TEXT,
    tipo            TEXT,
    status          TEXT DEFAULT 'pendente',
    entity_type     TEXT,
    entity_id       TEXT,
    responsavel_id  TEXT,
    prazo           TIMESTAMPTZ,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS workflow_tasks (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    titulo          TEXT NOT NULL,
    descricao       TEXT,
    tipo            TEXT,
    categoria       TEXT,
    status          TEXT DEFAULT 'pendente',
    blocking        BOOLEAN DEFAULT FALSE,
    entity_type     TEXT,
    entity_id       TEXT,
    responsavel_id  TEXT,
    responsavel_nome TEXT,
    prazo           TIMESTAMPTZ,
    concluido_em    TIMESTAMPTZ,
    concluido_por   TEXT,
    metadata        JSONB DEFAULT '{}',
    created_by      TEXT,
    created_by_name TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
--  ALERTAS / CONFIGURAÇÕES CRM
-- ============================================================

CREATE TABLE IF NOT EXISTS crm_alerts (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    tipo            TEXT,
    entity_type     TEXT,
    entity_id       TEXT,
    titulo          TEXT,
    mensagem        TEXT,
    lido            BOOLEAN DEFAULT FALSE,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS crm_column_configs (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    modulo          TEXT,
    configuracao    JSONB DEFAULT '{}',
    updated_by      TEXT,
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS crm_field_configs (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    modulo          TEXT,
    campo           TEXT,
    label           TEXT,
    visivel         BOOLEAN DEFAULT TRUE,
    obrigatorio     BOOLEAN DEFAULT FALSE,
    metadata        JSONB DEFAULT '{}',
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
--  OUTROS
-- ============================================================

CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    entity_type     TEXT,
    entity_id       TEXT,
    conteudo        TEXT,
    tipo            TEXT DEFAULT 'text',
    autor_id        TEXT,
    autor_nome      TEXT,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS files (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    entity_type     TEXT,
    entity_id       TEXT,
    nome            TEXT,
    tipo_mime       TEXT,
    url             TEXT,
    tamanho_bytes   BIGINT,
    metadata        JSONB DEFAULT '{}',
    uploaded_by     TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS requirements_items (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    entity_type     TEXT,
    entity_id       TEXT,
    titulo          TEXT,
    descricao       TEXT,
    status          TEXT DEFAULT 'pendente',
    prioridade      TEXT DEFAULT 'normal',
    metadata        JSONB DEFAULT '{}',
    created_by      TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Legacy pipeline (cards system - substituído pelo CRM v3)
CREATE TABLE IF NOT EXISTS cards (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    stage       TEXT,
    data        JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS card_amostras (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    card_id     TEXT REFERENCES cards(id),
    data        JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS card_history (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    card_id     TEXT,
    evento      TEXT,
    data        JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS card_products (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    card_id     TEXT,
    data        JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pipelines (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    nome        TEXT,
    etapas      JSONB DEFAULT '[]',
    metadata    JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS stages (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    pipeline_id TEXT REFERENCES pipelines(id),
    nome        TEXT,
    ordem       INTEGER,
    metadata    JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS fields (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    entity_type TEXT,
    nome        TEXT,
    tipo        TEXT,
    obrigatorio BOOLEAN DEFAULT FALSE,
    metadata    JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS field_values (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    field_id    TEXT REFERENCES fields(id),
    entity_id   TEXT,
    valor       TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS system_status (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    modulo      TEXT,
    status      TEXT,
    mensagem    TEXT,
    metadata    JSONB DEFAULT '{}',
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
--  ÍNDICES — Performance + Multi-tenancy
-- ============================================================

-- Sistema
CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_tenant ON audit_logs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_entity ON audit_logs(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_notifications_tenant_user ON notifications(tenant_id, user_id);
CREATE INDEX IF NOT EXISTS idx_counters_tenant ON counters(tenant_id);

-- CRM
CREATE INDEX IF NOT EXISTS idx_crm_clients_tenant ON crm_clients(tenant_id);
CREATE INDEX IF NOT EXISTS idx_crm_clients_stage ON crm_clients(tenant_id, stage);
CREATE INDEX IF NOT EXISTS idx_crm_clients_cnpj ON crm_clients(tenant_id, cnpj_normalized);
CREATE INDEX IF NOT EXISTS idx_crm_projects_tenant ON crm_projects(tenant_id);
CREATE INDEX IF NOT EXISTS idx_crm_projects_stage ON crm_projects(tenant_id, stage);
CREATE INDEX IF NOT EXISTS idx_crm_projects_cliente ON crm_projects(tenant_id, cliente_id);
CREATE INDEX IF NOT EXISTS idx_crm_samples_tenant ON crm_samples(tenant_id);
CREATE INDEX IF NOT EXISTS idx_crm_samples_projeto ON crm_samples(tenant_id, projeto_id);
CREATE INDEX IF NOT EXISTS idx_crm_sample_variacoes_sample ON crm_sample_variacoes(sample_id);
CREATE INDEX IF NOT EXISTS idx_crm_sample_variacoes_tenant ON crm_sample_variacoes(tenant_id);

-- SKUs
CREATE INDEX IF NOT EXISTS idx_skus_tenant ON skus(tenant_id);
CREATE INDEX IF NOT EXISTS idx_skus_cliente ON skus(tenant_id, cliente_id);
CREATE INDEX IF NOT EXISTS idx_skus_codigo ON skus(tenant_id, codigo_interno);

-- P&D
CREATE INDEX IF NOT EXISTS idx_pd_requests_tenant ON pd_requests(tenant_id);
CREATE INDEX IF NOT EXISTS idx_pd_cards_tenant ON pd_cards(tenant_id);
CREATE INDEX IF NOT EXISTS idx_pd_cards_project ON pd_cards(tenant_id, project_id);
CREATE INDEX IF NOT EXISTS idx_pd_tests_request ON pd_tests(tenant_id, request_id);
CREATE INDEX IF NOT EXISTS idx_pd_lab_results_request ON pd_lab_results(tenant_id, request_id);

-- Tasks
CREATE INDEX IF NOT EXISTS idx_tasks_tenant ON tasks(tenant_id);
CREATE INDEX IF NOT EXISTS idx_tasks_entity ON tasks(tenant_id, entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_workflow_tasks_tenant ON workflow_tasks(tenant_id);
CREATE INDEX IF NOT EXISTS idx_workflow_tasks_entity ON workflow_tasks(tenant_id, entity_type, entity_id);

-- Compras
CREATE INDEX IF NOT EXISTS idx_compras_fornecedores_tenant ON compras_fornecedores(tenant_id);
CREATE INDEX IF NOT EXISTS idx_compras_pos_tenant ON compras_pos(tenant_id);

-- Orders
CREATE INDEX IF NOT EXISTS idx_orders_tenant ON orders(tenant_id);
CREATE INDEX IF NOT EXISTS idx_orders_cliente ON orders(tenant_id, cliente_id);

-- ============================================================
--  RLS — Row Level Security (Supabase multi-tenancy)
--  Ativada por tabela; usa o JWT claim 'tenant_id' do usuário.
--  Aplique após configurar Supabase Auth com custom claims.
-- ============================================================

-- Template para habilitar RLS (descomente e aplique por módulo):
--
-- ALTER TABLE crm_clients ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY "tenant_isolation" ON crm_clients
--   FOR ALL USING (tenant_id = current_setting('app.tenant_id', TRUE));
--
-- No FastAPI, antes de cada request:
--   await conn.execute("SET app.tenant_id = $1", tenant_id)
