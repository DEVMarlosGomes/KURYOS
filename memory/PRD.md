# CRM Kuryos — PRD

## Visão Geral
Pipeline inteligente para cosméticos, perfumaria e desenvolvimento de produtos.
Sistema full-stack: React frontend + FastAPI backend + MongoDB.

## Arquitetura
- Backend: FastAPI (pd_routes.py, crm_routes.py, estoque_routes.py, workflow_engine.py, workflow_routes.py, server.py)
- Frontend: React com Tailwind/shadcn (PDDetail.js, PDPage.js, PDFormulaBank.js, CRM1Page.js, CRM2Page.js, ...)
- MongoDB: Collections: pd_requests, pd_developments, pd_formulas, pd_formula_items, pd_tests, pd_samples, pd_ficha_tecnica, pd_lab_results, workflow_tasks, etc.

## O que está implementado

### Módulo P&D
- Kanban de cards P&D com workflow de status (PENDING → IN_PROGRESS → IN_TESTS → IN_APPROVAL → APPROVED/REJECTED)
- Aba Manipulação/Formulação: ingredientes com catálogo de MPs, %, preço R$/kg, custo BRL/USD, % custo
- **[2026-05-06]** Formulação completa:
  - Campo **Fornecedor por ingrediente** (auto-fill do catálogo; texto livre para MPs manuais)
  - Coluna **Quantidade/Lote** calculada (volume × %/100)
  - **RN-PD-02**: bloqueio de transição IN_PROGRESS → IN_TESTS quando não há ingredientes ou total ≠ 100%
  - `canEdit` expandido para roles: admin, gestor, formulador, lider_pd, engenharia_produto
- **[2026-05-06]** Ficha Técnica como view dinâmica na UI:
  - Nova aba "Ficha Técnica" no PDDetail
  - Identificação do Produto (produto, lote, data fabricação, validade, quantidade)
  - Tabela de Análise do Produto Fabricado (Aspecto, Cor, Densidade, Odor, pH, Teor de Álcool) com colunas ESPECIFICAÇÃO / RESULTADO / PA
  - Tabela de Formulação puxada dos ingredientes da fórmula
  - Descrição da Elaboração (modo de preparo)
  - Campos APROVADO / REPROVADO + Resp. Técnico
  - Endpoints: GET/PUT /api/pd/requests/{req_id}/ficha-tecnica-ui
- **[2026-05-06]** Tarefas bloqueantes em transições de status:
  - `transition_status` checa `blocking_tasks` via workflow_engine
  - Frontend mostra dialog de confirmação com lista de tarefas bloqueantes
  - Full detail response inclui `blocking_tasks` por pd_card
- Banco de Fórmulas (PDFormulaBank.js): busca de MPs, INCI, fornecedores
- Módulo de Estabilidades: backend completo (9 condições, checkpoints D0/D7/D15/D30...)
- Homologação de fornecedores/MPs: alertas de risco (< 3 fornecedores por MP)
- Workflow Tasks engine: notificações, tarefas por perfil, escalada
- CRM Pipeline comercial (CRM1/CRM2)
- Módulo de Estoque

## Backlog Priorizado

### P0 (Crítico — impede uso)
- [FEITO] RN-PD-02: bloquear IN_TESTS sem ingredientes
- [FEITO] Fornecedor por ingrediente
- [FEITO] Ficha Técnica como view dinâmica
- [FEITO] Tarefas bloqueantes em transições

### P1 (Alta prioridade)
- Banco de Fórmulas — imutabilidade/versionamento: RN-BF-01/RN-PD-06 (fórmulas imutáveis após registro, toda alteração gera nova versão com justificativa)
- Módulo de Estabilidades frontend: conectar as 9 condições + checkpoints ao PDDetail (aba Estabilidades)
- Alerta D-2 para leituras de estabilidade

### P2 (Médio prazo)
- Documentos vivos (FT e EPA) com detecção automática de alteração → nova versão + tarefa de aprovação
- Sistema de Tarefas Pendentes completo: dashboard por perfil, notificações D-1, escalada
- Homologações de fornecedores: bloqueio liberação para Compras quando MP sem fornecedor homologado
- Perfis de usuário e permissões reais por módulo (formulador não vê CRM comercial, CQ só aprova)

### Backlog / Futuro
- Responsividade mobile/tablet (RN 12.8): campos P&D otimizados para tablet/celular
- EPA (Estudo de Pré-Aprovação) como documento vivo
- Gerador de PDF para Ficha Técnica (melhorar o existente para incluir novos campos)
- Alertas de fornecimento (< 3 fornecedores por MP)

## Credenciais de Teste
- Admin: admin@kuryos.com / admin123
- Formulador: formulador@kuryos.com / kuryos123
- Demais roles: @kuryos.com / kuryos123
