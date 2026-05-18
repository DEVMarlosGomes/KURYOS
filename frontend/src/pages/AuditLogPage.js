import { useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
    Activity,
    ArrowRight,
    CheckCircle2,
    ChevronDown,
    ChevronUp,
    Clock3,
    Copy,
    Filter,
    History,
    Pencil,
    Plus,
    RefreshCw,
    RotateCcw,
    Search,
    ShieldCheck,
    Tag,
    Trash2,
    User,
    Wand2,
    Zap,
} from "lucide-react";
import { toast } from "sonner";
import { formatApiError } from "@/lib/formatError";

const ENTITY_LABEL = {
    client: "Cliente",
    project: "Projeto",
    sample: "Amostra",
    variacao: "Variação",
    pd_card: "Card P&D",
    sku: "SKU",
    workflow_task: "Tarefa",
    tenant: "Tenant",
};

const ACTION_ICON = {
    client_created: Plus,
    client_moved: ArrowRight,
    project_created: Plus,
    project_moved: ArrowRight,
    sample_created: Plus,
    sample_moved: ArrowRight,
    sample_rework_created: RotateCcw,
    variacao_moved: ArrowRight,
    pd_card_auto_created: Wand2,
    pd_card_moved: ArrowRight,
    task_created: Plus,
    task_completed: CheckCircle2,
    task_updated: Pencil,
    task_deleted: Trash2,
    tenant_data_reset: RotateCcw,
};

