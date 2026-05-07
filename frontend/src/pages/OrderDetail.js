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
import { ArrowLeft, Save, Download, Loader2, Plus, Trash2, FileText, Pencil, Check, X } from "lucide-react";

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
    setEditing(true);
  };

  const cancelEdit = () => {
    setForm(deepClone(order));
    setEditing(false);
  };

  const saveOrder = async () => {
    setSaving(true);
    try {
      const payload = {
        numero_pedido: form.numero_pedido,
        data_pedido: form.data_pedido,
        status: form.status,
        cliente: form.cliente,
        frete: form.frete,
        items: form.items,
        condicoes: form.condicoes,
        insumos: form.insumos,
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

  const updateInsumo = (idx, key, value) => {
    setForm(p => {
      const insumos = [...(p.insumos || [])];
      insumos[idx] = { ...insumos[idx], [key]: value };
      return { ...p, insumos };
    });
  };

  const addInsumo = () => {
    setForm(p => ({
      ...p,
      insumos: [...(p.insumos || []), { item: "", especificacoes: "", quantidade: "" }],
    }));
  };

  const removeInsumo = (idx) => {
    setForm(p => ({ ...p, insumos: (p.insumos || []).filter((_, i) => i !== idx) }));
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

        {/* 1) Informações Iniciais */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <span className="font-mono text-primary">1)</span> Informações Iniciais
            </CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-1 md:grid-cols-3 gap-3">
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
            <Field label="Prazo" value={form.condicoes?.prazo} onChange={(v) => onCnd("prazo", v)} editing={editing} testid="field-cond-prazo" />
            <Field label="Forma de Pgto" value={form.condicoes?.forma_pgto} onChange={(v) => onCnd("forma_pgto", v)} editing={editing} testid="field-cond-pgto" />
          </CardContent>
        </Card>

        {/* 6) Insumos */}
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base flex items-center gap-2">
                <span className="font-mono text-primary">6)</span> Insumos a Serem Enviados
              </CardTitle>
              {editing && (
                <Button size="sm" variant="outline" onClick={addInsumo} className="gap-1.5" data-testid="add-insumo-btn">
                  <Plus className="h-3.5 w-3.5" /> Adicionar Insumo
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-[#1F2C5C] text-white text-xs">
                    <th className="text-left p-2 font-medium w-10">#</th>
                    <th className="text-left p-2 font-medium">Item</th>
                    <th className="text-left p-2 font-medium">Especificações</th>
                    <th className="text-left p-2 font-medium w-32">Quantidade</th>
                    {editing && <th className="w-10"></th>}
                  </tr>
                </thead>
                <tbody>
                  {(form.insumos || []).map((ins, idx) => (
                    <tr key={idx} className="border-t hover:bg-muted/30">
                      <td className="p-2 font-mono text-xs">{idx + 1}</td>
                      <td className="p-1">
                        {editing ? <Input value={ins.item || ""} onChange={(e) => updateInsumo(idx, "item", e.target.value)} className="h-8 text-xs" data-testid={`insumo-${idx}-item`} /> : (ins.item || "—")}
                      </td>
                      <td className="p-1">
                        {editing ? <Input value={ins.especificacoes || ""} onChange={(e) => updateInsumo(idx, "especificacoes", e.target.value)} className="h-8 text-xs" data-testid={`insumo-${idx}-spec`} /> : (ins.especificacoes || "—")}
                      </td>
                      <td className="p-1">
                        {editing ? <Input value={ins.quantidade || ""} onChange={(e) => updateInsumo(idx, "quantidade", e.target.value)} className="h-8 text-xs" data-testid={`insumo-${idx}-qtd`} /> : (ins.quantidade || "—")}
                      </td>
                      {editing && (
                        <td className="p-2 text-center">
                          <button onClick={() => removeInsumo(idx)} className="text-muted-foreground hover:text-red-500" data-testid={`remove-insumo-${idx}`}>
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </td>
                      )}
                    </tr>
                  ))}
                  {(form.insumos || []).length === 0 && (
                    <tr><td colSpan={editing ? 5 : 4} className="p-4 text-center text-xs text-muted-foreground">
                      Nenhum insumo. {editing && "Clique em 'Adicionar Insumo'."}
                    </td></tr>
                  )}
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
