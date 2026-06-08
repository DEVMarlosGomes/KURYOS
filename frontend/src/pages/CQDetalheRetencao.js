import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Loader2, ChevronRight } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

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
    mp: "Matéria-Prima",
    fragrancia: "Fragrância",
    produto_acabado: "Produto Acabado",
};

function getDiasRestantes(data_limite) {
    if (!data_limite) return null;
    return Math.ceil((new Date(data_limite) - new Date()) / (1000 * 60 * 60 * 24));
}

function SituacaoBadge({ diasRestantes }) {
    if (diasRestantes === null) return <span className="text-muted-foreground">—</span>;
    if (diasRestantes < 0)
        return <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200">Vencida</span>;
    if (diasRestantes < 30)
        return <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200">Vencendo em {diasRestantes} dia{diasRestantes !== 1 ? "s" : ""}</span>;
    return <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">Em guarda</span>;
}

export default function CQDetalheRetencao() {
    const { id } = useParams();
    const navigate = useNavigate();
    const [ret, setRet] = useState(null);
    const [loading, setLoading] = useState(true);

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const { data } = await api.get(`/cq/retencoes/${id}`);
            setRet(data);
        } catch (e) {
            toast.error("Erro ao carregar amostra de retenção");
        } finally {
            setLoading(false);
        }
    }, [id]);

    useEffect(() => { load(); }, [load]);

    if (loading) {
        return (
            <div className="p-6 flex items-center justify-center h-64">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
        );
    }

    if (!ret) {
        return (
            <div className="p-6">
                <p className="text-muted-foreground">Retenção não encontrada.</p>
                <Button variant="outline" className="mt-4" onClick={() => navigate("/cq/retencoes")}>Voltar</Button>
            </div>
        );
    }

    const diasRestantes = getDiasRestantes(ret.data_limite_guarda);

    const infoRows = [
        { label: "Nº Retenção", value: ret.numero_ret || ret.numero },
        { label: "Tipo", value: TIPO_LABELS[ret.tipo] || ret.tipo },
        { label: "Item", value: ret.item_nome },
        { label: "Fornecedor", value: ret.fornecedor_nome },
        { label: "Lote", value: ret.lote_numero },
        { label: "Qtd. Retida", value: ret.quantidade_retida != null ? `${ret.quantidade_retida} ${ret.unidade || ""}`.trim() : null },
        { label: "Localização Física", value: ret.localizacao_fisica },
        { label: "Data de Coleta", value: ret.data_coleta ? new Date(ret.data_coleta).toLocaleDateString("pt-BR") : null },
        { label: "Limite de Guarda", value: ret.data_limite_guarda ? new Date(ret.data_limite_guarda).toLocaleDateString("pt-BR") : null },
        { label: "Criado em", value: ret.created_at ? new Date(ret.created_at).toLocaleDateString("pt-BR") : null },
    ];

    return (
        <div className="p-6 page-enter" data-testid="cq-detalhe-retencao">
            {/* Breadcrumb */}
            <div className="flex items-center gap-2 text-sm text-muted-foreground mb-4">
                <button onClick={() => navigate("/cq/retencoes")} className="hover:text-foreground transition-colors">
                    Retenções
                </button>
                <ChevronRight className="h-4 w-4" />
                <span className="text-foreground font-medium">{ret.numero_ret || ret.numero || id}</span>
            </div>

            {/* Header */}
            <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 mb-6">
                <div>
                    <div className="flex items-center gap-3 mb-2 flex-wrap">
                        <h1 className="text-2xl font-heading font-bold">{ret.numero_ret || ret.numero || "—"}</h1>
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300">
                            {TIPO_LABELS[ret.tipo] || ret.tipo}
                        </span>
                        {ret.status && (
                            <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold ${STATUS_COLORS[ret.status] || "bg-gray-100 text-gray-700"}`}>
                                {STATUS_LABELS[ret.status] || ret.status}
                            </span>
                        )}
                    </div>
                    <p className="text-sm text-muted-foreground">{ret.item_nome || "—"}</p>
                </div>
                <div className="flex items-center gap-2">
                    <span className="text-sm text-muted-foreground">Situação:</span>
                    <SituacaoBadge diasRestantes={diasRestantes} />
                </div>
            </div>

            {/* Info Grid */}
            <div className="rounded-lg border border-border bg-card p-5 mb-6">
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    {infoRows.map(row => (
                        <div key={row.label}>
                            <p className="text-xs text-muted-foreground mb-0.5">{row.label}</p>
                            <p className="text-sm font-medium">{row.value || "—"}</p>
                        </div>
                    ))}
                </div>
            </div>

            {/* Vínculo com RA */}
            {ret.ra_id && (
                <div className="rounded-lg border border-border bg-card p-5">
                    <p className="text-xs text-muted-foreground mb-1">Registro de Análise de Origem</p>
                    <button
                        className="text-sm font-medium text-primary hover:underline"
                        onClick={() => navigate(`/cq/registros-analise/${ret.ra_id}`)}
                    >
                        Abrir RA vinculado →
                    </button>
                </div>
            )}
        </div>
    );
}
