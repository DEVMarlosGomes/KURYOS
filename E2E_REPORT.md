# Relatório de Execução End-to-End — Kuryos CRM

**Data:** 08/05/2026
**Executor:** Admin Kuryos (admin@kuryos.com)
**Objetivo:** Criar cliente, qualificá-lo e percorrer o fluxo até a aprovação de uma amostra com geração automática de SKU.

---

## ✅ Resumo Executivo

| Item | Status | Resultado |
|---|---|---|
| Cliente criado em Prospecção | ✅ | `Bella Cosmética Premium Ltda` (id: `60f9d0b1...`) |
| Qualificação completa | ✅ | Decisores, ANVISA, volume, fornecedor preenchidos |
| Movido para Projeto em Discussão | ✅ | Tarefa bloqueante validada e concluída |
| Projeto criado em batch | ✅ | `Linha Bella Hair Repair Premium 2026` |
| Projeto movido para Amostra Solicitada | ✅ | trigger_batch_samples = true |
| Amostra criada com 2 variações | ✅ | #101/A e #101/B (cards P&D auto-criados) |
| Variação 101/A — workflow completo | ✅ | solicitada → em_elaboracao → enviada → aprovada |
| **SKU gerado automaticamente** | 🎉 | **`KRY-001`** | Shampoo Bella Repair Premium - 101/A | R$ 95,50 | ATIVO |
| Projeto auto-avançado | ✅ | "amostra_solicitada" → "em_negociacao" (orquestração automática) |
| Auditoria registrada | ✅ | 20+ entries no audit log |

---

## 1. Ambiente

- **Backend:** FastAPI rodando em `:8001` (supervisor)
- **Frontend:** React rodando em `:3000` (supervisor)
- **MongoDB:** rodando em `127.0.0.1:27017` (db: `kuryos_crm`)
- **URL pública:** `https://approval-pipeline-9.preview.emergentagent.com`
- **Auth:** JWT em cookie HttpOnly (`access_token`)
- **Login usado:** `admin@kuryos.com / admin123` (perfil `admin`)

---

## 2. Fluxo End-to-End executado via API

### 2.1 Login

```http
POST /api/auth/login
{ "email": "admin@kuryos.com", "password": "admin123" }
```

Response:
```json
{ "id": "823fff1b-...", "email": "admin@kuryos.com", "role": "admin",
  "tenant_id": "209480ab-..." }
```
Set-Cookie: `access_token=eyJ...` (HttpOnly).

---

### 2.2 Criação do Cliente (CRM1 — Pipeline Comercial)

```http
POST /api/crm/clients
```
Payload usado (campos relevantes):
- `nome_empresa`: Bella Cosmética Premium Ltda
- `cnpj`: 11.222.333/0001-81 (validador interno aceitou)
- `contato_principal`: Maria Silva Oliveira / maria.silva@bellacosmetica.com.br / +55 11 98765-4321
- `canal_origem`: linkedin_dm_outbound
- `categoria_interesse`: shampoo, condicionador, mascara_capilar
- `temperatura_lead`: quente
- `segmento`: marca_propria
- `porte`: medio
- `regiao`: SP

> **Validações que falharam até acertar (aprendizado):**
> - CNPJ inválido (api valida o algoritmo) ➝ corrigido
> - "Segmento inválido" ➝ usar enum válido (`marca_propria`, `distribuidor`, etc.)

**Resultado:** Cliente criado em `stage = prospeccao`, id `60f9d0b1-43b5-4d54-83c4-d855bc18214f`.

---

### 2.3 Atualização de dados de qualificação

```http
PUT /api/crm/clients/{id}
```
Campos preenchidos:
- `decisores`: 2 (decisor_final + influenciador)
- `tem_marca_propria`: true
- `tem_anvisa`: sim
- `volume_estimado_mensal`: 5000-10000
- `fornecedor_atual`: { tem: true, motivo_troca: "Buscando melhor qualidade e claims naturais" }
- `prazo_urgencia`: 60_dias