const ACTION_STYLE = {
    client_created:       { badge: "bg-emerald-500/10 text-emerald-300 border-emerald-500/20", node: "border-emerald-500/40 bg-emerald-500/10", icon: "text-emerald-400", accent: "bg-emerald-500", glow: "0 0 0 1px rgba(34,197,94,0.08), 0 8px 32px rgba(34,197,94,0.05)" },
    client_moved:         { badge: "bg-sky-500/10 text-sky-300 border-sky-500/20", node: "border-sky-500/40 bg-sky-500/10", icon: "text-sky-400", accent: "bg-sky-500", glow: "0 0 0 1px rgba(14,165,233,0.08), 0 8px 32px rgba(14,165,233,0.05)" },
    project_created:      { badge: "bg-emerald-500/10 text-emerald-300 border-emerald-500/20", node: "border-emerald-500/40 bg-emerald-500/10", icon: "text-emerald-400", accent: "bg-emerald-500", glow: "0 0 0 1px rgba(34,197,94,0.08), 0 8px 32px rgba(34,197,94,0.05)" },
    project_moved:        { badge: "bg-sky-500/10 text-sky-300 border-sky-500/20", node: "border-sky-500/40 bg-sky-500/10", icon: "text-sky-400", accent: "bg-sky-500", glow: "0 0 0 1px rgba(14,165,233,0.08), 0 8px 32px rgba(14,165,233,0.05)" },
    sample_created:       { badge: "bg-emerald-500/10 text-emerald-300 border-emerald-500/20", node: "border-emerald-500/40 bg-emerald-500/10", icon: "text-emerald-400", accent: "bg-emerald-500", glow: "0 0 0 1px rgba(34,197,94,0.08), 0 8px 32px rgba(34,197,94,0.05)" },
    sample_moved:         { badge: "bg-sky-500/10 text-sky-300 border-sky-500/20", node: "border-sky-500/40 bg-sky-500/10", icon: "text-sky-400", accent: "bg-sky-500", glow: "0 0 0 1px rgba(14,165,233,0.08), 0 8px 32px rgba(14,165,233,0.05)" },
    sample_rework_created:{ badge: "bg-amber-500/10 text-amber-300 border-amber-500/20", node: "border-amber-500/40 bg-amber-500/10", icon: "text-amber-400", accent: "bg-amber-500", glow: "0 0 0 1px rgba(245,158,11,0.08), 0 8px 32px rgba(245,158,11,0.05)" },
    variacao_moved:       { badge: "bg-sky-500/10 text-sky-300 border-sky-500/20", node: "border-sky-500/40 bg-sky-500/10", icon: "text-sky-400", accent: "bg-sky-500", glow: "0 0 0 1px rgba(14,165,233,0.08), 0 8px 32px rgba(14,165,233,0.05)" },
    pd_card_auto_created: { badge: "bg-fuchsia-500/10 text-fuchsia-300 border-fuchsia-500/20", node: "border-fuchsia-500/40 bg-fuchsia-500/10", icon: "text-fuchsia-400", accent: "bg-fuchsia-500", glow: "0 0 0 1px rgba(217,70,239,0.08), 0 8px 32px rgba(217,70,239,0.05)" },
    pd_card_moved:        { badge: "bg-sky-500/10 text-sky-300 border-sky-500/20", node: "border-sky-500/40 bg-sky-500/10", icon: "text-sky-400", accent: "bg-sky-500", glow: "0 0 0 1px rgba(14,165,233,0.08), 0 8px 32px rgba(14,165,233,0.05)" },
    task_created:         { badge: "bg-cyan-500/10 text-cyan-300 border-cyan-500/20", node: "border-cyan-500/40 bg-cyan-500/10", icon: "text-cyan-400", accent: "bg-cyan-500", glow: "0 0 0 1px rgba(6,182,212,0.08), 0 8px 32px rgba(6,182,212,0.05)" },
    task_completed:       { badge: "bg-emerald-500/10 text-emerald-300 border-emerald-500/20", node: "border-emerald-500/40 bg-emerald-500/10", icon: "text-emerald-400", accent: "bg-emerald-500", glow: "0 0 0 1px rgba(34,197,94,0.08), 0 8px 32px rgba(34,197,94,0.05)" },
    task_updated:         { badge: "bg-slate-500/10 text-slate-300 border-slate-500/20", node: "border-slate-500/40 bg-slate-500/10", icon: "text-slate-400", accent: "bg-slate-400", glow: "0 0 0 1px rgba(148,163,184,0.08), 0 8px 32px rgba(148,163,184,0.04)" },
    task_deleted:         { badge: "bg-rose-500/10 text-rose-300 border-rose-500/20", node: "border-rose-500/40 bg-rose-500/10", icon: "text-rose-400", accent: "bg-rose-500", glow: "0 0 0 1px rgba(244,63,94,0.08), 0 8px 32px rgba(244,63,94,0.05)" },
    tenant_data_reset:    { badge: "bg-rose-500/10 text-rose-300 border-rose-500/20", node: "border-rose-600/40 bg-rose-600/10", icon: "text-rose-400", accent: "bg-rose-600", glow: "0 0 0 1px rgba(220,38,38,0.1), 0 8px 32px rgba(220,38,38,0.06)" },
};

const DEFAULT_STYLE = {
    badge: "bg-slate-500/10 text-slate-300 border-slate-500/20",
    node: "border-slate-500/40 bg-slate-500/10",
    icon: "text-slate-400",
    accent: "bg-slate-500",
    glow: "0 0 0 1px rgba(255,255,255,0.04), 0 4px 20px rgba(0,0,0,0.12)",
};

function prettifyAction(action) {
    if (!action) return "Ação desconhecida";
    return action.replace(/_/g, " ");
}

function shortId(value) {
    if (!value) return "Sem ID";
    return value.length > 16 ? `${value.slice(0, 8)}...${value.slice(-4)}` : value;
}

function formatTimestamp(ts) {
    if (!ts) return ["", ""];
    const d = new Date(ts);
    return [
        d.toLocaleDateString("pt-BR"),
        d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
    ];
}

