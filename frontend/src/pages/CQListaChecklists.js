import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Plus, Loader2, ChevronRight, AlertTriangle } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

const STATUS_COLORS = {
    em_preenchimento: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200",
    aprovado: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
    reprovado: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
};

const STATUS_LABELS = {
    em_preenchimento: "Em Preenchimento",
    aprovado: "Aprovado",
    reprovado: "Reprovado",
};

const CK_TYPES = ["CK-1", "CK-2", "CK-3", "CK-4", "CK-5", "CK-6", "CK-7", "CK-8"];

const EMPTY_FORM = {
    tipo: "",
    nome: "",
    op_id: "",
    op_numero: "",
    lote_id: "",
    turno: "",
    linha: "",
    subtipo_insumo: "",
};

export default function CQListaChecklists() {
    const navigate = useNavigate();
    const { user } = useAuth();
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [filterTipo, setFilterTipo] = useState("all");
    const [filterStatus, setFilterStatus] = useState("all");
    const [showModal, setShowModal] = useState(false);
    const [form, setForm] = useState(EMPTY_FORM);
    const [saving, setSaving] = useState(false);

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const params = {};
            if (filterTipo !== "all") params.tipo = filterTipo;
            if (filterStatus !== "all") params.status = filterStatus;
            const { data } = await api.get("/cq/checklists", { params });
            setItems(Array.isArray(data) ? data : (data?.items ?? data?.data ?? []));
        } catch (e) {
            toast.error("Erro ao carregar checklists");
        } finally {
            setLoading(false);
        }
    }, [filterTipo, filterStatus]);

    useEffect(() => { load(); }, [load]);

    const handleCreate = async () => {
        if (!form.tipo) {
            toast.error("Tipo do checklist é obrigatório");
            return;
        }
        setSaving(true);
        try {
            const payload = { ...form };
            if (form.tipo !== "CK-1") delete payload.subtipo_insumo;
            await api.post("/cq/checklists", payload);
            toast.success("Checklist criado!");
            setShowModal(false);
            setForm(EMPTY_FORM);
            load();
        } catch (e) {
            const detail = e.response?.data?.detail;
            const msg = typeof detail === "object" ? detail.message : detail;
            toast.error(msg || "Erro ao criar checklist");
        } finally {
            setSaving(false);
        }
    };

    const handleFilterChange = (field, val) => {
        if (field === "tipo") setFilterTipo(val);
        if (field === "status") setFilterStatus(val);
    };

    return (
        <div className="p-6 page-enter" data-testid="cq-lista-checklists">
            <div className="flex items-center justify-between mb-6">
                <div>
                    <h1 className="text-3xl font-heading font-semibold tracking-tight">Checklists</h1>
                    <p className="text-sm text-muted-foreground mt-1">Controle de qualidade em processo</p>
                </div>
                <Button onClick={() => { setForm(EMPTY_FORM); setShowModal(true); }} data-testid="btn-novo-checklist">
                    <Plus className="h-4 w-4 mr-2" /> Novo Checklist
                </Button>
            </div>

            {/* Filters */}
            <div className="flex flex-wrap gap-3 mb-5">
                <div className="flex items-center gap-2">
                    <Label className="text-sm">Tipo:</Label>
                    <Select value={filterTipo} onValueChange={(v) => handleFilterChange("tipo", v)}>
                        <SelectTrigger className="w-[140px]">
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="all">Todos</SelectItem>
                            {CK_TYPES.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                        </SelectContent>
                    </Select>
                </div>
                <div className="flex items-center gap-2">
                    <Label className="text-sm">Status:</Label>
                    <Select value={filterStatus} onValueChange={(v) => handleFilterChange("status", v)}>
                        <SelectTrigger className="w-[180px]">
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="all">Todos</SelectItem>
                            <SelectItem value="em_preenchimento">Em Preenchimento</SelectItem>
                            <SelectItem value="aprovado">Aprovado</SelectItem>
                            <SelectItem value="reprovado">Reprovado</SelectItem>
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
                <div className="rounded-lg border border-border overflow-hidden" data-testid="table-checklists">
                    <table className="w-full text-sm">
                        <thead className="bg-muted/50">
                            <tr>
                                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Nº CK</th>
                                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Tipo</th>
                                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Nome</th>
                                <th className="text-left px-4 py-3 font-medium text-muted-foreground">OP</th>
                                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Status</th>
                                <th className="text-left px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">NCs</th>
                                <th className="text-left px-4 py-3 font-medium text-muted-foreground hidden lg:table-cell">Progresso</th>
                                <th className="text-left px-4 py-3 font-medium text-muted-foreground hidden lg:table-cell">Data</th>
                                <th className="px-4 py-3" />
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-border">
                            {items.length === 0 ? (
                                <tr>
                                    <td colSpan={9} className="text-center py-10 text-muted-foreground">
                                        Nenhum checklist encontrado.
                                    </td>
                                </tr>
                            ) : items.map((ck) => {
                                const progresso = ck.total_itens
                                    ? `${ck.itens_preenchidos ?? 0}/${ck.total_itens}`
                                    : null;
                                return (
                                    <tr
                                        key={ck.id}
                                        className="hover:bg-accent/40 cursor-pointer transition-colors"
                                        onClick={() => navigate(`/cq/checklists/${ck.id}`)}
                                        data-testid={`row-ck-${ck.id}`}
                                    >
                                        <td className="px-4 py-3 font-mono text-xs font-medium">{ck.numero_ck}</td>
                                        <td className="px-4 py-3">
                                            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300">
                                                {ck.tipo}
                                            </span>
                                        </td>
                                        <td className="px-4 py-3 text-sm font-medium">{ck.nome || <span className="text-muted-foreground text-xs">—</span>}</td>
                                        <td className="px-4 py-3 text-xs">{ck.op_numero || "—"}</td>
                                        <td className="px-4 py-3">
                                            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[ck.status] || "bg-gray-100 text-gray-700"}`}>
                                                {STATUS_LABELS[ck.status] || ck.status}
                                            </span>
                                        </td>
                                        <td className="px-4 py-3 text-xs hidden md:table-cell">
                                            {ck.ncs_identificadas != null ? ck.ncs_identificadas : "—"}
                                        </td>
                                        <td className="px-4 py-3 text-xs hidden lg:table-cell">
                                            {progresso ?? "—"}
                                        </td>
                                        <td className="px-4 py-3 text-xs text-muted-foreground hidden lg:table-cell mono-num">
                                            {ck.created_at ? new Date(ck.created_at).toLocaleDateString("pt-BR") : "—"}
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

            {/* Create Modal */}
            <Dialog open={showModal} onOpenChange={setShowModal}>
                <DialogContent className="max-w-md" data-testid="modal-novo-checklist">
                    <DialogHeader>
                        <DialogTitle className="font-heading">Novo Checklist</DialogTitle>
                    </DialogHeader>
                    <div className="space-y-4">
                        <div className="space-y-2">
                            <Label>Tipo *</Label>
                            <Select value={form.tipo} onValueChange={(v) => setForm({ ...form, tipo: v, subtipo_insumo: "" })}>
                                <SelectTrigger><SelectValue placeholder="Selecionar tipo" /></SelectTrigger>
                                <SelectContent>
                                    {CK_TYPES.map(t => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                                </SelectContent>
                            </Select>
                        </div>
                        <div className="space-y-2">
                            <Label>Nome / Descrição</Label>
                            <Input value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} placeholder="Ex: Recebimento MP Fragrância Lote 123" />
                        </div>
                        {form.tipo === "CK-7" && (
                            <div className="flex items-start gap-2 rounded-md border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/30 p-3">
                                <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 shrink-0" />
                                <p className="text-xs text-amber-800 dark:text-amber-200">
                                    <strong>Pré-requisito:</strong> CK-7 (Liberação de Palete) exige que exista um{" "}
                                    <strong>Registro de Análise de Produto Acabado aprovado</strong> para o Lote informado. Preencha o campo "Lote ID" com o lote correto antes de criar.
                                </p>
                            </div>
                        )}
                        {form.tipo === "CK-1" && (
                            <div className="space-y-2">
                                <Label>Subtipo de Insumo</Label>
                                <Select value={form.subtipo_insumo} onValueChange={(v) => setForm({ ...form, subtipo_insumo: v })}>
                                    <SelectTrigger><SelectValue placeholder="Selecionar insumo" /></SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="frasco">Frasco</SelectItem>
                                        <SelectItem value="tampa">Tampa</SelectItem>
                                        <SelectItem value="valvula">Válvula</SelectItem>
                                        <SelectItem value="rotulo">Rótulo</SelectItem>
                                        <SelectItem value="cartucho">Cartucho</SelectItem>
                                        <SelectItem value="caixa">Caixa</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                        )}
                        <div className="grid grid-cols-2 gap-3">
                            <div className="space-y-2">
                                <Label>ID da OP</Label>
                                <Input value={form.op_id} onChange={(e) => setForm({ ...form, op_id: e.target.value })} placeholder="ID da ordem de produção" />
                            </div>
                            <div className="space-y-2">
                                <Label>Nº da OP</Label>
                                <Input value={form.op_numero} onChange={(e) => setForm({ ...form, op_numero: e.target.value })} placeholder="Número da OP" />
                            </div>
                            <div className="space-y-2">
                                <Label>Lote ID</Label>
                                <Input value={form.lote_id} onChange={(e) => setForm({ ...form, lote_id: e.target.value })} />
                            </div>
                            <div className="space-y-2">
                                <Label>Turno</Label>
                                <Input value={form.turno} onChange={(e) => setForm({ ...form, turno: e.target.value })} placeholder="Ex: Manhã" />
                            </div>
                            <div className="space-y-2 col-span-2">
                                <Label>Linha</Label>
                                <Input value={form.linha} onChange={(e) => setForm({ ...form, linha: e.target.value })} placeholder="Ex: Linha 1" />
                            </div>
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setShowModal(false)}>Cancelar</Button>
                        <Button onClick={handleCreate} disabled={saving}>
                            {saving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                            Criar Checklist
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
