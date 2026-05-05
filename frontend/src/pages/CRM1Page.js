import { useState, useEffect, useCallback, useMemo } from "react";
import api from "@/lib/api";
import { DragDropContext, Droppable, Draggable } from "@hello-pangea/dnd";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter
} from "@/components/ui/dialog";
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from "@/components/ui/select";
import { Plus, GripVertical, User, Trash2, Search, ChevronRight, AlertTriangle, Tag } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

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
    { id: "prospeccao", label: "Prospecção", color: "bg-blue-500" },
    { id: "qualificado", label: "Qualificado", color: "bg-cyan-500" },
    { id: "projeto_em_discussao", label: "Projeto em Discussão", color: "bg-violet-500" },
    { id: "negociacao", label: "Negociação", color: "bg-amber-500" },
    { id: "cliente_fechado", label: "Cliente Fechado", color: "bg-emerald-500" },
    { id: "cliente_perdido", label: "Cliente Perdido", color: "bg-red-500" },
];

const CANAL_OPTIONS = [
    { value: "indicacao", label: "Indicação" },
    { value: "linkedin", label: "LinkedIn" },
    { value: "feira", label: "Feira" },
    { value: "prospeccao_ativa", label: "Prospecção Ativa" },
    { value: "inbound", label: "Inbound" },
];

const CATEGORIA_OPTIONS = [
    { value: "perfume", label: "Perfume" },
    { value: "hidratante", label: "Hidratante" },
    { value: "shampoo", label: "Shampoo" },
    { value: "protetor_solar", label: "Protetor Solar" },
    { value: "body_splash", label: "Body Splash" },
    { value: "skin_care", label: "Skin Care" },
    { value: "outro", label: "Outro" },
];

const ORIGEM_OPTIONS = [
    { value: "cliente_pediu", label: "Cliente Pediu" },
    { value: "nos_provocamos", label: "Nós Provocamos" },
];

const LOSS_REASON_OPTIONS = [
    { value: "preco", label: "Preco" },
    { value: "prazo", label: "Prazo" },
    { value: "qualidade", label: "Qualidade" },
    { value: "concorrencia", label: "Concorrencia" },
    { value: "projeto_cancelado", label: "Projeto Cancelado" },
    { value: "sem_retorno", label: "Sem Retorno" },
    { value: "outro", label: "Outro" },
];

const VOLUME_OPTIONS = [
    { value: "menos_1k", label: "< 1.000 un" },
    { value: "1k_5k", label: "1.000 - 5.000" },
    { value: "5k_20k", label: "5.000 - 20.000" },
    { value: "mais_20k", label: "> 20.000" },
];

const STAGE_ORDER = ["prospeccao", "qualificado", "projeto_em_discussao", "negociacao", "cliente_fechado", "cliente_perdido"];

const CANAL_GROUP_LABELS = {
    prospeccao_ativa_digital: "Prospeccao Ativa - Digital",
    prospeccao_ativa_presencial: "Prospeccao Ativa - Presencial",
    indicacao: "Indicacao",
    inbound_digital: "Inbound - Digital",
    inbound_conteudo: "Inbound - Conteudo",
    relacionamento_existente: "Relacionamento Existente",
    outros: "Outros",
};

const EMPTY_ADDITIONAL_CONTACT = { nome: "", cargo: "", whatsapp: "", email: "" };

function createEmptyClient(defaultOwner = "") {
    return {
        nome_empresa: "",
        cnpj: "",
        contato_principal: { nome: "", whatsapp: "", email: "" },
        contatos_adicionais: [],
        canal_origem: "",
        categoria_interesse: [],
        origem_lead: "",
        temperatura_lead: "morno",
        responsavel_comercial: defaultOwner,
        segmento: "",
        porte: "",
        regiao: "",
        site: "",
        instagram: "",
        observacoes: "",
    };
}

function createEmptyProject(defaults = {}) {
    return {
        nome_projeto: "",
        categoria: "",
        responsavel_comercial: defaults.responsavel_comercial || "",
        briefing_resumido: "",
        ideia_conceito: "",
        referencia_mercado: "",
        publico_alvo: "",
        posicionamento: "",
        faixa_preco_venda: "",
        volume_estimado_pedido: "",
        tipo_servico: "",
        sensorial_desejado: "",
        restricoes_tecnicas: [],
        claims_desejados: "",
        prazo_desejado_amostra: "",
        observacoes_livres: "",
        ...defaults,
    };
}

function formatSlugLabel(value) {
    if (!value) return "";
    const overrides = {
        ceo: "CEO",
        seo: "SEO",
        dm: "DM",
        pdv: "PDV",
        anvisa: "ANVISA",
        moq: "MOQ",
        bb: "BB",
        cc: "CC",
        ph: "pH",
        fps6: "FPS >= 6",
        edp: "Eau de Parfum",
    };

    return String(value)
        .split("_")
        .map((part) => overrides[part.toLowerCase()] || (part ? part[0].toUpperCase() + part.slice(1) : ""))
        .join(" ");
}

