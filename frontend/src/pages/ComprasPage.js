import { useState, useEffect, useCallback } from "react";
import { useAuth } from "@/contexts/AuthContext";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import {
  ShoppingCart, Plus, Loader2, ChevronDown, ChevronRight, Package,
  ExternalLink, Filter, Search, FileText, CheckCircle2, Truck,
  XCircle, Clock, Pencil, X, RefreshCw
} from "lucide-react";
import { useNavigate } from "react-router-dom";

const STATUS_CONFIG = {
  rascunho:  { label: "Rascunho",   color: "bg-slate-100 text-slate-600 border-slate-200" },
  enviada:   { label: "Enviada",    color: "bg-blue-100 text-blue-700 border-blue-200" },
  confirmada:{ label: "Confirmada", color: "bg-amber-100 text-amber-700 border-amber-200" },
  entregue:  { label: "Entregue",   color: "bg-green-100 text-green-700 border-green-200" },
  cancelada: { label: "Cancelada",  color: "bg-red-100 text-red-600 border-red-200" },
};

const STATUS_ICONS = {
  rascunho:   Clock,
  enviada:    FileText,
  confirmada: CheckCircle2,
  entregue:   Truck,
  cancelada:  XCircle,
};

function formatBRL(value) {
  const n = parseFloat(value) || 0;
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function formatDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("pt-BR");
}

