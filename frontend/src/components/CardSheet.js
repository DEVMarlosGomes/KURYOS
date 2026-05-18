import { useState, useEffect, useRef } from "react";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { BACKEND_URL } from "@/lib/backend";
import { Save, Plus, Trash2, Send, Clock, Package, MessageSquare, FileText, Sparkles, Download, Loader2, Lightbulb, Pencil, X, ShieldCheck, Beaker } from "lucide-react";

const TEMP_CLASSES = { frio: "badge-frio", morno: "badge-morno", quente: "badge-quente" };

export default function CardSheet({ cardId, onClose }) {
    const { user: authUser } = useAuth();
    const canEdit = authUser && (authUser.role === "admin" || authUser.role === "gestor");
    const [details, setDetails] = useState(null);
    const [loading, setLoading] = useState(true);
    const [fieldValues, setFieldValues] = useState({});
    const [cardStatus, setCardStatus] = useState("");
    const [editingProject, setEditingProject] = useState(false);
    const [projectForm, setProjectForm] = useState({});
    const [savingProject, setSavingProject] = useState(false);
    const [newProduct, setNewProduct] = useState({ nome_produto: "", sku: "", quantidade: 1, valor_unitario: 0 });
    const [messageText, setMessageText] = useState("");
    const [aiSummary, setAiSummary] = useState("");
    const [aiLoading, setAiLoading] = useState(false);
    const [suggestions, setSuggestions] = useState([]);
    const [suggestionsLoading, setSuggestionsLoading] = useState(false);
    const [pdfLoading, setPdfLoading] = useState(false);
    const [templates, setTemplates] = useState([]);
    const [showTemplates, setShowTemplates] = useState(false);
    const chatEndRef = useRef(null);

    useEffect(() => {
        if (!cardId) { setDetails(null); return; }
        setLoading(true);
        setAiSummary("");
        setSuggestions([]);
        api.get(`/cards/${cardId}/details`).then(({ data }) => {
            setDetails(data);
            setCardStatus(data.card.status);
            const fv = {};
            data.field_values.forEach(v => { fv[v.field_id] = v.value_json; });
            setFieldValues(fv);
        }).catch(console.error).finally(() => setLoading(false));
        api.get("/whatsapp/templates").then(({ data }) => setTemplates(data)).catch(() => {});
    }, [cardId]);

    useEffect(() => {
        chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [details?.messages]);

    const saveFields = async () => {
        const values = Object.entries(fieldValues).map(([field_id, value_json]) => ({ field_id, value_json }));
        try {
            await api.post(`/cards/${cardId}/field-values`, values);
            toast.success("Campos salvos");
        } catch { toast.error("Erro ao salvar campos"); }
    };

    const startEditingProject = () => {
        const c = details.card;
        setProjectForm({
            nome_cliente: c.nome_cliente || "",
            telefone: c.telefone || "",
            email: c.email || "",
            produto: c.produto || "",
            nome_projeto: c.nome_projeto || "",
            objetivo_projeto: c.objetivo_projeto || "",
            aplicacoes_desenvolver: c.aplicacoes_desenvolver || "",
            ativos_claims: c.ativos_claims || "",
            referencias: c.referencias || "",
            referencias_fotos_url: c.referencias_fotos_url || "",
            orcamento_projeto: c.orcamento_projeto || "",
            textura_esperada: c.textura_esperada || "",
            aplicacao: c.aplicacao || "",
            sensorial: c.sensorial || "",
            ph: c.ph || "",
            outras_observacoes: c.outras_observacoes || "",
        });
        setEditingProject(true);
    };

    const saveProject = async () => {
        setSavingProject(true);
        try {
            await api.put(`/cards/${cardId}`, projectForm);
            setDetails(prev => ({ ...prev, card: { ...prev.card, ...projectForm } }));
            setEditingProject(false);
            toast.success("Dados do projeto salvos!");
        } catch { toast.error("Erro ao salvar"); }
        finally { setSavingProject(false); }
    };

    const updateStatus = async (newStatus) => {
        setCardStatus(newStatus);
        try {
            await api.put(`/cards/${cardId}`, { status: newStatus });
            toast.success("Status atualizado");
        } catch { toast.error("Erro ao atualizar status"); }
    };

    const addProduct = async () => {
        if (!newProduct.nome_produto) return;
        try {
            const { data } = await api.post(`/cards/${cardId}/products`, newProduct);
            setDetails(prev => ({ ...prev, products: [...prev.products, data] }));
            setNewProduct({ nome_produto: "", sku: "", quantidade: 1, valor_unitario: 0 });
            toast.success("Produto adicionado");
        } catch { toast.error("Erro ao adicionar produto"); }
    };

    const removeProduct = async (productId) => {
        try {
            await api.delete(`/card-products/${productId}`);
            setDetails(prev => ({ ...prev, products: prev.products.filter(p => p.id !== productId) }));
            toast.success("Produto removido");
        } catch { toast.error("Erro ao remover produto"); }
    };

    const sendMessage = async () => {
        if (!messageText.trim()) return;
        try {
            const { data } = await api.post(`/cards/${cardId}/messages`, { content: messageText, msg_type: "text" });
            setDetails(prev => ({ ...prev, messages: [...prev.messages, data] }));
            setMessageText("");
        } catch { toast.error("Erro ao enviar mensagem"); }
    };

    const generateSummary = async () => {
        setAiLoading(true);
        try {
            const { data } = await api.post(`/ai/lead-summary/${cardId}`);
            setAiSummary(data.summary);
            toast.success("Resumo gerado com IA");
        } catch (e) {
            toast.error("Erro ao gerar resumo");
        } finally { setAiLoading(false); }
    };

    const generateSuggestions = async () => {
        setSuggestionsLoading(true);
        try {
            const { data } = await api.post(`/ai/whatsapp-suggestions/${cardId}`);
            setSuggestions(data.suggestions || []);
        } catch (e) {
            toast.error("Erro ao gerar sugestoes");
        } finally { setSuggestionsLoading(false); }
    };

    const downloadPdf = async () => {
        setPdfLoading(true);
        try {
            const response = await api.get(`/cards/${cardId}/proposal-pdf`, { responseType: 'blob' });
            const url = window.URL.createObjectURL(new Blob([response.data]));
            const link = document.createElement('a');
            link.href = url;
            link.download = `proposta_${details?.card?.nome_cliente?.replace(/\s/g, '_') || 'lead'}.pdf`;
            document.body.appendChild(link);
            link.click();
            link.remove();
            window.URL.revokeObjectURL(url);
            toast.success("PDF gerado com sucesso");
        } catch { toast.error("Erro ao gerar PDF"); }
        finally { setPdfLoading(false); }
    };

    const handleFileUpload = async (fieldId, file) => {
        if (!file) return;
        const formData = new FormData();
        formData.append("file", file);
        try {
            const { data } = await api.post("/upload", formData, { headers: { "Content-Type": "multipart/form-data" } });
            setFieldValues(prev => ({ ...prev, [fieldId]: JSON.stringify({ fileId: data.id, filename: data.original_filename, size: data.size }) }));
            toast.success(`Arquivo "${data.original_filename}" enviado`);
        } catch (e) {
            toast.error("Erro ao enviar arquivo");
        }
    };

    const renderField = (field) => {
        const val = fieldValues[field.id] || "";
        const onChange = (v) => setFieldValues(prev => ({ ...prev, [field.id]: v }));

        switch (field.type) {
            case "text":
            case "number":
            case "date":
                return <Input type={field.type} value={val} onChange={(e) => onChange(e.target.value)} data-testid={`field-${field.id}`} />;
            case "textarea":
                return <Textarea value={val} onChange={(e) => onChange(e.target.value)} rows={3} data-testid={`field-${field.id}`} />;
            case "select":
                return (
                    <Select value={val} onValueChange={onChange} data-testid={`field-${field.id}`}>
                        <SelectTrigger><SelectValue placeholder="Selecionar..." /></SelectTrigger>
                        <SelectContent>
                            {(field.options || []).map(o => <SelectItem key={o} value={o}>{o}</SelectItem>)}
                        </SelectContent>
                    </Select>
                );
            case "boolean":
                return (
                    <div className="flex items-center gap-2">
                        <Checkbox checked={val === "true"} onCheckedChange={(c) => onChange(c ? "true" : "false")} data-testid={`field-${field.id}`} />
                        <span className="text-sm">{val === "true" ? "Sim" : "Nao"}</span>
                    </div>
                );
            case "file": {
                let fileInfo = null;
                try { fileInfo = val ? JSON.parse(val) : null; } catch {}
                return (
                    <div className="space-y-2">
                        <Input type="file" onChange={(e) => handleFileUpload(field.id, e.target.files?.[0])} data-testid={`field-${field.id}`} />
                        {fileInfo && (
                            <div className="flex items-center gap-2 text-xs text-muted-foreground p-2 bg-muted rounded">
                                <FileText className="h-3.5 w-3.5" />
                                <span className="truncate">{fileInfo.filename}</span>
                                <span className="mono-num shrink-0">({(fileInfo.size / 1024).toFixed(1)}KB)</span>
                            </div>
                        )}
                    </div>
                );
            }
            default:
                return <Input value={val} onChange={(e) => onChange(e.target.value)} />;
        }
    };

    const totalProducts = details?.products?.reduce((sum, p) => sum + (p.valor_total || 0), 0) || 0;

    return (
        <Sheet open={!!cardId} onOpenChange={(open) => { if (!open) onClose(); }}>
            <SheetContent side="right" className="sm:max-w-[680px] w-full p-0 flex flex-col" data-testid="card-sheet">
                {loading ? (
                    <div className="flex items-center justify-center h-full">
                        <div className="animate-spin h-6 w-6 border-2 border-primary border-t-transparent rounded-full" />
                    </div>
                ) : details ? (
                    <>
                        <SheetHeader className="p-6 pb-4">
                            <div className="flex items-start justify-between gap-4">
                                <div>
                                    <SheetTitle className="font-heading text-xl" data-testid="card-sheet-title">
                                        {details.card.nome_cliente}
                                    </SheetTitle>
                                    <SheetDescription className="mt-1">
                                        {details.stage?.name} &middot; Criado em {new Date(details.card.created_at).toLocaleDateString("pt-BR")}
                                    </SheetDescription>
                                </div>
                                <div className="flex items-center gap-2 shrink-0">
                                    <Button variant="outline" size="sm" onClick={generateSummary} disabled={aiLoading} data-testid="ai-summary-btn">
                                        {aiLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
                                        <span className="ml-1.5 text-xs">Resumo IA</span>
                                    </Button>
                                    <Button variant="outline" size="sm" onClick={downloadPdf} disabled={pdfLoading} data-testid="download-pdf-btn">
                                        {pdfLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
                                        <span className="ml-1.5 text-xs">PDF</span>
                                    </Button>
                                    <Select value={cardStatus} onValueChange={updateStatus} data-testid="card-status-select">
                                        <SelectTrigger className={`w-28 h-8 text-xs font-semibold uppercase tracking-wider ${TEMP_CLASSES[cardStatus]}`}>
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
                            {aiSummary && (
                                <div className="mt-3 p-3 rounded-md bg-muted border border-border text-sm leading-relaxed" data-testid="ai-summary-content">
                                    <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground mb-2">
                                        <Sparkles className="h-3 w-3" /> Resumo por IA (Claude Sonnet 4.5)
                                    </div>
                                    {aiSummary.split('\n').map((line, i) => line.trim() ? <p key={i} className="mb-1">{line}</p> : null)}
                                </div>
                            )}
                        </SheetHeader>

                        <Separator />

                        <Tabs defaultValue="details" className="flex-1 flex flex-col min-h-0">
                            <TabsList className="mx-6 mt-4 w-fit" data-testid="card-tabs">
                                <TabsTrigger value="details" className="text-xs"><FileText className="h-3.5 w-3.5 mr-1" /> Detalhes</TabsTrigger>
                                <TabsTrigger value="amostras" className="text-xs"><Beaker className="h-3.5 w-3.5 mr-1" /> Amostras</TabsTrigger>
                                <TabsTrigger value="products" className="text-xs"><Package className="h-3.5 w-3.5 mr-1" /> Produtos</TabsTrigger>
                                <TabsTrigger value="history" className="text-xs"><Clock className="h-3.5 w-3.5 mr-1" /> Timeline</TabsTrigger>
                                <TabsTrigger value="chat" className="text-xs"><MessageSquare className="h-3.5 w-3.5 mr-1" /> WhatsApp</TabsTrigger>
                            </TabsList>

                            <ScrollArea className="flex-1 min-h-0">
                                <TabsContent value="details" className="px-6 pb-6 mt-0">
                                    <div className="space-y-4 mt-4">
                                        {!editingProject ? (
                                            <>
                                                {/* View Mode */}
                                                <div className="flex items-center justify-between">
                                                    <h4 className="font-heading font-medium text-sm">Dados do Cliente</h4>
                                                    {canEdit && (
                                                        <Button variant="ghost" size="sm" onClick={startEditingProject} className="gap-1.5 text-xs h-7">
                                                            <Pencil className="h-3 w-3" /> Editar
                                                        </Button>
                                                    )}
                                                    {!canEdit && (
                                                        <Badge variant="outline" className="text-[10px] gap-1"><ShieldCheck className="h-3 w-3" /> Somente leitura</Badge>
                                                    )}
                                                </div>
                                                <div className="grid grid-cols-2 gap-4">
                                                    <div className="space-y-1">
                                                        <Label className="text-xs text-muted-foreground">Telefone</Label>
                                                        <p className="text-sm font-body">{details.card.telefone || "—"}</p>
                                                    </div>
                                                    <div className="space-y-1">
                                                        <Label className="text-xs text-muted-foreground">Email</Label>
                                                        <p className="text-sm font-body">{details.card.email || "—"}</p>
                                                    </div>
                                                </div>

                                                {/* Project Data - View */}
                                                <Separator />
                                                <h4 className="font-heading font-medium text-sm">Dados do Projeto</h4>
                                                <div className="grid grid-cols-2 gap-x-4 gap-y-3">
                                                    <ViewField label="Produto" value={details.card.produto} />
                                                    <ViewField label="Nome do Projeto" value={details.card.nome_projeto} />
                                                    <ViewField label="Orçamento" value={details.card.orcamento_projeto} />
                                                    <ViewField label="Aplicação" value={details.card.aplicacao} />
                                                </div>
                                                <ViewField label="Objetivo do Projeto" value={details.card.objetivo_projeto} multiline />
                                                <ViewField label="Aplicações a Desenvolver" value={details.card.aplicacoes_desenvolver} multiline />
                                                <ViewField label="Ativos para Claims" value={details.card.ativos_claims} multiline />
                                                <ViewField label="Referências" value={details.card.referencias} multiline />
                                                {details.card.referencias_fotos_url && (
                                                    <div className="space-y-1">
                                                        <Label className="text-xs text-muted-foreground">Referências Fotos</Label>
                                                        <a href={details.card.referencias_fotos_url} target="_blank" rel="noopener noreferrer" className="text-sm text-primary hover:underline break-all block">{details.card.referencias_fotos_url}</a>
                                                    </div>
                                                )}

                                                {/* Technical Specs - View */}
                                                <Separator />
                                                <h4 className="font-heading font-medium text-sm">Especificações Técnicas</h4>
                                                <div className="grid grid-cols-2 gap-x-4 gap-y-3">
                                                    <ViewField label="Textura Esperada" value={details.card.textura_esperada} />
                                                    <ViewField label="Sensorial" value={details.card.sensorial} />
                                                    <ViewField label="pH" value={details.card.ph} />
                                                </div>
                                                <ViewField label="Outras Observações" value={details.card.outras_observacoes} multiline highlight />
                                            </>
                                        ) : (
                                            <>
                                                {/* Edit Mode */}
                                                <div className="flex items-center justify-between">
                                                    <h4 className="font-heading font-medium text-sm">Editando Dados</h4>
                                                    <div className="flex gap-1.5">
                                                        <Button size="sm" onClick={saveProject} disabled={savingProject} className="gap-1 text-xs h-7">
                                                            <Save className="h-3 w-3" /> {savingProject ? "Salvando..." : "Salvar"}
                                                        </Button>
                                                        <Button size="sm" variant="ghost" onClick={() => setEditingProject(false)} className="text-xs h-7">
                                                            <X className="h-3 w-3" />
                                                        </Button>
                                                    </div>
                                                </div>

                                                {/* Client */}
                                                <div className="space-y-3 p-3 rounded-lg border bg-muted/30">
                                                    <Label className="text-[11px] text-muted-foreground uppercase tracking-wider font-semibold">Cliente</Label>
                                                    <div className="space-y-1.5">
                                                        <Label className="text-xs">Nome do Cliente</Label>
                                                        <Input value={projectForm.nome_cliente} onChange={e => setProjectForm(p => ({ ...p, nome_cliente: e.target.value }))} className="h-8 text-sm" />
                                                    </div>
                                                    <div className="grid grid-cols-2 gap-3">
                                                        <div className="space-y-1.5">
                                                            <Label className="text-xs">Telefone</Label>
                                                            <Input value={projectForm.telefone} onChange={e => setProjectForm(p => ({ ...p, telefone: e.target.value }))} className="h-8 text-sm" />
                                                        </div>
                                                        <div className="space-y-1.5">
                                                            <Label className="text-xs">Email</Label>
                                                            <Input value={projectForm.email} onChange={e => setProjectForm(p => ({ ...p, email: e.target.value }))} className="h-8 text-sm" />
                                                        </div>
                                                    </div>
                                                </div>

                                                {/* Project */}
                                                <div className="space-y-3 p-3 rounded-lg border bg-muted/30">
                                                    <Label className="text-[11px] text-muted-foreground uppercase tracking-wider font-semibold">Dados do Projeto</Label>
                                                    <div className="grid grid-cols-2 gap-3">
                                                        <div className="space-y-1.5">
                                                            <Label className="text-xs">Produto</Label>
                                                            <Input value={projectForm.produto} onChange={e => setProjectForm(p => ({ ...p, produto: e.target.value }))} className="h-8 text-sm" placeholder="Ex: Sérum, Creme" />
                                                        </div>
                                                        <div className="space-y-1.5">
                                                            <Label className="text-xs">Nome do Projeto</Label>
                                                            <Input value={projectForm.nome_projeto} onChange={e => setProjectForm(p => ({ ...p, nome_projeto: e.target.value }))} className="h-8 text-sm" />
                                                        </div>
                                                    </div>
                                                    <div className="space-y-1.5">
                                                        <Label className="text-xs">Objetivo do Projeto</Label>
                                                        <Textarea value={projectForm.objetivo_projeto} onChange={e => setProjectForm(p => ({ ...p, objetivo_projeto: e.target.value }))} rows={2} className="text-sm" />
                                                    </div>
                                                    <div className="space-y-1.5">
                                                        <Label className="text-xs">Aplicações a Desenvolver</Label>
                                                        <Textarea value={projectForm.aplicacoes_desenvolver} onChange={e => setProjectForm(p => ({ ...p, aplicacoes_desenvolver: e.target.value }))} rows={2} className="text-sm" />
                                                    </div>
                                                    <div className="space-y-1.5">
                                                        <Label className="text-xs">Ativos para Claims</Label>
                                                        <Textarea value={projectForm.ativos_claims} onChange={e => setProjectForm(p => ({ ...p, ativos_claims: e.target.value }))} rows={2} className="text-sm" />
                                                    </div>
                                                    <div className="space-y-1.5">
                                                        <Label className="text-xs">Referências</Label>
                                                        <Textarea value={projectForm.referencias} onChange={e => setProjectForm(p => ({ ...p, referencias: e.target.value }))} rows={2} className="text-sm" />
                                                    </div>
                                                    <div className="space-y-1.5">
                                                        <Label className="text-xs">Referências Fotos (URL)</Label>
                                                        <Input value={projectForm.referencias_fotos_url} onChange={e => setProjectForm(p => ({ ...p, referencias_fotos_url: e.target.value }))} className="h-8 text-sm" />
                                                    </div>
                                                    <div className="space-y-1.5">
                                                        <Label className="text-xs">Orçamento do Projeto</Label>
                                                        <Input value={projectForm.orcamento_projeto} onChange={e => setProjectForm(p => ({ ...p, orcamento_projeto: e.target.value }))} className="h-8 text-sm" />
                                                    </div>
                                                </div>

                                                {/* Technical Specs */}
                                                <div className="space-y-3 p-3 rounded-lg border bg-muted/30">
                                                    <Label className="text-[11px] text-muted-foreground uppercase tracking-wider font-semibold">Especificações Técnicas</Label>
                                                    <div className="grid grid-cols-2 gap-3">
                                                        <div className="space-y-1.5">
                                                            <Label className="text-xs">Textura Esperada</Label>
                                                            <Input value={projectForm.textura_esperada} onChange={e => setProjectForm(p => ({ ...p, textura_esperada: e.target.value }))} className="h-8 text-sm" />
                                                        </div>
                                                        <div className="space-y-1.5">
                                                            <Label className="text-xs">Aplicação</Label>
                                                            <Input value={projectForm.aplicacao} onChange={e => setProjectForm(p => ({ ...p, aplicacao: e.target.value }))} className="h-8 text-sm" />
                                                        </div>
                                                    </div>
                                                    <div className="grid grid-cols-2 gap-3">
                                                        <div className="space-y-1.5">
                                                            <Label className="text-xs">Sensorial</Label>
                                                            <Input value={projectForm.sensorial} onChange={e => setProjectForm(p => ({ ...p, sensorial: e.target.value }))} className="h-8 text-sm" />
                                                        </div>
                                                        <div className="space-y-1.5">
                                                            <Label className="text-xs">pH</Label>
                                                            <Input value={projectForm.ph} onChange={e => setProjectForm(p => ({ ...p, ph: e.target.value }))} className="h-8 text-sm" />
                                                        </div>
                                                    </div>
                                                    <div className="space-y-1.5">
                                                        <Label className="text-xs">Outras Observações e/ou Sensoriais</Label>
                                                        <Textarea value={projectForm.outras_observacoes} onChange={e => setProjectForm(p => ({ ...p, outras_observacoes: e.target.value }))} rows={3} className="text-sm" />
                                                    </div>
                                                </div>
                                            </>
                                        )}

                                        <Separator />
                                        <h4 className="font-heading font-medium text-sm">Campos da Fase: {details.stage?.name}</h4>

                                        {details.fields.map(field => (
                                            <div key={field.id} className="space-y-1.5">
                                                <Label className="text-xs">
                                                    {field.label} {field.required && <span className="text-destructive">*</span>}
                                                </Label>
                                                {renderField(field)}
                                            </div>
                                        ))}

                                        <Button onClick={saveFields} className="mt-2" data-testid="save-fields-btn">
                                            <Save className="h-4 w-4 mr-2" /> Salvar Campos
                                        </Button>
                                    </div>
                                </TabsContent>

                                <TabsContent value="amostras" className="px-6 pb-6 mt-0">
                                    <AmostrasSection cardId={cardId} amostras={details.amostras || []} canEdit={canEdit} onRefresh={() => {
                                        api.get(`/cards/${cardId}/details`).then(({ data }) => {
                                            setDetails(data);
                                        });
                                    }} />
                                </TabsContent>

                                <TabsContent value="products" className="px-6 pb-6 mt-0">
                                    <div className="space-y-4 mt-4">
                                        {details.products.length > 0 && (
                                            <div className="border rounded-md overflow-hidden">
                                                <table className="w-full text-sm">
                                                    <thead className="bg-muted">
                                                        <tr>
                                                            <th className="text-left p-2 font-medium">Produto</th>
                                                            <th className="text-right p-2 font-medium">Qtd</th>
                                                            <th className="text-right p-2 font-medium">Unit.</th>
                                                            <th className="text-right p-2 font-medium">Total</th>
                                                            <th className="w-10"></th>
                                                        </tr>
                                                    </thead>
                                                    <tbody>
                                                        {details.products.map(p => (
                                                            <tr key={p.id} className="border-t" data-testid={`product-${p.id}`}>
                                                                <td className="p-2">{p.nome_produto}</td>
                                                                <td className="p-2 text-right mono-num">{p.quantidade}</td>
                                                                <td className="p-2 text-right mono-num">R$ {p.valor_unitario?.toFixed(2)}</td>
                                                                <td className="p-2 text-right mono-num font-medium">R$ {p.valor_total?.toFixed(2)}</td>
                                                                <td className="p-2">
                                                                    <Button variant="ghost" size="icon" className="h-7 w-7"
                                                                        onClick={() => removeProduct(p.id)} data-testid={`remove-product-${p.id}`}>
                                                                        <Trash2 className="h-3.5 w-3.5 text-destructive" />
                                                                    </Button>
                                                                </td>
                                                            </tr>
                                                        ))}
                                                    </tbody>
                                                </table>
                                                <div className="border-t p-2 text-right text-sm font-medium">
                                                    Total: <span className="mono-num">R$ {totalProducts.toFixed(2)}</span>
                                                </div>
                                            </div>
                                        )}

                                        <div className="border rounded-md p-4 space-y-3">
                                            <h4 className="font-heading font-medium text-sm">Adicionar Produto</h4>
                                            <div className="grid grid-cols-2 gap-3">
                                                <div className="space-y-1">
                                                    <Label className="text-xs">Produto *</Label>
                                                    <Input data-testid="product-name" value={newProduct.nome_produto}
                                                        onChange={(e) => setNewProduct({ ...newProduct, nome_produto: e.target.value })} />
                                                </div>
                                                <div className="space-y-1">
                                                    <Label className="text-xs">SKU</Label>
                                                    <Input data-testid="product-sku" value={newProduct.sku}
                                                        onChange={(e) => setNewProduct({ ...newProduct, sku: e.target.value })} />
                                                </div>
                                                <div className="space-y-1">
                                                    <Label className="text-xs">Quantidade</Label>
                                                    <Input type="number" data-testid="product-qty" value={newProduct.quantidade}
                                                        onChange={(e) => setNewProduct({ ...newProduct, quantidade: parseInt(e.target.value) || 0 })} />
                                                </div>
                                                <div className="space-y-1">
                                                    <Label className="text-xs">Valor Unitario</Label>
                                                    <Input type="number" step="0.01" data-testid="product-price" value={newProduct.valor_unitario}
                                                        onChange={(e) => setNewProduct({ ...newProduct, valor_unitario: parseFloat(e.target.value) || 0 })} />
                                                </div>
                                            </div>
                                            <Button onClick={addProduct} size="sm" data-testid="add-product-btn" disabled={!newProduct.nome_produto}>
                                                <Plus className="h-4 w-4 mr-1" /> Adicionar
                                            </Button>
                                        </div>
                                    </div>
                                </TabsContent>

                                <TabsContent value="history" className="px-6 pb-6 mt-0">
                                    <div className="space-y-3 mt-4">
                                        {details.history.length === 0 ? (
                                            <p className="text-muted-foreground text-sm py-4">Nenhuma atividade registrada.</p>
                                        ) : details.history.map((h, i) => (
                                            <div key={i} className="flex gap-3" data-testid={`history-${i}`}>
                                                <div className="flex flex-col items-center">
                                                    <div className="w-2 h-2 rounded-full bg-primary mt-2" />
                                                    {i < details.history.length - 1 && <div className="w-px flex-1 bg-border mt-1" />}
                                                </div>
                                                <div className="pb-4">
                                                    <p className="text-sm font-medium">{h.action}</p>
                                                    <p className="text-xs text-muted-foreground">{h.details}</p>
                                                    <p className="text-[10px] text-muted-foreground mt-1 mono-num">
                                                        {h.user_name} &middot; {new Date(h.created_at).toLocaleString("pt-BR")}
                                                    </p>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </TabsContent>

                                <TabsContent value="chat" className="flex flex-col min-h-[400px] mt-0">
                                    <div className="flex-1 px-6 py-4 space-y-3 overflow-y-auto">
                                        {details.messages.length === 0 && (
                                            <p className="text-muted-foreground text-sm text-center py-8">Inicie uma conversa com o lead.</p>
                                        )}
                                        {details.messages.map(m => (
                                            <div key={m.id} className={m.sender === "agent" ? "flex justify-end" : "flex justify-start"}
                                                data-testid={`message-${m.id}`}>
                                                <div className={m.sender === "agent" ? "chat-bubble-agent px-4 py-2" : "chat-bubble-client px-4 py-2"}>
                                                    <p className="text-sm">{m.content}</p>
                                                    <p className="text-[10px] opacity-60 mt-1 mono-num">
                                                        {new Date(m.created_at).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}
                                                    </p>
                                                </div>
                                            </div>
                                        ))}
                                        <div ref={chatEndRef} />
                                    </div>
                                    {showTemplates && templates.length > 0 && (
                                        <div className="px-6 pb-2 space-y-1.5" data-testid="wa-templates">
                                            <p className="text-[10px] text-muted-foreground font-medium">Templates WhatsApp</p>
                                            {templates.map(t => (
                                                <button key={t.id} onClick={() => {
                                                    const msg = t.content
                                                        .replace("{nome}", details.card.nome_cliente)
                                                        .replace("{vendedor}", "Vendedor")
                                                        .replace("{empresa}", "Kuryos");
                                                    setMessageText(msg);
                                                    setShowTemplates(false);
                                                }}
                                                className="block w-full text-left text-xs px-3 py-2 rounded-md border border-border hover:bg-accent transition-colors"
                                                data-testid={`template-${t.id}`}>
                                                    <span className="font-medium">{t.name}</span>
                                                    <span className="text-muted-foreground ml-1 truncate">— {t.content.slice(0, 60)}...</span>
                                                </button>
                                            ))}
                                        </div>
                                    )}
                                    {suggestions.length > 0 && (
                                        <div className="px-6 pb-2 space-y-1.5" data-testid="ai-suggestions">
                                            <p className="text-[10px] text-muted-foreground font-medium flex items-center gap-1">
                                                <Lightbulb className="h-3 w-3" /> Sugestoes IA
                                            </p>
                                            {suggestions.map((s, i) => (
                                                <button key={i} onClick={() => setMessageText(s)}
                                                    className="block w-full text-left text-xs px-3 py-2 rounded-md border border-border hover:bg-accent transition-colors"
                                                    data-testid={`suggestion-${i}`}>
                                                    {s}
                                                </button>
                                            ))}
                                        </div>
                                    )}
                                    <div className="border-t p-4 flex gap-2">
                                        <Button variant="outline" size="icon" onClick={() => setShowTemplates(!showTemplates)}
                                            className="shrink-0" data-testid="wa-templates-btn" title="Templates">
                                            <FileText className="h-4 w-4" />
                                        </Button>
                                        <Button variant="outline" size="icon" onClick={generateSuggestions} disabled={suggestionsLoading}
                                            className="shrink-0" data-testid="ai-suggestions-btn" title="Sugestoes IA">
                                            {suggestionsLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                                        </Button>
                                        <Input value={messageText} onChange={(e) => setMessageText(e.target.value)}
                                            placeholder="Digite uma mensagem..." data-testid="chat-input"
                                            onKeyDown={(e) => e.key === "Enter" && sendMessage()} />
                                        <Button onClick={sendMessage} size="icon" data-testid="send-message-btn">
                                            <Send className="h-4 w-4" />
                                        </Button>
                                    </div>
                                </TabsContent>
                            </ScrollArea>
                        </Tabs>
                    </>
                ) : null}
            </SheetContent>
        </Sheet>
    );
}


function ViewField({ label, value, multiline, highlight }) {
    if (!value) return (
        <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">{label}</Label>
            <p className="text-sm text-muted-foreground/50">—</p>
        </div>
    );
    return (
        <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">{label}</Label>
            {multiline ? (
                <p className={`text-sm whitespace-pre-wrap ${highlight ? "bg-muted/50 p-2 rounded" : ""}`}>{value}</p>
            ) : (
                <p className="text-sm">{value}</p>
            )}
        </div>
    );
}


function AmostrasSection({ cardId, amostras, canEdit, onRefresh }) {
    const [showAdd, setShowAdd] = useState(false);
    const [form, setForm] = useState({ nome_amostra: "", tipo_produto: "", descricao: "", referencia: "", volume: "", observacoes: "" });
    const [saving, setSaving] = useState(false);

    const addAmostra = async () => {
        if (!form.nome_amostra.trim()) { toast.error("Nome da amostra é obrigatório"); return; }
        setSaving(true);
        try {
            await api.post(`/cards/${cardId}/amostras`, form);
            toast.success("Amostra adicionada!");
            setForm({ nome_amostra: "", tipo_produto: "", descricao: "", referencia: "", volume: "", observacoes: "" });
            setShowAdd(false);
            onRefresh();
        } catch { toast.error("Erro ao adicionar amostra"); }
        finally { setSaving(false); }
    };

    const removeAmostra = async (amostraId) => {
        try {
            await api.delete(`/cards/${cardId}/amostras/${amostraId}`);
            toast.success("Amostra removida");
            onRefresh();
        } catch { toast.error("Erro ao remover"); }
    };

    return (
        <div className="space-y-4 mt-4">
            <div className="flex items-center justify-between">
                <div>
                    <h4 className="font-medium text-sm">Amostras Solicitadas ({amostras.length})</h4>
                    <p className="text-xs text-muted-foreground">Cada amostra gerará um card próprio no P&D ao mover para "Amostras"</p>
                </div>
                {canEdit && (
                    <Button size="sm" onClick={() => setShowAdd(true)} className="gap-1.5 text-xs">
                        <Plus className="h-3 w-3" /> Adicionar
                    </Button>
                )}
            </div>

            {showAdd && (
                <div className="border rounded-lg p-4 space-y-3 border-primary/50 bg-muted/30">
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <Label className="text-xs">Nome da Amostra *</Label>
                            <Input value={form.nome_amostra} onChange={e => setForm(p => ({ ...p, nome_amostra: e.target.value }))} placeholder="Ex: Bodysplash Floral Rose" className="text-sm" />
                        </div>
                        <div>
                            <Label className="text-xs">Tipo de Produto</Label>
                            <Input value={form.tipo_produto} onChange={e => setForm(p => ({ ...p, tipo_produto: e.target.value }))} placeholder="Ex: Bodysplash, Creme, Perfume" className="text-sm" />
                        </div>
                        <div>
                            <Label className="text-xs">Referência</Label>
                            <Input value={form.referencia} onChange={e => setForm(p => ({ ...p, referencia: e.target.value }))} placeholder="Ex: Similar ao produto X" className="text-sm" />
                        </div>
                        <div>
                            <Label className="text-xs">Volume</Label>
                            <Input value={form.volume} onChange={e => setForm(p => ({ ...p, volume: e.target.value }))} placeholder="Ex: 200mL, 100g" className="text-sm" />
                        </div>
                        <div className="col-span-2">
                            <Label className="text-xs">Descrição</Label>
                            <Textarea value={form.descricao} onChange={e => setForm(p => ({ ...p, descricao: e.target.value }))} placeholder="Detalhes da amostra..." rows={2} className="text-sm" />
                        </div>
                        <div className="col-span-2">
                            <Label className="text-xs">Observações</Label>
                            <Textarea value={form.observacoes} onChange={e => setForm(p => ({ ...p, observacoes: e.target.value }))} placeholder="Notas adicionais..." rows={2} className="text-sm" />
                        </div>
                    </div>
                    <div className="flex gap-2">
                        <Button size="sm" onClick={addAmostra} disabled={saving} className="gap-1 text-xs">
                            <Plus className="h-3 w-3" /> {saving ? "Adicionando..." : "Adicionar Amostra"}
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setShowAdd(false)} className="text-xs">Cancelar</Button>
                    </div>
                </div>
            )}

            {amostras.length > 0 ? (
                <div className="space-y-2">
                    {amostras.map((a, idx) => (
                        <div key={a.id} className="border rounded-lg p-3 hover:border-primary/30 transition-colors">
                            <div className="flex items-start justify-between gap-2">
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2 flex-wrap">
                                        <Badge variant="outline" className="text-[10px] font-mono shrink-0">#{idx + 1}</Badge>
                                        <span className="font-medium text-sm">{a.nome_amostra}</span>
                                        {a.tipo_produto && <Badge variant="secondary" className="text-[10px]">{a.tipo_produto}</Badge>}
                                    </div>
                                    <div className="mt-1.5 grid grid-cols-2 gap-x-4 gap-y-0.5 text-xs text-muted-foreground">
                                        {a.referencia && <span><b>Ref:</b> {a.referencia}</span>}
                                        {a.volume && <span><b>Volume:</b> {a.volume}</span>}
                                    </div>
                                    {a.descricao && <p className="text-xs mt-1 text-muted-foreground">{a.descricao}</p>}
                                    {a.observacoes && <p className="text-xs mt-1 italic text-muted-foreground/80">{a.observacoes}</p>}
                                </div>
                                {canEdit && (
                                    <Button variant="ghost" size="icon" className="h-7 w-7 text-muted-foreground hover:text-red-500 shrink-0" onClick={() => removeAmostra(a.id)}>
                                        <Trash2 className="h-3.5 w-3.5" />
                                    </Button>
                                )}
                            </div>
                        </div>
                    ))}
                </div>
            ) : (
                !showAdd && (
                    <div className="text-center py-10 border rounded-lg border-dashed">
                        <Beaker className="h-10 w-10 mx-auto mb-3 text-muted-foreground/20" />
                        <p className="text-sm font-medium">Nenhuma amostra solicitada</p>
                        <p className="text-xs text-muted-foreground mt-1">Adicione as amostras que o cliente solicitou</p>
                    </div>
                )
            )}
        </div>
    );
}
