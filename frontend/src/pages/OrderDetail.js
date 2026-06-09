import React, { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { BACKEND_URL } from "@/lib/backend";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { ArrowLeft, Save, Download, Loader2, Plus, Trash2, FileText, Pencil, Check, X, ShieldCheck, AlertTriangle, Factory, Lock, CheckCircle2 } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";

const TIPOS_SERVICO = [
  { value: "producao",    label: "Produção",    desc: "Primeiro pedido — amostra aprovada, gera novo SKU" },
  { value: "reposicao",  label: "Reposição",   desc: "SKU existente, sem nova amostra, fluxo simplificado" },
  { value: "retrabalho", label: "Retrabalho",  desc: "Reprocessamento de lote com não conformidade" },
];

const NIVEIS_FORMALIZACAO = [
  { value: 1, label: "Nível 1 — Aceite simples",   desc: "Cliente recorrente + valor dentro do threshold" },
  { value: 2, label: "Nível 2 — Aceite formal",    desc: "Cliente novo OU valor acima do threshold" },
  { value: 3, label: "Nível 3 — Aditivo ao CGI",   desc: "Alto valor, condições atípicas ou risco elevado" },
];

const CATEGORIAS_INSUMO = [
  "Arte / Aprovação de arte",
  "Cadastro ANVISA / Notificação",
  "Rótulos / Gravação",
  "Frascos / Potes",
  "Tampas / Sobretampa",
  "Cartucho",
  "Válvulas",
  "Celofane / Sleeve",
  "Display",
  "Caixa de embarque",
  "Essência / Fragrância",
  "Matérias-primas específicas",
];

const INSUMO_STATUS_CFG = {
  pendente:     { label: "Pendente",     cls: "bg-slate-100 text-slate-600" },
  em_andamento: { label: "Em andamento", cls: "bg-amber-100 text-amber-700" },
  confirmado:   { label: "Confirmado",   cls: "bg-blue-100 text-blue-700" },
  recebido:     { label: "Recebido",     cls: "bg-green-100 text-green-700" },
};

function buildDefaultChecklist() {
  return CATEGORIAS_INSUMO.map(cat => ({
    categoria: cat, ativo: false, origem: "kuryos",
    status: "pendente", responsavel: "", data_prevista: null, observacoes: "",
  }));
}

// NNN/NNN/NNN auto-mask
function maskCondicaoPgto(raw) {
  const digits = raw.replace(/\D/g, "").slice(0, 9);
  if (digits.length <= 3) return digits;
  if (digits.length <= 6) return `${digits.slice(0, 3)}/${digits.slice(3)}`;
  return `${digits.slice(0, 3)}/${digits.slice(3, 6)}/${digits.slice(6)}`;
}

const STATUSES_IMUTAVEL = new Set(["confirmado", "em_producao", "concluido"]);

const STATUS_OPTIONS = [
  { value: "rascunho", label: "Rascunho" },
  { value: "confirmado", label: "Confirmado" },
  { value: "em_producao", label: "Em Produção" },
  { value: "concluido", label: "Concluído" },
  { value: "cancelado", label: "Cancelado" },
];

const STATUS_COLORS = {
  rascunho: "bg-slate-500/10 text-slate-600 border-slate-300 dark:text-slate-300",
  confirmado: "bg-blue-500/10 text-blue-600 border-blue-300 dark:text-blue-300",
  em_producao: "bg-amber-500/10 text-amber-700 border-amber-300 dark:text-amber-300",
  concluido: "bg-green-500/10 text-green-700 border-green-300 dark:text-green-300",
  cancelado: "bg-red-500/10 text-red-700 border-red-300 dark:text-red-300",
};

function formatCurrencyBR(value) {
  if (value === null || value === undefined || value === "") return "R$ 0,00";
  const n = Number(value);
  if (isNaN(n)) return "R$ 0,00";
  return `R$ ${n.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function dateInputValue(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toISOString().slice(0, 10);
  } catch { return ""; }
}

export default function OrderDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [order, setOrder] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState(null);

  const fetchOrder = useCallback(async () => {
    try {
      const res = await api.get(`/orders/${id}`);
      setOrder(res.data);
      setForm(deepClone(res.data));
    } catch (err) {
      toast.error("Erro ao carregar pedido");
      navigate("/orders");
    } finally {
      setLoading(false);
    }
  }, [id, navigate]);

  useEffect(() => { fetchOrder(); }, [fetchOrder]);

  const startEdit = () => {
    setForm(deepClone(order));
    ensureChecklist();
    setEditing(true);
  };

  const cancelEdit = () => {
    setForm(deepClone(order));
    setEditing(false);
  };

  const saveOrder = async () => {
    setSaving(true);
    try {
      const isLocked = STATUSES_IMUTAVEL.has(order.status);
      const payload = isLocked
        ? {
            status: form.status,
            observacoes: form.observacoes,
            checklist_insumos: form.checklist_insumos,
          }
        : {
            numero_pedido: form.numero_pedido,
            data_pedido: form.data_pedido,
            status: form.status,
            tipo_servico: form.tipo_servico,
            nivel_formalizacao: form.nivel_formalizacao,
            cliente: form.cliente,
            frete: form.frete,
            items: form.items,
            condicoes: form.condicoes,
            insumos: form.insumos,
            checklist_insumos: form.checklist_insumos,
            observacoes: form.observacoes,
          };
      const res = await api.put(`/orders/${id}`, payload);
      setOrder(res.data);
      setForm(deepClone(res.data));
      setEditing(false);
      toast.success("Pedido atualizado!");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Erro ao salvar");
    } finally {
      setSaving(false);
    }
  };

  const updateStatus = async (newStatus) => {
    try {
      const res = await api.put(`/orders/${id}`, { status: newStatus });
      setOrder(res.data);
      setForm(deepClone(res.data));
      toast.success("Status atualizado!");
    } catch (err) {
      toast.error("Erro ao alterar status");
    }
  };

  const downloadPDF = async () => {
    try {
      const response = await api.get(`/orders/${id}/pdf`, { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([response.data], { type: "application/pdf" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = `ordem_producao_${order?.numero_pedido || id}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      toast.success("PDF gerado!");
    } catch (err) {
      toast.error("Erro ao gerar PDF");
    }
  };

  const signCGI = async () => {
    try {
      const res = await api.post(`/orders/${id}/sign-cgi`);
      setOrder(res.data);
      setForm(deepClone(res.data));
      toast.success("CGI assinado com sucesso!");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Erro ao assinar CGI");
    }
  };

  const approveCliente = async () => {
    try {
      const res = await api.post(`/orders/${id}/aprovar-cliente`, { observacoes: "" });
      setOrder(res.data); setForm(deepClone(res.data));
      toast.success("Aprovação do cliente registrada");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Erro");
    }
  };

  const ensureChecklist = () => {
    if (!form.checklist_insumos || form.checklist_insumos.length < CATEGORIAS_INSUMO.length) {
      const existing = form.checklist_insumos || [];
      const existingCats = new Set(existing.map(c => c.categoria));
      const missing = CATEGORIAS_INSUMO.filter(cat => !existingCats.has(cat)).map(cat => ({
        categoria: cat, ativo: false, origem: "kuryos", status: "pendente", responsavel: "", data_prevista: null, observacoes: "",
      }));
      setForm(p => ({ ...p, checklist_insumos: [...existing, ...missing] }));
    }
  };

  const generateOP = async () => {
    try {
      const res = await api.post(`/orders/${id}/create-op`);
      toast.success(`OP ${res.data.numero_op} gerada!`);
      fetchOrder();
      navigate(`/ops/${res.data.id}`);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Erro ao gerar OP");
    }
  };

  if (loading || !form) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const onCli = (k, v) => setForm(p => ({ ...p, cliente: { ...p.cliente, [k]: v } }));
  const onFre = (k, v) => setForm(p => ({ ...p, frete: { ...p.frete, [k]: v } }));
  const onCnd = (k, v) => setForm(p => ({ ...p, condicoes: { ...p.condicoes, [k]: v } }));

  const updateItem = (idx, key, value) => {
    setForm(p => {
      const items = [...(p.items || [])];
      const it = { ...items[idx], [key]: value };
      // Auto-recompute valor_total
      if (key === "valor_unitario" || key === "qtd") {
        const vu = parseFloat(key === "valor_unitario" ? value : it.valor_unitario) || 0;
        const q = parseFloat(key === "qtd" ? value : it.qtd) || 0;
        it.valor_total = +(vu * q).toFixed(2);
      }
      items[idx] = it;
      return { ...p, items };
    });
  };

  const addItem = () => {
    setForm(p => ({
      ...p,
      items: [...(p.items || []), {
        codigo_kuryos: "", codigo_cliente: "", item: "",
        prazo_entrega: "20 Dias", valor_unitario: 0, qtd: 0, valor_total: 0,
      }],
    }));
  };

  const removeItem = (idx) => {
    setForm(p => ({ ...p, items: (p.items || []).filter((_, i) => i !== idx) }));
  };

  const totalCalc = (form.items || []).reduce((s, it) => s + (Number(it.valor_total) || 0), 0);
  const statusCfg = STATUS_COLORS[form.status] || STATUS_COLORS.rascunho;

  return (
    <div className="h-full overflow-auto">
      <div className="max-w-5xl mx-auto p-6 space-y-5">
        {/* Header */}
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="flex items-start gap-3">
            <Button variant="ghost" size="icon" onClick={() => navigate("/orders")} data-testid="back-to-orders">
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <div>
              <h1 className="text-xl font-heading font-semibold flex items-center gap-2">
                Ordem de Produção
                <span className="font-mono text-primary">#{form.numero_pedido}</span>
              </h1>
              <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                <Badge className={statusCfg}>
                  {STATUS_OPTIONS.find(s => s.value === form.status)?.label || form.status}
                </Badge>
                {form.auto_created && (
                  <Badge variant="outline" className="text-[10px] gap-1">
                    <FileText className="h-2.5 w-2.5" /> Auto-gerado a partir do P&D
                  </Badge>
                )}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {!editing && (
              <Select value={form.status} onValueChange={updateStatus}>
                <SelectTrigger className="w-44" data-testid="order-status-select">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {STATUS_OPTIONS.map(s => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}
                </SelectContent>
              </Select>
            )}
            {form.status === "confirmado" && !form.op_id && (
              <Button onClick={generateOP} variant="default" className="gap-1.5 bg-emerald-600 hover:bg-emerald-700" data-testid="generate-op-btn">
                <Factory className="h-4 w-4" /> Gerar OP
              </Button>
            )}
            {form.op_id && (
              <Button variant="outline" onClick={() => navigate(`/ops/${form.op_id}`)} className="gap-1.5" data-testid="view-op-btn">
                <Factory className="h-4 w-4" /> Ver OP
              </Button>
            )}
            <Button onClick={downloadPDF} className="gap-1.5" data-testid="download-pdf-btn">
              <Download className="h-4 w-4" /> Gerar PDF
            </Button>
            {!editing ? (
              <Button variant="outline" onClick={startEdit} className="gap-1.5" data-testid="edit-order-btn">
                <Pencil className="h-4 w-4" /> Editar
              </Button>
            ) : (
              <>
                <Button onClick={saveOrder} disabled={saving} className="gap-1.5" data-testid="save-order-btn">
                  {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                  Salvar
                </Button>
                <Button variant="ghost" onClick={cancelEdit} data-testid="cancel-edit-btn">
                  <X className="h-4 w-4" />
                </Button>
              </>
            )}
          </div>
        </div>

        {/* CGI Panel (RN-PI-01) */}
        <div className={`rounded-xl border px-5 py-4 flex items-center justify-between gap-4 ${form.cgi_status === "assinado" ? "bg-green-50 border-green-300 dark:bg-green-950/30 dark:border-green-800" : "bg-amber-50 border-amber-300 dark:bg-amber-950/30 dark:border-amber-800"}`}>
          <div className="flex items-center gap-3">
            {form.cgi_status === "assinado"
              ? <ShieldCheck className="h-5 w-5 text-green-600 shrink-0" />
              : <AlertTriangle className="h-5 w-5 text-amber-600 shrink-0" />
            }
            <div>
              <p className="text-sm font-semibold">
                {form.cgi_status === "assinado" ? "CGI Assinado" : "CGI Pendente (RN-PI-01)"}
              </p>
              <p className="text-xs text-muted-foreground">
                {form.cgi_status === "assinado"
                  ? `Assinado por ${form.cgi_assinado_por || "—"} em ${form.cgi_assinado_em ? new Date(form.cgi_assinado_em).toLocaleDateString("pt-BR") : "—"}`
                  : "O Contrato Geral de Industrialização deve ser assinado antes de confirmar o pedido."
                }
              </p>
            </div>
          </div>
          {form.cgi_status !== "assinado" && (
            <Button size="sm" variant="outline" onClick={signCGI} className="shrink-0 gap-1.5 border-amber-400 text-amber-700 hover:bg-amber-100" data-testid="sign-cgi-btn">
              <ShieldCheck className="h-3.5 w-3.5" /> Assinar CGI
            </Button>
          )}
        </div>

        {/* Imutabilidade banner */}
        {STATUSES_IMUTAVEL.has(form.status) && (
          <div className="rounded-xl border border-blue-300 bg-blue-50 dark:bg-blue-950/30 dark:border-blue-800 px-5 py-3 flex items-center gap-3">
            <Lock className="h-4 w-4 text-blue-600 shrink-0" />
            <p className="text-sm text-blue-700 dark:text-blue-300">
              <strong>Pedido imutável (RN-PI-05)</strong> — Status <em>{form.status}</em>. Campos comerciais bloqueados. Apenas checklist de insumos e observações podem ser atualizados. Para alterações, crie um aditivo.
            </p>
          </div>
        )}

        {/* Aprovação do Cliente */}
        <div className={`rounded-xl border px-5 py-4 flex items-center justify-between gap-4 ${form.aprovacao_cliente === "aprovado" ? "bg-green-50 border-green-300 dark:bg-green-950/30 dark:border-green-800" : "bg-slate-50 border-slate-300 dark:bg-slate-900/30 dark:border-slate-700"}`}>
          <div className="flex items-center gap-3">
            {form.aprovacao_cliente === "aprovado"
              ? <CheckCircle2 className="h-5 w-5 text-green-600 shrink-0" />
              : <AlertTriangle className="h-5 w-5 text-slate-400 shrink-0" />
            }
            <div>
              <p className="text-sm font-semibold">
                {form.aprovacao_cliente === "aprovado" ? "Cliente Aprovou o Pedido" : "Aprovação do Cliente Pendente (RN-PI-04)"}
              </p>
              <p className="text-xs text-muted-foreground">
                {form.aprovacao_cliente === "aprovado"
                  ? `Registrado por ${form.aprovacao_cliente_por || "—"} em ${form.aprovacao_cliente_em ? new Date(form.aprovacao_cliente_em).toLocaleDateString("pt-BR") : "—"}`
                  : "Comprovante (print/e-mail) deve ser anexado e aprovação registrada antes de gerar OP."
                }
              </p>
            </div>
          </div>
          {form.aprovacao_cliente !== "aprovado" && (
            <Button size="sm" variant="outline" onClick={approveCliente}
              className="shrink-0 gap-1.5 border-slate-400 text-slate-700 hover:bg-slate-100">
              <CheckCircle2 className="h-3.5 w-3.5" /> Registrar Aprovação
            </Button>
          )}
        </div>

        {/* 1) Informações Iniciais */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <span className="font-mono text-primary">1)</span> Informações Iniciais
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <Field label="Cliente" value={form.cliente?.nome} onChange={(v) => onCli("nome", v)} editing={editing} testid="field-cliente-nome" />
              <Field label="# Pedido" value={form.numero_pedido} onChange={(v) => setForm(p => ({ ...p, numero_pedido: v }))} editing={editing} testid="field-numero-pedido" />
              <Field
                label="Data"
                type="date"
                value={editing ? dateInputValue(form.data_pedido) : (form.data_pedido ? new Date(form.data_pedido).toLocaleDateString("pt-BR") : "")}
                onChange={(v) => setForm(p => ({ ...p, data_pedido: v ? new Date(v).toISOString() : null }))}
                editing={editing}
                testid="field-data-pedido"
              />
            </div>
            {/* Tipo de Serviço + Nível de Formalização */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <Label className="text-xs text-muted-foreground">Tipo de Serviço</Label>
                {editing && !STATUSES_IMUTAVEL.has(order.status) ? (
                  <Select value={form.tipo_servico || "producao"}
                    onValueChange={v => setForm(p => ({ ...p, tipo_servico: v }))}>
                    <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {TIPOS_SERVICO.map(t => (
                        <SelectItem key={t.value} value={t.value}>
                          <div><div className="font-medium">{t.label}</div><div className="text-xs text-muted-foreground">{t.desc}</div></div>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <p className="text-sm font-medium mt-1">
                    {TIPOS_SERVICO.find(t => t.value === form.tipo_servico)?.label || form.tipo_servico || "Produção"}
                  </p>
                )}
              </div>
              <div>
                <Label className="text-xs text-muted-foreground">Nível de Formalização</Label>
                {editing && !STATUSES_IMUTAVEL.has(order.status) ? (
                  <Select value={String(form.nivel_formalizacao || 1)}
                    onValueChange={v => setForm(p => ({ ...p, nivel_formalizacao: Number(v) }))}>
                    <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {NIVEIS_FORMALIZACAO.map(n => (
                        <SelectItem key={n.value} value={String(n.value)}>
                          <div><div className="font-medium">{n.label}</div><div className="text-xs text-muted-foreground">{n.desc}</div></div>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <p className="text-sm font-medium mt-1">
                    {NIVEIS_FORMALIZACAO.find(n => n.value === (form.nivel_formalizacao || 1))?.label || `Nível ${form.nivel_formalizacao || 1}`}
                  </p>
                )}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* 2) Dados do Cliente */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <span className="font-mono text-primary">2)</span> Dados do Cliente
            </CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Field label="Razão Social" value={form.cliente?.razao_social} onChange={(v) => onCli("razao_social", v)} editing={editing} testid="field-razao-social" />
            <Field label="CNPJ" value={form.cliente?.cnpj} onChange={(v) => onCli("cnpj", v)} editing={editing} testid="field-cnpj" />
            <Field label="Cidade / UF" value={form.cliente?.cidade_uf} onChange={(v) => onCli("cidade_uf", v)} editing={editing} testid="field-cidade-uf" />
            <Field label="Responsável" value={form.cliente?.responsavel} onChange={(v) => onCli("responsavel", v)} editing={editing} testid="field-responsavel" />
            <Field label="Telefone" value={form.cliente?.telefone} onChange={(v) => onCli("telefone", v)} editing={editing} testid="field-telefone" />
            <Field label="E-mail" value={form.cliente?.email} onChange={(v) => onCli("email", v)} editing={editing} testid="field-email" />
          </CardContent>
        </Card>

        {/* 3) Frete */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <span className="font-mono text-primary">3)</span> Frete
            </CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <Label className="text-xs text-muted-foreground">Tipo de Frete</Label>
              {editing ? (
                <Select value={form.frete?.tipo || "FOB"} onValueChange={(v) => onFre("tipo", v)}>
                  <SelectTrigger className="mt-1" data-testid="field-frete-tipo"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="FOB">FOB</SelectItem>
                    <SelectItem value="CIF">CIF</SelectItem>
                  </SelectContent>
                </Select>
              ) : (
                <p className="text-sm font-medium mt-1">{form.frete?.tipo || "—"}</p>
              )}
            </div>
            <Field label="Cidade / UF" value={form.frete?.cidade_uf} onChange={(v) => onFre("cidade_uf", v)} editing={editing} testid="field-frete-cidade" />
            <div className="md:col-span-2">
              <Field label="Endereço" value={form.frete?.endereco} onChange={(v) => onFre("endereco", v)} editing={editing} testid="field-frete-endereco" />
            </div>
            <div className="md:col-span-2">
              <Field label="Prazo p/ Coleta" value={form.frete?.prazo_coleta} onChange={(v) => onFre("prazo_coleta", v)} editing={editing} testid="field-frete-prazo" />
            </div>
          </CardContent>
        </Card>

        {/* 4) Pedido (Items) */}
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base flex items-center gap-2">
                <span className="font-mono text-primary">4)</span> Pedido
              </CardTitle>
              {editing && (
                <Button size="sm" variant="outline" onClick={addItem} className="gap-1.5" data-testid="add-item-btn">
                  <Plus className="h-3.5 w-3.5" /> Adicionar Item
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-[#1F2C5C] text-white text-xs">
                    <th className="text-left p-2 font-medium">#</th>
                    <th className="text-left p-2 font-medium">Cód. Kuryos</th>
                    <th className="text-left p-2 font-medium">Cód. Cliente</th>
                    <th className="text-left p-2 font-medium">Item</th>
                    <th className="text-left p-2 font-medium">Prazo</th>
                    <th className="text-right p-2 font-medium">Valor Unit.</th>
                    <th className="text-right p-2 font-medium">Qtd.</th>
                    <th className="text-right p-2 font-medium">Total</th>
                    {editing && <th className="w-10"></th>}
                  </tr>
                </thead>
                <tbody>
                  {(form.items || []).map((it, idx) => (
                    <tr key={idx} className="border-t hover:bg-muted/30">
                      <td className="p-2 font-mono text-xs">{idx + 1}</td>
                      <td className="p-1">
                        {editing ? (
                          <Input value={it.codigo_kuryos || ""} onChange={(e) => updateItem(idx, "codigo_kuryos", e.target.value)} className="h-8 text-xs" data-testid={`item-${idx}-codigo-kuryos`} />
                        ) : (it.codigo_kuryos || "—")}
                      </td>
                      <td className="p-1">
                        {editing ? (
                          <Input value={it.codigo_cliente || ""} onChange={(e) => updateItem(idx, "codigo_cliente", e.target.value)} className="h-8 text-xs" data-testid={`item-${idx}-codigo-cliente`} />
                        ) : (it.codigo_cliente || "—")}
                      </td>
                      <td className="p-1">
                        {editing ? (
                          <Input value={it.item || ""} onChange={(e) => updateItem(idx, "item", e.target.value)} className="h-8 text-xs" data-testid={`item-${idx}-nome`} />
                        ) : (it.item || "—")}
                      </td>
                      <td className="p-1">
                        {editing ? (
                          <Input value={it.prazo_entrega || ""} onChange={(e) => updateItem(idx, "prazo_entrega", e.target.value)} className="h-8 text-xs" data-testid={`item-${idx}-prazo`} />
                        ) : (it.prazo_entrega || "—")}
                      </td>
                      <td className="p-1 text-right">
                        {editing ? (
                          <Input type="number" step="0.01" value={it.valor_unitario || 0} onChange={(e) => updateItem(idx, "valor_unitario", e.target.value)} className="h-8 text-xs text-right font-mono" data-testid={`item-${idx}-valor-unit`} />
                        ) : formatCurrencyBR(it.valor_unitario)}
                      </td>
                      <td className="p-1 text-right">
                        {editing ? (
                          <Input type="number" value={it.qtd || 0} onChange={(e) => updateItem(idx, "qtd", e.target.value)} className="h-8 text-xs text-right font-mono" data-testid={`item-${idx}-qtd`} />
                        ) : (Number(it.qtd) || 0).toLocaleString("pt-BR")}
                      </td>
                      <td className="p-2 text-right font-mono text-xs font-semibold">
                        {formatCurrencyBR(it.valor_total)}
                      </td>
                      {editing && (
                        <td className="p-2 text-center">
                          <button onClick={() => removeItem(idx)} className="text-muted-foreground hover:text-red-500" data-testid={`remove-item-${idx}`}>
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </td>
                      )}
                    </tr>
                  ))}
                  {(form.items || []).length === 0 && (
                    <tr><td colSpan={editing ? 9 : 8} className="p-6 text-center text-xs text-muted-foreground">
                      Nenhum item. {editing && "Clique em 'Adicionar Item'."}
                    </td></tr>
                  )}
                </tbody>
                <tfoot>
                  <tr className="border-t-2 bg-muted/30 font-bold">
                    <td colSpan={editing ? 7 : 6} className="p-2 text-right">Total do Pedido</td>
                    <td className="p-2 text-right text-green-600 font-mono">{formatCurrencyBR(totalCalc)}</td>
                    {editing && <td></td>}
                  </tr>
                </tfoot>
              </table>
            </div>
          </CardContent>
        </Card>

        {/* 5) Condições */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <span className="font-mono text-primary">5)</span> Condições de Prazo e Pagamento
            </CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Field label="Prazo de Entrega" value={form.condicoes?.prazo} onChange={(v) => onCnd("prazo", v)} editing={editing} testid="field-cond-prazo" />
            <div>
              <Label className="text-xs text-muted-foreground">Condição de Pagamento (RN-PI-08)</Label>
              {editing && !STATUSES_IMUTAVEL.has(order.status) ? (
                <div>
                  <Input
                    value={form.condicoes?.condicao_pagamento || ""}
                    onChange={(e) => onCnd("condicao_pagamento", maskCondicaoPgto(e.target.value))}
                    placeholder="000/000/000"
                    className="mt-1 font-mono"
                    maxLength={11}
                    data-testid="field-cond-pgto"
                  />
                  <p className="text-[10px] text-muted-foreground mt-0.5">Formato obrigatório: NNN/NNN/NNN (ex: 030/060/090)</p>
                </div>
              ) : (
                <p className="text-sm font-medium mt-1 min-h-[28px] flex items-center font-mono" data-testid="field-cond-pgto">
                  {form.condicoes?.condicao_pagamento || form.condicoes?.forma_pgto || "—"}
                </p>
              )}
            </div>
            <Field label="Validade da Proposta" value={form.condicoes?.validade} onChange={(v) => onCnd("validade", v)} editing={editing} testid="field-cond-validade" />
          </CardContent>
        </Card>

        {/* 6) Checklist de Insumos */}
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-base flex items-center gap-2">
                  <span className="font-mono text-primary">6)</span> Checklist de Insumos (RN-PI-06)
                </CardTitle>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {(form.checklist_insumos || []).filter(c => c.ativo && c.status === "recebido").length} / {(form.checklist_insumos || []).filter(c => c.ativo).length} insumos ativos recebidos
                </p>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-[#1F2C5C] text-white">
                    <th className="text-left p-2 font-medium">Categoria</th>
                    <th className="text-center p-2 font-medium w-14">Aplica?</th>
                    <th className="text-center p-2 font-medium w-24">Origem</th>
                    <th className="text-center p-2 font-medium w-28">Status</th>
                    <th className="text-left p-2 font-medium w-32">Responsável</th>
                    <th className="text-left p-2 font-medium w-28">Data Prevista</th>
                  </tr>
                </thead>
                <tbody>
                  {(form.checklist_insumos || buildDefaultChecklist()).map((ci, idx) => {
                    const statusCfg = INSUMO_STATUS_CFG[ci.status] || INSUMO_STATUS_CFG.pendente;
                    const updateCI = (key, val) => setForm(p => {
                      const cl = [...(p.checklist_insumos || buildDefaultChecklist())];
                      cl[idx] = { ...cl[idx], [key]: val };
                      return { ...p, checklist_insumos: cl };
                    });
                    return (
                      <tr key={idx} className={`border-t ${ci.ativo ? "hover:bg-muted/30" : "opacity-50 hover:opacity-70"}`}>
                        <td className="p-2 font-medium">{ci.categoria}</td>
                        <td className="p-2 text-center">
                          <Checkbox
                            checked={!!ci.ativo}
                            onCheckedChange={editing ? (v) => updateCI("ativo", v) : undefined}
                            disabled={!editing}
                            data-testid={`ci-${idx}-ativo`}
                          />
                        </td>
                        <td className="p-1 text-center">
                          {editing && ci.ativo ? (
                            <Select value={ci.origem || "kuryos"} onValueChange={v => updateCI("origem", v)}>
                              <SelectTrigger className="h-6 text-[10px] px-1.5"><SelectValue /></SelectTrigger>
                              <SelectContent>
                                <SelectItem value="kuryos">Kuryos</SelectItem>
                                <SelectItem value="cliente">Cliente</SelectItem>
                              </SelectContent>
                            </Select>
                          ) : (
                            <span className={`text-[10px] rounded px-1.5 py-0.5 font-medium ${ci.origem === "cliente" ? "bg-purple-100 text-purple-700" : "bg-slate-100 text-slate-600"}`}>
                              {ci.origem === "cliente" ? "Cliente" : "Kuryos"}
                            </span>
                          )}
                        </td>
                        <td className="p-1 text-center">
                          {editing && ci.ativo ? (
                            <Select value={ci.status || "pendente"} onValueChange={v => updateCI("status", v)}>
                              <SelectTrigger className="h-6 text-[10px] px-1.5"><SelectValue /></SelectTrigger>
                              <SelectContent>
                                {Object.entries(INSUMO_STATUS_CFG).map(([k, cfg]) => (
                                  <SelectItem key={k} value={k}>{cfg.label}</SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          ) : (
                            <span className={`text-[10px] rounded px-1.5 py-0.5 font-medium ${statusCfg.cls}`}>{statusCfg.label}</span>
                          )}
                        </td>
                        <td className="p-1">
                          {editing && ci.ativo ? (
                            <Input value={ci.responsavel || ""} onChange={e => updateCI("responsavel", e.target.value)} className="h-6 text-[10px]" placeholder="Nome" data-testid={`ci-${idx}-resp`} />
                          ) : (
                            <span className="text-muted-foreground">{ci.responsavel || "—"}</span>
                          )}
                        </td>
                        <td className="p-1">
                          {editing && ci.ativo ? (
                            <Input type="date" value={ci.data_prevista || ""} onChange={e => updateCI("data_prevista", e.target.value)} className="h-6 text-[10px]" data-testid={`ci-${idx}-data`} />
                          ) : (
                            <span className="text-muted-foreground">
                              {ci.data_prevista ? new Date(ci.data_prevista).toLocaleDateString("pt-BR") : "—"}
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>

        {/* Observações */}
        {(editing || form.observacoes) && (
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Observações</CardTitle>
            </CardHeader>
            <CardContent>
              {editing ? (
                <Textarea
                  value={form.observacoes || ""}
                  onChange={(e) => setForm(p => ({ ...p, observacoes: e.target.value }))}
                  rows={3}
                  data-testid="field-observacoes"
                />
              ) : (
                <p className="text-sm whitespace-pre-wrap">{form.observacoes}</p>
              )}
            </CardContent>
          </Card>
        )}

        {/* Footer info */}
        <div className="text-[11px] text-muted-foreground pt-2">
          Criado por <strong>{order.created_by_name}</strong> em {order.created_at ? new Date(order.created_at).toLocaleString("pt-BR") : "—"}
          {order.pd_request_id && (
            <> • <button onClick={() => navigate(`/pd/${order.pd_request_id}`)} className="text-primary hover:underline" data-testid="link-to-pd">Ver projeto P&D</button></>
          )}
        </div>
      </div>
    </div>
  );
}

function Field({ label, value, onChange, editing, type = "text", testid }) {
  return (
    <div>
      <Label className="text-xs text-muted-foreground">{label}</Label>
      {editing ? (
        <Input
          type={type}
          value={value || ""}
          onChange={(e) => onChange(e.target.value)}
          className="mt-1"
          data-testid={testid}
        />
      ) : (
        <p className="text-sm font-medium mt-1 min-h-[28px] flex items-center" data-testid={testid}>
          {value || "—"}
        </p>
      )}
    </div>
  );
}

function deepClone(obj) {
  return JSON.parse(JSON.stringify(obj));
}