---

### 2.4 Move: prospeccao → qualificado

```http
PUT /api/crm/clients/{id}/move
{ "stage": "qualificado" }
```
✅ Stage alterado com sucesso.
🆕 **Tarefa automática gerada:**
- `TRF-2026-00002` — *Qualificar lead — preencher decisores, ANVISA, volume e fornecedor atual*
- `blocking: true` | `blocks_stages: ["projeto_em_discussao"]`
- Atribuída automaticamente ao usuário `Vendedor SDR` (responsável comercial do cliente).

---

### 2.5 Tentativa de avanço bloqueada (validação RBAC/workflow)

```http
PUT /api/crm/clients/{id}/move
{ "stage": "projeto_em_discussao", "trigger_batch_projects": true }
```
🛑 Resposta: `400 — Avanço bloqueado por 1 tarefa(s) obrigatória(s): Qualificar lead...`

> O motor de workflow está funcional: tarefas marcadas como `blocking=true` impedem transição.

---

### 2.6 Conclusão das tarefas pendentes

```http
PUT /api/workflow/tasks/{task_id}/complete
{ "comment": "Qualificação completa: decisores, ANVISA, volume, fornecedor preenchidos" }
```
- `TRF-2026-00001` (primeiro contato) → concluida
- `TRF-2026-00002` (qualificar lead — bloqueante) → concluida ✅

---

### 2.7 Move: qualificado → projeto_em_discussao + trigger batch projects

```http
PUT /api/crm/clients/{id}/move
{ "stage": "projeto_em_discussao", "trigger_batch_projects": true }
```
✅ Stage avançado.
🆕 Tarefa nova: `TRF-2026-00003 — Cadastrar projetos do cliente (briefing técnico)` (blocking).

---

### 2.8 Criação de projeto em batch (CRM2)

```http
POST /api/crm/projects/batch
{
  "cliente_id": "{client_id}",
  "projects": [
    { "nome_projeto": "Linha Bella Hair Repair Premium 2026",
      "categoria": "shampoo",
      "briefing_resumido": "Linha capilar premium...",
      "faixa_preco_venda": 89.90,
      "volume_estimado_pedido": 5000,
      "tipo_servico": "private_label",
      "restricoes_tecnicas": ["sem_sulfato","sem_paraben","vegano"],
      ...
    }
  ]
}
```
✅ Projeto criado em `stage = projeto_em_discussao` (id `0dff86d9...`).

> Herança automática de dados do cliente (categoria_interesse, canal_origem, ANVISA, volume).

---

### 2.9 Move: projeto → amostra_solicitada (CRM2)

```http
PUT /api/crm/projects/{id}/move
{ "stage": "amostra_solicitada" }
```
✅ Stage alterado.
🆕 Tarefa: `TRF-2026-00005 — Iniciar lote de amostras do projeto`.
📦 `trigger_batch_samples = true` → cliente pode iniciar lote.

---

### 2.10 Criação de amostras com variações (batch v2)

```http
POST /api/crm/samples/batch/v2
{
  "projeto_id": "{project_id}",
  "samples": [{
    "nome_produto": "Shampoo Bella Repair Premium",
    "categoria": "shampoo",
    "briefing_base": "Shampoo de reparação intensa...",
    "responsavel_pd": "Formulador P&D",
    "tipo_amostra": "bench_top",
    "quantidade_por_variacao": 200, "unidade_quantidade": "g",
    "ph": "5.0-6.0",
    "ativos_claims": "Argan, Aminoácidos, Proteína de Soja, Vegano",
    "variacoes": [
      { "descricao_aplicacao": "Variação A — Fragrância Floral Frutal",
        "percentual_fragrancia": 0.8, "referencia_fragrancia": "FRAG-RED-FLORAL-001",
        "custo_fragrancia": 95.50 },
      { "descricao_aplicacao": "Variação B — Fragrância Gourmand Baunilha",
        "percentual_fragrancia": 1.2, "referencia_fragrancia": "FRAG-VANILLA-GOURMAND-002",
        "custo_fragrancia": 120.00 }
    ]
  }]
}
```

