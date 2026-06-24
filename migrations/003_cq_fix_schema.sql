-- 003_cq_fix_schema.sql
-- Adiciona colunas faltantes nas 6 tabelas CQ para corresponder ao modelo FastAPI.
-- Execute no Supabase SQL Editor.

-- ─── cq_registros_analise ────────────────────────────────────────────────────
ALTER TABLE cq_registros_analise
  ADD COLUMN IF NOT EXISTS numero_ra                    TEXT,
  ADD COLUMN IF NOT EXISTS tipo                         TEXT,
  ADD COLUMN IF NOT EXISTS status                       TEXT DEFAULT 'rascunho',
  ADD COLUMN IF NOT EXISTS lote_id                      TEXT,
  ADD COLUMN IF NOT EXISTS lote_numero                  TEXT,
  ADD COLUMN IF NOT EXISTS item_id                      TEXT,
  ADD COLUMN IF NOT EXISTS item_nome                    TEXT,
  ADD COLUMN IF NOT EXISTS item_tipo                    TEXT,
  ADD COLUMN IF NOT EXISTS fornecedor_id                TEXT,
  ADD COLUMN IF NOT EXISTS fornecedor_nome              TEXT,
  ADD COLUMN IF NOT EXISTS nf_numero                    TEXT,
  ADD COLUMN IF NOT EXISTS nf_data                      TEXT,
  ADD COLUMN IF NOT EXISTS quantidade_recebida          NUMERIC(12,3),
  ADD COLUMN IF NOT EXISTS unidade                      TEXT,
  ADD COLUMN IF NOT EXISTS numero_lote_fornecedor       TEXT,
  ADD COLUMN IF NOT EXISTS data_fabricacao_fornecedor   TEXT,
  ADD COLUMN IF NOT EXISTS data_validade_fornecedor     TEXT,
  ADD COLUMN IF NOT EXISTS parametros                   JSONB DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS resultado_geral              TEXT,
  ADD COLUMN IF NOT EXISTS analista_id                  TEXT,
  ADD COLUMN IF NOT EXISTS analista_nome                TEXT,
  ADD COLUMN IF NOT EXISTS data_analise                 TEXT,
  ADD COLUMN IF NOT EXISTS fotos_file_ids               JSONB DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS amostra_retencao_id          TEXT,
  ADD COLUMN IF NOT EXISTS rnc_id                       TEXT,
  ADD COLUMN IF NOT EXISTS coa_gerado                   BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS coa_enviado_cliente          BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS coa_enviado_em               TEXT,
  ADD COLUMN IF NOT EXISTS updated_at                   TIMESTAMPTZ DEFAULT NOW(),
  ADD COLUMN IF NOT EXISTS log_auditoria                JSONB DEFAULT '[]';

