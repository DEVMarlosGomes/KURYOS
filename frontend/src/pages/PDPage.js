import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { formatApiError } from "@/lib/formatError";
import { DragDropContext, Droppable, Draggable } from "@hello-pangea/dnd";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { GripVertical, Search, Building2, Calendar, Plus, Sparkles, ExternalLink } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import PDSubNav from "@/components/PDSubNav";

const STAGES = [
    { id: "solicitado", label: "Aberto", color: "bg-gray-400" },
    { id: "em_desenvolvimento", label: "Em Desenvolvimento", color: "bg-blue-400" },
    { id: "em_testes", label: "Em Testes", color: "bg-purple-400" },
    { id: "aguardando_aprovacao", label: "Aguardando Aprovação", color: "bg-yellow-400" },
    { id: "retrabalho_interno", label: "Retrabalho", color: "bg-red-400" },
];

export default function PDPage() {
    const [cards, setCards] = useState([]);
    const [loading, setLoading] = useState(true);
    const [search, setSearch] = useState("");
    const [selectedCard, setSelectedCard] = useState(null);
    const [showResearch, setShowResearch] = useState(false);
    const [researchForm, setResearchForm] = useState({
        project_name: "",
        objectives: "",
        description: "",
        category: "",
        references: "",
        priority: "Normal",
        deadline: "",
    });
    const [creatingResearch, setCreatingResearch] = useState(false);
    const navigate = useNavigate();

    const loadCards = useCallback(async () => {
        try {
            const params = search ? { search } : {};
            const { data } = await api.get("/crm/pd/cards", { params });
            console.log("P&D cards loaded:", data);
            const validCards = Array.isArray(data) ? data.filter(c => c && c.id) : [];
            setCards(validCards);
        } catch (e) {
            console.error("Failed to load P&D cards", e);
            setCards([]);
        } finally {
            setLoading(false);
        }
    }, [search]);

    useEffect(() => { loadCards(); }, [loadCards]);

    const cardsByStage = STAGES.reduce((acc, stage) => {
        acc[stage.id] = cards.filter(c => c.status_pd === stage.id);
        return acc;
    }, {});

    const handleDragEnd = async (result) => {
        if (!result.destination) return;
        const { draggableId, source, destination } = result;
        if (source.droppableId === destination.droppableId) return;

        const newStatus = destination.droppableId;

        try {
            const { data } = await api.put(`/crm/pd/cards/${draggableId}/move`, {
                status: newStatus,
                observacao: ""
            });
            toast.success(`Card movido para ${data.to_status}`);
            if (data.synced_to_crm) {
                toast.success("Sincronizado com CRM Comercial!", { duration: 3000 });
            }
            loadCards();
        } catch (e) {
            toast.error(formatApiError(e));
        }
    };

    const createInternalResearch = async () => {
        if (!researchForm.project_name.trim()) {
            return toast.error("Nome do projeto é obrigatório");
        }
        setCreatingResearch(true);
        try {
            const payload = {
                ...researchForm,
                deadline: researchForm.deadline || null,
            };
            const { data } = await api.post("/pd/requests/internal-research", payload);
            toast.success(`Pesquisa Interna criada! (${data.id?.slice(0, 8)})`);
            setShowResearch(false);
            setResearchForm({
                project_name: "", objectives: "", description: "", category: "",
                references: "", priority: "Normal", deadline: "",
            });
            loadCards();
            // Navigate to detail page (PDDetail)
            if (data.id) {
                setTimeout(() => navigate(`/pd/${data.id}`), 600);
            }
        } catch (e) {
            toast.error(formatApiError(e));
        } finally {
            setCreatingResearch(false);
        }
    };

    const openCardDetail = (card) => {
        // If linked to pd_request, navigate to full detail page (like Abelinha print)
        if (card.pd_request_id) {
            navigate(`/pd/${card.pd_request_id}`);
        } else {
            setSelectedCard(card);
        }
    };

    if (loading) return (
        <div className="p-6 page-enter">
            <PDSubNav active="pd" />
            <div className="flex gap-4">
                {[1, 2, 3, 4, 5].map(i => <div key={i} className="h-96 w-64 bg-muted rounded-lg animate-pulse" />)}
            </div>
        </div>
    );

    return (
        <div className="p-6 page-enter">
            <PDSubNav active="pd" />
            <div className="flex items-center justify-between mb-6">
                <div>
                    <h1 className="text-3xl font-heading font-semibold tracking-tight">Pipeline P&D</h1>
                    <p className="text-sm text-muted-foreground mt-1">{cards.length} cards em desenvolvimento</p>
                </div>
                <div className="flex items-center gap-2">
                    <div className="relative">
                        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                        <Input placeholder="Buscar card..." value={search} onChange={(e) => setSearch(e.target.value)} className="pl-9 w-64" />
                    </div>
                    <Button onClick={() => setShowResearch(true)} className="gap-1.5">
                        <Sparkles className="h-4 w-4" /> Nova Pesquisa Interna
                    </Button>
                </div>
            </div>

            <DragDropContext onDragEnd={handleDragEnd}>
                <div className="kanban-board">
                    {STAGES.map((stage) => (
                        <Droppable droppableId={stage.id} key={stage.id}>
                            {(provided, snapshot) => (
                                <div
                                    ref={provided.innerRef}
                                    {...provided.droppableProps}
                                    className={`kanban-column rounded-lg ${snapshot.isDraggingOver ? "bg-accent/50" : "bg-muted/30"}`}
                                >
                                    <div className="p-3 border-b border-border">
                                        <div className="flex items-center gap-2">
                                            <div className={`w-2 h-2 rounded-full ${stage.color}`} />
                                            <h3 className="font-heading font-medium text-sm truncate">{stage.label}</h3>
                                            <span className="text-xs text-muted-foreground mono-num ml-auto">
                                                {(cardsByStage[stage.id] || []).length}
                                            </span>
                                        </div>
                                    </div>
                                    <div className="p-2 space-y-2 min-h-[200px]">
                                        {(cardsByStage[stage.id] || []).map((card, index) => (
                                            <Draggable draggableId={card.id} index={index} key={card.id}>
                                                {(provided, snapshot) => (
                                                    <div
                                                        ref={provided.innerRef}
                                                        {...provided.draggableProps}
                                                        className={`bg-card border border-border rounded-md p-3 cursor-pointer transition-transform duration-150 ${
                                                            snapshot.isDragging ? "kanban-card-dragging" : "hover:-translate-y-0.5 hover:shadow-sm"
                                                        } ${card.is_internal_research ? "border-purple-300 bg-purple-50/30 dark:bg-purple-950/10" : ""}`}
                                                        onClick={() => openCardDetail(card)}
                                                    >
                                                        <div className="flex items-start justify-between gap-2">
                                                            <div className="flex-1 min-w-0">
                                                                <div className="flex items-center gap-2 mb-1">
                                                                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold mono-num ${card.is_internal_research ? "bg-purple-500/20 text-purple-700 dark:text-purple-300" : "bg-primary/10 text-primary"}`}>
                                                                        {String(card.numero_completo || '?')}
                                                                    </span>
                                                                    {card.is_internal_research && (
                                                                        <Badge variant="outline" className="text-[9px] h-4 px-1 border-purple-300 text-purple-600">
                                                                            <Sparkles className="h-2.5 w-2.5 mr-0.5" /> Pesquisa
                                                                        </Badge>
                                                                    )}
                                                                </div>
                                                                <p className="font-body font-medium text-sm truncate">
                                                                    {String(card.produto || '')}
                                                                </p>
                                                                {card.descricao_aplicacao && (
                                                                    <p className="text-xs text-muted-foreground mt-1 truncate">
                                                                        {String(card.descricao_aplicacao)}
                                                                    </p>
                                                                )}
                                                                <p className="text-xs text-muted-foreground flex items-center gap-1 mt-1">
                                                                    <Building2 className="h-3 w-3" />
                                                                    {String(card.cliente || '')}
                                                                </p>
                                                                {card.responsavel_pd && (
                                                                    <p className="text-xs text-muted-foreground mt-0.5">
                                                                        👤 {String(card.responsavel_pd)}
                                                                    </p>
                                                                )}
                                                            </div>
                                                            <div {...provided.dragHandleProps} className="shrink-0">
                                                                <GripVertical className="h-4 w-4 text-muted-foreground/50" />
                                                            </div>
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

            {/* Card Detail Sheet */}
            <Sheet open={!!selectedCard} onOpenChange={(open) => !open && setSelectedCard(null)}>
                <SheetContent className="w-[480px] sm:w-[520px] p-0 flex flex-col" side="right">
                    {selectedCard && (
                        <>
                            <SheetHeader className="p-6 pb-3">
                                <SheetTitle className="font-heading text-xl">
                                    {String(selectedCard?.numero_completo || 'Card P&D')}
                                </SheetTitle>
                                <div className="flex items-center gap-2 mt-1 flex-wrap">
                                    <Badge variant="outline" className="text-xs">{String(selectedCard?.cliente || '')}</Badge>
                                    <Badge className="text-xs">{String(selectedCard?.produto || '')}</Badge>
                                </div>
                            </SheetHeader>
                            <div className="flex-1 overflow-y-auto px-6 py-4">
                                <div className="space-y-4">
                                    <div>
                                        <p className="text-xs font-semibold text-muted-foreground mb-1">Status</p>
                                        <Badge>{STAGES.find(s => s.id === selectedCard.status_pd)?.label || selectedCard.status_pd}</Badge>
                                    </div>
                                    {selectedCard.descricao_aplicacao && (
                                        <div>
                                            <p className="text-xs font-semibold text-muted-foreground mb-1">Descrição da Aplicação</p>
                                            <p className="text-sm">{selectedCard.descricao_aplicacao}</p>
                                        </div>
                                    )}
                                    {selectedCard.briefing_base && (
                                        <div>
                                            <p className="text-xs font-semibold text-muted-foreground mb-1">Briefing Base</p>
                                            <p className="text-sm whitespace-pre-wrap">{selectedCard.briefing_base}</p>
                                        </div>
                                    )}
                                    {selectedCard.observacoes_especificas && (
                                        <div>
                                            <p className="text-xs font-semibold text-muted-foreground mb-1">Observações Específicas</p>
                                            <p className="text-sm">{selectedCard.observacoes_especificas}</p>
                                        </div>
                                    )}
                                    <div>
                                        <p className="text-xs font-semibold text-muted-foreground mb-1">Responsável P&D</p>
                                        <p className="text-sm">{selectedCard.responsavel_pd || 'Não atribuído'}</p>
                                    </div>
                                    {selectedCard.prazo_prometido && (
                                        <div>
                                            <p className="text-xs font-semibold text-muted-foreground mb-1">Prazo Prometido</p>
                                            <p className="text-sm flex items-center gap-1">
                                                <Calendar className="h-3 w-3" />
                                                {new Date(selectedCard.prazo_prometido).toLocaleDateString('pt-BR')}
                                            </p>
                                        </div>
                                    )}
                                    {selectedCard.pd_request_id && (
                                        <Button size="sm" variant="outline" className="w-full gap-1.5" onClick={() => navigate(`/pd/${selectedCard.pd_request_id}`)}>
                                            <ExternalLink className="h-3.5 w-3.5" /> Abrir Detalhes Completos
                                        </Button>
                                    )}
                                </div>
                            </div>
                        </>
                    )}
                </SheetContent>
            </Sheet>

            {/* Nova Pesquisa Interna Dialog */}
            <Dialog open={showResearch} onOpenChange={setShowResearch}>
                <DialogContent className="max-w-2xl">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2">
                            <Sparkles className="h-5 w-5 text-purple-500" /> Nova Pesquisa Interna
                        </DialogTitle>
                        <DialogDescription>
                            Inicie um desenvolvimento de pesquisa própria do lab, sem cliente. O card aparecerá direto em "Em Desenvolvimento".
                        </DialogDescription>
                    </DialogHeader>

                    <div className="grid grid-cols-2 gap-3">
                        <div className="col-span-2">
                            <Label>Nome do Projeto *</Label>
                            <Input
                                value={researchForm.project_name}
                                onChange={(e) => setResearchForm(p => ({ ...p, project_name: e.target.value }))}
                                placeholder="Ex: Estudo de novas bases para body splash"
                            />
                        </div>
                        <div className="col-span-2">
                            <Label>Objetivos da Pesquisa</Label>
                            <Textarea
                                value={researchForm.objectives}
                                onChange={(e) => setResearchForm(p => ({ ...p, objectives: e.target.value }))}
                                rows={3}
                                placeholder="O que se espera descobrir / desenvolver?"
                            />
                        </div>
                        <div className="col-span-2">
                            <Label>Descrição</Label>
                            <Textarea
                                value={researchForm.description}
                                onChange={(e) => setResearchForm(p => ({ ...p, description: e.target.value }))}
                                rows={2}
                                placeholder="Contexto e detalhes"
                            />
                        </div>
                        <div>
                            <Label>Categoria</Label>
                            <Input
                                value={researchForm.category}
                                onChange={(e) => setResearchForm(p => ({ ...p, category: e.target.value }))}
                                placeholder="Ex: Perfumaria, Hidratação..."
                            />
                        </div>
                        <div>
                            <Label>Prioridade</Label>
                            <Select value={researchForm.priority} onValueChange={(v) => setResearchForm(p => ({ ...p, priority: v }))}>
                                <SelectTrigger><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="Baixa">Baixa</SelectItem>
                                    <SelectItem value="Normal">Normal</SelectItem>
                                    <SelectItem value="Alta">Alta</SelectItem>
                                    <SelectItem value="Urgente">Urgente</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        <div>
                            <Label>Prazo Alvo</Label>
                            <Input
                                type="date"
                                value={researchForm.deadline}
                                onChange={(e) => setResearchForm(p => ({ ...p, deadline: e.target.value }))}
                            />
                        </div>
                        <div>
                            <Label>Referências</Label>
                            <Input
                                value={researchForm.references}
                                onChange={(e) => setResearchForm(p => ({ ...p, references: e.target.value }))}
                                placeholder="Artigos, produtos similares..."
                            />
                        </div>
                    </div>

                    <DialogFooter>
                        <Button variant="ghost" onClick={() => setShowResearch(false)}>Cancelar</Button>
                        <Button onClick={createInternalResearch} disabled={creatingResearch} className="gap-1.5">
                            <Sparkles className="h-4 w-4" />
                            {creatingResearch ? "Criando..." : "Criar e abrir"}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
