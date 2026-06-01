import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Plus, Loader2, ChevronRight } from "lucide-react";
import { useNavigate } from "react-router-dom";
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

const RESULTADO_COLORS = {
    conforme: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
    nao_conforme: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
};

const TIPO_LABELS = {
    recepcao_mp: "Recepção MP",
    recepcao_embalagem: "Recepção Embalagem",
    bulk_piloto: "Bulk Piloto",
    produto_acabado: "Produto Acabado",
};

const EMPTY_FORM = {
    lote_id: "",
    lote_numero: "",
    tipo: "",
    item_nome: "",
    fornecedor_nome: "",
    quantidade_recebida: "",
    unidade: "",
    nf_numero: "",
    nf_data: "",
    data_validade_fornecedor: "",
};

const PAGE_SIZE = 50;

export default function CQListaRA() {
    const navigate = useNavigate();
    const { user } = useAuth();
    const [items, setItems] = useState([]);
    const [total, setTotal] = useState(0);
    const [loading, setLoading] = useState(true);
    const [offset, setOffset] = useState(0);
    const [filterStatus, setFilterStatus] = useState("all");
    const [filterTipo, setFilterTipo] = useState("all");
    const [showModal, setShowModal] = useState(false);
    const [form, setForm] = useState(EMPTY_FORM);
    const [saving, setSaving] = useState(false);

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const params = { limit: PAGE_SIZE, offset };
            if (filterStatus !== "all") params.status = filterStatus;
            if (filterTipo !== "all") params.tipo = filterTipo;
            const { data } = await api.get("/cq/registros-analise", { params });
            if (Array.isArray(data)) {
                setItems(data);
                setTotal(data.length + offset);
            } else {
                setItems(data?.items ?? data?.data ?? []);
                setTotal(data?.total ?? 0);
            }
        } catch (e) {
            toast.error("Erro ao carregar registros de análise");
        } finally {
            setLoading(false);
        }
    }, [offset, filterStatus, filterTipo]);

    useEffect(() => { load(); }, [load]);

    const handleCreate = async () => {
        if (!form.tipo || !form.item_nome.trim()) {
            toast.error("Tipo e Item são obrigatórios");
            return;
        }
        setSaving(true);
        try {
            const payload = {
                ...form,
                quantidade_recebida: form.quantidade_recebida ? parseFloat(form.quantidade_recebida) : null,
            };
            await api.post("/cq/registros-analise", payload);
            toast.success("Registro de Análise criado!");
            setShowModal(false);
            setForm(EMPTY_FORM);
            setOffset(0);
            load();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Erro ao criar RA");
        } finally {
            setSaving(false);
        }
    };

    const handleFilterChange = (field, val) => {
        setOffset(0);
        if (field === "status") setFilterStatus(val);
        if (field === "tipo") setFilterTipo(val);
    };

    return (
        <div className="p-6 page-enter" data-testid="cq-lista-ra">
            <div className="flex items-center justify-between mb-6">
                <div>
                    <h1 className="text-3xl font-heading font-semibold tracking-tight">Registros de Análise</h1>
                    <p className="text-sm text-muted-foreground mt-1">Gestão de laudos de recepção e análise</p>
                </div>
                <Button onClick={() => { setForm(EMPTY_FORM); setShowModal(true); }} data-testid="btn-novo-ra">
                    <Plus className="h-4 w-4 mr-2" /> Novo RA
                </Button>
            </div>

            {/* Filters */}
            <div className="flex flex-wrap gap-3 mb-5">
                <div className="flex items-center gap-2">
                    <Label className="text-sm">Status:</Label>
                    <Select value={filterStatus} onValueChange={(v) => handleFilterChange("status", v)}>
                        <SelectTrigger className="w-[160px]" data-testid="filter-status">
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="all">Todos</SelectItem>
                            <SelectItem value="rascunho">Rascunho</SelectItem>
                            <SelectItem value="em_analise">Em Análise</SelectItem>
                            <SelectItem value="aprovado">Aprovado</SelectItem>
                            <SelectItem value="reprovado">Reprovado</SelectItem>
                            <SelectItem value="concessao">Concessão</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
                <div className="flex items-center gap-2">
                    <Label className="text-sm">Tipo:</Label>
                    <Select value={filterTipo} onValueChange={(v) => handleFilterChange("tipo", v)}>
                        <SelectTrigger className="w-[200px]" data-testid="filter-tipo">
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="all">Todos</SelectItem>
                            <SelectItem value="recepcao_mp">Recepção MP</SelectItem>
                            <SelectItem value="recepcao_embalagem">Recepção Embalagem</SelectItem>
                            <SelectItem value="bulk_piloto">Bulk Piloto</SelectItem>
                            <SelectItem value="produto_acabado">Produto Acabado</SelectItem>
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
                <>
                    <div className="rounded-lg border border-border overflow-hidden" data-testid="table-ra">
                        <table className="w-full text-sm">
                            <thead className="bg-muted/50">
                                <tr>
                                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Nº RA</th>
                                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Tipo</th>
                                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Item</th>
                                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Lote</th>
                                    <th className="text-left px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">Fornecedor</th>
                                    <th className="text-left px-4 py-3 font-medium text-muted-foreground">Status</th>
                                    <th className="text-left px-4 py-3 font-medium text-muted-foreground hidden lg:table-cell">Resultado</th>
                                    <th className="text-left px-4 py-3 font-medium text-muted-foreground hidden lg:table-cell">Data</th>
                                    <th className="px-4 py-3" />
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-border">
                                {items.length === 0 ? (
                                    <tr>
                                        <td colSpan={9} className="text-center py-10 text-muted-foreground">
                                            Nenhum registro encontrado.
                                        </td>
                                    </tr>
                                ) : items.map((ra) => (
                                    <tr
                                        key={ra.id}
                                        className="hover:bg-accent/40 cursor-pointer transition-colors"
                                        onClick={() => navigate(`/cq/registros-analise/${ra.id}`)}
                                        data-testid={`row-ra-${ra.id}`}
                                    >
                                        <td className="px-4 py-3 font-mono text-xs font-medium">{ra.numero_ra}</td>
                                        <td className="px-4 py-3 text-xs">{TIPO_LABELS[ra.tipo] || ra.tipo}</td>
                                        <td className="px-4 py-3 font-medium">{ra.item_nome}</td>
                                        <td className="px-4 py-3 text-xs mono-num">{ra.lote_numero || "—"}</td>
                                        <td className="px-4 py-3 text-xs hidden md:table-cell">{ra.fornecedor_nome || "—"}</td>
                                        <td className="px-4 py-3">
                                            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[ra.status] || "bg-gray-100 text-gray-700"}`}>
                                                {STATUS_LABELS[ra.status] || ra.status}
                                            </span>
                                        </td>
                                        <td className="px-4 py-3 hidden lg:table-cell">
                                            {ra.resultado_geral ? (
                                                <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${RESULTADO_COLORS[ra.resultado_geral] || "bg-gray-100 text-gray-700"}`}>
                                                    {ra.resultado_geral === "conforme" ? "Conforme" : "Não Conforme"}
                                                </span>
                                            ) : (
                                                <span className="text-muted-foreground">—</span>
                                            )}
                                        </td>
                                        <td className="px-4 py-3 text-xs text-muted-foreground hidden lg:table-cell mono-num">
                                            {ra.created_at ? new Date(ra.created_at).toLocaleDateString("pt-BR") : "—"}
                                        </td>
                                        <td className="px-4 py-3">
                                            <ChevronRight className="h-4 w-4 text-muted-foreground" />
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>

                    {/* Pagination */}
                    <div className="flex items-center justify-between mt-4">
                        <p className="text-sm text-muted-foreground">
                            Mostrando {offset + 1}–{Math.min(offset + items.length, total > 0 ? total : offset + items.length)} de {total > 0 ? total : (offset + items.length)}
                        </p>
                        <div className="flex gap-2">
                            <Button
                                variant="outline" size="sm"
                                disabled={offset === 0}
                                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                            >
                                Anterior
                            </Button>
                            <Button
                                variant="outline" size="sm"
                                disabled={items.length < PAGE_SIZE}
                                onClick={() => setOffset(offset + PAGE_SIZE)}
                            >
                                Próximo
                            </Button>
                        </div>
                    </div>
                </>
            )}

            {/* Create Modal */}
            <Dialog open={showModal} onOpenChange={setShowModal}>
                <DialogContent className="max-w-lg max-h-[85vh] flex flex-col p-0 overflow-hidden" data-testid="modal-criar-ra">
                    <DialogHeader className="p-6 pb-2">
                        <DialogTitle className="font-heading">Novo Registro de Análise</DialogTitle>
                    </DialogHeader>
                    <div className="flex-1 min-h-0 overflow-y-auto px-6 pb-2">
                        <div className="space-y-4">
                            <div className="space-y-2">
                                <Label>Tipo *</Label>
                                <Select value={form.tipo} onValueChange={(v) => setForm({ ...form, tipo: v })}>
                                    <SelectTrigger><SelectValue placeholder="Selecionar tipo" /></SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="recepcao_mp">Recepção MP</SelectItem>
                                        <SelectItem value="recepcao_embalagem">Recepção Embalagem</SelectItem>
                                        <SelectItem value="bulk_piloto">Bulk Piloto</SelectItem>
                                        <SelectItem value="produto_acabado">Produto Acabado</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                            <div className="grid grid-cols-2 gap-3">
                                <div className="space-y-2">
                                    <Label>Item/Produto *</Label>
                                    <Input value={form.item_nome} onChange={(e) => setForm({ ...form, item_nome: e.target.value })} placeholder="Nome do item" />
                                </div>
                                <div className="space-y-2">
                                    <Label>Fornecedor</Label>
                                    <Input value={form.fornecedor_nome} onChange={(e) => setForm({ ...form, fornecedor_nome: e.target.value })} placeholder="Nome do fornecedor" />
                                </div>
                                <div className="space-y-2">
                                    <Label>Lote ID</Label>
                                    <Input value={form.lote_id} onChange={(e) => setForm({ ...form, lote_id: e.target.value })} placeholder="ID interno do lote" />
                                </div>
                                <div className="space-y-2">
                                    <Label>Nº do Lote</Label>
                                    <Input value={form.lote_numero} onChange={(e) => setForm({ ...form, lote_numero: e.target.value })} placeholder="Número do lote" />
                                </div>
                                <div className="space-y-2">
                                    <Label>Quantidade Recebida</Label>
                                    <Input type="number" value={form.quantidade_recebida} onChange={(e) => setForm({ ...form, quantidade_recebida: e.target.value })} />
                                </div>
                                <div className="space-y-2">
                                    <Label>Unidade</Label>
                                    <Input value={form.unidade} onChange={(e) => setForm({ ...form, unidade: e.target.value })} placeholder="kg, L, un..." />
                                </div>
                                <div className="space-y-2">
                                    <Label>Nº NF</Label>
                                    <Input value={form.nf_numero} onChange={(e) => setForm({ ...form, nf_numero: e.target.value })} />
                                </div>
                                <div className="space-y-2">
                                    <Label>Data NF</Label>
                                    <Input type="date" value={form.nf_data} onChange={(e) => setForm({ ...form, nf_data: e.target.value })} />
                                </div>
                                <div className="space-y-2 col-span-2">
                                    <Label>Validade (Fornecedor)</Label>
                                    <Input type="date" value={form.data_validade_fornecedor} onChange={(e) => setForm({ ...form, data_validade_fornecedor: e.target.value })} />
                                </div>
                            </div>
                        </div>
                    </div>
                    <DialogFooter className="p-6 pt-3 border-t">
                        <Button variant="outline" onClick={() => setShowModal(false)}>Cancelar</Button>
                        <Button onClick={handleCreate} disabled={saving}>
                            {saving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                            Criar RA
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
