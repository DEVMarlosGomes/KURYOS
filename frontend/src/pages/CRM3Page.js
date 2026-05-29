import { useState, useEffect, useCallback, useRef } from "react";
import api from "@/lib/api";
import { formatApiError } from "@/lib/formatError";
import { getCurrentBackendUrl, toWebSocketUrl } from "@/lib/backend";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter
} from "@/components/ui/dialog";
import { Building2, FlaskConical, AlertTriangle, ChevronRight, Trash2, Plus, X, Lock, Printer } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import ViewSwitcher from "@/components/ViewSwitcher";
import FilterBar, { applyFilters } from "@/components/FilterBar";
import ListView from "@/components/ListView";

function CRMSubNav({ active }) {
    const navigate = useNavigate();
    const tabs = [
        { id: "clients", label: "Clientes", path: "/crm/clients" },
        { id: "projects", label: "Projetos", path: "/crm/projects" },
        { id: "samples", label: "Amostras", path: "/crm/samples" },
    ];
    return (
        <div className="flex items-center gap-1 mb-5 border-b border-border pb-3">
            {tabs.map(t => (
                <button
                    key={t.id}
                    onClick={() => navigate(t.path)}
                    className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                        active === t.id
                            ? "bg-primary text-primary-foreground shadow-sm"
                            : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                    }`}
                >
                    {t.label}
                </button>
            ))}
        </div>
    );
}

const STAGES = [
    { id: "solicitada", label: "Solicitada", color: "bg-slate-400" },
    { id: "em_elaboracao", label: "Em Elaboração", color: "bg-blue-500" },
    { id: "retrabalho", label: "Retrabalho", color: "bg-amber-500" },
    { id: "enviada", label: "Enviada", color: "bg-cyan-500" },
    { id: "aprovada", label: "Aprovada", color: "bg-emerald-500" },
    { id: "reprovada", label: "Reprovada", color: "bg-red-500" },
];

const STAGE_LABELS = Object.fromEntries(STAGES.map(s => [s.id, s.label]));

export default function CRM3Page() {
    const { user: authUser } = useAuth();
    const wsRef = useRef(null);
    const [samples, setSamples] = useState([]);
    const [loading, setLoading] = useState(true);
    const [search, setSearch] = useState("");
    const [view, setView] = useState(() => localStorage.getItem("crm3:view") || "kanban");
    const [filters, setFilters] = useState({});
    const [selectedSample, setSelectedSample] = useState(null);
    const [selectedVariacao, setSelectedVariacao] = useState(null);
    const [tab, setTab] = useState("briefing");

    // Estado para registrar resultado do cliente (somente quando variação está em "enviada")
    const [resultadoForm, setResultadoForm] = useState({});  // variacaoId → { resultado, feedback, loading }

    useEffect(() => {
        localStorage.setItem("crm3:view", view);
    }, [view]);

    const loadSamples = useCallback(async () => {
        try {
            const params = search ? { search } : {};
            const { data } = await api.get("/crm/samples", { params });
            console.log("Samples loaded:", data);
            // Filter out invalid samples and validation errors
            const validSamples = Array.isArray(data) ? data.filter(s => {
                // Check if it's a validation error object
                if (s && s.type && s.loc && s.msg) {
                    console.warn("Validation error in response:", s);
                    return false;
                }
                // Check if it's a valid sample
                return s && typeof s === 'object' && s.id;
            }) : [];
            setSamples(validSamples);
        } catch (e) {
            console.error("Failed to load samples", e);
            setSamples([]);
        } finally {
            setLoading(false);
        }
    }, [search]);

    useEffect(() => { loadSamples(); }, [loadSamples]);

    // WebSocket: receive PD→CRM stage sync events
    useEffect(() => {
        const wsBackendUrl = toWebSocketUrl(getCurrentBackendUrl());
        if (!wsBackendUrl) return undefined;

        let disposed = false;
        let reconnectTimer = null;

        const connectWs = () => {
            if (disposed) return;
            try {
                const ws = new WebSocket(`${wsBackendUrl}/api/ws`);

                ws.onmessage = (event) => {
                    try {
                        const msg = JSON.parse(event.data);
                        if (msg.event !== "crm_sample_pd_synced") return;

                        const { amostra_id, variacao_id, status_pd_raw, status_pd_label } = msg.data || {};
                        if (!amostra_id || !variacao_id) return;

                        setSamples((current) =>
                            current.map((sample) => {
                                if (sample.id !== amostra_id) return sample;
                                return {
                                    ...sample,
                                    variacoes: (sample.variacoes || []).map((v) =>
                                        v.id === variacao_id
                                            ? { ...v, status_pd_raw, status_pd_label }
                                            : v
                                    ),
                                };
                            })
                        );
                    } catch {}
                };

                ws.onclose = () => {
                    if (disposed) return;
                    reconnectTimer = window.setTimeout(connectWs, 5000);
                };

                ws.onerror = () => { ws.close(); };

                wsRef.current = ws;
            } catch {
                reconnectTimer = window.setTimeout(connectWs, 5000);
            }
        };

        connectWs();

        return () => {
            disposed = true;
            clearTimeout(reconnectTimer);
            wsRef.current?.close();
        };
    }, []);

    // Agrupar variações por estágio
    const variacoesByStage = STAGES.reduce((acc, stage) => {
        acc[stage.id] = [];
        samples.forEach(sample => {
            try {
                // Validar que sample é um objeto válido
                if (!sample || typeof sample !== 'object' || !sample.id) {
                    console.warn("Invalid sample:", sample);
                    return;
                }

                if (sample.variacoes && Array.isArray(sample.variacoes) && sample.variacoes.length > 0) {
                    // Novo modelo com variações
                    sample.variacoes.forEach(variacao => {
                        if (!variacao || typeof variacao !== 'object') {
                            console.warn("Invalid variacao:", variacao);
                            return;
                        }
                        
                        if (variacao.status === stage.id) {
                            acc[stage.id].push({
                                id: variacao.id || `${sample.id}-var`,
                                codigo: variacao.codigo || '',
                                status: variacao.status || stage.id,
                                status_pd_label: variacao.status_pd_label || null,
                                status_pd_raw: variacao.status_pd_raw || null,
                                sample_id: sample.id,
                                sample_numero: sample.numero_amostra || '',
                                nome_produto: sample.nome_produto || sample.nome_amostra || '',
                                projeto_nome: sample.projeto_nome || '',
                                cliente_nome: sample.cliente_nome || '',
                                descricao_aplicacao: variacao.descricao_aplicacao || '',
                                sample_completa: sample
                            });
                        }
                    });
                } else if (sample.stage === stage.id) {
                    // Modelo antigo sem variações (compatibilidade)
                    acc[stage.id].push({
                        id: sample.id,
                        codigo: sample.codigo_referencia || sample.id,
                        status: sample.stage,
                        sample_id: sample.id,
                        sample_numero: sample.numero_amostra || '',
                        nome_produto: sample.nome_amostra || '',
                        projeto_nome: sample.projeto_nome || '',
                        cliente_nome: sample.cliente_nome || '',
                        descricao_aplicacao: '',
                        sample_completa: sample
                    });
                }
            } catch (err) {
                console.error("Error processing sample:", sample, err);
            }
        });
        return acc;
    }, {});

    const handleResultadoCliente = async (sampleId, variacaoId) => {
        const form = resultadoForm[variacaoId] || {};
        if (!form.resultado) return toast.error("Selecione o resultado do cliente");
        if (form.resultado === "retrabalho" && !(form.feedback || "").trim())
            return toast.error("Informe o feedback do cliente para o retrabalho");

        setResultadoForm(prev => ({ ...prev, [variacaoId]: { ...prev[variacaoId], loading: true } }));
        try {
            await api.post(`/crm/samples/${sampleId}/variacoes/${variacaoId}/resultado-cliente`, {
                resultado: form.resultado,
                feedback_cliente: form.feedback || "",
            });
            toast.success("Resultado do cliente registrado!");
            setResultadoForm(prev => { const n = { ...prev }; delete n[variacaoId]; return n; });
            loadSamples();
            const { data } = await api.get(`/crm/samples/${sampleId}`);
            setSelectedSample(data);
        } catch (e) {
            toast.error(formatApiError(e));
        } finally {
            setResultadoForm(prev => ({ ...prev, [variacaoId]: { ...prev[variacaoId], loading: false } }));
        }
    };

    const handleUpdateSample = async (sampleId, updates) => {
        try {
            await api.put(`/crm/samples/${sampleId}`, updates);
            toast.success("Amostra atualizada!");
            loadSamples();
        } catch (e) {
            toast.error(formatApiError(e));
        }
    };

    const handleDeleteSample = async () => {
        if (!selectedSample) return;
        if (!window.confirm(`Excluir amostra "${selectedSample.nome_produto || selectedSample.nome_amostra}" e TODAS as variações/cards P&D vinculados? Ação irreversível.`)) return;
        try {
            const { data } = await api.delete(`/crm/samples/${selectedSample.id}`);
            toast.success(`Amostra excluída (${data.deleted_pd_cards} card(s) P&D removidos).`);
            setSelectedSample(null);
            loadSamples();
        } catch (e) {
            toast.error(formatApiError(e));
        }
    };

    const handleUpdateVariacao = async (sampleId, variacaoId, updates) => {
        try {
            await api.put(`/crm/samples/${sampleId}/variacoes/${variacaoId}`, updates);
            toast.success("Variação atualizada!");
            loadSamples();
            // Reload selected sample
            const { data } = await api.get(`/crm/samples/${sampleId}`);
            setSelectedSample(data);
        } catch (e) {
            toast.error(formatApiError(e));
        }
    };

    const handleDeleteVariacao = async (sampleId, variacaoId, codigo) => {
        if (!window.confirm(`Excluir a variação ${codigo}? O card P&D vinculado também será removido.`)) return;
        try {
            await api.delete(`/crm/samples/${sampleId}/variacoes/${variacaoId}`);
            toast.success(`Variação ${codigo} excluída.`);
            loadSamples();
            const { data } = await api.get(`/crm/samples/${sampleId}`);
            setSelectedSample(data);
        } catch (e) {
            toast.error(formatApiError(e));
        }
    };

    const [showAddVariacoes, setShowAddVariacoes] = useState(false);
    const [newVariacoes, setNewVariacoes] = useState([{
        descricao_aplicacao: "",
        percentual_fragrancia: "",
        referencia_fragrancia: "",
        custo_fragrancia: "",
        observacoes_especificas: ""
    }]);

    const handleAddVariacoesSubmit = async () => {
        if (!selectedSample) return;
        const valid = newVariacoes.filter(v => v.descricao_aplicacao.trim() || v.referencia_fragrancia.trim());
        if (valid.length === 0) {
            toast.error("Preencha pelo menos uma variação.");
            return;
        }
        try {
            const payload = {
                variacoes: valid.map(v => ({
                    descricao_aplicacao: v.descricao_aplicacao,
                    percentual_fragrancia: v.percentual_fragrancia ? parseFloat(v.percentual_fragrancia) : null,
                    referencia_fragrancia: v.referencia_fragrancia,
                    custo_fragrancia: v.custo_fragrancia ? parseFloat(v.custo_fragrancia) : null,
                    observacoes_especificas: v.observacoes_especificas,
                }))
            };
            const { data } = await api.post(`/crm/samples/${selectedSample.id}/variacoes`, payload);
            toast.success(`${data.added} variação(ões) adicionada(s)!`);
            setShowAddVariacoes(false);
            setNewVariacoes([{
                descricao_aplicacao: "",
                percentual_fragrancia: "",
                referencia_fragrancia: "",
                custo_fragrancia: "",
                observacoes_especificas: ""
            }]);
            loadSamples();
            const response = await api.get(`/crm/samples/${selectedSample.id}`);
            setSelectedSample(response.data);
        } catch (e) {
            toast.error(formatApiError(e));
        }
    };

    if (loading) return (
        <div className="p-8 page-enter">
            <div className="animate-pulse space-y-4">
                <div className="h-8 w-64 bg-muted rounded" />
                <div className="flex gap-4">{[1,2,3,4,5,6].map(i => <div key={i} className="h-96 w-56 bg-muted rounded-lg" />)}</div>
            </div>
        </div>
    );

    return (
        <div className="p-6 page-enter" data-testid="crm3-page">
            <CRMSubNav active="samples" />
            <div className="flex items-center justify-between mb-4">
                <div>
                    <h1 className="text-3xl font-heading font-semibold tracking-tight">Pipeline de Amostras</h1>
                    <p className="text-sm text-muted-foreground mt-1">{samples.length} amostras</p>
                </div>
                <ViewSwitcher value={view} onChange={setView} testIdPrefix="crm3" />
            </div>

            {(() => {
                const allVariacoes = STAGES.flatMap((s) => variacoesByStage[s.id] || []);
                const filterFields = [
                    {
                        key: "search",
                        type: "search",
                        placeholder: "Buscar por código, produto, projeto ou cliente...",
                        searchKeys: [
                            (v) => v.codigo,
                            (v) => v.sample_numero,
                            (v) => v.nome_produto,
                            (v) => v.projeto_nome,
                            (v) => v.cliente_nome,
                            (v) => v.descricao_aplicacao,
                        ],
                    },
                    {
                        key: "status",
                        type: "multi",
                        label: "Status",
                        options: STAGES.map((s) => ({ value: s.id, label: s.label })),
                        getter: (v) => v.status,
                    },
                    {
                        key: "cliente_nome",
                        type: "select",
                        label: "Cliente",
                        options: Array.from(new Set(allVariacoes.map((v) => v.cliente_nome).filter(Boolean)))
                            .map((v) => ({ value: v, label: v })),
                        getter: (v) => v.cliente_nome,
                    },
                ];
                const filteredVariacoes = applyFilters(allVariacoes, filters, filterFields);
                const canPrintLabel = authUser && ["admin","lider_pd","formulador","qa","engenharia_produto"].includes(authUser.role);

                const printLabel = async (e, variacaoId, codigo) => {
                    e.stopPropagation();
                    try {
                        const res = await api.get(`/pd/samples/${variacaoId}/label.pdf`, { responseType: "blob" });
                        const url = URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
                        const a = document.createElement("a");
                        a.href = url;
                        a.download = `etiqueta_${String(codigo || variacaoId).replace("/", "-")}.pdf`;
                        a.click();
                        URL.revokeObjectURL(url);
                    } catch { toast.error("Erro ao gerar etiqueta"); }
                };

                const filteredByStage = STAGES.reduce((acc, s) => {
                    acc[s.id] = filteredVariacoes.filter((v) => v.status === s.id);
                    return acc;
                }, {});

                return (
                    <>
                        <FilterBar
                            filters={filters}
                            onChange={setFilters}
                            fields={filterFields}
                            testIdPrefix="crm3-filter"
                        />

                        {view === "kanban" ? (
                <div className="kanban-board" data-testid="crm3-kanban">
                    {STAGES.map((stage) => (
                        <div
                            key={stage.id}
                            className="kanban-column rounded-lg bg-muted/30"
                            data-testid={`crm3-stage-${stage.id}`}
                        >
                            <div className="p-3 border-b border-border">
                                <div className="flex items-center gap-2">
                                    <div className={`w-2 h-2 rounded-full ${stage.color}`} />
                                    <h3 className="font-heading font-medium text-sm truncate">{stage.label}</h3>
                                    <span className="text-xs text-muted-foreground mono-num ml-auto">
                                        {(filteredByStage[stage.id] || []).length}
                                    </span>
                                </div>
                            </div>
                            <div className="p-2 space-y-2 min-h-[200px]">
                                {(filteredByStage[stage.id] || []).map((variacao) => {
                                    const statusLabel = variacao.status_pd_label || STAGE_LABELS[variacao.status] || variacao.status;
                                    return (
                                        <div
                                            key={variacao.id || variacao.sample_id}
                                            className="bg-card border border-border rounded-md p-3 cursor-pointer hover:-translate-y-0.5 hover:shadow-sm transition-transform duration-150"
                                            onClick={() => {
                                                setSelectedSample(variacao.sample_completa);
                                                setSelectedVariacao(variacao);
                                                setTab("briefing");
                                            }}
                                            data-testid={`crm3-card-${variacao.id}`}
                                        >
                                            <div className="flex items-start justify-between gap-2">
                                                <div className="flex-1 min-w-0">
                                                    <div className="flex items-center gap-2 mb-1">
                                                        <span className="px-1.5 py-0.5 bg-primary/10 text-primary rounded text-[10px] font-bold mono-num">
                                                            {String(variacao.codigo || variacao.sample_numero || '?')}
                                                        </span>
                                                    </div>
                                                    <p className="font-body font-medium text-sm truncate">
                                                        {String(variacao.nome_produto || '')}
                                                    </p>
                                                    {variacao.descricao_aplicacao && (
                                                        <p className="text-xs text-muted-foreground mt-1 truncate">
                                                            {String(variacao.descricao_aplicacao)}
                                                        </p>
                                                    )}
                                                    <p className="text-xs text-muted-foreground flex items-center gap-1 mt-1">
                                                        <FlaskConical className="h-3 w-3" />
                                                        {String(variacao.projeto_nome || '')}
                                                    </p>
                                                    <p className="text-xs text-muted-foreground flex items-center gap-1 mt-0.5">
                                                        <Building2 className="h-3 w-3" />
                                                        {String(variacao.cliente_nome || '')}
                                                    </p>
                                                    {/* Badge de status rico do P&D */}
                                                    <div className="flex items-center gap-1 mt-1.5"
                                                         data-testid={`variacao-status-badge-${variacao.id}`}>
                                                        <span className="text-[10px] text-muted-foreground italic truncate max-w-[140px]">
                                                            {statusLabel}
                                                        </span>
                                                        <Lock className="h-2.5 w-2.5 text-muted-foreground/60 shrink-0" title="Status controlado pelo P&D" />
                                                    </div>
                                                    {canPrintLabel && (
                                                        <button
                                                            className="mt-1.5 flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground transition-colors"
                                                            onClick={(e) => printLabel(e, variacao.id, variacao.codigo)}
                                                            title="Imprimir etiqueta"
                                                        >
                                                            <Printer className="h-3 w-3" /> Etiqueta
                                                        </button>
                                                    )}
                                                </div>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    ))}
                </div>
                        ) : (
                            <ListView
                                items={filteredVariacoes}
                                onRowClick={(v) => {
                                    setSelectedSample(v.sample_completa);
                                    setSelectedVariacao(v);
                                    setTab("briefing");
                                }}
                                emptyMessage="Nenhuma amostra/variação corresponde aos filtros."
                                testIdPrefix="crm3-list"
                                getRowId={(v) => v.sample_id + (v.id ? `:${v.id}` : "")}
                                columns={[
                                    { key: "codigo", label: "Código",
                                      render: (v) => (
                                          <span className="font-mono text-xs font-semibold text-primary">
                                              {v.codigo || v.sample_numero || "?"}
                                          </span>
                                      ) },
                                    { key: "nome_produto", label: "Produto",
                                      render: (v) => <span className="font-medium">{v.nome_produto || "—"}</span> },
                                    { key: "descricao_aplicacao", label: "Aplicação",
                                      render: (v) => v.descricao_aplicacao || "—" },
                                    { key: "projeto_nome", label: "Projeto",
                                      render: (v) => v.projeto_nome || "—" },
                                    { key: "cliente_nome", label: "Cliente",
                                      render: (v) => v.cliente_nome || "—" },
                                    { key: "status", label: "Status",
                                      render: (v) => (
                                          <Badge variant="outline" className="text-[10px]">
                                              {STAGE_LABELS[v.status] || v.status}
                                          </Badge>
                                      ) },
                                ]}
                            />
                        )}
                    </>
                );
            })()}

            {/* Sample Detail Sheet */}
            <Sheet open={!!selectedSample} onOpenChange={(v) => { if (!v) { setSelectedSample(null); loadSamples(); } }}>
                <SheetContent className="w-[480px] sm:w-[520px] p-0 flex flex-col" side="right">
                    {selectedSample && (
                        <>
                            <SheetHeader className="p-6 pb-3">
                                <SheetTitle className="font-heading text-xl">
                                    {String(selectedSample?.nome_amostra || selectedSample?.nome_produto || 'Amostra')}
                                </SheetTitle>
                                <div className="flex items-center gap-2 mt-1 flex-wrap">
                                    <Badge variant="outline" className="text-xs">{String(selectedSample?.cliente_nome || '')}</Badge>
                                    <Badge className="text-xs">{String(selectedSample?.projeto_nome || '')}</Badge>
                                    {selectedSample?.codigo_referencia && (
                                        <span className="text-xs mono-num text-muted-foreground">{String(selectedSample.codigo_referencia)}</span>
                                    )}
                                </div>
                            </SheetHeader>
                            <Separator />
                            <Tabs value={tab} onValueChange={setTab} className="flex-1 flex flex-col min-h-0">
                                <TabsList className="mx-6 mt-3">
                                    <TabsTrigger value="briefing">Briefing</TabsTrigger>
                                    <TabsTrigger value="variacoes">Variações</TabsTrigger>
                                    <TabsTrigger value="info">Dados</TabsTrigger>
                                    <TabsTrigger value="retrabalhos">Retrabalhos</TabsTrigger>
                                    <TabsTrigger value="timeline">Histórico</TabsTrigger>
                                </TabsList>

                                <TabsContent value="briefing" className="flex-1 min-h-0 overflow-y-auto px-6 pb-6 mt-3">
                                    <div className="space-y-4">
                                        <div className="space-y-2">
                                            <Label className="text-xs font-semibold">Produto</Label>
                                            <Input defaultValue={selectedSample.produto || ""}
                                                onBlur={(e) => handleUpdateSample(selectedSample.id, { produto: e.target.value })} />
                                        </div>
                                        <div className="space-y-2">
                                            <Label className="text-xs font-semibold">Objetivo do Projeto</Label>
                                            <Textarea defaultValue={selectedSample.objetivo_projeto || ""} rows={3}
                                                onBlur={(e) => handleUpdateSample(selectedSample.id, { objetivo_projeto: e.target.value })} />
                                        </div>
                                        <div className="space-y-2">
                                            <Label className="text-xs font-semibold">Aplicações a Desenvolver</Label>
                                            <Textarea defaultValue={selectedSample.aplicacoes_desenvolver || ""} rows={3}
                                                onBlur={(e) => handleUpdateSample(selectedSample.id, { aplicacoes_desenvolver: e.target.value })} />
                                        </div>
                                        <div className="space-y-2">
                                            <Label className="text-xs font-semibold">Ativos para Claims</Label>
                                            <Textarea defaultValue={selectedSample.ativos_claims || ""} rows={3}
                                                onBlur={(e) => handleUpdateSample(selectedSample.id, { ativos_claims: e.target.value })} />
                                        </div>
                                        <div className="space-y-2">
                                            <Label className="text-xs font-semibold">Referências</Label>
                                            <Textarea defaultValue={selectedSample.referencias || ""} rows={3}
                                                onBlur={(e) => handleUpdateSample(selectedSample.id, { referencias: e.target.value })} />
                                        </div>
                                        <div className="space-y-2">
                                            <Label className="text-xs font-semibold">Referências de Fotos</Label>
                                            {selectedSample.referencias_fotos && selectedSample.referencias_fotos.length > 0 ? (
                                                <div className="grid grid-cols-2 gap-2">
                                                    {selectedSample.referencias_fotos.map((url, idx) => (
                                                        <img key={idx} src={url} alt={`Ref ${idx + 1}`} className="w-full h-32 object-cover rounded border" />
                                                    ))}
                                                </div>
                                            ) : (
                                                <p className="text-xs text-muted-foreground italic">Nenhuma foto de referência</p>
                                            )}
                                        </div>
                                        <div className="space-y-2">
                                            <Label className="text-xs font-semibold">Orçamento do Projeto</Label>
                                            <Input defaultValue={selectedSample.orcamento_projeto || ""}
                                                onBlur={(e) => handleUpdateSample(selectedSample.id, { orcamento_projeto: e.target.value })} />
                                        </div>
                                        <div className="grid grid-cols-3 gap-3">
                                            <div className="space-y-2">
                                                <Label className="text-xs font-semibold">Textura Esperada</Label>
                                                <Input defaultValue={selectedSample.textura_esperada || ""}
                                                    onBlur={(e) => handleUpdateSample(selectedSample.id, { textura_esperada: e.target.value })} />
                                            </div>
                                            <div className="space-y-2">
                                                <Label className="text-xs font-semibold">Sensorial</Label>
                                                <Input defaultValue={selectedSample.sensorial || ""}
                                                    onBlur={(e) => handleUpdateSample(selectedSample.id, { sensorial: e.target.value })} />
                                            </div>
                                            <div className="space-y-2">
                                                <Label className="text-xs font-semibold">pH</Label>
                                                <Input defaultValue={selectedSample.ph || ""}
                                                    onBlur={(e) => handleUpdateSample(selectedSample.id, { ph: e.target.value })} />
                                            </div>
                                        </div>
                                        <div className="space-y-2">
                                            <Label className="text-xs font-semibold">Aplicação</Label>
                                            <Textarea defaultValue={selectedSample.aplicacao || ""} rows={2}
                                                onBlur={(e) => handleUpdateSample(selectedSample.id, { aplicacao: e.target.value })} />
                                        </div>
                                    </div>
                                </TabsContent>

                                <TabsContent value="variacoes" className="flex-1 min-h-0 overflow-y-auto px-6 pb-6 mt-3">
                                    <div className="space-y-3">
                                        <div className="flex items-center justify-between">
                                            <div>
                                                <h4 className="text-sm font-semibold">
                                                    {(selectedSample?.variacoes?.length || 0)} variação(ões)
                                                </h4>
                                                <p className="text-xs text-muted-foreground">Amostra #{selectedSample?.numero_amostra || '?'}</p>
                                            </div>
                                            <Button size="sm" onClick={() => setShowAddVariacoes(true)} data-testid="btn-add-variacao">
                                                <Plus className="h-4 w-4 mr-1" /> Adicionar Variação
                                            </Button>
                                        </div>
                                        {(selectedSample?.variacoes || []).map((v) => {
                                            const vForm = resultadoForm[v.id] || {};
                                            const statusLabel = v.status_pd_label || STAGE_LABELS[v.status] || v.status;
                                            return (
                                            <div key={v.id} className="border border-border rounded-lg p-3 space-y-2 bg-card">
                                                <div className="flex items-center justify-between">
                                                    <div className="flex items-center gap-2 flex-wrap">
                                                        <span className="px-2 py-0.5 bg-primary/10 text-primary rounded text-xs font-bold mono-num">
                                                            {v.codigo}
                                                        </span>
                                                        {/* Status badge read-only — controlado pelo P&D */}
                                                        <span
                                                            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-medium border border-border bg-muted/50 text-muted-foreground"
                                                            data-testid={`variacao-status-badge-${v.id}`}
                                                            title="Status controlado pelo setor P&D"
                                                        >
                                                            {statusLabel}
                                                            <Lock className="h-2.5 w-2.5 shrink-0" />
                                                        </span>
                                                        {v.sku_id && <Badge className="text-[10px] bg-emerald-500">SKU</Badge>}
                                                    </div>
                                                    <Button
                                                        variant="ghost" size="icon"
                                                        className="h-7 w-7 text-destructive hover:text-destructive hover:bg-destructive/10"
                                                        onClick={() => handleDeleteVariacao(selectedSample.id, v.id, v.codigo)}
                                                        disabled={v.sku_id || (selectedSample.variacoes.length <= 1)}
                                                        title={v.sku_id ? "Não pode excluir: já gerou SKU" : (selectedSample.variacoes.length <= 1 ? "Última variação" : "Excluir variação")}
                                                        data-testid={`btn-delete-variacao-${v.id}`}
                                                    >
                                                        <Trash2 className="h-3.5 w-3.5" />
                                                    </Button>
                                                </div>
                                                <div className="grid grid-cols-2 gap-2">
                                                    <div className="space-y-1 col-span-2">
                                                        <Label className="text-[10px] text-muted-foreground">Descrição da Aplicação</Label>
                                                        <Input
                                                            defaultValue={v.descricao_aplicacao || ""}
                                                            className="h-8 text-xs"
                                                            onBlur={(e) => {
                                                                if (e.target.value !== (v.descricao_aplicacao || ""))
                                                                    handleUpdateVariacao(selectedSample.id, v.id, { descricao_aplicacao: e.target.value });
                                                            }}
                                                        />
                                                    </div>
                                                    <div className="space-y-1">
                                                        <Label className="text-[10px] text-muted-foreground">% Fragrância</Label>
                                                        <Input
                                                            type="number" step="0.01"
                                                            defaultValue={v.percentual_fragrancia ?? ""}
                                                            className="h-8 text-xs"
                                                            onBlur={(e) => {
                                                                const val = e.target.value === "" ? null : parseFloat(e.target.value);
                                                                if (val !== v.percentual_fragrancia)
                                                                    handleUpdateVariacao(selectedSample.id, v.id, { percentual_fragrancia: val });
                                                            }}
                                                        />
                                                    </div>
                                                    <div className="space-y-1">
                                                        <Label className="text-[10px] text-muted-foreground">Ref. Fragrância</Label>
                                                        <Input
                                                            defaultValue={v.referencia_fragrancia || ""}
                                                            className="h-8 text-xs"
                                                            onBlur={(e) => {
                                                                if (e.target.value !== (v.referencia_fragrancia || ""))
                                                                    handleUpdateVariacao(selectedSample.id, v.id, { referencia_fragrancia: e.target.value });
                                                            }}
                                                        />
                                                    </div>
                                                    <div className="space-y-1">
                                                        <Label className="text-[10px] text-muted-foreground">Custo Frag. (R$/kg)</Label>
                                                        <Input
                                                            type="number" step="0.01"
                                                            defaultValue={v.custo_fragrancia ?? ""}
                                                            className="h-8 text-xs"
                                                            onBlur={(e) => {
                                                                const val = e.target.value === "" ? null : parseFloat(e.target.value);
                                                                if (val !== v.custo_fragrancia)
                                                                    handleUpdateVariacao(selectedSample.id, v.id, { custo_fragrancia: val });
                                                            }}
                                                        />
                                                    </div>
                                                    <div className="space-y-1 col-span-2">
                                                        <Label className="text-[10px] text-muted-foreground">Observações</Label>
                                                        <Textarea
                                                            defaultValue={v.observacoes_especificas || ""}
                                                            rows={2}
                                                            className="text-xs"
                                                            onBlur={(e) => {
                                                                if (e.target.value !== (v.observacoes_especificas || ""))
                                                                    handleUpdateVariacao(selectedSample.id, v.id, { observacoes_especificas: e.target.value });
                                                            }}
                                                        />
                                                    </div>
                                                </div>
                                                {/* Registrar resultado do cliente — somente quando variação está em "enviada" */}
                                                {v.status === "enviada" && (
                                                    <div
                                                        className="mt-3 p-3 border border-purple-200 rounded-lg bg-purple-50 dark:bg-purple-950/20"
                                                        data-testid="resultado-cliente-section"
                                                    >
                                                        <p className="text-xs font-semibold text-purple-800 dark:text-purple-300 mb-2">
                                                            Registrar resultado do cliente
                                                        </p>
                                                        <div className="flex flex-col gap-1.5 mb-2">
                                                            {["aprovada", "reprovada", "retrabalho"].map(opt => (
                                                                <label
                                                                    key={opt}
                                                                    className={`flex items-center gap-2 px-2 py-1.5 rounded-md cursor-pointer border text-xs font-medium capitalize transition-colors ${
                                                                        vForm.resultado === opt
                                                                            ? "border-purple-500 bg-purple-100 dark:bg-purple-900/30 text-purple-800 dark:text-purple-200"
                                                                            : "border-border bg-card hover:border-purple-300"
                                                                    }`}
                                                                    data-testid={`resultado-option-${opt}`}
                                                                >
                                                                    <input
                                                                        type="radio"
                                                                        name={`resultado-${v.id}`}
                                                                        value={opt}
                                                                        checked={vForm.resultado === opt}
                                                                        onChange={() => setResultadoForm(prev => ({
                                                                            ...prev,
                                                                            [v.id]: { ...prev[v.id], resultado: opt }
                                                                        }))}
                                                                        className="accent-purple-600"
                                                                    />
                                                                    {opt}
                                                                </label>
                                                            ))}
                                                        </div>
                                                        {(vForm.resultado === "retrabalho" || vForm.resultado === "reprovada") && (
                                                            <Textarea
                                                                className="text-xs mb-2"
                                                                rows={2}
                                                                placeholder="Feedback do cliente (obrigatório para retrabalho)..."
                                                                value={vForm.feedback || ""}
                                                                onChange={(e) => setResultadoForm(prev => ({
                                                                    ...prev,
                                                                    [v.id]: { ...prev[v.id], feedback: e.target.value }
                                                                }))}
                                                                data-testid="feedback-cliente-input"
                                                            />
                                                        )}
                                                        <Button
                                                            size="sm"
                                                            className="w-full bg-purple-600 hover:bg-purple-700 text-white text-xs"
                                                            onClick={() => handleResultadoCliente(selectedSample.id, v.id)}
                                                            disabled={!vForm.resultado || vForm.loading}
                                                            data-testid="btn-confirmar-resultado-cliente"
                                                        >
                                                            {vForm.loading ? "Registrando..." : "Confirmar Resultado"}
                                                        </Button>
                                                    </div>
                                                )}
                                            </div>
                                        );
                                        })}
                                        {(!selectedSample?.variacoes || selectedSample.variacoes.length === 0) && (
                                            <p className="text-sm text-muted-foreground italic">Nenhuma variação (modelo antigo).</p>
                                        )}

                                        <Separator className="my-4" />
                                        <Button
                                            variant="outline"
                                            className="w-full text-destructive hover:text-destructive border-destructive/30"
                                            onClick={handleDeleteSample}
                                            data-testid="btn-delete-sample"
                                        >
                                            <Trash2 className="h-4 w-4 mr-2" /> Excluir Amostra Inteira
                                        </Button>
                                    </div>
                                </TabsContent>

                                <TabsContent value="info" className="flex-1 min-h-0 overflow-y-auto px-6 pb-6 mt-3">
                                    <div className="space-y-4">
                                        <div className="space-y-2">
                                            <Label className="text-xs">Observação Técnica</Label>
                                            <Textarea defaultValue={selectedSample.observacao_tecnica} rows={3}
                                                onBlur={(e) => { if (e.target.value !== selectedSample.observacao_tecnica) handleUpdateSample(selectedSample.id, { observacao_tecnica: e.target.value }); }} />
                                        </div>
                                        <div className="space-y-2">
                                            <Label className="text-xs">Data de Envio</Label>
                                            <Input type="date" defaultValue={selectedSample.data_envio || ""}
                                                onBlur={(e) => handleUpdateSample(selectedSample.id, { data_envio: e.target.value })} />
                                        </div>
                                        <div className="space-y-2">
                                            <Label className="text-xs">Feedback do Cliente</Label>
                                            <Textarea defaultValue={selectedSample.feedback_cliente} rows={3}
                                                onBlur={(e) => { if (e.target.value !== selectedSample.feedback_cliente) handleUpdateSample(selectedSample.id, { feedback_cliente: e.target.value }); }} />
                                        </div>
                                    </div>
                                </TabsContent>

                                <TabsContent value="retrabalhos" className="flex-1 min-h-0 overflow-y-auto px-6 pb-6 mt-3">
                                    <div className="space-y-3">
                                        {(selectedSample.historico_retrabalhos || []).length === 0 && (
                                            <p className="text-sm text-muted-foreground">Nenhum retrabalho registrado.</p>
                                        )}
                                        {(selectedSample.historico_retrabalhos || []).slice().reverse().map((r, idx) => (
                                            <div key={idx} className="border border-border rounded-lg p-3 bg-amber-50/50 dark:bg-amber-950/20">
                                                <div className="flex items-center gap-2 mb-1">
                                                    <AlertTriangle className="h-3.5 w-3.5 text-amber-500" />
                                                    <span className="text-xs font-semibold uppercase tracking-wider text-amber-600 dark:text-amber-400">
                                                        {r.origem === "externa" ? "Externa" : "Interna"}
                                                    </span>
                                                    <span className="text-xs text-muted-foreground ml-auto mono-num">
                                                        {new Date(r.data).toLocaleDateString("pt-BR")}
                                                    </span>
                                                </div>
                                                <p className="text-sm">{r.motivo}</p>
                                            </div>
                                        ))}
                                    </div>
                                </TabsContent>

                                <TabsContent value="timeline" className="flex-1 min-h-0 overflow-y-auto px-6 pb-6 mt-3">
                                    <div className="space-y-3">
                                        {(selectedSample.historico_movimentacoes || []).slice().reverse().map((mov, idx) => (
                                            <div key={idx} className="flex gap-3 items-start">
                                                <div className="mt-1 w-2 h-2 rounded-full bg-primary shrink-0" />
                                                <div>
                                                    <p className="text-sm">
                                                        <span className="font-medium">{STAGE_LABELS[mov.de] || mov.de}</span>
                                                        <ChevronRight className="h-3 w-3 inline mx-1" />
                                                        <span className="font-medium">{STAGE_LABELS[mov.para] || mov.para}</span>
                                                    </p>
                                                    <p className="text-xs text-muted-foreground">
                                                        {mov.usuario} · {new Date(mov.data).toLocaleString("pt-BR")}
                                                    </p>
                                                </div>
                                            </div>
                                        ))}
                                        {(!selectedSample.historico_movimentacoes || selectedSample.historico_movimentacoes.length === 0) && (
                                            <p className="text-sm text-muted-foreground">Nenhuma movimentação.</p>
                                        )}
                                    </div>
                                </TabsContent>
                            </Tabs>
                        </>
                    )}
                </SheetContent>
            </Sheet>

            {/* Add Variações Modal */}
            <Dialog open={showAddVariacoes} onOpenChange={setShowAddVariacoes}>
                <DialogContent className="max-w-2xl max-h-[85vh] overflow-hidden flex flex-col">
                    <DialogHeader>
                        <DialogTitle className="font-heading flex items-center gap-2">
                            <Plus className="h-5 w-5 text-primary" />
                            Adicionar Variações — Amostra #{selectedSample?.numero_amostra}
                        </DialogTitle>
                    </DialogHeader>
                    <div className="flex-1 overflow-y-auto space-y-3 p-1">
                        {newVariacoes.map((v, idx) => {
                            const existingCount = selectedSample?.variacoes?.length || 0;
                            const nextLetter = String.fromCharCode(65 + existingCount + idx);
                            return (
                                <div key={idx} className="border border-border rounded-lg p-3 space-y-3 bg-muted/20">
                                    <div className="flex items-center justify-between">
                                        <h4 className="text-sm font-semibold">
                                            Variação {selectedSample?.numero_amostra}/{nextLetter}
                                        </h4>
                                        {newVariacoes.length > 1 && (
                                            <Button
                                                variant="ghost" size="icon" className="h-7 w-7"
                                                onClick={() => setNewVariacoes(newVariacoes.filter((_, i) => i !== idx))}
                                            >
                                                <X className="h-4 w-4" />
                                            </Button>
                                        )}
                                    </div>
                                    <div className="grid grid-cols-2 gap-3">
                                        <div className="col-span-2 space-y-1">
                                            <Label className="text-xs">Descrição da Aplicação *</Label>
                                            <Input
                                                value={v.descricao_aplicacao}
                                                onChange={(e) => {
                                                    const list = [...newVariacoes];
                                                    list[idx].descricao_aplicacao = e.target.value;
                                                    setNewVariacoes(list);
                                                }}
                                                placeholder="Ex: Shampoo masculino amadeirado"
                                            />
                                        </div>
                                        <div className="space-y-1">
                                            <Label className="text-xs">% Fragrância</Label>
                                            <Input
                                                type="number" step="0.01"
                                                value={v.percentual_fragrancia}
                                                onChange={(e) => {
                                                    const list = [...newVariacoes];
                                                    list[idx].percentual_fragrancia = e.target.value;
                                                    setNewVariacoes(list);
                                                }}
                                            />
                                        </div>
                                        <div className="space-y-1">
                                            <Label className="text-xs">Referência Fragrância</Label>
                                            <Input
                                                value={v.referencia_fragrancia}
                                                onChange={(e) => {
                                                    const list = [...newVariacoes];
                                                    list[idx].referencia_fragrancia = e.target.value;
                                                    setNewVariacoes(list);
                                                }}
                                            />
                                        </div>
                                        <div className="space-y-1">
                                            <Label className="text-xs">Custo Fragrância (R$/kg)</Label>
                                            <Input
                                                type="number" step="0.01"
                                                value={v.custo_fragrancia}
                                                onChange={(e) => {
                                                    const list = [...newVariacoes];
                                                    list[idx].custo_fragrancia = e.target.value;
                                                    setNewVariacoes(list);
                                                }}
                                            />
                                        </div>
                                        <div className="col-span-2 space-y-1">
                                            <Label className="text-xs">Observações Específicas</Label>
                                            <Textarea
                                                rows={2}
                                                value={v.observacoes_especificas}
                                                onChange={(e) => {
                                                    const list = [...newVariacoes];
                                                    list[idx].observacoes_especificas = e.target.value;
                                                    setNewVariacoes(list);
                                                }}
                                            />
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                        <Button
                            variant="outline" size="sm" className="w-full"
                            onClick={() => setNewVariacoes([...newVariacoes, {
                                descricao_aplicacao: "",
                                percentual_fragrancia: "",
                                referencia_fragrancia: "",
                                custo_fragrancia: "",
                                observacoes_especificas: ""
                            }])}
                        >
                            <Plus className="h-4 w-4 mr-1" /> Adicionar outra variação
                        </Button>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setShowAddVariacoes(false)}>Cancelar</Button>
                        <Button onClick={handleAddVariacoesSubmit} data-testid="btn-submit-add-variacoes">
                            Adicionar {newVariacoes.length} variação(ões)
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
