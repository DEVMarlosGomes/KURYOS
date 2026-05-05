# CRM Kuryos - Product Requirements Document

## Architecture
- **Frontend**: React + TailwindCSS + Shadcn UI + @hello-pangea/dnd
- **Backend**: FastAPI (Python)
- **Database**: MongoDB
- **Auth**: JWT httpOnly cookies + RBAC (admin/gestor/vendedor)
- **AI**: Claude Sonnet 4.5 via Emergent LLM Key
- **Storage**: Emergent Object Storage
- **Real-time**: WebSocket (FastAPI native)

## Implemented Features

### Phase 1 - MVP (Kanban Core)
- JWT auth with multi-tenancy, RBAC
- Pipeline Kanban with 6 stages, drag-and-drop
- Card side-sheet with dynamic fields, products, timeline, WhatsApp chat
- Temperature badges, Task management, Dashboard metrics, Dark mode

### Phase 2 - AI + Documents + Real-time
- Claude Sonnet 4.5: Lead summary + WhatsApp suggestions
- PDF proposal generation (ReportLab)
- Excel report export (openpyxl)
- WebSocket real-time updates

### Phase 3 - User Management + Automations + Storage
- User invite with RBAC (admin-only)
- Role management (admin/gestor/vendedor)
- Funnel automations: Negociando Proposta -> auto-notification
- Hot lead automation: quente status -> notification + email
- File upload to Object Storage for form fields
- Notification system with bell icon and dropdown
- WhatsApp templates (5 pre-built templates)
- Mock email logging

## Remaining Backlog
### P1
- [ ] Real WhatsApp integration (Z-API/Evolution)
- [ ] Real email sending via Resend
- [ ] Pipeline customization (add/remove stages/fields)
- [ ] Card search and filters
- [ ] Mobile responsive optimization

### Phase 4 - P&D Module
- PD Request creation with CRM client autocomplete
- Kanban workflow: OPEN -> IN_PROGRESS -> IN_TESTS -> WAITING_APPROVAL -> APPROVED -> COMPLETED (+ REJECTED)
- Controlled status transitions with business rules
- Auto-creation of Development entity on IN_PROGRESS
- Formula management with auto-versioning and ingredient items
- Lab tests (Estabilidade, pH, Viscosidade, Sensorial, Compatibilidade)
- Samples tracking
- Approval system (client + internal)
- Cost calculation (ingredients, packaging, labor)
- Document/report management with file upload
- Full detail view with tabs for overview, formula, tests, samples, costs and documents
- Status timeline history
- PD Metrics dashboard endpoint

### Phase 4.1 - P&D Expansion
- Pipeline P&D as the active operational queue for development demand
- Banco de Formulas as a global versioned repository with origin, approvals and composition visibility
- Homologacoes for suppliers and MPs with approval workflow and purchasing-readiness checks
- Estabilidades as sample-based studies with monitored conditions, scheduled readings and audit history
- SKUs / Catalogo for finished products ready for production visibility
- Estoque Lab for controlled movement of laboratory raw materials and finished samples
- Relatorios with KPIs for queue, lead time, approval rate and homologation coverage

## 9. Integracoes Automaticas entre Modulos
Esta secao mapeia todos os gatilhos automaticos entre CRM, P&D e Documentos Internos. Cada gatilho elimina uma dependencia humana, convertendo-a em tarefa rastreavel ou em acao automatica do sistema.

