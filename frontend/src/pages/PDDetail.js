import React, { useState, useEffect, useCallback, useMemo } from "react";
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
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { toast } from "sonner";
import { BACKEND_URL } from "@/lib/backend";
import {
  ArrowLeft, FlaskConical, Clock, Plus, Trash2, CheckCircle2, XCircle,
  Loader2, ArrowRight, FileText, DollarSign, Beaker, Package, History,
  Eye, Download, Pencil, Save, X, ShieldCheck, Send, MessageSquare, Settings2,
  Bell, Hourglass, AlertTriangle, Sparkles, ClipboardList, ThumbsUp, ThumbsDown,
  PrinterIcon, CheckSquare, XSquare, Lock, Unlock, RefreshCw, TestTube, TrendingUp,
  Thermometer, Wind, Snowflake, Sun, ChevronUp, ChevronDown, Copy,
  Building2, ShoppingCart, Layers, CheckCircle, Clock4, AlertCircle,
  GitBranch, Combine, ChevronRight, FlaskRound
} from "lucide-react";
import OrdemManipulacaoSection from "@/components/OrdemManipulacaoSection";
import ModoPreparoEditor from "@/components/ModoPreparoEditor";
import RetrocederPDCardButton from "@/components/RetrocederPDCardButton";

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

