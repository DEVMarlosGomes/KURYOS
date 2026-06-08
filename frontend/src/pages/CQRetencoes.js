import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Loader2, Filter, ChevronRight } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

const STATUS_COLORS = {
    em_guarda: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
    descartada: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
    utilizada: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
};

const STATUS_LABELS = {
    em_guarda: "Em Guarda",
    descartada: "Descartada",
    utilizada: "Utilizada",
};

const TIPO_LABELS = {
    mp: "MP",
    fragrancia: "Fragrância",
    produto_acabado: "Produto Acabado",
};

function getDiasRestantes(data_limite) {
    if (!data_limite) return null;
    return Math.ceil((new Date(data_limite) - new Date()) / (1000 * 60 * 60 * 24));
}

function DiasBadge({ diasRestantes }) {
    if (diasRestantes === null) return <span className="text-muted-foreground">—</span>;
    if (diasRestantes < 0) {
        return (
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200">
                Vencida
            </span>
        );
    }
    if (diasRestantes < 30) {
        return (
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200">
                Vencendo em {diasRestantes} dia{diasRestantes !== 1 ? "s" : ""}
            </span>
        );
    }
    return (
        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">
            Em guarda
        </span>
    );
}

export default function CQRetencoes() {
    const navigate = useNavigate();
    const { user } = useAuth();
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [filterTipo, setFilterTipo] = useState("all");
    const [filterStatus, setFilterStatus] = useState("all");

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const params = { limit: 100 };
            if (filterTipo !== "all") params.tipo = filterTipo;
            if (filterStatus !== "all") params.status = filterStatus;
            const { data } = await api.get("/cq/retencoes", { params });
            setItems(Array.isArray(data) ? data : (data?.items ?? data?.data ?? []));
        } catch (e) {
            toast.error("Erro ao carregar retenções");
        } finally {
            setLoading(false);
        }
    }, [filterTipo, filterStatus]);

    useEffect(() => { load(); }, [load]);

    return (
        <div className="p-6 page-enter" data-testid="cq-retencoes">
            <div className="flex items-center justify-between mb-6">
                <div>
                    <h1 className="text-3xl font-heading font-semibold tracking-tight">Amostras de Retenção</h1>
                    <p className="text-sm text-muted-foreground mt-1">
                        Controle de guarda de amostras de referência
                    </p>
                </div>
            </div>

            {/* Filters */}
            <div className="flex flex-wrap gap-3 mb-5">
                <div className="flex items-center gap-2">
                    <Filter className="h-4 w-4 text-muted-foreground" />
                    <Label className="text-sm">Tipo:</Label>
                    <Select value={filterTipo} onValueChange={setFilterTipo}>
                        <SelectTrigger className="w-[180px]" data-testid="filter-tipo-ret">
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="all">Todos</SelectItem>
                            <SelectItem value="mp">MP</SelectItem>
                            <SelectItem value="fragrancia">Fragrância</SelectItem>
                            <SelectItem value="produto_acabado">Produto Acabado</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
                <div className="flex items-center gap-2">
                    <Label className="text-sm">Status:</Label>
                    <Select value={filterStatus} onValueChange={setFilterStatus}>
                        <SelectTrigger className="w-[160px]">
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="all">Todos</SelectItem>
                            <SelectItem value="em_guarda">Em Guarda</SelectItem>
                            <SelectItem value="descartada">Descartada</SelectItem>
                            <SelectItem value="utilizada">Utilizada</SelectItem>
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
                <div className="rounded-lg border border-border overflow-hidden" data-testid="table-retencoes">
                    <table className="w-full text-sm">
                        <thead className="bg-muted/50">
                            <tr>
                                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Nº Ret.</th>
                                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Tipo</th>
                                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Item</th>
                                <th className="text-left px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">Lote</th>
                                <th className="text-left px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">Data Coleta</th>
                                <th className="text-left px-4 py-3 font-medium text-muted-foreground hidden lg:table-cell">Limite Guarda</th>
                                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Situação</th>
                                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Status</th>
                                <th className="px-4 py-3" />
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-border">
                            {items.length === 0 ? (
                                <tr>
                                    <td colSpan={9} className="text-center py-10 text-muted-foreground">
                                        Nenhuma amostra de retenção encontrada.
                                    </td>
                                </tr>
                            ) : items.map((ret) => {
                                const diasRestantes = getDiasRestantes(ret.data_limite_guarda);
                                return (
                                    <tr key={ret.id} className="hover:bg-accent/40 cursor-pointer transition-colors" onClick={() => navigate(`/cq/retencoes/${ret.id}`)} data-testid={`row-ret-${ret.id}`}>
                                        <td className="px-4 py-3 font-mono text-xs font-medium">{ret.numero_ret || ret.numero || "—"}</td>
                                        <td className="px-4 py-3">
                                            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300">
                                                {TIPO_LABELS[ret.tipo] || ret.tipo || "—"}
                                            </span>
                                        </td>
                                        <td className="px-4 py-3 font-medium">{ret.item_nome || "—"}</td>
                                        <td className="px-4 py-3 text-xs hidden md:table-cell mono-num">{ret.lote_numero || "—"}</td>
                                        <td className="px-4 py-3 text-xs hidden md:table-cell mono-num">
                                            {ret.data_coleta ? new Date(ret.data_coleta).toLocaleDateString("pt-BR") : "—"}
                                        </td>
                                        <td className="px-4 py-3 text-xs hidden lg:table-cell mono-num">
                                            {ret.data_limite_guarda ? new Date(ret.data_limite_guarda).toLocaleDateString("pt-BR") : "—"}
                                        </td>
                                        <td className="px-4 py-3">
                                            <DiasBadge diasRestantes={diasRestantes} />
                                        </td>
                                        <td className="px-4 py-3">
                                            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${STATUS_COLORS[ret.status] || "bg-gray-100 text-gray-700"}`}>
                                                {STATUS_LABELS[ret.status] || ret.status || "—"}
                                            </span>
                                        </td>
                                        <td className="px-4 py-3">
                                            <ChevronRight className="h-4 w-4 text-muted-foreground" />
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}