| Evento Gatilho | Origem | Acao Automatica / Tarefa Gerada | Destino |
| --- | --- | --- | --- |
| Amostra criada no CRM | CRM Amostras | Criar card(s) P&D. Variacoes geram subcards. Tarefa: Lider P&D atribuir formulador. | P&D Pipeline |
| Card P&D aceito pelo formulador | P&D | Atualizar status da Amostra no CRM. Notificar comercial. | CRM Amostras |
| Card P&D entra em `Em Testes` | P&D | Abrir estudo de estabilidade automaticamente. | P&D Estabilidades |
| Card P&D entra em `Aguardando Aprovacao` | P&D | Tarefa criada para CQ: revisar e aprovar ou reprovar. | CQ - Tarefas |
| CQ aprova internamente | P&D | Notificar comercial. Tarefa: confirmar envio fisico. | CRM Notificacao |
| Comercial confirma envio fisico | CRM Amostras | Amostra avanca para `Enviada`. Tarefas de follow-up D+3/D+7/D+14 criadas. | CRM Follow-up |
| Amostra marcada como `Retrabalho` | CRM Amostras | Nova amostra criada (proximo numero). Novo card P&D com feedback pre-populado. | P&D Pipeline |
| Amostra marcada como `Aprovada` pelo cliente | CRM Amostras | Projeto avanca para `Em Negociacao`. Tarefa P&D: registrar formula. Tarefa P&D: gerar Ficha Tecnica. | CRM + P&D |
| Formula registrada no banco P&D | P&D Banco | Encerrar card P&D. Notificar CRM. Ficha Tecnica v1 gerada automaticamente (estrutura). Tarefa: Lider P&D aprovar FT. | CRM + FT |
| Kickoff / Contrato concluido | Eng. Produto | EPA v1 gerado automaticamente (estrutura). Tarefa: CQ + Eng. Produto + P&D aprovar EPA. | EPA - Tarefas |
| Dado de origem da FT alterado | P&D / Homologacoes | Nova versao da FT criada. Status: `Em revisao`. Tarefa: Lider P&D aprovar nova versao. | FT - Tarefas |
| Dado de origem do EPA alterado | Multiplos modulos | Nova versao do EPA criada. Status: `Em revisao`. Tarefa: CQ + responsaveis aprovarem nova versao. | EPA - Tarefas |
| Projeto avanca para `Pedido Aprovado` | CRM Projetos | Verificar homologacoes. Se OK: criar Pedido. Se nao: tarefa de homologacao pendente. | Operacional (futuro) |
| Data de leitura de estabilidade (D-2) | P&D Estabilidades | Tarefa de leitura criada para formulador e Lider P&D. | P&D - Tarefas |
| Leitura de estabilidade vence sem registro | P&D Estabilidades | Tarefa escalada para Lider P&D. Status `Em atraso` no dashboard. | P&D - Dashboard |

**Regra critica:** nenhum gatilho pode ser substituido por comunicacao manual. O sistema e a unica fonte de verdade das transicoes e das tarefas. Acoes realizadas fora do sistema nao sao reconhecidas.

## 10. Perfis de Usuario e Permissoes
| Perfil | Area | Acesso Principal | Restricoes |
| --- | --- | --- | --- |
| Vendedor / SDR | Comercial | Pipeline Clientes, Projetos e Amostras (leitura e escrita). Criacao de clientes e projetos. Suas tarefas pendentes. | Sem acesso ao modulo P&D. Ve apenas status de amostras e tarefas proprias. |
| Sales Ops | Comercial | Acesso total ao CRM. Relatorios, KPIs, configuracao de pipeline, validacao de viabilidade. Tarefas da area comercial. | Sem acesso a formulas e banco P&D. |
| Formulador P&D | P&D | Pipeline P&D, Banco de Formulas, Estoque Lab, Estabilidades. Geracao de Ficha Tecnica. Suas tarefas. | Dados de cliente/projeto em leitura. Sem acesso ao CRM comercial. |
| Qualidade (CQ) | P&D / CQ | Aprovacoes no Pipeline P&D. Homologacoes. Leitura de estabilidades. Aprovacao de FT e EPA. Suas tarefas. | Nao cria nem edita formulas, apenas aprova/reprova. |
| Lider P&D / Lab | P&D | Acesso total ao modulo P&D. Atribuicao de cards. Dashboard de fila e tarefas da equipe P&D. Abertura de cards internos. | Sem acesso ao CRM Comercial. |
| Engenharia de Produto | Operacional | Kickoff / Contrato. BOM e embalagem. Aprovacao de EPA. Suas tarefas. | Sem acesso ao banco de formulas completo. |
| Sucesso do Cliente | Pos-venda | Clientes fechados, historico de projetos e producao. Recompra, cross-sell. Suas tarefas. | Sem acesso a clientes em prospeccao. |
| Administrador | Todos | Acesso total a todos os modulos, configuracoes, logs e dashboard global de tarefas. | Restrito a Gustavo + responsaveis de area designados. |

- `RN-US-01`: toda acao no sistema e logada com usuario, data e hora. Log imutavel, nao pode ser apagado por nenhum perfil.
- `RN-US-02`: a troca de etapa em qualquer pipeline registra quem moveu, de qual etapa, para qual etapa, data e hora.
- `RN-US-03`: notificacoes sao enviadas ao responsavel pela proxima acao, nunca de forma generica para todos.

## 11. Glossario e Nomenclatura Oficial do Sistema
O sistema deve usar exatamente estes termos em toda a interface, documentacao e comunicacao interna. Consistencia de nomenclatura e regra de negocio.

