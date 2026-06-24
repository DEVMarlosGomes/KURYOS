-- 002_fase0_fix_schema.sql
-- Adiciona colunas faltantes nas tabelas FASE 0 para corresponder ao modelo FastAPI.
-- As tabelas foram criadas em 001_initial_schema.sql com colunas genéricas.
-- Este migration adiciona os campos específicos do domínio de negócio.
-- Execute no Supabase SQL Editor.

-- ─── categorias ──────────────────────────────────────────────────────────────
ALTER TABLE categorias
  ADD COLUMN IF NOT EXISTS status              TEXT DEFAULT 'pendente',
  ADD COLUMN IF NOT EXISTS solicitado_por      TEXT,
  ADD COLUMN IF NOT EXISTS solicitado_por_id   TEXT,
  ADD COLUMN IF NOT EXISTS solicitado_em       TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS aprovado_por        TEXT,
  ADD COLUMN IF NOT EXISTS aprovado_por_id     TEXT,
  ADD COLUMN IF NOT EXISTS aprovado_em         TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS justificativa       TEXT,
  ADD COLUMN IF NOT EXISTS justificativa_aprovacao TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_categorias_tenant_cat3
  ON categorias(tenant_id, cat3);
CREATE INDEX IF NOT EXISTS idx_categorias_tenant_status
  ON categorias(tenant_id, status);

-- ─── fragrancias ─────────────────────────────────────────────────────────────
ALTER TABLE fragrancias
  ADD COLUMN IF NOT EXISTS codigo_interno  TEXT,
  ADD COLUMN IF NOT EXISTS inspiracao      TEXT,
  ADD COLUMN IF NOT EXISTS descricao       TEXT,
  ADD COLUMN IF NOT EXISTS status          TEXT DEFAULT 'ativa',
  ADD COLUMN IF NOT EXISTS fornecedores    JSONB DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS created_by      TEXT,
  ADD COLUMN IF NOT EXISTS created_by_name TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_fragrancias_tenant_codigo
  ON fragrancias(tenant_id, codigo_interno)
  WHERE codigo_interno IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_fragrancias_tenant_status
  ON fragrancias(tenant_id, status);

-- ─── material_tipos ──────────────────────────────────────────────────────────
ALTER TABLE material_tipos
  ADD COLUMN IF NOT EXISTS tipo2         TEXT,
  ADD COLUMN IF NOT EXISTS subtipos      JSONB DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS justificativa TEXT,
  ADD COLUMN IF NOT EXISTS criado_por    TEXT,
  ADD COLUMN IF NOT EXISTS criado_por_id TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_material_tipos_tenant_tipo2
  ON material_tipos(tenant_id, tipo2)
  WHERE tipo2 IS NOT NULL;

-- ─── materiais ───────────────────────────────────────────────────────────────
ALTER TABLE materiais
  ADD COLUMN IF NOT EXISTS codigo_interno  TEXT,
  ADD COLUMN IF NOT EXISTS tipo2           TEXT,
  ADD COLUMN IF NOT EXISTS subtipo         TEXT,
  ADD COLUMN IF NOT EXISTS descricao       TEXT,
  ADD COLUMN IF NOT EXISTS unidade_estoque TEXT DEFAULT 'kg',
  ADD COLUMN IF NOT EXISTS unidade_compra  TEXT DEFAULT 'kg',
  ADD COLUMN IF NOT EXISTS fator_conversao NUMERIC(10,4) DEFAULT 1.0,
  ADD COLUMN IF NOT EXISTS atributos       JSONB DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS fornecedores    JSONB DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS status          TEXT DEFAULT 'ativo',
  ADD COLUMN IF NOT EXISTS created_by      TEXT,
  ADD COLUMN IF NOT EXISTS created_by_name TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_materiais_tenant_codigo
  ON materiais(tenant_id, codigo_interno)
  WHERE codigo_interno IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_materiais_tenant_tipo2_status
  ON materiais(tenant_id, tipo2, status);

-- ─── graneis ─────────────────────────────────────────────────────────────────
ALTER TABLE graneis
  ADD COLUMN IF NOT EXISTS codigo_interno  TEXT,
  ADD COLUMN IF NOT EXISTS descricao       TEXT,
  ADD COLUMN IF NOT EXISTS produto_pai_id  TEXT,
  ADD COLUMN IF NOT EXISTS unidade_estoque TEXT DEFAULT 'kg',
  ADD COLUMN IF NOT EXISTS standalone      BOOLEAN DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS created_by      TEXT,
  ADD COLUMN IF NOT EXISTS created_by_name TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_graneis_tenant_codigo
  ON graneis(tenant_id, codigo_interno)
  WHERE codigo_interno IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_graneis_tenant_produto
  ON graneis(tenant_id, produto_pai_id);
