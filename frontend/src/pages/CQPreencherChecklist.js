import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Loader2, ChevronRight, Check, X, AlertTriangle } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

const CQ_FULL = ["admin", "qa", "lider_pd"];
const CQ_ANALISTA = ["admin", "qa", "lider_pd", "formulador"];
const hasRole = (user, roles) => roles.includes(user?.role);

const STATUS_COLORS = {
    em_preenchimento: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200",
    aprovado: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
    reprovado: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
};

export default function CQPreencherChecklist() {
    const { id } = useParams();
    const navigate = useNavigate();
    const { user } = useAuth();
    const [ck, setCk] = useState(null);
    const [itens, setItens] = useState([]);
    const [loading, setLoading] = useState(true);
    const [openSections, setOpenSections] = useState({});
    const [localState, setLocalState] = useState({});
    const [showAprovar, setShowAprovar] = useState(false);
    const [aprovDecisao, setAprovDecisao] = useState("aprovado");
    const [aprovObs, setAprovObs] = useState("");
    const [aprovSaving, setAprovSaving] = useState(false);

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const { data } = await api.get(`/cq/checklists/${id}`);
            setCk(data);
            const listaItens = data.itens ?? data.items ?? [];
            setItens(listaItens);
            // init all sections open
            const sections = {};
            const localInit = {};
            listaItens.forEach(item => {
                if (item.secao) sections[item.secao] = true;
                localInit[item.id] = {
                    resposta: item.resposta ?? null,
                    nc_classificacao: item.nc_classificacao ?? "",
                    acao_imediata: item.acao_imediata ?? "",
                    observacao: item.observacao ?? "",
                };
            });
            setOpenSections(sections);
            setLocalState(localInit);
        } catch (e) {
            toast.error("Erro ao carregar checklist");
        } finally {
            setLoading(false);
        }
    }, [id]);

    useEffect(() => { load(); }, [load]);

    const putItem = async (itemId, updates) => {
        try {
            await api.put(`/cq/checklists/${id}/itens/${itemId}`, updates);
        } catch (e) {
            toast.error("Erro ao salvar item");
        }
    };

    const handleSNNA = async (item, resposta) => {
        const current = localState[item.id] || {};
        const next = { ...current, resposta };
        setLocalState(prev => ({ ...prev, [item.id]: next }));
        await putItem(item.id, next);
    };

    const handleFieldBlur = async (itemId, field, value) => {
        const current = localState[itemId] || {};
        const next = { ...current, [field]: value };
        setLocalState(prev => ({ ...prev, [itemId]: next }));
        await putItem(itemId, next);
    };

    const handleFieldChange = (itemId, field, value) => {
        setLocalState(prev => ({
            ...prev,
            [itemId]: { ...prev[itemId], [field]: value }
        }));
    };

    const handleAprovar = async () => {
        setAprovSaving(true);
        try {
            await api.post(`/cq/checklists/${id}/aprovar`, { decisao: aprovDecisao, observacoes: aprovObs });
            toast.success("Checklist " + (aprovDecisao === "aprovado" ? "aprovado" : "reprovado") + "!");
            setShowAprovar(false);
            load();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Erro ao aprovar checklist");
        } finally {
            setAprovSaving(false);
        }
    };

    const toggleSection = (secao) => {
        setOpenSections(prev => ({ ...prev, [secao]: !prev[secao] }));
    };

    if (loading) {
        return (
            <div className="p-6 flex items-center justify-center h-64">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
        );
    }

    if (!ck) {
        return (
            <div className="p-6">
                <p className="text-muted-foreground">Checklist não encontrado.</p>
                <Button variant="outline" className="mt-4" onClick={() => navigate("/cq/checklists")}>Voltar</Button>
            </div>
        );
    }

    const totalItens = itens.length;
    const preenchidos = itens.filter(i => (localState[i.id]?.resposta ?? i.resposta) !== null && (localState[i.id]?.resposta ?? i.resposta) !== undefined).length;
    const progressPct = totalItens > 0 ? Math.round((preenchidos / totalItens) * 100) : 0;

    // Group by secao
    const sections = [];
    const sectionMap = {};
    itens.forEach(item => {
        const sec = item.secao || "Geral";
        if (!sectionMap[sec]) {
            sectionMap[sec] = [];
            sections.push(sec);
        }
        sectionMap[sec].push(item);
    });

    const canApprove = hasRole(user, CQ_FULL) && ck.status === "em_preenchimento";

    return (
        <div className="p-6 page-enter pb-24" data-testid="cq-preencher-checklist">
            {/* Breadcrumb */}
            <div className="flex items-center gap-2 text-sm text-muted-foreground mb-4">
                <button onClick={() => navigate("/cq/checklists")} className="hover:text-foreground transition-colors">Checklists</button>
                <ChevronRight className="h-4 w-4" />
                <span className="text-foreground font-medium">{ck.numero_ck}</span>
            </div>

            {/* Header */}
            <div className="mb-6">
                <div className="flex items-center gap-3 mb-1">
                    <h1 className="text-2xl font-heading font-bold">{ck.numero_ck}</h1>
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300">
                        {ck.tipo}
                    </span>
                    {ck.status && (
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${STATUS_COLORS[ck.status] || "bg-gray-100 text-gray-700"}`}>
                            {ck.status === "em_preenchimento" ? "Em Preenchimento" : ck.status === "aprovado" ? "Aprovado" : "Reprovado"}
                        </span>
                    )}
                </div>
                <div className="flex flex-wrap gap-4 text-sm text-muted-foreground">
                    {ck.op_numero && <span>OP: <strong>{ck.op_numero}</strong></span>}
                    {ck.turno && <span>Turno: <strong>{ck.turno}</strong></span>}
                    {ck.linha && <span>Linha: <strong>{ck.linha}</strong></span>}
                </div>
            </div>

            {/* Progress Bar */}
            <div className="mb-6" data-testid="progress-bar">
                <div className="flex items-center justify-between mb-1">
                    <span className="text-sm text-muted-foreground">Progresso</span>
                    <span className="text-sm font-medium">{preenchidos}/{totalItens} ({progressPct}%)</span>
                </div>
                <div className="h-2 rounded-full bg-muted overflow-hidden">
                    <div
                        className="h-full rounded-full bg-primary transition-all duration-300"
                        style={{ width: `${progressPct}%` }}
                    />
                </div>
            </div>

            {/* Sections */}
            <div className="space-y-4">
                {sections.map(secao => (
                    <div key={secao} className="rounded-lg border border-border overflow-hidden" data-testid={`secao-${secao}`}>
                        <button
                            className="w-full flex items-center justify-between px-4 py-3 bg-muted/50 hover:bg-muted/70 transition-colors text-left"
                            onClick={() => toggleSection(secao)}
                        >
                            <span className="font-heading font-semibold text-sm">{secao}</span>
                            <ChevronRight className={`h-4 w-4 text-muted-foreground transition-transform ${openSections[secao] ? "rotate-90" : ""}`} />
                        </button>
                        {openSections[secao] && (
                            <div className="divide-y divide-border">
                                {(sectionMap[secao] || []).map(item => {
                                    const state = localState[item.id] || {};
                                    const resposta = state.resposta ?? item.resposta ?? null;
                                    const isSomenteCQ = item.somente_cq && !hasRole(user, CQ_FULL);
                                    const isNC = resposta === "N";
                                    const isCritica = isNC && state.nc_classificacao === "critica";

                                    return (
                                        <div key={item.id} className="px-4 py-4" data-testid={`item-${item.id}`}>
                                            <div className="flex items-start gap-3">
                                                <span className="text-xs text-muted-foreground font-mono mt-0.5 min-w-[2rem]">
                                                    {item.ordem ?? ""}
                                                </span>
                                                <div className="flex-1">
                                                    <div className="flex items-start justify-between gap-2 mb-3">
                                                        <p className="text-sm font-medium leading-snug">{item.descricao}</p>
                                                        <div className="flex items-center gap-2">
                                                            {isSomenteCQ && (
                                                                <span className="text-xs bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-200 px-2 py-0.5 rounded-full">
                                                                    Apenas CQ
                                                                </span>
                                                            )}
                                                            {item.conforme === true && <Check className="h-4 w-4 text-green-600" />}
                                                            {item.conforme === false && <X className="h-4 w-4 text-red-600" />}
                                                        </div>
                                                    </div>

                                                    {item.tipo_resposta === "snna" && (
                                                        <div className="flex gap-2 mb-2">
                                                            {["S", "N", "NA"].map(opt => (
                                                                <button
                                                                    key={opt}
                                                                    disabled={isSomenteCQ}
                                                                    data-testid={`btn-${opt}-${item.id}`}
                                                                    onClick={() => !isSomenteCQ && handleSNNA(item, opt)}
                                                                    className={`px-3 py-1 rounded text-xs font-semibold border transition-colors
                                                                        ${resposta === opt
                                                                            ? opt === "S" ? "bg-green-500 text-white border-green-500"
                                                                            : opt === "N" ? "bg-red-500 text-white border-red-500"
                                                                            : "bg-slate-500 text-white border-slate-500"
                                                                            : "bg-background border-border text-muted-foreground hover:bg-accent"
                                                                        }
                                                                        ${isSomenteCQ ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}
                                                                    `}
                                                                >
                                                                    {opt}
                                                                </button>
                                                            ))}
                                                        </div>
                                                    )}

                                                    {item.tipo_resposta === "numerico" && (
                                                        <Input
                                                            type="number"
                                                            className="w-40 h-7 text-xs mb-2"
                                                            disabled={isSomenteCQ}
                                                            value={state.resposta ?? ""}
                                                            data-testid={`input-resultado-${item.id}`}
                                                            onChange={(e) => handleFieldChange(item.id, "resposta", e.target.value)}
                                                            onBlur={(e) => handleFieldBlur(item.id, "resposta", e.target.value)}
                                                        />
                                                    )}

                                                    {item.tipo_resposta === "texto" && (
                                                        <Input
                                                            className="w-64 h-7 text-xs mb-2"
                                                            disabled={isSomenteCQ}
                                                            value={state.resposta ?? ""}
                                                            data-testid={`input-resultado-${item.id}`}
                                                            onChange={(e) => handleFieldChange(item.id, "resposta", e.target.value)}
                                                            onBlur={(e) => handleFieldBlur(item.id, "resposta", e.target.value)}
                                                        />
                                                    )}

                                                    {/* NC fields */}
                                                    {isNC && (
                                                        <div className="ml-0 mt-2 space-y-2 rounded-md border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-950/20 p-3">
                                                            <div className="flex flex-wrap gap-3">
                                                                <div className="space-y-1">
                                                                    <Label className="text-xs">Classificação *</Label>
                                                                    <Select
                                                                        value={state.nc_classificacao || ""}
                                                                        onValueChange={(v) => {
                                                                            handleFieldChange(item.id, "nc_classificacao", v);
                                                                            const next = { ...localState[item.id], nc_classificacao: v };
                                                                            setLocalState(prev => ({ ...prev, [item.id]: next }));
                                                                            putItem(item.id, next);
                                                                        }}
                                                                    >
                                                                        <SelectTrigger className="w-32 h-7 text-xs" data-testid={`select-classificacao-${item.id}`}>
                                                                            <SelectValue placeholder="Classificar" />
                                                                        </SelectTrigger>
                                                                        <SelectContent>
                                                                            <SelectItem value="critica">Crítica</SelectItem>
                                                                            <SelectItem value="maior">Maior</SelectItem>
                                                                            <SelectItem value="menor">Menor</SelectItem>
                                                                        </SelectContent>
                                                                    </Select>
                                                                </div>
                                                                <div className="flex-1 space-y-1">
                                                                    <Label className="text-xs">Ação Imediata</Label>
                                                                    <Input
                                                                        className="h-7 text-xs"
                                                                        value={state.acao_imediata || ""}
                                                                        onChange={(e) => handleFieldChange(item.id, "acao_imediata", e.target.value)}
                                                                        onBlur={(e) => handleFieldBlur(item.id, "acao_imediata", e.target.value)}
                                                                    />
                                                                </div>
                                                            </div>
                                                            {isCritica && (
                                                                <div
                                                                    className="flex items-center gap-2 text-red-700 dark:text-red-300 text-xs font-semibold"
                                                                    data-testid={`banner-nc-critica-${item.id}`}
                                                                >
                                                                    <AlertTriangle className="h-4 w-4" />
                                                                    RNC crítica será gerada automaticamente
                                                                </div>
                                                            )}
                                                        </div>
                                                    )}

                                                    {/* Observação */}
                                                    <div className="mt-2">
                                                        <Input
                                                            className="h-7 text-xs w-full"
                                                            placeholder="Observação..."
                                                            value={state.observacao || ""}
                                                            onChange={(e) => handleFieldChange(item.id, "observacao", e.target.value)}
                                                            onBlur={(e) => handleFieldBlur(item.id, "observacao", e.target.value)}
                                                        />
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                    </div>
                ))}
            </div>

            {/* Fixed bottom approve button */}
            {canApprove && (
                <div className="fixed bottom-0 left-0 right-0 border-t border-border bg-background p-4 flex justify-end gap-3 z-10">
                    <Button onClick={() => setShowAprovar(true)} data-testid="btn-aprovar-checklist">
                        Aprovar / Reprovar Checklist
                    </Button>
                </div>
            )}

            {/* Aprovar Modal */}
            <Dialog open={showAprovar} onOpenChange={setShowAprovar}>
                <DialogContent className="max-w-md">
                    <DialogHeader>
                        <DialogTitle className="font-heading">Decisão do Checklist</DialogTitle>
                    </DialogHeader>
                    <div className="space-y-4">
                        <div className="space-y-2">
                            <Label>Decisão *</Label>
                            <div className="flex flex-col gap-2">
                                <label className="flex items-center gap-2 cursor-pointer">
                                    <input type="radio" name="aprovDecisao" value="aprovado" checked={aprovDecisao === "aprovado"} onChange={() => setAprovDecisao("aprovado")} />
                                    <span className="text-sm">Aprovar</span>
                                </label>
                                <label className="flex items-center gap-2 cursor-pointer">
                                    <input type="radio" name="aprovDecisao" value="reprovado" checked={aprovDecisao === "reprovado"} onChange={() => setAprovDecisao("reprovado")} />
                                    <span className="text-sm">Reprovar</span>
                                </label>
                            </div>
                        </div>
                        <div className="space-y-2">
                            <Label>Observações</Label>
                            <Textarea rows={3} value={aprovObs} onChange={(e) => setAprovObs(e.target.value)} placeholder="Observações sobre a decisão..." />
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
        </div>
    );
}