| Termo | Definicao no contexto Kuryos |
| --- | --- |
| Cliente | Empresa contratante ou potencial contratante de industrializacao. Entidade permanente no sistema. |
| Projeto | Oportunidade especifica de produto dentro de um cliente. Ex: `Habibi / Body Splash 300ml`. |
| Amostra | Rodada fisica de desenvolvimento de um produto dentro de um projeto. Numerada globalmente (`#101`, `#102`). Variacoes com sufixo (`#101/A`, `#101/B`). |
| Variacao de Amostra | Versao de uma amostra que difere em apenas um parametro (fragrancia, cor, ativo). Identificada por sufixo alfabetico. |
| Pre-Briefing | Documento preenchido pelo comercial na criacao do projeto. Captura ideia inicial, referencias, posicionamento e restricoes. |
| Kickoff / Contrato de Industrializacao | Documento completo preenchido apos aprovacao de amostra pelo cliente. Inclui embalagem detalhada, BOM, SKUs, prazos e volumes. |
| Ficha Tecnica | Documento vivo de referencia para Manipulacao. Contem formula completa, modo de preparo passo a passo e parametros de controle in-process. Gerada apos aprovacao do cliente. |
| EPA | Especificacao de Produto Acabado. Documento vivo de referencia para a linha de producao e CQ. Contem BOM completo, especificacoes do produto, etapas de producao e criterios de liberacao de lote. Gerado apos Kickoff. |
| Formula | Conjunto de ingredientes, concentracoes e modo de preparo. Versionada e imutavel apos registro. |
| Estabilidade | Estudo que monitora integridade fisico-quimica e microbiologica do produto ao longo do tempo sob diferentes condicoes de armazenamento. |
| BOM | Bill of Materials, lista completa de todos os componentes do produto acabado com fornecedor, codigo e quantidade por unidade. |
| Tarefa Pendente | Unidade de trabalho rastreavel atribuida a um responsavel com prazo, status e historico. Toda dependencia humana vira uma tarefa. |
| Documento Vivo | Documento cujo conteudo e gerado dinamicamente a partir de dados dos modulos do sistema. Atualizado automaticamente quando dado de origem muda. Ex: Ficha Tecnica, EPA. |
| Homologacao | Processo formal de aprovacao de fornecedor ou MP pelo P&D e CQ. Obrigatoria antes de liberar projeto para Compras. |
| Full Service | Modalidade em que a Kuryos e responsavel pelo desenvolvimento completo do produto. |
| Co-desenvolvimento | Modalidade em que cliente e Kuryos desenvolvem juntos, com cliente trazendo referencia ou componentes. |
| Retrabalho | Nova rodada de desenvolvimento apos reprovacao parcial. Gera nova numeracao sequencial de amostra. |
| Grau 2 (ANVISA) | Classificacao de produtos com risco elevado (ex: protetor solar FPS >= 6, repelente). Exige registro ANVISA e prazo diferenciado. |

### 11.1 Sequencia de Documentos e Marcos - Imutavel
| # | Documento / Marco | Momento, Responsavel e Tarefa Gerada |
| --- | --- | --- |
| 1 | Pre-Briefing | Reuniao comercial -> criacao do Projeto. Preenchido pelo Comercial. Tarefa: validacao de viabilidade pelo P&D. |
| 2 | Amostra(s) - D0 | Solicitacao formal -> card P&D criado. Tarefa: Lider P&D atribuir formulador. Estabilidade aberta automaticamente em `Em Testes`. |
| 3 | Aprovacao interna (CQ) | Tarefa criada para CQ revisar. CQ aprova -> tarefa para comercial confirmar envio fisico. |
| 4 | Envio ao cliente | Comercial confirma envio. Tarefas de follow-up D+3/D+7/D+14 criadas automaticamente. |
| 5 | Feedback do cliente | Aprovada -> passos 6 e 7. Retrabalho -> retorna ao passo 2 com nova numeracao. Reprovada -> arquivado. |
| 6 | Ficha Tecnica v1 | Pos-aprovacao do cliente. Tarefa: formulador gerar FT. Tarefa: Lider P&D aprovar FT. |
| 7 | Kickoff / Contrato | Engenharia de Produto preenche BOM e embalagem. Tarefa: P&D + CQ + Eng. Produto gerar e aprovar EPA. |
| 8 | EPA v1 | Pos-Kickoff. Tarefas de aprovacao por CQ, Eng. Produto e Lider P&D. |
| 9 | Homologacao de fornecedores/MPs | Obrigatoria para todos os insumos antes de liberar para Compras. Tarefa gerada se pendente. |
| 10 | Pedido / PCP | Pedido formalizado -> PCP programa producao -> Compras acionadas. |

## 12. Pontos Criticos de Desenvolvimento - Checklist
Pre-requisitos de entrega. Nenhuma funcionalidade esta pronta se esses pontos nao estiverem implementados e testados.