✅ Amostra `#101` criada com 2 variações:
- **101/A** — id `b43bfd3a...` | status `solicitada` | pd_card auto-criado
- **101/B** — id `72ee8419...` | status `solicitada` | pd_card auto-criado

---

### 2.11 Workflow da Variação 101/A (caminho até aprovação)

| Passo | Endpoint | Status alcançado |
|---|---|---|
| 1 | `PUT .../variacoes/{var_a}/move {"status":"em_elaboracao"}` | ✅ em_elaboracao |
| 2 | `PUT .../variacoes/{var_a}/move {"status":"enviada"}` | ✅ enviada |
| 3 | Tentativa de aprovar | 🛑 Bloqueado por `TRF-2026-00007 — Registrar feedback do cliente apos envio` (blocking) |
| 4 | `PUT /api/crm/samples/{id}/variacoes/{var_a} { "feedback_cliente":"... APROVOU ..." }` | ✅ feedback registrado |
| 5 | `PUT .../tasks/{task}/complete` | ✅ task concluida |
| 6 | `PUT .../variacoes/{var_a}/move {"status":"aprovada"}` | 🎉 **APROVADA + SKU gerado** |

---

### 2.12 🎉 SKU gerado automaticamente

Resposta da última transição (campo `sku_created`):

```json
{
  "id": "e541ee14-b61f-40ea-a942-a603a9f53e16",
  "codigo_interno": "KRY-001",
  "nome_produto": "Shampoo Bella Repair Premium - 101/A",
  "categoria": "shampoo",
  "cliente_id": "60f9d0b1-43b5-4d54-83c4-d855bc18214f",
  "cliente_nome": "Bella Cosmética Premium Ltda",
  "projeto_id": "0dff86d9-e2f2-4951-8a8e-d85dc13e82f2",
  "amostra_id": "e6d83c4b-5687-4f36-ac5f-6a4e5aea07cc",
  "amostra_variacao_id": "b43bfd3a-55c5-490d-b18c-ad9ca0cfd2cb",
  "descricao_aplicacao": "Variação A — Fragrância Floral Frutal (frutos vermelhos + jasmim)",
  "preco_unitario": 95.5,
  "moq": 0,
  "anvisa": { "numero": "", "validade": null },
  "status": "ativo",
  "historico_pedidos": [],
  "frequencia_media_recompra_dias": 0
}
```

---

## 3. Auto-orquestração observada

Após a aprovação da variação 101/A, o sistema disparou automaticamente:
- **Projeto:** `amostra_solicitada` → `em_negociacao` (registrado em audit como `project_auto_moved`)
- **PD Card** vinculado: `pd_card_moved` para status concluído
- **Tarefas de pós-envio**: D+3, D+7, D+14 follow-ups gerados (não bloqueantes)

20 entries em `/api/workflow/audit-logs` confirmam todas as transições com `user_id`, `timestamp` e `action`.

---

## 4. Validação 360º — endpoint `/api/crm/clients/{id}/full`

```text
━━━ CLIENTE ━━━
  Nome: Bella Cosmética Premium Ltda
  CNPJ: 11.222.333/0001-81
  Stage atual: projeto_em_discussao
  Histórico:
    prospeccao → qualificado (Admin Kuryos)
    qualificado → projeto_em_discussao (Admin Kuryos)

━━━ PROJETOS ━━━
  - Linha Bella Hair Repair Premium 2026 | stage=em_negociacao

━━━ AMOSTRAS ━━━
  Amostra #101: Shampoo Bella Repair Premium
    └─ 101/A | status=aprovada | gera_sku=True | sku_id=e541ee14-...
    └─ 101/B | status=solicitada | gera_sku=False

━━━ SKUs ━━━
  KRY-001 | Shampoo Bella Repair Premium - 101/A | preço=R$ 95,50 | status=ativo
```

---

## 5. Validação UI (Playwright)

