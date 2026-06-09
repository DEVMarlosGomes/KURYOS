import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { formatApiError } from "@/lib/formatError";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
    Truck, Plus, Search, Loader2, ChevronRight, Trash2,
    Building2, Calendar, Package,
} from "lucide-react";

const STATUS_CONFIG = {
    pendente:   { label: "Pendente",    cls: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300" },
    preparando: { label: "Preparando",  cls: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300" },
    expedido:   { label: "Expedido",    cls: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300" },
    entregue:   { label: "Entregue",    cls: "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300" },
    cancelado:  { label: "Cancelado",   cls: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300" },
};

const NEXT_STATUS = {
    pendente:   { to: "preparando",  label: "Iniciar Separação" },
    preparando: { to: "expedido",    label: "Confirmar Despacho" },
    expedido:   { to: "entregue",    label: "Confirmar Entrega" },
};

function emptyItem() {
    return { produto_nome: "", sku: "", quantidade: "", unidade: "un", lote: "" };
}

function emptyForm() {
    return {
        order_id: "",
        order_numero: "",
        cliente_nome: "",
        endereco_entrega: "",
        transportadora: "",
        previsao_entrega: "",
        observacoes: "",
        items: [emptyItem()],
    };
}

function formatDate(iso) {
    if (!iso) return "—";
    try { return new Date(iso).toLocaleDateString("pt-BR"); } catch { return iso; }
}

function StatusBadge({ status }) {
    const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.pendente;
    return <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium ${cfg.cls}`}>{cfg.label}</span>;
}

export default function ExpedicaoPage() {
    const [ordens, setOrdens] = useState([]);
    const [loading, setLoading] = useState(true);
    const [search, setSearch] = useState("");
    const [statusFilter, setStatusFilter] = useState("all");
    const [showForm, setShowForm] = useState(false);
    const [form, setForm] = useState(emptyForm());
    const [saving, setSaving] = useState(false);
    const [selectedExp, setSelectedExp] = useState(null);
    const [actionLoading, setActionLoading] = useState(false);
    const [orders, setOrders] = useState([]);
    const [showDispatch, setShowDispatch] = useState(false);
    const [dispatchForm, setDispatchForm] = useState({ codigo_rastreio: "", transportadora: "" });

    const loadOrdens = useCallback(async () => {
        setLoading(true);
        try {
            const params = {};
            if (statusFilter !== "all") params.status = statusFilter;
            if (search.trim()) params.q = search.trim();
            const { data } = await api.get("/expedicao/ordens", { params });
            setOrdens(data || []);
        } catch (e) {
            toast.error(formatApiError(e));
        } finally {
            setLoading(false);
        }
    }, [search, statusFilter]);

    const loadOrders = useCallback(async () => {
        try {
            const { data } = await api.get("/orders", { params: { status: "concluido" } });
            setOrders(Array.isArray(data) ? data : []);
        } catch { /* optional */ }
    }, []);

    useEffect(() => { loadOrdens(); }, [loadOrdens]);
    useEffect(() => { loadOrders(); }, [loadOrders]);

    const setField = (k, v) => setForm(f => ({ ...f, [k]: v }));
    const setItem = (idx, k, v) => setForm(f => {
        const items = [...f.items];
        items[idx] = { ...items[idx], [k]: v };
        return { ...f, items };
    });
    const addItem = () => setForm(f => ({ ...f, items: [...f.items, emptyItem()] }));
    const removeItem = (idx) => setForm(f => ({
        ...f, items: f.items.length > 1 ? f.items.filter((_, i) => i !== idx) : f.items,
    }));

    const onSelectOrder = (orderId) => {
        const o = orders.find(x => x.id === orderId);
        if (!o) { setField("order_id", ""); return; }
        setForm(f => ({
            ...f,
            order_id: o.id,
            order_numero: o.numero_pedido || "",
            cliente_nome: o.cliente?.razao_social || o.cliente?.nome || f.cliente_nome,
            items: (o.items || []).map(i => ({
                produto_nome: i.descricao || i.produto || "",
                sku: i.sku || "",
                quantidade: String(i.quantidade || ""),
                unidade: i.unidade || "un",
                lote: "",
            })).filter(i => i.produto_nome) || [emptyItem()],
        }));
    };

    const handleCreate = async () => {
        if (!form.cliente_nome.trim()) { toast.error("Informe o nome do cliente"); return; }
        const itemsValidos = form.items.filter(i => i.produto_nome.trim() && Number(i.quantidade) > 0);
        if (!itemsValidos.length) { toast.error("Adicione ao menos 1 item válido"); return; }
        setSaving(true);
        try {
            await api.post("/expedicao/ordens", {
                order_id: form.order_id || null,
                order_numero: form.order_numero || null,
                cliente_nome: form.cliente_nome.trim(),
                endereco_entrega: form.endereco_entrega,
                transportadora: form.transportadora,
                previsao_entrega: form.previsao_entrega || null,
                observacoes: form.observacoes,
                items: itemsValidos.map(i => ({
                    produto_nome: i.produto_nome.trim(),
                    sku: i.sku,
                    quantidade: Number(i.quantidade),
                    unidade: i.unidade,
                    lote: i.lote,
                })),
            });
            toast.success("Ordem de expedição criada");
            setShowForm(false);
            setForm(emptyForm());
            loadOrdens();
        } catch (e) {
            toast.error(formatApiError(e));
        } finally {
            setSaving(false);
        }
    };

    const handleAdvance = async (exp, extra = {}) => {
        const next = NEXT_STATUS[exp.status];
        if (!next) return;
        if (next.to === "expedido" && !Object.keys(extra).length) {
            setSelectedExp(exp);
            setDispatchForm({ codigo_rastreio: "", transportadora: exp.transportadora || "" });
            setShowDispatch(true);
            return;
        }
        setActionLoading(true);
        try {
            const updated = await api.put(`/expedicao/ordens/${exp.id}`, { status: next.to, ...extra });
            toast.success(next.label + " — concluído");
            loadOrdens();
            if (selectedExp?.id === exp.id) setSelectedExp(updated.data);
        } catch (e) {
            toast.error(formatApiError(e));
        } finally {
            setActionLoading(false);
        }
    };

    const handleConfirmDispatch = async () => {
        if (!selectedExp) return;
        setActionLoading(true);
        try {
            const updated = await api.put(`/expedicao/ordens/${selectedExp.id}`, {
                status: "expedido",
                codigo_rastreio: dispatchForm.codigo_rastreio,
                transportadora: dispatchForm.transportadora,
            });
            toast.success("Despacho confirmado — estoque atualizado");
            setShowDispatch(false);
            setSelectedExp(updated.data);
            loadOrdens();
        } catch (e) {
            toast.error(formatApiError(e));
        } finally {
            setActionLoading(false);
        }
    };

    const handleCancel = async (exp) => {
        if (!window.confirm(`Cancelar ${exp.numero_exp}?`)) return;
        setActionLoading(true);
        try {
            await api.put(`/expedicao/ordens/${exp.id}`, { status: "cancelado" });
            toast.success("Expedição cancelada");
            loadOrdens();
            if (selectedExp?.id === exp.id) setSelectedExp(null);
        } catch (e) {
            toast.error(formatApiError(e));
        } finally {
            setActionLoading(false);
        }
    };

    const counts = {
        total: ordens.length,
        pendente: ordens.filter(o => o.status === "pendente").length,
        preparando: ordens.filter(o => o.status === "preparando").length,
        expedido: ordens.filter(o => o.status === "expedido").length,
    };

    return (
        <div className="h-full overflow-auto">
            <div className="max-w-6xl mx-auto p-6 space-y-5">
                <div className="flex items-start justify-between gap-4 flex-wrap">
                    <div>
                        <h1 className="text-2xl font-heading font-semibold tracking-tight flex items-center gap-2">
                            <Truck className="h-6 w-6" />
                            Expedição
                        </h1>
                        <p className="text-sm text-muted-foreground mt-1">
                            Separação, embalagem e despacho de produtos acabados
                        </p>
                    </div>
                    <Button onClick={() => { setForm(emptyForm()); setShowForm(true); }}>
                        <Plus className="h-4 w-4 mr-1" /> Nova Expedição
                    </Button>
                </div>

                {/* Stats */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    {[
                        { label: "Total", value: counts.total, cls: "text-foreground" },
                        { label: "Pendentes", value: counts.pendente, cls: "text-slate-600" },
                        { label: "Preparando", value: counts.preparando, cls: "text-amber-600" },
                        { label: "Em Trânsito", value: counts.expedido, cls: "text-blue-600" },
                    ].map(s => (
                        <Card key={s.label}><CardContent className="p-3">
                            <div className="text-[11px] text-muted-foreground uppercase tracking-wider">{s.label}</div>
                            <div className={`text-2xl font-bold mt-0.5 ${s.cls}`}>{s.value}</div>
                        </CardContent></Card>
                    ))}
                </div>

                {/* Filters */}
                <div className="flex gap-2 flex-wrap">
                    <div className="relative flex-1 min-w-[240px]">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                        <Input placeholder="Buscar EXP, cliente, PI…" value={search}
                            onChange={e => setSearch(e.target.value)} className="pl-9" />
                    </div>
                    <Select value={statusFilter} onValueChange={setStatusFilter}>
                        <SelectTrigger className="w-44"><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="all">Todos os Status</SelectItem>
                            {Object.entries(STATUS_CONFIG).map(([k, v]) => (
                                <SelectItem key={k} value={k}>{v.label}</SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>

                {/* List */}
                {loading ? (
                    <div className="flex items-center justify-center py-20">
                        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                    </div>
                ) : ordens.length === 0 ? (
                    <Card className="border-dashed"><CardContent className="py-16 text-center">
                        <Truck className="h-14 w-14 mx-auto mb-4 text-muted-foreground/30" />
                        <h3 className="text-lg font-semibold mb-1">Nenhuma expedição registrada</h3>
                        <p className="text-sm text-muted-foreground">Crie uma expedição a partir de um PI concluído.</p>
                    </CardContent></Card>
                ) : (
                    <div className="space-y-2">
                        {ordens.map(exp => (
                            <Card key={exp.id}
                                className="hover:border-primary/40 hover:shadow-sm transition-all cursor-pointer group"
                                onClick={() => setSelectedExp(exp)}
                                data-testid={`exp-card-${exp.id}`}
                            >
                                <CardContent className="p-4">
                                    <div className="flex items-start justify-between gap-4">
                                        <div className="flex-1 min-w-0 space-y-1.5">
                                            <div className="flex items-center gap-2 flex-wrap">
                                                <span className="font-mono text-sm font-bold text-primary">{exp.numero_exp}</span>
                                                <StatusBadge status={exp.status} />
                                                {exp.order_numero && (
                                                    <Badge variant="outline" className="text-[10px]">PI {exp.order_numero}</Badge>
                                                )}
                                            </div>
                                            <h3 className="font-semibold text-sm flex items-center gap-1">
                                                <Building2 className="h-3.5 w-3.5 text-muted-foreground" />
                                                {exp.cliente_nome}
                                            </h3>
                                            <div className="flex items-center gap-4 text-xs text-muted-foreground flex-wrap">
                                                <span>{exp.items?.length || 0} item(s)</span>
                                                {exp.transportadora && <span>Transportadora: {exp.transportadora}</span>}
                                                {exp.previsao_entrega && (
                                                    <span className="flex items-center gap-1">
                                                        <Calendar className="h-3 w-3" />Prev: {formatDate(exp.previsao_entrega)}
                                                    </span>
                                                )}
                                                {exp.codigo_rastreio && <span>Rastreio: {exp.codigo_rastreio}</span>}
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-2 shrink-0">
                                            {NEXT_STATUS[exp.status] && (
                                                <Button size="sm" variant="outline" className="h-8 text-xs"
                                                    disabled={actionLoading}
                                                    onClick={e => { e.stopPropagation(); handleAdvance(exp); }}
                                                >
                                                    {NEXT_STATUS[exp.status].label}
                                                </Button>
                                            )}
                                            <ChevronRight className="h-4 w-4 text-muted-foreground group-hover:text-primary transition-colors" />
                                        </div>
                                    </div>
                                </CardContent>
                            </Card>
                        ))}
                    </div>
                )}
            </div>

            {/* Detail Dialog */}
            {selectedExp && !showDispatch && (
                <Dialog open onOpenChange={() => setSelectedExp(null)}>
                    <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
                        <DialogHeader>
                            <DialogTitle className="flex items-center gap-2">
                                <Truck className="h-5 w-5" />{selectedExp.numero_exp} — {selectedExp.cliente_nome}
                            </DialogTitle>
                        </DialogHeader>
                        <div className="space-y-4 text-sm">
                            <div className="flex items-center gap-3 flex-wrap">
                                <StatusBadge status={selectedExp.status} />
                                {selectedExp.order_numero && <Badge variant="outline">PI {selectedExp.order_numero}</Badge>}
                            </div>
                            <div className="grid grid-cols-2 gap-3">
                                <div><span className="text-muted-foreground">Transportadora:</span> {selectedExp.transportadora || "—"}</div>
                                <div><span className="text-muted-foreground">Prev. Entrega:</span> {formatDate(selectedExp.previsao_entrega)}</div>
                                <div><span className="text-muted-foreground">Despacho:</span> {formatDate(selectedExp.data_expedicao)}</div>
                                <div><span className="text-muted-foreground">Entregue em:</span> {formatDate(selectedExp.data_entrega)}</div>
                                {selectedExp.codigo_rastreio && (
                                    <div className="col-span-2"><span className="text-muted-foreground">Rastreio:</span> <span className="font-mono">{selectedExp.codigo_rastreio}</span></div>
                                )}
                                {selectedExp.endereco_entrega && (
                                    <div className="col-span-2"><span className="text-muted-foreground">Endereço:</span> {selectedExp.endereco_entrega}</div>
                                )}
                            </div>
                            <Separator />
                            <div>
                                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Itens</p>
                                <div className="space-y-1.5">
                                    {(selectedExp.items || []).map((item, i) => (
                                        <div key={i} className="rounded-lg border border-border p-2.5 text-xs flex items-center justify-between gap-2">
                                            <div>
                                                <span className="font-medium">{item.produto_nome}</span>
                                                {item.sku && <span className="ml-2 text-muted-foreground font-mono">{item.sku}</span>}
                                                {item.lote && <span className="ml-2 text-muted-foreground">Lote: {item.lote}</span>}
                                            </div>
                                            <span className="font-semibold shrink-0">{item.quantidade} {item.unidade}</span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                            {(selectedExp.historico || []).length > 0 && (
                                <>
                                    <Separator />
                                    <div>
                                        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Histórico</p>
                                        <div className="space-y-1">
                                            {selectedExp.historico.map((h, i) => (
                                                <div key={i} className="text-xs text-muted-foreground flex gap-2">
                                                    <span className="mono-num">{new Date(h.em).toLocaleString("pt-BR")}</span>
                                                    <span>·</span>
                                                    <span>{h.para === "pendente" ? "Criada" : `${STATUS_CONFIG[h.de]?.label || h.de} → ${STATUS_CONFIG[h.para]?.label || h.para}`}</span>
                                                    <span>· por {h.por}</span>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                </>
                            )}
                        </div>
                        <DialogFooter className="flex flex-wrap gap-2 justify-between">
                            <div className="flex gap-2 flex-wrap">
                                {NEXT_STATUS[selectedExp.status] && (
                                    <Button size="sm" disabled={actionLoading}
                                        onClick={() => handleAdvance(selectedExp)}>
                                        {actionLoading ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null}
                                        {NEXT_STATUS[selectedExp.status].label}
                                    </Button>
                                )}
                                {["pendente", "preparando"].includes(selectedExp.status) && (
                                    <Button size="sm" variant="outline"
                                        className="text-destructive border-destructive/30 hover:text-destructive"
                                        disabled={actionLoading}
                                        onClick={() => handleCancel(selectedExp)}>
                                        Cancelar
                                    </Button>
                                )}
                            </div>
                            <Button variant="outline" onClick={() => setSelectedExp(null)}>Fechar</Button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>
            )}

            {/* Dispatch dialog */}
            {showDispatch && selectedExp && (
                <Dialog open onOpenChange={() => setShowDispatch(false)}>
                    <DialogContent>
                        <DialogHeader><DialogTitle>Confirmar Despacho — {selectedExp.numero_exp}</DialogTitle></DialogHeader>
                        <div className="space-y-3">
                            <div>
                                <Label>Transportadora</Label>
                                <Input value={dispatchForm.transportadora}
                                    onChange={e => setDispatchForm(f => ({ ...f, transportadora: e.target.value }))}
                                    placeholder="Nome da transportadora"
                                    className="mt-1" />
                            </div>
                            <div>
                                <Label>Código de Rastreio</Label>
                                <Input value={dispatchForm.codigo_rastreio}
                                    onChange={e => setDispatchForm(f => ({ ...f, codigo_rastreio: e.target.value }))}
                                    placeholder="Opcional"
                                    className="mt-1" />
                            </div>
                            <p className="text-xs text-muted-foreground">
                                O estoque de produto acabado será reduzido automaticamente para os itens vinculados ao WMS.
                            </p>
                        </div>
                        <DialogFooter>
                            <Button variant="outline" onClick={() => setShowDispatch(false)} disabled={actionLoading}>Cancelar</Button>
                            <Button onClick={handleConfirmDispatch} disabled={actionLoading}>
                                {actionLoading ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Truck className="h-4 w-4 mr-1" />}
                                Confirmar Despacho
                            </Button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>
            )}

            {/* New form */}
            <Dialog open={showForm} onOpenChange={v => { if (!v) setShowForm(false); }}>
                <DialogContent className="max-w-3xl max-h-[92vh] overflow-y-auto">
                    <DialogHeader><DialogTitle>Nova Ordem de Expedição</DialogTitle></DialogHeader>
                    <div className="space-y-4">
                        {orders.length > 0 && (
                            <div>
                                <Label>Importar de PI (opcional)</Label>
                                <Select onValueChange={onSelectOrder}>
                                    <SelectTrigger className="mt-1"><SelectValue placeholder="Selecionar PI concluído…" /></SelectTrigger>
                                    <SelectContent>
                                        {orders.map(o => (
                                            <SelectItem key={o.id} value={o.id}>
                                                #{o.numero_pedido} — {o.cliente?.razao_social || o.cliente?.nome || "—"}
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                        )}
                        <div className="grid grid-cols-2 gap-3">
                            <div>
                                <Label>Cliente *</Label>
                                <Input value={form.cliente_nome} onChange={e => setField("cliente_nome", e.target.value)}
                                    placeholder="Nome do cliente" className="mt-1" />
                            </div>
                            <div>
                                <Label>Transportadora</Label>
                                <Input value={form.transportadora} onChange={e => setField("transportadora", e.target.value)}
                                    placeholder="Opcional" className="mt-1" />
                            </div>
                            <div>
                                <Label>Endereço de Entrega</Label>
                                <Input value={form.endereco_entrega} onChange={e => setField("endereco_entrega", e.target.value)}
                                    placeholder="Rua, número, cidade…" className="mt-1" />
                            </div>
                            <div>
                                <Label>Previsão de Entrega</Label>
                                <Input type="date" value={form.previsao_entrega}
                                    onChange={e => setField("previsao_entrega", e.target.value)} className="mt-1" />
                            </div>
                        </div>
                        <Separator />
                        <div>
                            <div className="flex items-center justify-between mb-3">
                                <h3 className="font-semibold text-sm">Itens</h3>
                                <Button size="sm" variant="outline" onClick={addItem}>
                                    <Plus className="h-3.5 w-3.5 mr-1" /> Adicionar
                                </Button>
                            </div>
                            <div className="space-y-2">
                                {form.items.map((item, idx) => (
                                    <div key={idx} className="rounded-lg border border-border p-3 grid grid-cols-5 gap-2 items-end">
                                        <div className="col-span-2">
                                            <Label className="text-xs">Produto *</Label>
                                            <Input value={item.produto_nome}
                                                onChange={e => setItem(idx, "produto_nome", e.target.value)}
                                                placeholder="Nome" className="mt-0.5 h-8 text-sm" />
                                        </div>
                                        <div>
                                            <Label className="text-xs">SKU</Label>
                                            <Input value={item.sku} onChange={e => setItem(idx, "sku", e.target.value)}
                                                placeholder="—" className="mt-0.5 h-8 text-sm" />
                                        </div>
                                        <div>
                                            <Label className="text-xs">Qtd *</Label>
                                            <Input type="number" value={item.quantidade}
                                                onChange={e => setItem(idx, "quantidade", e.target.value)}
                                                placeholder="0" className="mt-0.5 h-8 text-sm" />
                                        </div>
                                        <div className="flex gap-1 items-end">
                                            <div className="flex-1">
                                                <Label className="text-xs">Un</Label>
                                                <Select value={item.unidade} onValueChange={v => setItem(idx, "unidade", v)}>
                                                    <SelectTrigger className="mt-0.5 h-8 text-sm"><SelectValue /></SelectTrigger>
                                                    <SelectContent>
                                                        {["un", "cx", "kg", "L"].map(u => <SelectItem key={u} value={u}>{u}</SelectItem>)}
                                                    </SelectContent>
                                                </Select>
                                            </div>
                                            {form.items.length > 1 && (
                                                <Button variant="ghost" size="icon"
                                                    className="h-8 w-8 text-destructive hover:text-destructive shrink-0"
                                                    onClick={() => removeItem(idx)}>
                                                    <Trash2 className="h-3.5 w-3.5" />
                                                </Button>
                                            )}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                        <div>
                            <Label>Observações</Label>
                            <Input value={form.observacoes} onChange={e => setField("observacoes", e.target.value)}
                                placeholder="Opcional" className="mt-1" />
                        </div>
                    </div>
                    <DialogFooter className="mt-4">
                        <Button variant="outline" onClick={() => setShowForm(false)} disabled={saving}>Cancelar</Button>
                        <Button onClick={handleCreate} disabled={saving}>
                            {saving ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Truck className="h-4 w-4 mr-1" />}
                            Criar Expedição
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
