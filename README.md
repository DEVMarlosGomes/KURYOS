# KURYOS

> Pipeline inteligente para cosméticos, perfumaria e desenvolvimento de produtos.

Sistema ERP SaaS full-stack voltado para indústrias de cosméticos e perfumaria. Cobre todo o ciclo de vida do produto — da formulação em P&D até a expedição — com rastreabilidade completa, controle de qualidade imutável e automação de workflows.

---

## Stack

| Camada | Tecnologia |
|--------|-----------|
| Frontend | React 19, React Router 7, Tailwind CSS 3, shadcn/ui (Radix UI) |
| Backend | FastAPI 0.110.1, Uvicorn, Pydantic 2 |
| Banco de Dados | MongoDB (Motor async 3.3.1) |
| Autenticação | JWT (access 12h / refresh 7d) + bcrypt |
| PDF / Excel | ReportLab + OpenPyXL |
| Integrações LLM | OpenAI, Google Generative AI, LiteLLM |
| Testes | Pytest + pytest-asyncio |

---

## Módulos

| Módulo | Descrição | Endpoints |
|--------|-----------|-----------|
| **P&D** | Formulações, estudos de estabilidade, versioning de fórmulas, Ficha Técnica | ~288 |
| **CRM Comercial** | Pipeline Kanban de clientes, projetos e amostras | ~153 |
| **Compras** | Fornecedores, MRP, cotações, ordens de compra | ~125 |
| **CQ** | Registros de análise, checklists, RNCs, retenções, instrumentos (imutável) | ~96 |
| **Kickoff** | Gestão de projeto pós-aprovação | ~61 |
| **PCP** | Planejamento e controle da produção | ~48 |
| **Pedidos** | Ordens de produção (auto-geradas via aprovação P&D) | ~44 |
| **Estoque** | Controle de lotes e movimentações | ~32 |
| **Expedição** | Notas de saída e rastreamento | ~20 |
| **Retrabalho** | Registros e fluxo de reprocesso | ~20 |
| **Recebimento** | Notas fiscais de entrada | ~21 |
| **Faturamento** | NF-e e controle de cobrança | ~16 |
| **Contratos** | Gestão de contratos comerciais | ~18 |
| **Workflow** | Tarefas, notificações, auditoria | ~25 |

---

## Fluxo principal

```
CRM (Cliente / Projeto / Amostra)
    └─> P&D (Formulação → Estabilidade → Ficha Técnica → Aprovação)
            └─> SKU gerado automaticamente
            └─> Pedido (Ordem de Produção) gerado automaticamente
                    └─> PCP → Produção → CQ → Expedição → Faturamento
```

### Status P&D
`PENDING` → `IN_PROGRESS` → `IN_TESTS` → `IN_APPROVAL` → `APPROVED / REJECTED`

### Status Pedido
`rascunho` → `confirmado` → `em_producao` → `concluido` (+ `cancelado`)

---

## Arquitetura

- **Multi-tenant**: todas as coleções indexadas por `tenant_id`
- **Imutável-first**: módulo CQ sem DELETE; fórmulas P&D bloqueadas ao avançar para IN_TESTS
- **RBAC**: roles — `admin`, `formulador`, `vendedor`, `lider_pd`, `engenharia_produto`, `compras`, `qa`, `sales_ops`, `sucesso_cliente`
- **Workflow Engine**: tarefas bloqueantes em transições de status, escalação automática, audit log
- **WebSocket**: suporte a notificações em tempo real
- **PDF**: Ordens de Produção, Fichas Técnicas, Certificados de Análise (ReportLab)

---

## Pré-requisitos

- Python 3.11+
- Node.js 20+ / Yarn 1.22+
- MongoDB 6+ rodando em `localhost:27017`

---

## Instalação

### Backend

```bash
cd backend
pip install -r requirements.txt
```

Variáveis de ambiente (opcional — padrões de desenvolvimento já estão embutidos):

```
MONGO_URL=mongodb://127.0.0.1:27017
DB_NAME=kuryos_crm
JWT_SECRET=dev-only-change-me
```

Iniciar:

```bash
python backend/server.py
# ou
uvicorn backend.server:app --reload --port 8000
```

### Frontend

```bash
cd frontend
yarn install        # ou npm install
```

Criar `.env` (ou renomear `.env.example`):

```
REACT_APP_BACKEND_URL=http://localhost:8000
```

Iniciar:

```bash
yarn start          # porta 3000
```

---

## Credenciais de teste

| Role | E-mail | Senha |
|------|--------|-------|
| Admin | admin@kuryos.com | admin123 |
| Formulador | formulador@kuryos.com | kuryos123 |
| Demais roles | `{role}`@kuryos.com | kuryos123 |

---

## Testes

```bash
# Todos os testes
pytest

# Módulo específico
pytest tests/cq_test.py -v
pytest tests/backend_test.py -v
pytest backend/tests/test_compras.py -v
```

> Os testes usam o banco `kuryos_cq_test` por padrão (configurado em `conftest.py`).

---

## Estrutura de pastas

```
KURYOS/
├── backend/
│   ├── server.py              # Entry point FastAPI + configuração MongoDB/JWT
│   ├── rbac.py                # Role-based access control
│   ├── *_routes.py            # Rotas por módulo (pd, crm, cq, compras, ...)
│   ├── workflow_engine.py     # Engine de tarefas e automações
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.js             # Router (40+ rotas)
│   │   ├── pages/             # 53 páginas (PDDetail, CQDetalheRA, ComprasPODetalhe, ...)
│   │   ├── components/        # Sidebar, RoleGuard, shadcn/ui library
│   │   └── contexts/          # AuthContext
│   ├── tailwind.config.js
│   └── package.json
├── tests/                     # Testes de integração e E2E
├── uploads/                   # Arquivos enviados (PDFs, imagens)
└── conftest.py                # Configuração global do pytest
```

---

## Design System

- **Tema**: dark/light mode com arquétipo Swiss/High-Contrast + Jewel/Luxury
- **Tipografia**: Outfit (headings) · Manrope (body) · JetBrains Mono (números)
- **Paleta**: cores semânticas de temperatura (frio/morno/quente) para status de processo
- **Componentes**: Kanban cards, side-sheet modals, glassmorphism backdrops

---

## Coleções MongoDB (principais)

| Módulo | Coleções |
|--------|---------|
| P&D | `pd_requests`, `pd_formulas`, `pd_formula_items`, `pd_stability_studies`, `pd_stability_readings`, `pd_ficha_tecnica` |
| CRM | `crm_clients`, `crm_projects`, `crm_samples`, `cards`, `stages` |
| CQ | `cq_registros_analise`, `cq_checklists`, `cq_rncs`, `cq_retencoes`, `cq_instrumentos` |
| Compras | `compras_fornecedores`, `compras_itens`, `compras_pos`, `compras_mrp_rodadas` |
| Operacional | `orders`, `estoque_lotes`, `recebimento_notas`, `expedicao_notas`, `faturamento_notas`, `faturamento_duplicatas` |
| Sistema | `users`, `tenants`, `workflow_tasks`, `audit_logs` |

---

## Próximos passos (backlog)

- Documentos vivos: detecção automática de alteração em FT/EPA → nova versão + tarefa de aprovação
- Alertas de estabilidade via cron/scheduler (hoje: acionamento manual)
- Homologação: bloqueio de liberação para Compras sem fornecedor homologado
- Responsividade mobile/tablet
- PDF da Ficha Técnica com assinatura digital