const BACKWARD_TRANSITIONS = {
  IN_PROGRESS: "OPEN",
  IN_TESTS: "IN_PROGRESS",
  WAITING_APPROVAL: "IN_TESTS",
  APPROVED: "WAITING_APPROVAL",
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
  const [showBackwardDialog, setShowBackwardDialog] = useState(false);
  const [backwardJustification, setBackwardJustification] = useState("");

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

  const handleStatusChange = async (newStatus, { isBackward = false, comment = "" } = {}) => {
    if (!isBackward) {
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
    }
    try {
      await api.put(`/pd/requests/${id}/status`, { new_status: newStatus, is_backward: isBackward, comment: comment || undefined });
      toast.success(isBackward ? "Etapa retrocedida!" : "Status atualizado!");
      fetchData();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Erro ao alterar status");
    }
  };

  const handleBackward = async () => {
    if (!backwardJustification.trim() || backwardJustification.trim().length < 10) {
      toast.error("Justificativa deve ter no mínimo 10 caracteres");
      return;
    }
    const currentStatus = data?.request?.status;
    const targetStatus = BACKWARD_TRANSITIONS[currentStatus];
    if (!targetStatus) return;
    await handleStatusChange(targetStatus, { isBackward: true, comment: backwardJustification });
    setShowBackwardDialog(false);
    setBackwardJustification("");
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

  const { request: req, development: dev, formulas, tests, samples, approval, costs, documents, history, client_info, formula_cost_data, cost_versions, lab_results, updates, pending } = data;
  const statusConfig = STATUS_CONFIG[req.status];
  const allowedNext = ALLOWED_TRANSITIONS[req.status] || [];
  const hasDev = !!dev;
  const pendingCount = (pending || []).filter(p => p.status === "pendente").length;
  const isInternalResearch = !!req.is_internal_research;
  const canViewCommercial = authUser && ["admin", "compras"].includes(authUser.role);

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
            {canEdit && BACKWARD_TRANSITIONS[req.status] && (
              <Button size="sm" variant="outline" onClick={() => { setBackwardJustification(""); setShowBackwardDialog(true); }} className="gap-1.5 text-muted-foreground border-dashed">
                <ArrowLeft className="h-3.5 w-3.5" /> Retroceder
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

          {showBackwardDialog && (
            <Dialog open onOpenChange={(open) => !open && setShowBackwardDialog(false)}>
              <DialogContent className="max-w-md">
                <DialogHeader>
                  <DialogTitle className="flex items-center gap-2">
                    <ArrowLeft className="h-4 w-4 text-amber-500" /> Retroceder Etapa
                  </DialogTitle>
                  <DialogDescription>
                    De <strong>{STATUS_CONFIG[req.status]?.label}</strong> → <strong>{STATUS_CONFIG[BACKWARD_TRANSITIONS[req.status]]?.label}</strong>. Justificativa obrigatória.
                  </DialogDescription>
                </DialogHeader>
                <div>
                  <Label>Justificativa <span className="text-red-500">*</span></Label>
                  <Textarea
                    value={backwardJustification}
                    onChange={e => setBackwardJustification(e.target.value)}
                    placeholder="Descreva o motivo do retrocesso (mínimo 10 caracteres)..."
                    rows={3}
                    className="mt-1"
                  />
                  <p className="text-[11px] text-muted-foreground mt-1">{backwardJustification.length} / 10 mín.</p>
                </div>
                <DialogFooter>
                  <Button variant="ghost" onClick={() => setShowBackwardDialog(false)}>Cancelar</Button>
                  <Button variant="outline" onClick={handleBackward} disabled={backwardJustification.trim().length < 10} className="gap-1.5">
                    <ArrowLeft className="h-3.5 w-3.5" /> Confirmar Retrocesso
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          )}
        </div>

        {/* Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="mb-4 flex-wrap h-auto gap-1">
            <TabsTrigger value="overview" className="gap-1.5"><Eye className="h-3.5 w-3.5" />Overview</TabsTrigger>
            <TabsTrigger value="formula" className="gap-1.5"><Beaker className="h-3.5 w-3.5" />Manipulação</TabsTrigger>
            <TabsTrigger value="tests" className="gap-1.5"><FlaskConical className="h-3.5 w-3.5" />Testes</TabsTrigger>
            <TabsTrigger value="samples" className="gap-1.5"><Package className="h-3.5 w-3.5" />Amostras</TabsTrigger>
            <TabsTrigger value="om" className="gap-1.5" data-testid="tab-om"><Beaker className="h-3.5 w-3.5" />Ordens Manip.</TabsTrigger>
            <TabsTrigger value="estabilidades" className="gap-1.5"><TestTube className="h-3.5 w-3.5" />Estabilidades</TabsTrigger>
            <TabsTrigger value="ficha_tecnica" className="gap-1.5"><ClipboardList className="h-3.5 w-3.5" />Ficha Técnica</TabsTrigger>
            <TabsTrigger value="updates" className="gap-1.5 relative">
              <Bell className="h-3.5 w-3.5" />Atualizações
              {pendingCount > 0 && (
                <span className="ml-1 inline-flex items-center justify-center px-1.5 min-w-[18px] h-[18px] text-[10px] font-bold rounded-full bg-amber-500 text-white">
                  {pendingCount}
                </span>
              )}
            </TabsTrigger>
            <TabsTrigger value="costs" className="gap-1.5"><DollarSign className="h-3.5 w-3.5" />Custos P&D</TabsTrigger>
            {canViewCommercial && (
              <TabsTrigger value="comercial" className="gap-1.5"><Building2 className="h-3.5 w-3.5" />Comercial</TabsTrigger>
            )}
            <TabsTrigger value="documents" className="gap-1.5"><FileText className="h-3.5 w-3.5" />Documentos</TabsTrigger>
            <TabsTrigger value="live_docs" className="gap-1.5" data-testid="tab-live-docs">
              <ShieldCheck className="h-3.5 w-3.5" />Documentos Vivos
            </TabsTrigger>
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

          <TabsContent value="om">
            <OrdensManipulacaoTab req={req} dev={dev} formulas={formulas} clientInfo={client_info} />
          </TabsContent>

          <TabsContent value="estabilidades">
            <EstabilidadesTab reqId={req.id} req={req} canEdit={canEdit} />
          </TabsContent>

          <TabsContent value="ficha_tecnica">
            <FichaTecnicaTab reqId={req.id} formulas={formulas} req={req} dev={dev} canEdit={canEdit} />
          </TabsContent>

          <TabsContent value="updates">
            <UpdatesTab reqId={req.id} updates={updates || []} pending={pending || []} onRefresh={fetchData} canEdit={canEdit} />
          </TabsContent>

          <TabsContent value="costs">
            {hasDev ? (
              <CostsTab devId={dev.id} costVersions={cost_versions} formulas={formulas} formulaCostData={formula_cost_data} onRefresh={fetchData} canEdit={canEdit} />
            ) : (
              <NeedsDev onAction={() => handleStatusChange("IN_PROGRESS")} status={req.status} canEdit={canEdit} />
            )}
          </TabsContent>

          {canViewCommercial && (
            <TabsContent value="comercial">
              {hasDev ? (
                <ComercialTab devId={dev.id} costVersions={cost_versions} formulaCostData={formula_cost_data} onRefresh={fetchData} />
              ) : (
                <NeedsDev onAction={() => handleStatusChange("IN_PROGRESS")} status={req.status} canEdit={canEdit} />
              )}
            </TabsContent>
          )}

          <TabsContent value="documents">
            {hasDev ? (
              <DocumentsTab devId={dev.id} documents={documents} onRefresh={fetchData} canEdit={canEdit} />
            ) : (
              <NeedsDev onAction={() => handleStatusChange("IN_PROGRESS")} status={req.status} canEdit={canEdit} />
            )}
          </TabsContent>

          <TabsContent value="live_docs">
            <LiveDocumentsTab reqId={req.id} req={req} />
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
  const [showBriefingDetail, setShowBriefingDetail] = useState(false);

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
        {/* Briefing Card from CRM - PROMINENT (Click to expand details) */}
        {clientInfo && (
          <Card
            className="border-blue-200 dark:border-blue-900 cursor-pointer hover:border-blue-400 dark:hover:border-blue-700 hover:shadow-md transition-all group"
            onClick={() => setShowBriefingDetail(true)}
            data-testid="briefing-card-clickable"
          >
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-blue-500" />
                  Briefing do Projeto (CRM)
                </CardTitle>
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className="text-[10px]">Dados do Pipeline</Badge>
                  <Eye className="h-3.5 w-3.5 text-muted-foreground group-hover:text-blue-500 transition-colors" />
                </div>
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
                  <p className="whitespace-pre-wrap line-clamp-2">{clientInfo.objetivo_projeto}</p>
                </div>
              )}
              <div className="pt-2 border-t border-dashed flex items-center justify-center text-xs text-muted-foreground group-hover:text-blue-500 transition-colors">
                <Eye className="h-3 w-3 mr-1.5" />
                Clique para ver todas as informações do briefing
              </div>
            </CardContent>
          </Card>
        )}

        {/* Briefing Detail Dialog - Full info from CRM */}
        <Dialog open={showBriefingDetail} onOpenChange={setShowBriefingDetail}>
          <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto" data-testid="briefing-detail-dialog">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-blue-500" />
                Briefing do Projeto (CRM)
                <Badge variant="outline" className="text-[10px] ml-2">Dados do Pipeline</Badge>
              </DialogTitle>
              <DialogDescription>
                Todas as informações do projeto vindas do CRM / Pipeline
              </DialogDescription>
            </DialogHeader>

            {clientInfo && (
              <div className="space-y-5 text-sm py-2">
                {/* Identificação */}
                <section>
                  <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-3 flex items-center gap-2">
                    <span className="w-1 h-4 bg-blue-500 rounded" />
                    Identificação
                  </h4>
                  <div className="grid grid-cols-2 gap-x-6 gap-y-3 pl-3">
                    <InfoRow label="1. Produto" value={clientInfo.produto} />
                    <InfoRow label="2. Cliente" value={clientInfo.nome_cliente} />
                    <InfoRow label="3. Nome do Projeto" value={clientInfo.nome_projeto} />
                    <InfoRow label="9. Orçamento" value={clientInfo.orcamento_projeto} />
                  </div>
                </section>

                {/* Especificações Técnicas */}
                <section>
                  <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-3 flex items-center gap-2">
                    <span className="w-1 h-4 bg-purple-500 rounded" />
                    Especificações Técnicas
                  </h4>
                  <div className="grid grid-cols-2 gap-x-6 gap-y-3 pl-3">
                    <InfoRow label="10. Textura Esperada" value={clientInfo.textura_esperada} />
                    <InfoRow label="11. Aplicação" value={clientInfo.aplicacao} />
                    <InfoRow label="12. Sensorial" value={clientInfo.sensorial} />
                    <InfoRow label="13. pH" value={clientInfo.ph} />
                  </div>
                </section>

                {/* Objetivo & Detalhes */}
                {(clientInfo.objetivo_projeto || clientInfo.aplicacoes_desenvolver || clientInfo.ativos_claims) && (
                  <section>
                    <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-3 flex items-center gap-2">
                      <span className="w-1 h-4 bg-green-500 rounded" />
                      Objetivos & Detalhes do Projeto
                    </h4>
                    <div className="space-y-3 pl-3">
                      {clientInfo.objetivo_projeto && (
                        <div>
                          <span className="text-muted-foreground text-xs font-medium block mb-1">4. Objetivo do Projeto</span>
                          <p className="whitespace-pre-wrap bg-muted/40 p-3 rounded-md">{clientInfo.objetivo_projeto}</p>
                        </div>
                      )}
                      {clientInfo.aplicacoes_desenvolver && (
                        <div>
                          <span className="text-muted-foreground text-xs font-medium block mb-1">5. Aplicações a Desenvolver</span>
                          <p className="whitespace-pre-wrap bg-muted/40 p-3 rounded-md">{clientInfo.aplicacoes_desenvolver}</p>
                        </div>
                      )}
                      {clientInfo.ativos_claims && (
                        <div>
                          <span className="text-muted-foreground text-xs font-medium block mb-1">6. Ativos para Claims</span>
                          <p className="whitespace-pre-wrap bg-muted/40 p-3 rounded-md">{clientInfo.ativos_claims}</p>
                        </div>
                      )}
                    </div>
                  </section>
                )}

                {/* Referências */}
                {(clientInfo.referencias || clientInfo.referencias_fotos_url) && (
                  <section>
                    <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-3 flex items-center gap-2">
                      <span className="w-1 h-4 bg-amber-500 rounded" />
                      Referências
                    </h4>
                    <div className="space-y-3 pl-3">
                      {clientInfo.referencias && (
                        <div>
                          <span className="text-muted-foreground text-xs font-medium block mb-1">7. Referências</span>
                          <p className="whitespace-pre-wrap bg-muted/40 p-3 rounded-md">{clientInfo.referencias}</p>
                        </div>
                      )}
                      {clientInfo.referencias_fotos_url && (
                        <div>
                          <span className="text-muted-foreground text-xs font-medium block mb-1">8. Referências Fotos</span>
                          <a href={clientInfo.referencias_fotos_url} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline text-sm break-all bg-muted/40 p-3 rounded-md block">
                            {clientInfo.referencias_fotos_url}
                          </a>
                        </div>
                      )}
                    </div>
                  </section>
                )}

                {/* Observações Adicionais */}
                {clientInfo.outras_observacoes && (
                  <section>
                    <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-3 flex items-center gap-2">
                      <span className="w-1 h-4 bg-rose-500 rounded" />
                      Outras Observações
                    </h4>
                    <div className="pl-3">
                      <span className="text-muted-foreground text-xs font-medium block mb-1">14. Outras Observações</span>
                      <p className="whitespace-pre-wrap bg-muted/40 p-3 rounded-md">{clientInfo.outras_observacoes}</p>
                    </div>
                  </section>
                )}

                {/* Metadata */}
                <section className="pt-3 border-t">
                  <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                    <span>
                      {req.created_by_name && <>Criado por <strong>{req.created_by_name}</strong></>}
                      {req.created_at && <> em {new Date(req.created_at).toLocaleDateString("pt-BR")}</>}
                    </span>
                    {clientInfo.nome_cliente && (
                      <Badge variant="secondary" className="text-[10px]">
                        Cliente: {clientInfo.nome_cliente}
                      </Badge>
                    )}
                  </div>
                </section>
              </div>
            )}

            <DialogFooter>
              <Button variant="outline" onClick={() => setShowBriefingDetail(false)} data-testid="close-briefing-detail-btn">
                Fechar
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

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
  const [newItem, setNewItem] = useState({ ingredient_name: "", percentage: "", price_per_kg: "", price_currency: "BRL", fornecedor: "", phase: "", function: "", catalog_id: "" });
  const [editingConfig, setEditingConfig] = useState(null);
  const [configForm, setConfigForm] = useState({});
  const [editingItemId, setEditingItemId] = useState(null);
  const [editItemForm, setEditItemForm] = useState({ ingredient_name: "", fornecedor: "", percentage: "", price_per_kg: "", price_currency: "BRL" });
  const [pendingCatalogItem, setPendingCatalogItem] = useState(null);
  const [catalog, setCatalog] = useState([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [showNewVersion, setShowNewVersion] = useState(null); // formula to create new version from
  const [newVersionJustification, setNewVersionJustification] = useState("");
  const [creatingVersion, setCreatingVersion] = useState(false);

  useEffect(() => {
    api.get("/pd/catalog").then(({ data }) => {
      setCatalog(Array.isArray(data) ? data : []);
    }).catch(() => setCatalog([]));
  }, []);

  const filteredCatalog = newItem.ingredient_name
    ? catalog.filter(c => c.nome.toLowerCase().includes(newItem.ingredient_name.toLowerCase()) ||
                          (c.inci && c.inci.toLowerCase().includes(newItem.ingredient_name.toLowerCase())))
    : catalog;

  const supplierRankColor = (rank) => {
    if (rank === 0) return "text-green-700 bg-green-50 border-green-200 hover:bg-green-100";
    if (rank === 1) return "text-yellow-700 bg-yellow-50 border-yellow-200 hover:bg-yellow-100";
    if (rank === 2) return "text-orange-600 bg-orange-50 border-orange-200 hover:bg-orange-100";
    return "text-red-600 bg-red-50 border-red-200 hover:bg-red-100";
  };

  const pickFromCatalog = (cat) => {
    const fornecedores = (cat.fornecedores || [])
      .slice()
      .sort((a, b) => (a.preco_rs_kg || 0) - (b.preco_rs_kg || 0));
    if (fornecedores.length > 0) {
      setNewItem(p => ({
        ...p,
        ingredient_name: cat.nome,
        catalog_id: cat.id,
        price_per_kg: "",
        price_currency: "BRL",
        fornecedor: "",
      }));
      setPendingCatalogItem({ ...cat, fornecedores });
    } else {
      setNewItem({
        ingredient_name: cat.nome,
        percentage: newItem.percentage,
        price_per_kg: String(cat.preco_rs_kg || 0),
        price_currency: "BRL",
        fornecedor: cat.fornecedor || "",
        phase: newItem.phase,
        function: newItem.function,
        catalog_id: cat.id,
      });
      setPendingCatalogItem(null);
    }
    setShowSuggestions(false);
  };

  const createNewVersion = async () => {
    if (!newVersionJustification.trim() || newVersionJustification.trim().length < 10) {
      return toast.error("Justificativa deve ter no mínimo 10 caracteres");
    }
    setCreatingVersion(true);
    try {
      await api.post(`/pd/formulas/${showNewVersion.id}/new-version`, { justification: newVersionJustification });
      toast.success(`Nova versão v${(showNewVersion.version || 1) + 1} criada!`);
      setShowNewVersion(null);
      setNewVersionJustification("");
      onRefresh();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Erro ao criar nova versão");
    } finally { setCreatingVersion(false); }
  };

  const createFormula = async () => {
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
      const formula = formulas.find(f => f.id === formulaId);
      const cotacao = formula?.cotacao_usd || 6.00;
      const rawPrice = parseFloat(newItem.price_per_kg) || 0;
      const priceInBRL = newItem.price_currency === "USD" ? rawPrice * cotacao : rawPrice;
      await api.post(`/pd/formulas/${formulaId}/items`, {
        ingredient_name: newItem.ingredient_name,
        percentage: parseFloat(newItem.percentage),
        price_per_kg: priceInBRL,
        fornecedor: newItem.fornecedor || "",
        phase: newItem.phase,
        function: newItem.function,
        catalog_id: newItem.catalog_id || null,
      });
      toast.success("Ingrediente adicionado!");
      setNewItem({ ingredient_name: "", percentage: "", price_per_kg: "", price_currency: "BRL", fornecedor: "", phase: "", function: "", catalog_id: "" });
      setShowSuggestions(false);
      onRefresh();
    } catch (err) { toast.error("Erro ao adicionar"); }
  };

  const deleteItem = async (itemId) => {
    try { await api.delete(`/pd/formula-items/${itemId}`); onRefresh(); }
    catch (err) { toast.error("Erro ao remover"); }
  };

  const startEditItem = (item) => {
    setEditingItemId(item.id);
    setEditItemForm({
      ingredient_name: item.ingredient_name,
      fornecedor: item.fornecedor || "",
      percentage: String(item.percentage || ""),
      price_per_kg: String(item.price_per_kg || ""),
      price_currency: "BRL",
    });
  };

  const cancelEditItem = () => setEditingItemId(null);

  const saveEditItem = async (formulaId) => {
    try {
      const formula = formulas.find(f => f.id === formulaId);
      const cotacao = formula?.cotacao_usd || 6.00;
      const rawPrice = parseFloat(editItemForm.price_per_kg) || 0;
      const priceInBRL = editItemForm.price_currency === "USD" ? rawPrice * cotacao : rawPrice;
      await api.put(`/pd/formula-items/${editingItemId}`, {
        ingredient_name: editItemForm.ingredient_name,
        fornecedor: editItemForm.fornecedor || "",
        percentage: parseFloat(editItemForm.percentage) || 0,
        price_per_kg: priceInBRL,
      });
      toast.success("Item atualizado!");
      cancelEditItem();
      onRefresh();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Erro ao atualizar");
    }
  };

  const duplicateFormula = async (formulaId) => {
    try {
      await api.post(`/pd/formulas/${formulaId}/duplicate`);
      toast.success("Variação criada! Ajuste o ingrediente diferente.");
      onRefresh();
    } catch (err) { toast.error(err.response?.data?.detail || "Erro ao duplicar"); }
  };

  const startEditConfig = (f) => {
    setEditingConfig(f.id);
    setConfigForm({
      volume: f.volume || "",
      volume_unit: f.volume_unit || "mL",
      indice_perdas: f.indice_perdas || 0,
      cotacao_usd: f.cotacao_usd || 6.00,
      fragrance_target: f.fragrance_target ?? "",
    });
  };

  const saveConfig = async (formulaId) => {
    try {
      const payload = {
        volume: parseFloat(configForm.volume) || 0,
        volume_unit: configForm.volume_unit,
        indice_perdas: parseFloat(configForm.indice_perdas) || 0,
        cotacao_usd: parseFloat(configForm.cotacao_usd) || 6.00,
      };
      if (configForm.fragrance_target !== "" && configForm.fragrance_target != null) {
        payload.fragrance_target = parseFloat(configForm.fragrance_target);
      }
      await api.put(`/pd/formulas/${formulaId}`, payload);
      toast.success("Configuração salva!");
      setEditingConfig(null);
      onRefresh();
    } catch (err) { toast.error("Erro ao salvar"); }
  };

  return (
    <div className="space-y-4">
      {/* Briefing técnico (CRM) — alvos para o P&D só preencher MPs/insumos */}
      {clientInfo && clientInfo._source === "crm_sample" && (
        <Card className="border-blue-200 dark:border-blue-900 bg-blue-50/30 dark:bg-blue-950/20" data-testid="formula-briefing-targets">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-blue-500" />
              Alvos do Briefing (CRM){clientInfo._variacao_codigo ? ` — Variação ${clientInfo._variacao_codigo}` : ""}
            </CardTitle>
            <p className="text-[11px] text-muted-foreground">
              Volume, fragrância e parâmetros já vieram da solicitação. P&D só precisa adicionar MPs/insumos/ingredientes.
            </p>
          </CardHeader>
          <CardContent className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs pt-0">
            {req?.volume && (
              <div><span className="text-muted-foreground">Volume alvo:</span> <span className="font-medium">{req.volume}</span></div>
            )}
            {clientInfo.ph && (
              <div><span className="text-muted-foreground">pH alvo:</span> <span className="font-medium">{clientInfo.ph}</span></div>
            )}
            {clientInfo.textura_esperada && (
              <div className="col-span-2"><span className="text-muted-foreground">Textura:</span> <span className="font-medium">{clientInfo.textura_esperada}</span></div>
            )}
            {clientInfo.sensorial && (
              <div className="col-span-2"><span className="text-muted-foreground">Sensorial:</span> <span className="font-medium">{clientInfo.sensorial}</span></div>
            )}
            {clientInfo.aplicacao && (
              <div className="col-span-2"><span className="text-muted-foreground">Aplicação:</span> <span className="font-medium">{clientInfo.aplicacao}</span></div>
            )}
            {clientInfo.ativos_claims && (
              <div className="col-span-4"><span className="text-muted-foreground">Ativos / Claims:</span> <span className="font-medium">{clientInfo.ativos_claims}</span></div>
            )}
            {clientInfo.orcamento_projeto && (
              <div className="col-span-2"><span className="text-muted-foreground">Orçamento:</span> <span className="font-medium">{clientInfo.orcamento_projeto}</span></div>
            )}
          </CardContent>
        </Card>
      )}
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
                  {f.locked && (
                    <Badge className="text-[10px] bg-amber-500/20 text-amber-700 border-amber-300 gap-1">
                      <Lock className="h-2.5 w-2.5" /> Registrada
                    </Badge>
                  )}
                  {f.version_justification && (
                    <span className="text-[10px] text-muted-foreground truncate max-w-xs" title={f.version_justification}>
                      "{f.version_justification.slice(0, 40)}..."
                    </span>
                  )}
                </CardTitle>
                <div className="flex items-center gap-2" onClick={e => e.stopPropagation()}>
                  {volume > 0 && (
                    <span className="text-xs text-muted-foreground">{volume} {volumeUnit}</span>
                  )}
                  <span className="text-xs font-bold text-green-600">
                    R$ {custoUnit.toFixed(2)}
                  </span>
                  <Badge variant="secondary" className="text-[10px]">{items.length} itens</Badge>
                  {canEdit && items.length > 0 && (
                    <Button size="sm" variant="ghost" className="h-7 text-xs gap-1 text-muted-foreground hover:text-foreground" onClick={() => duplicateFormula(f.id)} title="Copia todos os ingredientes para uma nova versão — ideal para variações de fragrância">
                      <Copy className="h-3 w-3" /> Duplicar
                    </Button>
                  )}
                  {canEdit && f.locked && (
                    <Button size="sm" variant="outline" className="h-7 text-xs gap-1 border-amber-300 hover:bg-amber-50" onClick={() => { setShowNewVersion(f); setNewVersionJustification(""); }} data-testid={`new-version-btn-${f.id}`}>
                      <RefreshCw className="h-3 w-3" /> Nova Versão
                    </Button>
                  )}
                </div>
              </div>
            </CardHeader>
            {open && (
              <CardContent className="pt-0 space-y-3">
                {/* Formula Config Header (like spreadsheet) */}
                <div className="bg-muted/50 rounded-lg p-3 border">
                  {editingConfig === f.id ? (
                    <div className="grid grid-cols-5 gap-3">
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
                      <div>
                        <Label className="text-[11px] text-purple-700">Target Fragrância (%)</Label>
                        <Input type="number" step="0.01" placeholder="ex: 2.50" value={configForm.fragrance_target} onChange={e => setConfigForm(p => ({ ...p, fragrance_target: e.target.value }))} className="h-8 text-sm" />
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
                        {f.fragrance_target != null && (
                          <span className="text-purple-700"><b>Target Fragr.:</b> {f.fragrance_target.toFixed(2)}%</span>
                        )}
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
                        <th className="w-16"></th>
                      </tr>
                    </thead>
                    <tbody>
                      {items.map(item => {
                        const isEditingThis = canEdit && editingItemId === item.id;
                        const costPct = totalCostBrl > 0 ? (item.cost_brl / totalCostBrl * 100) : 0;
                        const qtyLote = volume > 0 ? (volume * (item.percentage || 0) / 100) : 0;
                        const qtyLabel = qtyLote > 0 ? `${qtyLote.toFixed(3)} ${volumeUnit}` : "—";

                        if (isEditingThis) {
                          return (
                            <tr key={item.id} className="border-t bg-blue-50/40 dark:bg-blue-950/10">
                              <td className="p-1.5">
                                <Input value={editItemForm.ingredient_name} onChange={e => setEditItemForm(p => ({ ...p, ingredient_name: e.target.value }))} className="h-7 text-xs" />
                              </td>
                              <td className="p-1.5">
                                <Input value={editItemForm.fornecedor} onChange={e => setEditItemForm(p => ({ ...p, fornecedor: e.target.value }))} className="h-7 text-xs w-24" placeholder="Fornecedor" />
                              </td>
                              <td className="p-1.5">
                                <Input type="number" step="0.001" value={editItemForm.percentage} onChange={e => setEditItemForm(p => ({ ...p, percentage: e.target.value }))} className="h-7 text-xs w-20 text-right font-mono" />
                              </td>
                              <td className="p-2 text-right text-xs text-muted-foreground">—</td>
                              <td className="p-1.5">
                                <div className="flex gap-1">
                                  <Input type="number" step="0.01" value={editItemForm.price_per_kg} onChange={e => setEditItemForm(p => ({ ...p, price_per_kg: e.target.value }))} className="h-7 text-xs w-20 text-right font-mono" />
                                  <button type="button" onClick={() => setEditItemForm(p => ({ ...p, price_currency: p.price_currency === "USD" ? "BRL" : "USD" }))}
                                    className={`h-7 px-1.5 rounded text-[10px] font-bold border shrink-0 ${editItemForm.price_currency === "USD" ? "bg-blue-600 text-white border-blue-600" : "bg-muted text-muted-foreground border-border"}`}>
                                    {editItemForm.price_currency === "USD" ? "US$" : "R$"}
                                  </button>
                                </div>
                              </td>
                              <td className="p-2 text-xs text-muted-foreground text-right">—</td>
                              <td className="p-2 text-xs text-muted-foreground text-right">—</td>
                              <td className="p-2 text-xs text-muted-foreground text-right">—</td>
                              <td className="p-1.5">
                                <div className="flex gap-1.5 justify-center">
                                  <button onClick={() => saveEditItem(f.id)} className="text-green-600 hover:text-green-700 transition-colors" title="Salvar"><Save className="h-3.5 w-3.5" /></button>
                                  <button onClick={cancelEditItem} className="text-muted-foreground hover:text-red-500 transition-colors" title="Cancelar"><X className="h-3.5 w-3.5" /></button>
                                </div>
                              </td>
                            </tr>
                          );
                        }

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
                                <div className="flex gap-1.5 justify-center">
                                  <button onClick={() => startEditItem(item)} className="text-muted-foreground hover:text-blue-500 transition-colors" title="Editar"><Pencil className="h-3.5 w-3.5" /></button>
                                  <button onClick={() => deleteItem(item.id)} className="text-muted-foreground hover:text-red-500 transition-colors" title="Remover"><Trash2 className="h-3.5 w-3.5" /></button>
                                </div>
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
                          {filteredCatalog.slice(0, 15).map(cat => {
                            const temFornecedores = (cat.fornecedores || []).length > 0;
                            const precoMin = temFornecedores
                              ? Math.min(...cat.fornecedores.map(s => s.preco_rs_kg || 0))
                              : cat.preco_rs_kg || 0;
                            return (
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
                                    {cat.codigo_interno && <> · {cat.codigo_interno}</>}
                                    {temFornecedores ? <> · {cat.fornecedores.length} fornecedor(es)</> : cat.fornecedor ? <> · {cat.fornecedor}</> : null}
                                    {cat.categoria && <> · {cat.categoria}</>}
                                  </div>
                                </div>
                                <span className="text-xs font-mono font-semibold shrink-0 text-green-700">
                                  {temFornecedores ? "a partir de " : ""}R$ {precoMin.toFixed(2)}/{cat.unidade || "kg"}
                                </span>
                              </button>
                            );
                          })}
                        </div>
                      )}
                      {pendingCatalogItem && (
                        <div className="mt-1 border rounded-md bg-popover shadow-md p-2 z-40">
                          <div className="text-[10px] font-semibold text-muted-foreground mb-1.5 uppercase tracking-wide flex items-center justify-between">
                            <span>Selecionar fornecedor — {pendingCatalogItem.nome}</span>
                          </div>
                          <div className="space-y-1">
                            {pendingCatalogItem.fornecedores.map((sup, idx) => (
                              <button
                                key={idx}
                                type="button"
                                className={`w-full text-left px-2 py-1.5 rounded border text-xs flex items-center justify-between gap-2 transition-colors ${supplierRankColor(idx)}`}
                                onClick={() => {
                                  setNewItem(p => ({ ...p, fornecedor: sup.nome, price_per_kg: String(sup.preco_rs_kg || 0), price_currency: sup.moeda || "BRL" }));
                                  setPendingCatalogItem(null);
                                }}
                              >
                                <span className="font-medium">{sup.nome}{sup.codigo && <span className="text-[10px] ml-1 opacity-70">· {sup.codigo}</span>}</span>
                                <span className="font-mono font-semibold shrink-0">
                                  {sup.moeda === "USD" ? "US$" : "R$"} {(sup.preco_rs_kg || 0).toFixed(2)}/{pendingCatalogItem.unidade || "kg"}
                                </span>
                              </button>
                            ))}
                          </div>
                          <button type="button" className="mt-1.5 text-[10px] text-muted-foreground hover:text-foreground underline" onClick={() => setPendingCatalogItem(null)}>
                            ← inserir preço manualmente
                          </button>
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
                    <div className="w-36">
                      <Label className="text-[11px] text-muted-foreground">
                        Preço {newItem.price_currency === "USD" ? "US$/Kg" : "R$/Kg"}
                      </Label>
                      <div className="flex gap-1">
                        <Input type="number" step="0.01" value={newItem.price_per_kg}
                          onChange={e => setNewItem(p => ({ ...p, price_per_kg: e.target.value, catalog_id: "" }))}
                          placeholder="0.00" className="h-8 text-sm font-mono" />
                        <button
                          type="button"
                          onClick={() => setNewItem(p => ({ ...p, price_currency: p.price_currency === "USD" ? "BRL" : "USD" }))}
                          className={`h-8 px-2 rounded text-[10px] font-bold border shrink-0 transition-colors ${newItem.price_currency === "USD" ? "bg-blue-600 text-white border-blue-600" : "bg-muted text-muted-foreground border-border hover:bg-muted/80"}`}
                          title={newItem.price_currency === "USD" ? `Cotação: R$ ${(formulas.find(f2 => f2.id === f.id)?.cotacao_usd || 6).toFixed(2)}` : "Clique para inserir em US$"}
                        >
                          {newItem.price_currency === "USD" ? "US$" : "R$"}
                        </button>
                      </div>
                      {newItem.price_currency === "USD" && newItem.price_per_kg && (
                        <div className="text-[10px] text-blue-600 mt-0.5">
                          = R$ {((parseFloat(newItem.price_per_kg) || 0) * (formulas.find(f2 => f2.id === f.id)?.cotacao_usd || 6)).toFixed(2)}/Kg
                        </div>
                      )}
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
      {/* Nova Versão Dialog */}
      {showNewVersion && (
        <Dialog open onOpenChange={() => setShowNewVersion(null)}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <RefreshCw className="h-4 w-4 text-amber-500" />
                Criar Nova Versão da Fórmula
              </DialogTitle>
              <DialogDescription>
                A fórmula <strong>v{showNewVersion.version}</strong> está registrada e bloqueada (RN-BF-01).
                Uma nova versão será criada copiando os ingredientes atuais. A versão anterior permanece imutável.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-3 py-2">
              <div>
                <Label className="text-sm font-medium">Justificativa <span className="text-red-500">*</span></Label>
                <Textarea
                  value={newVersionJustification}
                  onChange={e => setNewVersionJustification(e.target.value)}
                  placeholder="Descreva o motivo da alteração da fórmula (mínimo 10 caracteres)..."
                  rows={4}
                  className="mt-1"
                  data-testid="new-version-justification"
                />
                <p className="text-xs text-muted-foreground mt-1">{newVersionJustification.length}/10 mínimo</p>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setShowNewVersion(null)}>Cancelar</Button>
              <Button onClick={createNewVersion} disabled={creatingVersion || newVersionJustification.trim().length < 10} data-testid="confirm-new-version-btn">
                {creatingVersion ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <RefreshCw className="h-4 w-4 mr-2" />}
                Criar v{(showNewVersion.version || 1) + 1}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      <SampleBatchSection devId={devId} formulas={formulas} onRefresh={onRefresh} canEdit={canEdit} />
    </div>
  );
}

/* ============ SAMPLE BATCH COMPONENTS ============ */

function SampleBatchEditor({ devId, formulas, initial, onSave, onClose }) {
  const emptyVariante = () => ({ id: crypto.randomUUID(), nome: "", versao: 1, overrides: [], notas: "" });
  const [form, setForm] = useState(initial ? {
    nome: initial.nome || "",
    formula_base_id: initial.formula_base_id || (formulas[0]?.id || ""),
    volume_base_ml: initial.volume_base_ml || 15,
    notas: initial.notas || "",
    variantes: (initial.variantes || []).map(v => ({
      id: v.id || crypto.randomUUID(),
      nome: v.nome || "",
      versao: v.versao || 1,
      overrides: (v.overrides || []).map(o => ({ ...o })),
      notas: v.notas || "",
    })),
  } : {
    nome: "",
    formula_base_id: formulas[0]?.id || "",
    volume_base_ml: 15,
    notas: "",
    variantes: [emptyVariante()],
  });
  const [saving, setSaving] = useState(false);
  const [baseItems, setBaseItems] = useState([]);
  const [loadingItems, setLoadingItems] = useState(false);

  useEffect(() => {
    if (!form.formula_base_id) return;
    setLoadingItems(true);
    api.get(`/pd/formulas/${form.formula_base_id}/items`)
      .then(({ data }) => setBaseItems(Array.isArray(data) ? data : []))
      .catch(() => setBaseItems([]))
      .finally(() => setLoadingItems(false));
  }, [form.formula_base_id]);

  const setVariante = (idx, updates) => setForm(f => {
    const v = [...f.variantes];
    v[idx] = { ...v[idx], ...updates };
    return { ...f, variantes: v };
  });

  const addVariante = () => setForm(f => ({ ...f, variantes: [...f.variantes, emptyVariante()] }));

  const removeVariante = (idx) => setForm(f => ({ ...f, variantes: f.variantes.filter((_, i) => i !== idx) }));

  const addOverride = (vIdx) => setVariante(vIdx, {
    overrides: [...(form.variantes[vIdx]?.overrides || []), { ingredient_name_base: "", ingredient_name: "", percentage: 0, fornecedor: "" }]
  });

  const updateOverride = (vIdx, oIdx, field, value) => {
    const v = [...form.variantes];
    const overrides = v[vIdx].overrides.map((o, i) => i === oIdx ? { ...o, [field]: value } : o);
    v[vIdx] = { ...v[vIdx], overrides };
    setForm(f => ({ ...f, variantes: v }));
  };

  const removeOverride = (vIdx, oIdx) => {
    const v = [...form.variantes];
    v[vIdx] = { ...v[vIdx], overrides: v[vIdx].overrides.filter((_, i) => i !== oIdx) };
    setForm(f => ({ ...f, variantes: v }));
  };

  const handleSave = async () => {
    if (!form.nome.trim()) { toast.error("Nome do lote é obrigatório"); return; }
    if (!form.formula_base_id) { toast.error("Selecione a fórmula base"); return; }
    setSaving(true);
    try {
      await onSave(form);
      onClose();
    } catch (err) {
      toast.error("Erro ao salvar lote");
    } finally { setSaving(false); }
  };

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1">
          <Label className="text-xs font-medium">Nome do Lote <span className="text-red-500">*</span></Label>
          <Input value={form.nome} onChange={e => setForm(f => ({ ...f, nome: e.target.value }))} placeholder="Ex: Lote Fragrâncias Jun/2026" />
        </div>
        <div className="space-y-1">
          <Label className="text-xs font-medium">Volume da Amostra (mL)</Label>
          <Input type="number" value={form.volume_base_ml} onChange={e => setForm(f => ({ ...f, volume_base_ml: parseFloat(e.target.value) || 0 }))} />
          <p className="text-[10px] text-muted-foreground">Volume de cada amostra a elaborar no lab — não o volume do produto final (padrão: 15 mL)</p>
        </div>
      </div>

      <div className="space-y-1">
        <Label className="text-xs font-medium">Fórmula Base <span className="text-red-500">*</span></Label>
        <Select value={form.formula_base_id} onValueChange={v => setForm(f => ({ ...f, formula_base_id: v }))}>
          <SelectTrigger><SelectValue placeholder="Selecione a fórmula base..." /></SelectTrigger>
          <SelectContent>
            {formulas.map(f => (
              <SelectItem key={f.id} value={f.id}>v{f.version} — {f.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        {loadingItems && <p className="text-xs text-muted-foreground">Carregando ingredientes...</p>}
        {baseItems.length > 0 && (
          <p className="text-xs text-muted-foreground">{baseItems.length} ingredientes na fórmula base</p>
        )}
      </div>

      <div className="space-y-1">
        <Label className="text-xs font-medium">Observações do Lote</Label>
        <Textarea value={form.notas} onChange={e => setForm(f => ({ ...f, notas: e.target.value }))} placeholder="Observações gerais sobre este lote..." rows={2} />
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <Label className="text-sm font-semibold flex items-center gap-1.5"><GitBranch className="h-4 w-4 text-violet-500" />Variantes</Label>
          <Button variant="outline" size="sm" onClick={addVariante} className="h-7 text-xs gap-1"><Plus className="h-3 w-3" />Adicionar</Button>
        </div>

        {form.variantes.map((v, vIdx) => (
          <div key={v.id} className="border rounded-lg p-3 space-y-3 bg-muted/30">
            <div className="flex items-center gap-2">
              <div className="flex items-center justify-center h-6 w-6 rounded-full bg-violet-100 text-violet-700 text-xs font-bold flex-shrink-0">{vIdx + 1}</div>
              <Input
                value={v.nome}
                onChange={e => setVariante(vIdx, { nome: e.target.value })}
                placeholder={`Nome da variante ${vIdx + 1} (ex: Rosa, Floral, sem frag.)`}
                className="h-8 text-sm flex-1"
              />
              <Input
                type="number"
                value={v.versao}
                onChange={e => setVariante(vIdx, { versao: parseInt(e.target.value) || 1 })}
                className="h-8 w-20 text-sm"
                placeholder="v"
                min={1}
              />
              {form.variantes.length > 1 && (
                <button onClick={() => removeVariante(vIdx)} className="text-muted-foreground hover:text-red-500 transition-colors">
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              )}
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground font-medium">Substituições de ingredientes</span>
                <Button variant="ghost" size="sm" onClick={() => addOverride(vIdx)} className="h-6 text-xs gap-1 text-violet-600 hover:text-violet-700">
                  <Plus className="h-3 w-3" />Substituição
                </Button>
              </div>
              {v.overrides.length === 0 && (
                <p className="text-xs text-muted-foreground italic py-1">Sem substituições — todos os ingredientes seguem a fórmula base.</p>
              )}
              {v.overrides.map((o, oIdx) => (
                <div key={oIdx} className="grid grid-cols-[1fr_auto_1fr_auto_80px_auto] gap-1.5 items-center">
                  <Select value={o.ingredient_name_base} onValueChange={val => updateOverride(vIdx, oIdx, "ingredient_name_base", val)}>
                    <SelectTrigger className="h-7 text-xs"><SelectValue placeholder="Substituir..." /></SelectTrigger>
                    <SelectContent>
                      {baseItems.map(it => <SelectItem key={it.id} value={it.ingredient_name}>{it.ingredient_name}</SelectItem>)}
                    </SelectContent>
                  </Select>
                  <ChevronRight className="h-3 w-3 text-muted-foreground flex-shrink-0" />
                  <Input value={o.ingredient_name} onChange={e => updateOverride(vIdx, oIdx, "ingredient_name", e.target.value)} placeholder="Novo ingrediente" className="h-7 text-xs" />
                  <span className="text-xs text-muted-foreground">%</span>
                  <Input type="number" step="0.001" value={o.percentage} onChange={e => updateOverride(vIdx, oIdx, "percentage", parseFloat(e.target.value) || 0)} className="h-7 text-xs" />
                  <button onClick={() => removeOverride(vIdx, oIdx)} className="text-muted-foreground hover:text-red-500 transition-colors">
                    <X className="h-3 w-3" />
                  </button>
                </div>
              ))}
            </div>

            <div className="space-y-1">
              <Textarea value={v.notas} onChange={e => setVariante(vIdx, { notas: e.target.value })} placeholder="Notas desta variante..." rows={1} className="text-xs" />
            </div>
          </div>
        ))}
      </div>

      <div className="flex justify-end gap-2 pt-2 border-t">
        <Button variant="outline" onClick={onClose}>Cancelar</Button>
        <Button onClick={handleSave} disabled={saving} className="gap-1.5">
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          Salvar Lote
        </Button>
      </div>
    </div>
  );
}

function fmtQty(pct, volumeMl) {
  const g = (pct / 100) * volumeMl;
  if (g === 0) return "0,000 g";
  if (g < 0.1) return `${(g * 1000).toFixed(0)} mg`;
  if (g < 10) return `${g.toFixed(3)} g`;
  return `${g.toFixed(2)} g`;
}

function SampleBatchCard({ batch, formulas, onEdit, onDelete, canEdit }) {
  const [baseItems, setBaseItems] = useState([]);
  const [expanded, setExpanded] = useState(false);
  const [showComparativo, setShowComparativo] = useState(false);

  useEffect(() => {
    if (!expanded || !batch.formula_base_id) return;
    api.get(`/pd/formulas/${batch.formula_base_id}/items`)
      .then(({ data }) => setBaseItems(Array.isArray(data) ? data : []))
      .catch(() => setBaseItems([]));
  }, [expanded, batch.formula_base_id]);

  const baseFormula = formulas.find(f => f.id === batch.formula_base_id);
  const variantes = batch.variantes || [];
  const volumeMl = batch.volume_base_ml || 15;

  const variableSlots = useMemo(() => {
    return new Set((batch.variantes || []).flatMap(v => (v.overrides || []).map(o => o.ingredient_name_base).filter(Boolean)));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [batch.variantes]);

  // Resolve all ingredients for a given variant (overrides applied)
  const resolveVariantItems = useCallback((v) => {
    return baseItems.map(baseItem => {
      const ov = (v.overrides || []).find(o => o.ingredient_name_base === baseItem.ingredient_name);
      if (ov) {
        return {
          ...baseItem,
          ingredient_name: ov.ingredient_name || baseItem.ingredient_name,
          percentage: ov.percentage,
          fornecedor: ov.fornecedor || baseItem.fornecedor,
          is_substituted: true,
          original_name: baseItem.ingredient_name,
        };
      }
      return { ...baseItem, is_substituted: false };
    });
  }, [baseItems]);

  // Group items by phase, preserving insertion order
  const groupByPhase = (items) => {
    const groups = new Map();
    items.forEach(it => {
      const ph = it.phase || "Geral";
      if (!groups.has(ph)) groups.set(ph, []);
      groups.get(ph).push(it);
    });
    return [...groups.entries()];
  };

  const fixedItems = useMemo(() => baseItems.filter(it => !variableSlots.has(it.ingredient_name)), [baseItems, variableSlots]);
  const variableItems = useMemo(() => baseItems.filter(it => variableSlots.has(it.ingredient_name)), [baseItems, variableSlots]);

  return (
    <div className="border rounded-xl bg-background shadow-sm overflow-hidden">
      {/* Collapsed header */}
      <div
        className="flex items-center gap-3 p-4 cursor-pointer hover:bg-muted/30 transition-colors"
        onClick={() => setExpanded(e => !e)}
      >
        <div className="flex items-center justify-center h-9 w-9 rounded-lg bg-violet-100 text-violet-600 flex-shrink-0">
          <Combine className="h-4.5 w-4.5" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-sm truncate">{batch.nome}</p>
          <p className="text-xs text-muted-foreground">
            Base: {baseFormula ? `v${baseFormula.version} — ${baseFormula.name}` : "—"} · <b>{volumeMl} mL</b> por amostra · {variantes.length} variante{variantes.length !== 1 ? "s" : ""}
          </p>
        </div>
        <div className="flex items-center gap-1.5 flex-wrap">
          {variantes.map((v, i) => (
            <span key={v.id} className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-violet-50 text-violet-700 border border-violet-200">
              {v.nome || `V${i + 1}`}
            </span>
          ))}
        </div>
        {canEdit && (
          <div className="flex gap-1" onClick={e => e.stopPropagation()}>
            <button onClick={() => onEdit(batch)} className="text-muted-foreground hover:text-blue-500 transition-colors p-1"><Pencil className="h-3.5 w-3.5" /></button>
            <button onClick={() => onDelete(batch.id)} className="text-muted-foreground hover:text-red-500 transition-colors p-1"><Trash2 className="h-3.5 w-3.5" /></button>
          </div>
        )}
        <ChevronDown className={`h-4 w-4 text-muted-foreground transition-transform ${expanded ? "rotate-180" : ""}`} />
      </div>

      {expanded && (
        <div className="border-t bg-muted/10">
          {baseItems.length === 0 ? (
            <div className="p-6 flex items-center justify-center gap-2 text-muted-foreground text-sm">
              <Loader2 className="h-4 w-4 animate-spin" /> Carregando ingredientes...
            </div>
          ) : (
            <>
              {/* ── Per-variant manipulation orders ── */}
              <div className="p-4 space-y-4">
                <div className="flex items-center gap-2">
                  <FlaskRound className="h-4 w-4 text-violet-600" />
                  <span className="text-xs font-bold uppercase tracking-wider text-violet-700">Ordens de Manipulação</span>
                  <span className="text-[10px] text-muted-foreground">— {volumeMl} mL por amostra (densidade ≈ 1 g/mL)</span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {variantes.map((v, vIdx) => {
                    const resolvedItems = resolveVariantItems(v);
                    const phases = groupByPhase(resolvedItems);
                    const totalPct = resolvedItems.reduce((s, it) => s + (it.percentage || 0), 0);

                    return (
                      <div key={v.id} className="border rounded-lg overflow-hidden shadow-sm">
                        {/* Order header */}
                        <div className="bg-slate-800 dark:bg-slate-900 text-white px-4 py-2.5 flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <div className="flex items-center justify-center h-5 w-5 rounded-full bg-violet-400/30 text-[10px] font-bold">{vIdx + 1}</div>
                            <span className="font-bold text-sm">{v.nome || `Variante ${vIdx + 1}`}</span>
                            {v.versao > 1 && <span className="text-[10px] opacity-60">v{v.versao}</span>}
                          </div>
                          <div className="text-[11px] opacity-70 font-mono">{volumeMl} mL</div>
                        </div>

                        {/* Ingredient list by phase */}
                        {phases.map(([phase, items]) => (
                          <div key={phase}>
                            <div className="px-3 py-1 bg-muted/40 border-b border-t text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                              Fase {phase}
                            </div>
                            {items.map((it, itIdx) => (
                              <div
                                key={itIdx}
                                className={`flex items-center justify-between px-3 py-2 border-b text-xs ${
                                  it.is_substituted
                                    ? "bg-amber-50/60 dark:bg-amber-950/20"
                                    : itIdx % 2 === 0 ? "bg-background" : "bg-muted/20"
                                }`}
                              >
                                <div className="flex-1 min-w-0 pr-3">
                                  <span className={`font-medium ${it.is_substituted ? "text-amber-700 dark:text-amber-400" : ""}`}>
                                    {it.ingredient_name}
                                  </span>
                                  {it.is_substituted && (
                                    <span className="ml-1.5 text-[10px] text-amber-600/70 dark:text-amber-500/70">
                                      ↳ subst. {it.original_name}
                                    </span>
                                  )}
                                  {it.fornecedor && (
                                    <span className="ml-1.5 text-[10px] text-muted-foreground">{it.fornecedor}</span>
                                  )}
                                </div>
                                <div className="flex items-center gap-4 flex-shrink-0 text-right">
                                  <span className="text-muted-foreground font-mono w-16">{(it.percentage || 0).toFixed(3)}%</span>
                                  <span className={`font-mono font-bold w-20 ${it.is_substituted ? "text-amber-700 dark:text-amber-400" : ""}`}>
                                    {fmtQty(it.percentage || 0, volumeMl)}
                                  </span>
                                </div>
                              </div>
                            ))}
                          </div>
                        ))}

                        {/* Order footer */}
                        <div className="flex items-center justify-between px-3 py-2 bg-slate-100 dark:bg-slate-800 font-bold border-t-2">
                          <span className="text-xs">Total</span>
                          <div className="flex items-center gap-4 text-right">
                            <span className="font-mono text-xs text-muted-foreground w-16">{totalPct.toFixed(2)}%</span>
                            <span className="font-mono text-sm w-20">{volumeMl.toFixed(1)} g*</span>
                          </div>
                        </div>

                        {v.notas && (
                          <div className="px-3 py-1.5 text-[10px] text-muted-foreground bg-muted/20 border-t italic">{v.notas}</div>
                        )}
                      </div>
                    );
                  })}
                </div>

                <p className="text-[10px] text-muted-foreground">* Estimativa assumindo densidade ≈ 1,0 g/mL (produto aquoso). Ajuste conforme densidade real do produto.</p>
              </div>

              {/* ── Comparativo (collapsible) ── */}
              <div className="border-t">
                <button
                  onClick={() => setShowComparativo(s => !s)}
                  className="w-full flex items-center gap-2 px-4 py-2.5 text-xs text-muted-foreground hover:bg-muted/20 transition-colors"
                >
                  <ChevronDown className={`h-3.5 w-3.5 transition-transform ${showComparativo ? "rotate-180" : ""}`} />
                  Tabela comparativa de variantes
                </button>
                {showComparativo && (
                  <div className="border-t overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="bg-muted/50">
                          <th className="p-2 text-left font-medium text-muted-foreground">Ingrediente</th>
                          <th className="p-2 text-right font-medium text-muted-foreground">% Base</th>
                          <th className="p-2 text-right font-medium text-muted-foreground">g/{volumeMl}mL</th>
                          {variantes.map(v => (
                            <th key={v.id} className="p-2 text-center font-medium text-violet-700 bg-violet-50/60">
                              {v.nome || "Variante"}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {fixedItems.map(it => (
                          <tr key={it.id} className="border-t hover:bg-muted/20">
                            <td className="p-2 font-medium">{it.ingredient_name}</td>
                            <td className="p-2 text-right font-mono">{(it.percentage || 0).toFixed(3)}</td>
                            <td className="p-2 text-right font-mono">{fmtQty(it.percentage || 0, volumeMl)}</td>
                            {variantes.map(v => (
                              <td key={v.id} className="p-2 text-center text-muted-foreground bg-violet-50/30">—</td>
                            ))}
                          </tr>
                        ))}
                        {variableItems.map(it => (
                          <tr key={it.id} className="border-t bg-amber-50/40 hover:bg-amber-50/60">
                            <td className="p-2 font-medium text-amber-700">{it.ingredient_name} <span className="text-[10px] bg-amber-100 text-amber-600 rounded px-1 ml-1">variável</span></td>
                            <td className="p-2 text-right font-mono text-amber-700">{(it.percentage || 0).toFixed(3)}</td>
                            <td className="p-2 text-right font-mono text-amber-700">{fmtQty(it.percentage || 0, volumeMl)}</td>
                            {variantes.map(v => {
                              const ov = (v.overrides || []).find(o => o.ingredient_name_base === it.ingredient_name);
                              return (
                                <td key={v.id} className="p-2 text-center bg-violet-50/50">
                                  {ov ? (
                                    <div>
                                      <p className="font-medium text-violet-700">{ov.ingredient_name || it.ingredient_name}</p>
                                      <p className="font-mono text-violet-600">{(ov.percentage || 0).toFixed(3)}%</p>
                                      <p className="font-mono text-[10px] text-violet-500">{fmtQty(ov.percentage || 0, volumeMl)}</p>
                                      {ov.fornecedor && <p className="text-[10px] text-muted-foreground">{ov.fornecedor}</p>}
                                    </div>
                                  ) : (
                                    <span className="text-muted-foreground">base</span>
                                  )}
                                </td>
                              );
                            })}
                          </tr>
                        ))}
                      </tbody>
                      <tfoot>
                        <tr className="border-t-2 bg-muted/30 font-bold">
                          <td className="p-2 text-xs">Total</td>
                          <td className="p-2 text-right font-mono">{baseItems.reduce((s, it) => s + (it.percentage || 0), 0).toFixed(2)}</td>
                          <td className="p-2 text-right font-mono">{volumeMl.toFixed(0)} mL</td>
                          {variantes.map(v => <td key={v.id} className="p-2 bg-violet-50/30" />)}
                        </tr>
                      </tfoot>
                    </table>
                  </div>
                )}
              </div>

              {batch.notas && (
                <div className="px-4 py-2 border-t">
                  <p className="text-xs text-muted-foreground bg-muted/30 rounded p-2">{batch.notas}</p>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function SampleBatchSection({ devId, formulas, onRefresh, canEdit }) {
  const [batches, setBatches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editingBatch, setEditingBatch] = useState(null);

  const fetchBatches = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/pd/developments/${devId}/sample-batches`);
      setBatches(Array.isArray(data) ? data : []);
    } catch { setBatches([]); } finally { setLoading(false); }
  }, [devId]);

  useEffect(() => { fetchBatches(); }, [fetchBatches]);

  const handleSave = async (form) => {
    if (editingBatch) {
      await api.put(`/pd/developments/${devId}/sample-batches/${editingBatch.id}`, form);
      toast.success("Lote atualizado");
    } else {
      await api.post(`/pd/developments/${devId}/sample-batches`, form);
      toast.success("Lote criado");
    }
    fetchBatches();
  };

  const handleDelete = async (batchId) => {
    if (!window.confirm("Remover este lote de amostras?")) return;
    try {
      await api.delete(`/pd/developments/${devId}/sample-batches/${batchId}`);
      toast.success("Lote removido");
      fetchBatches();
    } catch { toast.error("Erro ao remover lote"); }
  };

  const openCreate = () => { setEditingBatch(null); setEditorOpen(true); };
  const openEdit = (batch) => { setEditingBatch(batch); setEditorOpen(true); };

  return (
    <div className="mt-8 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="h-px flex-1 bg-border" />
          <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-violet-50 border border-violet-200">
            <GitBranch className="h-3.5 w-3.5 text-violet-600" />
            <span className="text-xs font-semibold text-violet-700">Lotes de Amostras</span>
            {batches.length > 0 && (
              <span className="text-[10px] bg-violet-200 text-violet-700 rounded-full px-1.5">{batches.length}</span>
            )}
          </div>
          <div className="h-px flex-1 bg-border" />
        </div>
        {canEdit && formulas.length > 0 && (
          <Button variant="outline" size="sm" onClick={openCreate} className="ml-3 h-7 text-xs gap-1 border-violet-200 text-violet-700 hover:bg-violet-50">
            <Plus className="h-3 w-3" />Novo Lote
          </Button>
        )}
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-6">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      ) : batches.length === 0 ? (
        <div className="text-center py-8 border border-dashed rounded-xl bg-muted/20">
          <Combine className="h-8 w-8 text-muted-foreground/40 mx-auto mb-2" />
          <p className="text-sm text-muted-foreground">Nenhum lote de amostras ainda.</p>
          {canEdit && formulas.length > 0 && (
            <p className="text-xs text-muted-foreground mt-1">Crie um lote para organizar variantes com mesma base (ex: diferentes fragrâncias).</p>
          )}
          {formulas.length === 0 && (
            <p className="text-xs text-muted-foreground mt-1">Crie uma fórmula base primeiro para habilitar lotes.</p>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {batches.map(batch => (
            <SampleBatchCard
              key={batch.id}
              batch={batch}
              formulas={formulas}
              onEdit={openEdit}
              onDelete={handleDelete}
              canEdit={canEdit}
            />
          ))}
        </div>
      )}

      <Dialog open={editorOpen} onOpenChange={open => { if (!open) setEditorOpen(false); }}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <GitBranch className="h-5 w-5 text-violet-600" />
              {editingBatch ? "Editar Lote de Amostras" : "Novo Lote de Amostras"}
            </DialogTitle>
            <DialogDescription>
              Defina uma fórmula base e configure variantes com substituições de ingredientes (ex: fragrâncias diferentes).
            </DialogDescription>
          </DialogHeader>
          {editorOpen && (
            <SampleBatchEditor
              devId={devId}
              formulas={formulas}
              initial={editingBatch}
              onSave={handleSave}
              onClose={() => setEditorOpen(false)}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

/* ============ ESTABILIDADES TAB ============ */

const CONDITION_ICONS = {
  ambient: Sparkles,
  climate_30_75: Wind,
  oven_40: Thermometer,
  oven_45: Thermometer,
  refrigerated_5: Snowflake,
  freezer_minus5: Snowflake,
  light_exposure: Sun,
  dark_storage: Eye,
  freeze_thaw: RefreshCw,
};

const CONDITION_COLORS = {
  ambient: "text-green-600",
  climate_30_75: "text-yellow-600",
  oven_40: "text-orange-500",
  oven_45: "text-red-500",
  refrigerated_5: "text-blue-400",
  freezer_minus5: "text-blue-600",
  light_exposure: "text-yellow-500",
  dark_storage: "text-purple-500",
  freeze_thaw: "text-cyan-500",
};

function EstabilidadesTab({ reqId, req, canEdit }) {
  const [study, setStudy] = useState(null);
  const [readings, setReadings] = useState([]);
  const [constants, setConstants] = useState({ conditions: [], parameters: [], checkpoints: [] });
  const [loading, setLoading] = useState(true);
  const [readingDialog, setReadingDialog] = useState(null); // { conditionCode, conditionLabel }
  const [readingForm, setReadingForm] = useState({ day_offset: 0, parameters: {}, notes: "" });
  const [savingReading, setSavingReading] = useState(false);

  const fetchStudy = async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/pd/requests/${reqId}/stability-study`);
      setStudy(data.study);
      setReadings(data.readings || []);
      setConstants(data.constants || { conditions: [], parameters: [], checkpoints: [] });
    } catch (err) {
      toast.error("Erro ao carregar estabilidades");
    } finally { setLoading(false); }
  };

  useEffect(() => { fetchStudy(); }, [reqId]);

  const readingsByCondition = useMemo(() => {
    const map = {};
    readings.forEach(r => {
      if (!map[r.condition_code]) map[r.condition_code] = {};
      map[r.condition_code][r.day_offset] = r;
    });
    return map;
  }, [readings]);

  const openReadingDialog = (cond) => {
    const existing = readingsByCondition[cond.code] || {};
    const completed = Object.keys(existing).map(Number);
    const pending = constants.checkpoints.filter(d => !completed.includes(d));
    const nextDay = pending[0] ?? 0;
    setReadingForm({ day_offset: nextDay, parameters: {}, notes: "" });
    setReadingDialog(cond);
  };

  const submitReading = async () => {
    if (!readingDialog || !study) return;
    if (Object.keys(readingForm.parameters).length === 0) return toast.error("Informe ao menos um parâmetro");
    setSavingReading(true);
    try {
      await api.post(`/pd/stability/studies/${study.id}/readings`, {
        condition_code: readingDialog.code,
        day_offset: readingForm.day_offset,
        parameters: readingForm.parameters,
        notes: readingForm.notes,
      });
      toast.success(`Leitura D${readingForm.day_offset} registrada!`);
      setReadingDialog(null);
      fetchStudy();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Erro ao registrar leitura");
    } finally { setSavingReading(false); }
  };

  const getOverallStatus = (cond) => {
    const studyCond = study?.conditions?.find(c => c.code === cond.code);
    return studyCond?.status || "pending_d0";
  };

  const isAlertD2 = (cond) => {
    const studyCond = study?.conditions?.find(c => c.code === cond.code);
    if (!studyCond?.next_due_at) return false;
    const diff = new Date(studyCond.next_due_at).getTime() - Date.now();
    return diff > 0 && diff <= 2 * 24 * 3600 * 1000;
  };

  if (loading) return <div className="flex items-center justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>;

  return (
    <div className="space-y-5" data-testid="estabilidades-tab">
      {/* Study Header */}
      {study && (
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-semibold flex items-center gap-2">
              <TestTube className="h-4 w-4 text-primary" />
              Estudo de Estabilidade
            </h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              Iniciado: {study.started_at ? new Date(study.started_at).toLocaleDateString("pt-BR") : "—"}
              &nbsp;·&nbsp;Checkpoints: D{constants.checkpoints.join(" / D")}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant={study.status === "concluido" ? "default" : "secondary"} className="text-xs">
              {study.status === "concluido" ? "Concluído" : study.status === "ativo" ? "Ativo" : study.status}
            </Badge>
            <Button size="sm" variant="outline" className="h-7 gap-1 text-xs" onClick={fetchStudy}>
              <RefreshCw className="h-3 w-3" /> Atualizar
            </Button>
          </div>
        </div>
      )}

      {/* Conditions Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {constants.conditions.map(cond => {
          const CIcon = CONDITION_ICONS[cond.code] || Thermometer;
          const colorCls = CONDITION_COLORS[cond.code] || "text-muted-foreground";
          const existing = readingsByCondition[cond.code] || {};
          const completedDays = Object.keys(existing).map(Number).sort((a, b) => a - b);
          const total = constants.checkpoints.length;
          const done = completedDays.length;
          const progress = total > 0 ? (done / total) * 100 : 0;
          const status = getOverallStatus(cond);
          const alertD2 = isAlertD2(cond);
          const studyCond = study?.conditions?.find(c => c.code === cond.code);
          const nextDue = studyCond?.next_due_day_offset;
          return (
            <Card key={cond.code} className={`relative ${alertD2 ? "border-amber-400 shadow-amber-100" : ""}`} data-testid={`condition-${cond.code}`}>
              {alertD2 && (
                <div className="absolute top-2 right-2">
                  <Badge className="text-[10px] bg-amber-500 text-white animate-pulse">D-2</Badge>
                </div>
              )}
              <CardContent className="p-4 space-y-3">
                <div className="flex items-center gap-2">
                  <CIcon className={`h-4 w-4 ${colorCls}`} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{cond.label}</p>
                    <p className="text-[11px] text-muted-foreground">{cond.temperature} · {cond.humidity}</p>
                  </div>
                </div>
                {/* Progress bar */}
                <div>
                  <div className="flex justify-between text-[10px] text-muted-foreground mb-1">
                    <span>{done}/{total} checkpoints</span>
                    {nextDue != null && <span className="text-blue-600">Próx: D{nextDue}</span>}
                  </div>
                  <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                    <div className="h-full bg-primary transition-all rounded-full" style={{ width: `${progress}%` }} />
                  </div>
                </div>
                {/* Checkpoints chips */}
                <div className="flex flex-wrap gap-1">
                  {constants.checkpoints.map(day => {
                    const reading = existing[day];
                    return (
                      <span
                        key={day}
                        className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono font-medium border ${
                          reading ? "bg-green-50 border-green-300 text-green-700" : "bg-muted border-border text-muted-foreground"
                        }`}
                        title={reading ? `Registrado em ${new Date(reading.reading_at).toLocaleDateString("pt-BR")}` : `D${day} pendente`}
                      >
                        D{day}{reading ? " ✓" : ""}
                      </span>
                    );
                  })}
                </div>
                {canEdit && study?.status !== "concluido" && (
                  <Button size="sm" variant="outline" className="w-full h-7 text-xs gap-1" onClick={() => openReadingDialog(cond)} data-testid={`registrar-leitura-${cond.code}`}>
                    <Plus className="h-3 w-3" /> Registrar Leitura
                  </Button>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Registrar Leitura Dialog */}
      {readingDialog && (
        <Dialog open onOpenChange={() => setReadingDialog(null)}>
          <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <TestTube className="h-4 w-4 text-primary" />
                Registrar Leitura — {readingDialog.label}
              </DialogTitle>
              <DialogDescription>
                {readingDialog.temperature} · {readingDialog.humidity}
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-2">
              <div>
                <Label className="text-sm font-medium">Checkpoint (Dia)</Label>
                <Select value={String(readingForm.day_offset)} onValueChange={v => setReadingForm(p => ({ ...p, day_offset: Number(v) }))}>
                  <SelectTrigger className="mt-1" data-testid="checkpoint-select">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {constants.checkpoints.map(d => {
                      const alreadyDone = !!(readingsByCondition[readingDialog.code] || {})[d];
                      return (
                        <SelectItem key={d} value={String(d)} disabled={alreadyDone}>
                          D{d} {alreadyDone ? "(já registrado)" : ""}
                        </SelectItem>
                      );
                    })}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid grid-cols-2 gap-3">
                {constants.parameters.map(param => (
                  <div key={param.code}>
                    <Label className="text-xs text-muted-foreground">{param.label}</Label>
                    <Input
                      value={readingForm.parameters[param.code] || ""}
                      onChange={e => setReadingForm(p => ({ ...p, parameters: { ...p.parameters, [param.code]: e.target.value } }))}
                      placeholder={param.label}
                      className="h-8 text-sm mt-1"
                      data-testid={`param-${param.code}`}
                    />
                  </div>
                ))}
              </div>
              <div>
                <Label className="text-xs text-muted-foreground">Observações</Label>
                <Textarea value={readingForm.notes} onChange={e => setReadingForm(p => ({ ...p, notes: e.target.value }))} placeholder="Observações adicionais..." rows={2} className="mt-1" />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setReadingDialog(null)}>Cancelar</Button>
              <Button onClick={submitReading} disabled={savingReading} data-testid="submit-reading-btn">
                {savingReading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Save className="h-4 w-4 mr-2" />}
                Salvar Leitura D{readingForm.day_offset}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
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
  const EMPTY_ELABORACAO = { secoes: [] };
  const parseElaboracao = (raw) => {
    if (!raw) return EMPTY_ELABORACAO;
    if (typeof raw === "object" && Array.isArray(raw.secoes)) return raw;
    // legacy plain string → migrate to single section
    if (typeof raw === "string" && raw.trim()) return { secoes: [{ id: "s1", nome: "Modo de Preparo", temperatura: "", etapas: [raw] }] };
    return EMPTY_ELABORACAO;
  };

  const [form, setForm] = useState({
    produto: "", lote: "", data_fabricacao: "", validade: "", quantidade: "",
    elaboracao: EMPTY_ELABORACAO, resp_tecnico: "", status_aprovacao: "",
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
        elaboracao: parseElaboracao(a.elaboracao),
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

  const elab = form.elaboracao || { secoes: [], observacoes_gerais: "" };
  const setElab = (updater) => setForm(p => ({ ...p, elaboracao: updater(p.elaboracao || { secoes: [], observacoes_gerais: "" }) }));

  const addSecao = () => setElab(e => ({
    ...e,
    secoes: [...e.secoes, {
      id: `s${Date.now()}`,
      nome: `Fase ${String.fromCharCode(65 + e.secoes.length)}`,
      tipo: "",
      temperatura: "",
      agitacao: "",
      tempo_min: "",
      etapas: [""],
    }]
  }));
  const removeSecao = (sid) => setElab(e => ({ ...e, secoes: e.secoes.filter(s => s.id !== sid) }));
  const updateSecao = (sid, field, val) => setElab(e => ({ ...e, secoes: e.secoes.map(s => s.id === sid ? { ...s, [field]: val } : s) }));
  const addEtapa = (sid) => setElab(e => ({ ...e, secoes: e.secoes.map(s => s.id === sid ? { ...s, etapas: [...s.etapas, ""] } : s) }));
  const removeEtapa = (sid, idx) => setElab(e => ({ ...e, secoes: e.secoes.map(s => s.id === sid ? { ...s, etapas: s.etapas.filter((_, i) => i !== idx) } : s) }));
  const updateEtapa = (sid, idx, val) => setElab(e => ({ ...e, secoes: e.secoes.map(s => s.id === sid ? { ...s, etapas: s.etapas.map((et, i) => i === idx ? val : et) } : s) }));
  const moveSecao = (idx, dir) => setElab(e => {
    const arr = [...e.secoes];
    const to = idx + dir;
    if (to < 0 || to >= arr.length) return e;
    [arr[idx], arr[to]] = [arr[to], arr[idx]];
    return { ...e, secoes: arr };
  });

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
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Descrição da Elaboração — Modo de Preparo (padrão Ameratti) */}
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-start justify-between gap-3">
            <div>
              <CardTitle className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                2.2 · Descrição da Elaboração — Modo de Preparo
              </CardTitle>
              <p className="text-xs text-muted-foreground mt-0.5">
                Fase a fase · etapa a etapa · ingredientes vinculados da fórmula
              </p>
            </div>
            {canEdit && (
              <Button size="sm" variant="outline" className="h-7 gap-1 text-xs shrink-0" onClick={addSecao}>
                <Plus className="h-3 w-3" /> Adicionar Fase
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent className="space-y-4 pt-2" data-testid="ft-elaboracao">
          {elab.secoes.length === 0 && (
            <div className="text-center py-10 text-muted-foreground border-2 border-dashed rounded-xl">
              <p className="text-sm font-medium">Nenhuma fase adicionada</p>
              {canEdit && <p className="text-xs mt-1">Use "+ Adicionar Fase" para criar Fase A, B, C...</p>}
            </div>
          )}

          {elab.secoes.map((secao, sIdx) => {
            // Auto-link formula items whose "phase" field matches this section name (case-insensitive)
            const linkedItems = (items || []).filter(it =>
              it.phase && secao.nome &&
              it.phase.trim().toLowerCase() === secao.nome.trim().toLowerCase()
            );
            const vol = latest?.volume || 0;
            const vu = latest?.volume_unit || "mL";

            const TIPO_COLORS = {
              "Aquosa":        "bg-blue-500/15 text-blue-700 dark:text-blue-300 border-blue-500/30",
              "Oleosa":        "bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/30",
              "Conservantes":  "bg-violet-500/15 text-violet-700 dark:text-violet-300 border-violet-500/30",
              "Ativos":        "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/30",
              "Emulsificação": "bg-orange-500/15 text-orange-700 dark:text-orange-300 border-orange-500/30",
              "Resfriamento":  "bg-cyan-500/15 text-cyan-700 dark:text-cyan-300 border-cyan-500/30",
              "Ajuste de pH":  "bg-rose-500/15 text-rose-700 dark:text-rose-300 border-rose-500/30",
              "Outro":         "bg-slate-500/15 text-slate-600 dark:text-slate-300 border-slate-500/30",
            };
            const tipoColor = TIPO_COLORS[secao.tipo] || "";

            return (
              <div key={secao.id} className="border rounded-xl overflow-hidden shadow-sm">
                {/* ── Phase header ── */}
                <div className="bg-[#0A0A0B] text-white px-4 py-2.5 flex items-center gap-3 flex-wrap">
                  {/* Letter badge */}
                  <span className="flex items-center justify-center h-7 w-7 rounded-lg bg-white/10 text-sm font-bold shrink-0">
                    {String.fromCharCode(65 + sIdx)}
                  </span>

                  {/* Phase name */}
                  {canEdit ? (
                    <Input
                      value={secao.nome}
                      onChange={e => updateSecao(secao.id, "nome", e.target.value)}
                      className="h-7 w-36 text-sm font-semibold bg-transparent border-0 border-b border-white/30 rounded-none text-white placeholder:text-white/40 focus:border-white/70 px-0"
                      placeholder="Nome da fase..."
                    />
                  ) : (
                    <span className="text-sm font-semibold">{secao.nome}</span>
                  )}

                  {/* Tipo */}
                  {canEdit ? (
                    <select
                      value={secao.tipo || ""}
                      onChange={e => updateSecao(secao.id, "tipo", e.target.value)}
                      className="h-7 text-xs bg-white/10 border border-white/20 rounded px-2 text-white focus:outline-none focus:border-white/50"
                    >
                      <option value="">Tipo...</option>
                      {["Aquosa","Oleosa","Conservantes","Ativos","Emulsificação","Resfriamento","Ajuste de pH","Outro"].map(t => (
                        <option key={t} value={t}>{t}</option>
                      ))}
                    </select>
                  ) : secao.tipo ? (
                    <span className={`text-[11px] font-medium border rounded-full px-2.5 py-0.5 ${tipoColor}`}>{secao.tipo}</span>
                  ) : null}

                  {/* Temperatura */}
                  {canEdit ? (
                    <div className="flex items-center gap-1">
                      <Thermometer className="h-3.5 w-3.5 text-white/50 shrink-0" />
                      <Input
                        value={secao.temperatura || ""}
                        onChange={e => updateSecao(secao.id, "temperatura", e.target.value)}
                        className="h-6 w-20 text-xs bg-transparent border-0 border-b border-white/30 rounded-none text-white placeholder:text-white/40 focus:border-white/70 px-0"
                        placeholder="ex: 70°C"
                      />
                    </div>
                  ) : secao.temperatura ? (
                    <span className="flex items-center gap-1 text-white/70 text-xs">
                      <Thermometer className="h-3 w-3" />{secao.temperatura}
                    </span>
                  ) : null}

                  {/* Agitação */}
                  {canEdit ? (
                    <select
                      value={secao.agitacao || ""}
                      onChange={e => updateSecao(secao.id, "agitacao", e.target.value)}
                      className="h-7 text-xs bg-white/10 border border-white/20 rounded px-2 text-white focus:outline-none focus:border-white/50"
                    >
                      <option value="">Agitação...</option>
                      {["Suave","Média","Alta","Homogeneizador","Sem agitação"].map(a => (
                        <option key={a} value={a}>{a}</option>
                      ))}
                    </select>
                  ) : secao.agitacao ? (
                    <span className="text-white/60 text-xs">Agit. {secao.agitacao}</span>
                  ) : null}

                  {/* Tempo */}
                  {canEdit ? (
                    <div className="flex items-center gap-1">
                      <span className="text-white/50 text-xs">Tempo:</span>
                      <Input
                        value={secao.tempo_min || ""}
                        onChange={e => updateSecao(secao.id, "tempo_min", e.target.value)}
                        className="h-6 w-14 text-xs bg-transparent border-0 border-b border-white/30 rounded-none text-white placeholder:text-white/40 focus:border-white/70 px-0"
                        placeholder="min"
                      />
                    </div>
                  ) : secao.tempo_min ? (
                    <span className="text-white/60 text-xs">{secao.tempo_min} min</span>
                  ) : null}

                  {/* Controls */}
                  <div className="ml-auto flex items-center gap-1 shrink-0">
                    {canEdit && (
                      <>
                        <button type="button" onClick={() => moveSecao(sIdx, -1)} disabled={sIdx === 0}
                          className="h-6 w-6 flex items-center justify-center rounded hover:bg-white/10 disabled:opacity-30 text-white/70">
                          <ChevronUp className="h-3.5 w-3.5" />
                        </button>
                        <button type="button" onClick={() => moveSecao(sIdx, 1)} disabled={sIdx === elab.secoes.length - 1}
                          className="h-6 w-6 flex items-center justify-center rounded hover:bg-white/10 disabled:opacity-30 text-white/70">
                          <ChevronDown className="h-3.5 w-3.5" />
                        </button>
                        <button type="button" onClick={() => removeSecao(secao.id)}
                          className="h-6 w-6 flex items-center justify-center rounded hover:bg-red-500/30 text-white/60 hover:text-red-300 ml-1">
                          <Trash2 className="h-3 w-3" />
                        </button>
                      </>
                    )}
                  </div>
                </div>

                {/* ── Linked ingredients (auto from formula) ── */}
                {linkedItems.length > 0 && (
                  <div className="border-b bg-muted/20">
                    <div className="px-4 py-1.5 flex items-center gap-2">
                      <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                        Ingredientes desta fase (da fórmula)
                      </span>
                      <span className="text-[10px] text-muted-foreground border rounded-full px-1.5 py-px">{linkedItems.length}</span>
                    </div>
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="border-t border-b text-muted-foreground">
                          <th className="text-left px-4 py-1.5 font-medium">Ingrediente</th>
                          <th className="text-left px-3 py-1.5 font-medium">Fornecedor</th>
                          <th className="text-right px-3 py-1.5 font-medium w-20">% Fórmula</th>
                          <th className="text-right px-4 py-1.5 font-medium w-24">Qtd / Lote</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y">
                        {linkedItems.map(item => {
                          const qty = vol > 0 ? `${(vol * (item.percentage || 0) / 100).toFixed(3)} ${vu}` : "—";
                          return (
                            <tr key={item.id} className="hover:bg-muted/30">
                              <td className="px-4 py-1.5 font-medium">{item.ingredient_name}</td>
                              <td className="px-3 py-1.5 text-muted-foreground">{item.fornecedor || "—"}</td>
                              <td className="px-3 py-1.5 text-right font-mono">{(item.percentage || 0).toFixed(3)}</td>
                              <td className="px-4 py-1.5 text-right font-mono text-blue-600 dark:text-blue-400">{qty}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}

                {linkedItems.length === 0 && items.length > 0 && (
                  <div className="border-b bg-muted/10 px-4 py-2 flex items-center gap-2">
                    <span className="text-[10px] text-muted-foreground/60 italic">
                      Nenhum ingrediente da fórmula com fase "{secao.nome}".
                      Defina o campo "Fase" nos ingredientes da formulação para vincular aqui.
                    </span>
                  </div>
                )}

                {/* ── Procedimento / Steps ── */}
                <div className="divide-y">
                  <div className="px-4 py-1.5 bg-muted/10">
                    <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Procedimento</span>
                  </div>
                  {secao.etapas.map((etapa, eIdx) => (
                    <div key={eIdx} className="flex items-start gap-2 px-4 py-2 hover:bg-muted/20 group">
                      <span className="text-xs font-mono font-bold text-muted-foreground/60 mt-2 w-5 shrink-0 text-right select-none">
                        {eIdx + 1}.
                      </span>
                      {canEdit ? (
                        <Textarea
                          value={etapa}
                          onChange={e => updateEtapa(secao.id, eIdx, e.target.value)}
                          rows={2}
                          placeholder="Descreva a etapa de preparo..."
                          className="flex-1 text-sm resize-none border-0 bg-transparent focus:bg-muted/30 focus:border rounded px-2 min-h-[2.5rem]"
                        />
                      ) : (
                        <p className="flex-1 text-sm py-1.5 leading-relaxed">
                          {etapa || <span className="italic text-muted-foreground">—</span>}
                        </p>
                      )}
                      {canEdit && (
                        <button type="button" onClick={() => removeEtapa(secao.id, eIdx)}
                          className="mt-1.5 h-6 w-6 flex items-center justify-center rounded opacity-0 group-hover:opacity-100 hover:bg-destructive/10 text-muted-foreground hover:text-destructive shrink-0 transition-opacity">
                          <X className="h-3 w-3" />
                        </button>
                      )}
                    </div>
                  ))}
                  {canEdit && (
                    <div className="px-4 py-2">
                      <button type="button" onClick={() => addEtapa(secao.id)}
                        className="text-xs text-primary hover:underline flex items-center gap-1">
                        <Plus className="h-3 w-3" /> Adicionar etapa
                      </button>
                    </div>
                  )}
                  {!canEdit && secao.etapas.length === 0 && (
                    <p className="px-4 py-2 text-xs text-muted-foreground italic">Nenhuma etapa registrada.</p>
                  )}
                </div>
              </div>
            );
          })}

          {/* Observações Gerais */}
          {(canEdit || elab.observacoes_gerais) && (
            <div className="border rounded-xl overflow-hidden">
              <div className="bg-muted/40 px-4 py-2 border-b">
                <span className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                  Observações Gerais de Processo
                </span>
              </div>
              <div className="p-4">
                {canEdit ? (
                  <Textarea
                    value={elab.observacoes_gerais || ""}
                    onChange={e => setElab(el => ({ ...el, observacoes_gerais: e.target.value }))}
                    rows={3}
                    placeholder="Ex: produto sensível à temperatura — não ultrapassar 45°C na adição de ativos. Ajustar pH para 5,5–6,0 com NaOH 10% ou ácido cítrico 10%."
                    className="w-full text-sm border-0 bg-transparent resize-none focus:bg-muted/20 focus:border rounded px-0"
                  />
                ) : (
                  <p className="text-sm leading-relaxed whitespace-pre-wrap">{elab.observacoes_gerais}</p>
                )}
              </div>
            </div>
          )}
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
  const [sampleVolume, setSampleVolume] = useState(15);
  const [showOrderId, setShowOrderId] = useState(null);

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

  const getSampleStatus = (s) => {
    if (!s.sent_to_client) return { label: "Com P&D", color: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400", stage: 0 };
    if (s.client_approved === true) return { label: "Aprovada", color: "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300", stage: 3 };
    if (s.client_approved === false) return { label: "Reprovada pelo cliente", color: "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300", stage: 3 };
    return { label: "Aguardando aprovação do cliente", color: "bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300", stage: 2 };
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h3 className="text-base font-semibold">Amostras ({samples.length})</h3>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 border rounded-md px-2 py-1 bg-muted/30">
            <Beaker className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="text-xs text-muted-foreground">Vol. amostra:</span>
            <input
              type="number"
              min={1}
              max={500}
              value={sampleVolume}
              onChange={e => setSampleVolume(parseFloat(e.target.value) || 15)}
              className="w-14 text-xs font-mono bg-transparent border-none outline-none text-right"
            />
            <span className="text-xs text-muted-foreground">mL</span>
          </div>
          <Button size="sm" onClick={() => setShowCreate(true)} className="gap-1.5" disabled={!canEdit}>
            <Plus className="h-3.5 w-3.5" /> Nova Amostra
          </Button>
        </div>
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
                <Label>Já entregue ao comercial</Label>
              </div>
            </div>
            <div className="flex gap-2">
              <Button size="sm" onClick={createSample}>Registrar Amostra</Button>
              <Button size="sm" variant="ghost" onClick={() => setShowCreate(false)}>Cancelar</Button>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="space-y-3">
        {samples.map(s => {
          const isEditing = editingId === s.id;
          const status = getSampleStatus(s);
          return (
            <Card key={s.id}>
              <CardContent className="p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap mb-2">
                      <span className="font-medium text-sm">Fórmula v{s.formula_version}</span>
                      <Badge className={`text-[11px] ${status.color}`}>{status.label}</Badge>
                    </div>

                    {/* Progress indicator */}
                    <div className="flex items-center gap-1 mb-3">
                      {[
                        { step: 1, label: "Com P&D", done: status.stage >= 1 },
                        { step: 2, label: "No Comercial", done: status.stage >= 2 },
                        { step: 3, label: "Decisão cliente", done: status.stage >= 3 },
                      ].map((st, i) => (
                        <React.Fragment key={st.step}>
                          <div className={`flex items-center gap-1 text-[10px] font-medium ${st.done ? "text-green-700" : "text-muted-foreground"}`}>
                            <div className={`h-4 w-4 rounded-full flex items-center justify-center text-[9px] font-bold ${st.done ? "bg-green-600 text-white" : "bg-muted border"}`}>
                              {st.step}
                            </div>
                            {st.label}
                          </div>
                          {i < 2 && <div className={`flex-1 h-px mx-1 ${st.done ? "bg-green-400" : "bg-border"}`} style={{ maxWidth: 24 }} />}
                        </React.Fragment>
                      ))}
                    </div>

                    {/* Feedback */}
                    {!isEditing ? (
                      s.feedback && (
                        <div className="bg-muted/50 p-2.5 rounded text-sm flex items-start gap-2">
                          <MessageSquare className="h-3.5 w-3.5 text-muted-foreground mt-0.5 shrink-0" />
                          <p className="text-sm">{s.feedback}</p>
                        </div>
                      )
                    ) : (
                      <div className="space-y-2">
                        <Label className="text-xs">Feedback do cliente</Label>
                        <Textarea value={editFeedback} onChange={e => setEditFeedback(e.target.value)} rows={2} placeholder="Feedback do cliente..." />
                        <div className="flex gap-2">
                          <Button size="sm" onClick={() => updateSample(s.id, { feedback: editFeedback })} className="gap-1"><Save className="h-3 w-3" /> Salvar</Button>
                          <Button size="sm" variant="ghost" onClick={() => setEditingId(null)}>Cancelar</Button>
                        </div>
                      </div>
                    )}
                  </div>

                  <div className="flex flex-col items-end gap-1.5 shrink-0">
                    {/* Stage 1 → 2: Entregar ao Comercial */}
                    {!s.sent_to_client && canEdit && (
                      <Button size="sm" variant="outline" onClick={() => updateSample(s.id, { sent_to_client: true })} className="gap-1 text-xs">
                        <Send className="h-3 w-3" /> Entregar ao Comercial
                      </Button>
                    )}
                    {/* Stage 2 → 3: Registrar decisão do cliente */}
                    {s.sent_to_client && s.client_approved == null && canEdit && (
                      <div className="flex gap-1.5">
                        <Button size="sm" variant="outline" className="gap-1 text-xs text-green-700 border-green-300 hover:bg-green-50"
                          onClick={() => { setEditingId(s.id); setEditFeedback(s.feedback || ""); updateSample(s.id, { client_approved: true }); }}>
                          <ThumbsUp className="h-3 w-3" /> Cliente aprovou
                        </Button>
                        <Button size="sm" variant="outline" className="gap-1 text-xs text-red-600 border-red-300 hover:bg-red-50"
                          onClick={() => { setEditingId(s.id); setEditFeedback(s.feedback || ""); updateSample(s.id, { client_approved: false }); }}>
                          <ThumbsDown className="h-3 w-3" /> Cliente reprovou
                        </Button>
                      </div>
                    )}
                    {/* Edit feedback */}
                    {!isEditing && canEdit && (
                      <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => { setEditingId(s.id); setEditFeedback(s.feedback || ""); }}>
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                    )}
                    {/* Manipulation order toggle */}
                    <Button
                      variant="ghost" size="sm"
                      className="gap-1 text-xs text-muted-foreground h-7"
                      onClick={() => setShowOrderId(prev => prev === s.id ? null : s.id)}
                    >
                      <ClipboardList className="h-3.5 w-3.5" />
                      {showOrderId === s.id ? "Fechar ordem" : "Ordem"}
                    </Button>
                  </div>
                </div>

                {/* Manipulation order panel */}
                {showOrderId === s.id && (() => {
                  const f = formulas.find(f => f.version === s.formula_version);
                  return (
                    <div className="mt-3 border-t pt-3">
                      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">
                        Ordem de manipulação — {sampleVolume} mL (≈ {sampleVolume} g)
                      </p>
                      {f ? (
                        <ManipulacaoOrder formulaId={f.id} sampleVolume={sampleVolume} />
                      ) : (
                        <p className="text-xs text-muted-foreground">Fórmula v{s.formula_version} não encontrada.</p>
                      )}
                    </div>
                  );
                })()}
              </CardContent>
            </Card>
          );
        })}
      </div>

      {samples.length === 0 && !showCreate && (
        <EmptyState icon={Package} title="Nenhuma amostra registrada" subtitle="Registre amostras produzidas para entrega ao comercial" />
      )}
    </div>
  );
}

/* ============ MANIPULACAO ORDER (per-sample inline) ============ */
function ManipulacaoOrder({ formulaId, sampleVolume }) {
  const [items, setItems] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!formulaId) return;
    setLoading(true);
    api.get(`/pd/formulas/${formulaId}/items`)
      .then(r => setItems(Array.isArray(r.data) ? r.data : []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, [formulaId]);

  if (loading) return <p className="text-xs text-muted-foreground py-2">Carregando composição...</p>;
  if (!items) return null;
  if (items.length === 0) return <p className="text-xs text-muted-foreground py-2">Fórmula sem ingredientes cadastrados.</p>;

  const totalPct = items.reduce((s, r) => s + (r.percentage || 0), 0);

  return (
    <div className="mt-3 rounded-md border bg-background overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="bg-muted/50 border-b">
            <th className="text-left px-3 py-2 font-semibold">Ingrediente</th>
            <th className="text-left px-3 py-2 font-semibold">Fase</th>
            <th className="text-right px-3 py-2 font-semibold">%</th>
            <th className="text-right px-3 py-2 font-semibold">Qtd (g)</th>
          </tr>
        </thead>
        <tbody>
          {items.map((row) => {
            const qty = ((row.percentage || 0) / 100) * sampleVolume;
            return (
              <tr key={row.id} className="border-b last:border-0 hover:bg-muted/20">
                <td className="px-3 py-1.5 font-medium">{row.ingredient_name}</td>
                <td className="px-3 py-1.5 text-muted-foreground">{row.phase || "—"}</td>
                <td className="px-3 py-1.5 text-right font-mono">{(row.percentage || 0).toFixed(3)}</td>
                <td className="px-3 py-1.5 text-right font-mono font-semibold">{qty.toFixed(4)}</td>
              </tr>
            );
          })}
          <tr className="bg-muted/30 font-semibold">
            <td className="px-3 py-1.5" colSpan={2}>TOTAL</td>
            <td className="px-3 py-1.5 text-right font-mono">{totalPct.toFixed(3)}</td>
            <td className="px-3 py-1.5 text-right font-mono">{((totalPct / 100) * sampleVolume).toFixed(4)}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

/* ============ COSTS TAB — P&D view (ingredient costs + submit to Compras) ============ */
function CostsTab({ devId, costVersions, formulas, formulaCostData, onRefresh, canEdit }) {
  const v1 = costVersions?.v1 || {};
  const v2summary = costVersions?.v2 || null;
  const totalFinal = costVersions?.total_final;
  const v1Status = v1.status || "rascunho";
  const isSubmitted = v1Status === "enviado";

  const [manualAdj, setManualAdj] = useState(v1.ingredient_cost_manual || 0);
  const [notes, setNotes] = useState(v1.notes || "");
  const [saving, setSaving] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    setManualAdj(v1.ingredient_cost_manual || 0);
    setNotes(v1.notes || "");
  }, [v1.ingredient_cost_manual, v1.notes]);

  const latestFormula = formulas && formulas.length > 0 ? formulas[0] : null;

  const saveV1 = async () => {
    setSaving(true);
    try {
      await api.put(`/pd/developments/${devId}/cost-versions/v1`, {
        ingredient_cost_manual: parseFloat(manualAdj) || 0,
        notes,
      });
      toast.success("Rascunho de custo salvo.");
      onRefresh();
    } catch (err) { toast.error(err.response?.data?.detail || "Erro ao salvar custo."); }
    finally { setSaving(false); }
  };

  const submitV1 = async () => {
    setSubmitting(true);
    try {
      await api.post(`/pd/developments/${devId}/cost-versions/v1/submit`);
      toast.success("Custo v1 enviado para Compras.");
      onRefresh();
    } catch (err) { toast.error(err.response?.data?.detail || "Erro ao enviar."); }
    finally { setSubmitting(false); }
  };

  const v1StatusConfig = {
    rascunho: { label: "Rascunho", icon: Clock4, cls: "bg-slate-500/10 text-slate-400 border-slate-500/20" },
    enviado:  { label: "Enviado para Compras", icon: CheckCircle, cls: "bg-emerald-500/10 text-emerald-600 border-emerald-500/20" },
  }[v1Status] || { label: v1Status, icon: AlertCircle, cls: "bg-amber-500/10 text-amber-600 border-amber-500/20" };

  const v2StatusConfig = !v2summary ? null : {
    rascunho:   { label: "Compras em análise", icon: Clock4, cls: "bg-sky-500/10 text-sky-600 border-sky-500/20" },
    finalizado: { label: "Custo final disponível", icon: CheckCircle2, cls: "bg-emerald-500/10 text-emerald-600 border-emerald-500/20" },
  }[v2summary.status] || { label: v2summary.status, icon: AlertCircle, cls: "bg-slate-500/10 text-slate-400 border-slate-500/20" };

  return (
    <div className="space-y-6">
      {/* Status header */}
      <div className="flex items-center gap-3 flex-wrap">
        <h3 className="text-base font-semibold flex items-center gap-2">
          <Layers className="h-4 w-4 text-cyan-500" />
          Custo P&D — v1
        </h3>
        <Badge className={`border gap-1.5 ${v1StatusConfig.cls}`}>
          <v1StatusConfig.icon className="h-3 w-3" />
          {v1StatusConfig.label}
        </Badge>
        {v1.submitted_at && (
          <span className="text-xs text-muted-foreground">
            por {v1.submitted_by_name} em {new Date(v1.submitted_at).toLocaleDateString("pt-BR")}
          </span>
        )}
        {v2StatusConfig && (
          <Badge className={`border gap-1.5 ${v2StatusConfig.cls}`}>
            <v2StatusConfig.icon className="h-3 w-3" />
            {v2StatusConfig.label}
          </Badge>
        )}
      </div>

      {/* Formula ingredient cost table (auto) */}
      {latestFormula && (
        <Card className="border-green-200 dark:border-green-900">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base flex items-center gap-2">
                <Beaker className="h-4 w-4 text-green-600" />
                Custo de Ingredientes — Fórmula v{latestFormula.version} ({latestFormula.name})
              </CardTitle>
              <Badge variant="outline" className="text-[10px] text-green-600 border-green-300">Auto-calculado</Badge>
            </div>
          </CardHeader>
          <CardContent>
            <div className="border rounded-md overflow-hidden mb-4">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-[#0A0A0B] text-white text-xs">
                    <th className="text-left p-2 font-medium">Ingrediente</th>
                    <th className="text-right p-2 font-medium w-24">% Fórmula</th>
                    <th className="text-right p-2 font-medium w-28">R$/Kg</th>
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
                        <td className="p-2 text-right font-mono text-xs">{(item.cost_brl || 0).toFixed(4)}</td>
                        <td className="p-2 text-right font-mono text-xs">{pct.toFixed(1)}%</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {formulaCostData && (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="rounded-lg border p-3 text-center">
                  <div className="text-xs text-muted-foreground mb-1">Custo/Kg (R$)</div>
                  <div className="text-lg font-bold">{formulaCostData.total_cost_per_kg.toFixed(4)}</div>
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
                    <div className="text-xs text-muted-foreground mb-1">c/ Perdas ({formulaCostData.indice_perdas}%)</div>
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

      {/* Manual adjustment + notes (editable only when rascunho) */}
      <Card className={isSubmitted ? "opacity-70" : ""}>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Ajuste Manual de Custo de Ingredientes</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <Label className="flex items-center gap-1.5 text-xs text-muted-foreground mb-1">
                <DollarSign className="h-3.5 w-3.5" /> Ajuste manual (R$)
              </Label>
              <Input type="number" step="0.01" value={manualAdj} disabled={isSubmitted || !canEdit}
                onChange={e => setManualAdj(e.target.value)} />
              <p className="text-[11px] text-muted-foreground mt-1">
                Valor somado ao custo auto-calculado da fórmula. Use para MP cotada fora do sistema.
              </p>
            </div>
            <div>
              <Label className="text-xs text-muted-foreground mb-1 block">Observações</Label>
              <Input value={notes} disabled={isSubmitted || !canEdit} onChange={e => setNotes(e.target.value)}
                placeholder="Justificativa do ajuste, fornecedor, etc." />
            </div>
          </div>

          <div className="flex items-center justify-between rounded-lg border p-3 bg-muted/30">
            <span className="text-sm font-medium">Total v1 (ingredientes):</span>
            <span className="text-xl font-bold text-green-700">
              R$ {((v1.ingredient_cost_auto || formulaCostData?.total_cost_per_kg || 0) + (parseFloat(manualAdj) || 0)).toFixed(4)}
            </span>
          </div>

          {!isSubmitted && canEdit && (
            <div className="flex gap-2">
              <Button variant="outline" onClick={saveV1} disabled={saving} className="flex-1 gap-1.5">
                <Save className="h-4 w-4" />
                {saving ? "Salvando..." : "Salvar Rascunho"}
              </Button>
              <Button onClick={submitV1} disabled={submitting} className="flex-1 gap-1.5 bg-emerald-600 hover:bg-emerald-700">
                <Send className="h-4 w-4" />
                {submitting ? "Enviando..." : "Enviar para Compras"}
              </Button>
            </div>
          )}

          {isSubmitted && (
            <div className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 dark:bg-emerald-950 dark:border-emerald-900 p-3 text-sm text-emerald-700 dark:text-emerald-300">
              <CheckCircle2 className="h-4 w-4 shrink-0" />
              Custo v1 enviado e bloqueado para edição. Aguardando análise comercial.
            </div>
          )}
        </CardContent>
      </Card>

      {/* Final cost (shown to P&D only when v2 is finalized) */}
      {totalFinal != null && (
        <Card className="border-2 border-emerald-500/30 bg-emerald-50/50 dark:bg-emerald-950/30">
          <CardContent className="pt-5 pb-5">
            <div className="flex items-center justify-between flex-wrap gap-3">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-5 w-5 text-emerald-600" />
                <div>
                  <p className="font-semibold text-sm">Custo Final Aprovado pelo Comercial</p>
                  <p className="text-xs text-muted-foreground">
                    Finalizado em {v2summary?.finalized_at ? new Date(v2summary.finalized_at).toLocaleDateString("pt-BR") : "—"}
                  </p>
                </div>
              </div>
              <div className="text-right">
                <div className="text-2xl font-bold text-emerald-700">R$ {totalFinal.toFixed(2)}</div>
                <div className="text-[11px] text-muted-foreground">custo total unitário</div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

/* ============ COMERCIAL TAB — Compras view (full v1 + v2 inputs) ============ */
function ComercialTab({ devId, costVersions, formulaCostData, onRefresh }) {
  const v1 = costVersions?.v1 || {};
  const v2 = costVersions?.v2 || {};
  const v1Status = v1.status || "rascunho";
  const v2Status = v2.status || null;
  const isFinalized = v2Status === "finalizado";
  const totalFinal = costVersions?.total_final || 0;

  const [form, setForm] = useState({
    packaging_cost: v2.packaging_cost || 0,
    labor_cost: v2.labor_cost || 0,
    overhead_cost: v2.overhead_cost || 0,
    other_cost: v2.other_cost || 0,
    notes: v2.notes || "",
  });
  const [saving, setSaving] = useState(false);
  const [finalizing, setFinalizing] = useState(false);

  useEffect(() => {
    setForm({
      packaging_cost: v2.packaging_cost || 0,
      labor_cost: v2.labor_cost || 0,
      overhead_cost: v2.overhead_cost || 0,
      other_cost: v2.other_cost || 0,
      notes: v2.notes || "",
    });
  }, [v2.packaging_cost, v2.labor_cost, v2.overhead_cost, v2.other_cost, v2.notes]);

  const v2Total = (parseFloat(form.packaging_cost) || 0) + (parseFloat(form.labor_cost) || 0)
    + (parseFloat(form.overhead_cost) || 0) + (parseFloat(form.other_cost) || 0);
  const previewTotal = (v1.total || 0) + v2Total;

  const saveV2 = async () => {
    setSaving(true);
    try {
      await api.put(`/pd/developments/${devId}/cost-versions/v2`, {
        packaging_cost: parseFloat(form.packaging_cost) || 0,
        labor_cost: parseFloat(form.labor_cost) || 0,
        overhead_cost: parseFloat(form.overhead_cost) || 0,
        other_cost: parseFloat(form.other_cost) || 0,
        notes: form.notes,
      });
      toast.success("Custos comerciais salvos.");
      onRefresh();
    } catch (err) { toast.error(err.response?.data?.detail || "Erro ao salvar."); }
    finally { setSaving(false); }
  };

  const finalizeV2 = async () => {
    setFinalizing(true);
    try {
      await api.post(`/pd/developments/${devId}/cost-versions/v2/finalize`);
      toast.success("Custo comercial finalizado e comunicado ao P&D.");
      onRefresh();
    } catch (err) { toast.error(err.response?.data?.detail || "Erro ao finalizar."); }
    finally { setFinalizing(false); }
  };

  if (v1Status !== "enviado") {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
        <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
          <Clock4 className="h-7 w-7 text-muted-foreground" />
        </div>
        <p className="font-medium">Aguardando custo v1 do P&D</p>
        <p className="text-sm text-muted-foreground max-w-sm">
          O setor de P&D ainda não enviou o custo de ingredientes. Assim que o custo v1 for submetido, você poderá preencher os custos comerciais aqui.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3 flex-wrap">
        <h3 className="text-base font-semibold flex items-center gap-2">
          <Building2 className="h-4 w-4 text-sky-500" />
          Análise Comercial — Custo v2
        </h3>
        {v2Status && (
          <Badge className={`border gap-1.5 ${v2Status === "finalizado"
            ? "bg-emerald-500/10 text-emerald-600 border-emerald-500/20"
            : "bg-sky-500/10 text-sky-600 border-sky-500/20"}`}>
            {v2Status === "finalizado" ? <CheckCircle2 className="h-3 w-3" /> : <Clock4 className="h-3 w-3" />}
            {v2Status === "finalizado" ? "Finalizado" : "Rascunho"}
          </Badge>
        )}
        {isFinalized && v2.finalized_at && (
          <span className="text-xs text-muted-foreground">
            por {v2.finalized_by_name} em {new Date(v2.finalized_at).toLocaleDateString("pt-BR")}
          </span>
        )}
      </div>

      {/* V1 summary (read-only for Compras) */}
      <Card className="border-green-200/50 dark:border-green-900/50">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center gap-2 text-muted-foreground">
            <Beaker className="h-3.5 w-3.5 text-green-600" />
            Custo P&D (v1 — recebido e bloqueado)
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="rounded-lg border p-3 text-center">
              <div className="text-xs text-muted-foreground mb-1">Ingredientes Auto</div>
              <div className="font-bold text-sm">R$ {(v1.ingredient_cost_auto || 0).toFixed(4)}</div>
            </div>
            {(v1.ingredient_cost_manual || 0) > 0 && (
              <div className="rounded-lg border p-3 text-center">
                <div className="text-xs text-muted-foreground mb-1">Ajuste Manual</div>
                <div className="font-bold text-sm">R$ {(v1.ingredient_cost_manual || 0).toFixed(4)}</div>
              </div>
            )}
            <div className="rounded-lg border bg-green-50 dark:bg-green-950 p-3 text-center col-span-2">
              <div className="text-xs text-muted-foreground mb-1">Total v1 (ingredientes)</div>
              <div className="font-bold text-lg text-green-700">R$ {(v1.total || 0).toFixed(4)}</div>
            </div>
          </div>
          {v1.notes && (
            <p className="mt-3 text-xs text-muted-foreground italic border-l-2 border-green-300 pl-2">{v1.notes}</p>
          )}
          {formulaCostData && (
            <div className="mt-3 grid grid-cols-2 sm:grid-cols-3 gap-2">
              <div className="rounded-lg border p-2.5 text-center">
                <div className="text-[10px] text-muted-foreground mb-0.5">Custo Unit. (fórmula)</div>
                <div className="font-bold text-sm">R$ {formulaCostData.custo_unitario.toFixed(2)}</div>
                <div className="text-[10px] text-muted-foreground">{formulaCostData.volume} {formulaCostData.volume_unit}</div>
              </div>
              {formulaCostData.indice_perdas > 0 && (
                <div className="rounded-lg border p-2.5 text-center">
                  <div className="text-[10px] text-muted-foreground mb-0.5">c/ Perdas ({formulaCostData.indice_perdas}%)</div>
                  <div className="font-bold text-sm text-orange-600">R$ {formulaCostData.custo_com_perdas.toFixed(2)}</div>
                </div>
              )}
              <div className="rounded-lg border p-2.5 text-center">
                <div className="text-[10px] text-muted-foreground mb-0.5">Cotação US$</div>
                <div className="font-bold text-sm">{formulaCostData.cotacao_usd.toFixed(2)}</div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* V2 inputs */}
      <Card className={isFinalized ? "opacity-75" : ""}>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <ShoppingCart className="h-4 w-4 text-sky-600" />
            Custos Adicionais (Compras)
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {[
              { key: "packaging_cost", label: "Embalagem (R$)", icon: Package, color: "text-amber-500" },
              { key: "labor_cost", label: "Mão de Obra (R$)", icon: DollarSign, color: "text-sky-500" },
              { key: "overhead_cost", label: "Overhead / Fixos (R$)", icon: Building2, color: "text-violet-500" },
              { key: "other_cost", label: "Outros (R$)", icon: Layers, color: "text-rose-500" },
            ].map(({ key, label, icon: Icon, color }) => (
              <div key={key}>
                <Label className={`flex items-center gap-1.5 text-xs mb-1 ${color}`}>
                  <Icon className="h-3.5 w-3.5" /> {label}
                </Label>
                <Input type="number" step="0.01" value={form[key]} disabled={isFinalized}
                  onChange={e => setForm(p => ({ ...p, [key]: e.target.value }))} />
              </div>
            ))}
          </div>

          <div>
            <Label className="text-xs text-muted-foreground mb-1 block">Observações do Compras</Label>
            <Input value={form.notes} disabled={isFinalized} onChange={e => setForm(p => ({ ...p, notes: e.target.value }))}
              placeholder="Fornecedor, cotação, condições de pagamento, etc." />
          </div>

          <Separator />

          {/* Cost breakdown summary */}
          <div className="rounded-lg border bg-muted/20 p-4 space-y-2">
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Ingredientes P&D (v1)</span>
              <span className="font-mono">R$ {(v1.total || 0).toFixed(4)}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Embalagem</span>
              <span className="font-mono">R$ {(parseFloat(form.packaging_cost) || 0).toFixed(2)}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Mão de Obra</span>
              <span className="font-mono">R$ {(parseFloat(form.labor_cost) || 0).toFixed(2)}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Overhead / Fixos</span>
              <span className="font-mono">R$ {(parseFloat(form.overhead_cost) || 0).toFixed(2)}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Outros</span>
              <span className="font-mono">R$ {(parseFloat(form.other_cost) || 0).toFixed(2)}</span>
            </div>
            <Separator />
            <div className="flex justify-between font-bold text-base">
              <span>Total Final</span>
              <span className="text-emerald-700">R$ {(isFinalized ? totalFinal : previewTotal).toFixed(2)}</span>
            </div>
          </div>

          {!isFinalized && (
            <div className="flex gap-2">
              <Button variant="outline" onClick={saveV2} disabled={saving} className="flex-1 gap-1.5">
                <Save className="h-4 w-4" />
                {saving ? "Salvando..." : "Salvar Rascunho"}
              </Button>
              <Button onClick={finalizeV2} disabled={finalizing || !v2Status} className="flex-1 gap-1.5 bg-emerald-600 hover:bg-emerald-700">
                <CheckCircle2 className="h-4 w-4" />
                {finalizing ? "Finalizando..." : "Finalizar Custo"}
              </Button>
            </div>
          )}

          {!v2Status && (
            <p className="text-xs text-center text-muted-foreground">Salve um rascunho antes de finalizar.</p>
          )}

          {isFinalized && (
            <div className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 dark:bg-emerald-950 dark:border-emerald-900 p-3 text-sm text-emerald-700 dark:text-emerald-300">
              <CheckCircle2 className="h-4 w-4 shrink-0" />
              Custo finalizado e comunicado ao P&D. Custo total: <strong>R$ {totalFinal.toFixed(2)}</strong>
            </div>
          )}
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


/* ============ LIVE DOCUMENTS TAB (FT/EPA versionados) ============ */

const LIVE_DOC_STATUS_CONFIG = {
  em_revisao: { label: "Em revisão", className: "bg-amber-500/10 text-amber-700 border-amber-300" },
  aprovado: { label: "Aprovado · vigente", className: "bg-emerald-500/10 text-emerald-700 border-emerald-300" },
  reprovado: { label: "Reprovado", className: "bg-red-500/10 text-red-600 border-red-300" },
  substituido: { label: "Substituído", className: "bg-muted text-muted-foreground border-border" },
};

const FIELD_LABELS = {
  briefing: "Briefing",
  ficha_tecnica: "Ficha técnica",
  bom_bulk_formula: "BOM bulk / fórmula",
  bom_embalagem_primaria: "BOM embalagem primária",
  especificacoes_produto_acabado: "Especificações do produto acabado",
  especificacoes_embalagem: "Especificações de embalagem",
  ordem_adicao: "Ordem de adição",
  parametros_in_process: "Parâmetros in-process",
  modo_preparo: "Modo de preparo",
  identificacao: "Identificação",
  identificacao_produto: "Identificação do produto",
  composicao_completa: "Composição completa",
  rendimento_teorico: "Rendimento teórico",
  observacoes_tecnicas: "Observações técnicas",
  informacoes_rotulo: "Informações de rótulo",
  kickoff: "Kickoff",
  aprovacao_cliente: "Aprovação do cliente",
  criterios_liberacao_lote: "Critérios de liberação de lote",
};

function fieldLabel(key) {
  if (!key) return "";
  return FIELD_LABELS[key] || key.replace(/_/g, " ");
}

function LiveDocumentsTab({ reqId, req }) {
  const { user } = useAuth();
  const role = (user?.role || "").toLowerCase();
  const isReviewer = ["admin", "lider_pd", "qa", "engenharia_produto", "formulador", "gestor"].includes(role);

  const [docType, setDocType] = useState("ficha_tecnica");
  const [versions, setVersions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [diffOpen, setDiffOpen] = useState(false);
  const [diffData, setDiffData] = useState(null);
  const [diffLoading, setDiffLoading] = useState(false);
  const [actingTaskId, setActingTaskId] = useState(null);
  const [generating, setGenerating] = useState(false);

  const fetchVersions = useCallback(async () => {
    if (!reqId) return;
    setLoading(true);
    try {
      const { data } = await api.get(`/pd/requests/${reqId}/live-documents/${docType}/versions`);
      setVersions(Array.isArray(data) ? data : []);
    } catch (err) {
      const detail = err?.response?.data?.detail || "Erro ao carregar versões";
      if (err?.response?.status !== 404) toast.error(detail);
      setVersions([]);
    } finally {
      setLoading(false);
    }
  }, [reqId, docType]);

  useEffect(() => { fetchVersions(); }, [fetchVersions]);

  const openDiff = async (versionId) => {
    setDiffOpen(true);
    setDiffData(null);
    setDiffLoading(true);
    try {
      const { data } = await api.get(`/pd/document-versions/${versionId}/diff`);
      setDiffData(data);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Erro ao carregar diff");
    } finally {
      setDiffLoading(false);
    }
  };

  const decideTask = async (taskId, decision) => {
    let comment = "";
    if (decision === "rejected") {
      comment = window.prompt("Justifique a reprovação (obrigatório):", "");
      if (!comment || !comment.trim()) {
        toast.error("Justificativa obrigatória para reprovação.");
        return;
      }
    } else {
      comment = window.prompt("Comentário (opcional):", "") || "";
    }
    setActingTaskId(taskId);
    try {
      await api.put(`/workflow/tasks/${taskId}/decision`, { decision, comment });
      toast.success(decision === "approved" ? "Tarefa aprovada" : "Tarefa reprovada");
      await fetchVersions();
      if (diffData?.current?.id) {
        const { data } = await api.get(`/pd/document-versions/${diffData.current.id}/diff`);
        setDiffData(data);
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Erro ao registrar decisão");
    } finally {
      setActingTaskId(null);
    }
  };

  const generateNow = async () => {
    const reason = window.prompt("Motivo da nova versão (curto):", "Geração manual");
    if (!reason) return;
    setGenerating(true);
    try {
      await api.post(`/pd/requests/${reqId}/live-documents/${docType}/generate`, {
        reason,
        changed_fields: [docType],
      });
      toast.success("Nova versão gerada");
      await fetchVersions();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Não foi possível gerar a versão");
    } finally {
      setGenerating(false);
    }
  };

  const docLabel = docType === "ficha_tecnica" ? "Ficha Técnica" : "EPA";

  return (
    <div className="space-y-5" data-testid="live-docs-tab">
      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <CardTitle className="text-base flex items-center gap-2">
                <ShieldCheck className="h-4 w-4 text-emerald-600" />
                Documentos Vivos — versionamento + aprovação
              </CardTitle>
              <p className="text-xs text-muted-foreground mt-1">
                Cada alteração em dado-fonte gera uma nova versão e cria tarefas de aprovação.
                Apenas a versão <span className="font-medium text-emerald-700">aprovada</span> é vigente para produção.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <div className="inline-flex rounded-md border border-border bg-card overflow-hidden">
                <button
                  type="button"
                  onClick={() => setDocType("ficha_tecnica")}
                  data-testid="live-docs-toggle-ft"
                  className={`px-3 py-1.5 text-xs font-medium ${docType === "ficha_tecnica" ? "bg-foreground text-background" : "text-muted-foreground hover:text-foreground"}`}
                >
                  Ficha Técnica
                </button>
                <button
                  type="button"
                  onClick={() => setDocType("epa")}
                  data-testid="live-docs-toggle-epa"
                  className={`px-3 py-1.5 text-xs font-medium border-l border-border ${docType === "epa" ? "bg-foreground text-background" : "text-muted-foreground hover:text-foreground"}`}
                >
                  EPA
                </button>
              </div>
              {isReviewer && (
                <Button size="sm" variant="outline" onClick={generateNow} disabled={generating} data-testid="live-docs-generate-btn" className="gap-1.5">
                  {generating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
                  Gerar versão
                </Button>
              )}
              <Button size="sm" variant="ghost" onClick={fetchVersions} disabled={loading} data-testid="live-docs-refresh-btn">
                <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="pt-0">
          {loading ? (
            <div className="py-10 flex items-center justify-center text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin" />
            </div>
          ) : versions.length === 0 ? (
            <div className="py-12 text-center text-sm text-muted-foreground" data-testid="live-docs-empty">
              <FileText className="h-10 w-10 mx-auto mb-3 text-muted-foreground/30" />
              Nenhuma versão de {docLabel} disponível ainda.<br />
              {docType === "ficha_tecnica"
                ? "Disponível após aprovação do cliente e fórmula registrada."
                : "Disponível após kickoff, aprovação do cliente e fórmula registrada."}
            </div>
          ) : (
            <div className="space-y-2">
              {versions.map((v) => {
                const cfg = LIVE_DOC_STATUS_CONFIG[v.status] || LIVE_DOC_STATUS_CONFIG.em_revisao;
                const isActive = v.active_for_operation && v.status === "aprovado";
                return (
                  <div
                    key={v.id}
                    data-testid={`live-doc-version-${v.version_code}`}
                    className={`rounded-lg border ${isActive ? "border-emerald-300 bg-emerald-500/5" : "border-border bg-card"} p-3 flex items-start gap-3`}
                  >
                    <div className="shrink-0 mt-0.5">
                      <div className={`h-9 w-9 rounded-md flex items-center justify-center ${isActive ? "bg-emerald-600 text-white" : "bg-muted text-foreground"}`}>
                        <FileText className="h-4 w-4" />
                      </div>
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-semibold text-sm">{v.version_code || `v${v.version_number}`}</span>
                        <Badge variant="outline" className={`text-[10px] ${cfg.className}`}>{cfg.label}</Badge>
                        {isActive && <Badge variant="outline" className="text-[10px] bg-emerald-500/10 text-emerald-700 border-emerald-300">VIGENTE</Badge>}
                        {v.source_trigger && v.source_trigger !== "manual" && (
                          <Badge variant="outline" className="text-[10px]">auto · {v.source_trigger}</Badge>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground mt-1 truncate">
                        {v.reason || "(sem motivo)"} · por {v.created_by_name || "—"} · {v.created_at?.replace("T", " ").slice(0, 16)}
                      </p>
                      {Array.isArray(v.changed_fields) && v.changed_fields.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-2">
                          {v.changed_fields.slice(0, 6).map((f) => (
                            <Badge key={f} variant="outline" className="text-[10px] bg-amber-500/5 text-amber-700 border-amber-200">
                              {fieldLabel(f)}
                            </Badge>
                          ))}
                          {v.changed_fields.length > 6 && (
                            <Badge variant="outline" className="text-[10px]">+{v.changed_fields.length - 6}</Badge>
                          )}
                        </div>
                      )}
                    </div>
                    <div className="shrink-0 flex flex-col items-end gap-1.5">
                      <Button
                        size="sm"
                        variant="outline"
                        className="gap-1.5 h-7 text-xs"
                        onClick={() => openDiff(v.id)}
                        data-testid={`live-doc-view-${v.version_code}`}
                      >
                        <Eye className="h-3 w-3" /> Ver diff
                      </Button>
                      <a
                        href={`${BACKEND_URL}/api/pd/document-versions/${v.id}/pdf`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-[11px] text-muted-foreground hover:text-foreground flex items-center gap-1"
                        data-testid={`live-doc-pdf-${v.version_code}`}
                      >
                        <Download className="h-3 w-3" /> PDF
                      </a>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={diffOpen} onOpenChange={setDiffOpen}>
        <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto" data-testid="live-doc-diff-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-emerald-600" />
              Diff & aprovação — {diffData?.current?.version_code || "..."}
            </DialogTitle>
            <DialogDescription>
              {diffData?.previous
                ? `Comparando com ${diffData.previous.version_code}`
                : "Primeira versão (sem versão anterior)"}
            </DialogDescription>
          </DialogHeader>

          {diffLoading || !diffData ? (
            <div className="py-12 flex items-center justify-center">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <div className="space-y-4">
              {Array.isArray(diffData.current?.source_changes) && diffData.current.source_changes.length > 0 && (
                <div className="rounded-md border border-border bg-amber-500/5 p-3">
                  <div className="text-xs font-semibold text-amber-700 mb-2 flex items-center gap-1.5">
                    <AlertTriangle className="h-3.5 w-3.5" /> Mudanças no dado-fonte que dispararam esta versão
                  </div>
                  <div className="space-y-1 text-xs">
                    {diffData.current.source_changes.map((c, i) => (
                      <div key={i} className="flex items-start gap-2">
                        <span className="font-medium min-w-[140px]">{c.label || c.field}:</span>
                        <span className="text-muted-foreground line-through">{String(c.before ?? "—")}</span>
                        <ArrowRight className="h-3 w-3 mt-0.5 text-muted-foreground" />
                        <span className="text-foreground font-medium">{String(c.after ?? "—")}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div>
                <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                  Diferenças campo a campo ({diffData.differences?.length || 0})
                </h4>
                {(!diffData.differences || diffData.differences.length === 0) ? (
                  <p className="text-xs text-muted-foreground italic">Sem diferenças detectadas no snapshot.</p>
                ) : (
                  <div className="space-y-1.5 max-h-[260px] overflow-y-auto pr-1">
                    {diffData.differences.map((d, i) => (
                      <div key={i} className="rounded border border-border p-2 text-xs">
                        <div className="font-medium mb-1">{d.label || d.path}</div>
                        <div className="grid grid-cols-2 gap-2">
                          <div className="rounded bg-red-500/5 border border-red-200 px-2 py-1 break-all">
                            <div className="text-[10px] uppercase text-red-600/70 mb-0.5">Antes</div>
                            <div className="text-foreground">{String(d.before ?? "—")}</div>
                          </div>
                          <div className="rounded bg-emerald-500/5 border border-emerald-200 px-2 py-1 break-all">
                            <div className="text-[10px] uppercase text-emerald-700/70 mb-0.5">Depois</div>
                            <div className="text-foreground">{String(d.after ?? "—")}</div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div>
                <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">
                  Tarefas de aprovação
                </h4>
                {(!diffData.approval_tasks || diffData.approval_tasks.length === 0) ? (
                  <p className="text-xs text-muted-foreground italic">Nenhuma tarefa de aprovação vinculada.</p>
                ) : (
                  <div className="space-y-1.5">
                    {diffData.approval_tasks.map((t) => {
                      const isClosed = t.status === "concluida" || t.status === "cancelada";
                      const decisionBadge =
                        t.decision === "approved"
                          ? "bg-emerald-500/10 text-emerald-700 border-emerald-300"
                          : t.decision === "rejected"
                            ? "bg-red-500/10 text-red-600 border-red-300"
                            : "bg-amber-500/10 text-amber-700 border-amber-300";
                      const isMine = t.responsible_id === user?.id;
                      const canDecide = !isClosed && (isMine || role === "admin" || role === "gestor" || role === "lider_pd");
                      return (
                        <div key={t.id} className="rounded border border-border p-2 text-xs flex items-start gap-2" data-testid={`approval-task-${t.id}`}>
                          <div className="flex-1 min-w-0">
                            <div className="flex flex-wrap items-center gap-1.5">
                              <span className="font-medium">{t.title}</span>
                              <Badge variant="outline" className={`text-[10px] ${decisionBadge}`}>
                                {t.decision === "approved" ? "Aprovada" : t.decision === "rejected" ? "Reprovada" : t.status}
                              </Badge>
                            </div>
                            <div className="text-muted-foreground mt-0.5">
                              Resp.: {t.responsible_name || "—"} · prazo {t.due_date?.slice(0, 10) || "—"}
                              {t.decision_comment && (
                                <span className="block mt-0.5 italic">"{t.decision_comment}"</span>
                              )}
                            </div>
                          </div>
                          {canDecide && (
                            <div className="flex flex-col gap-1 shrink-0">
                              <Button
                                size="sm"
                                variant="default"
                                className="h-7 px-2 gap-1 text-xs bg-emerald-600 hover:bg-emerald-700"
                                onClick={() => decideTask(t.id, "approved")}
                                disabled={actingTaskId === t.id}
                                data-testid={`approval-task-${t.id}-approve`}
                              >
                                <ThumbsUp className="h-3 w-3" /> Aprovar
                              </Button>
                              <Button
                                size="sm"
                                variant="destructive"
                                className="h-7 px-2 gap-1 text-xs"
                                onClick={() => decideTask(t.id, "rejected")}
                                disabled={actingTaskId === t.id}
                                data-testid={`approval-task-${t.id}-reject`}
                              >
                                <ThumbsDown className="h-3 w-3" /> Reprovar
                              </Button>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setDiffOpen(false)} data-testid="live-doc-diff-close">Fechar</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}


// ============================================================
// Item 3 - Tab "Ordens de Manipulação" (OM em lote)
// ============================================================
function OrdensManipulacaoTab({ req, dev, formulas, clientInfo }) {
  const [sampleId, setSampleId] = useState(null);
  const [variacoes, setVariacoes] = useState([]);
  const [loading, setLoading] = useState(false);
  const [sampleNotFound, setSampleNotFound] = useState(false);

  useEffect(() => {
    const resolveSample = async () => {
      setLoading(true);
      try {
        if (clientInfo?._sample_id) {
          setSampleId(clientInfo._sample_id);
          const { data } = await api.get(`/crm/samples/${clientInfo._sample_id}`);
          setVariacoes(data?.variacoes || []);
        } else if (clientInfo?._variacao_id) {
          const { data: samples } = await api.get("/crm/samples");
          const sample = (samples || []).find(s =>
            (s.variacoes || []).some(v => v.id === clientInfo._variacao_id)
          );
          if (sample) {
            setSampleId(sample.id);
            setVariacoes(sample.variacoes || []);
          } else {
            setSampleNotFound(true);
          }
        } else {
          setSampleNotFound(true);
        }
      } catch (e) {
        console.error(e);
        setSampleNotFound(true);
      } finally {
        setLoading(false);
      }
    };
    resolveSample();
  }, [clientInfo?._sample_id, clientInfo?._variacao_id]);

  if (loading) return <div className="text-sm text-muted-foreground py-6">Carregando…</div>;
  if (sampleNotFound || !sampleId) {
    return (
      <Card>
        <CardContent className="pt-6 text-sm text-muted-foreground space-y-2">
          <p className="font-medium text-foreground">
            Ordens de Manipulação só estão disponíveis para projetos com amostra vinculada no CRM.
          </p>
          <p>
            Use a aba <b>Amostras</b> para criar lotes simples. OMs em lote precisam de uma amostra
            CRM com múltiplas variações compartilhando a mesma base.
          </p>
        </CardContent>
      </Card>
    );
  }
  return <OrdemManipulacaoSection sampleId={sampleId} formulas={formulas} variacoes={variacoes} />;
}
