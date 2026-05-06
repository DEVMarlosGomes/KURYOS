import React, { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { toast } from "sonner";
import { BACKEND_URL } from "@/lib/backend";
import {
  ArrowLeft, FlaskConical, Clock, Plus, Trash2, CheckCircle2, XCircle,
  Loader2, ArrowRight, FileText, DollarSign, Beaker, Package, History,
  Eye, Download, Pencil, Save, X, ShieldCheck, Send, MessageSquare, Settings2,
  Bell, Hourglass, AlertTriangle, Sparkles, ClipboardList, ThumbsUp, ThumbsDown,
  PrinterIcon, CheckSquare, XSquare
} from "lucide-react";

const STATUS_CONFIG = {
  OPEN: { label: "Aberto", color: "bg-blue-500/10 text-blue-600 border-blue-200", dotColor: "bg-blue-500" },
  IN_PROGRESS: { label: "Em Desenvolvimento", color: "bg-amber-500/10 text-amber-600 border-amber-200", dotColor: "bg-amber-500" },
  IN_TESTS: { label: "Em Testes", color: "bg-purple-500/10 text-purple-600 border-purple-200", dotColor: "bg-purple-500" },
  WAITING_APPROVAL: { label: "Aguardando Aprovação", color: "bg-orange-500/10 text-orange-600 border-orange-200", dotColor: "bg-orange-500" },
  APPROVED: { label: "Aprovado", color: "bg-green-500/10 text-green-600 border-green-200", dotColor: "bg-green-500" },
  COMPLETED: { label: "Concluído", color: "bg-emerald-500/10 text-emerald-700 border-emerald-200", dotColor: "bg-emerald-600" },
  REJECTED: { label: "Rejeitado", color: "bg-red-500/10 text-red-600 border-red-200", dotColor: "bg-red-500" },
};

const ALLOWED_TRANSITIONS = {
  OPEN: ["IN_PROGRESS"],
  IN_PROGRESS: ["IN_TESTS"],
  IN_TESTS: ["WAITING_APPROVAL"],
  WAITING_APPROVAL: ["APPROVED", "REJECTED"],
  APPROVED: ["COMPLETED"],
  REJECTED: ["IN_PROGRESS"],
  COMPLETED: [],
};

const TEST_TYPES = ["Estabilidade", "pH", "Viscosidade", "Sensorial", "Compatibilidade"];
const TEST_STATUS_OPTIONS = ["PENDING", "RUNNING", "APPROVED", "FAILED"];
const DOC_TYPES = ["Ficha Técnica", "Laudo", "Especificação", "Briefing Cliente", "Outro"];

const REQUEST_TYPES = ["Produto Novo", "Reformulação", "Extensão de Linha", "Adequação Regulatória", "Outro"];
const CATEGORIES = ["Skincare", "Haircare", "Bodycare", "Perfumaria", "Maquiagem", "Higiene", "Outro"];
const PRIORITIES = ["Baixa", "Normal", "Alta", "Urgente"];

// Structured test fields per type
const TEST_FIELDS = {
  Estabilidade: [
    { key: "condicao", label: "Condição", placeholder: "Ex: 45°C / 90 dias" },
    { key: "aspecto", label: "Aspecto", placeholder: "Normal, separação, etc." },
    { key: "cor", label: "Cor", placeholder: "Inalterada, escurecida, etc." },
    { key: "odor", label: "Odor", placeholder: "Inalterado, alterado, etc." },
    { key: "observacoes", label: "Observações", placeholder: "Notas adicionais", multiline: true },
  ],
  pH: [
    { key: "valor_medido", label: "Valor Medido", placeholder: "Ex: 5.5" },
    { key: "faixa_aceitavel", label: "Faixa Aceitável", placeholder: "Ex: 5.0 - 6.0" },
    { key: "temperatura", label: "Temperatura (°C)", placeholder: "Ex: 25" },
    { key: "observacoes", label: "Observações", placeholder: "Notas adicionais", multiline: true },
  ],
  Viscosidade: [
    { key: "valor_medido", label: "Valor Medido", placeholder: "Ex: 15000" },
    { key: "unidade", label: "Unidade", placeholder: "Ex: cP, mPa.s" },
    { key: "spindle", label: "Spindle / Velocidade", placeholder: "Ex: S64 / 20 rpm" },
    { key: "temperatura", label: "Temperatura (°C)", placeholder: "Ex: 25" },
    { key: "observacoes", label: "Observações", placeholder: "Notas adicionais", multiline: true },
  ],
  Sensorial: [
    { key: "aspecto", label: "Aspecto", placeholder: "Creme, líquido, gel, etc." },
    { key: "cor", label: "Cor", placeholder: "Branca, translúcida, etc." },
    { key: "odor", label: "Odor", placeholder: "Agradável, suave, etc." },
    { key: "toque", label: "Toque", placeholder: "Sedoso, leve, pegajoso, etc." },
    { key: "espalhabilidade", label: "Espalhabilidade", placeholder: "Boa, excelente, etc." },
    { key: "observacoes", label: "Observações", placeholder: "Notas adicionais", multiline: true },
  ],
  Compatibilidade: [
    { key: "material_testado", label: "Material Testado", placeholder: "Ex: PET, Alumínio, PP" },
    { key: "tempo_dias", label: "Tempo (dias)", placeholder: "Ex: 30, 60, 90" },
    { key: "resultado", label: "Resultado", placeholder: "Compatível, incompatível, etc." },
    { key: "observacoes", label: "Observações", placeholder: "Notas adicionais", multiline: true },
  ],
};

export default function PDDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user: authUser } = useAuth();
  const canEdit = authUser && ["admin", "gestor", "formulador", "lider_pd", "engenharia_produto"].includes(authUser.role);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("overview");

  const fetchData = useCallback(async () => {
    try {
      const res = await api.get(`/pd/requests/${id}/full`);
      setData(res.data);
    } catch (err) {
      toast.error("Erro ao carregar dados");
      navigate("/pd");
    } finally {
      setLoading(false);
    }
  }, [id, navigate]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleStatusChange = async (newStatus) => {
    // Check blocking tasks before transition
    const blockingTasks = (data?.blocking_tasks || []).filter(t => 
      !t.blocks_stages?.length || t.blocks_stages.includes(newStatus)
    );
    if (blockingTasks.length > 0) {
      const titles = blockingTasks.slice(0, 3).map(t => `• ${t.title}`).join("\n");
      const confirmed = window.confirm(
        `Existem ${blockingTasks.length} tarefa(s) bloqueante(s):\n${titles}\n\nDeseja avançar mesmo assim?`
      );
      if (!confirmed) return;
    }
    try {
      await api.put(`/pd/requests/${id}/status`, { new_status: newStatus });
      toast.success("Status atualizado!");
      fetchData();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Erro ao alterar status");
    }
  };

  const downloadFichaTecnica = async () => {
    try {
      const response = await api.get(`/pd/requests/${id}/ficha-tecnica`, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.download = `ficha_tecnica_${data?.request?.project_name?.replace(/\s/g, '_') || 'pd'}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      toast.success("Ficha técnica gerada!");
    } catch (err) {
      toast.error("Erro ao gerar ficha técnica");
    }
  };

  if (loading || !data) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const { request: req, development: dev, formulas, tests, samples, approval, costs, documents, history, client_info, formula_cost_data, lab_results, updates, pending } = data;
  const statusConfig = STATUS_CONFIG[req.status];
  const allowedNext = ALLOWED_TRANSITIONS[req.status] || [];
  const hasDev = !!dev;
  const pendingCount = (pending || []).filter(p => p.status === "pendente").length;
  const isInternalResearch = !!req.is_internal_research;

  return (
    <div className="h-full overflow-auto">
      <div className="max-w-6xl mx-auto p-6">
        {/* Header */}
        <div className="flex items-start justify-between mb-6">
          <div className="flex items-start gap-3">
            <Button variant="ghost" size="icon" onClick={() => navigate("/pd")} className="mt-0.5">
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <div>
              <h1 className="text-xl font-bold flex items-center gap-2">
                <FlaskConical className="h-5 w-5" />
                {req.project_name}
              </h1>
              <div className="flex items-center gap-2 mt-1 flex-wrap">
                <Badge className={statusConfig.color}>{statusConfig.label}</Badge>
                <span className="text-xs text-muted-foreground">{req.request_type}</span>
                {req.client_name && <span className="text-xs text-muted-foreground">• {req.client_name}</span>}
                {req.priority && (
                  <Badge variant="outline" className="text-[10px]">{req.priority}</Badge>
                )}
                {isInternalResearch && (
                  <Badge className="bg-purple-500/20 text-purple-700 dark:text-purple-300 border-purple-300 text-[10px] gap-1">
                    <Sparkles className="h-3 w-3" /> Pesquisa Interna
                  </Badge>
                )}
                {pendingCount > 0 && (
                  <Badge className="bg-amber-500/20 text-amber-700 dark:text-amber-300 border-amber-300 text-[10px] gap-1">
                    <Hourglass className="h-3 w-3" /> {pendingCount} pendência(s)
                  </Badge>
                )}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2 flex-wrap justify-end">
            {hasDev && (
              <Button size="sm" variant="outline" onClick={downloadFichaTecnica} className="gap-1.5">
                <Download className="h-3.5 w-3.5" />
                Ficha Técnica PDF
              </Button>
            )}
            {canEdit && allowedNext.map(ns => (
              <Button
                key={ns}
                size="sm"
                variant={ns === "REJECTED" ? "destructive" : "default"}
                onClick={() => handleStatusChange(ns)}
                className="gap-1.5"
              >
                {ns === "REJECTED" ? <XCircle className="h-3.5 w-3.5" /> : <ArrowRight className="h-3.5 w-3.5" />}
                {STATUS_CONFIG[ns]?.label}
              </Button>
            ))}
          </div>
        </div>

        {/* Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="mb-4 flex-wrap h-auto gap-1">
            <TabsTrigger value="overview" className="gap-1.5"><Eye className="h-3.5 w-3.5" />Overview</TabsTrigger>
            <TabsTrigger value="formula" className="gap-1.5"><Beaker className="h-3.5 w-3.5" />Manipulação</TabsTrigger>
            <TabsTrigger value="tests" className="gap-1.5"><FlaskConical className="h-3.5 w-3.5" />Testes</TabsTrigger>
            <TabsTrigger value="samples" className="gap-1.5"><Package className="h-3.5 w-3.5" />Amostras</TabsTrigger>
            <TabsTrigger value="ficha_tecnica" className="gap-1.5"><ClipboardList className="h-3.5 w-3.5" />Ficha Técnica</TabsTrigger>
            <TabsTrigger value="updates" className="gap-1.5 relative">
              <Bell className="h-3.5 w-3.5" />Atualizações
              {pendingCount > 0 && (
                <span className="ml-1 inline-flex items-center justify-center px-1.5 min-w-[18px] h-[18px] text-[10px] font-bold rounded-full bg-amber-500 text-white">
                  {pendingCount}
                </span>
              )}
            </TabsTrigger>
            <TabsTrigger value="costs" className="gap-1.5"><DollarSign className="h-3.5 w-3.5" />Custos</TabsTrigger>
            <TabsTrigger value="documents" className="gap-1.5"><FileText className="h-3.5 w-3.5" />Documentos</TabsTrigger>
          </TabsList>

          <TabsContent value="overview">
            <OverviewTab req={req} dev={dev} formulas={formulas} tests={tests} samples={samples} approval={approval} costs={costs} history={history} onRefresh={fetchData} hasDev={hasDev} clientInfo={client_info} canEdit={canEdit} formulaCostData={formula_cost_data} />
          </TabsContent>

          <TabsContent value="formula">
            {hasDev ? (
              <FormulaTab devId={dev.id} formulas={formulas} onRefresh={fetchData} canEdit={canEdit} clientInfo={client_info} req={req} />
            ) : (
              <NeedsDev onAction={() => handleStatusChange("IN_PROGRESS")} status={req.status} canEdit={canEdit} />
            )}
          </TabsContent>

          <TabsContent value="tests">
            {hasDev ? (
              <TestsTab devId={dev.id} labResults={lab_results} onRefresh={fetchData} canEdit={canEdit} />
            ) : (
              <NeedsDev onAction={() => handleStatusChange("IN_PROGRESS")} status={req.status} canEdit={canEdit} />
            )}
          </TabsContent>

          <TabsContent value="samples">
            {hasDev ? (
              <SamplesTab devId={dev.id} samples={samples} formulas={formulas} onRefresh={fetchData} canEdit={canEdit} />
            ) : (
              <NeedsDev onAction={() => handleStatusChange("IN_PROGRESS")} status={req.status} canEdit={canEdit} />
            )}
          </TabsContent>

          <TabsContent value="ficha_tecnica">
            <FichaTecnicaTab reqId={req.id} formulas={formulas} req={req} dev={dev} canEdit={canEdit} />
          </TabsContent>

          <TabsContent value="updates">
            <UpdatesTab reqId={req.id} updates={updates || []} pending={pending || []} onRefresh={fetchData} canEdit={canEdit} />
          </TabsContent>

          <TabsContent value="costs">
            {hasDev ? (
              <CostsTab devId={dev.id} costs={costs} formulas={formulas} formulaCostData={formula_cost_data} onRefresh={fetchData} canEdit={canEdit} />
            ) : (
              <NeedsDev onAction={() => handleStatusChange("IN_PROGRESS")} status={req.status} canEdit={canEdit} />
            )}
          </TabsContent>

          <TabsContent value="documents">
            {hasDev ? (
              <DocumentsTab devId={dev.id} documents={documents} onRefresh={fetchData} canEdit={canEdit} />
            ) : (
              <NeedsDev onAction={() => handleStatusChange("IN_PROGRESS")} status={req.status} canEdit={canEdit} />
            )}
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}

/* ============ NEEDS DEV PLACEHOLDER ============ */
function NeedsDev({ onAction, status, canEdit }) {
  return (
    <div className="text-center py-16">
      <FlaskConical className="h-16 w-16 mx-auto mb-4 text-muted-foreground/30" />
      <h3 className="text-lg font-semibold mb-2">Desenvolvimento não iniciado</h3>
      <p className="text-sm text-muted-foreground mb-6 max-w-md mx-auto">
        Para acessar formulação, testes, amostras, custos e documentos, inicie o desenvolvimento.
      </p>
      {status === "OPEN" && canEdit && (
        <Button onClick={onAction} className="gap-2">
          <ArrowRight className="h-4 w-4" />
          Iniciar Desenvolvimento
        </Button>
      )}
    </div>
  );
}

/* ============ OVERVIEW TAB ============ */
function OverviewTab({ req, dev, formulas, tests, samples, approval, costs, history, onRefresh, hasDev, clientInfo, canEdit, formulaCostData }) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({});

  const startEditing = () => {
    setForm({
      project_name: req.project_name || "",
      request_type: req.request_type || "Produto Novo",
      category: req.category || "",
      description: req.description || "",
      references: req.references || "",
      restrictions: req.restrictions || "",
      volume: req.volume || "",
      packaging: req.packaging || "",
      priority: req.priority || "Normal",
      deadline: req.deadline || "",
    });
    setEditing(true);
  };

  const saveChanges = async () => {
    setSaving(true);
    try {
      await api.put(`/pd/requests/${req.id}`, form);
      toast.success("Solicitação atualizada!");
      setEditing(false);
      onRefresh();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Erro ao salvar");
    } finally {
      setSaving(false);
    }
  };

  const [showApproval, setShowApproval] = useState(false);
  const [approvalForm, setApprovalForm] = useState({
    approved_by_client: approval?.approved_by_client || false,
    approved_by_internal: approval?.approved_by_internal || false,
    notes: approval?.notes || "",
  });
  const [savingApproval, setSavingApproval] = useState(false);

  useEffect(() => {
    setApprovalForm({
      approved_by_client: approval?.approved_by_client || false,
      approved_by_internal: approval?.approved_by_internal || false,
      notes: approval?.notes || "",
    });
  }, [approval]);

  const saveApproval = async () => {
    if (!dev) return;
    setSavingApproval(true);
    try {
      await api.post(`/pd/developments/${dev.id}/approval`, approvalForm);
      toast.success("Aprovação registrada!");
      setShowApproval(false);
      onRefresh();
    } catch (err) {
      toast.error("Erro ao salvar aprovação");
    } finally {
      setSavingApproval(false);
    }
  };

  const testStats = {
    total: tests.length,
    approved: tests.filter(t => t.status === "APPROVED").length,
    failed: tests.filter(t => t.status === "FAILED").length,
    pending: tests.filter(t => t.status === "PENDING" || t.status === "RUNNING").length,
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <div className="lg:col-span-2 space-y-4">
        {/* Briefing Card from CRM - PROMINENT */}
        {clientInfo && (
          <Card className="border-blue-200 dark:border-blue-900">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-blue-500" />
                  Briefing do Projeto (CRM)
                </CardTitle>
                <Badge variant="outline" className="text-[10px]">Dados do Pipeline</Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div className="grid grid-cols-2 gap-x-6 gap-y-2">
                <InfoRow label="1. Produto" value={clientInfo.produto} />
                <InfoRow label="2. Cliente" value={clientInfo.nome_cliente} />
                <InfoRow label="3. Nome do Projeto" value={clientInfo.nome_projeto} />
                <InfoRow label="9. Orçamento" value={clientInfo.orcamento_projeto} />
                <InfoRow label="10. Textura Esperada" value={clientInfo.textura_esperada} />
                <InfoRow label="11. Aplicação" value={clientInfo.aplicacao} />
                <InfoRow label="12. Sensorial" value={clientInfo.sensorial} />
                <InfoRow label="13. pH" value={clientInfo.ph} />
              </div>
              {clientInfo.objetivo_projeto && (
                <div className="pt-2 border-t">
                  <span className="text-muted-foreground text-xs font-medium block mb-1">4. Objetivo do Projeto</span>
                  <p className="whitespace-pre-wrap">{clientInfo.objetivo_projeto}</p>
                </div>
              )}
              {clientInfo.aplicacoes_desenvolver && (
                <div>
                  <span className="text-muted-foreground text-xs font-medium block mb-1">5. Aplicações a Desenvolver</span>
                  <p className="whitespace-pre-wrap">{clientInfo.aplicacoes_desenvolver}</p>
                </div>
              )}
              {clientInfo.ativos_claims && (
                <div>
                  <span className="text-muted-foreground text-xs font-medium block mb-1">6. Ativos para Claims</span>
                  <p className="whitespace-pre-wrap">{clientInfo.ativos_claims}</p>
                </div>
              )}
              {clientInfo.referencias && (
                <div>
                  <span className="text-muted-foreground text-xs font-medium block mb-1">7. Referências</span>
                  <p className="whitespace-pre-wrap">{clientInfo.referencias}</p>
                </div>
              )}
              {clientInfo.referencias_fotos_url && (
                <div>
                  <span className="text-muted-foreground text-xs font-medium block mb-1">8. Referências Fotos</span>
                  <a href={clientInfo.referencias_fotos_url} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline text-sm break-all">{clientInfo.referencias_fotos_url}</a>
                </div>
              )}
              {clientInfo.outras_observacoes && (
                <div>
                  <span className="text-muted-foreground text-xs font-medium block mb-1">14. Outras Observações</span>
                  <p className="whitespace-pre-wrap bg-muted/50 p-2 rounded">{clientInfo.outras_observacoes}</p>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Request Details */}
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Detalhes da Solicitação</CardTitle>
              {!editing ? (
                canEdit && (
                  <Button size="sm" variant="ghost" onClick={startEditing} className="gap-1.5 text-xs">
                    <Pencil className="h-3.5 w-3.5" />
                    Editar
                  </Button>
                )
              ) : (
                <div className="flex gap-1.5">
                  <Button size="sm" variant="default" onClick={saveChanges} disabled={saving} className="gap-1 text-xs">
                    <Save className="h-3.5 w-3.5" />
                    {saving ? "Salvando..." : "Salvar"}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setEditing(false)} className="text-xs">
                    <X className="h-3.5 w-3.5" />
                  </Button>
                </div>
              )}
            </div>
          </CardHeader>
          <CardContent>
            {!editing ? (
              <div className="space-y-3 text-sm">
                <div className="grid grid-cols-2 gap-x-6 gap-y-2">
                  <InfoRow label="Tipo" value={req.request_type} />
                  <InfoRow label="Categoria" value={req.category} />
                  <InfoRow label="Prioridade" value={req.priority} />
                  <InfoRow label="Prazo" value={req.deadline ? new Date(req.deadline).toLocaleDateString("pt-BR") : null} />
                  <InfoRow label="Volume" value={req.volume} />
                  <InfoRow label="Embalagem" value={req.packaging} />
                </div>
                {/* SKU - only for approved/completed */}
                {(req.status === "APPROVED" || req.status === "COMPLETED") && (
                  <SkuField reqId={req.id} currentSku={req.sku} canEdit={canEdit} onRefresh={onRefresh} />
                )}
                {req.description && (
                  <div className="pt-2 border-t">
                    <span className="text-muted-foreground text-xs font-medium block mb-1">Descrição / Briefing</span>
                    <p className="whitespace-pre-wrap text-sm">{req.description}</p>
                  </div>
                )}
                {req.references && (
                  <div>
                    <span className="text-muted-foreground text-xs font-medium block mb-1">Referências</span>
                    <p className="whitespace-pre-wrap text-sm">{req.references}</p>
                  </div>
                )}
                <div className="text-[11px] text-muted-foreground pt-2 border-t">
                  Criado por {req.created_by_name} em {new Date(req.created_at).toLocaleDateString("pt-BR")}
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                <div>
                  <Label>Nome do Projeto</Label>
                  <Input value={form.project_name} onChange={e => setForm(p => ({ ...p, project_name: e.target.value }))} />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label>Tipo</Label>
                    <Select value={form.request_type} onValueChange={v => setForm(p => ({ ...p, request_type: v }))}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {REQUEST_TYPES.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label>Categoria</Label>
                    <Select value={form.category || "placeholder"} onValueChange={v => setForm(p => ({ ...p, category: v === "placeholder" ? "" : v }))}>
                      <SelectTrigger><SelectValue placeholder="Selecionar..." /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="placeholder" disabled>Selecionar...</SelectItem>
                        {CATEGORIES.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label>Prioridade</Label>
                    <Select value={form.priority} onValueChange={v => setForm(p => ({ ...p, priority: v }))}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {PRIORITIES.map(pr => <SelectItem key={pr} value={pr}>{pr}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label>Prazo</Label>
                    <Input type="date" value={form.deadline} onChange={e => setForm(p => ({ ...p, deadline: e.target.value }))} />
                  </div>
                </div>
                <div>
                  <Label>Descrição</Label>
                  <Textarea value={form.description} onChange={e => setForm(p => ({ ...p, description: e.target.value }))} rows={3} />
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Development + Indicators */}
        {hasDev && (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Desenvolvimento</CardTitle>
            </CardHeader>
            <CardContent className="text-sm">
              <div className="grid grid-cols-2 gap-x-6 gap-y-2 mb-4">
                <InfoRow label="Responsável" value={dev.assigned_to_name} />
                <InfoRow label="Versão Atual" value={`v${dev.current_version}`} />
                <InfoRow label="Início" value={new Date(dev.started_at).toLocaleDateString("pt-BR")} />
                <InfoRow label="Status" value={dev.status === "active" ? "Ativo" : "Concluído"} />
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-3 border-t">
                <MiniCard icon={Beaker} label="Fórmulas" value={formulas.length} color="text-purple-500" />
                <MiniCard icon={FlaskConical} label="Testes" value={`${testStats.approved}/${testStats.total}`} color="text-blue-500" extra={testStats.failed > 0 ? `${testStats.failed} falha(s)` : null} extraColor="text-red-500" />
                <MiniCard icon={Package} label="Amostras" value={samples.length} color="text-amber-500" />
                <MiniCard icon={DollarSign} label="Custo Unit." value={formulaCostData ? `R$ ${formulaCostData.custo_unitario.toFixed(2)}` : "—"} color="text-green-500" />
              </div>
            </CardContent>
          </Card>
        )}

        {/* Approval */}
        {hasDev && (
          <Card className={approval ? (approval.approved_by_client && approval.approved_by_internal ? "border-green-300 dark:border-green-800" : "border-orange-300 dark:border-orange-800") : ""}>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base flex items-center gap-2">
                  <ShieldCheck className="h-4 w-4" />
                  Aprovação
                </CardTitle>
                <Button size="sm" variant={showApproval ? "secondary" : "outline"} onClick={() => setShowApproval(!showApproval)} className="gap-1.5 text-xs" disabled={!canEdit}>
                  {showApproval ? <X className="h-3.5 w-3.5" /> : <Pencil className="h-3.5 w-3.5" />}
                  {showApproval ? "Fechar" : (approval ? "Editar" : "Registrar")}
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {!showApproval ? (
                approval ? (
                  <div className="space-y-2 text-sm">
                    <div className="flex items-center gap-3">
                      {approval.approved_by_client ? (
                        <Badge className="bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300 gap-1"><CheckCircle2 className="h-3 w-3" />Cliente Aprovou</Badge>
                      ) : (
                        <Badge className="bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400 gap-1"><Clock className="h-3 w-3" />Cliente Pendente</Badge>
                      )}
                      {approval.approved_by_internal ? (
                        <Badge className="bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300 gap-1"><CheckCircle2 className="h-3 w-3" />Aprovação Interna</Badge>
                      ) : (
                        <Badge className="bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400 gap-1"><Clock className="h-3 w-3" />Interno Pendente</Badge>
                      )}
                    </div>
                    {approval.notes && <p className="text-xs text-muted-foreground bg-muted/50 p-2 rounded mt-2">{approval.notes}</p>}
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">Nenhuma aprovação registrada.</p>
                )
              ) : (
                <div className="space-y-4">
                  <div className="flex items-center gap-6">
                    <div className="flex items-center gap-2">
                      <Switch checked={approvalForm.approved_by_client} onCheckedChange={v => setApprovalForm(p => ({ ...p, approved_by_client: v }))} />
                      <Label>Aprovação do Cliente</Label>
                    </div>
                    <div className="flex items-center gap-2">
                      <Switch checked={approvalForm.approved_by_internal} onCheckedChange={v => setApprovalForm(p => ({ ...p, approved_by_internal: v }))} />
                      <Label>Aprovação Interna</Label>
                    </div>
                  </div>
                  <div>
                    <Label>Observações</Label>
                    <Textarea value={approvalForm.notes} onChange={e => setApprovalForm(p => ({ ...p, notes: e.target.value }))} rows={2} />
                  </div>
                  <Button size="sm" onClick={saveApproval} disabled={savingApproval} className="gap-1.5">
                    <Save className="h-3.5 w-3.5" />
                    {savingApproval ? "Salvando..." : "Salvar Aprovação"}
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>

      {/* Right: Timeline */}
      <div>
        <Card className="sticky top-6">
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <History className="h-4 w-4" />
              Histórico
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-0">
              {history.map((h, i) => (
                <div key={h.id} className="flex gap-3 text-sm">
                  <div className="flex flex-col items-center">
                    <div className={`w-2.5 h-2.5 rounded-full mt-1.5 shrink-0 ${STATUS_CONFIG[h.to_status]?.dotColor || "bg-gray-400"}`} />
                    {i < history.length - 1 && <div className="w-px flex-1 bg-border" />}
                  </div>
                  <div className="pb-4">
                    <div className="font-medium text-xs">{STATUS_CONFIG[h.to_status]?.label || h.to_status}</div>
                    <div className="text-xs text-muted-foreground">{h.comment}</div>
                    <div className="text-[10px] text-muted-foreground mt-0.5">
                      {h.changed_by_name} • {new Date(h.created_at).toLocaleString("pt-BR")}
                    </div>
                  </div>
                </div>
              ))}
              {history.length === 0 && <p className="text-xs text-muted-foreground">Sem histórico</p>}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

/* Helpers */
function InfoRow({ label, value }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <span className="text-muted-foreground text-xs shrink-0">{label}:</span>
      <span className="text-sm font-medium">{value || "—"}</span>
    </div>
  );
}

function MiniCard({ icon: Icon, label, value, color, extra, extraColor }) {
  return (
    <div className="rounded-lg border p-3 text-center">
      <Icon className={`h-5 w-5 mx-auto mb-1 ${color}`} />
      <div className="text-base font-bold">{value}</div>
      <div className="text-[11px] text-muted-foreground">{label}</div>
      {extra && <div className={`text-[10px] ${extraColor || "text-muted-foreground"}`}>{extra}</div>}
    </div>
  );
}

/* ============ FORMULA TAB (Manipulação) ============ */
function FormulaTab({ devId, formulas, onRefresh, canEdit, clientInfo, req }) {
  const [showCreate, setShowCreate] = useState(false);
  const [formulaName, setFormulaName] = useState("");
  const [formulaNotes, setFormulaNotes] = useState("");
  const [formulaVolume, setFormulaVolume] = useState("");
  const [formulaVolumeUnit, setFormulaVolumeUnit] = useState("mL");
  const [formulaIndicePerdas, setFormulaIndicePerdas] = useState("0");
  const [formulaCotacao, setFormulaCotacao] = useState("6.00");
  const [saving, setSaving] = useState(false);
  const [expandedFormula, setExpandedFormula] = useState(formulas[0]?.id || null);
  const [newItem, setNewItem] = useState({ ingredient_name: "", percentage: "", price_per_kg: "", fornecedor: "", phase: "", function: "", catalog_id: "" });
  const [editingConfig, setEditingConfig] = useState(null);
  const [configForm, setConfigForm] = useState({});
  const [catalog, setCatalog] = useState([]);
  const [showSuggestions, setShowSuggestions] = useState(false);

  useEffect(() => {
    api.get("/pd/catalog").then(({ data }) => {
      setCatalog(Array.isArray(data) ? data : []);
    }).catch(() => setCatalog([]));
  }, []);

  const filteredCatalog = newItem.ingredient_name
    ? catalog.filter(c => c.nome.toLowerCase().includes(newItem.ingredient_name.toLowerCase()) ||
                          (c.inci && c.inci.toLowerCase().includes(newItem.ingredient_name.toLowerCase())))
    : catalog;

  const pickFromCatalog = (cat) => {
    setNewItem({
      ingredient_name: cat.nome,
      percentage: newItem.percentage,
      price_per_kg: String(cat.preco_rs_kg || 0),
      fornecedor: cat.fornecedor || "",
      phase: newItem.phase,
      function: newItem.function,
      catalog_id: cat.id,
    });
    setShowSuggestions(false);
  };

  const createFormula = async () => {
    if (!formulaName.trim()) return toast.error("Nome é obrigatório");
    setSaving(true);
    try {
      await api.post(`/pd/developments/${devId}/formulas`, {
        name: formulaName,
        notes: formulaNotes,
        volume: parseFloat(formulaVolume) || 0,
        volume_unit: formulaVolumeUnit,
        indice_perdas: parseFloat(formulaIndicePerdas) || 0,
        cotacao_usd: parseFloat(formulaCotacao) || 6.00,
      });
      toast.success("Fórmula criada!");
      setFormulaName(""); setFormulaNotes(""); setFormulaVolume(""); setShowCreate(false);
      onRefresh();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Erro");
    } finally { setSaving(false); }
  };

  const addItem = async (formulaId) => {
    if (!newItem.ingredient_name || !newItem.percentage) return toast.error("Preencha ingrediente e %");
    try {
      await api.post(`/pd/formulas/${formulaId}/items`, {
        ingredient_name: newItem.ingredient_name,
        percentage: parseFloat(newItem.percentage),
        price_per_kg: parseFloat(newItem.price_per_kg) || 0,
        fornecedor: newItem.fornecedor || "",
        phase: newItem.phase,
        function: newItem.function,
        catalog_id: newItem.catalog_id || null,
      });
      toast.success("Ingrediente adicionado!");
      setNewItem({ ingredient_name: "", percentage: "", price_per_kg: "", fornecedor: "", phase: "", function: "", catalog_id: "" });
      setShowSuggestions(false);
      onRefresh();
    } catch (err) { toast.error("Erro ao adicionar"); }
  };

  const deleteItem = async (itemId) => {
    try { await api.delete(`/pd/formula-items/${itemId}`); onRefresh(); }
    catch (err) { toast.error("Erro ao remover"); }
  };

  const startEditConfig = (f) => {
    setEditingConfig(f.id);
    setConfigForm({
      volume: f.volume || "",
      volume_unit: f.volume_unit || "mL",
      indice_perdas: f.indice_perdas || 0,
      cotacao_usd: f.cotacao_usd || 6.00,
    });
  };

  const saveConfig = async (formulaId) => {
    try {
      await api.put(`/pd/formulas/${formulaId}`, {
        volume: parseFloat(configForm.volume) || 0,
        volume_unit: configForm.volume_unit,
        indice_perdas: parseFloat(configForm.indice_perdas) || 0,
        cotacao_usd: parseFloat(configForm.cotacao_usd) || 6.00,
      });
      toast.success("Configuração salva!");
      setEditingConfig(null);
      onRefresh();
    } catch (err) { toast.error("Erro ao salvar"); }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold">Manipulação / Formulação ({formulas.length})</h3>
        <Button size="sm" onClick={() => setShowCreate(true)} className="gap-1.5" disabled={!canEdit}>
          <Plus className="h-3.5 w-3.5" /> Nova Versão
        </Button>
      </div>

      {showCreate && (
        <Card className="border-primary/50">
          <CardContent className="p-4 space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Nome da Fórmula *</Label>
                <Input value={formulaName} onChange={e => setFormulaName(e.target.value)} placeholder="Ex: Aromatizante v1" />
              </div>
              <div>
                <Label>Volume</Label>
                <div className="flex gap-2">
                  <Input type="number" value={formulaVolume} onChange={e => setFormulaVolume(e.target.value)} placeholder="200" className="flex-1" />
                  <Select value={formulaVolumeUnit} onValueChange={setFormulaVolumeUnit}>
                    <SelectTrigger className="w-20"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="mL">mL</SelectItem>
                      <SelectItem value="L">L</SelectItem>
                      <SelectItem value="g">g</SelectItem>
                      <SelectItem value="kg">kg</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div>
                <Label>Índice de Perdas e Acréscimos (%)</Label>
                <Input type="number" step="0.1" value={formulaIndicePerdas} onChange={e => setFormulaIndicePerdas(e.target.value)} placeholder="10" />
              </div>
              <div>
                <Label>Cotação US$</Label>
                <Input type="number" step="0.01" value={formulaCotacao} onChange={e => setFormulaCotacao(e.target.value)} placeholder="6.00" />
              </div>
            </div>
            <div>
              <Label>Notas</Label>
              <Textarea value={formulaNotes} onChange={e => setFormulaNotes(e.target.value)} placeholder="Observações..." rows={2} />
            </div>
            <div className="flex gap-2">
              <Button size="sm" onClick={createFormula} disabled={saving}>{saving ? "Criando..." : "Criar Fórmula"}</Button>
              <Button size="sm" variant="ghost" onClick={() => setShowCreate(false)}>Cancelar</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {formulas.map(f => {
        const items = f.items || [];
        const totalPct = items.reduce((s, it) => s + (it.percentage || 0), 0);
        const totalCostBrl = items.reduce((s, it) => s + (it.cost_brl || 0), 0);
        const totalPriceSum = items.reduce((s, it) => s + (it.price_per_kg || 0), 0);
        const isOk = Math.abs(totalPct - 100) < 0.5;
        const open = expandedFormula === f.id;
        
        const volume = f.volume || 0;
        const volumeUnit = f.volume_unit || "mL";
        const volumeKg = volumeUnit === "mL" ? volume / 1000 : (volumeUnit === "L" ? volume : (volumeUnit === "g" ? volume / 1000 : volume));
        const custoUnit = volumeKg > 0 ? totalCostBrl * volumeKg : totalCostBrl;
        const indicePerdas = f.indice_perdas || 0;
        const custoComPerdas = indicePerdas > 0 ? custoUnit * (1 + indicePerdas / 100) : custoUnit;

        return (
          <Card key={f.id} className={open ? "border-primary/30" : "hover:border-primary/20 transition-colors"}>
            <CardHeader className="pb-2 cursor-pointer" onClick={() => setExpandedFormula(open ? null : f.id)}>
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Badge variant="outline" className="text-xs font-mono">v{f.version}</Badge>
                  {f.name}
                </CardTitle>
                <div className="flex items-center gap-3">
                  {volume > 0 && (
                    <span className="text-xs text-muted-foreground">{volume} {volumeUnit}</span>
                  )}
                  <span className="text-xs font-bold text-green-600">
                    R$ {custoUnit.toFixed(2)}
                  </span>
                  <Badge variant="secondary" className="text-[10px]">{items.length} itens</Badge>
                </div>
              </div>
            </CardHeader>
            {open && (
              <CardContent className="pt-0 space-y-3">
                {/* Formula Config Header (like spreadsheet) */}
                <div className="bg-muted/50 rounded-lg p-3 border">
                  {editingConfig === f.id ? (
                    <div className="grid grid-cols-4 gap-3">
                      <div>
                        <Label className="text-[11px]">Volume</Label>
                        <div className="flex gap-1">
                          <Input type="number" value={configForm.volume} onChange={e => setConfigForm(p => ({ ...p, volume: e.target.value }))} className="h-8 text-sm" />
                          <Select value={configForm.volume_unit} onValueChange={v => setConfigForm(p => ({ ...p, volume_unit: v }))}>
                            <SelectTrigger className="w-16 h-8 text-xs"><SelectValue /></SelectTrigger>
                            <SelectContent>
                              <SelectItem value="mL">mL</SelectItem>
                              <SelectItem value="L">L</SelectItem>
                              <SelectItem value="g">g</SelectItem>
                              <SelectItem value="kg">kg</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                      </div>
                      <div>
                        <Label className="text-[11px]">Índice Perdas (%)</Label>
                        <Input type="number" step="0.1" value={configForm.indice_perdas} onChange={e => setConfigForm(p => ({ ...p, indice_perdas: e.target.value }))} className="h-8 text-sm" />
                      </div>
                      <div>
                        <Label className="text-[11px]">Cotação US$</Label>
                        <Input type="number" step="0.01" value={configForm.cotacao_usd} onChange={e => setConfigForm(p => ({ ...p, cotacao_usd: e.target.value }))} className="h-8 text-sm" />
                      </div>
                      <div className="flex items-end gap-1">
                        <Button size="sm" className="h-8" onClick={() => saveConfig(f.id)}><Save className="h-3 w-3" /></Button>
                        <Button size="sm" variant="ghost" className="h-8" onClick={() => setEditingConfig(null)}><X className="h-3 w-3" /></Button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-6 text-xs">
                        <span><b>Produto:</b> {clientInfo?.produto || req.project_name}</span>
                        <span><b>Cliente:</b> {clientInfo?.nome_cliente || req.client_name || "—"}</span>
                        <span><b>Volume:</b> {volume > 0 ? `${volume} ${volumeUnit}` : "—"}</span>
                        <span><b>Índice Perdas:</b> {indicePerdas > 0 ? `${indicePerdas}%` : "—"}</span>
                        <span><b>Cotação US$:</b> {(f.cotacao_usd || 6.00).toFixed(2)}</span>
                      </div>
                      {canEdit && (
                        <Button size="sm" variant="ghost" className="h-7 text-xs gap-1" onClick={(e) => { e.stopPropagation(); startEditConfig(f); }}>
                          <Settings2 className="h-3 w-3" /> Config
                        </Button>
                      )}
                    </div>
                  )}
                </div>

                {f.notes && <p className="text-xs text-muted-foreground italic">{f.notes}</p>}

                {/* Spreadsheet-like table with cost columns */}
                <div className="border rounded-md overflow-hidden">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-[#0A0A0B] text-white text-xs">
                        <th className="text-left p-2 font-medium">Formulação</th>
                        <th className="text-left p-2 font-medium w-32">Fornecedor</th>
                        <th className="text-right p-2 font-medium w-24">%Fórmula</th>
                        <th className="text-right p-2 font-medium w-24">Qtd/Lote</th>
                        <th className="text-right p-2 font-medium w-28">Preço R$ (Kg)</th>
                        <th className="text-right p-2 font-medium w-24">Custo R$</th>
                        <th className="text-right p-2 font-medium w-28">Custo Kg/U$</th>
                        <th className="text-right p-2 font-medium w-24">% de Custo</th>
                        <th className="w-10"></th>
                      </tr>
                    </thead>
                    <tbody>
                      {items.map(item => {
                        const costPct = totalCostBrl > 0 ? (item.cost_brl / totalCostBrl * 100) : 0;
                        const qtyLote = volume > 0 ? (volume * (item.percentage || 0) / 100) : 0;
                        const qtyLabel = qtyLote > 0 ? `${qtyLote.toFixed(3)} ${volumeUnit}` : "—";
                        return (
                          <tr key={item.id} className="border-t hover:bg-muted/30">
                            <td className="p-2 font-medium">{item.ingredient_name}</td>
                            <td className="p-2 text-xs text-muted-foreground">{item.fornecedor || "—"}</td>
                            <td className="p-2 text-right font-mono text-xs">{(item.percentage || 0).toFixed(3)}</td>
                            <td className="p-2 text-right font-mono text-xs text-blue-600">{qtyLabel}</td>
                            <td className="p-2 text-right font-mono text-xs">{(item.price_per_kg || 0).toFixed(2)}</td>
                            <td className="p-2 text-right font-mono text-xs">{(item.cost_brl || 0).toFixed(2)}</td>
                            <td className="p-2 text-right font-mono text-xs">{(item.cost_kg_usd || 0).toFixed(2)}</td>
                            <td className="p-2 text-right font-mono text-xs">{costPct.toFixed(1)}%</td>
                            <td className="p-2 text-center">
                              {canEdit && (
                                <button onClick={() => deleteItem(item.id)} className="text-muted-foreground hover:text-red-500 transition-colors">
                                  <Trash2 className="h-3.5 w-3.5" />
                                </button>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                      {items.length === 0 && (
                        <tr><td colSpan={9} className="p-4 text-center text-xs text-muted-foreground">Nenhum ingrediente. Adicione abaixo.</td></tr>
                      )}
                    </tbody>
                    <tfoot>
                      <tr className="border-t-2 bg-muted/30 font-bold">
                        <td className="p-2 text-xs">Custo Unit.</td>
                        <td className="p-2"></td>
                        <td className={`p-2 text-right font-mono text-xs ${isOk ? "text-green-600" : "text-amber-600"}`}>{totalPct.toFixed(2)}</td>
                        <td className="p-2 text-right font-mono text-xs text-blue-600">{volume > 0 ? `${volume} ${volumeUnit}` : "—"}</td>
                        <td className="p-2 text-right font-mono text-xs">{totalPriceSum.toFixed(2)}</td>
                        <td className="p-2 text-right font-mono text-xs bg-muted">
                          <span className="text-green-700 font-bold">R$ {custoUnit.toFixed(2)}</span>
                        </td>
                        <td className="p-2"></td>
                        <td className="p-2 text-right font-mono text-xs">100,00%</td>
                        <td className="p-2"></td>
                      </tr>
                      {indicePerdas > 0 && (
                        <tr className="bg-muted/20">
                          <td colSpan={4} className="p-2 text-xs text-muted-foreground">Com índice de perdas ({indicePerdas}%)</td>
                          <td className="p-2 text-right font-mono text-xs font-bold text-orange-600">R$ {custoComPerdas.toFixed(2)}</td>
                          <td colSpan={4}></td>
                        </tr>
                      )}
                    </tfoot>
                  </table>
                </div>

                {/* Add ingredient row */}
                {canEdit && (
                  <div className="flex gap-2 items-end p-3 bg-muted/30 rounded-lg border border-dashed relative">
                    <div className="flex-1 relative">
                      <Label className="text-[11px] text-muted-foreground flex items-center gap-1">
                        Ingrediente
                        {newItem.catalog_id && (
                          <Badge className="text-[9px] h-3.5 px-1 bg-green-500/20 text-green-700 border-green-300">do banco</Badge>
                        )}
                      </Label>
                      <Input value={newItem.ingredient_name}
                        onChange={e => {
                          setNewItem(p => ({ ...p, ingredient_name: e.target.value, catalog_id: "", fornecedor: "" }));
                          setShowSuggestions(true);
                        }}
                        onFocus={() => setShowSuggestions(true)}
                        onBlur={() => setTimeout(() => setShowSuggestions(false), 200)}
                        placeholder={catalog.length > 0 ? "Digite ou escolha do banco de custos..." : "Nome do ingrediente"}
                        className="h-8 text-sm" />
                      {showSuggestions && filteredCatalog.length > 0 && (
                        <div className="absolute top-full left-0 right-0 mt-1 bg-popover border rounded-md shadow-lg z-50 max-h-64 overflow-y-auto">
                          {filteredCatalog.slice(0, 15).map(cat => (
                            <button
                              key={cat.id}
                              type="button"
                              onMouseDown={(e) => { e.preventDefault(); pickFromCatalog(cat); }}
                              className="w-full text-left px-3 py-2 hover:bg-muted border-b last:border-0 flex items-center justify-between gap-2"
                            >
                              <div className="min-w-0">
                                <div className="text-sm font-medium truncate">{cat.nome}</div>
                                <div className="text-[10px] text-muted-foreground truncate">
                                  {cat.inci && <>INCI: {cat.inci}</>}
                                  {cat.fornecedor && <> • {cat.fornecedor}</>}
                                  {cat.categoria && <> • {cat.categoria}</>}
                                </div>
                              </div>
                              <span className="text-xs font-mono font-semibold shrink-0">
                                R$ {(cat.preco_rs_kg || 0).toFixed(2)}/{cat.unidade || "kg"}
                              </span>
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                    <div className="w-28">
                      <Label className="text-[11px] text-muted-foreground">Fornecedor</Label>
                      <Input value={newItem.fornecedor}
                        onChange={e => setNewItem(p => ({ ...p, fornecedor: e.target.value }))}
                        placeholder="Fornecedor" className="h-8 text-sm" />
                    </div>
                    <div className="w-20">
                      <Label className="text-[11px] text-muted-foreground">%Fórmula</Label>
                      <Input type="number" step="0.001" value={newItem.percentage}
                        onChange={e => setNewItem(p => ({ ...p, percentage: e.target.value }))}
                        placeholder="0.000" className="h-8 text-sm font-mono" />
                    </div>
                    <div className="w-24">
                      <Label className="text-[11px] text-muted-foreground">Preço R$/Kg</Label>
                      <Input type="number" step="0.01" value={newItem.price_per_kg}
                        onChange={e => setNewItem(p => ({ ...p, price_per_kg: e.target.value, catalog_id: "" }))}
                        placeholder="0.00" className="h-8 text-sm font-mono" />
                    </div>
                    <Button size="sm" className="h-8 gap-1" onClick={() => addItem(f.id)}>
                      <Plus className="h-3 w-3" /> Adicionar
                    </Button>
                  </div>
                )}
              </CardContent>
            )}
          </Card>
        );
      })}

      {formulas.length === 0 && !showCreate && (
        <EmptyState icon={Beaker} title="Nenhuma fórmula criada" subtitle="Crie a primeira versão da manipulação" />
      )}
    </div>
  );
}

/* ============ FICHA TÉCNICA TAB ============ */
const FT_PARAMS = [
  { key: "aspecto", label: "Aspecto" },
  { key: "cor", label: "Cor" },
  { key: "densidade", label: "Densidade" },
  { key: "odor", label: "Odor" },
  { key: "ph", label: "pH" },
  { key: "teor_alcool", label: "Teor de Álcool" },
];

function FichaTecnicaTab({ reqId, formulas, req, dev, canEdit }) {
  const [analise, setAnalise] = useState({});
  const [form, setForm] = useState({
    produto: "", lote: "", data_fabricacao: "", validade: "", quantidade: "",
    elaboracao: "", resp_tecnico: "", status_aprovacao: "",
    aspecto: { especificacao: "", resultado: "", pa: "" },
    cor: { especificacao: "", resultado: "", pa: "" },
    densidade: { especificacao: "", resultado: "", pa: "" },
    odor: { especificacao: "", resultado: "", pa: "" },
    ph: { especificacao: "", resultado: "", pa: "" },
    teor_alcool: { especificacao: "", resultado: "", pa: "" },
  });
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.get(`/pd/requests/${reqId}/ficha-tecnica-ui`).then(({ data }) => {
      const a = data.analise || {};
      setAnalise(a);
      setForm(prev => ({
        produto: a.produto || req.project_name || "",
        lote: a.lote || "",
        data_fabricacao: a.data_fabricacao || "",
        validade: a.validade || "",
        quantidade: a.quantidade || "",
        elaboracao: a.elaboracao || "",
        resp_tecnico: a.resp_tecnico || "",
        status_aprovacao: a.status_aprovacao || "",
        aspecto: a.aspecto || { especificacao: "", resultado: "", pa: "" },
        cor: a.cor || { especificacao: "", resultado: "", pa: "" },
        densidade: a.densidade || { especificacao: "", resultado: "", pa: "" },
        odor: a.odor || { especificacao: "", resultado: "", pa: "" },
        ph: a.ph || { especificacao: "", resultado: "", pa: "" },
        teor_alcool: a.teor_alcool || { especificacao: "", resultado: "", pa: "" },
      }));
    }).catch(() => {}).finally(() => setLoading(false));
  }, [reqId, req.project_name]);

  const setParam = (key, field, val) => {
    setForm(prev => ({ ...prev, [key]: { ...prev[key], [field]: val } }));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.put(`/pd/requests/${reqId}/ficha-tecnica-ui`, form);
      toast.success("Ficha Técnica salva!");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Erro ao salvar");
    } finally { setSaving(false); }
  };

  const latest = formulas?.[0];
  const items = latest?.items || [];

  if (loading) return <div className="flex items-center justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>;

  return (
    <div className="space-y-6 max-w-4xl" data-testid="ficha-tecnica-tab">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold flex items-center gap-2">
            <ClipboardList className="h-4 w-4 text-primary" />
            Ficha Técnica de Manipulação
          </h3>
          <p className="text-xs text-muted-foreground mt-0.5">Laudo analítico do produto fabricado</p>
        </div>
        {canEdit && (
          <Button size="sm" onClick={handleSave} disabled={saving} className="gap-1.5" data-testid="ft-save-btn">
            {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
            Salvar Ficha
          </Button>
        )}
      </div>

      {/* Identificação */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Identificação do Produto</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {[
            { key: "produto", label: "Produto" },
            { key: "lote", label: "Lote" },
            { key: "data_fabricacao", label: "Data de Fabricação" },
            { key: "validade", label: "Validade" },
            { key: "quantidade", label: "Quantidade" },
          ].map(({ key, label }) => (
            <div key={key}>
              <Label className="text-xs text-muted-foreground">{label}</Label>
              <Input
                value={form[key] || ""}
                onChange={e => setForm(p => ({ ...p, [key]: e.target.value }))}
                placeholder={label}
                className="h-8 text-sm mt-1"
                disabled={!canEdit}
                data-testid={`ft-field-${key}`}
              />
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Tabela de Análise do Produto Fabricado */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Análise do Produto Fabricado</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="border rounded-b-md overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-[#0A0A0B] text-white text-xs">
                  <th className="text-left p-3 font-medium w-32">TESTE</th>
                  <th className="text-left p-3 font-medium">ESPECIFICAÇÃO</th>
                  <th className="text-left p-3 font-medium">RESULTADO</th>
                  <th className="text-center p-3 font-medium w-36">PA</th>
                </tr>
              </thead>
              <tbody>
                {FT_PARAMS.map(({ key, label }) => (
                  <tr key={key} className="border-t hover:bg-muted/20">
                    <td className="p-3 font-medium text-sm">{label}</td>
                    <td className="p-2">
                      <Input
                        value={form[key]?.especificacao || ""}
                        onChange={e => setParam(key, "especificacao", e.target.value)}
                        placeholder="Especificação..."
                        className="h-7 text-xs border-0 bg-transparent focus:bg-background focus:border"
                        disabled={!canEdit}
                        data-testid={`ft-${key}-especificacao`}
                      />
                    </td>
                    <td className="p-2">
                      <Input
                        value={form[key]?.resultado || ""}
                        onChange={e => setParam(key, "resultado", e.target.value)}
                        placeholder="Resultado medido..."
                        className="h-7 text-xs border-0 bg-transparent focus:bg-background focus:border"
                        disabled={!canEdit}
                        data-testid={`ft-${key}-resultado`}
                      />
                    </td>
                    <td className="p-2 text-center">
                      {canEdit ? (
                        <Select value={form[key]?.pa || ""} onValueChange={v => setParam(key, "pa", v)}>
                          <SelectTrigger className="h-7 text-xs w-full" data-testid={`ft-${key}-pa`}>
                            <SelectValue placeholder="—" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="Conforme">Conforme</SelectItem>
                            <SelectItem value="Não Conforme">Não Conforme</SelectItem>
                            <SelectItem value="N/A">N/A</SelectItem>
                          </SelectContent>
                        </Select>
                      ) : (
                        <Badge className={
                          form[key]?.pa === "Conforme" ? "bg-green-500/20 text-green-700 border-green-300" :
                          form[key]?.pa === "Não Conforme" ? "bg-red-500/20 text-red-700 border-red-300" :
                          "bg-muted text-muted-foreground"
                        }>
                          {form[key]?.pa || "—"}
                        </Badge>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Tabela de Formulação */}
      {items.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold uppercase tracking-wide text-muted-foreground flex items-center justify-between">
              Formulação
              {latest && <Badge variant="outline" className="font-mono text-xs">v{latest.version}</Badge>}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-hidden border-t">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-muted text-muted-foreground">
                    <th className="text-left p-2 font-medium">Ingrediente</th>
                    <th className="text-left p-2 font-medium">Fornecedor</th>
                    <th className="text-right p-2 font-medium w-20">%Fórmula</th>
                    <th className="text-right p-2 font-medium w-24">Qtd/Lote</th>
                    <th className="text-right p-2 font-medium w-24">Custo R$</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item, i) => {
                    const vol = latest?.volume || 0;
                    const vu = latest?.volume_unit || "mL";
                    const qty = vol > 0 ? `${(vol * (item.percentage || 0) / 100).toFixed(3)} ${vu}` : "—";
                    return (
                      <tr key={item.id || i} className="border-t hover:bg-muted/20">
                        <td className="p-2 font-medium">{item.ingredient_name}</td>
                        <td className="p-2 text-muted-foreground">{item.fornecedor || "—"}</td>
                        <td className="p-2 text-right font-mono">{(item.percentage || 0).toFixed(3)}</td>
                        <td className="p-2 text-right font-mono text-blue-600">{qty}</td>
                        <td className="p-2 text-right font-mono">R$ {(item.cost_brl || 0).toFixed(2)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Descrição da Elaboração */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Descrição da Elaboração</CardTitle>
        </CardHeader>
        <CardContent>
          <Textarea
            value={form.elaboracao || ""}
            onChange={e => setForm(p => ({ ...p, elaboracao: e.target.value }))}
            placeholder="Descreva o modo de preparo passo a passo..."
            rows={5}
            disabled={!canEdit}
            data-testid="ft-elaboracao"
          />
        </CardContent>
      </Card>

      {/* Aprovação */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Aprovação</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex gap-4">
            <button
              type="button"
              disabled={!canEdit}
              onClick={() => canEdit && setForm(p => ({ ...p, status_aprovacao: "aprovado" }))}
              data-testid="ft-aprovado-btn"
              className={`flex items-center gap-2 px-4 py-2 rounded-lg border-2 text-sm font-semibold transition-all ${
                form.status_aprovacao === "aprovado"
                  ? "border-green-500 bg-green-50 text-green-700"
                  : "border-muted hover:border-green-300 text-muted-foreground"
              } ${!canEdit ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}`}
            >
              <CheckSquare className="h-4 w-4" /> APROVADO
            </button>
            <button
              type="button"
              disabled={!canEdit}
              onClick={() => canEdit && setForm(p => ({ ...p, status_aprovacao: "reprovado" }))}
              data-testid="ft-reprovado-btn"
              className={`flex items-center gap-2 px-4 py-2 rounded-lg border-2 text-sm font-semibold transition-all ${
                form.status_aprovacao === "reprovado"
                  ? "border-red-500 bg-red-50 text-red-700"
                  : "border-muted hover:border-red-300 text-muted-foreground"
              } ${!canEdit ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}`}
            >
              <XSquare className="h-4 w-4" /> REPROVADO
            </button>
          </div>
          <div className="max-w-xs">
            <Label className="text-xs text-muted-foreground">Resp. Técnico</Label>
            <Input
              value={form.resp_tecnico || ""}
              onChange={e => setForm(p => ({ ...p, resp_tecnico: e.target.value }))}
              placeholder="Nome do responsável técnico"
              className="mt-1 h-9"
              disabled={!canEdit}
              data-testid="ft-resp-tecnico"
            />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

/* ============ TESTS TAB (Unified form - all types at once) ============ */
function TestsTab({ devId, labResults, onRefresh, canEdit }) {
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    estabilidade: {},
    ph: {},
    viscosidade: {},
    sensorial: {},
    compatibilidade: {},
  });

  useEffect(() => {
    if (labResults) {
      setForm({
        estabilidade: labResults.estabilidade || {},
        ph: labResults.ph || {},
        viscosidade: labResults.viscosidade || {},
        sensorial: labResults.sensorial || {},
        compatibilidade: labResults.compatibilidade || {},
      });
    }
  }, [labResults]);

  const updateField = (section, key, value) => {
    setForm(prev => ({
      ...prev,
      [section]: { ...prev[section], [key]: value }
    }));
  };

  const saveAll = async () => {
    setSaving(true);
    try {
      await api.put(`/pd/developments/${devId}/lab-results`, form);
      toast.success("Testes salvos com sucesso!");
      onRefresh();
    } catch (err) {
      toast.error("Erro ao salvar testes");
    } finally {
      setSaving(false);
    }
  };

  const hasData = labResults && (
    Object.keys(labResults.estabilidade || {}).length > 0 ||
    Object.keys(labResults.ph || {}).length > 0 ||
    Object.keys(labResults.viscosidade || {}).length > 0 ||
    Object.keys(labResults.sensorial || {}).length > 0 ||
    Object.keys(labResults.compatibilidade || {}).length > 0
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold">Testes de Laboratório</h3>
        {hasData && labResults?.updated_by_name && (
          <span className="text-[11px] text-muted-foreground">
            Última atualização: {labResults.updated_by_name} • {new Date(labResults.updated_at).toLocaleString("pt-BR")}
          </span>
        )}
      </div>

      {/* ESTABILIDADE */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-purple-500" />
            Estabilidade
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label className="text-xs text-muted-foreground">Condição</Label>
              <Input value={form.estabilidade.condicao || ""} onChange={e => updateField("estabilidade", "condicao", e.target.value)} placeholder="Ex: 45°C / 90 dias" disabled={!canEdit} />
            </div>
            <div>
              <Label className="text-xs text-muted-foreground">Aspecto</Label>
              <Input value={form.estabilidade.aspecto || ""} onChange={e => updateField("estabilidade", "aspecto", e.target.value)} placeholder="Normal, separação, etc." disabled={!canEdit} />
            </div>
            <div>
              <Label className="text-xs text-muted-foreground">Cor</Label>
              <Input value={form.estabilidade.cor || ""} onChange={e => updateField("estabilidade", "cor", e.target.value)} placeholder="Inalterada, escurecida, etc." disabled={!canEdit} />
            </div>
            <div>
              <Label className="text-xs text-muted-foreground">Odor</Label>
              <Input value={form.estabilidade.odor || ""} onChange={e => updateField("estabilidade", "odor", e.target.value)} placeholder="Inalterado, alterado, etc." disabled={!canEdit} />
            </div>
            <div className="col-span-2">
              <Label className="text-xs text-muted-foreground">Observações</Label>
              <Textarea value={form.estabilidade.observacoes || ""} onChange={e => updateField("estabilidade", "observacoes", e.target.value)} placeholder="Notas adicionais" rows={2} disabled={!canEdit} />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* pH */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-blue-500" />
            pH
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label className="text-xs text-muted-foreground">Valor Medido</Label>
              <Input value={form.ph.valor_medido || ""} onChange={e => updateField("ph", "valor_medido", e.target.value)} placeholder="Ex: 5.5" disabled={!canEdit} />
            </div>
            <div>
              <Label className="text-xs text-muted-foreground">Faixa Aceitável</Label>
              <Input value={form.ph.faixa_aceitavel || ""} onChange={e => updateField("ph", "faixa_aceitavel", e.target.value)} placeholder="Ex: 5.0 - 6.0" disabled={!canEdit} />
            </div>
            <div>
              <Label className="text-xs text-muted-foreground">Temperatura (°C)</Label>
              <Input value={form.ph.temperatura || ""} onChange={e => updateField("ph", "temperatura", e.target.value)} placeholder="Ex: 25" disabled={!canEdit} />
            </div>
            <div>
              <Label className="text-xs text-muted-foreground">Observações</Label>
              <Input value={form.ph.observacoes || ""} onChange={e => updateField("ph", "observacoes", e.target.value)} placeholder="Notas adicionais" disabled={!canEdit} />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* VISCOSIDADE */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-amber-500" />
            Viscosidade
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label className="text-xs text-muted-foreground">Valor Medido</Label>
              <Input value={form.viscosidade.valor_medido || ""} onChange={e => updateField("viscosidade", "valor_medido", e.target.value)} placeholder="Ex: 15000" disabled={!canEdit} />
            </div>
            <div>
              <Label className="text-xs text-muted-foreground">Unidade</Label>
              <Input value={form.viscosidade.unidade || ""} onChange={e => updateField("viscosidade", "unidade", e.target.value)} placeholder="Ex: cP, mPa.s" disabled={!canEdit} />
            </div>
            <div>
              <Label className="text-xs text-muted-foreground">Spindle / Velocidade</Label>
              <Input value={form.viscosidade.spindle || ""} onChange={e => updateField("viscosidade", "spindle", e.target.value)} placeholder="Ex: S64 / 20 rpm" disabled={!canEdit} />
            </div>
            <div>
              <Label className="text-xs text-muted-foreground">Temperatura (°C)</Label>
              <Input value={form.viscosidade.temperatura || ""} onChange={e => updateField("viscosidade", "temperatura", e.target.value)} placeholder="Ex: 25" disabled={!canEdit} />
            </div>
            <div className="col-span-2">
              <Label className="text-xs text-muted-foreground">Observações</Label>
              <Textarea value={form.viscosidade.observacoes || ""} onChange={e => updateField("viscosidade", "observacoes", e.target.value)} placeholder="Notas adicionais" rows={2} disabled={!canEdit} />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* SENSORIAL */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-pink-500" />
            Sensorial
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label className="text-xs text-muted-foreground">Aspecto</Label>
              <Input value={form.sensorial.aspecto || ""} onChange={e => updateField("sensorial", "aspecto", e.target.value)} placeholder="Creme, líquido, gel, etc." disabled={!canEdit} />
            </div>
            <div>
              <Label className="text-xs text-muted-foreground">Cor</Label>
              <Input value={form.sensorial.cor || ""} onChange={e => updateField("sensorial", "cor", e.target.value)} placeholder="Branca, translúcida, etc." disabled={!canEdit} />
            </div>
            <div>
              <Label className="text-xs text-muted-foreground">Odor</Label>
              <Input value={form.sensorial.odor || ""} onChange={e => updateField("sensorial", "odor", e.target.value)} placeholder="Agradável, suave, etc." disabled={!canEdit} />
            </div>
            <div>
              <Label className="text-xs text-muted-foreground">Toque</Label>
              <Input value={form.sensorial.toque || ""} onChange={e => updateField("sensorial", "toque", e.target.value)} placeholder="Sedoso, leve, pegajoso, etc." disabled={!canEdit} />
            </div>
            <div>
              <Label className="text-xs text-muted-foreground">Espalhabilidade</Label>
              <Input value={form.sensorial.espalhabilidade || ""} onChange={e => updateField("sensorial", "espalhabilidade", e.target.value)} placeholder="Boa, excelente, etc." disabled={!canEdit} />
            </div>
            <div>
              <Label className="text-xs text-muted-foreground">Observações</Label>
              <Input value={form.sensorial.observacoes || ""} onChange={e => updateField("sensorial", "observacoes", e.target.value)} placeholder="Notas adicionais" disabled={!canEdit} />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* COMPATIBILIDADE */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-green-500" />
            Compatibilidade
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label className="text-xs text-muted-foreground">Material Testado</Label>
              <Input value={form.compatibilidade.material_testado || ""} onChange={e => updateField("compatibilidade", "material_testado", e.target.value)} placeholder="Ex: PET, Alumínio, PP" disabled={!canEdit} />
            </div>
            <div>
              <Label className="text-xs text-muted-foreground">Tempo (dias)</Label>
              <Input value={form.compatibilidade.tempo_dias || ""} onChange={e => updateField("compatibilidade", "tempo_dias", e.target.value)} placeholder="Ex: 30, 60, 90" disabled={!canEdit} />
            </div>
            <div>
              <Label className="text-xs text-muted-foreground">Resultado</Label>
              <Input value={form.compatibilidade.resultado || ""} onChange={e => updateField("compatibilidade", "resultado", e.target.value)} placeholder="Compatível, incompatível, etc." disabled={!canEdit} />
            </div>
            <div>
              <Label className="text-xs text-muted-foreground">Observações</Label>
              <Input value={form.compatibilidade.observacoes || ""} onChange={e => updateField("compatibilidade", "observacoes", e.target.value)} placeholder="Notas adicionais" disabled={!canEdit} />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Save Button */}
      {canEdit && (
        <div className="flex justify-end pt-2">
          <Button onClick={saveAll} disabled={saving} className="gap-2 px-8">
            <Save className="h-4 w-4" />
            {saving ? "Salvando..." : "Salvar Todos os Testes"}
          </Button>
        </div>
      )}
    </div>
  );
}

/* ============ SAMPLES TAB ============ */
function SamplesTab({ devId, samples, formulas, onRefresh, canEdit }) {
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ formula_version: formulas[0]?.version || 1, sent_to_client: false, feedback: "" });
  const [editingId, setEditingId] = useState(null);
  const [editFeedback, setEditFeedback] = useState("");

  const createSample = async () => {
    try {
      await api.post(`/pd/developments/${devId}/samples`, form);
      toast.success("Amostra registrada!");
      setShowCreate(false);
      onRefresh();
    } catch (err) { toast.error("Erro ao registrar amostra"); }
  };

  const updateSample = async (sampleId, updates) => {
    try {
      await api.put(`/pd/samples/${sampleId}`, updates);
      toast.success("Amostra atualizada!");
      setEditingId(null);
      onRefresh();
    } catch (err) { toast.error("Erro"); }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold">Amostras ({samples.length})</h3>
        <Button size="sm" onClick={() => setShowCreate(true)} className="gap-1.5" disabled={!canEdit}>
          <Plus className="h-3.5 w-3.5" /> Nova Amostra
        </Button>
      </div>

      {showCreate && (
        <Card className="border-primary/50">
          <CardContent className="p-4 space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Versão da Fórmula</Label>
                <Select value={String(form.formula_version)} onValueChange={v => setForm(p => ({ ...p, formula_version: parseInt(v) }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {formulas.length > 0 ? formulas.map(f => <SelectItem key={f.version} value={String(f.version)}>v{f.version} — {f.name}</SelectItem>) : <SelectItem value="1">v1</SelectItem>}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex items-center gap-3 pt-6">
                <Switch checked={form.sent_to_client} onCheckedChange={v => setForm(p => ({ ...p, sent_to_client: v }))} />
                <Label>Já enviada ao cliente</Label>
              </div>
            </div>
            <div>
              <Label>Feedback do cliente</Label>
              <Textarea value={form.feedback} onChange={e => setForm(p => ({ ...p, feedback: e.target.value }))} rows={2} placeholder="Comentários do cliente sobre a amostra..." />
            </div>
            <div className="flex gap-2">
              <Button size="sm" onClick={createSample}>Registrar Amostra</Button>
              <Button size="sm" variant="ghost" onClick={() => setShowCreate(false)}>Cancelar</Button>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="space-y-2">
        {samples.map(s => {
          const isEditing = editingId === s.id;
          return (
            <Card key={s.id}>
              <CardContent className="p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium text-sm">Fórmula v{s.formula_version}</span>
                      {s.sent_to_client ? (
                        <Badge className="bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300 text-[11px] gap-1"><Send className="h-3 w-3" /> Enviada</Badge>
                      ) : (
                        <Badge className="bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400 text-[11px]">Não enviada</Badge>
                      )}
                    </div>
                    {!isEditing ? (
                      <>
                        {s.feedback && (
                          <div className="mt-2 bg-muted/50 p-2.5 rounded text-sm flex items-start gap-2">
                            <MessageSquare className="h-3.5 w-3.5 text-muted-foreground mt-0.5 shrink-0" />
                            <p className="text-sm">{s.feedback}</p>
                          </div>
                        )}
                        {!s.feedback && <p className="text-xs text-muted-foreground mt-1 italic">Sem feedback do cliente</p>}
                      </>
                    ) : (
                      <div className="mt-2 space-y-2">
                        <Textarea value={editFeedback} onChange={e => setEditFeedback(e.target.value)} rows={2} placeholder="Feedback do cliente..." />
                        <div className="flex gap-2">
                          <Button size="sm" onClick={() => updateSample(s.id, { feedback: editFeedback })} className="gap-1"><Save className="h-3 w-3" /> Salvar</Button>
                          <Button size="sm" variant="ghost" onClick={() => setEditingId(null)}>Cancelar</Button>
                        </div>
                      </div>
                    )}
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    {!s.sent_to_client && canEdit && (
                      <Button size="sm" variant="outline" onClick={() => updateSample(s.id, { sent_to_client: true })} className="gap-1 text-xs">
                        <Send className="h-3 w-3" /> Enviar
                      </Button>
                    )}
                    {!isEditing && canEdit && (
                      <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => { setEditingId(s.id); setEditFeedback(s.feedback || ""); }}>
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {samples.length === 0 && !showCreate && (
        <EmptyState icon={Package} title="Nenhuma amostra registrada" subtitle="Registre amostras enviadas ao cliente" />
      )}
    </div>
  );
}

/* ============ COSTS TAB (Auto-calculated from formula + manual) ============ */
function CostsTab({ devId, costs, formulas, formulaCostData, onRefresh, canEdit }) {
  const [form, setForm] = useState({
    ingredient_cost: costs.ingredient_cost || 0,
    packaging_cost: costs.packaging_cost || 0,
    labor_cost: costs.labor_cost || 0,
  });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setForm({
      ingredient_cost: costs.ingredient_cost || 0,
      packaging_cost: costs.packaging_cost || 0,
      labor_cost: costs.labor_cost || 0,
    });
  }, [costs]);

  const total = (parseFloat(form.ingredient_cost) || 0) + (parseFloat(form.packaging_cost) || 0) + (parseFloat(form.labor_cost) || 0);

  const saveCosts = async () => {
    setSaving(true);
    try {
      await api.post(`/pd/developments/${devId}/costs`, {
        ingredient_cost: parseFloat(form.ingredient_cost) || 0,
        packaging_cost: parseFloat(form.packaging_cost) || 0,
        labor_cost: parseFloat(form.labor_cost) || 0,
      });
      toast.success("Custos salvos com sucesso!");
      onRefresh();
    } catch (err) { toast.error("Erro ao salvar custos"); }
    finally { setSaving(false); }
  };

  const latestFormula = formulas && formulas.length > 0 ? formulas[0] : null;

  return (
    <div className="space-y-6">
      <h3 className="text-base font-semibold">Relatório de Custos</h3>
      
      {/* Formula-based costs (auto-calculated) */}
      {latestFormula && (
        <Card className="border-green-200 dark:border-green-900">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base flex items-center gap-2">
                <Beaker className="h-4 w-4 text-green-600" />
                Custo da Fórmula (v{latestFormula.version} — {latestFormula.name})
              </CardTitle>
              <Badge variant="outline" className="text-[10px] text-green-600 border-green-300">Auto-calculado</Badge>
            </div>
          </CardHeader>
          <CardContent>
            {/* Mini formula cost table */}
            <div className="border rounded-md overflow-hidden mb-4">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-[#0A0A0B] text-white text-xs">
                    <th className="text-left p-2 font-medium">Formulação</th>
                    <th className="text-right p-2 font-medium w-24">%Fórmula</th>
                    <th className="text-right p-2 font-medium w-28">Preço R$/Kg</th>
                    <th className="text-right p-2 font-medium w-24">Custo R$</th>
                    <th className="text-right p-2 font-medium w-24">% Custo</th>
                  </tr>
                </thead>
                <tbody>
                  {(latestFormula.items || []).map(item => {
                    const totalC = (latestFormula.items || []).reduce((s, it) => s + (it.cost_brl || 0), 0);
                    const pct = totalC > 0 ? (item.cost_brl / totalC * 100) : 0;
                    return (
                      <tr key={item.id} className="border-t">
                        <td className="p-2">{item.ingredient_name}</td>
                        <td className="p-2 text-right font-mono text-xs">{(item.percentage || 0).toFixed(3)}</td>
                        <td className="p-2 text-right font-mono text-xs">{(item.price_per_kg || 0).toFixed(2)}</td>
                        <td className="p-2 text-right font-mono text-xs">{(item.cost_brl || 0).toFixed(2)}</td>
                        <td className="p-2 text-right font-mono text-xs">{pct.toFixed(1)}%</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Summary */}
            {formulaCostData && (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="rounded-lg border p-3 text-center">
                  <div className="text-xs text-muted-foreground mb-1">Custo/Kg</div>
                  <div className="text-lg font-bold">R$ {formulaCostData.total_cost_per_kg.toFixed(2)}</div>
                </div>
                <div className="rounded-lg border p-3 text-center bg-green-50 dark:bg-green-950">
                  <div className="text-xs text-muted-foreground mb-1">Custo Unitário</div>
                  <div className="text-lg font-bold text-green-700">R$ {formulaCostData.custo_unitario.toFixed(2)}</div>
                  {formulaCostData.volume > 0 && (
                    <div className="text-[10px] text-muted-foreground">{formulaCostData.volume} {formulaCostData.volume_unit}</div>
                  )}
                </div>
                {formulaCostData.indice_perdas > 0 && (
                  <div className="rounded-lg border p-3 text-center bg-orange-50 dark:bg-orange-950">
                    <div className="text-xs text-muted-foreground mb-1">Com Perdas ({formulaCostData.indice_perdas}%)</div>
                    <div className="text-lg font-bold text-orange-700">R$ {formulaCostData.custo_com_perdas.toFixed(2)}</div>
                  </div>
                )}
                <div className="rounded-lg border p-3 text-center">
                  <div className="text-xs text-muted-foreground mb-1">Cotação US$</div>
                  <div className="text-lg font-bold">{formulaCostData.cotacao_usd.toFixed(2)}</div>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Manual costs */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Custos Adicionais (Manual)</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <Label className="flex items-center gap-1.5"><Beaker className="h-3.5 w-3.5 text-purple-500" /> Ingredientes (R$)</Label>
              <Input type="number" step="0.01" value={form.ingredient_cost}
                onChange={e => setForm(p => ({ ...p, ingredient_cost: e.target.value }))} className="mt-1" />
            </div>
            <div>
              <Label className="flex items-center gap-1.5"><Package className="h-3.5 w-3.5 text-amber-500" /> Embalagem (R$)</Label>
              <Input type="number" step="0.01" value={form.packaging_cost}
                onChange={e => setForm(p => ({ ...p, packaging_cost: e.target.value }))} className="mt-1" />
            </div>
            <div>
              <Label className="flex items-center gap-1.5"><DollarSign className="h-3.5 w-3.5 text-green-500" /> Mão de Obra (R$)</Label>
              <Input type="number" step="0.01" value={form.labor_cost}
                onChange={e => setForm(p => ({ ...p, labor_cost: e.target.value }))} className="mt-1" />
            </div>
          </div>
          <Separator />
          <div className="flex items-center justify-between">
            <span className="font-semibold">Total Adicional:</span>
            <span className="text-xl font-bold">R$ {total.toFixed(2)}</span>
          </div>
          <Button onClick={saveCosts} disabled={saving || !canEdit} className="w-full gap-1.5">
            <Save className="h-4 w-4" />
            {saving ? "Salvando..." : "Salvar Custos"}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

/* ============ DOCUMENTS TAB ============ */
function DocumentsTab({ devId, documents, onRefresh, canEdit }) {
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ doc_type: "Ficha Técnica", file_url: "", file_name: "" });
  const [uploading, setUploading] = useState(false);

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await api.post("/upload", formData, { headers: { "Content-Type": "multipart/form-data" } });
      setForm(p => ({ ...p, file_url: `/api/files/${res.data.id}`, file_name: file.name }));
      toast.success("Arquivo enviado!");
    } catch (err) { toast.error("Erro ao enviar arquivo"); }
    finally { setUploading(false); }
  };

  const saveDocument = async () => {
    if (!form.file_url) return toast.error("Envie um arquivo primeiro");
    try {
      await api.post(`/pd/developments/${devId}/documents`, form);
      toast.success("Documento registrado!");
      setShowCreate(false);
      setForm({ doc_type: "Ficha Técnica", file_url: "", file_name: "" });
      onRefresh();
    } catch (err) { toast.error("Erro ao registrar documento"); }
  };

  const deleteDoc = async (docId) => {
    try { await api.delete(`/pd/documents/${docId}`); onRefresh(); }
    catch (err) { toast.error("Erro ao remover"); }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold">Documentos & Laudos ({documents.length})</h3>
        <Button size="sm" onClick={() => setShowCreate(true)} className="gap-1.5" disabled={!canEdit}>
          <Plus className="h-3.5 w-3.5" /> Novo Documento
        </Button>
      </div>

      {showCreate && (
        <Card className="border-primary/50">
          <CardContent className="p-4 space-y-3">
            <div>
              <Label>Tipo de Documento</Label>
              <Select value={form.doc_type} onValueChange={v => setForm(p => ({ ...p, doc_type: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {DOC_TYPES.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Arquivo</Label>
              <Input type="file" onChange={handleFileUpload} disabled={uploading} className="mt-1" />
              {uploading && <p className="text-xs text-muted-foreground mt-1 flex items-center gap-1"><Loader2 className="h-3 w-3 animate-spin" /> Enviando...</p>}
              {form.file_name && <p className="text-xs text-green-600 mt-1 flex items-center gap-1"><CheckCircle2 className="h-3 w-3" /> {form.file_name}</p>}
            </div>
            <div className="flex gap-2">
              <Button size="sm" onClick={saveDocument} disabled={!form.file_url}>Registrar Documento</Button>
              <Button size="sm" variant="ghost" onClick={() => setShowCreate(false)}>Cancelar</Button>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="space-y-2">
        {documents.map(doc => (
          <Card key={doc.id}>
            <CardContent className="p-3 flex items-center justify-between gap-3">
              <div className="flex items-center gap-3 min-w-0">
                <div className="h-10 w-10 rounded-md bg-muted flex items-center justify-center shrink-0">
                  <FileText className="h-5 w-5 text-muted-foreground" />
                </div>
                <div className="min-w-0">
                  <span className="font-medium text-sm truncate block">{doc.file_name || doc.doc_type}</span>
                  <div className="flex items-center gap-2 mt-0.5">
                    <Badge variant="outline" className="text-[10px]">{doc.doc_type}</Badge>
                    <span className="text-[10px] text-muted-foreground">
                      {doc.uploaded_by_name} • {new Date(doc.uploaded_at).toLocaleDateString("pt-BR")}
                    </span>
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-1.5 shrink-0">
                {doc.file_url && (
                  <a href={doc.file_url.startsWith("/api") ? `${BACKEND_URL}${doc.file_url}` : doc.file_url}
                    target="_blank" rel="noopener noreferrer">
                    <Button size="sm" variant="outline" className="gap-1 text-xs">
                      <Download className="h-3 w-3" /> Download
                    </Button>
                  </a>
                )}
                {canEdit && (
                  <Button variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-red-500" onClick={() => deleteDoc(doc.id)}>
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {documents.length === 0 && !showCreate && (
        <EmptyState icon={FileText} title="Nenhum documento registrado" subtitle="Anexe fichas técnicas, laudos, especificações e outros documentos" />
      )}
    </div>
  );
}

/* ============ SKU FIELD ============ */
function SkuField({ reqId, currentSku, canEdit, onRefresh }) {
  const [editing, setEditing] = useState(false);
  const [sku, setSku] = useState(currentSku || "");
  const [saving, setSaving] = useState(false);

  const saveSku = async () => {
    setSaving(true);
    try {
      await api.put(`/pd/requests/${reqId}`, { sku });
      toast.success("SKU salvo!");
      setEditing(false);
      onRefresh();
    } catch (err) { toast.error("Erro ao salvar SKU"); }
    finally { setSaving(false); }
  };

  return (
    <div className="pt-2 border-t mt-2">
      <div className="flex items-center justify-between">
        <Label className="text-xs text-muted-foreground font-medium flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-green-500" />
          SKU (Produção)
        </Label>
        {canEdit && !editing && (
          <Button size="sm" variant="ghost" onClick={() => setEditing(true)} className="text-xs gap-1 h-6">
            <Pencil className="h-3 w-3" /> {currentSku ? "Editar" : "Definir SKU"}
          </Button>
        )}
      </div>
      {!editing ? (
        currentSku ? (
          <p className="text-sm font-mono font-bold mt-1">{currentSku}</p>
        ) : (
          <p className="text-xs text-muted-foreground italic mt-1">SKU será definido para produção</p>
        )
      ) : (
        <div className="flex gap-2 mt-1">
          <Input value={sku} onChange={e => setSku(e.target.value)} placeholder="Ex: BSP-FLORAL-001" className="h-8 text-sm font-mono" />
          <Button size="sm" className="h-8" onClick={saveSku} disabled={saving}><Save className="h-3 w-3" /></Button>
          <Button size="sm" variant="ghost" className="h-8" onClick={() => { setEditing(false); setSku(currentSku || ""); }}><X className="h-3 w-3" /></Button>
        </div>
      )}
    </div>
  );
}

/* ============ EMPTY STATE ============ */
function EmptyState({ icon: Icon, title, subtitle }) {
  return (
    <div className="text-center py-16">
      <Icon className="h-14 w-14 mx-auto mb-4 text-muted-foreground/20" />
      <h4 className="font-medium mb-1">{title}</h4>
      <p className="text-xs text-muted-foreground">{subtitle}</p>
    </div>
  );
}

/* ============ UPDATES TAB (Atualizações + Pendências) ============ */
const PENDING_TYPES = [
  { id: "fragrancia", label: "Fragrância", icon: "🌸" },
  { id: "mp", label: "Matéria-Prima", icon: "🧪" },
  { id: "insumo", label: "Insumo", icon: "📦" },
  { id: "amostra", label: "Amostra/Embalagem", icon: "🎁" },
  { id: "outro", label: "Outro", icon: "📌" },
];

const PENDING_STATUS_COLORS = {
  pendente: "bg-amber-500/10 text-amber-700 border-amber-300",
  atrasado: "bg-red-500/10 text-red-700 border-red-300",
  recebido: "bg-green-500/10 text-green-700 border-green-300",
  cancelado: "bg-slate-500/10 text-slate-600 border-slate-300",
};

function UpdatesTab({ reqId, updates, pending, onRefresh, canEdit }) {
  const [showNewUpdate, setShowNewUpdate] = useState(false);
  const [newUpdateMsg, setNewUpdateMsg] = useState("");
  const [newUpdateVisible, setNewUpdateVisible] = useState(true);
  const [showNewPending, setShowNewPending] = useState(false);
  const [pendingForm, setPendingForm] = useState({
    tipo: "fragrancia",
    descricao: "",
    data_prevista: "",
    fornecedor: "",
    observacoes: "",
  });
  const [saving, setSaving] = useState(false);

  const addUpdate = async () => {
    if (!newUpdateMsg.trim()) return toast.error("Escreva a mensagem");
    setSaving(true);
    try {
      await api.post(`/pd/requests/${reqId}/updates`, {
        mensagem: newUpdateMsg,
        tipo: "observacao",
        visivel_comercial: newUpdateVisible,
      });
      toast.success("Atualização publicada");
      setNewUpdateMsg("");
      setShowNewUpdate(false);
      onRefresh();
    } catch (err) {
      toast.error("Erro ao publicar");
    } finally {
      setSaving(false);
    }
  };

  const deleteUpdate = async (upId) => {
    if (!window.confirm("Remover atualização?")) return;
    try {
      await api.delete(`/pd/updates/${upId}`);
      onRefresh();
    } catch (err) { toast.error("Erro"); }
  };

  const addPending = async () => {
    if (!pendingForm.descricao.trim()) return toast.error("Descreva a pendência");
    setSaving(true);
    try {
      await api.post(`/pd/requests/${reqId}/pending`, {
        tipo: pendingForm.tipo,
        descricao: pendingForm.descricao,
        data_prevista: pendingForm.data_prevista || null,
        fornecedor: pendingForm.fornecedor,
        observacoes: pendingForm.observacoes,
      });
      toast.success("Pendência criada");
      setShowNewPending(false);
      setPendingForm({ tipo: "fragrancia", descricao: "", data_prevista: "", fornecedor: "", observacoes: "" });
      onRefresh();
    } catch (err) { toast.error("Erro"); }
    finally { setSaving(false); }
  };

  const markReceived = async (pId) => {
    try {
      await api.put(`/pd/pending/${pId}`, { status: "recebido" });
      toast.success("Marcado como recebido");
      onRefresh();
    } catch (err) { toast.error("Erro"); }
  };

  const cancelPending = async (pId) => {
    if (!window.confirm("Cancelar esta pendência?")) return;
    try {
      await api.put(`/pd/pending/${pId}`, { status: "cancelado" });
      onRefresh();
    } catch (err) { toast.error("Erro"); }
  };

  const deletePending = async (pId) => {
    if (!window.confirm("Remover pendência?")) return;
    try {
      await api.delete(`/pd/pending/${pId}`);
      onRefresh();
    } catch (err) { toast.error("Erro"); }
  };

  const activePending = pending.filter(p => p.status === "pendente" || p.status === "atrasado");
  const resolvedPending = pending.filter(p => p.status === "recebido" || p.status === "cancelado");

  return (
    <div className="space-y-5">
      {/* PENDING ITEMS SECTION */}
      <Card className="border-amber-300/40">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base flex items-center gap-2">
              <Hourglass className="h-4 w-4 text-amber-500" />
              Pendências de Solicitação
              {activePending.length > 0 && (
                <Badge className="bg-amber-500/20 text-amber-700 border-amber-300">{activePending.length} ativa(s)</Badge>
              )}
            </CardTitle>
            {canEdit && (
              <Button size="sm" onClick={() => setShowNewPending(true)} className="gap-1.5">
                <Plus className="h-3.5 w-3.5" /> Nova Pendência
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent className="space-y-2">
          {showNewPending && (
            <Card className="border-primary/50 bg-muted/30">
              <CardContent className="p-3 space-y-2">
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <Label className="text-xs">Tipo</Label>
                    <Select value={pendingForm.tipo} onValueChange={(v) => setPendingForm(p => ({ ...p, tipo: v }))}>
                      <SelectTrigger className="h-8 text-sm"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {PENDING_TYPES.map(t => <SelectItem key={t.id} value={t.id}>{t.icon} {t.label}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label className="text-xs">Previsão de Recebimento</Label>
                    <Input type="date" value={pendingForm.data_prevista} onChange={(e) => setPendingForm(p => ({ ...p, data_prevista: e.target.value }))} className="h-8 text-sm" />
                  </div>
                  <div className="col-span-2">
                    <Label className="text-xs">Descrição *</Label>
                    <Input value={pendingForm.descricao} onChange={(e) => setPendingForm(p => ({ ...p, descricao: e.target.value }))} placeholder="Ex: Fragrância para Ginger" className="h-8 text-sm" />
                  </div>
                  <div>
                    <Label className="text-xs">Fornecedor</Label>
                    <Input value={pendingForm.fornecedor} onChange={(e) => setPendingForm(p => ({ ...p, fornecedor: e.target.value }))} className="h-8 text-sm" />
                  </div>
                  <div>
                    <Label className="text-xs">Observações</Label>
                    <Input value={pendingForm.observacoes} onChange={(e) => setPendingForm(p => ({ ...p, observacoes: e.target.value }))} className="h-8 text-sm" />
                  </div>
                </div>
                <div className="flex gap-2 pt-1">
                  <Button size="sm" onClick={addPending} disabled={saving}>{saving ? "Salvando..." : "Criar Pendência"}</Button>
                  <Button size="sm" variant="ghost" onClick={() => setShowNewPending(false)}>Cancelar</Button>
                </div>
              </CardContent>
            </Card>
          )}

          {activePending.length === 0 && !showNewPending && (
            <p className="text-xs text-muted-foreground italic text-center py-4">Nenhuma pendência ativa.</p>
          )}

          {activePending.map(p => {
            const status = p.status_calc || p.status;
            const typeInfo = PENDING_TYPES.find(t => t.id === p.tipo) || { icon: "📌", label: p.tipo };
            return (
              <div key={p.id} className={`flex items-center gap-3 p-3 rounded-md border ${status === "atrasado" ? "bg-red-50/40 dark:bg-red-950/10 border-red-200" : "bg-amber-50/30 dark:bg-amber-950/10 border-amber-200"}`}>
                <span className="text-xl">{typeInfo.icon}</span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-sm">{p.descricao}</span>
                    <Badge variant="outline" className="text-[10px]">{typeInfo.label}</Badge>
                    <Badge className={`${PENDING_STATUS_COLORS[status]} text-[10px]`}>
                      {status === "atrasado" && <AlertTriangle className="h-2.5 w-2.5 mr-0.5" />}
                      {status}
                    </Badge>
                  </div>
                  <div className="text-xs text-muted-foreground mt-0.5 flex items-center gap-3 flex-wrap">
                    <span>Solicitado em {new Date(p.data_solicitacao).toLocaleDateString("pt-BR")}</span>
                    {p.data_prevista && <span>• Previsão: {new Date(p.data_prevista).toLocaleDateString("pt-BR")}</span>}
                    {p.fornecedor && <span>• {p.fornecedor}</span>}
                  </div>
                  {p.observacoes && <p className="text-xs mt-1 italic">{p.observacoes}</p>}
                </div>
                {canEdit && (
                  <div className="flex items-center gap-1 shrink-0">
                    <Button size="sm" variant="outline" onClick={() => markReceived(p.id)} className="gap-1 h-7 text-xs">
                      <CheckCircle2 className="h-3 w-3" /> Recebido
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => cancelPending(p.id)} className="h-7 text-xs text-muted-foreground">
                      Cancelar
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => deletePending(p.id)} className="h-7 w-7 p-0 hover:text-red-500">
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </div>
                )}
              </div>
            );
          })}

          {resolvedPending.length > 0 && (
            <details className="mt-2">
              <summary className="text-xs text-muted-foreground cursor-pointer hover:text-foreground">Ver {resolvedPending.length} pendência(s) resolvida(s)</summary>
              <div className="space-y-1 mt-2">
                {resolvedPending.map(p => {
                  const typeInfo = PENDING_TYPES.find(t => t.id === p.tipo) || { icon: "📌", label: p.tipo };
                  return (
                    <div key={p.id} className="flex items-center gap-2 text-xs p-2 border rounded bg-muted/20">
                      <span>{typeInfo.icon}</span>
                      <span className="line-through text-muted-foreground flex-1">{p.descricao}</span>
                      <Badge className={`${PENDING_STATUS_COLORS[p.status]} text-[10px]`}>{p.status}</Badge>
                      {p.data_recebido && <span className="text-[10px] text-muted-foreground">em {new Date(p.data_recebido).toLocaleDateString("pt-BR")}</span>}
                    </div>
                  );
                })}
              </div>
            </details>
          )}
        </CardContent>
      </Card>

      {/* TIMELINE */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base flex items-center gap-2">
              <Bell className="h-4 w-4 text-blue-500" />
              Atualizações do Desenvolvimento
              <span className="text-xs text-muted-foreground font-normal">({updates.length})</span>
            </CardTitle>
            {canEdit && (
              <Button size="sm" onClick={() => setShowNewUpdate(true)} className="gap-1.5">
                <Plus className="h-3.5 w-3.5" /> Nova Atualização
              </Button>
            )}
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            Feed cronológico visível para o time comercial. Mantenha o CRM sincronizado sobre o status da amostra.
          </p>
        </CardHeader>
        <CardContent className="space-y-2">
          {showNewUpdate && (
            <div className="p-3 border rounded-md bg-muted/30 space-y-2">
              <Textarea
                value={newUpdateMsg}
                onChange={(e) => setNewUpdateMsg(e.target.value)}
                rows={3}
                placeholder="Ex: Solicitada fragrância para Ginger em 13/04. Previsão de recebimento em 20/04."
              />
              <div className="flex items-center justify-between flex-wrap gap-2">
                <label className="flex items-center gap-2 text-xs">
                  <Switch checked={newUpdateVisible} onCheckedChange={setNewUpdateVisible} />
                  <span>Visível para o comercial</span>
                </label>
                <div className="flex gap-2">
                  <Button size="sm" variant="ghost" onClick={() => setShowNewUpdate(false)}>Cancelar</Button>
                  <Button size="sm" onClick={addUpdate} disabled={saving} className="gap-1.5">
                    <Send className="h-3 w-3" />
                    {saving ? "Enviando..." : "Publicar"}
                  </Button>
                </div>
              </div>
            </div>
          )}

          {updates.length === 0 && !showNewUpdate && (
            <p className="text-xs text-muted-foreground italic text-center py-4">Nenhuma atualização ainda. Publique a primeira!</p>
          )}

          <div className="space-y-2">
            {updates.map(u => {
              const isSystemType = u.tipo === "pendencia_criada" || u.tipo === "pendencia_resolvida" || u.tipo === "status";
              return (
                <div key={u.id} className="flex gap-3 p-3 border rounded-md">
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${u.tipo === "pendencia_resolvida" ? "bg-green-100 text-green-600" : u.tipo === "pendencia_criada" ? "bg-amber-100 text-amber-600" : "bg-blue-100 text-blue-600"}`}>
                    {u.tipo === "pendencia_resolvida" ? <CheckCircle2 className="h-4 w-4" /> : u.tipo === "pendencia_criada" ? <Hourglass className="h-4 w-4" /> : <MessageSquare className="h-4 w-4" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-medium">{u.user_name || "Usuário"}</span>
                      <span className="text-xs text-muted-foreground">{new Date(u.created_at).toLocaleString("pt-BR")}</span>
                      {!u.visivel_comercial && (
                        <Badge variant="outline" className="text-[9px]">interno</Badge>
                      )}
                      {isSystemType && (
                        <Badge variant="outline" className="text-[9px] bg-muted">sistema</Badge>
                      )}
                    </div>
                    <p className="text-sm mt-1 whitespace-pre-wrap">{u.mensagem}</p>
                  </div>
                  {canEdit && !isSystemType && (
                    <Button size="icon" variant="ghost" className="h-6 w-6 shrink-0" onClick={() => deleteUpdate(u.id)}>
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  )}
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