export default function CRM1Page() {
    const { user } = useAuth();
    const [clients, setClients] = useState([]);
    const [loading, setLoading] = useState(true);
    const [search, setSearch] = useState("");
    const [selectedClient, setSelectedClient] = useState(null);
    const [showNewClient, setShowNewClient] = useState(false);
    const [showBatchProjects, setShowBatchProjects] = useState(false);
    const [showLossReason, setShowLossReason] = useState(false);
    const [pendingMove, setPendingMove] = useState(null);
    const [pendingProjectMove, setPendingProjectMove] = useState(null);
    const [batchClientId, setBatchClientId] = useState(null);
    const [crmConstants, setCrmConstants] = useState(null);
    const [crmUsers, setCrmUsers] = useState([]);

    const [newClient, setNewClient] = useState(createEmptyClient());

    const [lossReason, setLossReason] = useState("");
    const [batchProjects, setBatchProjects] = useState([createEmptyProject()]);

    const loadClients = useCallback(async () => {
        try {
            const params = search ? { search } : {};
            const { data } = await api.get("/crm/clients", { params });
            setClients(data);
        } catch (e) {
            console.error("Failed to load clients", e);
        } finally {
            setLoading(false);
        }
    }, [search]);

    useEffect(() => { loadClients(); }, [loadClients]);

    const loadFormData = useCallback(async () => {
        try {
            const [{ data: constants }, { data: users }] = await Promise.all([
                api.get("/crm/constants"),
                api.get("/crm/users-list"),
            ]);
            setCrmConstants(constants);
            setCrmUsers(users || []);
        } catch (e) {
            console.error("Failed to load CRM metadata", e);
        }
    }, []);

    useEffect(() => { loadFormData(); }, [loadFormData]);

    useEffect(() => {
        setNewClient((current) => (
            current.responsavel_comercial || !user?.id
                ? current
                : { ...current, responsavel_comercial: user.id }
        ));
    }, [user]);

    const categoryGroups = useMemo(() => crmConstants?.categoria_interesse || {}, [crmConstants]);
    const channelGroups = useMemo(() => crmConstants?.canal_origem_grupos || {}, [crmConstants]);
    const effectiveCategoryGroups = useMemo(
        () => (Object.keys(categoryGroups).length ? categoryGroups : { categorias: CATEGORIA_OPTIONS.map((option) => option.value) }),
        [categoryGroups]
    );
    const effectiveChannelGroups = useMemo(
        () => (Object.keys(channelGroups).length ? channelGroups : { outros: CANAL_OPTIONS.map((option) => option.value) }),
        [channelGroups]
    );
    const segmentOptions = crmConstants?.segmento || [];
    const porteOptions = crmConstants?.porte || [];
    const temperatureOptions = crmConstants?.temperatura_lead || ["quente", "morno", "frio"];
    const cargoOptions = crmConstants?.cargo_decisor || [];
    const ufOptions = crmConstants?.ufs || [];
    const projectPositioningOptions = crmConstants?.project_posicionamento || [];
    const projectServiceOptions = crmConstants?.project_tipo_servico || [];
    const projectRestrictionOptions = crmConstants?.project_restricoes_tecnicas || [];
    const projectCategoryOptions = useMemo(
        () => (
            Object.keys(effectiveCategoryGroups).length
                ? Object.entries(effectiveCategoryGroups).flatMap(([group, values]) =>
                    values.map((value) => ({ value, group, label: formatSlugLabel(value) }))
                )
                : CATEGORIA_OPTIONS.map((option) => ({ ...option, group: "fallback" }))
        ),
        [effectiveCategoryGroups]
    );
    const createProjectDraftForClient = useCallback((client) => createEmptyProject({
        categoria: client?.categoria_interesse?.[0] || "",
        responsavel_comercial: client?.responsavel_comercial || user?.id || "",
    }), [user]);
    const isNewClientValid = Boolean(
        newClient.nome_empresa.trim()
        && newClient.cnpj.trim()
        && newClient.contato_principal.nome.trim()
        && newClient.contato_principal.whatsapp.trim()
        && newClient.canal_origem
        && newClient.categoria_interesse.length
        && newClient.temperatura_lead
        && newClient.responsavel_comercial
        && newClient.segmento
    );

    const clientsByStage = STAGES.reduce((acc, stage) => {
        acc[stage.id] = clients.filter(c => c.stage === stage.id);
        return acc;
    }, {});

    const openProjectBatchModal = useCallback((client, shouldMoveClient = false) => {
        if (!client) return;
        setPendingProjectMove(shouldMoveClient ? { clientId: client.id, stage: "projeto_em_discussao" } : null);
        setBatchClientId(client.id);
        setBatchProjects([createProjectDraftForClient(client)]);
        setShowBatchProjects(true);
    }, [createProjectDraftForClient]);

    const handleDragEnd = async (result) => {
        if (!result.destination) return;
        const { draggableId, source, destination } = result;
        if (source.droppableId === destination.droppableId) return;

        const newStage = destination.droppableId;
        const client = clients.find(c => c.id === draggableId);
        if (!client) return;

        // Handle cliente_perdido — requires motivo
        if (newStage === "cliente_perdido") {
            setPendingMove({ clientId: draggableId, stage: newStage });
            setLossReason("");
            setShowLossReason(true);
            return;
        }

        if (newStage === "projeto_em_discussao") {
            openProjectBatchModal(client, true);
            return;
        }

        try {
            const { data } = await api.put(`/crm/clients/${draggableId}/move`, { stage: newStage });
            toast.success(`Cliente movido para ${data.to_stage}`);

            loadClients();
        } catch (e) {
            const msg = e.response?.data?.detail || "Erro ao mover cliente";
            toast.error(msg);
        }
    };

    const confirmLoss = async () => {
        if (!pendingMove || !lossReason) return;
        try {
            const { data } = await api.put(`/crm/clients/${pendingMove.clientId}/move`, {
                stage: pendingMove.stage, motivo_perda: lossReason,
            });
            toast.success(`Cliente movido para ${data.to_stage}`);
            setShowLossReason(false);
            setPendingMove(null);
            loadClients();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Erro");
        }
    };

    const handleCreateClient = async () => {
        if (!isNewClientValid) return;
        try {
            await api.post("/crm/clients", newClient);
            toast.success("Cliente criado!");
            setShowNewClient(false);
            setNewClient(createEmptyClient(user?.id || ""));
            loadClients();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Erro ao criar cliente");
        }
    };

    const handleBatchProjectSubmit = async () => {
        const valid = batchProjects.filter((project) => (
            project.nome_projeto.trim()
            && project.categoria
            && project.responsavel_comercial
            && project.ideia_conceito.trim()
            && project.posicionamento
            && String(project.volume_estimado_pedido || "").trim()
            && project.tipo_servico
            && project.prazo_desejado_amostra
        ));
        if (valid.length === 0 || !batchClientId) {
            toast.error("Preencha os campos obrigatÃ³rios do prÃ©-briefing em pelo menos um projeto.");
            return;
        }
        try {
            const { data } = await api.post("/crm/projects/batch", {
                cliente_id: batchClientId,
                projects: valid.map((project) => ({
                    ...project,
                    faixa_preco_venda: project.faixa_preco_venda ? parseFloat(project.faixa_preco_venda) : null,
                    volume_estimado_pedido: project.volume_estimado_pedido ? parseInt(project.volume_estimado_pedido, 10) : null,
                })),
            });
            if (pendingProjectMove?.clientId === batchClientId) {
                await api.put(`/crm/clients/${batchClientId}/move`, { stage: pendingProjectMove.stage });
            }
            toast.success(`${data.count} projeto(s) criado(s)!`);
            setShowBatchProjects(false);
            setPendingProjectMove(null);
            setBatchClientId(null);
            setBatchProjects([createEmptyProject({ responsavel_comercial: user?.id || "" })]);
            loadClients();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Erro ao criar projetos");
        }
    };

    const toggleCategoria = (cat) => {
        const current = newClient.categoria_interesse || [];
        if (current.includes(cat)) {
            setNewClient({ ...newClient, categoria_interesse: current.filter(c => c !== cat) });
        } else {
            setNewClient({ ...newClient, categoria_interesse: [...current, cat] });
        }
    };

    const updateMainContact = (field, value) => {
        setNewClient((current) => ({
            ...current,
            contato_principal: { ...current.contato_principal, [field]: value },
        }));
    };

    const addAdditionalContact = () => {
        setNewClient((current) => ({
            ...current,
            contatos_adicionais: [...(current.contatos_adicionais || []), { ...EMPTY_ADDITIONAL_CONTACT }],
        }));
    };

    const updateAdditionalContact = (index, field, value) => {
        setNewClient((current) => ({
            ...current,
            contatos_adicionais: current.contatos_adicionais.map((item, itemIndex) => (
                itemIndex === index ? { ...item, [field]: value } : item
            )),
        }));
    };

    const removeAdditionalContact = (index) => {
        setNewClient((current) => ({
            ...current,
            contatos_adicionais: current.contatos_adicionais.filter((_, itemIndex) => itemIndex !== index),
        }));
    };

    if (loading) return (
        <div className="p-8 page-enter">
            <div className="animate-pulse space-y-4">
                <div className="h-8 w-64 bg-muted rounded" />
                <div className="flex gap-4">{[1,2,3,4,5,6].map(i => <div key={i} className="h-96 w-72 bg-muted rounded-lg" />)}</div>
            </div>
        </div>
    );

    return (
        <div className="p-6 page-enter" data-testid="crm1-page">
            <CRMSubNav active="clients" />
            <div className="flex items-center justify-between mb-6">
                <div>
                    <h1 className="text-3xl font-heading font-semibold tracking-tight">Pipeline Comercial</h1>
                    <p className="text-sm text-muted-foreground mt-1">
                        {clients.length} clientes no pipeline
                    </p>
                </div>
                <div className="flex items-center gap-3">
                    <div className="relative">
                        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                        <Input
                            placeholder="Buscar empresa..."
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            className="pl-9 w-64"
                        />
                    </div>
                    <Button onClick={() => { setNewClient(createEmptyClient(user?.id || "")); setShowNewClient(true); }} data-testid="new-client-btn">
                        <Plus className="h-4 w-4 mr-2" /> Novo Cliente
                    </Button>
                </div>
            </div>

            <DragDropContext onDragEnd={handleDragEnd}>
                <div className="kanban-board" data-testid="crm1-kanban">
                    {STAGES.map((stage) => (
                        <Droppable droppableId={stage.id} key={stage.id}>
                            {(provided, snapshot) => (
                                <div
                                    ref={provided.innerRef}
                                    {...provided.droppableProps}
                                    className={`kanban-column rounded-lg ${snapshot.isDraggingOver ? "bg-accent/50" : "bg-muted/30"}`}
                                    data-testid={`crm1-stage-${stage.id}`}
                                >
                                    <div className="p-3 border-b border-border">
                                        <div className="flex items-center gap-2">
                                            <div className={`w-2 h-2 rounded-full ${stage.color}`} />
                                            <h3 className="font-heading font-medium text-sm truncate">{stage.label}</h3>
                                            <span className="text-xs text-muted-foreground mono-num ml-auto">
                                                {(clientsByStage[stage.id] || []).length}
                                            </span>
                                        </div>
                                    </div>
                                    <div className="p-2 space-y-2 min-h-[200px]">
                                        {(clientsByStage[stage.id] || []).map((client, index) => (
                                            <Draggable draggableId={client.id} index={index} key={client.id}>
                                                {(provided, snapshot) => (
                                                    <div
                                                        ref={provided.innerRef}
                                                        {...provided.draggableProps}
                                                        className={`bg-card border border-border rounded-md p-3 cursor-pointer transition-transform duration-150 ${
                                                            snapshot.isDragging ? "kanban-card-dragging" : "hover:-translate-y-0.5 hover:shadow-sm"
                                                        }`}
                                                        onClick={() => setSelectedClient(client)}
                                                    >
                                                        <div className="flex items-start justify-between gap-2">
                                                            <div className="flex-1 min-w-0">
                                                                <p className="font-body font-medium text-sm truncate">{client.nome_empresa}</p>
                                                                {client.contato_principal?.nome && (
                                                                    <p className="text-xs text-muted-foreground flex items-center gap-1 mt-1">
                                                                        <User className="h-3 w-3" />{client.contato_principal.nome}
                                                                    </p>
                                                                )}
                                                            </div>
                                                            <div {...provided.dragHandleProps} className="shrink-0">
                                                                <GripVertical className="h-4 w-4 text-muted-foreground/50" />
                                                            </div>
                                                        </div>
                                                        <div className="mt-2 flex flex-wrap gap-1">
                                                            {client.temperatura_lead && (
                                                                <span className="inline-block px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-[0.08em] bg-slate-100 text-slate-700 dark:bg-slate-900 dark:text-slate-300">
                                                                    {formatSlugLabel(client.temperatura_lead)}
                                                                </span>
                                                            )}
                                                            {client.origem_lead && (
                                                                <span className="inline-block px-1.5 py-0.5 rounded text-[10px] bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300">
                                                                    {client.origem_lead}
                                                                </span>
                                                            )}
                                                            {(client.categoria_interesse || []).slice(0, 2).map(cat => (
                                                                <span key={cat} className="inline-block px-1.5 py-0.5 rounded text-[10px] bg-muted text-muted-foreground">
                                                                    {formatSlugLabel(cat)}
                                                                </span>
                                                            ))}
                                                        </div>
                                                        <div className="mt-1.5 text-[10px] text-muted-foreground mono-num">
                                                            {new Date(client.created_at).toLocaleDateString("pt-BR")}
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

            {/* Client Detail Sheet */}
            <ClientDetailSheet
                client={selectedClient}
                constants={crmConstants}
                users={crmUsers}
                onCreateProject={(client) => openProjectBatchModal(client, false)}
                onClose={() => { setSelectedClient(null); loadClients(); }}
            />

            {/* New Client Dialog */}
            <Dialog open={showNewClient} onOpenChange={setShowNewClient}>
                <DialogContent className="max-w-lg max-h-[85vh] flex flex-col p-0 overflow-hidden">
                    <DialogHeader className="p-6 pb-2">
                        <DialogTitle className="font-heading">Novo Cliente</DialogTitle>
                    </DialogHeader>
                    <div className="flex-1 min-h-0 overflow-y-auto px-6 pb-2">
                        <div className="space-y-5">
                            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                                <div className="space-y-2 md:col-span-2">
                                    <Label>Empresa *</Label>
                                    <Input
                                        value={newClient.nome_empresa}
                                        onChange={(e) => setNewClient({ ...newClient, nome_empresa: e.target.value })}
                                        placeholder="Nome da empresa"
                                    />
                                </div>
                                <div className="space-y-2">
                                    <Label>CNPJ *</Label>
                                    <Input
                                        value={newClient.cnpj}
                                        onChange={(e) => setNewClient({ ...newClient, cnpj: e.target.value })}
                                        placeholder="00.000.000/0000-00"
                                    />
                                </div>
                                <div className="space-y-2">
                                    <Label>Temperatura *</Label>
                                    <Select value={newClient.temperatura_lead} onValueChange={(v) => setNewClient({ ...newClient, temperatura_lead: v })}>
                                        <SelectTrigger><SelectValue placeholder="Selecionar" /></SelectTrigger>
                                        <SelectContent>
                                            {temperatureOptions.map((option) => (
                                                <SelectItem key={option} value={option}>{formatSlugLabel(option)}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>
                            </div>

                            <div className="space-y-3">
                                <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Contato Principal</h4>
                                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                                    <div className="space-y-2">
                                        <Label>Nome *</Label>
                                        <Input placeholder="Nome do contato" value={newClient.contato_principal.nome} onChange={(e) => updateMainContact("nome", e.target.value)} />
                                    </div>
                                    <div className="space-y-2">
                                        <Label>WhatsApp *</Label>
                                        <Input placeholder="+55 com DDD" value={newClient.contato_principal.whatsapp} onChange={(e) => updateMainContact("whatsapp", e.target.value)} />
                                    </div>
                                    <div className="space-y-2 md:col-span-2">
                                        <Label>E-mail</Label>
                                        <Input placeholder="contato@empresa.com" value={newClient.contato_principal.email} onChange={(e) => updateMainContact("email", e.target.value)} />
                                    </div>
                                </div>
                            </div>

                            <div className="space-y-3">
                                <div className="flex items-center justify-between">
                                    <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Contatos Adicionais</h4>
                                    <Button type="button" variant="outline" size="sm" onClick={addAdditionalContact}>
                                        <Plus className="h-3.5 w-3.5 mr-1" /> Adicionar
                                    </Button>
                                </div>
                                {(newClient.contatos_adicionais || []).map((contact, index) => (
                                    <div key={index} className="rounded-lg border border-border p-3 space-y-3">
                                        <div className="flex items-center justify-between">
                                            <span className="text-xs font-medium text-muted-foreground">Contato {index + 1}</span>
                                            <Button type="button" variant="ghost" size="sm" onClick={() => removeAdditionalContact(index)}>
                                                <Trash2 className="h-3.5 w-3.5 text-red-500" />
                                            </Button>
                                        </div>
                                        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                                            <Input placeholder="Nome" value={contact.nome} onChange={(e) => updateAdditionalContact(index, "nome", e.target.value)} />
                                            <Select value={contact.cargo || ""} onValueChange={(v) => updateAdditionalContact(index, "cargo", v)}>
                                                <SelectTrigger><SelectValue placeholder="Cargo" /></SelectTrigger>
                                                <SelectContent>
                                                    {cargoOptions.map((option) => (
                                                        <SelectItem key={option} value={option}>{formatSlugLabel(option)}</SelectItem>
                                                    ))}
                                                </SelectContent>
                                            </Select>
                                            <Input placeholder="WhatsApp" value={contact.whatsapp} onChange={(e) => updateAdditionalContact(index, "whatsapp", e.target.value)} />
                                            <Input placeholder="E-mail" value={contact.email} onChange={(e) => updateAdditionalContact(index, "email", e.target.value)} />
                                        </div>
                                    </div>
                                ))}
                            </div>

                            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                                <div className="space-y-2">
                                    <Label>Canal de Origem *</Label>
                                    <Select value={newClient.canal_origem} onValueChange={(v) => setNewClient({ ...newClient, canal_origem: v })}>
                                        <SelectTrigger><SelectValue placeholder="Selecionar" /></SelectTrigger>
                                        <SelectContent>
                                            {Object.entries(effectiveChannelGroups).map(([group, values]) => (
                                                <div key={group}>
                                                    <div className="px-2 py-1.5 text-xs font-semibold text-muted-foreground">
                                                        {CANAL_GROUP_LABELS[group] || formatSlugLabel(group)}
                                                    </div>
                                                    {values.map((value) => (
                                                        <SelectItem key={value} value={value}>{formatSlugLabel(value)}</SelectItem>
                                                    ))}
                                                </div>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>
                                <div className="space-y-2">
                                    <Label>Responsavel Comercial *</Label>
                                    <Select value={newClient.responsavel_comercial || ""} onValueChange={(v) => setNewClient({ ...newClient, responsavel_comercial: v })}>
                                        <SelectTrigger><SelectValue placeholder="Selecionar" /></SelectTrigger>
                                        <SelectContent>
                                            {crmUsers.map((crmUser) => (
                                                <SelectItem key={crmUser.id} value={crmUser.id}>{crmUser.name}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>
                                <div className="space-y-2">
                                    <Label>Segmento *</Label>
                                    <Select value={newClient.segmento || ""} onValueChange={(v) => setNewClient({ ...newClient, segmento: v })}>
                                        <SelectTrigger><SelectValue placeholder="Selecionar" /></SelectTrigger>
                                        <SelectContent>
                                            {segmentOptions.map((option) => (
                                                <SelectItem key={option} value={option}>{formatSlugLabel(option)}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>
                                <div className="space-y-2">
                                    <Label>Porte</Label>
                                    <Select value={newClient.porte || ""} onValueChange={(v) => setNewClient({ ...newClient, porte: v })}>
                                        <SelectTrigger><SelectValue placeholder="Selecionar" /></SelectTrigger>
                                        <SelectContent>
                                            {porteOptions.map((option) => (
                                                <SelectItem key={option} value={option}>{formatSlugLabel(option)}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>
                                <div className="space-y-2">
                                    <Label>UF</Label>
                                    <Select value={newClient.regiao || ""} onValueChange={(v) => setNewClient({ ...newClient, regiao: v })}>
                                        <SelectTrigger><SelectValue placeholder="Selecionar" /></SelectTrigger>
                                        <SelectContent>
                                            {ufOptions.map((option) => (
                                                <SelectItem key={option} value={option}>{option}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>
                                <div className="space-y-2">
                                    <Label>Site / Instagram</Label>
                                    <Input
                                        placeholder="https://site.com ou @instagram"
                                        value={newClient.site}
                                        onChange={(e) => setNewClient({ ...newClient, site: e.target.value })}
                                    />
                                </div>
                            </div>

                            <div className="space-y-2">
                                <Label>Categorias de Interesse *</Label>
                                <div className="space-y-3 rounded-lg border border-border p-3">
                                    {Object.entries(effectiveCategoryGroups).map(([group, values]) => (
                                        <div key={group} className="space-y-2">
                                            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                                                {formatSlugLabel(group)}
                                            </p>
                                            <div className="flex flex-wrap gap-2">
                                                {values.map((value) => (
                                                    <button
                                                        key={value}
                                                        type="button"
                                                        onClick={() => toggleCategoria(value)}
                                                        className={`px-3 py-1 rounded-md text-xs font-medium border transition-colors ${
                                                            (newClient.categoria_interesse || []).includes(value)
                                                                ? "bg-primary text-primary-foreground border-primary"
                                                                : "bg-muted text-muted-foreground border-border hover:bg-accent"
                                                        }`}
                                                    >
                                                        {formatSlugLabel(value)}
                                                    </button>
                                                ))}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>

                            <div className="space-y-2">
                                <Label>Origem do Lead (detalhe)</Label>
                                <Input
                                    value={newClient.origem_lead}
                                    onChange={(e) => setNewClient({ ...newClient, origem_lead: e.target.value })}
                                    placeholder="Ex: Indicacao do cliente Habibi Perfumes"
                                />
                            </div>

                            <div className="space-y-2">
                                <Label>Instagram</Label>
                                <Input
                                    value={newClient.instagram}
                                    onChange={(e) => setNewClient({ ...newClient, instagram: e.target.value })}
                                    placeholder="@cliente"
                                />
                            </div>

                            <div className="space-y-2">
                                <Label>Observacoes</Label>
                                <Textarea
                                    value={newClient.observacoes}
                                    onChange={(e) => setNewClient({ ...newClient, observacoes: e.target.value })}
                                    placeholder="Contexto geral sobre o cliente"
                                    rows={4}
                                />
                            </div>
                        </div>
                    </div>
                    <DialogFooter className="p-6 pt-3 border-t">
                        <Button variant="outline" onClick={() => setShowNewClient(false)}>Cancelar</Button>
                        <Button onClick={handleCreateClient} disabled={!isNewClientValid}>Criar Cliente</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Loss Reason Dialog */}
            <Dialog open={showLossReason} onOpenChange={(v) => { if (!v) { setShowLossReason(false); setPendingMove(null); } }}>
                <DialogContent className="max-w-md">
                    <DialogHeader>
                        <DialogTitle className="font-heading flex items-center gap-2">
                            <AlertTriangle className="h-5 w-5 text-red-500" /> Cliente Perdido
                        </DialogTitle>
                    </DialogHeader>
                    <div className="space-y-3">
                        <Label>Motivo da perda *</Label>
                        <Select value={lossReason} onValueChange={setLossReason}>
                            <SelectTrigger>
                                <SelectValue placeholder="Selecione o motivo" />
                            </SelectTrigger>
                            <SelectContent>
                                {LOSS_REASON_OPTIONS.map((option) => (
                                    <SelectItem key={option.value} value={option.value}>
                                        {option.label}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => { setShowLossReason(false); setPendingMove(null); }}>Cancelar</Button>
                        <Button variant="destructive" onClick={confirmLoss} disabled={!lossReason}>Confirmar Perda</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Batch Project Creation Modal */}
            <Dialog open={showBatchProjects} onOpenChange={(open) => {
                setShowBatchProjects(open);
                if (!open) {
                    setPendingProjectMove(null);
                    setBatchClientId(null);
                    setBatchProjects([createEmptyProject({ responsavel_comercial: user?.id || "" })]);
                }
            }}>
                <DialogContent className="max-w-5xl max-h-[90vh] flex flex-col p-0 overflow-hidden">
                    <DialogHeader className="p-6 pb-2">
                        <DialogTitle className="font-heading">Criar Projetos em Lote</DialogTitle>
                        <p className="text-sm text-muted-foreground">Adicione os projetos que serão desenvolvidos para este cliente.</p>
                    </DialogHeader>
                    <div className="flex-1 min-h-0 overflow-y-auto px-6 pb-2">
                        <div className="space-y-3">
                            {batchProjects.map((proj, idx) => (
                                <div key={idx} className="border border-border rounded-lg p-4 space-y-3 bg-card">
                                    <div className="flex items-center justify-between">
                                        <span className="text-xs font-semibold text-muted-foreground">Projeto {idx + 1}</span>
                                        {batchProjects.length > 1 && (
                                            <Button variant="ghost" size="sm" onClick={() => setBatchProjects(batchProjects.filter((_, i) => i !== idx))}>
                                                <Trash2 className="h-3.5 w-3.5 text-red-500" />
                                            </Button>
                                        )}
                                    </div>
                                    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                                        <div className="space-y-2 md:col-span-2">
                                            <Label>Nome do projeto *</Label>
                                            <Input placeholder="Ex: Habibi / Body Splash 300ml" value={proj.nome_projeto}
                                                onChange={(e) => { const p = [...batchProjects]; p[idx] = { ...p[idx], nome_projeto: e.target.value }; setBatchProjects(p); }} />
                                        </div>
                                        <div className="space-y-2">
                                            <Label>Categoria do produto *</Label>
                                            <Select value={proj.categoria} onValueChange={(v) => { const p = [...batchProjects]; p[idx] = { ...p[idx], categoria: v }; setBatchProjects(p); }}>
                                                <SelectTrigger><SelectValue placeholder="Categoria" /></SelectTrigger>
                                                <SelectContent>
                                                    {projectCategoryOptions.map((option) => (
                                                        <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                                                    ))}
                                                </SelectContent>
                                            </Select>
                                        </div>
                                        <div className="space-y-2">
                                            <Label>ResponsÃ¡vel comercial *</Label>
                                            <Select value={proj.responsavel_comercial} onValueChange={(v) => { const p = [...batchProjects]; p[idx] = { ...p[idx], responsavel_comercial: v }; setBatchProjects(p); }}>
                                                <SelectTrigger><SelectValue placeholder="Selecionar" /></SelectTrigger>
                                                <SelectContent>
                                                    {crmUsers.map((crmUser) => (
                                                        <SelectItem key={crmUser.id} value={crmUser.id}>{crmUser.name}</SelectItem>
                                                    ))}
                                                </SelectContent>
                                            </Select>
                                        </div>
                                        <div className="space-y-2 md:col-span-2">
                                            <Label>Ideia / conceito do produto *</Label>
                                            <Textarea placeholder="Descreva o que o cliente quer desenvolver." value={proj.ideia_conceito} rows={3}
                                                onChange={(e) => { const p = [...batchProjects]; p[idx] = { ...p[idx], ideia_conceito: e.target.value, briefing_resumido: e.target.value }; setBatchProjects(p); }} />
                                        </div>
                                        <div className="space-y-2">
                                            <Label>ReferÃªncia de mercado</Label>
                                            <Input placeholder="Concorrente ou inspiraÃ§Ã£o" value={proj.referencia_mercado}
                                                onChange={(e) => { const p = [...batchProjects]; p[idx] = { ...p[idx], referencia_mercado: e.target.value }; setBatchProjects(p); }} />
                                        </div>
                                        <div className="space-y-2">
                                            <Label>PÃºblico-alvo</Label>
                                            <Input placeholder="A quem o produto se destina" value={proj.publico_alvo}
                                                onChange={(e) => { const p = [...batchProjects]; p[idx] = { ...p[idx], publico_alvo: e.target.value }; setBatchProjects(p); }} />
                                        </div>
                                        <div className="space-y-2">
                                            <Label>Posicionamento *</Label>
                                            <Select value={proj.posicionamento} onValueChange={(v) => { const p = [...batchProjects]; p[idx] = { ...p[idx], posicionamento: v }; setBatchProjects(p); }}>
                                                <SelectTrigger><SelectValue placeholder="Selecionar" /></SelectTrigger>
                                                <SelectContent>
                                                    {projectPositioningOptions.map((option) => (
                                                        <SelectItem key={option} value={option}>{formatSlugLabel(option)}</SelectItem>
                                                    ))}
                                                </SelectContent>
                                            </Select>
                                        </div>
                                        <div className="space-y-2">
                                            <Label>Tipo de serviÃ§o *</Label>
                                            <Select value={proj.tipo_servico} onValueChange={(v) => { const p = [...batchProjects]; p[idx] = { ...p[idx], tipo_servico: v }; setBatchProjects(p); }}>
                                                <SelectTrigger><SelectValue placeholder="Selecionar" /></SelectTrigger>
                                                <SelectContent>
                                                    {projectServiceOptions.map((option) => (
                                                        <SelectItem key={option} value={option}>{formatSlugLabel(option)}</SelectItem>
                                                    ))}
                                                </SelectContent>
                                            </Select>
                                        </div>
                                        <div className="space-y-2">
                                            <Label>Faixa de preÃ§o de venda (R$)</Label>
                                            <Input type="number" value={proj.faixa_preco_venda}
                                                onChange={(e) => { const p = [...batchProjects]; p[idx] = { ...p[idx], faixa_preco_venda: e.target.value }; setBatchProjects(p); }} />
                                        </div>
                                        <div className="space-y-2">
                                            <Label>Volume estimado por pedido *</Label>
                                            <Input type="number" value={proj.volume_estimado_pedido}
                                                onChange={(e) => { const p = [...batchProjects]; p[idx] = { ...p[idx], volume_estimado_pedido: e.target.value }; setBatchProjects(p); }} />
                                        </div>
                                        <div className="space-y-2">
                                            <Label>Prazo desejado para amostra *</Label>
                                            <Input type="date" value={proj.prazo_desejado_amostra}
                                                onChange={(e) => { const p = [...batchProjects]; p[idx] = { ...p[idx], prazo_desejado_amostra: e.target.value }; setBatchProjects(p); }} />
                                        </div>
                                        <div className="space-y-2">
                                            <Label>Sensorial desejado</Label>
                                            <Input placeholder="Textura, cor, fragrÃ¢ncia" value={proj.sensorial_desejado}
                                                onChange={(e) => { const p = [...batchProjects]; p[idx] = { ...p[idx], sensorial_desejado: e.target.value }; setBatchProjects(p); }} />
                                        </div>
                                        <div className="space-y-2 md:col-span-2">
                                            <Label>Claims desejados</Label>
                                            <Textarea value={proj.claims_desejados} rows={2}
                                                onChange={(e) => { const p = [...batchProjects]; p[idx] = { ...p[idx], claims_desejados: e.target.value }; setBatchProjects(p); }} />
                                        </div>
                                        <div className="space-y-2 md:col-span-2">
                                            <Label>RestriÃ§Ãµes tÃ©cnicas</Label>
                                            <div className="flex flex-wrap gap-2">
                                                {projectRestrictionOptions.map((option) => {
                                                    const active = (proj.restricoes_tecnicas || []).includes(option);
                                                    return (
                                                        <button
                                                            key={option}
                                                            type="button"
                                                            className={`px-2.5 py-1 rounded-full text-xs border transition-colors ${active ? "bg-primary text-primary-foreground border-primary" : "border-border text-muted-foreground hover:bg-accent"}`}
                                                            onClick={() => {
                                                                const current = proj.restricoes_tecnicas || [];
                                                                const next = current.includes(option)
                                                                    ? current.filter((item) => item !== option)
                                                                    : [...current, option];
                                                                const p = [...batchProjects];
                                                                p[idx] = { ...p[idx], restricoes_tecnicas: next };
                                                                setBatchProjects(p);
                                                            }}
                                                        >
                                                            {formatSlugLabel(option)}
                                                        </button>
                                                    );
                                                })}
                                            </div>
                                        </div>
                                        <div className="space-y-2 md:col-span-2">
                                            <Label>ObservaÃ§Ãµes livres</Label>
                                            <Textarea value={proj.observacoes_livres} rows={2}
                                                onChange={(e) => { const p = [...batchProjects]; p[idx] = { ...p[idx], observacoes_livres: e.target.value }; setBatchProjects(p); }} />
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                        <Button variant="outline" className="w-full mt-3" onClick={() => setBatchProjects([...batchProjects, createProjectDraftForClient(clients.find((client) => client.id === batchClientId))])}>
                            <Plus className="h-4 w-4 mr-2" /> Adicionar Projeto
                        </Button>
                    </div>
                    <DialogFooter className="p-6 pt-3 border-t">
                        <Button variant="outline" onClick={() => { setShowBatchProjects(false); setPendingProjectMove(null); setBatchClientId(null); setBatchProjects([createEmptyProject({ responsavel_comercial: user?.id || "" })]); }}>Cancelar</Button>
                        <Button onClick={handleBatchProjectSubmit}>
                            Criar {batchProjects.filter((project) => project.nome_projeto.trim()).length} Projeto(s)
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}


// ======= Client Detail Sheet =======
function ClientDetailSheet({ client, onClose, onCreateProject }) {
    const [data, setData] = useState(null);
    const [editing, setEditing] = useState({});
    const [saving, setSaving] = useState(false);
    const [tab, setTab] = useState("info");

    useEffect(() => {
        if (client) {
            setData({ ...client });
            setEditing({});
            setTab("info");
        } else {
            setData(null);
        }
    }, [client]);

    const stageIndex = STAGE_ORDER.indexOf(data?.stage || "prospeccao");

    const handleSave = async () => {
        if (!data) return;
        setSaving(true);
        try {
            const updates = {};
            for (const [k, v] of Object.entries(editing)) {
                if (v !== undefined) updates[k] = v;
            }
            if (Object.keys(updates).length > 0) {
                await api.put(`/crm/clients/${data.id}`, updates);
                toast.success("Cliente atualizado!");
            }
            setEditing({});
        } catch (e) {
            toast.error(e.response?.data?.detail || "Erro ao salvar");
        } finally {
            setSaving(false);
        }
    };

    const val = (field) => editing[field] !== undefined ? editing[field] : (data?.[field] ?? "");
    const setVal = (field, value) => setEditing({ ...editing, [field]: value });

    if (!data) return null;

    return (
        <Sheet open={!!client} onOpenChange={(v) => { if (!v) onClose(); }}>
            <SheetContent className="w-[500px] sm:w-[550px] p-0 flex flex-col" side="right">
                <SheetHeader className="p-6 pb-3">
                    <SheetTitle className="font-heading text-xl">{data.nome_empresa}</SheetTitle>
                    <div className="flex items-center gap-2 mt-1">
                        <Badge variant="outline" className="text-xs">
                            {STAGES.find(s => s.id === data.stage)?.label || data.stage}
                        </Badge>
                        {data.cnpj && <span className="text-xs text-muted-foreground mono-num">{data.cnpj}</span>}
                    </div>
                    {data.stage !== "cliente_perdido" && (
                        <div className="pt-3">
                            <Button variant="outline" size="sm" onClick={() => onCreateProject?.(data)}>
                                <Plus className="h-4 w-4 mr-2" /> Novo Projeto para este Cliente
                            </Button>
                        </div>
                    )}
                </SheetHeader>
                <Separator />
                <Tabs value={tab} onValueChange={setTab} className="flex-1 flex flex-col min-h-0">
                    <TabsList className="mx-6 mt-3">
                        <TabsTrigger value="info">Dados</TabsTrigger>
                        <TabsTrigger value="timeline">Histórico</TabsTrigger>
                    </TabsList>

                    <TabsContent value="info" className="flex-1 min-h-0 overflow-y-auto px-6 pb-6 mt-3">
                        <div className="space-y-5">
                            {/* Prospecção — always visible */}
                            <section>
                                <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">Prospecção</h4>
                                <div className="space-y-3">
                                    <div><Label className="text-xs">Empresa</Label><Input value={val("nome_empresa")} onChange={(e) => setVal("nome_empresa", e.target.value)} /></div>
                                    <div><Label className="text-xs">CNPJ</Label><Input value={val("cnpj")} onChange={(e) => setVal("cnpj", e.target.value)} /></div>
                                    <div><Label className="text-xs">Contato — Nome</Label><Input value={val("contato_principal")?.nome || data.contato_principal?.nome || ""} onChange={(e) => setVal("contato_principal", { ...(data.contato_principal || {}), ...(editing.contato_principal || {}), nome: e.target.value })} /></div>
                                    <div><Label className="text-xs">Contato — WhatsApp</Label><Input value={val("contato_principal")?.whatsapp || data.contato_principal?.whatsapp || ""} onChange={(e) => setVal("contato_principal", { ...(data.contato_principal || {}), ...(editing.contato_principal || {}), whatsapp: e.target.value })} /></div>
                                    <div><Label className="text-xs">Contato — Email</Label><Input value={val("contato_principal")?.email || data.contato_principal?.email || ""} onChange={(e) => setVal("contato_principal", { ...(data.contato_principal || {}), ...(editing.contato_principal || {}), email: e.target.value })} /></div>
                                    <div>
                                        <Label className="text-xs">Canal de Origem</Label>
                                        <Select value={val("canal_origem")} onValueChange={(v) => setVal("canal_origem", v)}>
                                            <SelectTrigger><SelectValue placeholder="Selecionar" /></SelectTrigger>
                                            <SelectContent>{CANAL_OPTIONS.map(o => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}</SelectContent>
                                        </Select>
                                    </div>
                                    <div>
                                        <Label className="text-xs flex items-center gap-1">Origem do Lead <Tag className="h-3 w-3 text-amber-500" /></Label>
                                        <Select value={val("origem_lead")} onValueChange={(v) => setVal("origem_lead", v)}>
                                            <SelectTrigger><SelectValue placeholder="Selecionar" /></SelectTrigger>
                                            <SelectContent>{ORIGEM_OPTIONS.map(o => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}</SelectContent>
                                        </Select>
                                    </div>
                                </div>
                            </section>

                            {/* Qualificado — visible from stage >= qualificado */}
                            {stageIndex >= 1 && (
                                <section>
                                    <Separator className="mb-3" />
                                    <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">Qualificação</h4>
                                    <div className="space-y-3">
                                        <div>
                                            <Label className="text-xs">Tem Marca Própria?</Label>
                                            <div className="flex items-center gap-2 mt-1">
                                                <Switch checked={val("tem_marca_propria") || false} onCheckedChange={(v) => setVal("tem_marca_propria", v)} />
                                                <span className="text-sm">{val("tem_marca_propria") ? "Sim" : "Não"}</span>
                                            </div>
                                        </div>
                                        <div>
                                            <Label className="text-xs">Tem ANVISA?</Label>
                                            <Select value={val("tem_anvisa")} onValueChange={(v) => setVal("tem_anvisa", v)}>
                                                <SelectTrigger><SelectValue placeholder="Selecionar" /></SelectTrigger>
                                                <SelectContent>
                                                    <SelectItem value="sim">Sim</SelectItem>
                                                    <SelectItem value="nao">Não</SelectItem>
                                                    <SelectItem value="depende_de_nos">Depende de Nós</SelectItem>
                                                </SelectContent>
                                            </Select>
                                        </div>
                                        <div>
                                            <Label className="text-xs">Volume Estimado Mensal</Label>
                                            <Select value={val("volume_estimado_mensal")} onValueChange={(v) => setVal("volume_estimado_mensal", v)}>
                                                <SelectTrigger><SelectValue placeholder="Selecionar" /></SelectTrigger>
                                                <SelectContent>{VOLUME_OPTIONS.map(o => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}</SelectContent>
                                            </Select>
                                        </div>
                                        <div><Label className="text-xs">Prazo / Urgência</Label><Input type="date" value={val("prazo_urgencia") || ""} onChange={(e) => setVal("prazo_urgencia", e.target.value)} /></div>
                                    </div>
                                </section>
                            )}

                            {/* Negociação — visible from stage >= negociacao */}
                            {stageIndex >= 3 && (
                                <section>
                                    <Separator className="mb-3" />
                                    <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">Negociação</h4>
                                    <div className="space-y-3">
                                        <div><Label className="text-xs">Valor Estimado do Projeto (R$)</Label><Input type="number" value={val("valor_estimado_projeto") || ""} onChange={(e) => setVal("valor_estimado_projeto", parseFloat(e.target.value) || 0)} /></div>
                                        <div><Label className="text-xs">MOQ Negociado</Label><Input value={val("moq_negociado")} onChange={(e) => setVal("moq_negociado", e.target.value)} /></div>
                                        <div><Label className="text-xs">Condição de Pagamento</Label><Input value={val("condicao_pagamento")} onChange={(e) => setVal("condicao_pagamento", e.target.value)} /></div>
                                        <div><Label className="text-xs">Concorrentes Envolvidos</Label><Input value={(val("concorrentes_envolvidos") || []).join(", ")} onChange={(e) => setVal("concorrentes_envolvidos", e.target.value.split(",").map(s => s.trim()).filter(Boolean))} placeholder="Separados por vírgula" /></div>
                                    </div>
                                </section>
                            )}

                            {/* Fechado — visible from stage >= cliente_fechado */}
                            {stageIndex >= 4 && (
                                <section>
                                    <Separator className="mb-3" />
                                    <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">Fechamento</h4>
                                    <div className="space-y-3">
                                        <div><Label className="text-xs">Data do Pedido</Label><Input type="date" value={val("data_pedido") || ""} onChange={(e) => setVal("data_pedido", e.target.value)} /></div>
                                        <div><Label className="text-xs">Valor do Primeiro Pedido (R$)</Label><Input type="number" value={val("valor_primeiro_pedido") || ""} onChange={(e) => setVal("valor_primeiro_pedido", parseFloat(e.target.value) || 0)} /></div>
                                        <div><Label className="text-xs">Previsão Segundo Pedido</Label><Input type="date" value={val("previsao_segundo_pedido") || ""} onChange={(e) => setVal("previsao_segundo_pedido", e.target.value)} /></div>
                                    </div>
                                </section>
                            )}

                            {/* Perdido */}
                            {data.stage === "cliente_perdido" && data.motivo_perda && (
                                <section>
                                    <Separator className="mb-3" />
                                    <h4 className="text-xs font-semibold text-red-500 uppercase tracking-wider mb-2">Motivo da Perda</h4>
                                    <p className="text-sm bg-red-50 dark:bg-red-950/30 p-3 rounded-md border border-red-200 dark:border-red-800">{data.motivo_perda}</p>
                                </section>
                            )}

                            {Object.keys(editing).length > 0 && (
                                <div className="pt-3">
                                    <Button onClick={handleSave} disabled={saving} className="w-full">
                                        {saving ? "Salvando..." : "Salvar Alterações"}
                                    </Button>
                                </div>
                            )}
                        </div>
                    </TabsContent>

                    <TabsContent value="timeline" className="flex-1 min-h-0 overflow-y-auto px-6 pb-6 mt-3">
                        <div className="space-y-3">
                            {(data.historico_movimentacoes || []).slice().reverse().map((mov, idx) => (
                                <div key={idx} className="flex gap-3 items-start">
                                    <div className="mt-1 w-2 h-2 rounded-full bg-primary shrink-0" />
                                    <div>
                                        <p className="text-sm">
                                            <span className="font-medium">{STAGES.find(s => s.id === mov.de)?.label || mov.de}</span>
                                            <ChevronRight className="h-3 w-3 inline mx-1" />
                                            <span className="font-medium">{STAGES.find(s => s.id === mov.para)?.label || mov.para}</span>
                                        </p>
                                        <p className="text-xs text-muted-foreground">
                                            {mov.usuario} · {new Date(mov.data).toLocaleString("pt-BR")}
                                        </p>
                                    </div>
                                </div>
                            ))}
                            {(!data.historico_movimentacoes || data.historico_movimentacoes.length === 0) && (
                                <p className="text-sm text-muted-foreground">Nenhuma movimentação registrada.</p>
                            )}
                        </div>
                    </TabsContent>
                </Tabs>
            </SheetContent>
        </Sheet>
    );
}
