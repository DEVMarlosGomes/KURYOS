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
    Receipt, Plus, Search, Loader2, ChevronRight, DollarSign,
    Building2, Calendar, CheckCircle2, AlertTriangle,
} from "lucide-react";

const NF_STATUS_CONFIG = {
    rascunho: { label: "Rascunho",  cls: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300" },
    emitida:  { label: "Emitida",   cls: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300" },
    cancelada:{ label: "Cancelada", cls: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300" },
};

const PGTO_CONFIG = {
    aguardando:   { label: "Aguardando",   cls: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300" },
    pago_parcial: { label: "Pago Parcial", cls: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300" },
    pago:         { label: "Pago",         cls: "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300" },
    vencido:      { label: "Vencido",      cls: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300" },
};

function formatCurrency(val) {
    if (!val && val !== 0) return "R$ 0,00";
    return `R$ ${Number(val).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatDate(iso) {
    if (!iso) return "—";
    try { return new Date(iso).toLocaleDateString("pt-BR"); } catch { return iso; }
}

function emptyForm() {
    return {
        order_id: "",
        order_numero: "",
        exp_id: "",
        exp_numero: "",
        cliente_nome: "",
        cliente_cnpj: "",
        valor_produtos: "",
        valor_frete: "",
        valor_impostos: "",
        forma_pagamento: "pix",
        condicao_pagamento: "à vista",
        data_emissao: new Date().toISOString().slice(0, 10),
        data_vencimento: "",
        observacoes: "",
    };
}

function NFBadge({ status }) {
    const cfg = NF_STATUS_CONFIG[status] || NF_STATUS_CONFIG.rascunho;
    return <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium ${cfg.cls}`}>{cfg.label}</span>;
}

function PgtoBadge({ status }) {
    const cfg = PGTO_CONFIG[status] || PGTO_CONFIG.aguardando;
    return <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium ${cfg.cls}`}>{cfg.label}</span>;
}

export default function FaturamentoPage() {
    const [notas, setNotas] = useState([]);
    const [loading, setLoading] = useState(true);
    const [search, setSearch] = useState("");
    const [statusFilter, setStatusFilter] = useState("all");
    const [pgtoFilter, setPgtoFilter] = useState("all");
    const [showForm, setShowForm] = useState(false);
    const [form, setForm] = useState(emptyForm());
    const [saving, setSaving] = useState(false);
    const [selectedNF, setSelectedNF] = useState(null);
    const [actionLoading, setActionLoading] = useState(false);
    const [showEmitir, setShowEmitir] = useState(false);
    const [emitirForm, setEmitirForm] = useState({ numero_nfe: "", chave_acesso: "" });
    const [showPagamento, setShowPagamento] = useState(false);
    const [pgtoForm, setPgtoForm] = useState({ status_pagamento: "pago", valor_pago: "", data_pagamento: "" });
    const [orders, setOrders] = useState([]);
    const [expeditions, setExpeditions] = useState([]);
    const [dashboard, setDashboard] = useState(null);

    const loadNotas = useCallback(async () => {
        setLoading(true);
        try {
            const params = {};
            if (statusFilter !== "all") params.status = statusFilter;
            if (pgtoFilter !== "all") params.status_pagamento = pgtoFilter;
            if (search.trim()) params.q = search.trim();
            const { data } = await api.get("/faturamento/notas", { params });
            setNotas(data || []);
        } catch (e) {
            toast.error(formatApiError(e));
        } finally {
            setLoading(false);
        }
    }, [search, statusFilter, pgtoFilter]);

    const loadDashboard = useCallback(async () => {
        try {
            const { data } = await api.get("/faturamento/dashboard");
            setDashboard(data);
        } catch { /* optional */ }
    }, []);

    const loadRefs = useCallback(async () => {
        try {
            const [ordRes, expRes] = await Promise.all([
                api.get("/orders", { params: { status: "concluido" } }),
                api.get("/expedicao/ordens", { params: { status: "expedido" } }),
            ]);
            setOrders(Array.isArray(ordRes.data) ? ordRes.data : []);
            setExpeditions(Array.isArray(expRes.data) ? expRes.data : []);
        } catch { /* optional */ }
    }, []);

    useEffect(() => { loadNotas(); }, [loadNotas]);
    useEffect(() => { loadDashboard(); }, [loadDashboard]);
    useEffect(() => { loadRefs(); }, [loadRefs]);

    const setField = (k, v) => setForm(f => ({ ...f, [k]: v }));

    const onSelectOrder = (orderId) => {
        const o = orders.find(x => x.id === orderId);
        if (!o) { setField("order_id", ""); return; }
        setForm(f => ({
            ...f,
            order_id: o.id,
            order_numero: o.numero_pedido || "",
            cliente_nome: o.cliente?.razao_social || o.cliente?.nome || f.cliente_nome,
            cliente_cnpj: o.cliente?.cnpj || f.cliente_cnpj,
            valor_produtos: String(o.total_pedido || ""),
        }));
    };

    const onSelectExp = (expId) => {
        const e = expeditions.find(x => x.id === expId);
        if (!e) { setField("exp_id", ""); return; }
        setForm(f => ({
            ...f,
            exp_id: e.id,
            exp_numero: e.numero_exp || "",
            cliente_nome: e.cliente_nome || f.cliente_nome,
        }));
    };

    const calcTotal = () => {
        const p = Number(form.valor_produtos) || 0;
        const fr = Number(form.valor_frete) || 0;
        const im = Number(form.valor_impostos) || 0;
        return p + fr + im;
    };

    const handleCreate = async () => {
        if (!form.cliente_nome.trim()) { toast.error("Informe o nome do cliente"); return; }
        setSaving(true);
        try {
            const total = calcTotal();
            await api.post("/faturamento/notas", {
                order_id: form.order_id || null,
                order_numero: form.order_numero || null,
                exp_id: form.exp_id || null,
                exp_numero: form.exp_numero || null,
                cliente_nome: form.cliente_nome.trim(),
                cliente_cnpj: form.cliente_cnpj,
                valor_produtos: Number(form.valor_produtos) || 0,
                valor_frete: Number(form.valor_frete) || 0,
                valor_impostos: Number(form.valor_impostos) || 0,
                valor_total: total,
                forma_pagamento: form.forma_pagamento,
                condicao_pagamento: form.condicao_pagamento,
                data_emissao: form.data_emissao || null,
                data_vencimento: form.data_vencimento || null,
                observacoes: form.observacoes,
            });
            toast.success("Nota Fiscal criada");
            setShowForm(false);
            setForm(emptyForm());
            loadNotas();
            loadDashboard();
        } catch (e) {
            toast.error(formatApiError(e));
        } finally {
            setSaving(false);
        }
    };

    const handleEmitir = async () => {
        if (!selectedNF) return;
        setActionLoading(true);
        try {
            const updated = await api.put(`/faturamento/notas/${selectedNF.id}`, {
                status: "emitida",
                numero_nfe: emitirForm.numero_nfe || null,
                chave_acesso: emitirForm.chave_acesso || null,
            });
            toast.success("NF emitida");
            setShowEmitir(false);
            setSelectedNF(updated.data);
            loadNotas();
            loadDashboard();
        } catch (e) {
            toast.error(formatApiError(e));
        } finally {
            setActionLoading(false);
        }
    };

    const handleRegistrarPagamento = async () => {
        if (!selectedNF) return;
        setActionLoading(true);
        try {
            const updated = await api.put(`/faturamento/notas/${selectedNF.id}`, {
                status_pagamento: pgtoForm.status_pagamento,
                valor_pago: Number(pgtoForm.valor_pago) || selectedNF.valor_total,
                data_pagamento: pgtoForm.data_pagamento || new Date().toISOString().slice(0, 10),
            });
            toast.success("Pagamento registrado");
            setShowPagamento(false);
            setSelectedNF(updated.data);
            loadNotas();
            loadDashboard();
        } catch (e) {
            toast.error(formatApiError(e));
        } finally {
            setActionLoading(false);
        }
    };

    const handleCancel = async (nf) => {
        if (!window.confirm(`Cancelar ${nf.numero_interno}?`)) return;
        setActionLoading(true);
        try {
            const updated = await api.put(`/faturamento/notas/${nf.id}`, { status: "cancelada" });
            toast.success("NF cancelada");
            loadNotas();
            loadDashboard();
            if (selectedNF?.id === nf.id) setSelectedNF(updated.data);
        } catch (e) {
            toast.error(formatApiError(e));
        } finally {
            setActionLoading(false);
        }
    };

    return (
        <div className="h-full overflow-auto">
            <div className="max-w-6xl mx-auto p-6 space-y-5">
                <div className="flex items-start justify-between gap-4 flex-wrap">
                    <div>
                        <h1 className="text-2xl font-heading font-semibold tracking-tight flex items-center gap-2">
                            <Receipt className="h-6 w-6" />
                            Faturamento
                        </h1>
                        <p className="text-sm text-muted-foreground mt-1">
                            Emissão e controle de Notas Fiscais de saída
                        </p>
                    </div>
                    <Button onClick={() => { setForm(emptyForm()); setShowForm(true); }}>
                        <Plus className="h-4 w-4 mr-1" /> Nova NF
                    </Button>
                </div>

                {/* Dashboard strip */}
                {dashboard && (
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                        {[
                            { label: "NFs Emitidas", value: dashboard.emitidas, cls: "text-blue-600" },
                            { label: "Aguard. Pagamento", value: dashboard.aguardando_pagamento, cls: "text-amber-600" },
                            { label: "Vencidas", value: dashboard.vencidas, cls: "text-red-600" },
                            { label: "A Receber", value: formatCurrency(dashboard.total_a_receber), cls: "text-green-600", isText: true },
                        ].map(s => (
                            <Card key={s.label}><CardContent className="p-3">
                                <div className="text-[11px] text-muted-foreground uppercase tracking-wider">{s.label}</div>
                                <div className={`font-bold mt-0.5 ${s.cls} ${s.isText ? "text-base" : "text-2xl"}`}>{s.value}</div>
                            </CardContent></Card>
                        ))}
                    </div>
                )}

                {/* Filters */}
                <div className="flex gap-2 flex-wrap">
                    <div className="relative flex-1 min-w-[220px]">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                        <Input placeholder="Buscar NF, cliente, PI…" value={search}
                            onChange={e => setSearch(e.target.value)} className="pl-9" />
                    </div>
                    <Select value={statusFilter} onValueChange={setStatusFilter}>
                        <SelectTrigger className="w-36"><SelectValue placeholder="Status NF" /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="all">Todos</SelectItem>
                            {Object.entries(NF_STATUS_CONFIG).map(([k, v]) => (
                                <SelectItem key={k} value={k}>{v.label}</SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                    <Select value={pgtoFilter} onValueChange={setPgtoFilter}>
                        <SelectTrigger className="w-40"><SelectValue placeholder="Pagamento" /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="all">Todos Pagamentos</SelectItem>
                            {Object.entries(PGTO_CONFIG).map(([k, v]) => (
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
                ) : notas.length === 0 ? (
                    <Card className="border-dashed"><CardContent className="py-16 text-center">
                        <Receipt className="h-14 w-14 mx-auto mb-4 text-muted-foreground/30" />
                        <h3 className="text-lg font-semibold mb-1">Nenhuma nota fiscal</h3>
                        <p className="text-sm text-muted-foreground">Crie uma NF vinculada a um PI ou EXP.</p>
                    </CardContent></Card>
                ) : (
                    <div className="space-y-2">
                        {notas.map(nf => (
                            <Card key={nf.id}
                                className="hover:border-primary/40 hover:shadow-sm transition-all cursor-pointer group"
                                onClick={() => setSelectedNF(nf)}
                                data-testid={`nf-card-${nf.id}`}
                            >
                                <CardContent className="p-4">
                                    <div className="flex items-start justify-between gap-4">
                                        <div className="flex-1 min-w-0 space-y-1.5">
                                            <div className="flex items-center gap-2 flex-wrap">
                                                <span className="font-mono text-sm font-bold text-primary">
                                                    {nf.numero_nfe || nf.numero_interno}
                                                </span>
                                                <NFBadge status={nf.status} />
                                                <PgtoBadge status={nf.status_pagamento} />
                                                {nf.order_numero && <Badge variant="outline" className="text-[10px]">PI {nf.order_numero}</Badge>}
                                                {nf.exp_numero && <Badge variant="outline" className="text-[10px]">EXP {nf.exp_numero}</Badge>}
                                            </div>
                                            <h3 className="font-semibold text-sm flex items-center gap-1">
                                                <Building2 className="h-3.5 w-3.5 text-muted-foreground" />
                                                {nf.cliente_nome}
                                            </h3>
                                            <div className="flex items-center gap-4 text-xs text-muted-foreground flex-wrap">
                                                <span className="flex items-center gap-1">
                                                    <DollarSign className="h-3 w-3" />{formatCurrency(nf.valor_total)}
                                                </span>
                                                <span>Emissão: {formatDate(nf.data_emissao)}</span>
                                                {nf.data_vencimento && (
                                                    <span className="flex items-center gap-1">
                                                        <Calendar className="h-3 w-3" />Venc: {formatDate(nf.data_vencimento)}
                                                    </span>
                                                )}
                                                <span>{nf.forma_pagamento} · {nf.condicao_pagamento}</span>
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-2 shrink-0">
                                            {nf.status === "rascunho" && (
                                                <Button size="sm" variant="outline" className="h-8 text-xs"
                                                    disabled={actionLoading}
                                                    onClick={e => { e.stopPropagation(); setSelectedNF(nf); setEmitirForm({ numero_nfe: "", chave_acesso: "" }); setShowEmitir(true); }}>
                                                    Emitir NF
                                                </Button>
                                            )}
                                            {nf.status === "emitida" && ["aguardando", "pago_parcial"].includes(nf.status_pagamento) && (
                                                <Button size="sm" variant="outline" className="h-8 text-xs"
                                                    disabled={actionLoading}
                                                    onClick={e => { e.stopPropagation(); setSelectedNF(nf); setPgtoForm({ status_pagamento: "pago", valor_pago: String(nf.valor_total), data_pagamento: new Date().toISOString().slice(0, 10) }); setShowPagamento(true); }}>
                                                    Registrar Pgto
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

            {/* Detail dialog */}
            {selectedNF && !showEmitir && !showPagamento && (
                <Dialog open onOpenChange={() => setSelectedNF(null)}>
                    <DialogContent className="max-w-xl max-h-[90vh] overflow-y-auto">
                        <DialogHeader>
                            <DialogTitle className="flex items-center gap-2">
                                <Receipt className="h-5 w-5" />
                                {selectedNF.numero_nfe || selectedNF.numero_interno}
                            </DialogTitle>
                        </DialogHeader>
                        <div className="space-y-4 text-sm">
                            <div className="flex items-center gap-2 flex-wrap">
                                <NFBadge status={selectedNF.status} />
                                <PgtoBadge status={selectedNF.status_pagamento} />
                            </div>
                            <div className="grid grid-cols-2 gap-3">
                                <div><span className="text-muted-foreground">Cliente:</span> {selectedNF.cliente_nome}</div>
                                <div><span className="text-muted-foreground">CNPJ:</span> {selectedNF.cliente_cnpj || "—"}</div>
                                <div><span className="text-muted-foreground">Emissão:</span> {formatDate(selectedNF.data_emissao)}</div>
                                <div><span className="text-muted-foreground">Vencimento:</span> {formatDate(selectedNF.data_vencimento)}</div>
                                <div><span className="text-muted-foreground">Pagamento:</span> {selectedNF.forma_pagamento} / {selectedNF.condicao_pagamento}</div>
                                <div><span className="text-muted-foreground">Pago:</span> {formatCurrency(selectedNF.valor_pago)}</div>
                            </div>
                            {selectedNF.numero_nfe && (
                                <div className="rounded-lg bg-muted/40 p-3 text-xs space-y-1">
                                    <div><span className="font-semibold">NF-e:</span> {selectedNF.numero_nfe}</div>
                                    {selectedNF.chave_acesso && <div className="break-all font-mono text-[10px]">{selectedNF.chave_acesso}</div>}
                                </div>
                            )}
                            <Separator />
                            <div className="grid grid-cols-3 gap-3 text-center">
                                {[
                                    ["Produtos", selectedNF.valor_produtos],
                                    ["Frete", selectedNF.valor_frete],
                                    ["Impostos", selectedNF.valor_impostos],
                                ].map(([label, val]) => (
                                    <div key={label} className="rounded-lg bg-muted/30 p-2">
                                        <div className="text-xs text-muted-foreground">{label}</div>
                                        <div className="font-semibold text-sm">{formatCurrency(val)}</div>
                                    </div>
                                ))}
                            </div>
                            <div className="rounded-lg bg-primary/10 p-3 flex items-center justify-between">
                                <span className="font-semibold">Total</span>
                                <span className="text-lg font-bold text-primary">{formatCurrency(selectedNF.valor_total)}</span>
                            </div>
                        </div>
                        <DialogFooter className="flex flex-wrap gap-2 justify-between">
                            <div className="flex gap-2 flex-wrap">
                                {selectedNF.status === "rascunho" && (
                                    <Button size="sm"
                                        onClick={() => { setEmitirForm({ numero_nfe: "", chave_acesso: "" }); setShowEmitir(true); }}>
                                        Emitir NF
                                    </Button>
                                )}
                                {selectedNF.status === "emitida" && ["aguardando", "pago_parcial"].includes(selectedNF.status_pagamento) && (
                                    <Button size="sm" variant="outline"
                                        onClick={() => { setPgtoForm({ status_pagamento: "pago", valor_pago: String(selectedNF.valor_total), data_pagamento: new Date().toISOString().slice(0, 10) }); setShowPagamento(true); }}>
                                        <CheckCircle2 className="h-4 w-4 mr-1" />Registrar Pagamento
                                    </Button>
                                )}
                                {["rascunho", "emitida"].includes(selectedNF.status) && (
                                    <Button size="sm" variant="outline"
                                        className="text-destructive border-destructive/30 hover:text-destructive"
                                        disabled={actionLoading}
                                        onClick={() => handleCancel(selectedNF)}>
                                        Cancelar NF
                                    </Button>
                                )}
                            </div>
                            <Button variant="outline" onClick={() => setSelectedNF(null)}>Fechar</Button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>
            )}

            {/* Emitir dialog */}
            {showEmitir && selectedNF && (
                <Dialog open onOpenChange={() => setShowEmitir(false)}>
                    <DialogContent>
                        <DialogHeader><DialogTitle>Emitir NF — {selectedNF.numero_interno}</DialogTitle></DialogHeader>
                        <div className="space-y-3">
                            <div>
                                <Label>Número NF-e</Label>
                                <Input value={emitirForm.numero_nfe}
                                    onChange={e => setEmitirForm(f => ({ ...f, numero_nfe: e.target.value }))}
                                    placeholder="000000000" className="mt-1 font-mono" />
                            </div>
                            <div>
                                <Label>Chave de Acesso (44 dígitos)</Label>
                                <Input value={emitirForm.chave_acesso}
                                    onChange={e => setEmitirForm(f => ({ ...f, chave_acesso: e.target.value }))}
                                    placeholder="Opcional" className="mt-1 font-mono text-xs" />
                            </div>
                        </div>
                        <DialogFooter>
                            <Button variant="outline" onClick={() => setShowEmitir(false)} disabled={actionLoading}>Cancelar</Button>
                            <Button onClick={handleEmitir} disabled={actionLoading}>
                                {actionLoading ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Receipt className="h-4 w-4 mr-1" />}
                                Confirmar Emissão
                            </Button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>
            )}

            {/* Pagamento dialog */}
            {showPagamento && selectedNF && (
                <Dialog open onOpenChange={() => setShowPagamento(false)}>
                    <DialogContent>
                        <DialogHeader><DialogTitle>Registrar Pagamento — {selectedNF.numero_nfe || selectedNF.numero_interno}</DialogTitle></DialogHeader>
                        <div className="space-y-3">
                            <div>
                                <Label>Status do Pagamento</Label>
                                <Select value={pgtoForm.status_pagamento}
                                    onValueChange={v => setPgtoForm(f => ({ ...f, status_pagamento: v }))}>
                                    <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="pago">Pago Integralmente</SelectItem>
                                        <SelectItem value="pago_parcial">Pago Parcial</SelectItem>
                                        <SelectItem value="vencido">Vencido</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                            <div>
                                <Label>Valor Pago</Label>
                                <Input type="number" min="0" step="0.01"
                                    value={pgtoForm.valor_pago}
                                    onChange={e => setPgtoForm(f => ({ ...f, valor_pago: e.target.value }))}
                                    placeholder="0,00" className="mt-1" />
                            </div>
                            <div>
                                <Label>Data do Pagamento</Label>
                                <Input type="date" value={pgtoForm.data_pagamento}
                                    onChange={e => setPgtoForm(f => ({ ...f, data_pagamento: e.target.value }))}
                                    className="mt-1" />
                            </div>
                        </div>
                        <DialogFooter>
                            <Button variant="outline" onClick={() => setShowPagamento(false)} disabled={actionLoading}>Cancelar</Button>
                            <Button onClick={handleRegistrarPagamento} disabled={actionLoading}>
                                {actionLoading ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <CheckCircle2 className="h-4 w-4 mr-1" />}
                                Confirmar
                            </Button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>
            )}

            {/* Create form dialog */}
            <Dialog open={showForm} onOpenChange={v => { if (!v) setShowForm(false); }}>
                <DialogContent className="max-w-2xl max-h-[92vh] overflow-y-auto">
                    <DialogHeader><DialogTitle>Nova Nota Fiscal</DialogTitle></DialogHeader>
                    <div className="space-y-4">
                        <div className="grid grid-cols-2 gap-3">
                            {orders.length > 0 && (
                                <div>
                                    <Label>Vincular PI</Label>
                                    <Select onValueChange={onSelectOrder}>
                                        <SelectTrigger className="mt-1"><SelectValue placeholder="Selecionar PI…" /></SelectTrigger>
                                        <SelectContent>
                                            {orders.map(o => (
                                                <SelectItem key={o.id} value={o.id}>
                                                    #{o.numero_pedido} — {o.cliente?.razao_social || "—"}
                                                </SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>
                            )}
                            {expeditions.length > 0 && (
                                <div>
                                    <Label>Vincular EXP</Label>
                                    <Select onValueChange={onSelectExp}>
                                        <SelectTrigger className="mt-1"><SelectValue placeholder="Selecionar EXP…" /></SelectTrigger>
                                        <SelectContent>
                                            {expeditions.map(e => (
                                                <SelectItem key={e.id} value={e.id}>
                                                    {e.numero_exp} — {e.cliente_nome}
                                                </SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>
                            )}
                        </div>
                        <div className="grid grid-cols-2 gap-3">
                            <div>
                                <Label>Cliente *</Label>
                                <Input value={form.cliente_nome} onChange={e => setField("cliente_nome", e.target.value)}
                                    placeholder="Razão social" className="mt-1" />
                            </div>
                            <div>
                                <Label>CNPJ</Label>
                                <Input value={form.cliente_cnpj} onChange={e => setField("cliente_cnpj", e.target.value)}
                                    placeholder="00.000.000/0000-00" className="mt-1" />
                            </div>
                        </div>
                        <div className="grid grid-cols-3 gap-3">
                            <div>
                                <Label>Valor Produtos (R$)</Label>
                                <Input type="number" value={form.valor_produtos}
                                    onChange={e => setField("valor_produtos", e.target.value)}
                                    placeholder="0,00" className="mt-1" />
                            </div>
                            <div>
                                <Label>Frete (R$)</Label>
                                <Input type="number" value={form.valor_frete}
                                    onChange={e => setField("valor_frete", e.target.value)}
                                    placeholder="0,00" className="mt-1" />
                            </div>
                            <div>
                                <Label>Impostos (R$)</Label>
                                <Input type="number" value={form.valor_impostos}
                                    onChange={e => setField("valor_impostos", e.target.value)}
                                    placeholder="0,00" className="mt-1" />
                            </div>
                        </div>
                        <div className="rounded-lg bg-primary/10 p-3 flex items-center justify-between">
                            <span className="font-semibold text-sm">Total</span>
                            <span className="text-lg font-bold text-primary">{formatCurrency(calcTotal())}</span>
                        </div>
                        <div className="grid grid-cols-2 gap-3">
                            <div>
                                <Label>Forma de Pagamento</Label>
                                <Select value={form.forma_pagamento} onValueChange={v => setField("forma_pagamento", v)}>
                                    <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                        {["pix", "boleto", "transferencia", "cheque", "cartao", "prazo"].map(v => (
                                            <SelectItem key={v} value={v}>{v}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                            <div>
                                <Label>Condição</Label>
                                <Input value={form.condicao_pagamento}
                                    onChange={e => setField("condicao_pagamento", e.target.value)}
                                    placeholder="à vista / 30/60/90…" className="mt-1" />
                            </div>
                            <div>
                                <Label>Data de Emissão</Label>
                                <Input type="date" value={form.data_emissao}
                                    onChange={e => setField("data_emissao", e.target.value)} className="mt-1" />
                            </div>
                            <div>
                                <Label>Data de Vencimento</Label>
                                <Input type="date" value={form.data_vencimento}
                                    onChange={e => setField("data_vencimento", e.target.value)} className="mt-1" />
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
                            {saving ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Receipt className="h-4 w-4 mr-1" />}
                            Criar Nota Fiscal
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