CREATE UNIQUE INDEX IF NOT EXISTS idx_cq_ra_tenant_numero
  ON cq_registros_analise(tenant_id, numero_ra) WHERE numero_ra IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cq_ra_tenant_status
  ON cq_registros_analise(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_cq_ra_tenant_lote
  ON cq_registros_analise(tenant_id, lote_id);
CREATE INDEX IF NOT EXISTS idx_cq_ra_tenant_tipo
  ON cq_registros_analise(tenant_id, tipo);

-- ─── cq_checklists ───────────────────────────────────────────────────────────
ALTER TABLE cq_checklists
  ADD COLUMN IF NOT EXISTS numero_ck              TEXT,
  ADD COLUMN IF NOT EXISTS status                 TEXT DEFAULT 'em_preenchimento',
  ADD COLUMN IF NOT EXISTS op_id                  TEXT,
  ADD COLUMN IF NOT EXISTS op_numero              TEXT,
  ADD COLUMN IF NOT EXISTS lote_id                TEXT,
  ADD COLUMN IF NOT EXISTS linha                  TEXT,
  ADD COLUMN IF NOT EXISTS turno                  TEXT,
  ADD COLUMN IF NOT EXISTS subtipo_insumo         TEXT,
  ADD COLUMN IF NOT EXISTS horario_previsto_ronda TEXT,
  ADD COLUMN IF NOT EXISTS ra_id                  TEXT,
  ADD COLUMN IF NOT EXISTS ncs_identificadas      INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS rncs_geradas           JSONB DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS preenchido_por_id      TEXT,
  ADD COLUMN IF NOT EXISTS preenchido_por_nome    TEXT,
  ADD COLUMN IF NOT EXISTS aprovado_por_id        TEXT,
  ADD COLUMN IF NOT EXISTS aprovado_por_nome      TEXT,
  ADD COLUMN IF NOT EXISTS aprovado_em            TEXT,
  ADD COLUMN IF NOT EXISTS log_auditoria          JSONB DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS ck5_medias             JSONB DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_cq_ck_tenant_op
  ON cq_checklists(tenant_id, op_id);
CREATE INDEX IF NOT EXISTS idx_cq_ck_tenant_tipo_status
  ON cq_checklists(tenant_id, tipo, status);
CREATE INDEX IF NOT EXISTS idx_cq_ck_tenant_lote
  ON cq_checklists(tenant_id, lote_id);

-- ─── cq_rncs ─────────────────────────────────────────────────────────────────
ALTER TABLE cq_rncs
  ADD COLUMN IF NOT EXISTS numero_rnc                      TEXT,
  ADD COLUMN IF NOT EXISTS classificacao                    TEXT,
  ADD COLUMN IF NOT EXISTS origem                          TEXT,
  ADD COLUMN IF NOT EXISTS ra_id                           TEXT,
  ADD COLUMN IF NOT EXISTS ck_id                           TEXT,
  ADD COLUMN IF NOT EXISTS lote_id                         TEXT,
  ADD COLUMN IF NOT EXISTS lote_numero                     TEXT,
  ADD COLUMN IF NOT EXISTS item_nome                       TEXT,
  ADD COLUMN IF NOT EXISTS fornecedor_id                   TEXT,
  ADD COLUMN IF NOT EXISTS fornecedor_nome                 TEXT,
  ADD COLUMN IF NOT EXISTS quantidade_afetada              NUMERIC(12,3),
  ADD COLUMN IF NOT EXISTS fotos_file_ids                  JSONB DEFAULT '[]',
  ADD COLUMN IF NOT EXISTS disposicao_imediata             TEXT,
  ADD COLUMN IF NOT EXISTS responsavel_id                  TEXT,
  ADD COLUMN IF NOT EXISTS responsavel_nome                TEXT,
  ADD COLUMN IF NOT EXISTS prazo_resolucao                 TEXT,
  ADD COLUMN IF NOT EXISTS comunicado_fornecedor_enviado   BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS comunicado_enviado_em           TEXT,
  ADD COLUMN IF NOT EXISTS resposta_fornecedor             TEXT,
  ADD COLUMN IF NOT EXISTS capa_descricao                  TEXT,
  ADD COLUMN IF NOT EXISTS evidencia_resolucao             TEXT,
  ADD COLUMN IF NOT EXISTS encerrado_por_id                TEXT,
  ADD COLUMN IF NOT EXISTS encerrado_em                    TEXT,
  ADD COLUMN IF NOT EXISTS autorizacao_concessao           TEXT,
  ADD COLUMN IF NOT EXISTS log_auditoria                   JSONB DEFAULT '[]';

CREATE UNIQUE INDEX IF NOT EXISTS idx_cq_rnc_tenant_numero
  ON cq_rncs(tenant_id, numero_rnc) WHERE numero_rnc IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cq_rnc_tenant_status
  ON cq_rncs(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_cq_rnc_tenant_fornecedor
  ON cq_rncs(tenant_id, fornecedor_id);

-- ─── cq_retencoes ────────────────────────────────────────────────────────────
ALTER TABLE cq_retencoes
  ADD COLUMN IF NOT EXISTS numero_ret          TEXT,
  ADD COLUMN IF NOT EXISTS tipo                TEXT,
  ADD COLUMN IF NOT EXISTS ra_id               TEXT,
  ADD COLUMN IF NOT EXISTS lote_id             TEXT,
  ADD COLUMN IF NOT EXISTS lote_numero         TEXT,
  ADD COLUMN IF NOT EXISTS item_nome           TEXT,
  ADD COLUMN IF NOT EXISTS fornecedor_nome     TEXT,
  ADD COLUMN IF NOT EXISTS quantidade_retida   NUMERIC(12,3),
  ADD COLUMN IF NOT EXISTS localizacao_fisica  TEXT,
  ADD COLUMN IF NOT EXISTS data_coleta         TEXT,
  ADD COLUMN IF NOT EXISTS data_limite_guarda  TEXT,
  ADD COLUMN IF NOT EXISTS updated_at          TIMESTAMPTZ DEFAULT NOW();

CREATE UNIQUE INDEX IF NOT EXISTS idx_cq_ret_tenant_numero
  ON cq_retencoes(tenant_id, numero_ret) WHERE numero_ret IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cq_ret_tenant_status
  ON cq_retencoes(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_cq_ret_data_limite
  ON cq_retencoes(tenant_id, data_limite_guarda);

-- ─── cq_instrumentos ─────────────────────────────────────────────────────────
ALTER TABLE cq_instrumentos
  ADD COLUMN IF NOT EXISTS codigo_interno           TEXT,
  ADD COLUMN IF NOT EXISTS frequencia_calibracao_dias INTEGER,
  ADD COLUMN IF NOT EXISTS ultima_calibracao_iso    TEXT,
  ADD COLUMN IF NOT EXISTS certificado_file_id      TEXT,
  ADD COLUMN IF NOT EXISTS historico_calibracoes    JSONB DEFAULT '[]';

CREATE UNIQUE INDEX IF NOT EXISTS idx_cq_instr_tenant_codigo
  ON cq_instrumentos(tenant_id, codigo_interno) WHERE codigo_interno IS NOT NULL;

-- ─── cq_status_lote ──────────────────────────────────────────────────────────
ALTER TABLE cq_status_lote
  ADD COLUMN IF NOT EXISTS lote_id          TEXT,
  ADD COLUMN IF NOT EXISTS lote_numero      TEXT,
  ADD COLUMN IF NOT EXISTS status_anterior  TEXT,
  ADD COLUMN IF NOT EXISTS status_novo      TEXT,
  ADD COLUMN IF NOT EXISTS motivo           TEXT,
  ADD COLUMN IF NOT EXISTS ra_id            TEXT,
  ADD COLUMN IF NOT EXISTS rnc_id           TEXT,
  ADD COLUMN IF NOT EXISTS alterado_por_id   TEXT,
  ADD COLUMN IF NOT EXISTS alterado_por_nome TEXT;

CREATE INDEX IF NOT EXISTS idx_cq_sl_tenant_lote
  ON cq_status_lote(tenant_id, lote_id);
CREATE INDEX IF NOT EXISTS idx_cq_sl_tenant_created
  ON cq_status_lote(tenant_id, created_at DESC);
