# CRM Kuryos — PRD

## Visão Geral
Pipeline inteligente para cosméticos, perfumaria e desenvolvimento de produtos.
Sistema full-stack: React frontend + FastAPI backend + MongoDB.

## Arquitetura
- Backend: FastAPI (pd_routes.py, crm_routes.py, estoque_routes.py, workflow_engine.py, workflow_routes.py, server.py)
- Frontend: React com Tailwind/shadcn (PDDetail.js, PDPage.js, PDFormulaBank.js, CRM1Page.js, CRM2Page.js, TasksPage.js, ...)
- MongoDB: pd_requests, pd_developments, pd_formulas, pd_formula_items, pd_tests, pd_samples, pd_ficha_tecnica, pd_lab_results, pd_stability_studies, pd_stability_readings, workflow_tasks, etc.

## O que está implementado

### Módulo P&D
- Kanban de cards P&D com workflow de status (PENDING → IN_PROGRESS → IN_TESTS → IN_APPROVAL → APPROVED/REJECTED)
- **Formulação completa [2026-05-06]**:
  - Campo Fornecedor por ingrediente (auto-fill catálogo + texto livre)
  - Coluna Quantidade/Lote (volume × %/100)
  - RN-PD-02: bloqueio IN_PROGRESS→IN_TESTS sem ingredientes ou total ≠ 100%
  - canEdit: admin, gestor, formulador, lider_pd, engenharia_produto
- **Ficha Técnica como view dinâmica [2026-05-06]**:
  - Aba "Ficha Técnica" no PDDetail: Identificação, tabela de Análise (6 params), Formulação, Elaboração, APROVADO/REPROVADO
  - Endpoints: GET/PUT /api/pd/requests/{id}/ficha-tecnica-ui
- **Tarefas bloqueantes em transições [2026-05-06]**: backend checa blocking_tasks, frontend mostra dialog
- **Banco de Fórmulas — Versionamento/Imutabilidade [2026-05-06]**:
  - RN-BF-01/RN-PD-06: fórmula auto-locked quando card avança para IN_TESTS
  - Bloqueio de add/delete/update em fórmulas locked (409 com mensagem RN-BF-01)
  - Badge "Registrada" + botão "Nova Versão" por fórmula locked
  - Endpoint: POST /api/pd/formulas/{id}/new-version (justificativa ≥10 chars, copia ingredientes)
- **Aba Estabilidades [2026-05-06]**:
  - Nova aba "Estabilidades" no PDDetail
  - 9 condições (Ambiente, Estufa 40/45°C, Geladeira 5°C, Freezer -5°C, Ciclo Freeze/Thaw, etc.)
  - Checkpoints D0/D7/D15/D30/D45/D60/D90 com progresso visual
  - Badge D-2 para leituras iminentes
  - "Registrar Leitura" dialog com 12 parâmetros (aspecto, cor, pH, viscosidade, etc.)
  - Auto-criação do estudo ao abrir a aba
  - Endpoint: GET /api/pd/requests/{id}/stability-study
- **Sistema de Tarefas Pendentes [2026-05-06]**:
  - Botão "Verificar D-1" → POST /api/workflow/tasks/check-reminders (cria notificações, marca escalação)
  - Botão "Criar Tarefa Manual" com dialog completo (entidade, tipo, prazo, bloqueante)
  - Badges de Escalado (vermelho) e D-1 (âmbar) nos cards de tarefa
  - Endpoint: POST /api/workflow/tasks/check-reminders

### Módulo CRM Comercial
- CRM Pipeline comercial (CRM1/CRM2), Estoque, Auditoria

## Backlog Priorizado

### P1 (Alta prioridade)
- Documentos vivos (FT e EPA): detecção automática de alteração em dado de origem → nova versão + tarefa de aprovação
- Módulo de Estabilidades: conectar alerts D-2 ao sistema de notificações do usuário
- Alerta automático de estabilidade (cron/scheduler) — hoje só manual via check-reminders

### P2 (Médio prazo)
- Perfis de usuário e permissões reais por módulo (formulador não vê CRM comercial, CQ só aprova)
- Homologações: bloqueio liberação para Compras quando MP sem fornecedor homologado
- Responsividade mobile/tablet (RN 12.8)

### Backlog / Futuro
- EPA como documento vivo
- Melhorar PDF da Ficha Técnica (incluir novos campos análise + assinatura digital)
- Alertas de fornecimento (< 3 fornecedores por MP)

## Credenciais de Teste
- Admin: admin@kuryos.com / admin123
- Formulador: formulador@kuryos.com / kuryos123
- Demais roles: {role}@kuryos.com / kuryos123

## Update — 07/05/2026: Briefing Card → Modal de Detalhes (P&D)
**Solicitação**: "traga essas informações para o P&D ao clicar no card"
- Card "Briefing do Projeto (CRM)" no PDDetail (Overview) agora é **clicável** (cursor-pointer, hover, ícone Eye)
- Ao clicar, abre **Dialog completo** (data-testid `briefing-detail-dialog`) com 5 seções:
  - **Identificação**: Produto, Cliente, Nome do Projeto, Orçamento (1, 2, 3, 9)
  - **Especificações Técnicas**: Textura, Aplicação, Sensorial, pH (10, 11, 12, 13)
  - **Objetivos & Detalhes**: Objetivo, Aplicações a Desenvolver, Ativos para Claims (4, 5, 6)
  - **Referências**: Texto + URL de fotos (7, 8)
  - **Outras Observações** (14)
- Card preview mantém top-line + hint "Clique para ver todas as informações do briefing"
- Backend já retornava `client_info` em GET /api/pd/requests/{id}/full — sem mudanças no backend
- **Testado**: 100% sucesso (iteração 9). Test data: PD `c04daf64-da3a-4e86-b6d9-04e917209adc`

