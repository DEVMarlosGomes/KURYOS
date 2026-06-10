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
    Package, Plus, Search, Trash2, Loader2, AlertTriangle, Zap, Link,
} from "lucide-react";

const TIPO_MP_OPTIONS = [
    { value: "FORMULACAO", label: "Matéria-Prima (Formulação)" },
    { value: "ROTULO",     label: "Rótulo / Arte" },
    { value: "EMBALAGEM",  label: "Embalagem / Insumo" },
];

const STATUS_CONFIG = {
    quarentena: { label: "Quarentena CQ", cls: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300" },
    liberado:   { label: "Liberado",       cls: "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300" },
    reprovado:  { label: "Reprovado",      cls: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300" },
};

function emptyItem() {
    return { nome: "", codigo: "", tipo_mp: "FORMULACAO", quantidade: "", unidade: "kg", lote: "", validade: "", urgente: false };
}

function emptyForm() {
    return {
        po_id: "",
        po_numero: "",
        fornecedor_id: "",
        fornecedor_nome: "",
        numero_nf: "",
        data_nf: new Date().toISOString().slice(0, 10),
        observacoes: "",
        items: [emptyItem()],
    };
}

function formatDate(iso) {
    if (!iso) return "—";
    try { return new Date(iso).toLocaleDateString("pt-BR"); } catch { return iso; }
}

export default function RecebimentoPage() {
    const [entradas, setEntradas] = useState([]);
    const [loading, setLoading] = useState(true);
    const [search, setSearch] = useState("");
    const [showForm, setShowForm] = useState(false);
    const [form, setForm] = useState(emptyForm());
    const [saving, setSaving] = useState(false);
    const [fornecedores, setFornecedores] = useState([]);
    const [pos, setPOs] = useState([]);
    const [selectedEntrada, setSelectedEntrada] = useState(null);
    const [poSugestoes, setPoSugestoes] = useState([]);
    const [loadingSugestao, setLoadingSugestao] = useState(false);
    const [checkingUrgente, setCheckingUrgente] = useState({});

    const loadEntradas = useCallback(async () => {
        setLoading(true);
        try {
            const params = {};
            if (search.trim()) params.q = search.trim();
            const { data } = await api.get("/recebimento/entradas", { params });
            setEntradas(data);
        } catch (e) {
            toast.error(formatApiError(e));
        } finally {
            setLoading(false);
        }
    }, [search]);

    const loadFornecedores = useCallback(async () => {
        try {
            const { data } = await api.get("/compras/fornecedores");
            setFornecedores(data || []);
        } catch { /* optional */ }
    }, []);

    const loadPOs = useCallback(async () => {
        try {
            const { data } = await api.get("/compras/pos");
            setPOs((data || []).filter(p => p.status === "aprovada" || p.status === "em_entrega"));
        } catch { /* optional */ }
    }, []);

    useEffect(() => { loadEntradas(); }, [loadEntradas]);
    useEffect(() => { loadFornecedores(); loadPOs(); }, [loadFornecedores, loadPOs]);

    const openForm = () => {
        setForm(emptyForm());
        setPoSugestoes([]);
        setShowForm(true);
    };

    const setField = (key, val) => setForm(f => ({ ...f, [key]: val }));

    const setItem = (idx, key, val) => {
        setForm(f => {
            const items = [...f.items];
            items[idx] = { ...items[idx], [key]: val };
            return { ...f, items };
        });
    };

    const addItem = () => setForm(f => ({ ...f, items: [...f.items, emptyItem()] }));

    const removeItem = (idx) => setForm(f => ({
        ...f,
        items: f.items.length > 1 ? f.items.filter((_, i) => i !== idx) : f.items,
    }));

    // RN-REC-03: Auto-link PO suggestion
    const buscarSugestoesPO = async (fornecedorId, itemNome) => {
        if (!fornecedorId) return;
        setLoadingSugestao(true);
        try {
            const params = { fornecedor_id: fornecedorId };
            if (itemNome) params.item_nome = itemNome;
            const { data } = await api.get("/recebimento/sugerir-po", { params });
            setPoSugestoes(data || []);
            if (data && data.length === 1) {
                onSelectPO(data[0].id, data);
                toast.info(`PO ${data[0].numero_po || data[0].id.slice(-6)} vinculada automaticamente`);
            }
        } catch { /* silent */ } finally {
            setLoadingSugestao(false);
        }
    };

    // RN-REC-00B: Check URGENT for an item
    const checkUrgente = async (idx, nome) => {
        if (!nome.trim()) return;
        setCheckingUrgente(prev => ({ ...prev, [idx]: true }));
        try {
            const { data } = await api.get("/recebimento/check-urgente", { params: { item_nome: nome } });
            if (data.urgente) {
                setItem(idx, "urgente", true);
                toast.warning(`URGENTE: ${nome} está bloqueando uma OP nos próximos 14 dias!`);
            } else {
                setItem(idx, "urgente", false);
            }
        } catch { /* silent */ } finally {
            setCheckingUrgente(prev => ({ ...prev, [idx]: false }));
        }
    };

    const onSelectPO = (poId, sugestoes) => {
        const pool = sugestoes || poSugestoes;
        const po = pos.find(p => p.id === poId) || pool.find(p => p.id === poId);
        if (!po) { setField("po_id", ""); setField("po_numero", ""); return; }
        const forn = fornecedores.find(f => f.id === po.fornecedor_id);
        setForm(f => ({
            ...f,
            po_id: po.id,
            po_numero: po.numero_po || po.id.slice(-6),
            fornecedor_id: po.fornecedor_id || "",
            fornecedor_nome: forn?.razao_social || forn?.nome_fantasia || po.fornecedor_nome || "",
        }));
    };

    const onFornecedorChange = (id) => {
        const f = fornecedores.find(x => x.id === id);
        setForm(prev => ({
            ...prev,
            fornecedor_id: id,
            fornecedor_nome: f?.razao_social || f?.nome_fantasia || "",
        }));
        const primeiroItem = form.items[0]?.nome;
        buscarSugestoesPO(id, primeiroItem || "");
    };

    const handleSave = async () => {
        if (!form.numero_nf.trim()) { toast.error("Informe o número da NF"); return; }
        if (!form.data_nf) { toast.error("Informe a data da NF"); return; }
        const itemsValidos = form.items.filter(i => i.nome.trim() && Number(i.quantidade) > 0);
        if (itemsValidos.length === 0) { toast.error("Adicione ao menos 1 item válido (nome + quantidade)"); return; }

        setSaving(true);
        try {
            const payload = {
                po_id: form.po_id || null,
                po_numero: form.po_numero || null,
                fornecedor_id: form.fornecedor_id || null,
                fornecedor_nome: form.fornecedor_nome || null,
                numero_nf: form.numero_nf.trim(),
                data_nf: form.data_nf,
                observacoes: form.observacoes,
                items: itemsValidos.map(i => ({
                    nome: i.nome.trim(),
                    codigo: i.codigo.trim(),
                    tipo_mp: i.tipo_mp,
                    quantidade: Number(i.quantidade),
                    unidade: i.unidade || "kg",
                    lote: i.lote.trim(),
                    validade: i.validade || null,
                })),
            };
            const { data: result } = await api.post("/recebimento/entradas", payload);
            const temUrgente = result.tem_urgente;
            toast.success(
                temUrgente
                    ? `NF ${form.numero_nf} registrada — ⚡ item URGENTE detectado, verifique a RA CQ!`
                    : `NF ${form.numero_nf} registrada — itens em quarentena CQ`
            );
            setShowForm(false);
            loadEntradas();
        } catch (e) {
            toast.error(formatApiError(e));
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className="h-full overflow-auto">
            <div className="max-w-6xl mx-auto p-6 space-y-5">
                {/* Header */}
                <div className="flex items-start justify-between gap-4 flex-wrap">
                    <div>
                        <h1 className="text-2xl font-heading font-semibold tracking-tight flex items-center gap-2">
                            <Package className="h-6 w-6" />
                            Recebimento de Materiais
                        </h1>
                        <p className="text-sm text-muted-foreground mt-1">
                            Entrada de NF → estoque em quarentena → RA CQ automático
                        </p>
                    </div>
                    <Button onClick={openForm} data-testid="btn-novo-recebimento">
                        <Plus className="h-4 w-4 mr-1" /> Novo Recebimento
                    </Button>
                </div>

                {/* Search */}
                <div className="relative max-w-md">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                        placeholder="Buscar por NF, fornecedor, PO…"
                        value={search}
                        onChange={e => setSearch(e.target.value)}
                        className="pl-9"
                    />
                </div>

                {/* List */}
                {loading ? (
                    <div className="flex items-center justify-center py-20">
                        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                    </div>
                ) : entradas.length === 0 ? (
                    <Card className="border-dashed">
                        <CardContent className="py-16 text-center">
                            <Package className="h-14 w-14 mx-auto mb-4 text-muted-foreground/30" />
                            <h3 className="text-lg font-semibold mb-1">Nenhuma entrada registrada</h3>
                            <p className="text-sm text-muted-foreground">
                                Clique em "Novo Recebimento" para registrar a chegada de materiais.
                            </p>
                        </CardContent>
                    </Card>
                ) : (
                    <div className="space-y-2">
                        {entradas.map(ent => {
                            const stCfg = STATUS_CONFIG[ent.status] || STATUS_CONFIG.quarentena;
                            return (
                                <Card
                                    key={ent.id}
                                    className="hover:border-primary/40 hover:shadow-sm transition-all cursor-pointer"
                                    onClick={() => setSelectedEntrada(ent)}
                                    data-testid={`entrada-${ent.id}`}
                                >
                                    <CardContent className="p-4">
                                        <div className="flex items-start justify-between gap-4 flex-wrap">
                                            <div className="flex-1 min-w-0 space-y-1">
                                                <div className="flex items-center gap-2 flex-wrap">
                                                    <span className="font-mono text-sm font-bold text-primary">NF {ent.numero_nf}</span>
                                                    <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium ${stCfg.cls}`}>
                                                        {stCfg.label}
                                                    </span>
                                                    {ent.po_numero && (
                                                        <Badge variant="outline" className="text-[10px]">PO {ent.po_numero}</Badge>
                                                    )}
                                                    {ent.tem_urgente && (
                                                        <Badge className="text-[10px] bg-red-600 text-white gap-1">
                                                            <Zap className="h-2.5 w-2.5" />URGENTE
                                                        </Badge>
                                                    )}
                                                </div>
                                                <div className="text-sm font-medium">{ent.fornecedor_nome || "Fornecedor não informado"}</div>
                                                <div className="text-xs text-muted-foreground">
                                                    Data NF: {formatDate(ent.data_nf)} · {ent.items?.length || 0} item(s)
                                                    · Registrado em {formatDate(ent.created_at)} por {ent.created_by_name}
                                                </div>
                                            </div>
                                            <div className="text-right text-xs text-muted-foreground shrink-0">
                                                {(ent.items || []).slice(0, 3).map((i, idx) => (
                                                    <div key={idx} className="flex items-center gap-1 justify-end">
                                                        {i.urgente && <Zap className="h-3 w-3 text-red-500" />}
                                                        {i.nome} · {i.quantidade} {i.unidade}
                                                    </div>
                                                ))}
                                                {ent.items?.length > 3 && <div>+{ent.items.length - 3} mais</div>}
                                            </div>
                                        </div>
                                    </CardContent>
                                </Card>
                            );
                        })}
                    </div>
                )}
            </div>

            {/* Detail dialog */}
            {selectedEntrada && (
                <Dialog open onOpenChange={() => setSelectedEntrada(null)}>
                    <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
                        <DialogHeader>
                            <DialogTitle>Recebimento NF {selectedEntrada.numero_nf}</DialogTitle>
                        </DialogHeader>
                        <div className="space-y-4 text-sm">
                            <div className="grid grid-cols-2 gap-3">
                                <div><span className="text-muted-foreground">Fornecedor:</span> {selectedEntrada.fornecedor_nome || "—"}</div>
                                <div><span className="text-muted-foreground">Data NF:</span> {formatDate(selectedEntrada.data_nf)}</div>
                                <div><span className="text-muted-foreground">PO Vinculada:</span> {selectedEntrada.po_numero || "—"}</div>
                                <div><span className="text-muted-foreground">Status:</span>{" "}
                                    {(() => { const c = STATUS_CONFIG[selectedEntrada.status]; return c ? <span className={`px-1.5 py-0.5 rounded text-[11px] font-medium ${c.cls}`}>{c.label}</span> : selectedEntrada.status; })()}
                                </div>
                            </div>
                            <Separator />
                            <div>
                                <h4 className="font-semibold mb-2">Itens recebidos</h4>
                                <div className="space-y-2">
                                    {(selectedEntrada.items || []).map((item, idx) => (
                                        <div
                                            key={idx}
                                            className={`rounded-lg border p-3 text-xs space-y-1 ${item.urgente ? "border-red-300 bg-red-50/50 dark:bg-red-950/20" : "border-border"}`}
                                        >
                                            <div className="font-medium flex items-center gap-2">
                                                {item.urgente && (
                                                    <Badge className="text-[10px] bg-red-600 text-white gap-1 py-0">
                                                        <Zap className="h-2.5 w-2.5" />URGENTE
                                                    </Badge>
                                                )}
                                                {item.nome} {item.codigo ? `(${item.codigo})` : ""}
                                            </div>
                                            <div className="text-muted-foreground flex flex-wrap gap-x-3 gap-y-0.5">
                                                <span>Tipo: {TIPO_MP_OPTIONS.find(t => t.value === item.tipo_mp)?.label || item.tipo_mp}</span>
                                                <span>Qtd: {item.quantidade} {item.unidade}</span>
                                                {item.lote && <span>Lote: {item.lote}</span>}
                                                {item.validade && <span>Validade: {formatDate(item.validade)}</span>}
                                                {item.data_limite_cq && (
                                                    <span className="text-amber-600">Prazo CQ: {formatDate(item.data_limite_cq)}</span>
                                                )}
                                            </div>
                                            {item.ra_id && (
                                                <div className="mt-1 text-[10px] text-amber-600 flex items-center gap-1">
                                                    <AlertTriangle className="h-3 w-3" />
                                                    RA CQ criada · Status: {item.ra_status || "rascunho"}
                                                </div>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            </div>
                            {selectedEntrada.observacoes && (
                                <>
                                    <Separator />
                                    <p className="text-muted-foreground italic">{selectedEntrada.observacoes}</p>
                                </>
                            )}
                        </div>
                        <DialogFooter>
                            <Button variant="outline" onClick={() => setSelectedEntrada(null)}>Fechar</Button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>
            )}

            {/* New entry form dialog */}
            <Dialog open={showForm} onOpenChange={v => { if (!v) setShowForm(false); }}>
                <DialogContent className="max-w-3xl max-h-[92vh] overflow-y-auto">
                    <DialogHeader>
                        <DialogTitle>Registrar Recebimento de Materiais</DialogTitle>
                    </DialogHeader>

                    <div className="space-y-5">
                        {/* Fornecedor + PO auto-link */}
                        <div className="grid grid-cols-2 gap-3">
                            <div>
                                <Label>Fornecedor</Label>
                                {fornecedores.length > 0 ? (
                                    <Select value={form.fornecedor_id} onValueChange={onFornecedorChange}>
                                        <SelectTrigger className="mt-1">
                                            <SelectValue placeholder="Selecionar…" />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {fornecedores.map(f => (
                                                <SelectItem key={f.id} value={f.id}>
                                                    {f.razao_social || f.nome_fantasia}
                                                </SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                ) : (
                                    <Input
                                        value={form.fornecedor_nome}
                                        onChange={e => setField("fornecedor_nome", e.target.value)}
                                        placeholder="Nome do fornecedor"
                                        className="mt-1"
                                    />
                                )}
                            </div>
                            <div>
                                <Label className="flex items-center justify-between">
                                    <span className="flex items-center gap-1">
                                        PO Vinculada
                                        {loadingSugestao && <Loader2 className="h-3 w-3 animate-spin ml-1" />}
                                    </span>
                                    {form.fornecedor_id && !form.po_id && (
                                        <button
                                            type="button"
                                            className="text-[10px] text-primary hover:underline flex items-center gap-1"
                                            onClick={() => buscarSugestoesPO(form.fornecedor_id, form.items[0]?.nome)}
                                        >
                                            <Link className="h-3 w-3" />Sugerir PO
                                        </button>
                                    )}
                                </Label>
                                {poSugestoes.length > 1 ? (
                                    <Select onValueChange={v => onSelectPO(v, poSugestoes)}>
                                        <SelectTrigger className="mt-1">
                                            <SelectValue placeholder={`${poSugestoes.length} POs encontradas — selecione`} />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {poSugestoes.map(po => (
                                                <SelectItem key={po.id} value={po.id}>
                                                    PO {po.numero_po || po.id.slice(-6)} · {po.fornecedor_nome || "—"}
                                                </SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                ) : pos.length > 0 ? (
                                    <Select value={form.po_id} onValueChange={v => onSelectPO(v, [])}>
                                        <SelectTrigger className="mt-1">
                                            <SelectValue placeholder="Selecionar PO…" />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {pos.map(po => (
                                                <SelectItem key={po.id} value={po.id}>
                                                    PO {po.numero_po || po.id.slice(-6)} · {po.fornecedor_nome || "—"}
                                                </SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                ) : (
                                    <Input
                                        value={form.po_numero}
                                        onChange={e => setField("po_numero", e.target.value)}
                                        placeholder="Nº da PO (opcional)"
                                        className="mt-1"
                                    />
                                )}
                                {form.po_id && (
                                    <p className="text-[10px] text-green-600 mt-1 flex items-center gap-1">
                                        <Link className="h-3 w-3" />PO {form.po_numero} vinculada
                                    </p>
                                )}
                            </div>
                        </div>

                        {/* NF data */}
                        <div className="grid grid-cols-2 gap-3">
                            <div>
                                <Label htmlFor="numero_nf">Número da NF *</Label>
                                <Input
                                    id="numero_nf"
                                    value={form.numero_nf}
                                    onChange={e => setField("numero_nf", e.target.value)}
                                    placeholder="Ex: 000123"
                                    className="mt-1"
                                    data-testid="input-numero-nf"
                                />
                            </div>
                            <div>
                                <Label htmlFor="data_nf">Data da NF *</Label>
                                <Input
                                    id="data_nf"
                                    type="date"
                                    value={form.data_nf}
                                    onChange={e => setField("data_nf", e.target.value)}
                                    className="mt-1"
                                />
                            </div>
                        </div>

                        <div>
                            <Label htmlFor="observacoes">Observações</Label>
                            <Input
                                id="observacoes"
                                value={form.observacoes}
                                onChange={e => setField("observacoes", e.target.value)}
                                placeholder="Opcional"
                                className="mt-1"
                            />
                        </div>

                        <Separator />

                        {/* Items */}
                        <div>
                            <div className="flex items-center justify-between mb-3">
                                <h3 className="font-semibold text-sm">Itens Recebidos</h3>
                                <Button size="sm" variant="outline" onClick={addItem}>
                                    <Plus className="h-3.5 w-3.5 mr-1" /> Adicionar Item
                                </Button>
                            </div>
                            <div className="space-y-3">
                                {form.items.map((item, idx) => (
                                    <div
                                        key={idx}
                                        className={`rounded-lg border p-3 space-y-3 ${item.urgente ? "border-red-300 bg-red-50/40 dark:bg-red-950/20" : "border-border"}`}
                                    >
                                        <div className="flex items-center justify-between">
                                            <div className="flex items-center gap-2">
                                                <span className="text-xs font-semibold text-muted-foreground uppercase">Item {idx + 1}</span>
                                                {item.urgente && (
                                                    <Badge className="text-[10px] bg-red-600 text-white gap-1 py-0">
                                                        <Zap className="h-2.5 w-2.5" />URGENTE — bloqueando OP!
                                                    </Badge>
                                                )}
                                                {checkingUrgente[idx] && (
                                                    <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
                                                )}
                                            </div>
                                            {form.items.length > 1 && (
                                                <Button
                                                    size="icon" variant="ghost"
                                                    className="h-6 w-6 text-destructive hover:text-destructive"
                                                    onClick={() => removeItem(idx)}
                                                >
                                                    <Trash2 className="h-3.5 w-3.5" />
                                                </Button>
                                            )}
                                        </div>
                                        <div className="grid grid-cols-2 gap-2">
                                            <div>
                                                <Label className="text-xs">Nome *</Label>
                                                <Input
                                                    value={item.nome}
                                                    onChange={e => setItem(idx, "nome", e.target.value)}
                                                    onBlur={e => {
                                                        const val = e.target.value.trim();
                                                        if (val) checkUrgente(idx, val);
                                                        if (val && form.fornecedor_id) buscarSugestoesPO(form.fornecedor_id, val);
                                                    }}
                                                    placeholder="Nome da matéria-prima"
                                                    className="mt-0.5 h-8 text-sm"
                                                />
                                            </div>
                                            <div>
                                                <Label className="text-xs">Código interno</Label>
                                                <Input
                                                    value={item.codigo}
                                                    onChange={e => setItem(idx, "codigo", e.target.value)}
                                                    placeholder="Opcional"
                                                    className="mt-0.5 h-8 text-sm"
                                                />
                                            </div>
                                            <div>
                                                <Label className="text-xs">Tipo</Label>
                                                <Select value={item.tipo_mp} onValueChange={v => setItem(idx, "tipo_mp", v)}>
                                                    <SelectTrigger className="mt-0.5 h-8 text-sm">
                                                        <SelectValue />
                                                    </SelectTrigger>
                                                    <SelectContent>
                                                        {TIPO_MP_OPTIONS.map(o => (
                                                            <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                                                        ))}
                                                    </SelectContent>
                                                </Select>
                                            </div>
                                            <div className="grid grid-cols-2 gap-1">
                                                <div>
                                                    <Label className="text-xs">Quantidade *</Label>
                                                    <Input
                                                        type="number"
                                                        min="0"
                                                        step="0.001"
                                                        value={item.quantidade}
                                                        onChange={e => setItem(idx, "quantidade", e.target.value)}
                                                        placeholder="0"
                                                        className="mt-0.5 h-8 text-sm"
                                                    />
                                                </div>
                                                <div>
                                                    <Label className="text-xs">Unidade</Label>
                                                    <Select value={item.unidade} onValueChange={v => setItem(idx, "unidade", v)}>
                                                        <SelectTrigger className="mt-0.5 h-8 text-sm">
                                                            <SelectValue />
                                                        </SelectTrigger>
                                                        <SelectContent>
                                                            {["kg", "g", "L", "mL", "un", "cx", "sc"].map(u => (
                                                                <SelectItem key={u} value={u}>{u}</SelectItem>
                                                            ))}
                                                        </SelectContent>
                                                    </Select>
                                                </div>
                                            </div>
                                            <div>
                                                <Label className="text-xs">Lote do Fornecedor</Label>
                                                <Input
                                                    value={item.lote}
                                                    onChange={e => setItem(idx, "lote", e.target.value)}
                                                    placeholder="Opcional"
                                                    className="mt-0.5 h-8 text-sm"
                                                />
                                            </div>
                                            <div>
                                                <Label className="text-xs">Validade</Label>
                                                <Input
                                                    type="date"
                                                    value={item.validade}
                                                    onChange={e => setItem(idx, "validade", e.target.value)}
                                                    className="mt-0.5 h-8 text-sm"
                                                />
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>

                        <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 flex items-start gap-2 text-xs">
                            <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
                            <span>Após registrar, os itens entrarão no estoque em <strong>quarentena CQ</strong> e um <strong>Registro de Análise</strong> será criado automaticamente para cada item.</span>
                        </div>
                    </div>

                    <DialogFooter className="mt-4">
                        <Button variant="outline" onClick={() => setShowForm(false)} disabled={saving}>Cancelar</Button>
                        <Button onClick={handleSave} disabled={saving} data-testid="btn-salvar-recebimento">
                            {saving ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Package className="h-4 w-4 mr-1" />}
                            Registrar Recebimento
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
