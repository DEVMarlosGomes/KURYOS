import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Loader2, ChevronRight, Send } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

const CQ_FULL = ["admin", "qa", "lider_pd"];
const hasRole = (user, roles) => roles.includes(user?.role);

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
    aguardando_fornecedor: "Aguardando Fornecedor",
    encerrada: "Encerrada",
    encerrada_concessao: "Encerrada c/ Concessão",
};

const CLASS_LABELS = {
    critica: "Crítica",
    maior: "Maior",
    menor: "Menor",
};

export default function CQDetalheRNC() {
    const { id } = useParams();
    const navigate = useNavigate();
    const { user } = useAuth();
    const [rnc, setRnc] = useState(null);
    const [loading, setLoading] = useState(true);
    const [capaTexto, setCapaTexto] = useState("");
    const [capaSaving, setCapaSaving] = useState(false);
    const [showEncerrar, setShowEncerrar] = useState(false);
    const [showComunicar, setShowComunicar] = useState(false);
    const [encEvidencia, setEncEvidencia] = useState("");
    const [encConcessao, setEncConcessao] = useState(false);
    const [encAutorizacao, setEncAutorizacao] = useState("");
    const [encObs, setEncObs] = useState("");
    const [encSaving, setEncSaving] = useState(false);
    const [comEmail, setComEmail] = useState("");
    const [comObs, setComObs] = useState("");
    const [comSaving, setComSaving] = useState(false);

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const { data } = await api.get(`/cq/rncs/${id}`);
            setRnc(data);
            setCapaTexto(data.capa_descricao || "");
        } catch (e) {
            toast.error("Erro ao carregar RNC");
        } finally {
            setLoading(false);
        }
    }, [id]);

    useEffect(() => { load(); }, [load]);

    const handleSaveCapa = async () => {
        setCapaSaving(true);
        try {
            await api.put(`/cq/rncs/${id}`, { capa_descricao: capaTexto });
            toast.success("CAPA salva!");
        } catch (e) {
            toast.error(e.response?.data?.detail || "Erro ao salvar CAPA");
        } finally {
            setCapaSaving(false);
        }
    };

    const handleEncerrar = async () => {
        if (!encEvidencia.trim()) {
            toast.error("Evidência de resolução é obrigatória");
            return;
        }
        if (encConcessao && !encAutorizacao.trim()) {
            toast.error("Autorização de concessão é obrigatória");
            return;
        }
        setEncSaving(true);
        try {
            await api.post(`/cq/rncs/${id}/encerrar`, {
                evidencia_resolucao: encEvidencia,
                com_concessao: encConcessao,
                autorizacao_concessao: encConcessao ? encAutorizacao : undefined,
                observacoes: encObs,
            });
            toast.success("RNC encerrada!");
            setShowEncerrar(false);
            load();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Erro ao encerrar RNC");
        } finally {
            setEncSaving(false);
        }
    };

    const handleComunicar = async () => {
        setComSaving(true);
        try {
            const res = await api.post(`/cq/rncs/${id}/comunicar-fornecedor`, {
                email_destinatario: comEmail,
                observacoes: comObs,
            }, { responseType: "blob" });
            // Try download PDF if returned
            const url = window.URL.createObjectURL(new Blob([res.data]));
            const link = document.createElement("a");
            link.href = url;
            link.setAttribute("download", `RNC_${rnc?.numero_rnc || id}_comunicado.pdf`);
            document.body.appendChild(link);
            link.click();
            link.remove();
            window.URL.revokeObjectURL(url);
            toast.success("Comunicado enviado ao fornecedor!");
            setShowComunicar(false);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Erro ao comunicar fornecedor");
        } finally {
            setComSaving(false);
        }
    };

    if (loading) {
        return (
            <div className="p-6 flex items-center justify-center h-64">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
        );
    }

    if (!rnc) {
        return (
            <div className="p-6">
                <p className="text-muted-foreground">RNC não encontrada.</p>
                <Button variant="outline" className="mt-4" onClick={() => navigate("/cq/rncs")}>Voltar</Button>
            </div>
        );
    }

    const isEncerrada = rnc.status === "encerrada" || rnc.status === "encerrada_concessao";
    const canAct = hasRole(user, CQ_FULL) && !isEncerrada;
    const canComunicar = canAct && (rnc.origem === "recepcao_mp" || rnc.origem === "recepcao_embalagem");

    const infoRows = [
        { label: "Origem", value: rnc.origem },
        { label: "Item", value: rnc.item_nome },
        { label: "Fornecedor", value: rnc.fornecedor_nome },
        { label: "Lote", value: rnc.lote_numero },
        { label: "Qtd Afetada", value: rnc.quantidade_afetada },
        { label: "Disposição Imediata", value: rnc.disposicao_imediata },
        { label: "Prazo Resolução", value: rnc.prazo_resolucao ? new Date(rnc.prazo_resolucao).toLocaleDateString("pt-BR") : "—" },
        { label: "Responsável", value: rnc.responsavel_nome },
        { label: "Criado em", value: rnc.created_at ? new Date(rnc.created_at).toLocaleDateString("pt-BR") : "—" },
    ];

    return (
        <div className="p-6 page-enter" data-testid="cq-detalhe-rnc">
            {/* Breadcrumb */}
            <div className="flex items-center gap-2 text-sm text-muted-foreground mb-4">
                <button onClick={() => navigate("/cq/rncs")} className="hover:text-foreground transition-colors">RNCs</button>
                <ChevronRight className="h-4 w-4" />
                <span className="text-foreground font-medium">{rnc.numero_rnc}</span>
            </div>

            {/* Header */}
            <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 mb-6">
                <div>
                    <div className="flex items-center gap-3 mb-2 flex-wrap">
                        <h1 className="text-2xl font-heading font-bold">{rnc.numero_rnc}</h1>
                        {rnc.classificacao && (
                            <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold ${CLASS_COLORS[rnc.classificacao] || ""}`}>
                                {CLASS_LABELS[rnc.classificacao] || rnc.classificacao}
                            </span>
                        )}
                        {rnc.status && (
                            <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold ${STATUS_COLORS[rnc.status] || ""}`}>
                                {STATUS_LABELS[rnc.status] || rnc.status}
                            </span>
                        )}
                    </div>
                </div>
                <div className="flex flex-wrap gap-2">
                    {canAct && (
                        <Button variant="destructive" onClick={() => setShowEncerrar(true)} data-testid="btn-encerrar-rnc">
                            Encerrar RNC
                        </Button>
                    )}
                    {canComunicar && (
                        <Button variant="outline" onClick={() => setShowComunicar(true)} data-testid="btn-comunicar-fornecedor">
                            <Send className="h-4 w-4 mr-2" /> Comunicar Fornecedor
                        </Button>
                    )}
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

            {/* Descrição */}
            {rnc.descricao && (
                <div className="mb-6">
                    <h2 className="font-heading font-semibold mb-2">Descrição</h2>
                    <div className="rounded-lg border border-border bg-muted/30 p-4 text-sm whitespace-pre-wrap">
                        {rnc.descricao}
                    </div>
                </div>
            )}

            {/* CAPA Section */}
            <div className="mb-6">
                <h2 className="font-heading font-semibold mb-2">CAPA — Ação Corretiva</h2>
                <Textarea
                    rows={5}
                    value={capaTexto}
                    onChange={(e) => setCapaTexto(e.target.value)}
                    disabled={isEncerrada}
                    placeholder="Descreva a análise de causa raiz e as ações corretivas planejadas..."
                    data-testid="capa-textarea"
                />
                {!isEncerrada && (
                    <Button className="mt-2" onClick={handleSaveCapa} disabled={capaSaving} data-testid="btn-salvar-capa">
                        {capaSaving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                        Salvar CAPA
                    </Button>
                )}
            </div>

            {/* Audit Log */}
            {rnc.log_auditoria && rnc.log_auditoria.length > 0 && (
                <div>
                    <h2 className="font-heading font-semibold mb-3">Histórico de Auditoria</h2>
                    <div className="space-y-3">
                        {rnc.log_auditoria.map((entry, idx) => (
                            <div key={idx} className="flex gap-3 items-start">
                                <div className="mt-1.5 w-2 h-2 rounded-full bg-primary shrink-0" />
                                <div>
                                    <p className="text-sm font-medium">{entry.acao || entry.action}</p>
                                    <p className="text-xs text-muted-foreground">
                                        {entry.usuario || entry.user} · {entry.data || entry.created_at ? new Date(entry.data || entry.created_at).toLocaleString("pt-BR") : ""}
                                    </p>
                                    {(entry.descricao || entry.description) && (
                                        <p className="text-xs text-muted-foreground italic">{entry.descricao || entry.description}</p>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Encerrar Modal */}
            <Dialog open={showEncerrar} onOpenChange={setShowEncerrar}>
                <DialogContent className="max-w-md" data-testid="modal-encerrar-rnc">
                    <DialogHeader>
                        <DialogTitle className="font-heading">Encerrar RNC</DialogTitle>
                    </DialogHeader>
                    <div className="space-y-4">
                        <div className="space-y-2">
                            <Label>Evidência de Resolução *</Label>
                            <Textarea
                                rows={3}
                                value={encEvidencia}
                                onChange={(e) => setEncEvidencia(e.target.value)}
                                placeholder="Descreva a evidência de que o problema foi resolvido..."
                            />
                        </div>
                        <div className="flex items-center gap-2">
                            <input
                                type="checkbox"
                                id="encConcessao"
                                checked={encConcessao}
                                onChange={(e) => setEncConcessao(e.target.checked)}
                            />
                            <label htmlFor="encConcessao" className="text-sm cursor-pointer">Encerrar com Concessão</label>
                        </div>
                        {encConcessao && (
                            <div className="space-y-2">
                                <Label>Autorização de Concessão *</Label>
                                <Input
                                    value={encAutorizacao}
                                    onChange={(e) => setEncAutorizacao(e.target.value)}
                                    placeholder="Número ou referência da autorização"
                                />
                            </div>
                        )}
                        <div className="space-y-2">
                            <Label>Observações</Label>
                            <Textarea rows={2} value={encObs} onChange={(e) => setEncObs(e.target.value)} />
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setShowEncerrar(false)}>Cancelar</Button>
                        <Button onClick={handleEncerrar} disabled={encSaving}>
                            {encSaving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                            Encerrar RNC
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Comunicar Fornecedor Modal */}
            <Dialog open={showComunicar} onOpenChange={setShowComunicar}>
                <DialogContent className="max-w-md" data-testid="modal-comunicar-fornecedor">
                    <DialogHeader>
                        <DialogTitle className="font-heading">Comunicar Fornecedor</DialogTitle>
                    </DialogHeader>
                    <div className="space-y-4">
                        <div className="space-y-2">
                            <Label>E-mail do Destinatário</Label>
                            <Input
                                type="email"
                                value={comEmail}
                                onChange={(e) => setComEmail(e.target.value)}
                                placeholder="contato@fornecedor.com"
                            />
                        </div>
                        <div className="space-y-2">
                            <Label>Observações</Label>
                            <Textarea rows={3} value={comObs} onChange={(e) => setComObs(e.target.value)} />
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setShowComunicar(false)}>Cancelar</Button>
                        <Button onClick={handleComunicar} disabled={comSaving}>
                            {comSaving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                            <Send className="h-4 w-4 mr-2" /> Enviar
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
