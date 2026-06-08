import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Loader2, ChevronRight, Filter, Info } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

const CLASS_COLORS = {
    critica: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
    maior: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200",
    menor: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
};

const STATUS_COLORS = {
    aberta: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
    em_investigacao: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
    aguardando_fornecedor: "bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200",
    encerrada: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200",
    encerrada_concessao: "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200",
};

const STATUS_LABELS = {
    aberta: "Aberta",
    em_investigacao: "Em Investigação",
    aguardando_fornecedor: "Aguard. Fornecedor",
    encerrada: "Encerrada",
    encerrada_concessao: "Encerrada c/ Concessão",
};

const CLASS_LABELS = {
    critica: "Crítica",
    maior: "Maior",
    menor: "Menor",
};

export default function CQListaRNCs() {
    const navigate = useNavigate();
    const { user } = useAuth();
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [filterStatus, setFilterStatus] = useState("all");
    const [filterClass, setFilterClass] = useState("all");

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const params = {};
            if (filterStatus !== "all") params.status = filterStatus;
            if (filterClass !== "all") params.classificacao = filterClass;
            const { data } = await api.get("/cq/rncs", { params });
            setItems(Array.isArray(data) ? data : (data?.items ?? data?.data ?? []));
        } catch (e) {
            toast.error("Erro ao carregar RNCs");
        } finally {
            setLoading(false);
        }
    }, [filterStatus, filterClass]);

    useEffect(() => { load(); }, [load]);

    return (
        <div className="p-6 page-enter" data-testid="cq-lista-rncs">
            <div className="flex items-center justify-between mb-6">
                <div>
                    <h1 className="text-3xl font-heading font-semibold tracking-tight">Registros de Não Conformidade</h1>
                    <p className="text-sm text-muted-foreground mt-1">Gestão de RNCs abertas e em tratamento</p>
                </div>
            </div>

            {/* Filters */}
            <div className="flex flex-wrap gap-3 mb-5">
                <div className="flex items-center gap-2">
                    <Filter className="h-4 w-4 text-muted-foreground" />
                    <Label className="text-sm">Status:</Label>
                    <Select value={filterStatus} onValueChange={(v) => { setFilterStatus(v); }} data-testid="filter-status-rnc">
                        <SelectTrigger className="w-[200px]" data-testid="filter-status-rnc">
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="all">Todos</SelectItem>
                            <SelectItem value="aberta">Aberta</SelectItem>
                            <SelectItem value="em_investigacao">Em Investigação</SelectItem>
                            <SelectItem value="aguardando_fornecedor">Aguardando Fornecedor</SelectItem>
                            <SelectItem value="encerrada">Encerrada</SelectItem>
                            <SelectItem value="encerrada_concessao">Encerrada c/ Concessão</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
                <div className="flex items-center gap-2">
                    <Label className="text-sm">Classificação:</Label>
                    <Select value={filterClass} onValueChange={(v) => { setFilterClass(v); }}>
                        <SelectTrigger className="w-[140px]" data-testid="filter-classificacao">
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="all">Todas</SelectItem>
                            <SelectItem value="critica">Crítica</SelectItem>
                            <SelectItem value="maior">Maior</SelectItem>
                            <SelectItem value="menor">Menor</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
            </div>

            {/* Table */}
            {loading ? (
                <div className="flex items-center justify-center h-48">
                    <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
            ) : (
                <div className="rounded-lg border border-border overflow-hidden" data-testid="table-rncs">
                    <table className="w-full text-sm">
                        <thead className="bg-muted/50">
                            <tr>
                                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Nº RNC</th>
                                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Classificação</th>
                                <th className="text-left px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">Origem</th>
                                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Item</th>
                                <th className="text-left px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">Fornecedor</th>
                                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Status</th>
                                <th className="text-left px-4 py-3 font-medium text-muted-foreground hidden lg:table-cell">Prazo</th>
                                <th className="text-left px-4 py-3 font-medium text-muted-foreground hidden lg:table-cell">Responsável</th>
                                <th className="px-4 py-3" />
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-border">
                            {items.length === 0 ? (
                                <tr>
                                    <td colSpan={9} className="py-10">
                                        <div className="flex flex-col items-center gap-2 text-muted-foreground">
                                            <Info className="h-8 w-8 opacity-40" />
                                            <p className="font-medium text-sm">Nenhuma RNC encontrada</p>
                                            {filterStatus === "all" && filterClass === "all" && (
                                                <p className="text-xs text-center max-w-xs">
                                                    RNCs são criadas automaticamente ao <strong>reprovar um Registro de Análise</strong> ou ao marcar um item de checklist como "Não Conforme crítico".
                                                </p>
                                            )}
                                        </div>
                                    </td>
                                </tr>
                            ) : items.map((rnc) => (
                                <tr
                                    key={rnc.id}
                                    className="hover:bg-accent/40 cursor-pointer transition-colors"
                                    onClick={() => navigate(`/cq/rncs/${rnc.id}`)}
                                    data-testid={`row-rnc-${rnc.id}`}
                                >
                                    <td className="px-4 py-3 font-mono text-xs font-medium">{rnc.numero_rnc}</td>
                                    <td className="px-4 py-3">
                                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${CLASS_COLORS[rnc.classificacao] || "bg-gray-100 text-gray-700"}`}>
                                            {CLASS_LABELS[rnc.classificacao] || rnc.classificacao}
                                        </span>
                                    </td>
                                    <td className="px-4 py-3 text-xs hidden md:table-cell">{rnc.origem || "—"}</td>
                                    <td className="px-4 py-3 font-medium text-sm">{rnc.item_nome || "—"}</td>
                                    <td className="px-4 py-3 text-xs hidden md:table-cell">{rnc.fornecedor_nome || "—"}</td>
                                    <td className="px-4 py-3">
                                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${STATUS_COLORS[rnc.status] || "bg-gray-100 text-gray-700"}`}>
                                            {STATUS_LABELS[rnc.status] || rnc.status}
                                        </span>
                                    </td>
                                    <td className="px-4 py-3 text-xs text-muted-foreground hidden lg:table-cell mono-num">
                                        {rnc.prazo_resolucao ? new Date(rnc.prazo_resolucao).toLocaleDateString("pt-BR") : "—"}
                                    </td>
                                    <td className="px-4 py-3 text-xs hidden lg:table-cell">{rnc.responsavel_nome || "—"}</td>
                                    <td className="px-4 py-3">
                                        <ChevronRight className="h-4 w-4 text-muted-foreground" />
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}