## Update — 07/05/2026 (sessão 2): Módulo Pedidos (Ordem de Produção)
**Solicitação**: "aba de pedidos. Depois que virar um pedido, vai pra essa aba. Pós amostra pronta, aprovada e com pedido feito"

### Backend (`/app/backend/orders_routes.py`)
- Coleção MongoDB: `orders` (com índices em tenant_id, status, pd_request_id, created_at)
- Endpoints CRUD: `GET/POST /api/orders`, `GET/PUT/DELETE /api/orders/{id}`, `GET /api/orders/{id}/pdf`
- **Auto-criação na aprovação P&D**: hook em `pd_routes.py` chama `auto_create_order_on_pd_approval(pd_id, user)` quando status vira APPROVED — **idempotente** (1 pedido por PD)
- **Auto-fill do CRM**: razão social, CNPJ, cidade/UF, responsável, telefone, e-mail vindos de `crm_clients` via `client_card_id` → `cards` → `cliente_id`
- **Auto-fill do P&D**: itens iniciais com SKU/código interno + nome do projeto + volume
- **PDF "Ordem de Produção"** gerado via reportlab com layout idêntico ao mockup Kuryos: título centralizado, logo, 6 seções numeradas (Informações Iniciais, Dados do Cliente, Frete, Pedido com tabela em azul Kuryos #1F2C5C, Condições, Insumos), notas de rodapé

### Frontend
- Nova entrada no Sidebar: **Pedidos** (icon: ShoppingCart, visível a TODOS os perfis)
- `/orders` — `OrdersPage.js`: listagem com 5 stats (Total, Rascunho, Confirmado, Em Produção, Valor Total), busca, filtro por status, cards clicáveis com badge "Auto-gerado"
- `/orders/:id` — `OrderDetail.js`: 6 seções editáveis, dropdown de status, botões "Gerar PDF" + "Editar/Salvar/Cancelar", tabela de itens com auto-recálculo de valor_total
- Link de volta ao P&D quando pedido foi auto-gerado

### Status workflow
`rascunho` → `confirmado` → `em_producao` → `concluido` (+ `cancelado`)

### Numeração
Format `MM_NN` (ex: `05_01`) — sequencial mensal por tenant

### Testado
- iteração 10: 19/19 backend pytest + frontend admin/vendedor/formulador — **100% sucesso, sem bugs**
- Validado: auto-criação, idempotência, RBAC, CRUD, PDF download, edit flow, navegação P&D↔Pedidos

## Update — 08/05/2026 (sessão E2E): Validação end-to-end completa do fluxo CRM → SKU

**Solicitação**: "RODE ESSE PROJETO DE PONTA A PONTA CRIANDO CLIENTE, QUALIFICANDO ELE ATÉ APROVAR. FAÇA ETAPA POR ETAPA COMPLETO."

### Escopo executado
- Login via `POST /api/auth/login` (cookie HttpOnly) com `admin@kuryos.com`
- Cliente criado em `prospeccao` (Bella Cosmética Premium Ltda) → qualificado → projeto_em_discussao
- 2 tarefas bloqueantes geradas pelo workflow engine — concluídas via `/api/workflow/tasks/{id}/complete`
- Projeto criado via batch (`POST /api/crm/projects/batch`) e movido até `amostra_solicitada`
- Amostra `#101` criada com 2 variações (`POST /api/crm/samples/batch/v2`); cards P&D auto-criados
- Variação `101/A` percorreu solicitada → em_elaboracao → enviada → aprovada (com bloqueio por feedback do cliente exercitado)
- 🎉 **SKU `KRY-001` gerado automaticamente** ao aprovar a variação (preço R$ 95,50, status ativo)
- Projeto auto-avançou para `em_negociacao` (auto-orquestração via `project_auto_moved`)
- Validação UI: capturadas screenshots Login, CRM1, CRM2, CRM3, SKUs, Pipeline P&D, Tasks e detalhes — UI espelha exatamente os dados criados via API
- 20+ entries em `/api/workflow/audit-logs` confirmam toda a trilha

### Comportamentos validados em produção
- ✅ Validação de CNPJ (algoritmo) e enums (segmento/porte/UF/canal_origem)
- ✅ Workflow engine bloqueia transição com tarefas `blocking=true`
- ✅ RBAC: tarefas atribuídas automaticamente por papel
- ✅ Herança de dados cliente→projeto→amostra→variação
- ✅ Auto-criação de pd_card por variação (sync bidirecional CRM↔P&D)
- ✅ Geração sequencial de SKU (`KRY-001` formato)
- ✅ Auto-orquestração de stages após aprovação de amostra

### Artefatos gerados
- `/app/E2E_REPORT.md` — relatório markdown completo com cada etapa (curl, payloads, responses, screenshots descritos)
- IDs criados:
  - Client: `60f9d0b1-43b5-4d54-83c4-d855bc18214f`
  - Project: `0dff86d9-e2f2-4951-8a8e-d85dc13e82f2`
  - Sample: `e6d83c4b-5687-4f36-ac5f-6a4e5aea07cc`
  - Variação A: `b43bfd3a-55c5-490d-b18c-ad9ca0cfd2cb` → SKU `e541ee14-...` (KRY-001)
  - Variação B: `72ee8419-e9fd-42ee-825c-736ce633a2b4` (em "solicitada", pronta para próximo ciclo)

### Próximos passos sugeridos (backlog dessa sessão)
- Aprovar 101/B para gerar `KRY-002` e validar incremento sequencial
- Criar pedido para `KRY-001` (`POST /api/orders`) e validar auto-cálculo de `frequencia_media_recompra_dias`
- Mover o cliente até `cliente_fechado` registrando `data_pedido` e `valor_primeiro_pedido`

