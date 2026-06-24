-- 007_fase7_schema.sql
-- Phase 7: Fix workflow_tasks, contratos, order_material_requirements schemas.
-- Also adds missing columns needed by workflow_engine functions.
-- Execute in Supabase SQL Editor (idempotent DROP/CREATE).

-- ─── workflow_tasks ───────────────────────────────────────────────────────────
-- Recreated with English field names that match the workflow_engine.py document.
DROP TABLE IF EXISTS workflow_tasks CASCADE;

CREATE TABLE workflow_tasks (
    id                  TEXT PRIMARY KEY,
    tenant_id           TEXT NOT NULL,
    display_code        TEXT DEFAULT '',
    entity_type         TEXT NOT NULL DEFAULT '',
    entity_id           TEXT NOT NULL DEFAULT '',
    module_origin       TEXT DEFAULT '',
    title               TEXT NOT NULL DEFAULT '',
    description         TEXT DEFAULT '',
    category            TEXT DEFAULT '',
    task_type           TEXT DEFAULT 'standard',
    priority            TEXT DEFAULT 'normal',
    blocking            BOOLEAN DEFAULT FALSE,
    blocks_stages       JSONB DEFAULT '[]',
    responsible_id      TEXT DEFAULT '',
    responsible_name    TEXT DEFAULT '',
    assignment_history  JSONB DEFAULT '[]',
    due_date            TEXT,
    status              TEXT DEFAULT 'pendente',
    decision            TEXT,
    decision_comment    TEXT DEFAULT '',
    decision_at         TEXT,
    decision_by         TEXT,
    decision_by_name    TEXT DEFAULT '',
    completed_at        TEXT,
    completed_by        TEXT,
    completed_by_name   TEXT DEFAULT '',
    completion_comment  TEXT DEFAULT '',
    d1_notified         BOOLEAN DEFAULT FALSE,
    escalated           BOOLEAN DEFAULT FALSE,
    escalated_at        TEXT,
    notification_flags  JSONB DEFAULT '{}',
    metadata            JSONB DEFAULT '{}',
    created_by          TEXT DEFAULT '',
    created_by_name     TEXT DEFAULT '',
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_wftask_tenant_status   ON workflow_tasks(tenant_id, status);
CREATE INDEX idx_wftask_tenant_entity   ON workflow_tasks(tenant_id, entity_type, entity_id);
CREATE INDEX idx_wftask_tenant_resp     ON workflow_tasks(tenant_id, responsible_id);
CREATE INDEX idx_wftask_tenant_due      ON workflow_tasks(tenant_id, due_date);
CREATE INDEX idx_wftask_blocking        ON workflow_tasks(tenant_id, blocking) WHERE blocking = TRUE;

-- ─── contratos ───────────────────────────────────────────────────────────────
-- Recreated with full CGI fields matching contratos_routes.py document structure.
DROP TABLE IF EXISTS contratos CASCADE;

CREATE TABLE contratos (
    id                  TEXT PRIMARY KEY,
    tenant_id           TEXT NOT NULL,
    numero_contrato     TEXT NOT NULL DEFAULT '',
    kickoff_id          TEXT,
    numero_kickoff      TEXT DEFAULT '',
    kickoff_versao      TEXT DEFAULT '',
    client_id           TEXT,
    contratante         JSONB DEFAULT '{}',
    fabricante          JSONB DEFAULT '{}',
    clausulas           JSONB DEFAULT '[]',
    observacoes         TEXT DEFAULT '',
    pdf_size_bytes      INTEGER DEFAULT 0,
    pdf_data            BYTEA,
    status              TEXT DEFAULT 'gerado',
    version             INTEGER DEFAULT 1,
    tipo                TEXT DEFAULT 'CGI',
    created_by          TEXT DEFAULT '',
    created_by_name     TEXT DEFAULT '',
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_contratos_tenant_numero ON contratos(tenant_id, numero_contrato);
CREATE INDEX idx_contratos_tenant_kickoff ON contratos(tenant_id, kickoff_id);
CREATE INDEX idx_contratos_tenant_client  ON contratos(tenant_id, client_id);
CREATE INDEX idx_contratos_tenant_created ON contratos(tenant_id, created_at DESC);

-- ─── order_material_requirements ─────────────────────────────────────────────
-- Replaces normalized (material_id FK) schema with JSONB materiais array,
-- matching the document written by propostas_routes.py.
DROP TABLE IF EXISTS order_material_requirements CASCADE;

CREATE TABLE order_material_requirements (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    proposta_id     TEXT,
    order_id        TEXT,
    projeto_id      TEXT,
    gerado_em       TEXT,
    gerado_por      TEXT DEFAULT '',
    gerado_por_nome TEXT DEFAULT '',
    status          TEXT DEFAULT 'pendente',
    materiais       JSONB DEFAULT '[]',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_omreq_tenant_proposta ON order_material_requirements(tenant_id, proposta_id)
    WHERE proposta_id IS NOT NULL;
CREATE INDEX idx_omreq_tenant_projeto ON order_material_requirements(tenant_id, projeto_id);
CREATE INDEX idx_omreq_tenant_order   ON order_material_requirements(tenant_id, order_id);
CREATE INDEX idx_omreq_tenant_created ON order_material_requirements(tenant_id, gerado_em);

-- ─── Patch existing tables ────────────────────────────────────────────────────
-- pd_document_versions: approval_summary used by workflow_engine._sync_pd_document_version_status
ALTER TABLE pd_document_versions ADD COLUMN IF NOT EXISTS approval_summary JSONB DEFAULT '{}';

-- orders: followups JSONB array used by check_followup_notifications_for_tenant scheduler
ALTER TABLE orders ADD COLUMN IF NOT EXISTS followups JSONB DEFAULT '[]';

-- orders: expedicao link used by expedicao_routes.py
ALTER TABLE orders ADD COLUMN IF NOT EXISTS project_name TEXT DEFAULT '';
ALTER TABLE orders ADD COLUMN IF NOT EXISTS exp_id       TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS exp_numero   TEXT DEFAULT '';

-- ops: extra fields used by retrabalho_routes and recebimento_routes
ALTER TABLE ops ADD COLUMN IF NOT EXISTS pedido_id    TEXT DEFAULT '';
ALTER TABLE ops ADD COLUMN IF NOT EXISTS pedido_numero TEXT DEFAULT '';
ALTER TABLE ops ADD COLUMN IF NOT EXISTS data_prevista TEXT;
ALTER TABLE ops ADD COLUMN IF NOT EXISTS insumos      JSONB DEFAULT '[]';

-- bom_items: full BOM fields (MongoDB schema) needed by propostas/produtos routes
ALTER TABLE bom_items
  ADD COLUMN IF NOT EXISTS codigo_material      TEXT DEFAULT '',
  ADD COLUMN IF NOT EXISTS camada               TEXT DEFAULT 'bulk',
  ADD COLUMN IF NOT EXISTS vigente              BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS nome_material        TEXT DEFAULT '',
  ADD COLUMN IF NOT EXISTS quantidade_por_unidade NUMERIC(12,4) DEFAULT 0,
  ADD COLUMN IF NOT EXISTS unidade_consumo      TEXT DEFAULT '',
  ADD COLUMN IF NOT EXISTS unidade_compra       TEXT DEFAULT '',
  ADD COLUMN IF NOT EXISTS tipo                 TEXT DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_bom_camada_vigente ON bom_items(tenant_id, produto_pai_id, camada) WHERE vigente = TRUE;
CREATE INDEX IF NOT EXISTS idx_bom_sku_camada ON bom_items(tenant_id, sku_id, camada) WHERE vigente = TRUE;

-- cq_registros_analise: add RT/recebimento cross-module fields
ALTER TABLE cq_registros_analise
  ADD COLUMN IF NOT EXISTS data_limite_cq   TEXT,
  ADD COLUMN IF NOT EXISTS urgente          BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS recebimento_id   TEXT,
  ADD COLUMN IF NOT EXISTS created_by_name  TEXT DEFAULT '',
  ADD COLUMN IF NOT EXISTS produto_nome     TEXT DEFAULT '',
  ADD COLUMN IF NOT EXISTS origem_rt_id     TEXT,
  ADD COLUMN IF NOT EXISTS origem_rt_numero TEXT DEFAULT '',
  ADD COLUMN IF NOT EXISTS categoria_rt     TEXT DEFAULT '';

-- ─── retrabalho_ordens — recreate with full document schema ──────────────────
DROP TABLE IF EXISTS retrabalho_ordens CASCADE;
CREATE TABLE retrabalho_ordens (
    id                    TEXT PRIMARY KEY,
    tenant_id             TEXT NOT NULL,
    numero_rt             TEXT DEFAULT '',
    categoria             TEXT DEFAULT 'RT-1',
    rnc_id                TEXT,
    rnc_numero            TEXT DEFAULT '',
    op_id                 TEXT,
    op_numero             TEXT DEFAULT '',
    pedido_id             TEXT DEFAULT '',
    pedido_numero         TEXT DEFAULT '',
    lote_id               TEXT,
    lote_numero           TEXT DEFAULT '',
    produto_nome          TEXT DEFAULT '',
    problema_descrito     TEXT DEFAULT '',
    instrucoes_retrabalho TEXT DEFAULT '',
    responsavel_id        TEXT DEFAULT '',
    responsavel_nome      TEXT DEFAULT '',
    data_limite           TEXT,
    custo_estimado        NUMERIC(12,2) DEFAULT 0,
    devolucao_id          TEXT,
    status                TEXT DEFAULT 'pendente',
    nova_ra_id            TEXT,
    nova_ra_numero        TEXT,
    observacoes           TEXT DEFAULT '',
    observacoes_conclusao TEXT DEFAULT '',
    historico             JSONB DEFAULT '[]',
    created_by            TEXT DEFAULT '',
    created_by_name       TEXT DEFAULT '',
    created_at            TIMESTAMPTZ DEFAULT NOW(),
    updated_at            TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_rt_tenant_status   ON retrabalho_ordens(tenant_id, status);
CREATE INDEX idx_rt_tenant_created  ON retrabalho_ordens(tenant_id, created_at DESC);
CREATE INDEX idx_rt_tenant_cat      ON retrabalho_ordens(tenant_id, categoria);

-- ─── recebimentos — recreate with full document schema ────────────────────────
DROP TABLE IF EXISTS recebimentos CASCADE;
CREATE TABLE recebimentos (
    id             TEXT PRIMARY KEY,
    tenant_id      TEXT NOT NULL,
    po_id          TEXT,
    po_numero      TEXT DEFAULT '',
    fornecedor_id  TEXT,
    fornecedor_nome TEXT DEFAULT '',
    numero_nf      TEXT DEFAULT '',
    data_nf        TEXT DEFAULT '',
    status         TEXT DEFAULT 'quarentena',
    items          JSONB DEFAULT '[]',
    tem_urgente    BOOLEAN DEFAULT FALSE,
    observacoes    TEXT DEFAULT '',
    created_by     TEXT DEFAULT '',
    created_by_name TEXT DEFAULT '',
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    updated_at     TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_rec_tenant_status  ON recebimentos(tenant_id, status);
CREATE INDEX idx_rec_tenant_created ON recebimentos(tenant_id, created_at DESC);

-- ─── recebimento_sla_config — single row per tenant ──────────────────────────
DROP TABLE IF EXISTS recebimento_sla_config CASCADE;
CREATE TABLE recebimento_sla_config (
    tenant_id  TEXT PRIMARY KEY,
    formulacao INTEGER DEFAULT 3,
    rotulo     INTEGER DEFAULT 2,
    embalagem  INTEGER DEFAULT 2,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─── estoque_items / estoque_movimentos — recreate with full schema ───────────
-- Drop movimentos first (has FK to estoque_items)
DROP TABLE IF EXISTS estoque_movimentos CASCADE;
DROP TABLE IF EXISTS estoque_items CASCADE;

CREATE TABLE estoque_items (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    tipo_item       TEXT DEFAULT 'mp',
    setor           TEXT DEFAULT '',
    nome            TEXT DEFAULT '',
    codigo          TEXT DEFAULT '',
    mp_id           TEXT,
    sku_id          TEXT,
    produto_id      TEXT,
    unidade         TEXT DEFAULT 'kg',
    quantidade_atual NUMERIC(12,3) DEFAULT 0,
    estoque_minimo  NUMERIC(12,3) DEFAULT 0,
    localizacao     TEXT DEFAULT '',
    lote            TEXT DEFAULT '',
    validade        TEXT,
    observacoes     TEXT DEFAULT '',
    posicao_cq      TEXT DEFAULT 'quarentena',
    status          TEXT DEFAULT 'disponivel',
    created_by      TEXT DEFAULT '',
    created_by_name TEXT DEFAULT '',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_estq_tenant_setor  ON estoque_items(tenant_id, setor);
CREATE INDEX idx_estq_tenant_mpid   ON estoque_items(tenant_id, mp_id) WHERE mp_id IS NOT NULL;
CREATE INDEX idx_estq_tenant_nome   ON estoque_items(tenant_id, nome);

CREATE TABLE estoque_movimentos (
    id              TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    item_id         TEXT REFERENCES estoque_items(id),
    setor           TEXT DEFAULT '',
    tipo_item       TEXT DEFAULT '',
    nome_item       TEXT DEFAULT '',
    codigo_item     TEXT DEFAULT '',
    lote            TEXT DEFAULT '',
    tipo            TEXT DEFAULT '',
    direcao         TEXT DEFAULT 'entrada',
    quantidade      NUMERIC(12,3),
    unidade         TEXT DEFAULT '',
    quantidade_antes NUMERIC(12,3) DEFAULT 0,
    quantidade_depois NUMERIC(12,3) DEFAULT 0,
    motivo          TEXT DEFAULT '',
    referencia      TEXT DEFAULT '',
    documento       TEXT DEFAULT '',
    usuario         TEXT DEFAULT '',
    usuario_id      TEXT DEFAULT '',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_estmov_tenant_item ON estoque_movimentos(tenant_id, item_id);
CREATE INDEX idx_estmov_tenant_created ON estoque_movimentos(tenant_id, created_at DESC);

-- ─── expedicao_ordens — recreate with full document schema ───────────────────
DROP TABLE IF EXISTS expedicao_ordens CASCADE;
CREATE TABLE expedicao_ordens (
    id               TEXT PRIMARY KEY,
    tenant_id        TEXT NOT NULL,
    numero_exp       TEXT DEFAULT '',
    order_id         TEXT,
    order_numero     TEXT DEFAULT '',
    project_name     TEXT DEFAULT '',
    cliente_nome     TEXT DEFAULT '',
    cliente_id       TEXT,
    endereco_entrega TEXT DEFAULT '',
    transportadora   TEXT DEFAULT '',
    previsao_entrega TEXT,
    data_expedicao   TEXT,
    data_entrega     TEXT,
    codigo_rastreio  TEXT,
    numero_nf_saida  TEXT DEFAULT '',
    status           TEXT DEFAULT 'pendente',
    conferencia      JSONB,
    items            JSONB DEFAULT '[]',
    observacoes      TEXT DEFAULT '',
    historico        JSONB DEFAULT '[]',
    created_by       TEXT DEFAULT '',
    created_by_name  TEXT DEFAULT '',
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_exp_tenant_status  ON expedicao_ordens(tenant_id, status);
CREATE INDEX idx_exp_tenant_created ON expedicao_ordens(tenant_id, created_at DESC);
CREATE INDEX idx_exp_tenant_order   ON expedicao_ordens(tenant_id, order_id);

-- ─── propostas_comerciais — recreate with full document schema ────────────────
DROP TABLE IF EXISTS propostas_comerciais CASCADE;
CREATE TABLE propostas_comerciais (
    id                   TEXT PRIMARY KEY,
    tenant_id            TEXT NOT NULL,
    projeto_id           TEXT,
    projeto_nome         TEXT DEFAULT '',
    cliente_id           TEXT,
    cliente_nome         TEXT DEFAULT '',
    tipo_produto         TEXT DEFAULT '',
    variacao_produto     TEXT DEFAULT '',
    preco_unitario       NUMERIC(12,4),
    insumos_inclusos     JSONB DEFAULT '[]',
    observacoes_proposta TEXT DEFAULT '',
    items_pedido         JSONB DEFAULT '[]',
    condicoes_pagamento  TEXT DEFAULT '',
    insumos_fabricacao   JSONB DEFAULT '[]',
    rodape_observacoes   TEXT DEFAULT '',
    status               TEXT DEFAULT 'rascunho',
    arquivos             JSONB DEFAULT '[]',
    created_by           TEXT DEFAULT '',
    created_by_name      TEXT DEFAULT '',
    created_at           TIMESTAMPTZ DEFAULT NOW(),
    updated_at           TIMESTAMPTZ DEFAULT NOW(),
    updated_by           TEXT DEFAULT '',
    updated_by_name      TEXT DEFAULT ''
);
CREATE UNIQUE INDEX idx_prop_tenant_projeto ON propostas_comerciais(tenant_id, projeto_id)
    WHERE projeto_id IS NOT NULL;
CREATE INDEX idx_prop_tenant_status  ON propostas_comerciais(tenant_id, status);
CREATE INDEX idx_prop_tenant_cliente ON propostas_comerciais(tenant_id, cliente_id);

-- ==========================================
-- ETAPA 7.3 SCHEMA ADDITIONS
-- ==========================================

-- produtos_pai: missing columns
ALTER TABLE produtos_pai ADD COLUMN IF NOT EXISTS descricao TEXT DEFAULT '';
ALTER TABLE produtos_pai ADD COLUMN IF NOT EXISTS cliente_id TEXT;
ALTER TABLE produtos_pai ADD COLUMN IF NOT EXISTS cliente_nome TEXT DEFAULT '';
ALTER TABLE produtos_pai ADD COLUMN IF NOT EXISTS created_by TEXT;
ALTER TABLE produtos_pai ADD COLUMN IF NOT EXISTS created_by_name TEXT DEFAULT '';

-- bom_items: versioning + embalagem-only columns
ALTER TABLE bom_items ADD COLUMN IF NOT EXISTS versao INTEGER DEFAULT 1;
ALTER TABLE bom_items ADD COLUMN IF NOT EXISTS vigente_desde TEXT;
ALTER TABLE bom_items ADD COLUMN IF NOT EXISTS motivo_revisao TEXT DEFAULT '';
ALTER TABLE bom_items ADD COLUMN IF NOT EXISTS fator_conversao NUMERIC(8,4) DEFAULT 1.0;
ALTER TABLE bom_items ADD COLUMN IF NOT EXISTS observacoes TEXT DEFAULT '';

-- skus: apresentacao JSONB for SKU-to-produto-pai link
ALTER TABLE skus ADD COLUMN IF NOT EXISTS apresentacao JSONB DEFAULT '{}';

-- estoque_items: structured location
ALTER TABLE estoque_items ADD COLUMN IF NOT EXISTS localizacao_estruturada TEXT DEFAULT '';

-- ops: PCP scheduling + lotes + items columns
ALTER TABLE ops ADD COLUMN IF NOT EXISTS items JSONB DEFAULT '[]';
ALTER TABLE ops ADD COLUMN IF NOT EXISTS checklist_insumos JSONB DEFAULT '{}';
ALTER TABLE ops ADD COLUMN IF NOT EXISTS cliente_nome TEXT DEFAULT '';
ALTER TABLE ops ADD COLUMN IF NOT EXISTS pcp_slot_id TEXT;
ALTER TABLE ops ADD COLUMN IF NOT EXISTS pcp_numero TEXT;
ALTER TABLE ops ADD COLUMN IF NOT EXISTS lote_ids JSONB DEFAULT '[]';

-- orders: NF reference columns
ALTER TABLE orders ADD COLUMN IF NOT EXISTS nf_id TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS nf_numero TEXT;

-- faturamento_notas: full schema recreation
DROP TABLE IF EXISTS faturamento_notas CASCADE;
CREATE TABLE faturamento_notas (
    id                  TEXT PRIMARY KEY,
    tenant_id           TEXT NOT NULL,
    numero_interno      TEXT,
    numero_nfe          TEXT,
    chave_acesso        TEXT,
    order_id            TEXT,
    order_numero        TEXT,
    exp_id              TEXT,
    exp_numero          TEXT,
    cliente_nome        TEXT NOT NULL,
    cliente_id          TEXT,
    cliente_cnpj        TEXT DEFAULT '',
    valor_produtos      NUMERIC(12,2) DEFAULT 0,
    valor_frete         NUMERIC(12,2) DEFAULT 0,
    valor_impostos      NUMERIC(12,2) DEFAULT 0,
    valor_total         NUMERIC(12,2) DEFAULT 0,
    forma_pagamento     TEXT DEFAULT '',
    condicao_pagamento  TEXT DEFAULT '',
    data_emissao        TEXT,
    data_vencimento     TEXT,
    status              TEXT DEFAULT 'rascunho',
    status_pagamento    TEXT DEFAULT 'aguardando',
    valor_pago          NUMERIC(12,2) DEFAULT 0,
    data_pagamento      TEXT,
    duplicatas_geradas  BOOLEAN DEFAULT FALSE,
    total_parcelas      INTEGER DEFAULT 0,
    observacoes         TEXT DEFAULT '',
    historico           JSONB DEFAULT '[]',
    created_by          TEXT,
    created_by_name     TEXT DEFAULT '',
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- faturamento_duplicatas: full schema recreation
DROP TABLE IF EXISTS faturamento_duplicatas CASCADE;
CREATE TABLE faturamento_duplicatas (
    id                  TEXT PRIMARY KEY,
    tenant_id           TEXT NOT NULL,
    nf_id               TEXT,
    nf_numero           TEXT,
    order_id            TEXT,
    order_numero        TEXT,
    cliente_nome        TEXT,
    cliente_cnpj        TEXT DEFAULT '',
    cliente_id          TEXT,
    numero_parcela      INTEGER DEFAULT 1,
    total_parcelas      INTEGER DEFAULT 1,
    label               TEXT,
    valor               NUMERIC(12,2) DEFAULT 0,
    valor_pago          NUMERIC(12,2) DEFAULT 0,
    data_emissao        TEXT,
    data_vencimento     TEXT,
    status              TEXT DEFAULT 'aberta',
    forma_pagamento     TEXT DEFAULT '',
    data_pagamento      TEXT,
    data_protesto       TEXT,
    observacoes         TEXT DEFAULT '',
    created_by          TEXT,
    created_by_name     TEXT DEFAULT '',
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- PCP tables: DROP all (children first) then RECREATE with full schema
DROP TABLE IF EXISTS pcp_lotes CASCADE;
DROP TABLE IF EXISTS pcp_programacao CASCADE;
DROP TABLE IF EXISTS pcp_calendario CASCADE;
DROP TABLE IF EXISTS pcp_linhas CASCADE;

CREATE TABLE pcp_linhas (
    id                  TEXT PRIMARY KEY,
    tenant_id           TEXT NOT NULL,
    nome                TEXT NOT NULL,
    codigo              TEXT DEFAULT '',
    tipo                TEXT DEFAULT 'geral',
    capacidade_diaria   NUMERIC(12,3) DEFAULT 0,
    unidade_capacidade  TEXT DEFAULT 'kg',
    setup_minutos       INTEGER DEFAULT 30,
    status              TEXT DEFAULT 'ativa',
    observacoes         TEXT DEFAULT '',
    created_by          TEXT,
    created_by_name     TEXT DEFAULT '',
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE pcp_calendario (
    id                  TEXT PRIMARY KEY,
    tenant_id           TEXT NOT NULL,
    semana              TEXT NOT NULL,
    linha_id            TEXT REFERENCES pcp_linhas(id),
    linha_nome          TEXT DEFAULT '',
    seg                 JSONB DEFAULT '{}',
    ter                 JSONB DEFAULT '{}',
    qua                 JSONB DEFAULT '{}',
    qui                 JSONB DEFAULT '{}',
    sex                 JSONB DEFAULT '{}',
    sab                 JSONB DEFAULT '{}',
    dom                 JSONB DEFAULT '{}',
    created_by          TEXT,
    created_by_name     TEXT DEFAULT '',
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, semana, linha_id)
);

CREATE TABLE pcp_programacao (
    id                  TEXT PRIMARY KEY,
    tenant_id           TEXT NOT NULL,
    numero_prog         TEXT,
    op_id               TEXT,
    op_numero           TEXT DEFAULT '',
    pedido_id           TEXT DEFAULT '',
    pedido_numero       TEXT DEFAULT '',
    cliente_nome        TEXT DEFAULT '',
    produto_nome        TEXT DEFAULT '',
    sku                 TEXT DEFAULT '',
    linha_id            TEXT REFERENCES pcp_linhas(id),
    linha_nome          TEXT DEFAULT '',
    linha_tipo          TEXT DEFAULT 'geral',
    data                TEXT,
    hora_inicio         TEXT DEFAULT '07:00',
    hora_fim            TEXT DEFAULT '18:00',
    tipo                TEXT DEFAULT 'producao',
    setup_tempo_min     INTEGER,
    setup_tipo          TEXT,
    lote_id             TEXT,
    data_inicio         TEXT,
    data_fim            TEXT,
    turno               TEXT DEFAULT 'integral',
    qtd_planejada       NUMERIC(12,3) DEFAULT 0,
    qtd_produzida       NUMERIC(12,3) DEFAULT 0,
    status              TEXT DEFAULT 'planejado',
    historico           JSONB DEFAULT '[]',
    observacoes         TEXT DEFAULT '',
    created_by          TEXT,
    created_by_name     TEXT DEFAULT '',
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE pcp_lotes (
    id                  TEXT PRIMARY KEY,
    tenant_id           TEXT NOT NULL,
    numero_lote         TEXT,
    op_id               TEXT,
    op_numero           TEXT DEFAULT '',
    pedido_id           TEXT DEFAULT '',
    pedido_numero       TEXT DEFAULT '',
    cliente_nome        TEXT DEFAULT '',
    produto_nome        TEXT DEFAULT '',
    sku                 TEXT DEFAULT '',
    data_manipulacao    TEXT,
    data_envase         TEXT,
    qtd_planejada       INTEGER DEFAULT 0,
    qtd_produzida       NUMERIC(12,3) DEFAULT 0,
    status              TEXT DEFAULT 'planejado',
    historico           JSONB DEFAULT '[]',
    observacoes         TEXT DEFAULT '',
    created_by          TEXT,
    created_by_name     TEXT DEFAULT '',
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- ETAPA 7.4 — orders (PI), order_audit_log, ops, kickoffs
-- ============================================================

-- orders: full PI (Pedido Industrialização) fields
ALTER TABLE orders ADD COLUMN IF NOT EXISTS pd_request_id TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS kickoff_id TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS client_card_id TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS data_pedido TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS tipo_servico TEXT DEFAULT 'producao';
ALTER TABLE orders ADD COLUMN IF NOT EXISTS nivel_formalizacao INTEGER DEFAULT 1;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS cliente JSONB DEFAULT '{}';
ALTER TABLE orders ADD COLUMN IF NOT EXISTS frete JSONB DEFAULT '{}';
ALTER TABLE orders ADD COLUMN IF NOT EXISTS items JSONB DEFAULT '[]';
ALTER TABLE orders ADD COLUMN IF NOT EXISTS condicoes JSONB DEFAULT '{}';
ALTER TABLE orders ADD COLUMN IF NOT EXISTS insumos JSONB DEFAULT '[]';
ALTER TABLE orders ADD COLUMN IF NOT EXISTS checklist_insumos JSONB DEFAULT '[]';
ALTER TABLE orders ADD COLUMN IF NOT EXISTS total_bruto NUMERIC(15,2) DEFAULT 0;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS total_desconto NUMERIC(15,2) DEFAULT 0;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS desconto_pct_medio NUMERIC(8,4) DEFAULT 0;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS cgi_status TEXT DEFAULT 'pendente';
ALTER TABLE orders ADD COLUMN IF NOT EXISTS cgi_assinado_em TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS cgi_assinado_por TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS aprovacao_cliente TEXT DEFAULT 'pendente';
ALTER TABLE orders ADD COLUMN IF NOT EXISTS aprovacao_cliente_obs TEXT DEFAULT '';
ALTER TABLE orders ADD COLUMN IF NOT EXISTS aprovacao_cliente_em TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS aprovacao_cliente_por TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS aprovacao_comercial TEXT DEFAULT 'nao_necessaria';
ALTER TABLE orders ADD COLUMN IF NOT EXISTS aprovacao_comercial_nivel TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS aprovacao_comercial_por TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS aprovacao_comercial_em TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS aprovacao_comercial_obs TEXT DEFAULT '';
ALTER TABLE orders ADD COLUMN IF NOT EXISTS op_id TEXT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS auto_created BOOLEAN DEFAULT FALSE;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS reproducao_de TEXT;

-- order_audit_log: extra fields for immutability audit
ALTER TABLE order_audit_log ADD COLUMN IF NOT EXISTS order_numero TEXT DEFAULT '';
ALTER TABLE order_audit_log ADD COLUMN IF NOT EXISTS fields_changed JSONB DEFAULT '[]';
ALTER TABLE order_audit_log ADD COLUMN IF NOT EXISTS justificativa TEXT DEFAULT '';

-- ops: production tracking
ALTER TABLE ops ADD COLUMN IF NOT EXISTS project_name TEXT DEFAULT '';
ALTER TABLE ops ADD COLUMN IF NOT EXISTS created_by TEXT;
ALTER TABLE ops ADD COLUMN IF NOT EXISTS created_by_name TEXT DEFAULT '';
ALTER TABLE ops ADD COLUMN IF NOT EXISTS apontamentos JSONB DEFAULT '[]';
ALTER TABLE ops ADD COLUMN IF NOT EXISTS pausas JSONB DEFAULT '[]';
ALTER TABLE ops ADD COLUMN IF NOT EXISTS perdas JSONB DEFAULT '[]';

-- kickoffs: full versioned schema
ALTER TABLE kickoffs ADD COLUMN IF NOT EXISTS kickoff_group_id TEXT;
ALTER TABLE kickoffs ADD COLUMN IF NOT EXISTS parent_kickoff_id TEXT;
ALTER TABLE kickoffs ADD COLUMN IF NOT EXISTS formula_id TEXT;
ALTER TABLE kickoffs ADD COLUMN IF NOT EXISTS data_abertura TEXT;
ALTER TABLE kickoffs ADD COLUMN IF NOT EXISTS versao TEXT DEFAULT 'v1';
ALTER TABLE kickoffs ADD COLUMN IF NOT EXISTS versao_numero INTEGER DEFAULT 1;
ALTER TABLE kickoffs ADD COLUMN IF NOT EXISTS bloco4 JSONB DEFAULT '{}';
ALTER TABLE kickoffs ADD COLUMN IF NOT EXISTS bom JSONB DEFAULT '[]';
ALTER TABLE kickoffs ADD COLUMN IF NOT EXISTS aprovacoes JSONB DEFAULT '[]';
ALTER TABLE kickoffs ADD COLUMN IF NOT EXISTS log_auditoria JSONB DEFAULT '[]';
ALTER TABLE kickoffs ADD COLUMN IF NOT EXISTS approved_at TEXT;
ALTER TABLE kickoffs ADD COLUMN IF NOT EXISTS approved_by TEXT;
ALTER TABLE kickoffs ADD COLUMN IF NOT EXISTS approved_by_name TEXT DEFAULT '';
ALTER TABLE kickoffs ADD COLUMN IF NOT EXISTS created_by_name TEXT DEFAULT '';

-- crm_projects: kickoff sync
ALTER TABLE crm_projects ADD COLUMN IF NOT EXISTS kickoff_id TEXT;
ALTER TABLE crm_projects ADD COLUMN IF NOT EXISTS kickoff_status TEXT;
ALTER TABLE crm_projects ADD COLUMN IF NOT EXISTS kickoff_numero TEXT;
ALTER TABLE crm_projects ADD COLUMN IF NOT EXISTS kickoff_versao TEXT;
ALTER TABLE crm_projects ADD COLUMN IF NOT EXISTS kickoff_group_id TEXT;
ALTER TABLE crm_projects ADD COLUMN IF NOT EXISTS briefing_resumido TEXT DEFAULT '';

-- pd_requests: project link alias
ALTER TABLE pd_requests ADD COLUMN IF NOT EXISTS linked_projeto_id TEXT;

-- homologacao_mps: BOM ingredient resolution
ALTER TABLE homologacao_mps ADD COLUMN IF NOT EXISTS nome TEXT DEFAULT '';
ALTER TABLE homologacao_mps ADD COLUMN IF NOT EXISTS inci TEXT DEFAULT '';
ALTER TABLE homologacao_mps ADD COLUMN IF NOT EXISTS codigo_interno TEXT DEFAULT '';
ALTER TABLE homologacao_mps ADD COLUMN IF NOT EXISTS fornecedor_nome TEXT DEFAULT '';