function computeDiff(before, after) {
    if (!before && !after) return [];
    const b = before || {};
    const a = after || {};
    const allKeys = Array.from(new Set([...Object.keys(b), ...Object.keys(a)]));

    const rows = allKeys.map((key) => {
        const bVal = b[key];
        const aVal = a[key];
        if (!(key in b)) return { key, type: "added", after: aVal };
        if (!(key in a)) return { key, type: "removed", before: bVal };
        if (JSON.stringify(bVal) !== JSON.stringify(aVal)) return { key, type: "changed", before: bVal, after: aVal };
        return { key, type: "unchanged", value: bVal };
    });

    const order = { changed: 0, added: 1, removed: 2, unchanged: 3 };
    return rows.sort((x, y) => order[x.type] - order[y.type]);
}

function formatValue(val) {
    if (val === null || val === undefined) return <span className="italic opacity-25">null</span>;
    if (typeof val === "boolean") return <span className={val ? "text-emerald-400" : "text-rose-400"}>{String(val)}</span>;
    if (typeof val === "number") return <span className="text-cyan-300">{val}</span>;
    if (typeof val === "string") {
        const display = val.length > 48 ? `${val.slice(0, 48)}…` : val;
        return <span title={val.length > 48 ? val : undefined}>{display}</span>;
    }
    const str = JSON.stringify(val);
    const display = str.length > 48 ? `${str.slice(0, 48)}…` : str;
    return <span className="opacity-50" title={str.length > 48 ? str : undefined}>{display}</span>;
}

function DiffRow({ item }) {
    const baseCell = "px-4 py-2 text-[11px] font-mono leading-relaxed";
    const keyCell = `${baseCell} text-white/40 font-medium whitespace-nowrap`;

    if (item.type === "unchanged") {
        return (
            <tr className="opacity-30 hover:opacity-60 transition-opacity duration-150">
                <td className={keyCell}>{item.key}</td>
                <td className={`${baseCell} text-white/60`}>{formatValue(item.value)}</td>
                <td className={`${baseCell} text-white/60`}>{formatValue(item.value)}</td>
            </tr>
        );
    }
    if (item.type === "added") {
        return (
            <tr className="bg-emerald-500/[0.04]">
                <td className={`${keyCell} text-emerald-400/60`}>{item.key}</td>
                <td className={`${baseCell} text-white/20 italic`}>—</td>
                <td className={`${baseCell} text-emerald-300`}>{formatValue(item.after)}</td>
            </tr>
        );
    }
    if (item.type === "removed") {
        return (
            <tr className="bg-rose-500/[0.04]">
                <td className={`${keyCell} text-rose-400/60`}>{item.key}</td>
                <td className={`${baseCell} text-rose-300`}>{formatValue(item.before)}</td>
                <td className={`${baseCell} text-white/20 italic`}>—</td>
            </tr>
        );
    }
    return (
        <tr className="bg-amber-500/[0.04]">
            <td className={`${keyCell} text-amber-400/60`}>{item.key}</td>
            <td className={`${baseCell} text-rose-300/70 line-through decoration-rose-500/40`}>{formatValue(item.before)}</td>
            <td className={`${baseCell} text-emerald-300`}>{formatValue(item.after)}</td>
        </tr>
    );
}

