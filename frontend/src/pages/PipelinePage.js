import { useState, useEffect, useCallback, useRef } from "react";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { DragDropContext, Droppable, Draggable } from "@hello-pangea/dnd";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter
} from "@/components/ui/dialog";
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from "@/components/ui/select";
import CardSheet from "@/components/CardSheet";
import ViewSwitcher from "@/components/ViewSwitcher";
import FilterBar, { applyFilters } from "@/components/FilterBar";
import ListView from "@/components/ListView";
import { Plus, Phone, Mail, GripVertical, Wifi, WifiOff } from "lucide-react";
import { toast } from "sonner";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";
import { getCurrentBackendUrl, toWebSocketUrl } from "@/lib/backend";

const TEMP_CLASSES = { frio: "badge-frio", morno: "badge-morno", quente: "badge-quente" };
const TEMP_LABELS = { frio: "FRIO", morno: "MORNO", quente: "QUENTE" };

export default function PipelinePage() {
    const { user } = useAuth();
    const [board, setBoard] = useState(null);
    const [loading, setLoading] = useState(true);
    const [selectedCardId, setSelectedCardId] = useState(null);
    const [showNewCard, setShowNewCard] = useState(false);
    const [newCardStageId, setNewCardStageId] = useState("");
    const [newCard, setNewCard] = useState({
        nome_cliente: "", telefone: "", email: "", status: "frio",
        produto: "", nome_projeto: "", objetivo_projeto: "", aplicacoes_desenvolver: "",
        ativos_claims: "", referencias: "", referencias_fotos_url: "", orcamento_projeto: "",
        textura_esperada: "", aplicacao: "", sensorial: "", ph: "", outras_observacoes: "",
    });
    const [wsConnected, setWsConnected] = useState(false);
    const [view, setView] = useState(() => localStorage.getItem("pipeline:view") || "kanban");
    const [filters, setFilters] = useState({});
    const [backwardMove, setBackwardMove] = useState(null); // { draggableId, srcStage, dstStage }
    const [justification, setJustification] = useState("");
    const [justificationError, setJustificationError] = useState(false);
    const wsRef = useRef(null);
    const boardLoadedRef = useRef(false);

    useEffect(() => {
        localStorage.setItem("pipeline:view", view);
    }, [view]);

    const loadBoard = useCallback(async () => {
        try {
            const { data: pipelines } = await api.get("/pipelines");
            if (pipelines.length === 0) return;
            const { data } = await api.get(`/pipelines/${pipelines[0].id}/board`);
            setBoard(data);
            boardLoadedRef.current = true;
        } catch (e) {
            console.error("Failed to load board", e);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { loadBoard(); }, [loadBoard]);

    // WebSocket connection
    useEffect(() => {
        const wsBackendUrl = toWebSocketUrl(getCurrentBackendUrl());
        if (!user || !wsBackendUrl) return;

        const connectWs = async () => {
            try {
                // Browser sends cookies automatically for same-origin WS
                const ws = new WebSocket(`${wsBackendUrl}/api/ws`);

                ws.onopen = () => {
                    setWsConnected(true);
                    console.log("WebSocket connected");
                };

                ws.onmessage = (event) => {
                    try {
                        const msg = JSON.parse(event.data);
                        if (msg.event === "card_created" || msg.event === "card_moved") {
                            if (boardLoadedRef.current) {
                                loadBoard();
                            }
                        }
                    } catch {}
                };

                ws.onclose = () => {
                    setWsConnected(false);
                    setTimeout(connectWs, 5000);
                };

                ws.onerror = () => {
                    setWsConnected(false);
                };

                wsRef.current = ws;
            } catch {
                setTimeout(connectWs, 5000);
            }
        };

        connectWs();

        return () => {
            if (wsRef.current) {
                wsRef.current.close();
            }
        };
    }, [user, loadBoard]);

    const handleDragEnd = async (result) => {
        if (!result.destination || !board) return;
        const { draggableId, source, destination } = result;
        if (source.droppableId === destination.droppableId) return;

        const srcStage = board.stages.find(s => s.id === source.droppableId);
        const dstStage = board.stages.find(s => s.id === destination.droppableId);
        if (!srcStage || !dstStage) return;

        const isBackward = (dstStage.order ?? 0) < (srcStage.order ?? 0);
        if (isBackward) {
            // Don't do the optimistic move — ask for justification first
            setBackwardMove({ draggableId, srcStage, dstStage, destinationIndex: destination.index });
            setJustification("");
            setJustificationError(false);
            return;
        }

        const newStages = board.stages.map(s => ({ ...s, cards: [...s.cards] }));
        const srcStageOpt = newStages.find(s => s.id === source.droppableId);
        const dstStageOpt = newStages.find(s => s.id === destination.droppableId);
        const cardIdx = srcStageOpt.cards.findIndex(c => c.id === draggableId);
        if (cardIdx === -1) return;
        const [card] = srcStageOpt.cards.splice(cardIdx, 1);
        card.stage_id = destination.droppableId;
        dstStageOpt.cards.splice(destination.index, 0, card);
        setBoard({ ...board, stages: newStages });

        try {
            await api.put(`/cards/${draggableId}/move`, { stage_id: destination.droppableId });
            toast.success(`Lead movido para ${dstStage.name}`);
        } catch {
            toast.error("Erro ao mover lead");
            loadBoard();
        }
    };

    const handleConfirmBackwardMove = async () => {
        if (!justification.trim()) {
            setJustificationError(true);
            return;
        }
        const { draggableId, dstStage } = backwardMove;
        try {
            await api.put(`/cards/${draggableId}/move`, {
                stage_id: dstStage.id,
                justification: justification.trim(),
            });
            toast.success(`Lead retornado para "${dstStage.name}". Líder notificado para revisão.`);
            setBackwardMove(null);
            setJustification("");
            loadBoard();
        } catch (err) {
            toast.error(err.response?.data?.detail || "Erro ao mover lead");
        }
    };

    const handleCreateCard = async () => {
        if (!newCard.nome_cliente || !newCardStageId || !board) return;
        try {
            await api.post("/cards", {
                ...newCard,
                stage_id: newCardStageId,
                pipeline_id: board.pipeline.id,
            });
            setShowNewCard(false);
            setNewCard({
                nome_cliente: "", telefone: "", email: "", status: "frio",
                produto: "", nome_projeto: "", objetivo_projeto: "", aplicacoes_desenvolver: "",
                ativos_claims: "", referencias: "", referencias_fotos_url: "", orcamento_projeto: "",
                textura_esperada: "", aplicacao: "", sensorial: "", ph: "", outras_observacoes: "",
            });
            setNewCardStageId("");
            toast.success("Lead criado com sucesso");
            loadBoard();
        } catch {
            toast.error("Erro ao criar lead");
        }
    };

    if (loading) return (
        <div className="p-8 page-enter" data-testid="pipeline-loading">
            <div className="animate-pulse space-y-4">
                <div className="h-8 w-56 bg-muted rounded" />
                <div className="flex gap-4">{[1,2,3,4].map(i => <div key={i} className="h-96 w-72 bg-muted rounded-lg" />)}</div>
            </div>
        </div>
    );

    if (!board) return (
        <div className="p-8" data-testid="pipeline-empty">
            <p className="text-muted-foreground">Nenhum pipeline encontrado.</p>
        </div>
    );

    return (
        <div className="p-6 page-enter" data-testid="pipeline-page">
            <div className="flex items-center justify-between mb-6">
                <div>
                    <h1 className="text-3xl font-heading font-semibold tracking-tight">{board.pipeline.name}</h1>
                    <p className="text-sm text-muted-foreground mt-1">
                        {board.stages.reduce((sum, s) => sum + s.cards.length, 0)} leads no pipeline
                    </p>
                </div>
                <div className="flex items-center gap-3">
                    <ViewSwitcher value={view} onChange={setView} testIdPrefix="pipeline" />
                    <span className={`flex items-center gap-1.5 text-xs ${wsConnected ? "text-green-500" : "text-muted-foreground"}`} data-testid="ws-status">
                        {wsConnected ? <Wifi className="h-3.5 w-3.5" /> : <WifiOff className="h-3.5 w-3.5" />}
                        {wsConnected ? "Tempo real" : "Offline"}
                    </span>
                    <Button onClick={() => setShowNewCard(true)} data-testid="new-card-btn">
                        <Plus className="h-4 w-4 mr-2" /> Novo Lead
                    </Button>
                </div>
            </div>

            {(() => {
                const stageOptions = board.stages.map((s) => ({ value: s.id, label: s.name }));
                const filterFields = [
                    { key: "search", type: "search", placeholder: "Buscar por nome, telefone, e-mail...",
                      searchKeys: [(c) => c.nome_cliente, (c) => c.telefone, (c) => c.email, (c) => c.produto] },
                    { key: "stage", type: "multi", label: "Fase", options: stageOptions, getter: (c) => c.stage_id },
                    { key: "status", type: "select", label: "Temperatura",
                      options: [
                          { value: "frio", label: "Frio" },
                          { value: "morno", label: "Morno" },
                          { value: "quente", label: "Quente" },
                      ] },
                ];
                const allCards = board.stages.flatMap((s) => s.cards.map((c) => ({ ...c, stage_id: s.id })));
                const filteredCards = applyFilters(allCards, filters, filterFields);
                const filteredStages = board.stages.map((s) => ({
                    ...s,
                    cards: filteredCards.filter((c) => c.stage_id === s.id),
                }));
                const stageNameById = Object.fromEntries(board.stages.map((s) => [s.id, s.name]));

                return (
                    <>
                        <FilterBar
                            filters={filters}
                            onChange={setFilters}
                            fields={filterFields}
                            testIdPrefix="pipeline-filter"
                        />

                        {view === "kanban" ? (
            <DragDropContext onDragEnd={handleDragEnd}>
                <div className="kanban-board" data-testid="kanban-board">
                    {filteredStages.map((stage) => (
                        <Droppable droppableId={stage.id} key={stage.id}>
                            {(provided, snapshot) => (
                                <div
                                    ref={provided.innerRef}
                                    {...provided.droppableProps}
                                    className={`kanban-column rounded-lg ${
                                        snapshot.isDraggingOver ? "bg-accent/50" : "bg-muted/30"
                                    }`}
                                    data-testid={`stage-${stage.order}`}
                                >
                                    <div className="p-3 border-b border-border">
                                        <div className="flex items-center justify-between">
                                            <h3 className="font-heading font-medium text-sm truncate">{stage.name}</h3>
                                            <span className="text-xs text-muted-foreground mono-num ml-2">{stage.cards.length}</span>
                                        </div>
                                    </div>
                                    <div className="p-2 space-y-2 min-h-[200px]">
                                        {stage.cards.map((card, index) => (
                                            <Draggable draggableId={card.id} index={index} key={card.id}>
                                                {(provided, snapshot) => (
                                                    <div
                                                        ref={provided.innerRef}
                                                        {...provided.draggableProps}
                                                        className={`bg-card border border-border rounded-md p-3 cursor-pointer transition-transform duration-150 ${
                                                            snapshot.isDragging ? "kanban-card-dragging" : "hover:-translate-y-0.5 hover:shadow-sm"
                                                        }`}
                                                        onClick={() => setSelectedCardId(card.id)}
                                                        data-testid={`card-${card.id}`}
                                                    >
                                                        <div className="flex items-start justify-between gap-2">
                                                            <div className="flex-1 min-w-0">
                                                                <p className="font-body font-medium text-sm truncate">{card.nome_cliente}</p>
                                                                <div className="flex items-center gap-2 mt-1.5">
                                                                    {card.telefone && (
                                                                        <span className="text-xs text-muted-foreground flex items-center gap-1">
                                                                            <Phone className="h-3 w-3" />{card.telefone}
                                                                        </span>
                                                                    )}
                                                                    {card.email && (
                                                                        <span className="text-xs text-muted-foreground flex items-center gap-1 truncate">
                                                                            <Mail className="h-3 w-3" />{card.email}
                                                                        </span>
                                                                    )}
                                                                </div>
                                                            </div>
                                                            <div {...provided.dragHandleProps} className="shrink-0 mt-0.5">
                                                                <GripVertical className="h-4 w-4 text-muted-foreground/50" />
                                                            </div>
                                                        </div>
                                                        <div className="mt-2 flex items-center justify-between">
                                                            <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-[0.1em] ${TEMP_CLASSES[card.status] || "badge-frio"}`}
                                                                data-testid={`temp-badge-${card.status}`}>
                                                                {TEMP_LABELS[card.status] || "FRIO"}
                                                            </span>
                                                            <span className="text-[10px] text-muted-foreground mono-num">
                                                                {new Date(card.created_at).toLocaleDateString("pt-BR")}
                                                            </span>
                                                        </div>
                                                    </div>
                                                )}
                                            </Draggable>
                                        ))}
                                        {provided.placeholder}
                                    </div>
                                </div>
                            )}
                        </Droppable>
                    ))}
                </div>
            </DragDropContext>
                        ) : (
                            <ListView
                                items={filteredCards}
                                onRowClick={(c) => setSelectedCardId(c.id)}
                                emptyMessage="Nenhum lead corresponde aos filtros."
                                testIdPrefix="pipeline-list"
                                columns={[
                                    { key: "nome_cliente", label: "Cliente",
                                      render: (c) => <span className="font-medium">{c.nome_cliente}</span> },
                                    { key: "produto", label: "Produto",
                                      render: (c) => c.produto || c.nome_projeto || "—" },
                                    { key: "telefone", label: "Telefone",
                                      render: (c) => c.telefone || "—" },
                                    { key: "email", label: "E-mail",
                                      render: (c) => c.email || "—" },
                                    { key: "stage_id", label: "Fase",
                                      render: (c) => stageNameById[c.stage_id] || "—" },
                                    { key: "status", label: "Temperatura",
                                      render: (c) => (
                                          <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-[0.1em] ${TEMP_CLASSES[c.status] || "badge-frio"}`}>
                                              {TEMP_LABELS[c.status] || "FRIO"}
                                          </span>
                                      ) },
                                    { key: "created_at", label: "Criado em",
                                      render: (c) => new Date(c.created_at).toLocaleDateString("pt-BR") },
                                ]}
                            />
                        )}
                    </>
                );
            })()}

            <CardSheet
                cardId={selectedCardId}
                onClose={() => { setSelectedCardId(null); loadBoard(); }}
            />

            <Dialog open={!!backwardMove} onOpenChange={(open) => { if (!open) setBackwardMove(null); }}>
                <DialogContent className="max-w-md">
                    <DialogHeader>
                        <DialogTitle className="font-heading flex items-center gap-2">
                            Retorno de Fase
                        </DialogTitle>
                    </DialogHeader>
                    <div className="space-y-4 py-2">
                        {backwardMove && (
                            <p className="text-sm text-muted-foreground">
                                Movendo <b>{backwardMove.srcStage.name}</b> → <b>{backwardMove.dstStage.name}</b>.
                                Esta é uma movimentação retroativa e requer aprovação do líder.
                            </p>
                        )}
                        <div className="space-y-2">
                            <Label>Justificativa <span className="text-destructive">*</span></Label>
                            <Textarea
                                placeholder="Explique o motivo do retorno de fase..."
                                value={justification}
                                onChange={(e) => { setJustification(e.target.value); setJustificationError(false); }}
                                rows={3}
                                className={justificationError ? "border-destructive" : ""}
                            />
                            {justificationError && (
                                <p className="text-xs text-destructive">Justificativa obrigatória para retorno de fase.</p>
                            )}
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setBackwardMove(null)}>Cancelar</Button>
                        <Button variant="destructive" onClick={handleConfirmBackwardMove}>
                            Confirmar Retorno
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            <Dialog open={showNewCard} onOpenChange={setShowNewCard}>
                <DialogContent data-testid="new-card-dialog" className="max-w-2xl max-h-[85vh] flex flex-col p-0 overflow-hidden">
                    <DialogHeader className="p-6 pb-2">
                        <DialogTitle className="font-heading">Novo Cadastro — Projeto</DialogTitle>
                    </DialogHeader>
                    <div className="flex-1 min-h-0 overflow-y-auto px-6 pb-2 scrollbar-visible">
                        <div className="space-y-4 pr-3">
                            {/* Dados do Cliente */}
                            <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider pt-1">Dados do Cliente</h4>
                            <div className="space-y-2">
                                <Label>Cliente *</Label>
                                <Input data-testid="new-card-name" value={newCard.nome_cliente}
                                    onChange={(e) => setNewCard({ ...newCard, nome_cliente: e.target.value })} placeholder="Nome completo do cliente" />
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div className="space-y-2">
                                    <Label>Telefone</Label>
                                    <Input data-testid="new-card-phone" value={newCard.telefone}
                                        onChange={(e) => setNewCard({ ...newCard, telefone: e.target.value })} placeholder="(11) 99999-9999" />
                                </div>
                                <div className="space-y-2">
                                    <Label>Email</Label>
                                    <Input data-testid="new-card-email" value={newCard.email}
                                        onChange={(e) => setNewCard({ ...newCard, email: e.target.value })} placeholder="email@exemplo.com" />
                                </div>
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div className="space-y-2">
                                    <Label>Fase</Label>
                                    <Select value={newCardStageId} onValueChange={setNewCardStageId} data-testid="new-card-stage">
                                        <SelectTrigger data-testid="new-card-stage-trigger">
                                            <SelectValue placeholder="Selecionar fase" />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {board.stages.map(s => (
                                                <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>
                                <div className="space-y-2">
                                    <Label>Temperatura</Label>
                                    <Select value={newCard.status} onValueChange={(v) => setNewCard({ ...newCard, status: v })} data-testid="new-card-status">
                                        <SelectTrigger data-testid="new-card-status-trigger">
                                            <SelectValue />
                                        </SelectTrigger>
                                        <SelectContent>
                                            <SelectItem value="frio">Frio</SelectItem>
                                            <SelectItem value="morno">Morno</SelectItem>
                                            <SelectItem value="quente">Quente</SelectItem>
                                        </SelectContent>
                                    </Select>
                                </div>
                            </div>

                            {/* Dados do Projeto */}
                            <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider pt-3 border-t mt-2">Dados do Projeto</h4>
                            <div className="grid grid-cols-2 gap-4">
                                <div className="space-y-2">
                                    <Label>Produto</Label>
                                    <Input value={newCard.produto}
                                        onChange={(e) => setNewCard({ ...newCard, produto: e.target.value })} placeholder="Ex: Sérum, Creme, Shampoo" />
                                </div>
                                <div className="space-y-2">
                                    <Label>Nome do Projeto</Label>
                                    <Input value={newCard.nome_projeto}
                                        onChange={(e) => setNewCard({ ...newCard, nome_projeto: e.target.value })} placeholder="Nome interno do projeto" />
                                </div>
                            </div>
                            <div className="space-y-2">
                                <Label>Objetivo do Projeto</Label>
                                <Textarea value={newCard.objetivo_projeto}
                                    onChange={(e) => setNewCard({ ...newCard, objetivo_projeto: e.target.value })} placeholder="Qual o objetivo principal deste desenvolvimento?" rows={2} />
                            </div>
                            <div className="space-y-2">
                                <Label>Aplicações a Desenvolver</Label>
                                <Textarea value={newCard.aplicacoes_desenvolver}
                                    onChange={(e) => setNewCard({ ...newCard, aplicacoes_desenvolver: e.target.value })} placeholder="Quais aplicações serão desenvolvidas?" rows={2} />
                            </div>
                            <div className="space-y-2">
                                <Label>Ativos para Claims</Label>
                                <Textarea value={newCard.ativos_claims}
                                    onChange={(e) => setNewCard({ ...newCard, ativos_claims: e.target.value })} placeholder="Ativos desejados, claims de marketing..." rows={2} />
                            </div>
                            <div className="space-y-2">
                                <Label>Referências</Label>
                                <Textarea value={newCard.referencias}
                                    onChange={(e) => setNewCard({ ...newCard, referencias: e.target.value })} placeholder="Produtos de referência, benchmarks..." rows={2} />
                            </div>
                            <div className="space-y-2">
                                <Label>Referências Fotos <span className="text-muted-foreground text-xs">(não obrigatório — cole URL)</span></Label>
                                <Input value={newCard.referencias_fotos_url}
                                    onChange={(e) => setNewCard({ ...newCard, referencias_fotos_url: e.target.value })} placeholder="URL da imagem ou link de referência" />
                            </div>
                            <div className="space-y-2">
                                <Label>Orçamento do Projeto</Label>
                                <Input value={newCard.orcamento_projeto}
                                    onChange={(e) => setNewCard({ ...newCard, orcamento_projeto: e.target.value })} placeholder="R$ 0,00 ou faixa de valor" />
                            </div>

                            {/* Especificações Técnicas */}
                            <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider pt-3 border-t mt-2">Especificações Técnicas</h4>
                            <div className="grid grid-cols-2 gap-4">
                                <div className="space-y-2">
                                    <Label>Textura Esperada</Label>
                                    <Input value={newCard.textura_esperada}
                                        onChange={(e) => setNewCard({ ...newCard, textura_esperada: e.target.value })} placeholder="Ex: Gel creme, fluida, mousse" />
                                </div>
                                <div className="space-y-2">
                                    <Label>Aplicação</Label>
                                    <Input value={newCard.aplicacao}
                                        onChange={(e) => setNewCard({ ...newCard, aplicacao: e.target.value })} placeholder="Ex: Facial, corporal, capilar" />
                                </div>
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div className="space-y-2">
                                    <Label>Sensorial</Label>
                                    <Input value={newCard.sensorial}
                                        onChange={(e) => setNewCard({ ...newCard, sensorial: e.target.value })} placeholder="Ex: Toque seco, hidratante, aveludado" />
                                </div>
                                <div className="space-y-2">
                                    <Label>pH</Label>
                                    <Input value={newCard.ph}
                                        onChange={(e) => setNewCard({ ...newCard, ph: e.target.value })} placeholder="Ex: 5.5 - 6.0" />
                                </div>
                            </div>
                            <div className="space-y-2 pb-2">
                                <Label>Outras Observações e/ou Sensoriais</Label>
                                <Textarea value={newCard.outras_observacoes}
                                    onChange={(e) => setNewCard({ ...newCard, outras_observacoes: e.target.value })} placeholder="Informações adicionais sobre o projeto..." rows={3} />
                            </div>
                        </div>
                    </div>
                    <DialogFooter className="p-6 pt-3 border-t">
                        <Button variant="outline" onClick={() => setShowNewCard(false)}>Cancelar</Button>
                        <Button onClick={handleCreateCard} data-testid="create-card-btn" disabled={!newCard.nome_cliente || !newCardStageId}>
                            Criar Cadastro
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