Capturadas screenshots em todos os pontos críticos confirmando que a UI reflete corretamente os dados criados via API:

1. **Login Page** — CRM Kuryos com 8 perfis demo visíveis.
2. **CRM1 — Pipeline Comercial** — `Bella Cosmética Premium Ltda` na coluna "Projeto em Discussão" com badges QUENTE / outbound / Shampoo / Condicionador.
3. **CRM2 — Pipeline de Projetos** — `Linha Bella Hair Repair Premium 2026` na coluna "Em Negociação" (indica que o auto-avanço pós-aprovação aconteceu).
4. **CRM3 — Pipeline de Amostras** — `101/B` em "Solicitada" + `101/A` em "Aprovada".
5. **SKUs / Catálogo** — 1 linha: `KRY-001 | Shampoo Bella Repair Premium - 101/A | Bella Cosmética Premium Ltda | shampoo | ATIVO | R$ 95,50 | 0 pedidos`.
6. **Pipeline P&D** — 101/A e 101/B no kanban do P&D (origem CRM, vinculadas via `pd_card_id`).
7. **Detalhe Cliente** — abas Dados/Histórico mostrando todos os campos preenchidos.
8. **Detalhe Amostra** — aba Briefing com todas as informações herdadas (produto, objetivo, claims, referências, pH, sensorial).
9. **Tarefas (TasksPage)** — fila de 6 tarefas pendentes incluindo a bloqueante `Cadastrar projetos do cliente`.

---

## 6. Tarefas geradas durante o fluxo (workflow engine)

| Código | Título | Entidade | Bloqueante | Origem |
|---|---|---|---|---|
| TRF-2026-00001 | Realizar primeiro contato comercial | client | não | criação cliente |
| TRF-2026-00002 | Qualificar lead — preencher decisores, ANVISA, volume e fornecedor atual | client | **sim** | move qualificado |
| TRF-2026-00003 | Cadastrar projetos do cliente (briefing técnico) | client | **sim** | move projeto_em_discussao |
| TRF-2026-00004 | Validar viabilidade tecnica do pre-briefing | project | não | criação projeto |
| TRF-2026-00005 | Iniciar lote de amostras do projeto | project | não | move amostra_solicitada |
| TRF-2026-00007 | Registrar feedback do cliente apos envio | variacao | **sim** | move enviada |
| TRF-2026-00008/9/10 | Follow-up D+3/D+7/D+14 da amostra enviada | variacao | não | move enviada |

**Total:** 10 tarefas geradas automaticamente, com responsáveis atribuídos por papel (RBAC) e prazos calculados.

---

## 7. Conclusão

O ciclo completo **Cliente → Projeto → Amostra → Variação Aprovada → SKU** funcionou de ponta a ponta tanto pela API quanto refletido na UI. Validações de RBAC, tarefas bloqueantes, herança de dados, auto-orquestração de stages e geração automática do SKU `KRY-001` foram todos exercitados com sucesso.

**Comportamentos confirmados:**
- ✅ Validação rigorosa de CNPJ
- ✅ Enums de segmento/porte/UF aplicados
- ✅ Workflow Engine bloqueia avanço com tarefas pendentes (`blocking=true`)
- ✅ Geração automática de tarefas em transições de stage com responsável por RBAC
- ✅ Auto-criação de cards no Pipeline P&D para cada variação
- ✅ Auto-geração de SKU sequencial (`KRY-001`) ao aprovar variação
- ✅ Auto-avanço do projeto para `em_negociacao` após aprovação de amostra
- ✅ Auditoria completa em `audit-logs`

**Próximos passos sugeridos (não realizados, pois fora do escopo "até aprovar"):**
- Aprovar 101/B para gerar `KRY-002`
- Criar pedido (`POST /api/orders`) para o SKU `KRY-001`
- Mover cliente até `cliente_fechado` registrando `data_pedido`, `valor_primeiro_pedido`
- Adicionar histórico de pedidos para alimentar `frequencia_media_recompra_dias`
