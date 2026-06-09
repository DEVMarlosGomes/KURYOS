import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { formatApiError } from "@/lib/formatError";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
    RotateCcw, Plus, Search, Loader2, ChevronRight, AlertTriangle,
    ClipboardList, Calendar, User,
} from "lucide-react";

const STATUS_CONFIG = {
    pendente:      { label: "Pendente",       cls: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300" },
    em_retrabalho: { label: "Em Retrabalho",  cls: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300" },
    concluido:     { label: "Aguardando CQ",  cls: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300" },
    reprovado:     { label: "Reprovado",      cls: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300" },
    cancelado:     { label: "Cancelado",      cls: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400" },
};

const NEXT_STATUS = {
    pendente:      "em_retrabalho",
    em_retrabalho: "concluido",
};

const NEXT_STATUS_LABEL = {
    pendente:      "Iniciar Retrabalho",
    em_retrabalho: "Concluir e Enviar para CQ",
};

function emptyForm() {
    return {
        origem_tipo: "rnc",
        origem_id: "",
        lote_numero: "",
        produto_nome: "",
        problema_descrito: "",
        instrucoes_retrabalho: "",
        responsavel_nome: "",
        data_limite: "",
        observacoes: "",
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

export default function CQRetrabalho() {
    const navigate = useNavigate();
    const [ordens, setOrdens] = useState([]);
    const [loading, setLoading] = useState(true);
    const [search, setSearch] = useState("");
    const [statusFilter, setStatusFilter] = useState("all");
    const [showForm, setShowForm] = useState(false);
    const [form, setForm] = useState(emptyForm());
    const [saving, setSaving] = useState(false);
    const [selectedRT, setSelectedRT] = useState(null);
    const [actionLoading, setActionLoading] = useState(false);
    const [showConcluir, setShowConcluir] = useState(false);
    const [obsConc, setObsConc] = useState("");
    const [rncs, setRncs] = useState([]);
    const [ras, setRas] = useState([]);

    const loadOrdens = useCallback(async () => {
        setLoading(true);
        try {
            const params = {};
            if (statusFilter !== "all") params.status = statusFilter;
            if (search.trim()) params.q = search.trim();
            const { data } = await api.get("/retrabalho/ordens", { params });
            setOrdens(data || []);
        } catch (e) {
            toast.error(formatApiError(e));
        } finally {
            setLoading(false);
        }
    }, [search, statusFilter]);

    const loadRefs = useCallback(async () => {
        try {
            const [rncRes, raRes] = await Promise.all([
                api.get("/cq/rncs", { params: { status: "aberta" } }),
                api.get("/cq/registros-analise", { params: { status: "reprovado" } }),
            ]);
            setRncs(Array.isArray(rncRes.data) ? rncRes.data : []);
            setRas(Array.isArray(raRes.data) ? raRes.data : []);
        } catch { /* optional */ }
    }, []);

    useEffect(() => { loadOrdens(); }, [loadOrdens]);
    useEffect(() => { loadRefs(); }, [loadRefs]);

    const setField = (k, v) => setForm(f => ({ ...f, [k]: v }));

    const onOrigemChange = (tipo) => {
        setForm(f => ({ ...f, origem_tipo: tipo, origem_id: "" }));
    };

    const onOrigemIdChange = (id) => {
        setField("origem_id", id);
        if (form.origem_tipo === "rnc") {
            const rnc = rncs.find(r => r.id === id);
            if (rnc && !form.produto_nome) {
                setField("produto_nome", rnc.produto_nome || rnc.lote_numero || "");
                if (!form.problema_descrito) setField("problema_descrito", rnc.descricao || "");
            }
        } else {
            const ra = ras.find(r => r.id === id);
            if (ra && !form.produto_nome) {
                setField("produto_nome", ra.item_nome || ra.produto_nome || "");
                setField("lote_numero", ra.lote_numero || "");
            }
        }
    };

    const handleCreate = async () => {
        if (!form.produto_nome.trim()) { toast.error("Informe o nome do produto"); return; }
        if (!form.problema_descrito.trim()) { toast.error("Descreva o problema identificado"); return; }
        setSaving(true);
        try {
            await api.post("/retrabalho/ordens", {
                origem_tipo: form.origem_tipo,
                origem_id: form.origem_id || null,
                lote_numero: form.lote_numero || null,
                produto_nome: form.produto_nome.trim(),
                problema_descrito: form.problema_descrito.trim(),
                instrucoes_retrabalho: form.instrucoes_retrabalho,
                responsavel_nome: form.responsavel_nome || null,
                data_limite: form.data_limite || null,
                observacoes: form.observacoes,
            });
            toast.success("Ordem de Retrabalho criada");
            setShowForm(false);
            setForm(emptyForm());
            loadOrdens();
        } catch (e) {
            toast.error(formatApiError(e));
        } finally {
            setSaving(false);
        }
    };

    const handleAdvanceStatus = async (rt) => {
        const next = NEXT_STATUS[rt.status];
        if (!next) return;
        if (next === "concluido") {
            setSelectedRT(rt);
            setObsConc("");
            setShowConcluir(true);
            return;
        }
        setActionLoading(true);
        try {
            await api.put(`/retrabalho/ordens/${rt.id}`, { status: next });
            toast.success(`Status atualizado: ${STATUS_CONFIG[next]?.label}`);
            loadOrdens();
            if (selectedRT?.id === rt.id) {
                const { data } = await api.get(`/retrabalho/ordens/${rt.id}`);
                setSelectedRT(data);
            }
        } catch (e) {
            toast.error(formatApiError(e));
        } finally {
            setActionLoading(false);
        }
    };

    const handleConcluir = async () => {
        if (!selectedRT) return;
        setActionLoading(true);
        try {
            await api.post(`/retrabalho/ordens/${selectedRT.id}/concluir`, {
                observacoes_conclusao: obsConc,
                criar_ra: true,
            });
            toast.success("Retrabalho concluído — nova RA criada para re-inspeção CQ");
            setShowConcluir(false);
            setSelectedRT(null);
            loadOrdens();
        } catch (e) {
            toast.error(formatApiError(e));
        } finally {
            setActionLoading(false);
        }
    };

    const handleCancel = async (rt) => {
        if (!window.confirm(`Cancelar ${rt.numero_rt}?`)) return;
        setActionLoading(true);
        try {
            await api.put(`/retrabalho/ordens/${rt.id}`, { status: "cancelado" });
            toast.success("Ordem cancelada");
            loadOrdens();
            if (selectedRT?.id === rt.id) setSelectedRT(null);
        } catch (e) {
            toast.error(formatApiError(e));
        } finally {
            setActionLoading(false);
        }
    };

    const openDetail = async (rt) => {
        setSelectedRT(rt);
    };

    const reloadDetail = async (id) => {
        try {
            const { data } = await api.get(`/retrabalho/ordens/${id}`);
            setSelectedRT(data);
        } catch { /* ignore */ }
    };

    const counts = {
        total: ordens.length,
        pendente: ordens.filter(o => o.status === "pendente").length,
        em_retrabalho: ordens.filter(o => o.status === "em_retrabalho").length,
        concluido: ordens.filter(o => o.status === "concluido").length,
    };

    return (
        <div className="h-full overflow-auto">
            <div className="max-w-6xl mx-auto p-6 space-y-5">
                {/* Header */}
                <div className="flex items-start justify-between gap-4 flex-wrap">
                    <div>
                        <h1 className="text-2xl font-heading font-semibold tracking-tight flex items-center gap-2">
                            <RotateCcw className="h-6 w-6" />
                            Retrabalho
                        </h1>
                        <p className="text-sm text-muted-foreground mt-1">
                            Lotes reprovados no CQ → reprocessamento → re-inspeção automática
                        </p>
                    </div>
                    <Button onClick={() => { setForm(emptyForm()); setShowForm(true); }} data-testid="btn-nova-rt">
                        <Plus className="h-4 w-4 mr-1" /> Nova Ordem
                    </Button>
                </div>

                {/* Mini stats */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    {[
                        { label: "Total", value: counts.total, cls: "text-foreground" },
                        { label: "Pendentes", value: counts.pendente, cls: "text-slate-600" },
                        { label: "Em Retrabalho", value: counts.em_retrabalho, cls: "text-amber-600" },
                        { label: "Aguard. CQ", value: counts.concluido, cls: "text-blue-600" },
                    ].map(s => (
                        <Card key={s.label}>
                            <CardContent className="p-3">
                                <div className="text-[11px] text-muted-foreground uppercase tracking-wider">{s.label}</div>
                                <div className={`text-2xl font-bold mt-0.5 ${s.cls}`}>{s.value}</div>
                            </CardContent>
                        </Card>
                    ))}
                </div>

                {/* Filters */}
                <div className="flex gap-2 items-center flex-wrap">
                    <div className="relative flex-1 min-w-[240px]">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                        <Input
                            placeholder="Buscar RT, produto, lote…"
                            value={search}
                            onChange={e => setSearch(e.target.value)}
                            className="pl-9"
                        />
                    </div>
                    <Select value={statusFilter} onValueChange={setStatusFilter}>
                        <SelectTrigger className="w-48">
                            <SelectValue />
                        </SelectTrigger>
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
                    <Card className="border-dashed">
                        <CardContent className="py-16 text-center">
                            <RotateCcw className="h-14 w-14 mx-auto mb-4 text-muted-foreground/30" />
                            <h3 className="text-lg font-semibold mb-1">Nenhuma ordem de retrabalho</h3>
                            <p className="text-sm text-muted-foreground">
                                Crie uma ordem quando um lote for reprovado pelo CQ e precisar de reprocessamento.
                            </p>
                        </CardContent>
                    </Card>
                ) : (
                    <div className="space-y-2">
                        {ordens.map(rt => (
                            <Card
                                key={rt.id}
                                className="hover:border-primary/40 hover:shadow-sm transition-all cursor-pointer group"
                                onClick={() => openDetail(rt)}
                                data-testid={`rt-card-${rt.id}`}
                            >
                                <CardContent className="p-4">
                                    <div className="flex items-start justify-between gap-4">
                                        <div className="flex-1 min-w-0 space-y-1.5">
                                            <div className="flex items-center gap-2 flex-wrap">
                                                <span className="font-mono text-sm font-bold text-primary">{rt.numero_rt}</span>
                                                <StatusBadge status={rt.status} />
                                                {rt.origem_tipo === "rnc" && rt.rnc_numero && (
                                                    <Badge variant="outline" className="text-[10px]">RNC {rt.rnc_numero}</Badge>
                                                )}
                                                {rt.origem_tipo === "ra" && rt.ra_numero && (
                                                    <Badge variant="outline" className="text-[10px]">RA {rt.ra_numero}</Badge>
                                                )}
                                            </div>
                                            <h3 className="font-semibold text-sm">{rt.produto_nome}</h3>
                                            <p className="text-xs text-muted-foreground line-clamp-1">{rt.problema_descrito}</p>
                                            <div className="flex items-center gap-4 text-xs text-muted-foreground flex-wrap">
                                                {rt.lote_numero && <span>Lote: {rt.lote_numero}</span>}
                                                <span className="flex items-center gap-1">
                                                    <User className="h-3 w-3" />{rt.responsavel_nome}
                                                </span>
                                                {rt.data_limite && (
                                                    <span className="flex items-center gap-1">
                                                        <Calendar className="h-3 w-3" />Prazo: {formatDate(rt.data_limite)}
                                                    </span>
                                                )}
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-2 shrink-0">
                                            {NEXT_STATUS[rt.status] && (
                                                <Button
                                                    size="sm"
                                                    variant="outline"
                                                    className="h-8 text-xs"
                                                    disabled={actionLoading}
                                                    onClick={e => { e.stopPropagation(); handleAdvanceStatus(rt); }}
                                                >
                                                    {NEXT_STATUS_LABEL[rt.status]}
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
            {selectedRT && !showConcluir && (
                <Dialog open onOpenChange={() => setSelectedRT(null)}>
                    <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
                        <DialogHeader>
                            <DialogTitle className="flex items-center gap-2">
                                <RotateCcw className="h-5 w-5" />
                                {selectedRT.numero_rt} — {selectedRT.produto_nome}
                            </DialogTitle>
                        </DialogHeader>
                        <div className="space-y-4 text-sm">
                            <div className="flex items-center gap-3 flex-wrap">
                                <StatusBadge status={selectedRT.status} />
                                {selectedRT.data_limite && (
                                    <span className="text-xs text-muted-foreground flex items-center gap-1">
                                        <Calendar className="h-3.5 w-3.5" />Prazo: {formatDate(selectedRT.data_limite)}
                                    </span>
                                )}
                            </div>

                            <div className="grid grid-cols-2 gap-3 text-sm">
                                <div><span className="text-muted-foreground">Responsável:</span> {selectedRT.responsavel_nome || "—"}</div>
                                <div><span className="text-muted-foreground">Lote:</span> {selectedRT.lote_numero || "—"}</div>
                                {selectedRT.rnc_numero && <div><span className="text-muted-foreground">RNC:</span> {selectedRT.rnc_numero}</div>}
                                {selectedRT.ra_numero && <div><span className="text-muted-foreground">RA:</span> {selectedRT.ra_numero}</div>}
                            </div>

                            <div>
                                <p className="text-xs text-muted-foreground uppercase tracking-wider font-semibold mb-1">Problema Identificado</p>
                                <p className="bg-muted/40 rounded-lg p-3 text-sm">{selectedRT.problema_descrito}</p>
                            </div>

                            {selectedRT.instrucoes_retrabalho && (
                                <div>
                                    <p className="text-xs text-muted-foreground uppercase tracking-wider font-semibold mb-1">Instruções de Retrabalho</p>
                                    <p className="bg-muted/40 rounded-lg p-3 text-sm whitespace-pre-wrap">{selectedRT.instrucoes_retrabalho}</p>
                                </div>
                            )}

                            {selectedRT.nova_ra_id && (
                                <div className="rounded-lg border border-blue-300 bg-blue-50 dark:bg-blue-950/30 dark:border-blue-800 p-3">
                                    <p className="text-xs font-semibold text-blue-700 dark:text-blue-300 mb-1">Re-inspeção CQ criada</p>
                                    <p className="text-xs text-blue-600 dark:text-blue-400">RA {selectedRT.nova_ra_numero} — aguardando análise do CQ</p>
                                    <Button
                                        size="sm" variant="outline"
                                        className="mt-2 h-7 text-xs"
                                        onClick={() => navigate(`/cq/registros-analise/${selectedRT.nova_ra_id}`)}
                                    >
                                        Ver RA <ChevronRight className="h-3 w-3 ml-1" />
                                    </Button>
                                </div>
                            )}

                            {(selectedRT.historico || []).length > 0 && (
                                <>
                                    <Separator />
                                    <div>
                                        <p className="text-xs text-muted-foreground uppercase tracking-wider font-semibold mb-2">Histórico</p>
                                        <div className="space-y-1.5">
                                            {selectedRT.historico.map((h, i) => (
                                                <div key={i} className="text-xs flex items-center gap-2 text-muted-foreground">
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
                                {NEXT_STATUS[selectedRT.status] && (
                                    <Button
                                        size="sm"
                                        disabled={actionLoading}
                                        onClick={() => handleAdvanceStatus(selectedRT)}
                                    >
                                        {actionLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                                        {NEXT_STATUS_LABEL[selectedRT.status]}
                                    </Button>
                                )}
                                {["pendente", "em_retrabalho"].includes(selectedRT.status) && (
                                    <Button
                                        size="sm"
                                        variant="outline"
                                        className="text-destructive border-destructive/30 hover:text-destructive"
                                        disabled={actionLoading}
                                        onClick={() => handleCancel(selectedRT)}
                                    >
                                        Cancelar RT
                                    </Button>
                                )}
                            </div>
                            <Button variant="outline" onClick={() => setSelectedRT(null)}>Fechar</Button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>
            )}

            {/* Concluir dialog */}
            {showConcluir && selectedRT && (
                <Dialog open onOpenChange={() => setShowConcluir(false)}>
                    <DialogContent>
                        <DialogHeader>
                            <DialogTitle>Concluir Retrabalho — {selectedRT.numero_rt}</DialogTitle>
                        </DialogHeader>
                        <div className="space-y-4">
                            <div className="rounded-lg border border-amber-300 bg-amber-50 dark:bg-amber-950/30 dark:border-amber-800 p-3 text-xs flex items-start gap-2">
                                <AlertTriangle className="h-4 w-4 text-amber-600 shrink-0 mt-0.5" />
                                <span>Uma nova <strong>RA (Registro de Análise)</strong> será criada automaticamente para re-inspeção do lote pelo CQ.</span>
                            </div>
                            <div>
                                <Label>Observações da Conclusão</Label>
                                <Textarea
                                    value={obsConc}
                                    onChange={e => setObsConc(e.target.value)}
                                    placeholder="Descreva o que foi realizado no retrabalho…"
                                    className="mt-1"
                                    rows={4}
                                />
                            </div>
                        </div>
                        <DialogFooter>
                            <Button variant="outline" onClick={() => setShowConcluir(false)} disabled={actionLoading}>Voltar</Button>
                            <Button onClick={handleConcluir} disabled={actionLoading}>
                                {actionLoading ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <RotateCcw className="h-4 w-4 mr-1" />}
                                Confirmar Conclusão
                            </Button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>
            )}

            {/* New RT Form */}
            <Dialog open={showForm} onOpenChange={v => { if (!v) setShowForm(false); }}>
                <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
                    <DialogHeader>
                        <DialogTitle>Nova Ordem de Retrabalho</DialogTitle>
                    </DialogHeader>
                    <div className="space-y-4">
                        {/* Source */}
                        <div className="grid grid-cols-2 gap-3">
                            <div>
                                <Label>Origem</Label>
                                <Select value={form.origem_tipo} onValueChange={onOrigemChange}>
                                    <SelectTrigger className="mt-1">
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="rnc">RNC (Não-Conformidade)</SelectItem>
                                        <SelectItem value="ra">RA (Registro de Análise)</SelectItem>
                                        <SelectItem value="manual">Manual (sem origem)</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                            {form.origem_tipo === "rnc" && rncs.length > 0 && (
                                <div>
                                    <Label>RNC</Label>
                                    <Select value={form.origem_id} onValueChange={onOrigemIdChange}>
                                        <SelectTrigger className="mt-1">
                                            <SelectValue placeholder="Selecionar RNC…" />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {rncs.map(r => (
                                                <SelectItem key={r.id} value={r.id}>
                                                    {r.numero_rnc || r.id.slice(-6)} — {(r.descricao || "").slice(0, 40)}
                                                </SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>
                            )}
                            {form.origem_tipo === "ra" && ras.length > 0 && (
                                <div>
                                    <Label>RA Reprovada</Label>
                                    <Select value={form.origem_id} onValueChange={onOrigemIdChange}>
                                        <SelectTrigger className="mt-1">
                                            <SelectValue placeholder="Selecionar RA…" />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {ras.map(r => (
                                                <SelectItem key={r.id} value={r.id}>
                                                    {r.numero_ra || r.id.slice(-6)} — {r.item_nome || r.produto_nome || ""}
                                                </SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>
                            )}
                        </div>

                        <div className="grid grid-cols-2 gap-3">
                            <div>
                                <Label>Produto / Material *</Label>
                                <Input
                                    value={form.produto_nome}
                                    onChange={e => setField("produto_nome", e.target.value)}
                                    placeholder="Nome do produto ou matéria-prima"
                                    className="mt-1"
                                />
                            </div>
                            <div>
                                <Label>Nº do Lote</Label>
                                <Input
                                    value={form.lote_numero}
                                    onChange={e => setField("lote_numero", e.target.value)}
                                    placeholder="Opcional"
                                    className="mt-1"
                                />
                            </div>
                        </div>

                        <div>
                            <Label>Problema Identificado *</Label>
                            <Textarea
                                value={form.problema_descrito}
                                onChange={e => setField("problema_descrito", e.target.value)}
                                placeholder="Descreva a não-conformidade que justifica o retrabalho…"
                                className="mt-1"
                                rows={3}
                            />
                        </div>

                        <div>
                            <Label>Instruções de Retrabalho</Label>
                            <Textarea
                                value={form.instrucoes_retrabalho}
                                onChange={e => setField("instrucoes_retrabalho", e.target.value)}
                                placeholder="Passo a passo do que deve ser feito…"
                                className="mt-1"
                                rows={3}
                            />
                        </div>

                        <div className="grid grid-cols-2 gap-3">
                            <div>
                                <Label>Responsável</Label>
                                <Input
                                    value={form.responsavel_nome}
                                    onChange={e => setField("responsavel_nome", e.target.value)}
                                    placeholder="Nome do responsável"
                                    className="mt-1"
                                />
                            </div>
                            <div>
                                <Label>Prazo</Label>
                                <Input
                                    type="date"
                                    value={form.data_limite}
                                    onChange={e => setField("data_limite", e.target.value)}
                                    className="mt-1"
                                />
                            </div>
                        </div>

                        <div>
                            <Label>Observações</Label>
                            <Input
                                value={form.observacoes}
                                onChange={e => setField("observacoes", e.target.value)}
                                placeholder="Opcional"
                                className="mt-1"
                            />
                        </div>
                    </div>
                    <DialogFooter className="mt-4">
                        <Button variant="outline" onClick={() => setShowForm(false)} disabled={saving}>Cancelar</Button>
                        <Button onClick={handleCreate} disabled={saving} data-testid="btn-salvar-rt">
                            {saving ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <RotateCcw className="h-4 w-4 mr-1" />}
                            Criar Ordem de Retrabalho
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
