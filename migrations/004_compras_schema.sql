-- 004_compras_schema.sql
-- Cria as 6 tabelas do módulo Compras no PostgreSQL.
-- Execute no Supabase SQL Editor.
--
-- Idempotente: dropa e recria cada tabela para garantir schema correto.
-- Seguro enquanto as tabelas estão vazias (fase de configuração).

-- ─── compras_fornecedores ─────────────────────────────────────────────────────
DROP TABLE IF EXISTS compras_fornecedores CASCADE;

CREATE TABLE compras_fornecedores (
    id                  TEXT PRIMARY KEY,
    tenant_id           TEXT NOT NULL,
    codigo_interno      TEXT,
    razao_social        TEXT NOT NULL DEFAULT '',
    nome_fantasia       TEXT NOT NULL DEFAULT '',
    cnpj                TEXT NOT NULL DEFAULT '',
    cnpj_normalizado    TEXT,
    ie                  TEXT DEFAULT '',
    im                  TEXT DEFAULT '',
    endereco            JSONB DEFAULT '{}',
    contatos            JSONB DEFAULT '[]',
    categorias          JSONB DEFAULT '[]',
    homologacao         JSONB DEFAULT '{}',
    status_cadastro     TEXT DEFAULT 'ativo',
    log_auditoria       JSONB DEFAULT '[]',
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_cmpforn_tenant_cnpj
    ON compras_fornecedores(tenant_id, cnpj_normalizado)
    WHERE cnpj_normalizado IS NOT NULL;
CREATE INDEX idx_cmpforn_tenant_status_cad  ON compras_fornecedores(tenant_id, status_cadastro);
CREATE INDEX idx_cmpforn_tenant_codigo      ON compras_fornecedores(tenant_id, codigo_interno);
CREATE INDEX idx_cmpforn_hom_status         ON compras_fornecedores((homologacao->>'status'));
CREATE INDEX idx_cmpforn_categorias         ON compras_fornecedores USING GIN(categorias);
CREATE INDEX idx_cmpforn_tenant_created     ON compras_fornecedores(tenant_id, created_at DESC);

-- ─── compras_itens ────────────────────────────────────────────────────────────
DROP TABLE IF EXISTS compras_itens CASCADE;

CREATE TABLE compras_itens (
    id                          TEXT PRIMARY KEY,
    tenant_id                   TEXT NOT NULL,
    codigo_interno              TEXT NOT NULL,
    descricao                   TEXT NOT NULL DEFAULT '',
    categoria                   TEXT NOT NULL DEFAULT '',
    sub_categoria               TEXT DEFAULT '',
    unidade_compra              TEXT DEFAULT '',
    fator_conversao_producao    NUMERIC(12,6) DEFAULT 1.0,
    estoque_minimo              NUMERIC(12,3),
    estoque_seguranca           NUMERIC(12,3) DEFAULT 0.0,
    lead_time_dias              INTEGER DEFAULT 0,
    requer_homologacao_cq       BOOLEAN DEFAULT TRUE,
    fornecedores_homologados    JSONB DEFAULT '[]',
    created_at                  TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_cmpitens_tenant_codigo   ON compras_itens(tenant_id, codigo_interno);
CREATE INDEX        idx_cmpitens_tenant_categoria ON compras_itens(tenant_id, categoria);

-- ─── compras_condicoes_comerciais (imutável — sem updated_at) ─────────────────
DROP TABLE IF EXISTS compras_condicoes_comerciais CASCADE;

CREATE TABLE compras_condicoes_comerciais (
    id                          TEXT PRIMARY KEY,
    tenant_id                   TEXT NOT NULL,
    fornecedor_id               TEXT,
    fornecedor_nome             TEXT DEFAULT '',
    item_id                     TEXT,
    item_descricao              TEXT DEFAULT '',
    preco_unitario              NUMERIC(16,6) NOT NULL DEFAULT 0,
    preco_unitario_currency     TEXT DEFAULT 'BRL',
    prazo_pagamento_texto       TEXT DEFAULT '',
    prazo_pagamento_dias        INTEGER DEFAULT 0,
    prazo_entrega_dias_uteis    INTEGER DEFAULT 0,
    moq                         NUMERIC(12,3) DEFAULT 1.0,
    frete_tipo                  TEXT DEFAULT 'cif',
    frete_valor                 NUMERIC(12,2) DEFAULT 0.0,
    valido_ate                  TEXT,
    origem                      TEXT DEFAULT 'manual',
    cotado_por_id               TEXT,
    cotado_por_nome             TEXT DEFAULT '',
    created_at                  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_cmpcond_tenant_forn           ON compras_condicoes_comerciais(tenant_id, fornecedor_id);
CREATE INDEX idx_cmpcond_tenant_item           ON compras_condicoes_comerciais(tenant_id, item_id);
CREATE INDEX idx_cmpcond_tenant_item_date      ON compras_condicoes_comerciais(tenant_id, item_id, created_at DESC);
CREATE INDEX idx_cmpcond_tenant_item_forn_date ON compras_condicoes_comerciais(tenant_id, item_id, fornecedor_id, created_at DESC);

-- ─── compras_pos ─────────────────────────────────────────────────────────────
DROP TABLE IF EXISTS compras_pos CASCADE;

CREATE TABLE compras_pos (
    id                          TEXT PRIMARY KEY,
    tenant_id                   TEXT NOT NULL,
    numero_po                   TEXT,
    fornecedor_id               TEXT,
    fornecedor_nome             TEXT DEFAULT '',
    fornecedor_cnpj             TEXT DEFAULT '',
    status                      TEXT DEFAULT 'rascunho',
    origem                      TEXT DEFAULT 'manual',
    ops_vinculadas              JSONB DEFAULT '[]',
    data_emissao                TEXT,
    data_entrega_solicitada     TEXT,
    data_entrega_confirmada     TEXT,
    prazo_pagamento_texto       TEXT DEFAULT '',
    prazo_pagamento_dias        INTEGER DEFAULT 0,
    fornecedor_homologado       BOOLEAN DEFAULT FALSE,
    itens                       JSONB DEFAULT '[]',
    valor_total_po              NUMERIC(16,2) DEFAULT 0.0,
    compartilhamento            JSONB DEFAULT '{}',
    nfs_vinculadas              JSONB DEFAULT '[]',
    gatilho_financeiro_acionado BOOLEAN DEFAULT FALSE,
    data_vencimento_pagamento   TEXT,
    cancelado_motivo            TEXT,
    cancelado_por               TEXT,
    cancelado_em                TEXT,
    requer_aprovacao            BOOLEAN DEFAULT FALSE,
    aprovado_por                TEXT,
    aprovado_em                 TEXT,
    created_at                  TIMESTAMPTZ DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ DEFAULT NOW(),
    created_by_id               TEXT,
    created_by_nome             TEXT DEFAULT '',
    log_auditoria               JSONB DEFAULT '[]'
);

CREATE UNIQUE INDEX idx_cmppos_tenant_numero  ON compras_pos(tenant_id, numero_po) WHERE numero_po IS NOT NULL;
CREATE INDEX        idx_cmppos_tenant_status  ON compras_pos(tenant_id, status);
CREATE INDEX        idx_cmppos_tenant_forn    ON compras_pos(tenant_id, fornecedor_id);
CREATE INDEX        idx_cmppos_tenant_created ON compras_pos(tenant_id, created_at DESC);

-- ─── compras_mrp_rodadas ──────────────────────────────────────────────────────
DROP TABLE IF EXISTS compras_mrp_rodadas CASCADE;

CREATE TABLE compras_mrp_rodadas (
    id                    TEXT PRIMARY KEY,
    tenant_id             TEXT NOT NULL,
    numero_mrp            TEXT,
    status                TEXT DEFAULT 'gerada',
    ops_consideradas      JSONB DEFAULT '[]',
    snapshot_estoque      JSONB DEFAULT '{}',
    snapshot_pos_transito JSONB DEFAULT '{}',
    itens_sugeridos       JSONB DEFAULT '[]',
    aprovado_por_id       TEXT,
    aprovado_por_nome     TEXT DEFAULT '',
    aprovado_em           TEXT,
    disparado_por_id      TEXT,
    disparado_por_nome    TEXT DEFAULT '',
    created_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_cmpmrp_tenant_status  ON compras_mrp_rodadas(tenant_id, status);
CREATE INDEX idx_cmpmrp_tenant_created ON compras_mrp_rodadas(tenant_id, created_at DESC);

-- ─── compras_demandas ─────────────────────────────────────────────────────────
DROP TABLE IF EXISTS compras_demandas CASCADE;

CREATE TABLE compras_demandas (
    id                        TEXT PRIMARY KEY,
    tenant_id                 TEXT NOT NULL,
    mrp_rodada_id             TEXT,
    mrp_numero                TEXT DEFAULT '',
    item_id                   TEXT,
    item_descricao            TEXT DEFAULT '',
    quantidade                NUMERIC(12,4) DEFAULT 0.0,
    data_limite_pedido        TEXT,
    urgente                   BOOLEAN DEFAULT FALSE,
    motivo                    TEXT DEFAULT '',
    fornecedor_selecionado_id TEXT,
    condicao_comercial_id     TEXT,
    po_id                     TEXT,
    status                    TEXT DEFAULT 'pendente',
    created_at                TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_cmpdem_tenant_status  ON compras_demandas(tenant_id, status);
CREATE INDEX idx_cmpdem_tenant_mrp     ON compras_demandas(tenant_id, mrp_rodada_id);
CREATE INDEX idx_cmpdem_tenant_po      ON compras_demandas(tenant_id, po_id);
CREATE INDEX idx_cmpdem_tenant_created ON compras_demandas(tenant_id, created_at DESC);