function OCStatusBadge({ status }) {
  const cfg = STATUS_CONFIG[status] || { label: status, color: "bg-muted text-muted-foreground" };
  const Icon = STATUS_ICONS[status] || Clock;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border ${cfg.color}`}>
      <Icon className="h-3 w-3" />
      {cfg.label}
    </span>
  );
}

function NewOCDialog({ open, onClose, onCreated }) {
  const [boms, setBoms] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [loadingBoms, setLoadingBoms] = useState(false);
  const [selectedKickoff, setSelectedKickoff] = useState("");
  const [selectedBomItem, setSelectedBomItem] = useState("");
  const [form, setForm] = useState({
    fornecedor_id: "",
    quantidade: "",
    unidade: "kg",
    preco_unitario_rs: "",
    data_necessidade: "",
    observacoes: "",
  });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLoadingBoms(true);
    Promise.all([
      api.get("/compras/boms"),
      api.get("/pd/suppliers"),
    ]).then(([bomsRes, suppRes]) => {
      setBoms(bomsRes.data?.boms || []);
      setSuppliers(suppRes.data?.suppliers || suppRes.data || []);
    }).catch(() => {
      toast.error("Erro ao carregar dados");
    }).finally(() => setLoadingBoms(false));
  }, [open]);

  const selectedKickoffData = boms.find(b => b.kickoff_id === selectedKickoff);
  const bomLines = selectedKickoffData?.bom || [];
  const selectedLine = bomLines.find(l => (l.codigo_interno || l.id) === selectedBomItem);

  const handleSave = async () => {
    if (!selectedKickoff) { toast.error("Selecione um Kickoff"); return; }
    if (!selectedBomItem) { toast.error("Selecione um item do BOM"); return; }
    if (!form.fornecedor_id) { toast.error("Selecione um fornecedor"); return; }
    if (!form.quantidade || parseFloat(form.quantidade) <= 0) { toast.error("Informe a quantidade"); return; }
    if (!form.preco_unitario_rs || parseFloat(form.preco_unitario_rs) < 0) { toast.error("Informe o preço unitário"); return; }

    setSaving(true);
    try {
      await api.post("/compras/ordens", {
        kickoff_id: selectedKickoff,
        bom_item_id: selectedBomItem,
        fornecedor_id: form.fornecedor_id,
        quantidade: parseFloat(form.quantidade),
        unidade: form.unidade,
        preco_unitario_rs: parseFloat(form.preco_unitario_rs),
        data_necessidade: form.data_necessidade || undefined,
        observacoes: form.observacoes,
      });
      toast.success("Ordem de Compra criada");
      onCreated();
      onClose();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Erro ao criar OC");
    } finally { setSaving(false); }
  };

  const reset = () => {
    setSelectedKickoff(""); setSelectedBomItem("");
    setForm({ fornecedor_id: "", quantidade: "", unidade: "kg", preco_unitario_rs: "", data_necessidade: "", observacoes: "" });
  };

  return (
    <Dialog open={open} onOpenChange={o => { if (!o) { reset(); onClose(); } }}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ShoppingCart className="h-5 w-5 text-blue-600" />
            Nova Ordem de Compra
          </DialogTitle>
          <DialogDescription>
            Selecione um Kickoff aprovado e o item do BOM para emitir a OC.
          </DialogDescription>
        </DialogHeader>

        {loadingBoms ? (
          <div className="flex justify-center py-8"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
        ) : (
          <div className="space-y-4">
            <div className="space-y-1">
              <Label className="text-xs font-medium">Kickoff (aprovado) <span className="text-red-500">*</span></Label>
              <Select value={selectedKickoff} onValueChange={v => { setSelectedKickoff(v); setSelectedBomItem(""); }}>
                <SelectTrigger>
                  <SelectValue placeholder="Selecione o Kickoff..." />
                </SelectTrigger>
                <SelectContent>
                  {boms.length === 0 && <SelectItem value="__none" disabled>Nenhum Kickoff aprovado com BOM</SelectItem>}
                  {boms.map(b => (
                    <SelectItem key={b.kickoff_id} value={b.kickoff_id}>
                      {b.numero_kickoff} — {b.cliente || b.projeto_vinculado || b.kickoff_id}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {selectedKickoffData && (
              <div className="space-y-1">
                <Label className="text-xs font-medium">Item do BOM <span className="text-red-500">*</span></Label>
                <Select value={selectedBomItem} onValueChange={setSelectedBomItem}>
                  <SelectTrigger>
                    <SelectValue placeholder="Selecione o item..." />
                  </SelectTrigger>
                  <SelectContent>
                    {bomLines.length === 0 && <SelectItem value="__none" disabled>BOM vazio</SelectItem>}
                    {bomLines.map(l => (
                      <SelectItem key={l.codigo_interno || l.id || l.descricao} value={l.codigo_interno || l.id || l.descricao}>
                        {l.descricao || l.codigo_interno} {l.tipo ? `(${l.tipo})` : ""}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {selectedLine && (
                  <p className="text-xs text-muted-foreground">
                    Qtd BOM: {selectedLine.quantidade} {selectedLine.unidade} · Tipo: {selectedLine.tipo || "—"}
                  </p>
                )}
              </div>
            )}

            <div className="space-y-1">
              <Label className="text-xs font-medium">Fornecedor <span className="text-red-500">*</span></Label>
              <Select value={form.fornecedor_id} onValueChange={v => setForm(f => ({ ...f, fornecedor_id: v }))}>
                <SelectTrigger>
                  <SelectValue placeholder="Selecione o fornecedor..." />
                </SelectTrigger>
                <SelectContent>
                  {suppliers.length === 0 && <SelectItem value="__none" disabled>Nenhum fornecedor homologado</SelectItem>}
                  {suppliers.map(s => (
                    <SelectItem key={s.id} value={s.id}>
                      {s.razao_social || s.nome} {s.status !== "homologado" ? `(${s.status})` : ""}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="grid grid-cols-3 gap-3">
              <div className="col-span-2 space-y-1">
                <Label className="text-xs font-medium">Quantidade <span className="text-red-500">*</span></Label>
                <Input type="number" step="0.001" min="0" value={form.quantidade} onChange={e => setForm(f => ({ ...f, quantidade: e.target.value }))} placeholder="0.000" />
              </div>
              <div className="space-y-1">
                <Label className="text-xs font-medium">Unidade</Label>
                <Select value={form.unidade} onValueChange={v => setForm(f => ({ ...f, unidade: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {["kg", "g", "L", "mL", "un", "cx", "pç"].map(u => <SelectItem key={u} value={u}>{u}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs font-medium">Preço Unit. (R$) <span className="text-red-500">*</span></Label>
                <Input type="number" step="0.01" min="0" value={form.preco_unitario_rs} onChange={e => setForm(f => ({ ...f, preco_unitario_rs: e.target.value }))} placeholder="0.00" />
                {form.quantidade && form.preco_unitario_rs && (
                  <p className="text-xs text-muted-foreground">Total: {formatBRL(parseFloat(form.quantidade) * parseFloat(form.preco_unitario_rs))}</p>
                )}
              </div>
              <div className="space-y-1">
                <Label className="text-xs font-medium">Data Necessidade</Label>
                <Input type="date" value={form.data_necessidade} onChange={e => setForm(f => ({ ...f, data_necessidade: e.target.value }))} />
                <p className="text-xs text-muted-foreground">Auto-calculada se omitida</p>
              </div>
            </div>

            <div className="space-y-1">
              <Label className="text-xs font-medium">Observações</Label>
              <Textarea value={form.observacoes} onChange={e => setForm(f => ({ ...f, observacoes: e.target.value }))} rows={2} placeholder="Observações adicionais..." />
            </div>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => { reset(); onClose(); }}>Cancelar</Button>
          <Button onClick={handleSave} disabled={saving || loadingBoms} className="gap-1.5">
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
            Emitir OC
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function UpdateStatusDialog({ oc, open, onClose, onUpdated }) {
  const [status, setStatus] = useState(oc?.status || "");
  const [saving, setSaving] = useState(false);

  useEffect(() => { if (oc) setStatus(oc.status); }, [oc]);

  const ALLOWED_NEXT = {
    rascunho: ["enviada", "cancelada"],
    enviada: ["confirmada", "cancelada"],
    confirmada: ["entregue", "cancelada"],
    entregue: [],
    cancelada: [],
  };

  const options = ALLOWED_NEXT[oc?.status || ""] || [];

  const handleSave = async () => {
    if (!status || status === oc?.status) return;
    setSaving(true);
    try {
      await api.put(`/compras/ordens/${oc.id}`, { status });
      toast.success("Status atualizado");
      onUpdated();
      onClose();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Erro ao atualizar");
    } finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={o => { if (!o) onClose(); }}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Atualizar Status — {oc?.numero_oc}</DialogTitle>
        </DialogHeader>
        {options.length === 0 ? (
          <p className="text-sm text-muted-foreground py-2">Nenhuma transição disponível a partir de "{oc?.status}".</p>
        ) : (
          <div className="space-y-2 py-2">
            {options.map(s => (
              <button
                key={s}
                onClick={() => setStatus(s)}
                className={`w-full text-left px-3 py-2 rounded-lg border text-sm transition-colors ${status === s ? "border-primary bg-primary/5" : "border-border hover:bg-muted/40"}`}
              >
                <OCStatusBadge status={s} />
              </button>
            ))}
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button onClick={handleSave} disabled={saving || !status || status === oc?.status || options.length === 0}>
            {saving ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null}
            Salvar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function OCCard({ oc, onRefresh, canEdit }) {
  const [expanded, setExpanded] = useState(false);
  const [statusDialog, setStatusDialog] = useState(false);

  return (
    <div className="border rounded-xl bg-background shadow-sm overflow-hidden">
      <div
        className="flex items-center gap-3 p-4 cursor-pointer hover:bg-muted/30 transition-colors"
        onClick={() => setExpanded(e => !e)}
      >
        <div className="flex items-center justify-center h-9 w-9 rounded-lg bg-blue-50 text-blue-600 flex-shrink-0">
          <Package className="h-4.5 w-4.5" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-sm">{oc.numero_oc}</span>
            <OCStatusBadge status={oc.status} />
          </div>
          <p className="text-xs text-muted-foreground truncate mt-0.5">
            {oc.bom_item_descricao || oc.bom_item_id} · {oc.fornecedor_nome} · {formatBRL(oc.valor_total_rs)}
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground flex-shrink-0">
          <span>{oc.numero_kickoff}</span>
          {canEdit && oc.status !== "entregue" && oc.status !== "cancelada" && (
            <button
              onClick={e => { e.stopPropagation(); setStatusDialog(true); }}
              className="p-1 rounded hover:bg-muted transition-colors"
              title="Atualizar status"
            >
              <Pencil className="h-3.5 w-3.5" />
            </button>
          )}
          <ChevronDown className={`h-4 w-4 transition-transform ${expanded ? "rotate-180" : ""}`} />
        </div>
      </div>

      {expanded && (
        <div className="border-t px-4 py-3 grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm bg-muted/10">
          <div><p className="text-xs text-muted-foreground">Kickoff</p><p className="font-medium">{oc.numero_kickoff}</p></div>
          <div><p className="text-xs text-muted-foreground">Item BOM</p><p className="font-medium">{oc.bom_item_descricao || oc.bom_item_id}</p></div>
          <div><p className="text-xs text-muted-foreground">Tipo</p><p className="font-medium">{oc.bom_item_tipo || "—"}</p></div>
          <div><p className="text-xs text-muted-foreground">Fornecedor</p><p className="font-medium">{oc.fornecedor_nome}</p></div>
          <div><p className="text-xs text-muted-foreground">Quantidade</p><p className="font-medium">{oc.quantidade} {oc.unidade}</p></div>
          <div><p className="text-xs text-muted-foreground">Preço Unit.</p><p className="font-medium">{formatBRL(oc.preco_unitario_rs)}</p></div>
          <div><p className="text-xs text-muted-foreground">Valor Total</p><p className="font-semibold text-green-700">{formatBRL(oc.valor_total_rs)}</p></div>
          <div><p className="text-xs text-muted-foreground">Data Necessidade</p><p className="font-medium">{formatDate(oc.data_necessidade)}</p></div>
          <div><p className="text-xs text-muted-foreground">Criado em</p><p className="font-medium">{new Date(oc.created_at).toLocaleString("pt-BR")}</p></div>
          {oc.observacoes && <div className="col-span-full"><p className="text-xs text-muted-foreground">Observações</p><p className="text-sm">{oc.observacoes}</p></div>}
        </div>
      )}

      {statusDialog && (
        <UpdateStatusDialog
          oc={oc}
          open={statusDialog}
          onClose={() => setStatusDialog(false)}
          onUpdated={onRefresh}
        />
      )}
    </div>
  );
}

export default function ComprasPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [ocs, setOcs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [newOCOpen, setNewOCOpen] = useState(false);
  const [filterStatus, setFilterStatus] = useState("");
  const [search, setSearch] = useState("");

  const canEdit = user && ["admin", "compras", "engenharia_produto"].includes(user.role);

  const fetchOCs = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (filterStatus) params.status = filterStatus;
      const { data } = await api.get("/compras/ordens", { params });
      setOcs(data.ordens || []);
    } catch { toast.error("Erro ao carregar ordens de compra"); }
    finally { setLoading(false); }
  }, [filterStatus]);

  useEffect(() => { fetchOCs(); }, [fetchOCs]);

  const filtered = ocs.filter(oc =>
    !search ||
    (oc.numero_oc || "").toLowerCase().includes(search.toLowerCase()) ||
    (oc.numero_kickoff || "").toLowerCase().includes(search.toLowerCase()) ||
    (oc.fornecedor_nome || "").toLowerCase().includes(search.toLowerCase()) ||
    (oc.bom_item_descricao || "").toLowerCase().includes(search.toLowerCase())
  );

  const totalValor = filtered.reduce((s, oc) => s + (oc.valor_total_rs || 0), 0);

  const byStatus = Object.fromEntries(
    Object.keys(STATUS_CONFIG).map(k => [k, ocs.filter(o => o.status === k).length])
  );

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-heading font-semibold flex items-center gap-2">
            <ShoppingCart className="h-6 w-6 text-blue-600" />
            Ordens de Compra
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">Compras vinculadas ao BOM dos Kickoffs aprovados</p>
        </div>
        {canEdit && (
          <Button onClick={() => setNewOCOpen(true)} className="gap-1.5">
            <Plus className="h-4 w-4" />
            Nova OC
          </Button>
        )}
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        {Object.entries(STATUS_CONFIG).map(([k, cfg]) => (
          <Card key={k} className={`cursor-pointer border transition-colors ${filterStatus === k ? "border-primary bg-primary/5" : ""}`} onClick={() => setFilterStatus(f => f === k ? "" : k)}>
            <CardContent className="p-3 text-center">
              <p className="text-xl font-bold">{byStatus[k] || 0}</p>
              <p className="text-xs text-muted-foreground">{cfg.label}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Filters */}
      <div className="flex gap-2 items-center">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input className="pl-8 h-9 text-sm" placeholder="Buscar OC, kickoff, fornecedor..." value={search} onChange={e => setSearch(e.target.value)} />
          {search && <button className="absolute right-2.5 top-2.5" onClick={() => setSearch("")}><X className="h-4 w-4 text-muted-foreground" /></button>}
        </div>
        {filterStatus && (
          <Button variant="ghost" size="sm" onClick={() => setFilterStatus("")} className="gap-1 text-xs">
            <X className="h-3 w-3" />
            Limpar filtro
          </Button>
        )}
        <Button variant="ghost" size="sm" onClick={fetchOCs} className="h-9 w-9 p-0">
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
        </Button>
      </div>

      {/* List */}
      {loading ? (
        <div className="flex justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16 border border-dashed rounded-xl bg-muted/10">
          <ShoppingCart className="h-10 w-10 text-muted-foreground/30 mx-auto mb-3" />
          <p className="text-muted-foreground">
            {ocs.length === 0 ? "Nenhuma Ordem de Compra ainda." : "Nenhuma OC corresponde ao filtro."}
          </p>
          {canEdit && ocs.length === 0 && (
            <Button variant="outline" className="mt-4 gap-1.5" onClick={() => setNewOCOpen(true)}>
              <Plus className="h-4 w-4" />Nova OC
            </Button>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map(oc => (
            <OCCard key={oc.id} oc={oc} onRefresh={fetchOCs} canEdit={canEdit} />
          ))}
          <div className="flex justify-end pt-2">
            <p className="text-sm text-muted-foreground">
              {filtered.length} ordem{filtered.length !== 1 ? "s" : ""} · Total: <strong>{formatBRL(totalValor)}</strong>
            </p>
          </div>
        </div>
      )}

      <NewOCDialog open={newOCOpen} onClose={() => setNewOCOpen(false)} onCreated={fetchOCs} />
    </div>
  );
}
