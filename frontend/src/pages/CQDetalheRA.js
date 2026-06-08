import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Download, Send, Loader2, ChevronRight, Check, X, ClipboardList } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

const STATUS_COLORS = {
    rascunho: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
    em_analise: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
    aprovado: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
    reprovado: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
    concessao: "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200",
};

const STATUS_LABELS = {
    rascunho: "Rascunho",
    em_analise: "Em Análise",
    aprovado: "Aprovado",
    reprovado: "Reprovado",
    concessao: "Concessão",
};

export default function CQDetalheRA() {
    const { id } = useParams();
    const navigate = useNavigate();
    const { user } = useAuth();
    const [ra, setRa] = useState(null);
    const [parametros, setParametros] = useState([]);
    const [loading, setLoading] = useState(true);
    const [checklists, setChecklists] = useState([]);
    const [showAprovar, setShowAprovar] = useState(false);
    const [showEnvio, setShowEnvio] = useState(false);
    const [aprovDecisao, setAprovDecisao] = useState("aprovado");
    const [aprovDisposicao, setAprovDisposicao] = useState("");
    const [aprovJustificativa, setAprovJustificativa] = useState("");
    const [aprovObs, setAprovObs] = useState("");
    const [aprovSaving, setAprovSaving] = useState(false);
    const [envioCliente, setEnvioCliente] = useState("");
    const [envioCanal, setEnvioCanal] = useState("");
    const [envioObs, setEnvioObs] = useState("");
    const [envioSaving, setEnvioSaving] = useState(false);
    const [localResults, setLocalResults] = useState({});

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const { data } = await api.get(`/cq/registros-analise/${id}`);
            setRa(data);
            const params = data.parametros ?? data.parametros_analise ?? [];
            setParametros(params);
            const initResults = {};
            params.forEach(p => {
                initResults[p.id] = { resultado: p.resultado ?? "", observacao: p.observacao ?? "" };
            });
            setLocalResults(initResults);
            const ckRes = await api.get("/cq/checklists", { params: { ra_id: id, limit: 50 } });
            const ckData = ckRes.data;
            setChecklists(Array.isArray(ckData) ? ckData : (ckData?.items ?? []));
        } catch (e) {
            toast.error("Erro ao carregar registro de análise");
        } finally {
            setLoading(false);
        }
    }, [id]);

    useEffect(() => { load(); }, [load]);

    const computeConforme = (param, resultadoStr) => {
        const val = parseFloat(resultadoStr);
        if (isNaN(val)) return null;
        const { esp_min, esp_max } = param;
        if (esp_min != null && esp_max != null) {
            return val >= parseFloat(esp_min) && val <= parseFloat(esp_max);
        }
        return null;
    };

    const saveParam = async (paramId, field, value) => {
        try {
            const current = localResults[paramId] || {};
            const payload = { parametros: [{ id: paramId, ...current, [field]: value }] };
            await api.put(`/cq/registros-analise/${id}/parametros`, payload);
        } catch (e) {
            toast.error("Erro ao salvar parâmetro");
        }
    };

    const handleAprovar = async () => {
        setAprovSaving(true);
        try {
            const payload = { decisao: aprovDecisao, observacoes: aprovObs };
            if (aprovDecisao === "reprovado") {
                payload.disposicao_imediata = aprovDisposicao;
            }
            if (aprovDecisao === "concessao") {
                if (!aprovJustificativa.trim()) {
                    toast.error("Justificativa de concessão é obrigatória");
                    setAprovSaving(false);
                    return;
                }
                payload.justificativa_concessao = aprovJustificativa;
            }
            await api.post(`/cq/registros-analise/${id}/aprovar`, payload);
            toast.success("Decisão registrada com sucesso!");
            setShowAprovar(false);
            load();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Erro ao registrar decisão");
        } finally {
            setAprovSaving(false);
        }
    };

    const handleDownloadCoa = async (tipo_coa) => {
        try {
            const res = await api.get(`/cq/registros-analise/${id}/coa`, {
                params: { tipo_coa },
                responseType: "blob",
            });
            const url = window.URL.createObjectURL(new Blob([res.data]));
            const link = document.createElement("a");
            link.href = url;
            link.setAttribute("download", `CoA_${tipo_coa}_${ra?.numero_ra || id}.pdf`);
            document.body.appendChild(link);
            link.click();
            link.remove();
            window.URL.revokeObjectURL(url);
        } catch (e) {
            toast.error("Erro ao gerar CoA");
        }
    };

    const handleEnvio = async () => {
        setEnvioSaving(true);
        try {
            await api.post(`/cq/registros-analise/${id}/registrar-envio-coa`, {
                cliente_nome: envioCliente,
                canal: envioCanal,
                observacoes: envioObs,
            });
            toast.success("Envio registrado!");
            setShowEnvio(false);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Erro ao registrar envio");
        } finally {
            setEnvioSaving(false);
        }
    };

    if (loading) {
        return (
            <div className="p-6 flex items-center justify-center h-64">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
        );
    }

    if (!ra) {
        return (
            <div className="p-6">
                <p className="text-muted-foreground">Registro não encontrado.</p>
                <Button variant="outline" className="mt-4" onClick={() => navigate("/cq/registros-analise")}>
                    Voltar
                </Button>
            </div>
        );
    }

    const isEmAnalise = ra.status === "em_analise";
    const isAprovadoConcessao = ra.status === "aprovado" || ra.status === "concessao";

    return (
        <div className="p-6 page-enter" data-testid="cq-detalhe-ra">
            {/* Breadcrumb */}
            <div className="flex items-center gap-2 text-sm text-muted-foreground mb-4">
                <button onClick={() => navigate("/cq/registros-analise")} className="hover:text-foreground transition-colors">
                    Registros de Análise
                </button>
                <ChevronRight className="h-4 w-4" />
                <span className="text-foreground font-medium">{ra.numero_ra}</span>
            </div>

            {/* Header */}
            <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 mb-6">
                <div>
                    <div className="flex items-center gap-3 mb-2">
                        <h1 className="text-2xl font-heading font-bold">{ra.numero_ra}</h1>
                        <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold ${STATUS_COLORS[ra.status] || ""}`}>
                            {STATUS_LABELS[ra.status] || ra.status}
                        </span>
                    </div>
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-1 text-sm">
                        <div><span className="text-muted-foreground">Tipo: </span>{ra.tipo}</div>
                        <div><span className="text-muted-foreground">Item: </span><span className="font-medium">{ra.item_nome}</span></div>
                        <div><span className="text-muted-foreground">Fornecedor: </span>{ra.fornecedor_nome || "—"}</div>
                        <div><span className="text-muted-foreground">Lote: </span>{ra.lote_numero || "—"}</div>
                        <div><span className="text-muted-foreground">NF: </span>{ra.nf_numero || "—"}</div>
                        <div><span className="text-muted-foreground">Data NF: </span>{ra.nf_data ? new Date(ra.nf_data).toLocaleDateString("pt-BR") : "—"}</div>
                        <div><span className="text-muted-foreground">Qtd: </span>{ra.quantidade_recebida != null ? `${ra.quantidade_recebida} ${ra.unidade || ""}` : "—"}</div>
                    </div>
                </div>
                <div className="flex flex-wrap gap-2">
                    {isEmAnalise && (
                        <Button onClick={() => setShowAprovar(true)} data-testid="btn-aprovar">
                            Aprovar / Reprovar
                        </Button>
                    )}
                    {isAprovadoConcessao && (
                        <>
                            <Button variant="outline" onClick={() => handleDownloadCoa("interno")} data-testid="btn-coa-interno">
                                <Download className="h-4 w-4 mr-2" /> CoA Interno
                            </Button>
                            <Button variant="outline" onClick={() => handleDownloadCoa("comercial")} data-testid="btn-coa-comercial">
                                <Download className="h-4 w-4 mr-2" /> CoA Comercial
                            </Button>
                            <Button variant="outline" onClick={() => setShowEnvio(true)}>
                                <Send className="h-4 w-4 mr-2" /> Registrar Envio
                            </Button>
                        </>
                    )}
                </div>
            </div>

            {/* Parameter Table */}
            <div className="rounded-lg border border-border overflow-hidden" data-testid="tabela-parametros">
                <div className="bg-muted/50 px-4 py-3 border-b border-border">
                    <h2 className="font-heading font-semibold">Parâmetros de Análise</h2>
                </div>
                <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead className="bg-muted/30">
                            <tr>
                                <th className="text-left px-4 py-2 font-medium text-muted-foreground">Parâmetro</th>
                                <th className="text-left px-4 py-2 font-medium text-muted-foreground">Unidade</th>
                                <th className="text-left px-4 py-2 font-medium text-muted-foreground">Método</th>
                                <th className="text-left px-4 py-2 font-medium text-muted-foreground">Especificação</th>
                                <th className="text-left px-4 py-2 font-medium text-muted-foreground">Resultado</th>
                                <th className="text-left px-4 py-2 font-medium text-muted-foreground">Conforme</th>
                                <th className="text-left px-4 py-2 font-medium text-muted-foreground">Observação</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-border">
                            {parametros.length === 0 ? (
                                <tr>
                                    <td colSpan={7} className="text-center py-8 text-muted-foreground">
                                        Nenhum parâmetro cadastrado.
                                    </td>
                                </tr>
                            ) : parametros.map((param) => {
                                const localVal = localResults[param.id] || {};
                                const resultado = localVal.resultado ?? "";
                                const observacao = localVal.observacao ?? "";
                                const conforme = computeConforme(param, resultado);
                                const rowBg = conforme === true
                                    ? "bg-green-50 dark:bg-green-950/20"
                                    : conforme === false
                                    ? "bg-red-50 dark:bg-red-950/20"
                                    : "";
                                const espStr = param.esp_min != null && param.esp_max != null
                                    ? `${param.esp_min} – ${param.esp_max}`
                                    : (param.especificacao || "—");
                                return (
                                    <tr key={param.id} className={rowBg}>
                                        <td className="px-4 py-2 font-medium">{param.nome || param.parametro}</td>
                                        <td className="px-4 py-2 text-xs">{param.unidade || "—"}</td>
                                        <td className="px-4 py-2 text-xs">{param.metodo || "—"}</td>
                                        <td className="px-4 py-2 text-xs">{espStr}</td>
                                        <td className="px-4 py-2">
                                            <Input
                                                type="number"
                                                className="w-28 h-7 text-xs"
                                                value={resultado}
                                                data-testid={`param-resultado-${param.id}`}
                                                onChange={(e) => setLocalResults(prev => ({
                                                    ...prev,
                                                    [param.id]: { ...prev[param.id], resultado: e.target.value }
                                                }))}
                                                onBlur={(e) => saveParam(param.id, "resultado", e.target.value)}
                                            />
                                        </td>
                                        <td className="px-4 py-2">
                                            {conforme === true && <Check className="h-4 w-4 text-green-600" />}
                                            {conforme === false && <X className="h-4 w-4 text-red-600" />}
                                            {conforme === null && <span className="text-muted-foreground text-xs">—</span>}
                                        </td>
                                        <td className="px-4 py-2">
                                            <Input
                                                className="w-40 h-7 text-xs"
                                                value={observacao}
                                                data-testid={`param-observacao-${param.id}`}
                                                onChange={(e) => setLocalResults(prev => ({
                                                    ...prev,
                                                    [param.id]: { ...prev[param.id], observacao: e.target.value }
                                                }))}
                                                onBlur={(e) => saveParam(param.id, "observacao", e.target.value)}
                                            />
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            </div>

            {/* Resultado Geral */}
            {ra.resultado_geral && (
                <div className="mt-4 flex items-center gap-2">
                    <span className="text-sm font-medium text-muted-foreground">Resultado Geral:</span>
                    <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold ${ra.resultado_geral === "conforme" ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200" : "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200"}`}>
                        {ra.resultado_geral === "conforme" ? "Conforme" : "Não Conforme"}
                    </span>
                </div>
            )}

            {/* Checklists vinculados */}
            <div className="mt-6">
                <div className="flex items-center gap-2 mb-3">
                    <ClipboardList className="h-4 w-4 text-muted-foreground" />
                    <h2 className="font-heading font-semibold">Checklists Vinculados</h2>
                </div>
                {checklists.length === 0 ? (
                    <p className="text-sm text-muted-foreground">Nenhum checklist vinculado a este Registro de Análise.</p>
                ) : (
                    <div className="rounded-lg border border-border overflow-hidden">
                        <table className="w-full text-sm">
                            <thead className="bg-muted/50">
                                <tr>
                                    <th className="text-left px-4 py-2 font-medium text-muted-foreground">Nº CK</th>
                                    <th className="text-left px-4 py-2 font-medium text-muted-foreground">Tipo</th>
                                    <th className="text-left px-4 py-2 font-medium text-muted-foreground">Nome</th>
                                    <th className="text-left px-4 py-2 font-medium text-muted-foreground">Status</th>
                                    <th className="px-4 py-2" />
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-border">
                                {checklists.map(ck => (
                                    <tr
                                        key={ck.id}
                                        className="hover:bg-accent/40 cursor-pointer transition-colors"
                                        onClick={() => navigate(`/cq/checklists/${ck.id}`)}
                                    >
                                        <td className="px-4 py-2 font-mono text-xs font-medium">{ck.numero_ck}</td>
                                        <td className="px-4 py-2">
                                            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300">
                                                {ck.tipo}
                                            </span>
                                        </td>
                                        <td className="px-4 py-2 text-sm">{ck.nome || <span className="text-muted-foreground">—</span>}</td>
                                        <td className="px-4 py-2">
                                            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${
                                                ck.status === "aprovado" ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
                                                : ck.status === "reprovado" ? "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200"
                                                : "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200"
                                            }`}>
                                                {ck.status === "aprovado" ? "Aprovado" : ck.status === "reprovado" ? "Reprovado" : "Em Preenchimento"}
                                            </span>
                                        </td>
                                        <td className="px-4 py-2"><ChevronRight className="h-4 w-4 text-muted-foreground" /></td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>

            {/* Aprovar Modal */}
            <Dialog open={showAprovar} onOpenChange={setShowAprovar}>
                <DialogContent className="max-w-md" data-testid="modal-aprovar">
                    <DialogHeader>
                        <DialogTitle className="font-heading">Registrar Decisão</DialogTitle>
                    </DialogHeader>
                    <div className="space-y-4">
                        <div className="space-y-2">
                            <Label>Decisão *</Label>
                            <div className="flex flex-col gap-2">
                                {[
                                    { value: "aprovado", label: "Aprovado" },
                                    { value: "reprovado", label: "Reprovado" },
                                    { value: "concessao", label: "Com Concessão" },
                                ].map((opt) => (
                                    <label key={opt.value} className="flex items-center gap-2 cursor-pointer">
                                        <input
                                            type="radio"
                                            name="aprovDecisao"
                                            value={opt.value}
                                            checked={aprovDecisao === opt.value}
                                            onChange={() => setAprovDecisao(opt.value)}
                                        />
                                        <span className="text-sm">{opt.label}</span>
                                    </label>
                                ))}
                            </div>
                        </div>
                        {aprovDecisao === "reprovado" && (
                            <div className="space-y-2">
                                <Label>Disposição Imediata</Label>
                                <Select value={aprovDisposicao} onValueChange={setAprovDisposicao}>
                                    <SelectTrigger><SelectValue placeholder="Selecionar" /></SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="devolucao">Devolução</SelectItem>
                                        <SelectItem value="descarte">Descarte</SelectItem>
                                        <SelectItem value="reprocesso">Reprocesso</SelectItem>
                                        <SelectItem value="concessao">Concessão</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                        )}
                        {aprovDecisao === "concessao" && (
                            <div className="space-y-2">
                                <Label>Justificativa da Concessão *</Label>
                                <Textarea
                                    rows={3}
                                    value={aprovJustificativa}
                                    onChange={(e) => setAprovJustificativa(e.target.value)}
                                    placeholder="Descreva a justificativa para a concessão..."
                                />
                            </div>
                        )}
                        <div className="space-y-2">
                            <Label>Observações</Label>
                            <Textarea
                                rows={3}
                                value={aprovObs}
                                onChange={(e) => setAprovObs(e.target.value)}
                                placeholder="Observações adicionais..."
                            />
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setShowAprovar(false)}>Cancelar</Button>
                        <Button onClick={handleAprovar} disabled={aprovSaving}>
                            {aprovSaving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                            Confirmar
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Envio Modal */}
            <Dialog open={showEnvio} onOpenChange={setShowEnvio}>
                <DialogContent className="max-w-md">
                    <DialogHeader>
                        <DialogTitle className="font-heading">Registrar Envio de CoA</DialogTitle>
                    </DialogHeader>
                    <div className="space-y-4">
                        <div className="space-y-2">
                            <Label>Cliente *</Label>
                            <Input value={envioCliente} onChange={(e) => setEnvioCliente(e.target.value)} placeholder="Nome do cliente" />
                        </div>
                        <div className="space-y-2">
                            <Label>Canal</Label>
                            <Select value={envioCanal} onValueChange={setEnvioCanal}>
                                <SelectTrigger><SelectValue placeholder="Selecionar canal" /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="email">E-mail</SelectItem>
                                    <SelectItem value="whatsapp">WhatsApp</SelectItem>
                                    <SelectItem value="portal">Portal</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        <div className="space-y-2">
                            <Label>Observações</Label>
                            <Textarea rows={3} value={envioObs} onChange={(e) => setEnvioObs(e.target.value)} />
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setShowEnvio(false)}>Cancelar</Button>
                        <Button onClick={handleEnvio} disabled={envioSaving || !envioCliente.trim()}>
                            {envioSaving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                            <Send className="h-4 w-4 mr-2" /> Registrar
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
