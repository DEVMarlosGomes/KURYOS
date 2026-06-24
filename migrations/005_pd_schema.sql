-- 005_pd_schema.sql
-- P&D Module — 25 tabelas PostgreSQL.
-- Execute no Supabase SQL Editor (DROP + CREATE = idempotente para setup inicial).

-- ─── pd_requests ──────────────────────────────────────────────────────────────
DROP TABLE IF EXISTS pd_requests CASCADE;
CREATE TABLE pd_requests (
    id                  TEXT PRIMARY KEY,
    tenant_id           TEXT NOT NULL,
    client_card_id      TEXT,
    client_name         TEXT DEFAULT '',
    project_name        TEXT NOT NULL DEFAULT '',
    technical_name      TEXT DEFAULT '',
    commercial_name     TEXT DEFAULT '',
    internal_code       TEXT DEFAULT '',
    request_type        TEXT DEFAULT '',
    category            TEXT DEFAULT '',
    description         TEXT DEFAULT '',
    "references"        TEXT DEFAULT '',
    restrictions        TEXT DEFAULT '',
    volume              TEXT DEFAULT '',
    packaging           TEXT DEFAULT '',
    priority            TEXT DEFAULT 'normal',
    deadline            TEXT,
    status              TEXT DEFAULT 'OPEN',
    is_internal_research BOOLEAN DEFAULT FALSE,
    kickoff_completed   BOOLEAN DEFAULT FALSE,
    amostra_id          TEXT,
    linked_amostra_id   TEXT,
    linked_variacao_id  TEXT,
    crm_project_id      TEXT,
    pd_card_id          TEXT,
    sku                 TEXT DEFAULT '',
    vinculado_em        TEXT,
    vinculado_por       TEXT,
    created_by          TEXT,
    created_by_name     TEXT DEFAULT '',
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_pdrq_tenant_status    ON pd_requests(tenant_id, status);
CREATE INDEX idx_pdrq_tenant_created   ON pd_requests(tenant_id, created_at DESC);
CREATE INDEX idx_pdrq_tenant_client    ON pd_requests(tenant_id, client_card_id);
CREATE INDEX idx_pdrq_tenant_amostra   ON pd_requests(tenant_id, amostra_id);

-- ─── pd_request_status_history ────────────────────────────────────────────────
DROP TABLE IF EXISTS pd_request_status_history CASCADE;
CREATE TABLE pd_request_status_history (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    pd_request_id   TEXT NOT NULL,
    from_status     TEXT,
    to_status       TEXT NOT NULL,
    changed_by      TEXT,
    changed_by_name TEXT DEFAULT '',
    comment         TEXT DEFAULT '',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_pdrsh_req     ON pd_request_status_history(pd_request_id, created_at DESC);
CREATE INDEX idx_pdrsh_tenant  ON pd_request_status_history(tenant_id, created_at DESC);

-- ─── pd_developments ──────────────────────────────────────────────────────────
DROP TABLE IF EXISTS pd_developments CASCADE;
CREATE TABLE pd_developments (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    pd_request_id   TEXT NOT NULL,
    assigned_to     TEXT,
    assigned_to_name TEXT DEFAULT '',
    lab_responsible  TEXT,
    current_version  INTEGER DEFAULT 0,
    status          TEXT DEFAULT 'active',
    started_at      TEXT,
    completed_at    TEXT,
    is_internal_research BOOLEAN DEFAULT FALSE
);
CREATE UNIQUE INDEX idx_pddev_req ON pd_developments(pd_request_id);
CREATE INDEX        idx_pddev_tenant ON pd_developments(tenant_id);

-- ─── pd_formulas ──────────────────────────────────────────────────────────────
DROP TABLE IF EXISTS pd_formulas CASCADE;
CREATE TABLE pd_formulas (
    id               TEXT PRIMARY KEY,
    tenant_id        TEXT NOT NULL,
    development_id   TEXT NOT NULL,
    version          INTEGER NOT NULL DEFAULT 1,
    name             TEXT DEFAULT '',
    notes            TEXT DEFAULT '',
    volume           NUMERIC(14,4) DEFAULT 0,
    volume_unit      TEXT DEFAULT 'mL',
    indice_perdas    NUMERIC(8,4) DEFAULT 0,
    cotacao_usd      NUMERIC(10,4) DEFAULT 6.0,
    fragrance_target NUMERIC(8,4),
    locked           BOOLEAN DEFAULT FALSE,
    locked_at        TEXT,
    locked_by        TEXT,
    locked_by_name   TEXT DEFAULT '',
    created_by       TEXT,
    created_by_name  TEXT DEFAULT '',
    created_at       TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_pdform_dev          ON pd_formulas(development_id, version DESC);
CREATE INDEX idx_pdform_tenant       ON pd_formulas(tenant_id);

-- ─── pd_formula_items ─────────────────────────────────────────────────────────
DROP TABLE IF EXISTS pd_formula_items CASCADE;
CREATE TABLE pd_formula_items (
    id                    TEXT PRIMARY KEY,
    formula_id            TEXT NOT NULL,
    ingredient_name       TEXT NOT NULL DEFAULT '',
    percentage            NUMERIC(10,6) DEFAULT 0,
    price_per_kg          NUMERIC(14,6) DEFAULT 0,
    price_usd             NUMERIC(14,6),
    cost_brl              NUMERIC(14,6) DEFAULT 0,
    cost_kg_usd           NUMERIC(14,6),
    cost_brl_via_cambio   NUMERIC(14,6),
    fornecedor            TEXT DEFAULT '',
    phase                 TEXT DEFAULT '',
    "function"            TEXT DEFAULT '',
    catalog_id            TEXT
);
CREATE INDEX idx_pdfi_formula  ON pd_formula_items(formula_id);
CREATE INDEX idx_pdfi_catalog  ON pd_formula_items(catalog_id) WHERE catalog_id IS NOT NULL;

-- ─── pd_tests ─────────────────────────────────────────────────────────────────
DROP TABLE IF EXISTS pd_tests CASCADE;
CREATE TABLE pd_tests (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    development_id  TEXT NOT NULL,
    test_type       TEXT DEFAULT '',
    dados           JSONB DEFAULT '{}',
    status          TEXT DEFAULT 'PENDING',
    created_by      TEXT,
    created_by_name TEXT DEFAULT '',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_pdtst_dev     ON pd_tests(development_id, created_at DESC);
CREATE INDEX idx_pdtst_tenant  ON pd_tests(tenant_id);

-- ─── pd_lab_results ───────────────────────────────────────────────────────────
DROP TABLE IF EXISTS pd_lab_results CASCADE;
CREATE TABLE pd_lab_results (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    development_id  TEXT NOT NULL,
    estabilidade    JSONB DEFAULT '{}',
    ph              JSONB DEFAULT '{}',
    viscosidade     JSONB DEFAULT '{}',
    sensorial       JSONB DEFAULT '{}',
    compatibilidade JSONB DEFAULT '{}',
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_by      TEXT,
    updated_by_name TEXT DEFAULT ''
);
CREATE UNIQUE INDEX idx_pdlr_dev    ON pd_lab_results(development_id);
CREATE INDEX        idx_pdlr_tenant ON pd_lab_results(tenant_id);

-- ─── pd_stability_studies ─────────────────────────────────────────────────────
DROP TABLE IF EXISTS pd_stability_studies CASCADE;
CREATE TABLE pd_stability_studies (
    id                  TEXT PRIMARY KEY,
    tenant_id           TEXT NOT NULL,
    pd_card_id          TEXT,
    amostra_id          TEXT,
    amostra_variacao_id TEXT,
    status              TEXT DEFAULT 'ativo',
    conditions          JSONB DEFAULT '[]',
    summary             JSONB DEFAULT '{}',
    d0_completed        BOOLEAN DEFAULT FALSE,
    started_at          TEXT,
    created_by          TEXT,
    created_by_name     TEXT DEFAULT '',
    extra               JSONB DEFAULT '{}',
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_pdss_tenant   ON pd_stability_studies(tenant_id, created_at DESC);
CREATE INDEX idx_pdss_amostra  ON pd_stability_studies(tenant_id, amostra_id);
CREATE INDEX idx_pdss_card     ON pd_stability_studies(pd_card_id);

-- ─── pd_stability_readings ────────────────────────────────────────────────────
DROP TABLE IF EXISTS pd_stability_readings CASCADE;
CREATE TABLE pd_stability_readings (
    id                  TEXT PRIMARY KEY,
    tenant_id           TEXT NOT NULL,
    study_id            TEXT NOT NULL,
    pd_card_id          TEXT,
    amostra_id          TEXT,
    amostra_variacao_id TEXT,
    condition_code      TEXT NOT NULL,
    condition_label     TEXT DEFAULT '',
    day_offset          INTEGER NOT NULL DEFAULT 0,
    reading_at          TEXT,
    parameters          JSONB DEFAULT '{}',
    notes               TEXT DEFAULT '',
    photo_urls          JSONB DEFAULT '[]',
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    created_by          TEXT,
    created_by_name     TEXT DEFAULT ''
);
CREATE UNIQUE INDEX idx_pdsr_study_cond_day ON pd_stability_readings(study_id, condition_code, day_offset);
CREATE INDEX        idx_pdsr_study          ON pd_stability_readings(study_id, day_offset);
CREATE INDEX        idx_pdsr_tenant         ON pd_stability_readings(tenant_id, created_at DESC);

-- ─── pd_samples ───────────────────────────────────────────────────────────────
DROP TABLE IF EXISTS pd_samples CASCADE;
CREATE TABLE pd_samples (
    id               TEXT PRIMARY KEY,
    tenant_id        TEXT NOT NULL,
    development_id   TEXT NOT NULL,
    formula_version  INTEGER,
    sent_to_client   BOOLEAN DEFAULT FALSE,
    sent_at          TEXT,
    feedback         TEXT DEFAULT '',
    internal_approved BOOLEAN DEFAULT FALSE,
    client_approved  BOOLEAN DEFAULT FALSE,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_pdsa_dev    ON pd_samples(development_id, created_at DESC);
CREATE INDEX idx_pdsa_tenant ON pd_samples(tenant_id);

-- ─── pd_approvals ─────────────────────────────────────────────────────────────
DROP TABLE IF EXISTS pd_approvals CASCADE;
CREATE TABLE pd_approvals (
    id                       TEXT PRIMARY KEY,
    tenant_id                TEXT NOT NULL,
    development_id           TEXT NOT NULL,
    pd_request_id            TEXT,
    approved_by_client       BOOLEAN DEFAULT FALSE,
    approved_by_internal     BOOLEAN DEFAULT FALSE,
    approved_by_comercial    BOOLEAN DEFAULT FALSE,
    approved_by_comercial_id   TEXT,
    approved_by_comercial_name TEXT DEFAULT '',
    approval_date            TEXT,
    approved_at              TEXT,
    notes                    TEXT DEFAULT '',
    approved_by_user         TEXT,
    approved_by_user_name    TEXT DEFAULT '',
    created_at               TIMESTAMPTZ DEFAULT NOW(),
    updated_at               TIMESTAMPTZ DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_pdap_dev    ON pd_approvals(development_id);
CREATE INDEX        idx_pdap_tenant ON pd_approvals(tenant_id);

-- ─── pd_costs ─────────────────────────────────────────────────────────────────
DROP TABLE IF EXISTS pd_costs CASCADE;
CREATE TABLE pd_costs (
    id               TEXT PRIMARY KEY,
    tenant_id        TEXT NOT NULL,
    development_id   TEXT NOT NULL,
    ingredient_cost  NUMERIC(16,6) DEFAULT 0,
    packaging_cost   NUMERIC(16,6) DEFAULT 0,
    labor_cost       NUMERIC(16,6) DEFAULT 0,
    total_cost       NUMERIC(16,6) DEFAULT 0,
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_pdco_dev    ON pd_costs(development_id);
CREATE INDEX        idx_pdco_tenant ON pd_costs(tenant_id);

-- ─── pd_cost_versions ─────────────────────────────────────────────────────────
DROP TABLE IF EXISTS pd_cost_versions CASCADE;
CREATE TABLE pd_cost_versions (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    development_id  TEXT NOT NULL,
    v1              JSONB DEFAULT '{}',
    v2              JSONB,
    total_final     NUMERIC(16,6) DEFAULT 0,
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_pdcv_dev    ON pd_cost_versions(development_id);
CREATE INDEX        idx_pdcv_tenant ON pd_cost_versions(tenant_id);

-- ─── pd_documents ─────────────────────────────────────────────────────────────
DROP TABLE IF EXISTS pd_documents CASCADE;
CREATE TABLE pd_documents (
    id               TEXT PRIMARY KEY,
    tenant_id        TEXT NOT NULL,
    development_id   TEXT NOT NULL,
    doc_type         TEXT DEFAULT '',
    file_url         TEXT DEFAULT '',
    file_name        TEXT DEFAULT '',
    uploaded_by      TEXT,
    uploaded_by_name TEXT DEFAULT '',
    uploaded_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_pddoc_dev    ON pd_documents(development_id, uploaded_at DESC);
CREATE INDEX idx_pddoc_tenant ON pd_documents(tenant_id);

-- ─── pd_document_versions ─────────────────────────────────────────────────────
DROP TABLE IF EXISTS pd_document_versions CASCADE;
CREATE TABLE pd_document_versions (
    id                  TEXT PRIMARY KEY,
    tenant_id           TEXT NOT NULL,
    pd_request_id       TEXT NOT NULL,
    doc_type            TEXT NOT NULL,
    version_number      INTEGER NOT NULL DEFAULT 1,
    status              TEXT DEFAULT 'rascunho',
    active_for_operation BOOLEAN DEFAULT FALSE,
    snapshot            JSONB DEFAULT '{}',
    changed_fields      JSONB DEFAULT '[]',
    source_changes      JSONB DEFAULT '[]',
    reason              TEXT DEFAULT '',
    source_trigger      TEXT DEFAULT 'manual',
    version_code        TEXT DEFAULT '',
    updated_at          TIMESTAMPTZ DEFAULT NOW(),
    approved_at         TEXT,
    approval_task_ids   JSONB DEFAULT '[]',
    created_by          TEXT,
    created_by_name     TEXT DEFAULT '',
    created_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_pddv_req_type        ON pd_document_versions(pd_request_id, doc_type, version_number DESC);
CREATE INDEX idx_pddv_tenant_req      ON pd_document_versions(tenant_id, pd_request_id);
CREATE INDEX idx_pddv_active          ON pd_document_versions(pd_request_id, doc_type, active_for_operation) WHERE active_for_operation = TRUE;

-- ─── pd_catalog ───────────────────────────────────────────────────────────────
DROP TABLE IF EXISTS pd_catalog CASCADE;
CREATE TABLE pd_catalog (
    id                  TEXT PRIMARY KEY,
    tenant_id           TEXT NOT NULL,
    nome                TEXT NOT NULL DEFAULT '',
    inci                TEXT DEFAULT '',
    codigo_interno      TEXT DEFAULT '',
    fornecedor          TEXT DEFAULT '',
    preco_rs_kg         NUMERIC(14,6) DEFAULT 0,
    moeda               TEXT DEFAULT 'BRL',
    unidade             TEXT DEFAULT 'kg',
    categoria           TEXT DEFAULT '',
    observacoes         TEXT DEFAULT '',
    fornecedores        JSONB DEFAULT '[]',
    ultima_atualizacao  TEXT,
    atualizado_por      TEXT DEFAULT '',
    atualizado_por_id   TEXT,
    created_by          TEXT,
    created_by_name     TEXT DEFAULT '',
    created_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_pdcat_tenant       ON pd_catalog(tenant_id, nome ASC);
CREATE INDEX idx_pdcat_tenant_cat   ON pd_catalog(tenant_id, categoria);
CREATE INDEX idx_pdcat_codigo       ON pd_catalog(tenant_id, codigo_interno);

-- ─── pd_catalog_price_history ─────────────────────────────────────────────────
DROP TABLE IF EXISTS pd_catalog_price_history CASCADE;
CREATE TABLE pd_catalog_price_history (
    id               TEXT PRIMARY KEY,
    tenant_id        TEXT NOT NULL,
    catalog_item_id  TEXT NOT NULL,
    preco_anterior   NUMERIC(14,6) DEFAULT 0,
    preco_novo       NUMERIC(14,6) DEFAULT 0,
    moeda            TEXT DEFAULT 'BRL',
    atualizado_por   TEXT DEFAULT '',
    atualizado_por_id TEXT,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_pdcph_item   ON pd_catalog_price_history(catalog_item_id, created_at DESC);
CREATE INDEX idx_pdcph_tenant ON pd_catalog_price_history(tenant_id);

-- ─── pd_cards ─────────────────────────────────────────────────────────────────
DROP TABLE IF EXISTS pd_cards CASCADE;
CREATE TABLE pd_cards (
    id                  TEXT PRIMARY KEY,
    tenant_id           TEXT NOT NULL,
    amostra_id          TEXT,
    amostra_variacao_id TEXT,
    pd_request_id       TEXT,
    status_pd           TEXT DEFAULT 'solicitado',
    executor_id         TEXT,
    executor_name       TEXT DEFAULT '',
    atribuido_em        TEXT,
    atribuido_por       TEXT,
    atribuido_por_nome  TEXT DEFAULT '',
    extra               JSONB DEFAULT '{}',
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_pdcard_tenant   ON pd_cards(tenant_id, status_pd);
CREATE INDEX idx_pdcard_amostra  ON pd_cards(tenant_id, amostra_id);
CREATE INDEX idx_pdcard_req      ON pd_cards(pd_request_id);

-- ─── pd_ficha_tecnica ─────────────────────────────────────────────────────────
DROP TABLE IF EXISTS pd_ficha_tecnica CASCADE;
CREATE TABLE pd_ficha_tecnica (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    pd_request_id   TEXT NOT NULL,
    conteudo        JSONB DEFAULT '{}',
    versao          INTEGER DEFAULT 1,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_pdft_req    ON pd_ficha_tecnica(pd_request_id);
CREATE INDEX        idx_pdft_tenant ON pd_ficha_tecnica(tenant_id);

-- ─── pd_stock_items ───────────────────────────────────────────────────────────
DROP TABLE IF EXISTS pd_stock_items CASCADE;
CREATE TABLE pd_stock_items (
    id                    TEXT PRIMARY KEY,
    tenant_id             TEXT NOT NULL,
    nome                  TEXT NOT NULL DEFAULT '',
    codigo_interno        TEXT DEFAULT '',
    categoria             TEXT DEFAULT '',
    unidade               TEXT DEFAULT '',
    quantidade_atual      NUMERIC(14,4) DEFAULT 0,
    quantidade_minima     NUMERIC(14,4) DEFAULT 0,
    validade              TEXT,
    lote                  TEXT DEFAULT '',
    custo_unitario        NUMERIC(14,6) DEFAULT 0,
    fornecedor            TEXT DEFAULT '',
    observacoes           TEXT DEFAULT '',
    catalog_id            TEXT,
    formula_ref           TEXT DEFAULT '',
    fragrancia_percentual NUMERIC(8,4),
    fragrancia_id         TEXT,
    localizacao           TEXT DEFAULT '',
    linked_pd_request_id  TEXT,
    linked_formula_id     TEXT,
    created_by            TEXT,
    created_by_name       TEXT DEFAULT '',
    created_at            TIMESTAMPTZ DEFAULT NOW(),
    updated_at            TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_pdsi_tenant    ON pd_stock_items(tenant_id, nome ASC);
CREATE INDEX idx_pdsi_categoria ON pd_stock_items(tenant_id, categoria);
CREATE INDEX idx_pdsi_catalog   ON pd_stock_items(catalog_id) WHERE catalog_id IS NOT NULL;

-- ─── pd_stock_movements ───────────────────────────────────────────────────────
DROP TABLE IF EXISTS pd_stock_movements CASCADE;
CREATE TABLE pd_stock_movements (
    id               TEXT PRIMARY KEY,
    tenant_id        TEXT NOT NULL,
    stock_item_id    TEXT NOT NULL,
    tipo             TEXT NOT NULL,
    quantidade       NUMERIC(14,4) NOT NULL,
    quantidade_antes NUMERIC(14,4) DEFAULT 0,
    quantidade_depois NUMERIC(14,4) DEFAULT 0,
    motivo           TEXT DEFAULT '',
    lote             TEXT DEFAULT '',
    linked_dev_id    TEXT,
    linked_pd_request_id TEXT,
    user_id          TEXT,
    user_name        TEXT DEFAULT '',
    created_at       TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_pdsm_item   ON pd_stock_movements(stock_item_id, created_at DESC);
CREATE INDEX idx_pdsm_tenant ON pd_stock_movements(tenant_id, created_at DESC);
CREATE INDEX idx_pdsm_tipo   ON pd_stock_movements(tenant_id, tipo);

-- ─── pd_updates ───────────────────────────────────────────────────────────────
DROP TABLE IF EXISTS pd_updates CASCADE;
CREATE TABLE pd_updates (
    id                TEXT PRIMARY KEY,
    tenant_id         TEXT NOT NULL,
    pd_request_id     TEXT NOT NULL,
    tipo              TEXT DEFAULT '',
    mensagem          TEXT DEFAULT '',
    visivel_comercial BOOLEAN DEFAULT FALSE,
    recebido          BOOLEAN DEFAULT FALSE,
    recebido_em       TEXT,
    recebido_por      TEXT,
    recebido_por_nome TEXT DEFAULT '',
    item_solicitado   TEXT DEFAULT '',
    fornecedor        TEXT DEFAULT '',
    previsao_entrega  TEXT,
    user_id           TEXT,
    user_name         TEXT DEFAULT '',
    user_role         TEXT DEFAULT '',
    pending_item_id   TEXT,
    created_at        TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_pdup_req    ON pd_updates(pd_request_id, created_at DESC);
CREATE INDEX idx_pdup_tenant ON pd_updates(tenant_id, created_at DESC);

-- ─── pd_pending_items ─────────────────────────────────────────────────────────
DROP TABLE IF EXISTS pd_pending_items CASCADE;
CREATE TABLE pd_pending_items (
    id               TEXT PRIMARY KEY,
    tenant_id        TEXT NOT NULL,
    pd_request_id    TEXT NOT NULL,
    tipo             TEXT DEFAULT '',
    descricao        TEXT DEFAULT '',
    data_solicitacao TEXT,
    data_prevista    TEXT,
    data_recebido    TEXT,
    fornecedor       TEXT DEFAULT '',
    observacoes      TEXT DEFAULT '',
    status           TEXT DEFAULT 'pendente',
    user_id          TEXT,
    user_name        TEXT DEFAULT '',
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_pdpi_req    ON pd_pending_items(pd_request_id, created_at DESC);
CREATE INDEX idx_pdpi_tenant ON pd_pending_items(tenant_id, status);

-- ─── pd_sample_batches ────────────────────────────────────────────────────────
DROP TABLE IF EXISTS pd_sample_batches CASCADE;
CREATE TABLE pd_sample_batches (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    development_id  TEXT NOT NULL,
    conteudo        JSONB DEFAULT '{}',
    created_by      TEXT,
    created_by_name TEXT DEFAULT '',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_pdsb_dev    ON pd_sample_batches(development_id, created_at DESC);
CREATE INDEX idx_pdsb_tenant ON pd_sample_batches(tenant_id);

-- ─── pd_batch_orders ──────────────────────────────────────────────────────────
DROP TABLE IF EXISTS pd_batch_orders CASCADE;
CREATE TABLE pd_batch_orders (
    id                      TEXT PRIMARY KEY,
    tenant_id               TEXT NOT NULL,
    ordem_numero            TEXT,
    amostra_ids             JSONB DEFAULT '[]',
    volume_por_amostra_ml   NUMERIC(14,4) DEFAULT 0,
    n_amostras              INTEGER DEFAULT 0,
    base_compartilhada      JSONB DEFAULT '[]',
    ingredientes_por_variacao JSONB DEFAULT '{}',
    observacao              TEXT DEFAULT '',
    criado_por              TEXT,
    criado_por_nome         TEXT DEFAULT '',
    created_at              TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_pdbo_tenant ON pd_batch_orders(tenant_id, created_at DESC);
