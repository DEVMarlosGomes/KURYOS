# KURYOS ERP — Relatório de Gap (Especificação vs. Repositório Atual)

**Data:** 2026-05-08
**Repositório auditado:** `C:\Users\MARLOS\Downloads\KURYOS` (branch local)
**Autor da auditoria:** Cowork (Claude)

---

## TL;DR

A especificação `ERP_Kuryos_Especificacao_v3` lista 8 módulos como "ausentes". Após auditoria do código, **6 dos 8 módulos já estão totalmente ou substancialmente implementados**. Os gaps reais são pontuais e bem menores do que a spec sugere. Recomendamos **não reimplementar** o que já existe e focar apenas nos gaps confirmados abaixo.

---

## Status real por módulo

| # | Módulo da spec | Status real | Onde está | Ação recomendada |
|---|---|---|---|---|
| 1 | Kickoff (Blocos 1–5 + BOM + aprovação) | ✅ Completo | `backend/kickoff_routes.py` (61 KB, 10 endpoints, todos os modelos Pydantic, validações RN-KO-01..10, BOM auto, aprovação sequencial, versionamento) | Nenhuma — apenas testes E2E |
| 5.1 | CRM "pedido_aprovado" → criar Kickoff | ✅ Completo | `crm_routes.py:1537–1624` chama `create_kickoff_for_project`, valida fórmula registrada, cria tarefa Bloco 2, retorna `kickoff_criado` | Nenhuma |
| 5.3 | Homologações (Fornecedores + MPs) | ✅ Completo | `pd_routes.py:4282–4653` (16 endpoints CRUD + dashboard), índices Mongo em `homologacao_fornecedores` e `homologacao_mps` | Nenhuma |
| 7 | Tarefas Pendentes expandidas | ✅ Completo | `workflow_engine.py` + `workflow_routes.py` (9 endpoints `/tasks`); todos os `task_code` da spec presentes em `kickoff_routes.py` (preencher_kickoff_bloco2/3/4, aprovar_kickoff_*, gerar_epa, homologar_fornecedor_mp) | Nenhuma |
| 2 | Ficha Técnica (FT) como documento vivo | ✅ Completo | `pd_routes.py:_generate_live_document_version` (`doc_type="ficha_tecnica"`), endpoints `/pd/requests/{id}/live-documents/ficha_tecnica/...`, UI em `frontend/pages/PDDetail.js:2906+` (tab Live Documents) | Opcional: rota dedicada `/fichas-tecnicas/:id` |
| 3 | EPA como documento vivo | ✅ Completo | Mesma infra do FT (`doc_type="epa"`), gerado automaticamente após Kickoff aprovado em `_mark_pd_request_kickoff_complete` | Opcional: rota dedicada `/epas/:id` |
| 4 | Compras vinculadas ao BOM do Kickoff | ⚠️ **Parcial** | `orders_routes.py` existe (6 endpoints CRUD básicos) mas **não tem FK obrigatória para `kickoff_id` nem para `bom_item_id`** | **GAP REAL** |
| 6 | Geração automática do CGI em PDF | ❌ **Ausente** | Não há gerador. Apenas referências textuais em `kickoff_routes.py` e `workflow_engine.py` | **GAP REAL** |
| 8 | Perfis e permissões expandidos | ✅ Completo | `rbac.py:16–34` define os 6 perfis (sales_ops, formulador, qualidade_cq via `qa`, lider_pd, engenharia_produto, sucesso_cliente) | Nenhuma |

### Frontend

| Página da spec | Existe? | Arquivo |
|---|---|---|
| F1 KickoffPage | ✅ | `pages/KickoffPage.js` |
| F2 FichaTecnicaPage | ⚠️ embarcada em `PDDetail.js` (tab Live Documents) | sem rota dedicada |
| F3 EPAPage | ⚠️ embarcada em `PDDetail.js` (tab Live Documents, toggle FT/EPA) | sem rota dedicada |
| F4 KickoffsListPage | ✅ | `pages/KickoffsListPage.js` |
| F5 HomologacoesPage | ✅ | `pages/PDHomologacao.js` |
| F6 Badge Kickoff em CRM2 + toast | ✅ | `pages/CRM2Page.js:100–104, 275–279` |

---

## Gaps reais a implementar

### Gap A — Módulo 4: Compras vinculadas ao BOM do Kickoff
**Arquivo afetado:** `backend/orders_routes.py`
**O que falta:**
- Adicionar `kickoff_id` (FK obrigatória) e `bom_item_id` ao modelo `OrdemCompra`
- Validar no `POST /api/compras/ordens` que o Kickoff existe e está em status `aprovado`
- Validar que o `bom_item_id` pertence ao BOM consolidado do Kickoff
- Endpoint `GET /api/compras/boms` listando BOMs aprovados disponíveis
- Auto-gerar `numero_oc` no formato `OC-2026-0001`
- Calcular `data_necessidade` a partir de `data_entrega_contratada - lead_time_producao_dias_uteis` do Kickoff

### Gap B — Módulo 6: Gerador de Contrato (CGI) em PDF
**Arquivo a criar:** `backend/contratos_routes.py` (novo)
**O que falta:**
- `POST /api/contratos/gerar` — recebe `kickoff_id`, lê dados do Kickoff + cliente, preenche template CGI, retorna PDF
- Template CGI com cláusulas 1–29 baseado no documento `CGI_Contrato_Geral_de_Industrializacao_Kuryos.docx`
- Dados fixos da KURYOS BEAUTY PACKING INDUSTRIAL LTDA (CNPJ 00.767.554/0001-19)
- `GET /api/contratos/{id}` e `GET /api/contratos` para listar/recuperar
- Persistir referência do PDF na coleção `contratos` com FK ao Kickoff
- Frontend: botão "Gerar Contrato" na `KickoffPage.js` quando status = aprovado

---

## Recomendação de ordem de execução

1. **Gap A primeiro** (Compras ↔ BOM): pequeno (≈ 200 linhas), desbloqueia ciclo operacional pós-Kickoff
2. **Gap B depois** (CGI PDF generator): médio (≈ 400 linhas + template), valor alto para Comercial e Direção
3. (Opcional) Rotas dedicadas `/fichas-tecnicas/:id` e `/epas/:id` no frontend para facilitar deep-link e impressão

Os módulos de Prioridade BAIXA da spec (PCP, Produção, Logística, Financeiro, Sucesso do Cliente) permanecem fora do escopo atual conforme a própria spec.
