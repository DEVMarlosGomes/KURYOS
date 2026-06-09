import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { formatApiError } from "@/lib/formatError";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
    Calendar, ChevronLeft, ChevronRight, Plus, Loader2, Settings,
    Factory, Play, CheckCircle2, XCircle, Clock, Wrench,
} from "lucide-react";

// ─── helpers ───────────────────────────────────────────────────────────
const DAYS_PT = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];
const MONTHS_PT = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"];

function startOfWeek(date) {
    const d = new Date(date);
    const day = d.getDay();
    d.setDate(d.getDate() - day + (day === 0 ? -6 : 1)); // start Monday
    d.setHours(0, 0, 0, 0);
    return d;
}

function addDays(date, n) {
    const d = new Date(date);
    d.setDate(d.getDate() + n);
    return d;
}

function toYMD(date) {
    return date.toISOString().slice(0, 10);
}

function formatDateBR(ymd) {
    if (!ymd) return "—";
    const [y, m, d] = ymd.split("-");
    return `${d}/${m}`;
}

// ─── status config ──────────────────────────────────────────────────────
const SLOT_STATUS = {
    planejado:    { label: "Planejado",    cls: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300", cellCls: "bg-slate-200/80 dark:bg-slate-700/80 border-slate-400" },
    em_execucao:  { label: "Em Execução",  cls: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300", cellCls: "bg-amber-200/80 dark:bg-amber-800/60 border-amber-500" },
    concluido:    { label: "Concluído",    cls: "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300", cellCls: "bg-green-200/80 dark:bg-green-800/60 border-green-500" },
    cancelado:    { label: "Cancelado",    cls: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300", cellCls: "bg-red-200/60 dark:bg-red-900/40 border-red-400" },
};

const NEXT_STATUS = {
    planejado:   { to: "em_execucao", label: "Iniciar", Icon: Play },
    em_execucao: { to: "concluido",   label: "Concluir", Icon: CheckCircle2 },
};

const TURNO_LABEL = { manha: "Manhã", tarde: "Tarde", noite: "Noite", integral: "Integral" };
const TIPO_LINHA_LABEL = { manipulacao: "Manipulação", embalagem: "Embalagem", rotulagem: "Rotulagem", envase: "Envase", geral: "Geral" };

function SlotBadge({ status }) {
    const cfg = SLOT_STATUS[status] || SLOT_STATUS.planejado;
    return <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium ${cfg.cls}`}>{cfg.label}</span>;
}

// ─── tabs ───────────────────────────────────────────────────────────────
const TABS = ["Programação", "OPs Pendentes", "Linhas"];

export default function PCPPage() {
    const [tab, setTab] = useState("Programação");
    const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date()));
    const [linhas, setLinhas] = useState([]);
    const [slots, setSlots] = useState([]);
    const [opsPendentes, setOpsPendentes] = useState([]);
    const [loadingSlots, setLoadingSlots] = useState(true);
    const [loadingOps, setLoadingOps] = useState(false);
    const [dashboard, setDashboard] = useState(null);

    // Dialogs
    const [showSchedule, setShowSchedule] = useState(false);
    const [scheduleOp, setScheduleOp] = useState(null);
    const [schedForm, setSchedForm] = useState({ linha_id: "", data_inicio: "", data_fim: "", turno: "integral", qtd_planejada: "", observacoes: "" });
    const [saving, setSaving] = useState(false);
    const [selectedSlot, setSelectedSlot] = useState(null);
    const [actionLoading, setActionLoading] = useState(false);
    const [showLinhaForm, setShowLinhaForm] = useState(false);
    const [editLinha, setEditLinha] = useState(null);
    const [linhaForm, setLinhaForm] = useState({ nome: "", codigo: "", tipo: "geral", capacidade_diaria: "", unidade_capacidade: "kg", setup_minutos: 30, observacoes: "" });

    const weekDays = Array.from({ length: 7 }, (_, i) => addDays(weekStart, i));

    const loadLinhas = useCallback(async () => {
        try {
            const { data } = await api.get("/pcp/linhas");
            setLinhas(data || []);
        } catch (e) { toast.error(formatApiError(e)); }
    }, []);

    const loadSlots = useCallback(async () => {
        setLoadingSlots(true);
        try {
            const { data } = await api.get("/pcp/programacao", {
                params: {
                    data_inicio: toYMD(weekStart),
                    data_fim: toYMD(addDays(weekStart, 6)),
                },
            });
            setSlots(data || []);
        } catch (e) { toast.error(formatApiError(e)); }
        finally { setLoadingSlots(false); }
    }, [weekStart]);

    const loadOpsPendentes = useCallback(async () => {
        setLoadingOps(true);
        try {
            const { data } = await api.get("/ops", { params: { status: "aberta" } });
            const ops = (data || []).filter(op => !op.pcp_slot_id);
            setOpsPendentes(ops);
        } catch (e) { toast.error(formatApiError(e)); }
        finally { setLoadingOps(false); }
    }, []);

    const loadDashboard = useCallback(async () => {
        try {
            const { data } = await api.get("/pcp/dashboard");
            setDashboard(data);
        } catch { /* optional */ }
    }, []);

    useEffect(() => { loadLinhas(); loadDashboard(); }, [loadLinhas, loadDashboard]);
    useEffect(() => { loadSlots(); }, [loadSlots]);
    useEffect(() => {
        if (tab === "OPs Pendentes") loadOpsPendentes();
    }, [tab, loadOpsPendentes]);

    // ── schedule op ───────────────────────────────────────────────────
    const openSchedule = (op) => {
        setScheduleOp(op);
        setSchedForm({
            linha_id: linhas[0]?.id || "",
            data_inicio: toYMD(new Date()),
            data_fim: toYMD(new Date()),
            turno: "integral",
            qtd_planejada: String((op.items?.[0]?.qtd_planejada) || ""),
            observacoes: "",
        });
        setShowSchedule(true);
    };

    const handleSchedule = async () => {
        if (!schedForm.linha_id || !schedForm.data_inicio) {
            toast.error("Selecione a linha e a data de início"); return;
        }
        setSaving(true);
        try {
            await api.post("/pcp/programacao", {
                op_id: scheduleOp.id,
                linha_id: schedForm.linha_id,
                data_inicio: schedForm.data_inicio,
                data_fim: schedForm.data_fim || schedForm.data_inicio,
                turno: schedForm.turno,
                qtd_planejada: Number(schedForm.qtd_planejada) || 0,
                observacoes: schedForm.observacoes,
            });
            toast.success("OP programada");
            setShowSchedule(false);
            loadSlots();
            loadOpsPendentes();
            loadDashboard();
        } catch (e) { toast.error(formatApiError(e)); }
        finally { setSaving(false); }
    };

    // ── slot advance ──────────────────────────────────────────────────
    const handleAdvance = async (slot) => {
        const next = NEXT_STATUS[slot.status];
        if (!next) return;
        setActionLoading(true);
        try {
            const updated = await api.put(`/pcp/programacao/${slot.id}`, { status: next.to });
            toast.success(`${next.label} — concluído`);
            loadSlots();
            loadDashboard();
            setSelectedSlot(updated.data);
        } catch (e) { toast.error(formatApiError(e)); }
        finally { setActionLoading(false); }
    };

    const handleCancelSlot = async (slot) => {
        if (!window.confirm(`Cancelar ${slot.numero_prog}?`)) return;
        setActionLoading(true);
        try {
            await api.put(`/pcp/programacao/${slot.id}`, { status: "cancelado" });
            toast.success("Programação cancelada");
            loadSlots();
            loadDashboard();
            setSelectedSlot(null);
        } catch (e) { toast.error(formatApiError(e)); }
        finally { setActionLoading(false); }
    };

    // ── linha CRUD ────────────────────────────────────────────────────
    const openLinhaForm = (linha = null) => {
        setEditLinha(linha);
        setLinhaForm(linha ? {
            nome: linha.nome, codigo: linha.codigo || "", tipo: linha.tipo || "geral",
            capacidade_diaria: String(linha.capacidade_diaria || ""), unidade_capacidade: linha.unidade_capacidade || "kg",
            setup_minutos: linha.setup_minutos || 30, observacoes: linha.observacoes || "",
        } : { nome: "", codigo: "", tipo: "geral", capacidade_diaria: "", unidade_capacidade: "kg", setup_minutos: 30, observacoes: "" });
        setShowLinhaForm(true);
    };

    const handleSaveLinha = async () => {
        if (!linhaForm.nome.trim()) { toast.error("Nome obrigatório"); return; }
        setSaving(true);
        try {
            const payload = {
                nome: linhaForm.nome.trim(),
                codigo: linhaForm.codigo,
                tipo: linhaForm.tipo,
                capacidade_diaria: Number(linhaForm.capacidade_diaria) || 0,
                unidade_capacidade: linhaForm.unidade_capacidade,
                setup_minutos: Number(linhaForm.setup_minutos) || 30,
                observacoes: linhaForm.observacoes,
            };
            if (editLinha) {
                await api.put(`/pcp/linhas/${editLinha.id}`, payload);
                toast.success("Linha atualizada");
            } else {
                await api.post("/pcp/linhas", payload);
                toast.success("Linha criada");
            }
            setShowLinhaForm(false);
            loadLinhas();
            loadDashboard();
        } catch (e) { toast.error(formatApiError(e)); }
        finally { setSaving(false); }
    };

    const handleToggleLinha = async (linha) => {
        try {
            await api.put(`/pcp/linhas/${linha.id}`, { status: linha.status === "ativa" ? "inativa" : "ativa" });
            toast.success(linha.status === "ativa" ? "Linha inativada" : "Linha ativada");
            loadLinhas();
        } catch (e) { toast.error(formatApiError(e)); }
    };

    // ── weekly grid ───────────────────────────────────────────────────
    const getSlotsForCell = (linhaId, ymd) =>
        slots.filter(s => s.linha_id === linhaId && s.data_inicio <= ymd && s.data_fim >= ymd);

    const activeLinhas = linhas.filter(l => l.status === "ativa");

    return (
        <div className="h-full overflow-auto">
            <div className="max-w-7xl mx-auto p-6 space-y-5">
                {/* Header */}
                <div className="flex items-start justify-between gap-4 flex-wrap">
                    <div>
                        <h1 className="text-2xl font-heading font-semibold tracking-tight flex items-center gap-2">
                            <Calendar className="h-6 w-6" />
                            PCP — Programação da Produção
                        </h1>
                        <p className="text-sm text-muted-foreground mt-1">
                            Alocação de OPs em linhas de produção
                        </p>
                    </div>
                </div>

                {/* Dashboard strip */}
                {dashboard && (
                    <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
                        {[
                            { label: "Linhas Ativas", value: dashboard.linhas_ativas, cls: "text-foreground" },
                            { label: "Planejados", value: dashboard.planejados, cls: "text-slate-600" },
                            { label: "Em Execução", value: dashboard.em_execucao, cls: "text-amber-600" },
                            { label: "Concluídos Hoje", value: dashboard.concluidos_hoje, cls: "text-green-600" },
                            { label: "OPs s/ PCP", value: dashboard.ops_sem_pcp, cls: "text-red-600" },
                        ].map(s => (
                            <Card key={s.label}><CardContent className="p-3">
                                <div className="text-[10px] text-muted-foreground uppercase tracking-wider">{s.label}</div>
                                <div className={`text-xl font-bold mt-0.5 ${s.cls}`}>{s.value}</div>
                            </CardContent></Card>
                        ))}
                    </div>
                )}

                {/* Tabs */}
                <div className="flex border-b border-border">
                    {TABS.map(t => (
                        <button key={t} onClick={() => setTab(t)}
                            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                                tab === t ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"
                            }`}>{t}</button>
                    ))}
                </div>

                {/* ── Tab: Programação ────────────────────────────────────── */}
                {tab === "Programação" && (
                    <div className="space-y-3">
                        <div className="flex items-center gap-3">
                            <Button variant="outline" size="icon" onClick={() => setWeekStart(w => addDays(w, -7))}>
                                <ChevronLeft className="h-4 w-4" />
                            </Button>
                            <span className="text-sm font-medium min-w-[200px] text-center">
                                {formatDateBR(toYMD(weekStart))} — {formatDateBR(toYMD(addDays(weekStart, 6)))} / {weekStart.getFullYear()}
                            </span>
                            <Button variant="outline" size="icon" onClick={() => setWeekStart(w => addDays(w, 7))}>
                                <ChevronRight className="h-4 w-4" />
                            </Button>
                            <Button variant="outline" size="sm" onClick={() => setWeekStart(startOfWeek(new Date()))}>
                                Hoje
                            </Button>
                        </div>

                        {loadingSlots ? (
                            <div className="flex justify-center py-20">
                                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                            </div>
                        ) : activeLinhas.length === 0 ? (
                            <Card className="border-dashed"><CardContent className="py-12 text-center">
                                <Wrench className="h-12 w-12 mx-auto mb-3 text-muted-foreground/30" />
                                <p className="font-semibold">Nenhuma linha de produção ativa</p>
                                <p className="text-sm text-muted-foreground mt-1">Crie linhas na aba "Linhas" primeiro.</p>
                                <Button className="mt-4" size="sm" onClick={() => setTab("Linhas")}>Gerenciar Linhas</Button>
                            </CardContent></Card>
                        ) : (
                            <div className="overflow-x-auto rounded-xl border border-border">
                                <table className="w-full text-xs border-collapse min-w-[700px]">
                                    <thead>
                                        <tr className="bg-muted/40">
                                            <th className="text-left px-3 py-2.5 font-semibold text-muted-foreground w-40 border-r border-border">
                                                Linha
                                            </th>
                                            {weekDays.map(d => {
                                                const ymd = toYMD(d);
                                                const isToday = ymd === toYMD(new Date());
                                                return (
                                                    <th key={ymd} className={`text-center px-2 py-2.5 font-semibold border-r border-border last:border-r-0 ${isToday ? "text-primary" : "text-muted-foreground"}`}>
                                                        <div>{DAYS_PT[d.getDay()]}</div>
                                                        <div className={`text-base font-bold ${isToday ? "text-primary" : "text-foreground"}`}>{d.getDate()}</div>
                                                    </th>
                                                );
                                            })}
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {activeLinhas.map((linha, li) => (
                                            <tr key={linha.id} className={`border-t border-border ${li % 2 === 0 ? "" : "bg-muted/10"}`}>
                                                <td className="px-3 py-2 border-r border-border font-medium">
                                                    <div className="font-semibold truncate">{linha.nome}</div>
                                                    <div className="text-muted-foreground text-[10px]">{TIPO_LINHA_LABEL[linha.tipo] || linha.tipo}</div>
                                                </td>
                                                {weekDays.map(d => {
                                                    const ymd = toYMD(d);
                                                    const cellSlots = getSlotsForCell(linha.id, ymd);
                                                    return (
                                                        <td key={ymd} className="px-1 py-1 border-r border-border last:border-r-0 min-h-[56px] align-top">
                                                            <div className="space-y-1 min-h-[48px]">
                                                                {cellSlots.map(slot => {
                                                                    const cfg = SLOT_STATUS[slot.status] || SLOT_STATUS.planejado;
                                                                    return (
                                                                        <div key={slot.id}
                                                                            className={`rounded border px-1.5 py-1 cursor-pointer hover:opacity-90 transition-opacity ${cfg.cellCls}`}
                                                                            onClick={() => setSelectedSlot(slot)}>
                                                                            <div className="font-bold text-[10px] truncate">{slot.numero_prog}</div>
                                                                            <div className="truncate text-[10px]">{slot.produto_nome || slot.op_numero}</div>
                                                                            <div className="text-[10px] opacity-70">{TURNO_LABEL[slot.turno] || slot.turno}</div>
                                                                        </div>
                                                                    );
                                                                })}
                                                            </div>
                                                        </td>
                                                    );
                                                })}
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        )}
                    </div>
                )}

                {/* ── Tab: OPs Pendentes ─────────────────────────────────── */}
                {tab === "OPs Pendentes" && (
                    <div className="space-y-2">
                        {loadingOps ? (
                            <div className="flex justify-center py-16">
                                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                            </div>
                        ) : opsPendentes.length === 0 ? (
                            <Card className="border-dashed"><CardContent className="py-12 text-center">
                                <CheckCircle2 className="h-12 w-12 mx-auto mb-3 text-green-500/40" />
                                <p className="font-semibold">Todas as OPs estão programadas</p>
                            </CardContent></Card>
                        ) : opsPendentes.map(op => (
                            <Card key={op.id} className="hover:border-primary/40 transition-colors">
                                <CardContent className="p-4 flex items-start justify-between gap-4">
                                    <div className="space-y-1 flex-1 min-w-0">
                                        <div className="flex items-center gap-2 flex-wrap">
                                            <span className="font-mono text-sm font-bold text-primary">{op.numero_op}</span>
                                            <Badge variant="outline" className="text-[10px]">{op.status}</Badge>
                                        </div>
                                        <p className="font-semibold text-sm">{op.cliente_nome || "—"}</p>
                                        <p className="text-xs text-muted-foreground">{op.project_name || (op.items?.[0]?.item) || "—"}</p>
                                        {op.items?.[0]?.qtd_planejada > 0 && (
                                            <p className="text-xs text-muted-foreground">Qtd planejada: {op.items[0].qtd_planejada}</p>
                                        )}
                                    </div>
                                    <Button size="sm" disabled={linhas.filter(l => l.status === "ativa").length === 0}
                                        onClick={() => openSchedule(op)}>
                                        <Calendar className="h-3.5 w-3.5 mr-1" />
                                        Programar
                                    </Button>
                                </CardContent>
                            </Card>
                        ))}
                    </div>
                )}

                {/* ── Tab: Linhas ────────────────────────────────────────── */}
                {tab === "Linhas" && (
                    <div className="space-y-3">
                        <div className="flex justify-end">
                            <Button onClick={() => openLinhaForm()}>
                                <Plus className="h-4 w-4 mr-1" /> Nova Linha
                            </Button>
                        </div>
                        {linhas.length === 0 ? (
                            <Card className="border-dashed"><CardContent className="py-12 text-center">
                                <Factory className="h-12 w-12 mx-auto mb-3 text-muted-foreground/30" />
                                <p className="font-semibold">Nenhuma linha cadastrada</p>
                            </CardContent></Card>
                        ) : (
                            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
                                {linhas.map(linha => (
                                    <Card key={linha.id} className={linha.status !== "ativa" ? "opacity-60" : ""}>
                                        <CardContent className="p-4 space-y-2">
                                            <div className="flex items-start justify-between gap-2">
                                                <div>
                                                    <p className="font-semibold">{linha.nome}</p>
                                                    {linha.codigo && <p className="text-xs text-muted-foreground font-mono">{linha.codigo}</p>}
                                                </div>
                                                <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium ${linha.status === "ativa" ? "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300" : "bg-red-100 text-red-700"}`}>
                                                    {linha.status === "ativa" ? "Ativa" : "Inativa"}
                                                </span>
                                            </div>
                                            <div className="text-xs text-muted-foreground space-y-0.5">
                                                <div>{TIPO_LINHA_LABEL[linha.tipo] || linha.tipo}</div>
                                                {linha.capacidade_diaria > 0 && (
                                                    <div>Cap: {linha.capacidade_diaria} {linha.unidade_capacidade}/dia</div>
                                                )}
                                                <div className="flex items-center gap-1">
                                                    <Clock className="h-3 w-3" />Setup: {linha.setup_minutos} min
                                                </div>
                                            </div>
                                            <div className="flex gap-1.5 pt-1">
                                                <Button variant="outline" size="sm" className="flex-1 h-7 text-xs"
                                                    onClick={() => openLinhaForm(linha)}>
                                                    <Settings className="h-3 w-3 mr-1" />Editar
                                                </Button>
                                                <Button variant="outline" size="sm" className="flex-1 h-7 text-xs"
                                                    onClick={() => handleToggleLinha(linha)}>
                                                    {linha.status === "ativa" ? "Inativar" : "Ativar"}
                                                </Button>
                                            </div>
                                        </CardContent>
                                    </Card>
                                ))}
                            </div>
                        )}
                    </div>
                )}
            </div>

            {/* ── Slot detail dialog ─────────────────────────────────────────── */}
            {selectedSlot && (
                <Dialog open onOpenChange={() => setSelectedSlot(null)}>
                    <DialogContent className="max-w-lg">
                        <DialogHeader>
                            <DialogTitle className="flex items-center gap-2">
                                <Calendar className="h-5 w-5" />{selectedSlot.numero_prog}
                            </DialogTitle>
                        </DialogHeader>
                        <div className="space-y-3 text-sm">
                            <div className="flex items-center gap-2 flex-wrap">
                                <SlotBadge status={selectedSlot.status} />
                                <span className="text-xs text-muted-foreground">{TURNO_LABEL[selectedSlot.turno] || selectedSlot.turno}</span>
                            </div>
                            <div className="grid grid-cols-2 gap-3">
                                <div><span className="text-muted-foreground">OP:</span> <span className="font-mono">{selectedSlot.op_numero || "—"}</span></div>
                                <div><span className="text-muted-foreground">Linha:</span> {selectedSlot.linha_nome}</div>
                                <div><span className="text-muted-foreground">Produto:</span> {selectedSlot.produto_nome || "—"}</div>
                                <div><span className="text-muted-foreground">Cliente:</span> {selectedSlot.cliente_nome || "—"}</div>
                                <div><span className="text-muted-foreground">Início:</span> {formatDateBR(selectedSlot.data_inicio)}</div>
                                <div><span className="text-muted-foreground">Fim:</span> {formatDateBR(selectedSlot.data_fim)}</div>
                                <div><span className="text-muted-foreground">Qtd Plan.:</span> {selectedSlot.qtd_planejada}</div>
                                <div><span className="text-muted-foreground">Qtd Prod.:</span> {selectedSlot.qtd_produzida}</div>
                            </div>
                            {selectedSlot.observacoes && (
                                <p className="text-xs text-muted-foreground border-t border-border pt-2">{selectedSlot.observacoes}</p>
                            )}
                            {(selectedSlot.historico || []).length > 0 && (
                                <>
                                    <Separator />
                                    <div>
                                        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1.5">Histórico</p>
                                        {selectedSlot.historico.map((h, i) => (
                                            <div key={i} className="text-xs text-muted-foreground flex gap-2">
                                                <span>{new Date(h.em).toLocaleString("pt-BR")}</span>
                                                <span>·</span>
                                                <span>{h.de ? `${SLOT_STATUS[h.de]?.label || h.de} → ${SLOT_STATUS[h.para]?.label || h.para}` : "Criado"}</span>
                                                <span>· {h.por}</span>
                                            </div>
                                        ))}
                                    </div>
                                </>
                            )}
                        </div>
                        <DialogFooter className="flex flex-wrap gap-2 justify-between">
                            <div className="flex gap-2 flex-wrap">
                                {NEXT_STATUS[selectedSlot.status] && (() => {
                                    const n = NEXT_STATUS[selectedSlot.status];
                                    return (
                                        <Button size="sm" disabled={actionLoading} onClick={() => handleAdvance(selectedSlot)}>
                                            {actionLoading ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <n.Icon className="h-4 w-4 mr-1" />}
                                            {n.label}
                                        </Button>
                                    );
                                })()}
                                {["planejado", "em_execucao"].includes(selectedSlot.status) && (
                                    <Button size="sm" variant="outline"
                                        className="text-destructive border-destructive/30 hover:text-destructive"
                                        disabled={actionLoading}
                                        onClick={() => handleCancelSlot(selectedSlot)}>
                                        <XCircle className="h-4 w-4 mr-1" />Cancelar
                                    </Button>
                                )}
                            </div>
                            <Button variant="outline" onClick={() => setSelectedSlot(null)}>Fechar</Button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>
            )}

            {/* ── Schedule dialog ──────────────────────────────────────────── */}
            {showSchedule && scheduleOp && (
                <Dialog open onOpenChange={() => setShowSchedule(false)}>
                    <DialogContent className="max-w-md">
                        <DialogHeader>
                            <DialogTitle>Programar OP — {scheduleOp.numero_op}</DialogTitle>
                        </DialogHeader>
                        <div className="space-y-3 text-sm">
                            <p className="text-muted-foreground">{scheduleOp.cliente_nome} · {scheduleOp.items?.[0]?.item || scheduleOp.project_name || "—"}</p>
                            <div>
                                <Label>Linha de Produção *</Label>
                                <Select value={schedForm.linha_id}
                                    onValueChange={v => setSchedForm(f => ({ ...f, linha_id: v }))}>
                                    <SelectTrigger className="mt-1"><SelectValue placeholder="Selecionar linha…" /></SelectTrigger>
                                    <SelectContent>
                                        {linhas.filter(l => l.status === "ativa").map(l => (
                                            <SelectItem key={l.id} value={l.id}>{l.nome} ({TIPO_LINHA_LABEL[l.tipo] || l.tipo})</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <Label>Data Início *</Label>
                                    <Input type="date" value={schedForm.data_inicio}
                                        onChange={e => setSchedForm(f => ({ ...f, data_inicio: e.target.value }))} className="mt-1" />
                                </div>
                                <div>
                                    <Label>Data Fim</Label>
                                    <Input type="date" value={schedForm.data_fim}
                                        onChange={e => setSchedForm(f => ({ ...f, data_fim: e.target.value }))} className="mt-1" />
                                </div>
                            </div>
                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <Label>Turno</Label>
                                    <Select value={schedForm.turno} onValueChange={v => setSchedForm(f => ({ ...f, turno: v }))}>
                                        <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                                        <SelectContent>
                                            {Object.entries(TURNO_LABEL).map(([k, v]) => (
                                                <SelectItem key={k} value={k}>{v}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>
                                <div>
                                    <Label>Qtd Planejada</Label>
                                    <Input type="number" value={schedForm.qtd_planejada}
                                        onChange={e => setSchedForm(f => ({ ...f, qtd_planejada: e.target.value }))}
                                        placeholder="0" className="mt-1" />
                                </div>
                            </div>
                            <div>
                                <Label>Observações</Label>
                                <Input value={schedForm.observacoes}
                                    onChange={e => setSchedForm(f => ({ ...f, observacoes: e.target.value }))}
                                    placeholder="Opcional" className="mt-1" />
                            </div>
                        </div>
                        <DialogFooter>
                            <Button variant="outline" onClick={() => setShowSchedule(false)} disabled={saving}>Cancelar</Button>
                            <Button onClick={handleSchedule} disabled={saving}>
                                {saving ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Calendar className="h-4 w-4 mr-1" />}
                                Confirmar Programação
                            </Button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>
            )}

            {/* ── Linha form ───────────────────────────────────────────────── */}
            <Dialog open={showLinhaForm} onOpenChange={v => { if (!v) setShowLinhaForm(false); }}>
                <DialogContent className="max-w-md">
                    <DialogHeader>
                        <DialogTitle>{editLinha ? "Editar Linha" : "Nova Linha de Produção"}</DialogTitle>
                    </DialogHeader>
                    <div className="space-y-3">
                        <div className="grid grid-cols-2 gap-3">
                            <div>
                                <Label>Nome *</Label>
                                <Input value={linhaForm.nome}
                                    onChange={e => setLinhaForm(f => ({ ...f, nome: e.target.value }))}
                                    placeholder="Ex: Linha 01" className="mt-1" />
                            </div>
                            <div>
                                <Label>Código</Label>
                                <Input value={linhaForm.codigo}
                                    onChange={e => setLinhaForm(f => ({ ...f, codigo: e.target.value }))}
                                    placeholder="L01" className="mt-1" />
                            </div>
                        </div>
                        <div>
                            <Label>Tipo</Label>
                            <Select value={linhaForm.tipo} onValueChange={v => setLinhaForm(f => ({ ...f, tipo: v }))}>
                                <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    {Object.entries(TIPO_LINHA_LABEL).map(([k, v]) => (
                                        <SelectItem key={k} value={k}>{v}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                        <div className="grid grid-cols-2 gap-3">
                            <div>
                                <Label>Cap. Diária</Label>
                                <Input type="number" value={linhaForm.capacidade_diaria}
                                    onChange={e => setLinhaForm(f => ({ ...f, capacidade_diaria: e.target.value }))}
                                    placeholder="0" className="mt-1" />
                            </div>
                            <div>
                                <Label>Unidade</Label>
                                <Select value={linhaForm.unidade_capacidade}
                                    onValueChange={v => setLinhaForm(f => ({ ...f, unidade_capacidade: v }))}>
                                    <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                        {["kg", "L", "un", "cx", "lotes"].map(u => <SelectItem key={u} value={u}>{u}</SelectItem>)}
                                    </SelectContent>
                                </Select>
                            </div>
                        </div>
                        <div>
                            <Label>Setup (minutos)</Label>
                            <Input type="number" value={linhaForm.setup_minutos}
                                onChange={e => setLinhaForm(f => ({ ...f, setup_minutos: e.target.value }))}
                                className="mt-1" />
                        </div>
                        <div>
                            <Label>Observações</Label>
                            <Input value={linhaForm.observacoes}
                                onChange={e => setLinhaForm(f => ({ ...f, observacoes: e.target.value }))}
                                placeholder="Opcional" className="mt-1" />
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setShowLinhaForm(false)} disabled={saving}>Cancelar</Button>
                        <Button onClick={handleSaveLinha} disabled={saving}>
                            {saving ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Factory className="h-4 w-4 mr-1" />}
                            {editLinha ? "Salvar" : "Criar Linha"}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
