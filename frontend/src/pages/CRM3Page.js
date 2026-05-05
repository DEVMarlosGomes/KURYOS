import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { formatApiError } from "@/lib/formatError";
import { DragDropContext, Droppable, Draggable } from "@hello-pangea/dnd";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter
} from "@/components/ui/dialog";
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from "@/components/ui/select";
import { GripVertical, Search, Building2, FlaskConical, AlertTriangle, PackageCheck, ChevronRight, Trash2, Plus, X, Edit2 } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

function CRMSubNav({ active }) {
    const navigate = useNavigate();
    const tabs = [
        { id: "clients", label: "Clientes", path: "/crm/clients" },
        { id: "projects", label: "Projetos", path: "/crm/projects" },
        { id: "samples", label: "Amostras", path: "/crm/samples" },
    ];
    return (
        <div className="flex items-center gap-1 mb-5 border-b border-border pb-3">
            {tabs.map(t => (
                <button
                    key={t.id}
                    onClick={() => navigate(t.path)}
                    className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                        active === t.id
                            ? "bg-primary text-primary-foreground shadow-sm"
                            : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                    }`}
                >
                    {t.label}
                </button>
            ))}
        </div>
    );
}

const STAGES = [
    { id: "solicitada", label: "Solicitada", color: "bg-slate-400" },
    { id: "em_elaboracao", label: "Em Elaboração", color: "bg-blue-500" },
    { id: "retrabalho", label: "Retrabalho", color: "bg-amber-500" },
    { id: "enviada", label: "Enviada", color: "bg-cyan-500" },
    { id: "aprovada", label: "Aprovada", color: "bg-emerald-500" },
    { id: "reprovada", label: "Reprovada", color: "bg-red-500" },
];

const STAGE_LABELS = Object.fromEntries(STAGES.map(s => [s.id, s.label]));

export default function CRM3Page() {
    const [samples, setSamples] = useState([]);
    const [loading, setLoading] = useState(true);
    const [search, setSearch] = useState("");
    const [selectedSample, setSelectedSample] = useState(null);
    const [selectedVariacao, setSelectedVariacao] = useState(null);
    const [showReasonModal, setShowReasonModal] = useState(false);
    const [pendingMove, setPendingMove] = useState(null);
    const [reason, setReason] = useState("");
    const [reasonOrigin, setReasonOrigin] = useState("interna");
    const [feedbackText, setFeedbackText] = useState("");
    const [reworkDirections, setReworkDirections] = useState("");
    const [tab, setTab] = useState("briefing");

    const loadSamples = useCallback(async () => {
        try {
            const params = search ? { search } : {};
            const { data } = await api.get("/crm/samples", { params });
            console.log("Samples loaded:", data);
            // Filter out invalid samples and validation errors
            const validSamples = Array.isArray(data) ? data.filter(s => {
                // Check if it's a validation error object
                if (s && s.type && s.loc && s.msg) {
                    console.warn("Validation error in response:", s);
                    return false;
                }
                // Check if it's a valid sample
                return s && typeof s === 'object' && s.id;
            }) : [];
            setSamples(validSamples);
        } catch (e) {
            console.error("Failed to load samples", e);
            setSamples([]);
        } finally {
            setLoading(false);
        }
    }, [search]);

    useEffect(() => { loadSamples(); }, [loadSamples]);

    // Agrupar variações por estágio
    const variacoesByStage = STAGES.reduce((acc, stage) => {
        acc[stage.id] = [];
        samples.forEach(sample => {
            try {
                // Validar que sample é um objeto válido
                if (!sample || typeof sample !== 'object' || !sample.id) {
                    console.warn("Invalid sample:", sample);
                    return;
                }

                if (sample.variacoes && Array.isArray(sample.variacoes) && sample.variacoes.length > 0) {
                    // Novo modelo com variações
                    sample.variacoes.forEach(variacao => {
                        if (!variacao || typeof variacao !== 'object') {
                            console.warn("Invalid variacao:", variacao);
                            return;
                        }
                        
                        if (variacao.status === stage.id) {
                            acc[stage.id].push({
                                id: variacao.id || `${sample.id}-var`,
                                codigo: variacao.codigo || '',
                                status: variacao.status || stage.id,
                                sample_id: sample.id,
                                sample_numero: sample.numero_amostra || '',
                                nome_produto: sample.nome_produto || sample.nome_amostra || '',
                                projeto_nome: sample.projeto_nome || '',
                                cliente_nome: sample.cliente_nome || '',
                                descricao_aplicacao: variacao.descricao_aplicacao || '',
                                sample_completa: sample
                            });
                        }
                    });
                } else if (sample.stage === stage.id) {
                    // Modelo antigo sem variações (compatibilidade)
                    acc[stage.id].push({
                        id: sample.id,
                        codigo: sample.codigo_referencia || sample.id,
                        status: sample.stage,
                        sample_id: sample.id,
                        sample_numero: sample.numero_amostra || '',
                        nome_produto: sample.nome_amostra || '',
                        projeto_nome: sample.projeto_nome || '',
                        cliente_nome: sample.cliente_nome || '',
                        descricao_aplicacao: '',
                        sample_completa: sample
                    });
                }
            } catch (err) {
                console.error("Error processing sample:", sample, err);
            }
        });
        return acc;
    }, {});

    const handleDragEnd = async (result) => {
        if (!result.destination) return;
        const { draggableId, source, destination } = result;
        if (source.droppableId === destination.droppableId) return;

        const newStage = destination.droppableId;

        // draggableId formato: sampleId:variacaoId ou sampleId (antigo)
        const [sampleId, variacaoId] = draggableId.split(':');

        // Require reason for retrabalho and reprovada
        if (newStage === "retrabalho" || newStage === "reprovada") {
            setPendingMove({ sampleId, variacaoId, stage: newStage });
            setReason("");
            setReasonOrigin("interna");
            setFeedbackText("");
            setReworkDirections("");
            setShowReasonModal(true);
            return;
        }

        try {
            let data;
            if (variacaoId) {
                // Novo modelo com variações
                const response = await api.put(`/crm/samples/${sampleId}/variacoes/${variacaoId}/move`, { status: newStage });
                data = response.data;
                toast.success(`Variação movida para ${data.to_status}`);
            } else {
                // Modelo antigo (compatibilidade)
                const response = await api.put(`/crm/samples/${sampleId}/move`, { stage: newStage });
                data = response.data;
                toast.success(`Amostra movida para ${data.to_stage}`);
            }

            if (data.sku_created) {
                toast.success(`SKU ${data.sku_created.codigo_interno} criado automaticamente!`, {
                    duration: 5000,
                    description: `Produto: ${data.sku_created.nome_produto}`,
                });
            }

            loadSamples();
        } catch (e) {
            toast.error(formatApiError(e));
        }
    };

    const confirmReason = async () => {
        if (!pendingMove || !reason.trim()) return;
        try {
            let data;
            if (pendingMove.stage === "retrabalho") {
                const response = await api.post(`/crm/samples/${pendingMove.sampleId}/rework`, {
                    motivo: reason,
                    origem: reasonOrigin,
                    variacao_id: pendingMove.variacaoId || undefined,
                    feedback_cliente: feedbackText || reason,
                    direcoes_retrabalho: reworkDirections,
                });
                data = response.data;
                toast.success(`Retrabalho criado como amostra #${data.novo_numero}`);
            } else if (pendingMove.variacaoId) {
                // Novo modelo com variações
                const response = await api.put(`/crm/samples/${pendingMove.sampleId}/variacoes/${pendingMove.variacaoId}/move`, {
                    status: pendingMove.stage,
                    motivo_retrabalho: reason,
                    origem_retrabalho: reasonOrigin,
                });
                data = response.data;
                toast.success(`Variação movida para ${data.to_status}`);
            } else {
                // Modelo antigo
                const response = await api.put(`/crm/samples/${pendingMove.sampleId}/move`, {
                    stage: pendingMove.stage,
                    motivo_retrabalho: reason,
                    origem_retrabalho: reasonOrigin,
                    feedback_cliente: feedbackText,
                    direcoes_retrabalho: reworkDirections,
                });
                data = response.data;
                toast.success(`Amostra movida para ${data.to_stage}`);
            }
            setShowReasonModal(false);
            setPendingMove(null);
            setFeedbackText("");
            setReworkDirections("");
            loadSamples();
        } catch (e) {
            toast.error(formatApiError(e));
        }
    };

    const handleUpdateSample = async (sampleId, updates) => {
        try {
            await api.put(`/crm/samples/${sampleId}`, updates);
            toast.success("Amostra atualizada!");
            loadSamples();
        } catch (e) {
            toast.error(formatApiError(e));
        }
    };

    const handleDeleteSample = async () => {
        if (!selectedSample) return;
        if (!window.confirm(`Excluir amostra "${selectedSample.nome_produto || selectedSample.nome_amostra}" e TODAS as variações/cards P&D vinculados? Ação irreversível.`)) return;
        try {
            const { data } = await api.delete(`/crm/samples/${selectedSample.id}`);
            toast.success(`Amostra excluída (${data.deleted_pd_cards} card(s) P&D removidos).`);
            setSelectedSample(null);
            loadSamples();
        } catch (e) {
            toast.error(formatApiError(e));
        }
    };

    const handleUpdateVariacao = async (sampleId, variacaoId, updates) => {
        try {
            await api.put(`/crm/samples/${sampleId}/variacoes/${variacaoId}`, updates);
            toast.success("Variação atualizada!");
            loadSamples();
            // Reload selected sample
            const { data } = await api.get(`/crm/samples/${sampleId}`);
            setSelectedSample(data);
        } catch (e) {
            toast.error(formatApiError(e));
        }
    };

    const handleDeleteVariacao = async (sampleId, variacaoId, codigo) => {
        if (!window.confirm(`Excluir a variação ${codigo}? O card P&D vinculado também será removido.`)) return;
        try {
            await api.delete(`/crm/samples/${sampleId}/variacoes/${variacaoId}`);
            toast.success(`Variação ${codigo} excluída.`);
            loadSamples();
            const { data } = await api.get(`/crm/samples/${sampleId}`);
            setSelectedSample(data);
        } catch (e) {
            toast.error(formatApiError(e));
        }
    };

    const [showAddVariacoes, setShowAddVariacoes] = useState(false);
    const [newVariacoes, setNewVariacoes] = useState([{
        descricao_aplicacao: "",
        percentual_fragrancia: "",
        referencia_fragrancia: "",
        custo_fragrancia: "",
        observacoes_especificas: ""
    }]);

    const handleAddVariacoesSubmit = async () => {
        if (!selectedSample) return;
        const valid = newVariacoes.filter(v => v.descricao_aplicacao.trim() || v.referencia_fragrancia.trim());
        if (valid.length === 0) {
            toast.error("Preencha pelo menos uma variação.");
            return;
        }
        try {
            const payload = {
                variacoes: valid.map(v => ({
                    descricao_aplicacao: v.descricao_aplicacao,
                    percentual_fragrancia: v.percentual_fragrancia ? parseFloat(v.percentual_fragrancia) : null,
                    referencia_fragrancia: v.referencia_fragrancia,
                    custo_fragrancia: v.custo_fragrancia ? parseFloat(v.custo_fragrancia) : null,
                    observacoes_especificas: v.observacoes_especificas,
                }))
            };
            const { data } = await api.post(`/crm/samples/${selectedSample.id}/variacoes`, payload);
            toast.success(`${data.added} variação(ões) adicionada(s)!`);
            setShowAddVariacoes(false);
            setNewVariacoes([{
                descricao_aplicacao: "",
                percentual_fragrancia: "",
                referencia_fragrancia: "",
                custo_fragrancia: "",
                observacoes_especificas: ""
            }]);
            loadSamples();
            const response = await api.get(`/crm/samples/${selectedSample.id}`);
            setSelectedSample(response.data);
        } catch (e) {
            toast.error(formatApiError(e));
        }
    };

    if (loading) return (
        <div className="p-8 page-enter">
            <div className="animate-pulse space-y-4">
                <div className="h-8 w-64 bg-muted rounded" />
                <div className="flex gap-4">{[1,2,3,4,5,6].map(i => <div key={i} className="h-96 w-56 bg-muted rounded-lg" />)}</div>
            </div>
        </div>
    );

    return (
        <div className="p-6 page-enter" data-testid="crm3-page">
            <CRMSubNav active="samples" />
            <div className="flex items-center justify-between mb-6">
                <div>
                    <h1 className="text-3xl font-heading font-semibold tracking-tight">Pipeline de Amostras</h1>
                    <p className="text-sm text-muted-foreground mt-1">{samples.length} amostras</p>
                </div>
                <div className="relative">
                    <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                    <Input placeholder="Buscar amostra..." value={search} onChange={(e) => setSearch(e.target.value)} className="pl-9 w-64" />
                </div>
            </div>

            <DragDropContext onDragEnd={handleDragEnd}>
                <div className="kanban-board" data-testid="crm3-kanban">
                    {STAGES.map((stage) => (
                        <Droppable droppableId={stage.id} key={stage.id}>
                            {(provided, snapshot) => (
                                <div
                                    ref={provided.innerRef}
                                    {...provided.droppableProps}
                                    className={`kanban-column rounded-lg ${snapshot.isDraggingOver ? "bg-accent/50" : "bg-muted/30"}`}
                                    data-testid={`crm3-stage-${stage.id}`}
                                >
                                    <div className="p-3 border-b border-border">
                                        <div className="flex items-center gap-2">
                                            <div className={`w-2 h-2 rounded-full ${stage.color}`} />
                                            <h3 className="font-heading font-medium text-sm truncate">{stage.label}</h3>
                                            <span className="text-xs text-muted-foreground mono-num ml-auto">
                                                {(variacoesByStage[stage.id] || []).length}
                                            </span>
                                        </div>
                                    </div>
                                    <div className="p-2 space-y-2 min-h-[200px]">
                                        {(variacoesByStage[stage.id] || []).map((variacao, index) => {
                                            const draggableId = variacao.sample_id + (variacao.id ? `:${variacao.id}` : '');
                                            return (
                                            <Draggable draggableId={draggableId} index={index} key={draggableId}>
                                                {(provided, snapshot) => (
                                                    <div
                                                        ref={provided.innerRef}
                                                        {...provided.draggableProps}
                                                        className={`bg-card border border-border rounded-md p-3 cursor-pointer transition-transform duration-150 ${
                                                            snapshot.isDragging ? "kanban-card-dragging" : "hover:-translate-y-0.5 hover:shadow-sm"
                                                        }`}
                                                        onClick={() => { 
                                                            setSelectedSample(variacao.sample_completa); 
                                                            setSelectedVariacao(variacao);
                                                            setTab("briefing"); 
                                                        }}
                                                    >
                                                        <div className="flex items-start justify-between gap-2">
                                                            <div className="flex-1 min-w-0">
                                                                <div className="flex items-center gap-2 mb-1">
                                                                    <span className="px-1.5 py-0.5 bg-primary/10 text-primary rounded text-[10px] font-bold mono-num">
                                                                        {String(variacao.codigo || variacao.sample_numero || '?')}
                                                                    </span>
                                                                </div>
                                                                <p className="font-body font-medium text-sm truncate">
                                                                    {String(variacao.nome_produto || '')}
                                                                </p>
                                                                {variacao.descricao_aplicacao && (
                                                                    <p className="text-xs text-muted-foreground mt-1 truncate">
                                                                        {String(variacao.descricao_aplicacao)}
                                                                    </p>
                                                                )}
                                                                <p className="text-xs text-muted-foreground flex items-center gap-1 mt-1">
                                                                    <FlaskConical className="h-3 w-3" />
                                                                    {String(variacao.projeto_nome || '')}
                                                                </p>
                                                                <p className="text-xs text-muted-foreground flex items-center gap-1 mt-0.5">
                                                                    <Building2 className="h-3 w-3" />
                                                                    {String(variacao.cliente_nome || '')}
                                                                </p>
                                                            </div>
                                                            <div {...provided.dragHandleProps} className="shrink-0">
                                                                <GripVertical className="h-4 w-4 text-muted-foreground/50" />
                                                            </div>
                                                        </div>
                                                    </div>
                                                )}
                                            </Draggable>
                                            );
                                        })}
                                        {provided.placeholder}
                                    </div>
                                </div>
                            )}
                        </Droppable>
                    ))}
                </div>
            </DragDropContext>

            {/* Sample Detail Sheet */}
            <Sheet open={!!selectedSample} onOpenChange={(v) => { if (!v) { setSelectedSample(null); loadSamples(); } }}>
                <SheetContent className="w-[480px] sm:w-[520px] p-0 flex flex-col" side="right">
                    {selectedSample && (
                        <>
                            <SheetHeader className="p-6 pb-3">
                                <SheetTitle className="font-heading text-xl">
                                    {String(selectedSample?.nome_amostra || selectedSample?.nome_produto || 'Amostra')}
                                </SheetTitle>
                                <div className="flex items-center gap-2 mt-1 flex-wrap">
                                    <Badge variant="outline" className="text-xs">{String(selectedSample?.cliente_nome || '')}</Badge>
                                    <Badge className="text-xs">{String(selectedSample?.projeto_nome || '')}</Badge>
                                    {selectedSample?.codigo_referencia && (
                                        <span className="text-xs mono-num text-muted-foreground">{String(selectedSample.codigo_referencia)}</span>
                                    )}
                                </div>
                            </SheetHeader>
                            <Separator />
                            <Tabs value={tab} onValueChange={setTab} className="flex-1 flex flex-col min-h-0">
                                <TabsList className="mx-6 mt-3">
                                    <TabsTrigger value="briefing">Briefing</TabsTrigger>
                                    <TabsTrigger value="variacoes">Variações</TabsTrigger>
                                    <TabsTrigger value="info">Dados</TabsTrigger>
                                    <TabsTrigger value="retrabalhos">Retrabalhos</TabsTrigger>
                                    <TabsTrigger value="timeline">Histórico</TabsTrigger>
                                </TabsList>

                                <TabsContent value="briefing" className="flex-1 min-h-0 overflow-y-auto px-6 pb-6 mt-3">
                                    <div className="space-y-4">
                                        <div className="space-y-2">
                                            <Label className="text-xs font-semibold">Produto</Label>
                                            <Input defaultValue={selectedSample.produto || ""}
                                                onBlur={(e) => handleUpdateSample(selectedSample.id, { produto: e.target.value })} />
                                        </div>
                                        <div className="space-y-2">
                                            <Label className="text-xs font-semibold">Objetivo do Projeto</Label>
                                            <Textarea defaultValue={selectedSample.objetivo_projeto || ""} rows={3}
                                                onBlur={(e) => handleUpdateSample(selectedSample.id, { objetivo_projeto: e.target.value })} />
                                        </div>
                                        <div className="space-y-2">
                                            <Label className="text-xs font-semibold">Aplicações a Desenvolver</Label>
                                            <Textarea defaultValue={selectedSample.aplicacoes_desenvolver || ""} rows={3}
                                                onBlur={(e) => handleUpdateSample(selectedSample.id, { aplicacoes_desenvolver: e.target.value })} />
                                        </div>
                                        <div className="space-y-2">
                                            <Label className="text-xs font-semibold">Ativos para Claims</Label>
                                            <Textarea defaultValue={selectedSample.ativos_claims || ""} rows={3}
                                                onBlur={(e) => handleUpdateSample(selectedSample.id, { ativos_claims: e.target.value })} />
                                        </div>
                                        <div className="space-y-2">
                                            <Label className="text-xs font-semibold">Referências</Label>
                                            <Textarea defaultValue={selectedSample.referencias || ""} rows={3}
                                                onBlur={(e) => handleUpdateSample(selectedSample.id, { referencias: e.target.value })} />
                                        </div>
                                        <div className="space-y-2">
                                            <Label className="text-xs font-semibold">Referências de Fotos</Label>
                                            {selectedSample.referencias_fotos && selectedSample.referencias_fotos.length > 0 ? (
                                                <div className="grid grid-cols-2 gap-2">
                                                    {selectedSample.referencias_fotos.map((url, idx) => (
                                                        <img key={idx} src={url} alt={`Ref ${idx + 1}`} className="w-full h-32 object-cover rounded border" />
                                                    ))}
                                                </div>
                                            ) : (
                                                <p className="text-xs text-muted-foreground italic">Nenhuma foto de referência</p>
                                            )}
                                        </div>
                                        <div className="space-y-2">
                                            <Label className="text-xs font-semibold">Orçamento do Projeto</Label>
                                            <Input defaultValue={selectedSample.orcamento_projeto || ""}
                                                onBlur={(e) => handleUpdateSample(selectedSample.id, { orcamento_projeto: e.target.value })} />
                                        </div>
                                        <div className="grid grid-cols-3 gap-3">
                                            <div className="space-y-2">
                                                <Label className="text-xs font-semibold">Textura Esperada</Label>
                                                <Input defaultValue={selectedSample.textura_esperada || ""}
                                                    onBlur={(e) => handleUpdateSample(selectedSample.id, { textura_esperada: e.target.value })} />
                                            </div>
                                            <div className="space-y-2">
                                                <Label className="text-xs font-semibold">Sensorial</Label>
                                                <Input defaultValue={selectedSample.sensorial || ""}
                                                    onBlur={(e) => handleUpdateSample(selectedSample.id, { sensorial: e.target.value })} />
                                            </div>
                                            <div className="space-y-2">
                                                <Label className="text-xs font-semibold">pH</Label>
                                                <Input defaultValue={selectedSample.ph || ""}
                                                    onBlur={(e) => handleUpdateSample(selectedSample.id, { ph: e.target.value })} />
                                            </div>
                                        </div>
                                        <div className="space-y-2">
                                            <Label className="text-xs font-semibold">Aplicação</Label>
                                            <Textarea defaultValue={selectedSample.aplicacao || ""} rows={2}
                                                onBlur={(e) => handleUpdateSample(selectedSample.id, { aplicacao: e.target.value })} />
                                        </div>
                                    </div>
                                </TabsContent>

                                <TabsContent value="variacoes" className="flex-1 min-h-0 overflow-y-auto px-6 pb-6 mt-3">
                                    <div className="space-y-3">
                                        <div className="flex items-center justify-between">
                                            <div>
                                                <h4 className="text-sm font-semibold">
                                                    {(selectedSample?.variacoes?.length || 0)} variação(ões)
                                                </h4>
                                                <p className="text-xs text-muted-foreground">Amostra #{selectedSample?.numero_amostra || '?'}</p>
                                            </div>
                                            <Button size="sm" onClick={() => setShowAddVariacoes(true)} data-testid="btn-add-variacao">
                                                <Plus className="h-4 w-4 mr-1" /> Adicionar Variação
                                            </Button>
                                        </div>
                                        {(selectedSample?.variacoes || []).map((v) => (
                                            <div key={v.id} className="border border-border rounded-lg p-3 space-y-2 bg-card">
                                                <div className="flex items-center justify-between">
                                                    <div className="flex items-center gap-2">
                                                        <span className="px-2 py-0.5 bg-primary/10 text-primary rounded text-xs font-bold mono-num">
                                                            {v.codigo}
                                                        </span>
                                                        <Badge variant="outline" className="text-[10px]">{STAGE_LABELS[v.status] || v.status}</Badge>
                                                        {v.sku_id && <Badge className="text-[10px] bg-emerald-500">SKU</Badge>}
                                                    </div>
                                                    <Button
                                                        variant="ghost" size="icon"
                                                        className="h-7 w-7 text-destructive hover:text-destructive hover:bg-destructive/10"
                                                        onClick={() => handleDeleteVariacao(selectedSample.id, v.id, v.codigo)}
                                                        disabled={v.sku_id || (selectedSample.variacoes.length <= 1)}
                                                        title={v.sku_id ? "Não pode excluir: já gerou SKU" : (selectedSample.variacoes.length <= 1 ? "Última variação" : "Excluir variação")}
                                                        data-testid={`btn-delete-variacao-${v.id}`}
                                                    >
                                                        <Trash2 className="h-3.5 w-3.5" />
                                                    </Button>
                                                </div>
                                                <div className="grid grid-cols-2 gap-2">
                                                    <div className="space-y-1 col-span-2">
                                                        <Label className="text-[10px] text-muted-foreground">Descrição da Aplicação</Label>
                                                        <Input
                                                            defaultValue={v.descricao_aplicacao || ""}
                                                            className="h-8 text-xs"
                                                            onBlur={(e) => {
                                                                if (e.target.value !== (v.descricao_aplicacao || ""))
                                                                    handleUpdateVariacao(selectedSample.id, v.id, { descricao_aplicacao: e.target.value });
                                                            }}
                                                        />
                                                    </div>
                                                    <div className="space-y-1">
                                                        <Label className="text-[10px] text-muted-foreground">% Fragrância</Label>
                                                        <Input
                                                            type="number" step="0.01"
                                                            defaultValue={v.percentual_fragrancia ?? ""}
                                                            className="h-8 text-xs"
                                                            onBlur={(e) => {
                                                                const val = e.target.value === "" ? null : parseFloat(e.target.value);
                                                                if (val !== v.percentual_fragrancia)
                                                                    handleUpdateVariacao(selectedSample.id, v.id, { percentual_fragrancia: val });
                                                            }}
                                                        />
                                                    </div>
                                                    <div className="space-y-1">
                                                        <Label className="text-[10px] text-muted-foreground">Ref. Fragrância</Label>
                                                        <Input
                                                            defaultValue={v.referencia_fragrancia || ""}
                                                            className="h-8 text-xs"
                                                            onBlur={(e) => {
                                                                if (e.target.value !== (v.referencia_fragrancia || ""))
                                                                    handleUpdateVariacao(selectedSample.id, v.id, { referencia_fragrancia: e.target.value });
                                                            }}
                                                        />
                                                    </div>
                                                    <div className="space-y-1">
                                                        <Label className="text-[10px] text-muted-foreground">Custo Frag. (R$/kg)</Label>
                                                        <Input
                                                            type="number" step="0.01"
                                                            defaultValue={v.custo_fragrancia ?? ""}
                                                            className="h-8 text-xs"
                                                            onBlur={(e) => {
                                                                const val = e.target.value === "" ? null : parseFloat(e.target.value);
                                                                if (val !== v.custo_fragrancia)
                                                                    handleUpdateVariacao(selectedSample.id, v.id, { custo_fragrancia: val });
                                                            }}
                                                        />
                                                    </div>
                                                    <div className="space-y-1 col-span-2">
                                                        <Label className="text-[10px] text-muted-foreground">Observações</Label>
                                                        <Textarea
                                                            defaultValue={v.observacoes_especificas || ""}
                                                            rows={2}
                                                            className="text-xs"
                                                            onBlur={(e) => {
                                                                if (e.target.value !== (v.observacoes_especificas || ""))
                                                                    handleUpdateVariacao(selectedSample.id, v.id, { observacoes_especificas: e.target.value });
                                                            }}
                                                        />
                                                    </div>
                                                </div>
                                            </div>
                                        ))}
                                        {(!selectedSample?.variacoes || selectedSample.variacoes.length === 0) && (
                                            <p className="text-sm text-muted-foreground italic">Nenhuma variação (modelo antigo).</p>
                                        )}

                                        <Separator className="my-4" />
                                        <Button
                                            variant="outline"
                                            className="w-full text-destructive hover:text-destructive border-destructive/30"
                                            onClick={handleDeleteSample}
                                            data-testid="btn-delete-sample"
                                        >
                                            <Trash2 className="h-4 w-4 mr-2" /> Excluir Amostra Inteira
                                        </Button>
                                    </div>
                                </TabsContent>

                                <TabsContent value="info" className="flex-1 min-h-0 overflow-y-auto px-6 pb-6 mt-3">
                                    <div className="space-y-4">
                                        <div className="space-y-2">
                                            <Label className="text-xs">Observação Técnica</Label>
                                            <Textarea defaultValue={selectedSample.observacao_tecnica} rows={3}
                                                onBlur={(e) => { if (e.target.value !== selectedSample.observacao_tecnica) handleUpdateSample(selectedSample.id, { observacao_tecnica: e.target.value }); }} />
                                        </div>
                                        <div className="space-y-2">
                                            <Label className="text-xs">Data de Envio</Label>
                                            <Input type="date" defaultValue={selectedSample.data_envio || ""}
                                                onBlur={(e) => handleUpdateSample(selectedSample.id, { data_envio: e.target.value })} />
                                        </div>
                                        <div className="space-y-2">
                                            <Label className="text-xs">Feedback do Cliente</Label>
                                            <Textarea defaultValue={selectedSample.feedback_cliente} rows={3}
                                                onBlur={(e) => { if (e.target.value !== selectedSample.feedback_cliente) handleUpdateSample(selectedSample.id, { feedback_cliente: e.target.value }); }} />
                                        </div>
                                    </div>
                                </TabsContent>

                                <TabsContent value="retrabalhos" className="flex-1 min-h-0 overflow-y-auto px-6 pb-6 mt-3">
                                    <div className="space-y-3">
                                        {(selectedSample.historico_retrabalhos || []).length === 0 && (
                                            <p className="text-sm text-muted-foreground">Nenhum retrabalho registrado.</p>
                                        )}
                                        {(selectedSample.historico_retrabalhos || []).slice().reverse().map((r, idx) => (
                                            <div key={idx} className="border border-border rounded-lg p-3 bg-amber-50/50 dark:bg-amber-950/20">
                                                <div className="flex items-center gap-2 mb-1">
                                                    <AlertTriangle className="h-3.5 w-3.5 text-amber-500" />
                                                    <span className="text-xs font-semibold uppercase tracking-wider text-amber-600 dark:text-amber-400">
                                                        {r.origem === "externa" ? "Externa" : "Interna"}
                                                    </span>
                                                    <span className="text-xs text-muted-foreground ml-auto mono-num">
                                                        {new Date(r.data).toLocaleDateString("pt-BR")}
                                                    </span>
                                                </div>
                                                <p className="text-sm">{r.motivo}</p>
                                            </div>
                                        ))}
                                    </div>
                                </TabsContent>

                                <TabsContent value="timeline" className="flex-1 min-h-0 overflow-y-auto px-6 pb-6 mt-3">
                                    <div className="space-y-3">
                                        {(selectedSample.historico_movimentacoes || []).slice().reverse().map((mov, idx) => (
                                            <div key={idx} className="flex gap-3 items-start">
                                                <div className="mt-1 w-2 h-2 rounded-full bg-primary shrink-0" />
                                                <div>
                                                    <p className="text-sm">
                                                        <span className="font-medium">{STAGE_LABELS[mov.de] || mov.de}</span>
                                                        <ChevronRight className="h-3 w-3 inline mx-1" />
                                                        <span className="font-medium">{STAGE_LABELS[mov.para] || mov.para}</span>
                                                    </p>
                                                    <p className="text-xs text-muted-foreground">
                                                        {mov.usuario} · {new Date(mov.data).toLocaleString("pt-BR")}
                                                    </p>
                                                </div>
                                            </div>
                                        ))}
                                        {(!selectedSample.historico_movimentacoes || selectedSample.historico_movimentacoes.length === 0) && (
                                            <p className="text-sm text-muted-foreground">Nenhuma movimentação.</p>
                                        )}
                                    </div>
                                </TabsContent>
                            </Tabs>
                        </>
                    )}
                </SheetContent>
            </Sheet>

            {/* Reason Modal (Retrabalho / Reprovada) */}
            <Dialog open={showReasonModal} onOpenChange={(v) => { if (!v) { setShowReasonModal(false); setPendingMove(null); setFeedbackText(""); setReworkDirections(""); } }}>
                <DialogContent className="max-w-md">
                    <DialogHeader>
                        <DialogTitle className="font-heading flex items-center gap-2">
                            <AlertTriangle className={`h-5 w-5 ${pendingMove?.stage === "reprovada" ? "text-red-500" : "text-amber-500"}`} />
                            {pendingMove?.stage === "reprovada" ? "Reprovar Amostra" : "Retrabalho"}
                        </DialogTitle>
                    </DialogHeader>
                    <div className="space-y-3">
                        <div>
                            <Label>Motivo *</Label>
                            <Textarea value={reason} onChange={(e) => setReason(e.target.value)}
                                placeholder="Descreva o motivo..." rows={3} />
                        </div>
                        {pendingMove?.stage === "retrabalho" && (
                            <div>
                                <Label>Origem</Label>
                                <Select value={reasonOrigin} onValueChange={setReasonOrigin}>
                                    <SelectTrigger><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="interna">Interna (P&D)</SelectItem>
                                        <SelectItem value="externa">Externa (Cliente)</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                        )}
                        {pendingMove?.stage === "retrabalho" && (
                            <>
                                <div>
                                    <Label>Feedback do Cliente *</Label>
                                    <Textarea value={feedbackText} onChange={(e) => setFeedbackText(e.target.value)}
                                        placeholder="O que o cliente aprovou ou rejeitou?" rows={3} />
                                </div>
                                <div>
                                    <Label>DireÃ§Ãµes para Retrabalho *</Label>
                                    <Textarea value={reworkDirections} onChange={(e) => setReworkDirections(e.target.value)}
                                        placeholder="Ex: aumentar viscosidade, trocar fragrÃ¢ncia..." rows={3} />
                                </div>
                            </>
                        )}
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => { setShowReasonModal(false); setPendingMove(null); setFeedbackText(""); setReworkDirections(""); }}>Cancelar</Button>
                        <Button variant={pendingMove?.stage === "reprovada" ? "destructive" : "default"}
                            onClick={confirmReason} disabled={!reason.trim() || (pendingMove?.stage === "retrabalho" && (!feedbackText.trim() || !reworkDirections.trim()))}>
                            Confirmar
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Add Variações Modal */}
            <Dialog open={showAddVariacoes} onOpenChange={setShowAddVariacoes}>
                <DialogContent className="max-w-2xl max-h-[85vh] overflow-hidden flex flex-col">
                    <DialogHeader>
                        <DialogTitle className="font-heading flex items-center gap-2">
                            <Plus className="h-5 w-5 text-primary" />
                            Adicionar Variações — Amostra #{selectedSample?.numero_amostra}
                        </DialogTitle>
                    </DialogHeader>
                    <div className="flex-1 overflow-y-auto space-y-3 p-1">
                        {newVariacoes.map((v, idx) => {
                            const existingCount = selectedSample?.variacoes?.length || 0;
                            const nextLetter = String.fromCharCode(65 + existingCount + idx);
                            return (
                                <div key={idx} className="border border-border rounded-lg p-3 space-y-3 bg-muted/20">
                                    <div className="flex items-center justify-between">
                                        <h4 className="text-sm font-semibold">
                                            Variação {selectedSample?.numero_amostra}/{nextLetter}
                                        </h4>
                                        {newVariacoes.length > 1 && (
                                            <Button
                                                variant="ghost" size="icon" className="h-7 w-7"
                                                onClick={() => setNewVariacoes(newVariacoes.filter((_, i) => i !== idx))}
                                            >
                                                <X className="h-4 w-4" />
                                            </Button>
                                        )}
                                    </div>
                                    <div className="grid grid-cols-2 gap-3">
                                        <div className="col-span-2 space-y-1">
                                            <Label className="text-xs">Descrição da Aplicação *</Label>
                                            <Input
                                                value={v.descricao_aplicacao}
                                                onChange={(e) => {
                                                    const list = [...newVariacoes];
                                                    list[idx].descricao_aplicacao = e.target.value;
                                                    setNewVariacoes(list);
                                                }}
                                                placeholder="Ex: Shampoo masculino amadeirado"
                                            />
                                        </div>
                                        <div className="space-y-1">
                                            <Label className="text-xs">% Fragrância</Label>
                                            <Input
                                                type="number" step="0.01"
                                                value={v.percentual_fragrancia}
                                                onChange={(e) => {
                                                    const list = [...newVariacoes];
                                                    list[idx].percentual_fragrancia = e.target.value;
                                                    setNewVariacoes(list);
                                                }}
                                            />
                                        </div>
                                        <div className="space-y-1">
                                            <Label className="text-xs">Referência Fragrância</Label>
                                            <Input
                                                value={v.referencia_fragrancia}
                                                onChange={(e) => {
                                                    const list = [...newVariacoes];
                                                    list[idx].referencia_fragrancia = e.target.value;
                                                    setNewVariacoes(list);
                                                }}
                                            />
                                        </div>
                                        <div className="space-y-1">
                                            <Label className="text-xs">Custo Fragrância (R$/kg)</Label>
                                            <Input
                                                type="number" step="0.01"
                                                value={v.custo_fragrancia}
                                                onChange={(e) => {
                                                    const list = [...newVariacoes];
                                                    list[idx].custo_fragrancia = e.target.value;
                                                    setNewVariacoes(list);
                                                }}
                                            />
                                        </div>
                                        <div className="col-span-2 space-y-1">
                                            <Label className="text-xs">Observações Específicas</Label>
                                            <Textarea
                                                rows={2}
                                                value={v.observacoes_especificas}
                                                onChange={(e) => {
                                                    const list = [...newVariacoes];
                                                    list[idx].observacoes_especificas = e.target.value;
                                                    setNewVariacoes(list);
                                                }}
                                            />
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                        <Button
                            variant="outline" size="sm" className="w-full"
                            onClick={() => setNewVariacoes([...newVariacoes, {
                                descricao_aplicacao: "",
                                percentual_fragrancia: "",
                                referencia_fragrancia: "",
                                custo_fragrancia: "",
                                observacoes_especificas: ""
                            }])}
                        >
                            <Plus className="h-4 w-4 mr-1" /> Adicionar outra variação
                        </Button>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setShowAddVariacoes(false)}>Cancelar</Button>
                        <Button onClick={handleAddVariacoesSubmit} data-testid="btn-submit-add-variacoes">
                            Adicionar {newVariacoes.length} variação(ões)
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