function AuditCard({ log, isLast }) {
    const [showUnchanged, setShowUnchanged] = useState(false);
    const style = ACTION_STYLE[log.action] || DEFAULT_STYLE;
    const ActionIcon = ACTION_ICON[log.action] || Zap;
    const diff = useMemo(() => computeDiff(log.before, log.after), [log.before, log.after]);
    const [date, time] = formatTimestamp(log.timestamp);

    const changedRows = diff.filter((d) => d.type !== "unchanged");
    const unchangedRows = diff.filter((d) => d.type === "unchanged");
    const visibleDiff = showUnchanged ? diff : changedRows;
    const changedCount = changedRows.filter((d) => d.type === "changed").length;
    const addedCount = changedRows.filter((d) => d.type === "added").length;
    const removedCount = changedRows.filter((d) => d.type === "removed").length;

    function copyId() {
        if (!log.entity_id) return;
        navigator.clipboard.writeText(log.entity_id);
        toast.success("ID copiado para a área de transferência");
    }

    return (
        <div className="relative flex gap-5 group/row">
            <div className="flex flex-col items-center shrink-0 w-10">
                <div
                    className={`relative h-10 w-10 rounded-xl border-2 ${style.node} flex items-center justify-center z-10 transition-all duration-300 group-hover/row:scale-110 group-hover/row:shadow-lg`}
                    style={{ boxShadow: style.glow }}
                >
                    <ActionIcon className={`h-4 w-4 ${style.icon}`} />
                </div>
                {!isLast && (
                    <div className="flex-1 w-px bg-gradient-to-b from-white/10 via-white/[0.04] to-transparent mt-2" />
                )}
            </div>

            <div
                className="flex-1 mb-5 rounded-2xl border border-white/[0.07] bg-white/[0.025] backdrop-blur-sm overflow-hidden transition-all duration-300 hover:border-white/[0.11] hover:bg-white/[0.035]"
                style={{ boxShadow: style.glow }}
                data-testid={`audit-${log.id}`}
            >
                <div className="flex h-full">
                    <div className={`w-[3px] shrink-0 ${style.accent} opacity-60`} />

                    <div className="flex-1 min-w-0">
                        <div className="flex items-start justify-between gap-4 px-5 pt-5 pb-4 flex-wrap">
                            <div className="min-w-0 flex-1">
                                <div className="flex items-center gap-2.5 flex-wrap">
                                    <Badge className={`border text-[10px] px-2.5 py-0.5 tracking-[0.15em] uppercase font-semibold ${style.badge}`}>
                                        {prettifyAction(log.action)}
                                    </Badge>
                                    <span
                                        className="text-[15px] font-semibold tracking-tight text-white/90"
                                        data-testid={`audit-action-${log.id}`}
                                    >
                                        {ENTITY_LABEL[log.entity_type] || log.entity_type}
                                    </span>
                                    {(changedCount > 0 || addedCount > 0 || removedCount > 0) && (
                                        <span className="flex items-center gap-1.5 text-[11px] text-white/35">
                                            {changedCount > 0 && <span className="text-amber-400/70">{changedCount} alt.</span>}
                                            {addedCount > 0 && <span className="text-emerald-400/70">{addedCount} add.</span>}
                                            {removedCount > 0 && <span className="text-rose-400/70">{removedCount} rem.</span>}
                                        </span>
                                    )}
                                </div>

                                <div className="mt-3 flex items-center gap-2 flex-wrap">
                                    <button
                                        onClick={copyId}
                                        className="group/id inline-flex items-center gap-1.5 rounded-lg border border-white/[0.08] bg-white/[0.04] px-2.5 py-1 text-[11px] font-mono text-white/45 transition-all hover:border-white/15 hover:text-white/75 hover:bg-white/[0.07] cursor-pointer"
                                        title="Clique para copiar ID completo"
                                    >
                                        <Tag className="h-3 w-3 shrink-0" />
                                        {shortId(log.entity_id)}
                                        <Copy className="h-2.5 w-2.5 opacity-0 group-hover/id:opacity-50 transition-opacity" />
                                    </button>

                                    {log.user_name && (
                                        <span className="inline-flex items-center gap-1.5 rounded-lg border border-white/[0.08] bg-white/[0.04] px-2.5 py-1 text-[11px] text-white/45">
                                            <User className="h-3 w-3 shrink-0" />
                                            {log.user_name}
                                        </span>
                                    )}
                                </div>
                            </div>

                            <div className="text-right shrink-0 tabular-nums mt-0.5">
                                <div className="text-[13px] font-medium text-white/75">{date}</div>
                                <div className="text-[11px] text-white/35 mt-0.5 font-mono tracking-wide">{time}</div>
                            </div>
                        </div>

                        {diff.length > 0 ? (
                            <div className="px-5 pb-5">
                                <div className="rounded-xl border border-white/[0.07] bg-black/25 overflow-hidden">
                                    <table className="w-full">
                                        <thead>
                                            <tr className="border-b border-white/[0.06]">
                                                <th className="px-4 py-2.5 text-left text-[9px] uppercase tracking-[0.22em] text-white/25 font-semibold w-1/4">Campo</th>
                                                <th className="px-4 py-2.5 text-left text-[9px] uppercase tracking-[0.22em] text-rose-400/45 font-semibold w-[37.5%]">Antes</th>
                                                <th className="px-4 py-2.5 text-left text-[9px] uppercase tracking-[0.22em] text-emerald-400/45 font-semibold">Depois</th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y divide-white/[0.04]">
                                            {visibleDiff.map((item) => (
                                                <DiffRow key={item.key} item={item} />
                                            ))}
                                        </tbody>
                                    </table>

                                    {unchangedRows.length > 0 && (
                                        <button
                                            onClick={() => setShowUnchanged((v) => !v)}
                                            className="flex w-full items-center justify-center gap-1.5 border-t border-white/[0.05] py-2.5 text-[11px] text-white/30 transition-all hover:text-white/60 hover:bg-white/[0.03] cursor-pointer"
                                        >
                                            {showUnchanged ? (
                                                <><ChevronUp className="h-3 w-3" /> Ocultar {unchangedRows.length} campo(s) sem alteração</>
                                            ) : (
                                                <><ChevronDown className="h-3 w-3" /> +{unchangedRows.length} campo(s) sem alteração</>
                                            )}
                                        </button>
                                    )}
                                </div>
                            </div>
                        ) : (
                            <div className="px-5 pb-5">
                                <div className="rounded-xl border border-dashed border-white/[0.07] bg-white/[0.02] px-4 py-4 text-[12px] text-white/25 text-center">
                                    Evento sem dados estruturados de diff
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}

function buildStats(logs) {
    const users = new Set();
    const actions = new Set();
    const entities = new Set();

    logs.forEach((log) => {
        if (log.user_name) users.add(log.user_name);
        if (log.action) actions.add(log.action);
        if (log.entity_id) entities.add(`${log.entity_type}:${log.entity_id}`);
    });

    return [
        { label: "Eventos visíveis", value: logs.length, icon: Activity, tone: "text-cyan-300" },
        { label: "Ações distintas", value: actions.size, icon: Filter, tone: "text-amber-300" },
        { label: "Usuários", value: users.size, icon: User, tone: "text-emerald-300" },
        { label: "Entidades afetadas", value: entities.size, icon: Tag, tone: "text-fuchsia-300" },
    ];
}

export default function AuditLogPage() {
    const [logs, setLogs] = useState([]);
    const [loading, setLoading] = useState(true);
    const [entityType, setEntityType] = useState("all");
    const [actionFilter, setActionFilter] = useState("");
    const [search, setSearch] = useState("");

    useEffect(() => {
        loadLogs();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [entityType, actionFilter]);

    const loadLogs = async () => {
        setLoading(true);
        try {
            const params = { limit: 300 };
            if (entityType !== "all") params.entity_type = entityType;
            if (actionFilter) params.action = actionFilter;
            const { data } = await api.get("/workflow/audit-logs", { params });
            setLogs(data || []);
        } catch (e) {
            toast.error(
                formatApiError(e?.response?.data?.detail) || "Erro ao carregar auditoria."
            );
            setLogs([]);
        } finally {
            setLoading(false);
        }
    };

    const actions = useMemo(() => {
        const set = new Set();
        logs.forEach((log) => { if (log.action) set.add(log.action); });
        return Array.from(set).sort();
    }, [logs]);

    const filtered = useMemo(() => {
        const query = search.trim().toLowerCase();
        if (!query) return logs;
        return logs.filter((log) => (
            log.action?.toLowerCase().includes(query) ||
            log.entity_id?.toLowerCase().includes(query) ||
            log.user_name?.toLowerCase().includes(query) ||
            log.entity_type?.toLowerCase().includes(query)
        ));
    }, [logs, search]);

    const stats = useMemo(() => buildStats(filtered), [filtered]);

    return (
        <div className="p-6 md:p-8 space-y-6 page-enter" data-testid="audit-page">
            <Card className="overflow-hidden border-white/10 bg-[radial-gradient(circle_at_top_left,_rgba(34,197,94,0.14),_transparent_32%),radial-gradient(circle_at_top_right,_rgba(14,165,233,0.18),_transparent_36%),linear-gradient(180deg,rgba(255,255,255,0.03),rgba(255,255,255,0))]">
                <CardContent className="p-0">
                    <div className="grid gap-6 lg:grid-cols-[1.4fr_0.8fr]">
                        <div className="p-6 md:p-8">
                            <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[11px] uppercase tracking-[0.24em] text-muted-foreground">
                                <ShieldCheck className="h-3.5 w-3.5 text-emerald-300" />
                                trilha imutável
                            </div>
                            <div className="mt-4 flex items-start justify-between gap-4 flex-wrap">
                                <div className="max-w-2xl">
                                    <h1 className="text-3xl md:text-4xl font-heading font-semibold tracking-tight flex items-center gap-3">
                                        <span className="rounded-2xl border border-white/10 bg-white/5 p-3">
                                            <History className="h-7 w-7 text-cyan-300" />
                                        </span>
                                        Audit Log
                                    </h1>
                                    <p className="mt-3 text-sm md:text-base text-muted-foreground leading-relaxed">
                                        Linha do tempo operacional com diff campo a campo de cada mutação relevante.
                                        Focada em rastreabilidade, repasse rápido e leitura técnica.
                                    </p>
                                </div>
                                <Button variant="outline" onClick={loadLogs} data-testid="refresh-audit" className="shrink-0 border-white/10 bg-background/30 backdrop-blur">
                                    <RefreshCw className="h-4 w-4 mr-2" />
                                    Atualizar
                                </Button>
                            </div>
                        </div>

                        <div className="grid grid-cols-2 gap-px bg-white/5">
                            {stats.map(({ label, value, icon: Icon, tone }) => (
                                <div key={label} className="bg-background/50 p-5 md:p-6">
                                    <div className="flex items-center justify-between">
                                        <span className="text-xs uppercase tracking-[0.2em] text-muted-foreground">{label}</span>
                                        <Icon className={`h-4 w-4 ${tone}`} />
                                    </div>
                                    <div className="mt-4 text-3xl font-heading font-semibold mono-num">{value}</div>
                                </div>
                            ))}
                        </div>
                    </div>
                </CardContent>
            </Card>

            <Card className="border-white/10 bg-card/70 backdrop-blur">
                <CardHeader className="pb-4">
                    <CardTitle className="flex items-center gap-2 text-base">
                        <Filter className="h-4 w-4 text-cyan-300" />
                        Filtros
                    </CardTitle>
                    <CardDescription>
                        Refine por entidade, tipo de ação ou qualquer termo chave do evento.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                        <div className="space-y-2">
                            <Label className="text-xs uppercase tracking-wide text-muted-foreground">Tipo de entidade</Label>
                            <Select value={entityType} onValueChange={setEntityType}>
                                <SelectTrigger data-testid="entity-type-filter">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="all">Todas</SelectItem>
                                    {Object.entries(ENTITY_LABEL).map(([key, label]) => (
                                        <SelectItem key={key} value={key}>{label}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>

                        <div className="space-y-2">
                            <Label className="text-xs uppercase tracking-wide text-muted-foreground">Ação</Label>
                            <Select value={actionFilter || "__all__"} onValueChange={(value) => setActionFilter(value === "__all__" ? "" : value)}>
                                <SelectTrigger data-testid="action-filter">
                                    <SelectValue placeholder="Todas" />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="__all__">Todas</SelectItem>
                                    {actions.map((action) => (
                                        <SelectItem key={action} value={action}>{prettifyAction(action)}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>

                        <div className="space-y-2">
                            <Label className="text-xs uppercase tracking-wide text-muted-foreground">Buscar</Label>
                            <div className="relative">
                                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                                <Input
                                    value={search}
                                    onChange={(e) => setSearch(e.target.value)}
                                    placeholder="usuário, ação, entidade ou ID"
                                    className="pl-9"
                                    data-testid="audit-search"
                                />
                            </div>
                        </div>
                    </div>

                    <div className="flex items-center justify-between gap-3 flex-wrap border-t border-border/70 pt-4 text-sm">
                        <div className="flex items-center gap-2 text-muted-foreground">
                            <Clock3 className="h-4 w-4" />
                            {loading ? "Atualizando eventos..." : `${filtered.length} evento(s) exibido(s)`}
                        </div>
                        <div className="flex items-center gap-2 flex-wrap">
                            <Badge variant="outline" className="border-white/10 bg-white/5">limite 300</Badge>
                            {entityType !== "all" && <Badge variant="outline">{ENTITY_LABEL[entityType] || entityType}</Badge>}
                            {actionFilter && <Badge variant="outline">{prettifyAction(actionFilter)}</Badge>}
                            {search.trim() && <Badge variant="outline">busca ativa</Badge>}
                        </div>
                    </div>
                </CardContent>
            </Card>

            {loading ? (
                <div className="flex gap-5">
                    <div className="flex flex-col items-center shrink-0 w-10">
                        {[1, 2, 3].map((item) => (
                            <div key={item} className="flex flex-col items-center w-full">
                                <div className="h-10 w-10 rounded-xl bg-white/5 animate-pulse" />
                                {item < 3 && <div className="flex-1 w-px bg-white/5 h-32 mt-2" />}
                            </div>
                        ))}
                    </div>
                    <div className="flex-1 space-y-5">
                        {[1, 2, 3].map((item) => (
                            <div key={item} className="rounded-2xl border border-white/[0.07] bg-white/[0.025] overflow-hidden">
                                <div className="flex">
                                    <div className="w-[3px] bg-white/10" />
                                    <div className="flex-1 p-5 space-y-4">
                                        <div className="flex items-center gap-3">
                                            <div className="h-5 w-24 rounded-full bg-white/8 animate-pulse" />
                                            <div className="h-5 w-32 rounded bg-white/5 animate-pulse" />
                                        </div>
                                        <div className="flex gap-2">
                                            <div className="h-6 w-28 rounded-lg bg-white/5 animate-pulse" />
                                            <div className="h-6 w-20 rounded-lg bg-white/5 animate-pulse" />
                                        </div>
                                        <div className="rounded-xl border border-white/[0.06] overflow-hidden">
                                            <div className="h-8 bg-white/[0.03] animate-pulse" />
                                            <div className="h-20 bg-white/[0.02] animate-pulse" />
                                        </div>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            ) : (
                <div>
                    {filtered.length === 0 ? (
                        <Card className="border-dashed border-white/10">
                            <CardContent className="flex flex-col items-center justify-center gap-3 p-12 text-center">
                                <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                                    <History className="h-6 w-6 text-muted-foreground" />
                                </div>
                                <div>
                                    <p className="text-base font-medium">Nenhum evento encontrado</p>
                                    <p className="text-sm text-muted-foreground mt-1">
                                        Ajuste os filtros ou limpe a busca para ampliar o histórico.
                                    </p>
                                </div>
                            </CardContent>
                        </Card>
                    ) : (
                        <div>
                            {filtered.map((log, idx) => (
                                <AuditCard
                                    key={log.id}
                                    log={log}
                                    isLast={idx === filtered.length - 1}
                                />
                            ))}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
