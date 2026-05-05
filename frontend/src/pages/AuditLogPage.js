import { useState, useEffect, useMemo } from "react";
import api from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { History, RefreshCw, User, Tag } from "lucide-react";
import { toast } from "sonner";
import { formatApiError } from "@/lib/formatError";

const ENTITY_LABEL = {
    client: "Cliente",
    project: "Projeto",
    sample: "Amostra",
    variacao: "Variação",
    pd_card: "Card P&D",
    sku: "SKU",
    workflow_task: "Tarefa Workflow",
    tenant: "Tenant",
};

const ACTION_COLOR = {
    client_created: "bg-emerald-500",
    client_moved: "bg-blue-500",
    project_created: "bg-emerald-500",
    project_moved: "bg-blue-500",
    sample_created: "bg-emerald-500",
    sample_moved: "bg-blue-500",
    sample_rework_created: "bg-amber-500",
    variacao_moved: "bg-blue-500",
    pd_card_auto_created: "bg-violet-500",
    pd_card_moved: "bg-blue-500",
    task_created: "bg-cyan-500",
    task_completed: "bg-emerald-500",
    task_updated: "bg-slate-400",
    task_deleted: "bg-red-500",
    tenant_data_reset: "bg-red-600",
};

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
                formatApiError(e?.response?.data?.detail) ||
                "Erro ao carregar audit log (apenas admin/gestor)"
            );
            setLogs([]);
        } finally {
            setLoading(false);
        }
    };

    const actions = useMemo(() => {
        const set = new Set();
        logs.forEach((l) => set.add(l.action));
        return Array.from(set).sort();
    }, [logs]);

    const filtered = useMemo(() => {
        const q = search.trim().toLowerCase();
        if (!q) return logs;
        return logs.filter((l) => {
            return (
                l.action?.toLowerCase().includes(q) ||
                l.entity_id?.toLowerCase().includes(q) ||
                l.user_name?.toLowerCase().includes(q)
            );
        });
    }, [logs, search]);

    return (
        <div className="p-8 space-y-6 page-enter" data-testid="audit-page">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-heading font-semibold tracking-tight flex items-center gap-2">
                        <History className="h-7 w-7" /> Audit Log
                    </h1>
                    <p className="text-sm text-muted-foreground mt-1">
                        Histórico imutável de todas as ações relevantes do ERP. Visível apenas para admin e gestor.
                    </p>
                </div>
                <Button variant="outline" onClick={loadLogs} data-testid="refresh-audit">
                    <RefreshCw className="h-4 w-4 mr-2" />
                    Atualizar
                </Button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div>
                    <Label className="text-xs">Tipo de entidade</Label>
                    <Select value={entityType} onValueChange={setEntityType}>
                        <SelectTrigger data-testid="entity-type-filter"><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="all">Todas</SelectItem>
                            {Object.entries(ENTITY_LABEL).map(([k, l]) => (
                                <SelectItem key={k} value={k}>{l}</SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>
                <div>
                    <Label className="text-xs">Ação</Label>
                    <Select value={actionFilter || "__all__"} onValueChange={(v) => setActionFilter(v === "__all__" ? "" : v)}>
                        <SelectTrigger data-testid="action-filter"><SelectValue placeholder="Todas" /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="__all__">Todas</SelectItem>
                            {actions.map((a) => (
                                <SelectItem key={a} value={a}>{a}</SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>
                <div>
                    <Label className="text-xs">Buscar (usuário, ação, ID)</Label>
                    <Input
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        placeholder="ex: admin, sample_moved, 39ba8a..."
                        data-testid="audit-search"
                    />
                </div>
            </div>

            {loading ? (
                <div className="space-y-2">
                    {[1, 2, 3, 4].map((i) => (
                        <div key={i} className="h-16 bg-muted rounded-lg animate-pulse" />
                    ))}
                </div>
            ) : (
                <div className="space-y-2">
                    {filtered.length === 0 && (
                        <Card>
                            <CardContent className="p-10 text-center text-sm text-muted-foreground">
                                Nenhum registro encontrado para os filtros atuais.
                            </CardContent>
                        </Card>
                    )}
                    {filtered.map((log) => (
                        <Card key={log.id} data-testid={`audit-${log.id}`}>
                            <CardContent className="p-4">
                                <div className="flex items-start gap-3">
                                    <div className={`mt-1 h-2 w-2 rounded-full shrink-0 ${ACTION_COLOR[log.action] || "bg-slate-400"}`} />
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center justify-between gap-2 flex-wrap">
                                            <span className="font-medium text-sm" data-testid={`audit-action-${log.id}`}>
                                                {log.action}
                                            </span>
                                            <span className="text-xs text-muted-foreground">
                                                {new Date(log.timestamp).toLocaleString("pt-BR")}
                                            </span>
                                        </div>
                                        <div className="flex items-center flex-wrap gap-2 mt-1 text-xs text-muted-foreground">
                                            <Badge variant="outline" className="gap-1 text-[10px]">
                                                <Tag className="h-3 w-3" />
                                                {ENTITY_LABEL[log.entity_type] || log.entity_type}
                                            </Badge>
                                            <span className="font-mono text-[10px] break-all">
                                                {log.entity_id?.substring(0, 12)}…
                                            </span>
                                            {log.user_name && (
                                                <span className="flex items-center gap-1">
                                                    <User className="h-3 w-3" />
                                                    {log.user_name}
                                                </span>
                                            )}
                                        </div>
                                        {(log.before || log.after) && (
                                            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-2 text-[11px]">
                                                {log.before && (
                                                    <div className="bg-red-500/5 rounded p-2 border border-red-500/15">
                                                        <p className="text-[10px] uppercase font-semibold text-red-700 mb-1">Antes</p>
                                                        <pre className="whitespace-pre-wrap break-all font-mono">
                                                            {JSON.stringify(log.before, null, 2)}
                                                        </pre>
                                                    </div>
                                                )}
                                                {log.after && (
                                                    <div className="bg-emerald-500/5 rounded p-2 border border-emerald-500/15">
                                                        <p className="text-[10px] uppercase font-semibold text-emerald-700 mb-1">Depois</p>
                                                        <pre className="whitespace-pre-wrap break-all font-mono">
                                                            {JSON.stringify(log.after, null, 2)}
                                                        </pre>
                                                    </div>
                                                )}
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                    ))}
                </div>
            )}
        </div>
    );
}