### 12.1 Estrutura de Dados
- [ ] Hierarquia Cliente -> Projeto -> Amostra -> Card P&D com FK no banco
- [ ] Entidade filha nao pode existir sem entidade pai (bloqueio no sistema)
- [ ] Heranca automatica de campos entre entidades
- [ ] Numeracao global sequencial de amostras (nunca reutilizada)
- [ ] Sistema de variacoes por sufixo alfabetico (`#101/A`, `#101/B`)
- [ ] Resultados independentes por variacao
- [ ] Versionamento de formulas com imutabilidade apos registro
- [ ] Documentos vivos (FT e EPA) como views dinamicas de dados distribuidos
- [ ] Versionamento de FT e EPA com historico de alteracoes
- [ ] Log de auditoria imutavel em todas as entidades

### 12.2 Sistema de Tarefas Pendentes
- [ ] Estrutura completa de tarefa com todos os campos definidos na Secao 8.1
- [ ] Criacao automatica de tarefa para cada evento gatilho mapeado na Secao 8.2
- [ ] Dashboard de tarefas por perfil: Minhas Tarefas / Em Atraso / Esta Semana
- [ ] Visao de equipe para lideres de area
- [ ] Visao global para Administrador
- [ ] Tarefas de aprovacao com opcao explicita: `Aprovado` / `Reprovado com justificativa`
- [ ] Bloqueio de avanco de etapa quando tarefa pre-requisito nao esta concluida
- [ ] Notificacoes: ao criar, D-1 do prazo, ao entrar em atraso, ao concluir
- [ ] Repasse de tarefa com historico de atribuicoes
- [ ] KPIs de tarefas nos relatorios por area

### 12.3 Documentos Internos (FT e EPA)
- [ ] Geracao automatica da estrutura da FT apos registro da formula
- [ ] Geracao automatica da estrutura do EPA apos conclusao do Kickoff
- [ ] FT e EPA bloqueados para geracao antes do momento correto
- [ ] Deteccao automatica de alteracao em dado de origem -> nova versao + tarefa de aprovacao
- [ ] Status `Em revisao` para versoes aguardando aprovacao
- [ ] Versao vigente visivel apenas para linha de producao, versoes em revisao restritas
- [ ] Exportacao de FT e EPA em formato padronizado (PDF)
- [ ] Historico de versoes com numero, data, o que mudou, quem alterou, quem aprovou

### 12.4 Pipelines e Transicoes
- [ ] Modal de criacao em lote de Projetos ao avancar cliente
- [ ] Modal de criacao em lote de Amostras com suporte a variacoes
- [ ] Validacao de campos obrigatorios antes de qualquer transicao
- [ ] Registro de data/hora/usuario em cada transicao
- [ ] Campo obrigatorio de motivo ao mover para etapas de perda/arquivo
- [ ] Alerta de reativacao para clientes perdidos e projetos arquivados

### 12.5 Automacoes e Gatilhos
- [ ] Criacao automatica de card(s) P&D ao criar Amostra no CRM
- [ ] Subcards por variacao vinculados ao card pai
- [ ] Abertura automatica de estudo de estabilidade ao entrar em `Em Testes`
- [ ] Todos os gatilhos da Secao 9 implementados
- [ ] Bloqueio de pedido quando MP sem fornecedor homologado
- [ ] Alertas de risco de fornecimento (menos de 3 fornecedores por MP)

### 12.6 Modulo de Estabilidades
- [ ] Criacao e gestao de estudos por amostra e por variacao
- [ ] 9 condicoes de armazenamento mapeadas
- [ ] D0 obrigatorio antes do inicio formal
- [ ] Registro de leitura com todos os parametros definidos
- [ ] Upload de foto por leitura
- [ ] Dashboard de estudos com semaforo de status
- [ ] Estudo permanece ativo apos aprovacao do cliente
- [ ] Exportacao de laudo de estabilidade

### 12.7 Categorizacao e Qualidade de Dados
- [ ] Categorias de interesse em 2 niveis com alerta Grau 2 ANVISA
- [ ] Canais de origem com agrupamento e campo de detalhe
- [ ] Validacao de CNPJ, e-mail e telefone
- [ ] Buscas por nome, CNPJ, contato, categoria, ingrediente

### 12.8 Interface e Usabilidade
- [ ] Sistema responsivo para celular (equipe comercial em campo)
- [ ] Campos P&D otimizados para tablets (formuladores no laboratorio)
- [ ] Dashboard inicial personalizado por perfil com tarefas pendentes em destaque
- [ ] Notificacoes in-app e opcionalmente WhatsApp/e-mail

**Regra de bloqueio:** este checklist deve ser revisado a cada sprint. Itens nao marcados bloqueiam o avanco para o modulo subsequente (Pedidos / PCP / Compras / Producao).
