# KURYOS ERP — PRD (Product Requirements Document)

**Repo:** https://github.com/DEVMarlosGomes/KURYOS
**Stack:** Python/FastAPI + React/JavaScript + MongoDB

## Original Problem Statement
Implementação dos 8 itens do documento `260509_Comentarios_ERP_modulo_CRM_e_PeD_v1.docx`
referentes ao fluxo P&D / CRM. Sistema em produção com dados reais (amostra 102/A visível).
Sprints 1-4 contendo correções, novas features e refatorações de fluxo.

## User Personas
- **Comercial** (vendedor / sales_ops / sucesso_cliente) — pipeline de clientes, projetos e amostras
- **P&D** (formulador / lider_pd) — formulação, testes, ficha técnica
- **CQ** (qa) — aprovações e revisão de documentos
- **Engenharia de Produto** — kickoff, BOM/embalagem
- **Compras** — custo v2 (embalagem, mão de obra, overhead)
- **Admin** — total

## Architecture (estado atual)
- Backend: FastAPI (`/app/backend/server.py` + módulos `pd_routes.py`, `crm_routes.py`, etc.)
- Frontend: React + Tailwind + Shadcn UI (`/app/frontend/src/`)
- DB: MongoDB (collections: `pd_*`, `crm_*`, `users`, `tenants`, `ordens_manipulacao`, `pd_retrocessos_pendentes`)
- RBAC: `rbac.py` com perfis canônicos + helpers de visibilidade de custos

## Implementação concluída (2026-05-18) — Sprints 1-4

### SPRINT 1 — Fixes rápidos
- **Item 1 (PUT formula-item)** ✅ Já existia: `PUT /api/pd/formula-items/{item_id}` no `pd_routes.py:1762`.
  Frontend `PDDetail.js` já usa `startEditItem` / `saveEditItem` com chamada para esse endpoint.
- **Item 7 (% fragrância no banco)** ✅ `formula_bank` já retornava `fragrance_percentage`.
  Refinada a detecção para usar `phase` (`Fragrância`) + keywords. Frontend `PDFormulaBank.js`
  já exibe a coluna com badge colorido.

### SPRINT 2 — P&D core
- **Item 2 (autocomplete MP)** ✅ Novo endpoint `GET /api/pd/catalog/search?q=...` retorna
  itens com fornecedores ordenados por preço (mais barato → mais caro) + semáforo
  (`verde / amarelo / laranja / vermelho`) e flag `homologado`. Frontend `PDDetail.js` já
  tinha `pickFromCatalog` com ranking — novo endpoint disponível para uso futuro.
- **Item 8 (modo de preparo estruturado)** ✅ `FormulaUpdate` aceita `modo_preparo` como
  lista de objetos `{ordem, fase, descricao, temperatura_c, tempo_minutos, equipamento, rpm, alerta}`
  (retrocompat com lista de strings). Novo componente
  `/app/frontend/src/components/ModoPreparoEditor.js` para edição visual.

### SPRINT 3 — Documentos operacionais
- **Item 4 (Ficha Técnica sem custos)** ✅ Novo endpoint JSON
  `GET /api/pd/requests/{req_id}/ficha-tecnica-data` retorna estrutura sem nenhum campo
  financeiro (`price_per_kg`, `cost_brl`, `cost_kg_usd` removidos). Também ajustado
  `GET /api/pd/requests/{req_id}/ficha-tecnica-ui` para strip de custos nos `formula_items`.
  PDF da FT (`/ficha-tecnica`) já tinha apenas colunas operacionais (Ingrediente, Fornecedor,
  %Fórmula, Qtd/Lote).
- **Item 3 (Ordem de Manipulação em lote)** ✅ Novo módulo completo:
  - `POST /api/pd/ordens-manipulacao` — gera OM calculando quantidade em gramas da base
    e fragrâncias por variação com fator de perda configurável (default 10%)
  - `GET /api/pd/ordens-manipulacao` — lista OMs (filtros: sample_id, status, formula_base_id)
  - `GET /api/pd/ordens-manipulacao/{id}` — detalhe
  - `PUT /api/pd/ordens-manipulacao/{id}/status` — fluxo `rascunho → emitida → executada`
  - `DELETE /api/pd/ordens-manipulacao/{id}` — só se não estiver executada
  - `GET /api/pd/ordens-manipulacao/{id}/pdf` — PDF profissional (reportlab) com cabeçalho,
    tabela BASE, tabela FRAGRÂNCIAS, resumo e assinatura
  - Frontend: nova aba **Ordens Manip.** no `PDDetail.js` + componente
    `OrdemManipulacaoSection.js` com formulário, lista e botões de PDF/status.
  - Numeração `OM-AAAA-NNNN` por tenant.

### SPRINT 4 — Fluxo e governança
- **Item 5 (versionamento de custos v1/v2 com visibilidade por perfil)** ✅ Já existia
  infraestrutura completa (`cost-versions/v1`, `cost-versions/v2`, `submit`, `finalize`).
  Ajustes:
  - `_build_cost_versions_response` agora retorna 3 visões: `compras` (full),
    `pd` (v1 full + v2 status), `comercial` (apenas `total_final` + status v2).
  - `GET /api/pd/developments/{id}/cost-versions` aberto para roles comerciais.
- **Item 6 (dupla aprovação + retrocesso com justificativa)** ✅
  - Novos status no Pipeline P&D: `aprovado_internamente`, `entregue_ao_comercial`.
  - Mapeamento CRM: `entregue_ao_comercial` → `aguardando_envio_cliente` (variação CRM).
  - Validação de transições válidas em `PUT /api/crm/pd/cards/{id}/move` (formulador
    recebe `400` com lista de transições permitidas se tentar pular etapa; admin/lider_pd
    podem pular).
  - Novos endpoints:
    - `POST /api/pd/cards/{id}/retroceder` — justificativa min. 10 chars; admin/lider_pd
      executam direto; outros perfis criam solicitação pendente.
    - `GET /api/pd/retrocessos/pendentes` — fila para Líder P&D.
    - `PUT /api/pd/retrocessos/{id}/decisao` — aprovar / negar.
  - Novo componente frontend `RetrocederPDCardButton.js`.

## Backlog / Próximos passos
### P1 (próxima sprint)
- Wire backend `GET /api/pd/catalog/search` no autocomplete real do `PDDetail.js` (hoje usa
  filtragem client-side do `/catalog`).
- Integrar `ModoPreparoEditor` na aba **Manipulação** do `PDDetail.js`.
- Integrar `RetrocederPDCardButton` nos pontos de transição (PipelinePage + PDDetail header).
- Adicionar dashboard de "Retrocessos pendentes" no PipelinePage para Líder P&D.

### P2
- Integração FT/OM com sistema de assinaturas eletrônicas.
- Versionamento histórico das OMs.
- Notificação ao Comercial quando card chega em `entregue_ao_comercial`.
- Export Excel da OM em paralelo ao PDF.

## Test Credentials
Ver `/app/memory/test_credentials.md`.
