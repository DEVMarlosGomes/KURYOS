import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { Plus, Search, Loader2, RefreshCw, ChevronRight } from "lucide-react";
import { useNavigate } from "react-router-dom";

const CATEGORIAS = ["mp", "fragrancia", "embalagem"];

function NovoItemDialog({ open, onClose, onCreated }) {
    const [form, setForm] = useState({ codigo_interno: "", descricao: "", categoria: "mp", unidade_compra: "kg", lead_time_dias: 0, estoque_minimo: "" });
    const [saving, setSaving] = useState(false);
    const salvar = async () => {
        if (!form.codigo_interno.trim() || !form.descricao.trim()) { toast.error("Código e descrição são obrigatórios"); return; }
        setSaving(true);
        try {
            const body = { ...form, lead_time_dias: parseInt(form.lead_time_dias) || 0, estoque_minimo: form.estoque_minimo ? parseFloat(form.estoque_minimo) : null };
            const { data } = await api.post("/compras/itens", body);
            toast.success(`Item ${data.codigo_interno} criado`);
            onCreated(data); onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Erro ao criar item"); }
        finally { setSaving(false); }
    };
    const set = (k, v) => setForm(f => ({ ...f, [k]: v }));
    return (
        <Dialog open={open} onOpenChange={onClose}>
            <DialogContent>
                <DialogHeader><DialogTitle>Novo Item de Compra</DialogTitle></DialogHeader>
                <div className="grid grid-cols-2 gap-3">
                    <div className="col-span-2">
                        <Label className="text-xs">Código Interno *</Label>
                        <Input className="h-8 text-sm mt-1" value={form.codigo_interno} onChange={e => set("codigo_interno", e.target.value)} />
                    </div>
                    <div className="col-span-2">
                        <Label className="text-xs">Descrição *</Label>
                        <Input className="h-8 text-sm mt-1" value={form.descricao} onChange={e => set("descricao", e.target.value)} />
                    </div>
                    <div>
                        <Label className="text-xs">Categoria *</Label>
                        <Select value={form.categoria} onValueChange={v => set("categoria", v)}>
                            <SelectTrigger className="h-8 text-sm mt-1"><SelectValue /></SelectTrigger>
                            <SelectContent>{CATEGORIAS.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                        </Select>
                    </div>
                    <div>
                        <Label className="text-xs">Unidade de Compra *</Label>
                        <Input className="h-8 text-sm mt-1" placeholder="kg, L, un..." value={form.unidade_compra} onChange={e => set("unidade_compra", e.target.value)} />
                    </div>
                    <div>
                        <Label className="text-xs">Lead Time (dias)</Label>
                        <Input type="number" className="h-8 text-sm mt-1" value={form.lead_time_dias} onChange={e => set("lead_time_dias", e.target.value)} />
                    </div>
                    <div>
                        <Label className="text-xs">Estoque Mínimo</Label>
                        <Input type="number" className="h-8 text-sm mt-1" value={form.estoque_minimo} onChange={e => set("estoque_minimo", e.target.value)} />
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" size="sm" onClick={onClose}>Cancelar</Button>
                    <Button size="sm" onClick={salvar} disabled={saving}>{saving && <Loader2 className="h-3 w-3 animate-spin mr-1" />} Criar</Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

export default function ComprasItens() {
    const nav = useNavigate();
    const [items, setItems] = useState([]);
    const [total, setTotal] = useState(0);
    const [loading, setLoading] = useState(false);
    const [q, setQ] = useState("");
    const [categoria, setCategoria] = useState("all");
    const [novoOpen, setNovoOpen] = useState(false);

    const carregar = useCallback(async () => {
        setLoading(true);
        try {
            const params = { limit: 200 };
            if (q) params.q = q;
            if (categoria && categoria !== "all") params.categoria = categoria;
            const { data } = await api.get("/compras/itens", { params });
            setItems(data.itens || []);
            setTotal(data.total || 0);
        } catch { toast.error("Erro ao carregar itens"); }
        finally { setLoading(false); }
    }, [q, categoria]);

    useEffect(() => { carregar(); }, [carregar]);

    return (
        <div className="p-4 md:p-6 max-w-6xl mx-auto space-y-4">
            <div className="flex items-center justify-between">
                <h1 className="text-xl font-bold">Itens de Compra <span className="text-muted-foreground text-sm font-normal">({total})</span></h1>
                <div className="flex gap-2">
                    <Button size="sm" variant="outline" onClick={carregar}><RefreshCw className="h-4 w-4" /></Button>
                    <Button size="sm" onClick={() => setNovoOpen(true)}><Plus className="h-4 w-4 mr-1" /> Novo</Button>
                </div>
            </div>

            <div className="flex flex-wrap gap-2">
                <div className="relative flex-1 min-w-48">
                    <Search className="absolute left-2.5 top-2 h-4 w-4 text-muted-foreground" />
                    <Input className="pl-8 h-8 text-sm" placeholder="Buscar..." value={q} onChange={e => setQ(e.target.value)} />
                </div>
                <Select value={categoria} onValueChange={setCategoria}>
                    <SelectTrigger className="h-8 w-36 text-xs"><SelectValue placeholder="Categoria" /></SelectTrigger>
                    <SelectContent>
                        <SelectItem value="all">Todas</SelectItem>
                        {CATEGORIAS.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                    </SelectContent>
                </Select>
            </div>

            <div className="rounded-lg border overflow-hidden">
                <table className="w-full text-xs">
                    <thead className="bg-muted/60 border-b">
                        <tr>
                            <th className="text-left px-3 py-2 font-medium text-muted-foreground">Código</th>
                            <th className="text-left px-3 py-2 font-medium text-muted-foreground">Descrição</th>
                            <th className="text-left px-3 py-2 font-medium text-muted-foreground">Categoria</th>
                            <th className="text-right px-3 py-2 font-medium text-muted-foreground">Est. Mín</th>
                            <th className="text-right px-3 py-2 font-medium text-muted-foreground">Lead Time</th>
                            <th className="text-right px-3 py-2 font-medium text-muted-foreground">Últ. Preço</th>
                            <th className="px-3 py-2" />
                        </tr>
                    </thead>
                    <tbody>
                        {loading ? (
                            <tr><td colSpan={7} className="text-center py-10"><Loader2 className="h-5 w-5 animate-spin mx-auto text-muted-foreground" /></td></tr>
                        ) : items.length === 0 ? (
                            <tr><td colSpan={7} className="text-center py-10 text-muted-foreground">Nenhum item encontrado.</td></tr>
                        ) : items.map(it => (
                            <tr key={it.id} className="border-b last:border-0 hover:bg-muted/30 cursor-pointer" onClick={() => nav(`/compras/itens/${it.id}`)}>
                                <td className="px-3 py-2 font-mono">{it.codigo_interno}</td>
                                <td className="px-3 py-2 font-medium">{it.descricao}</td>
                                <td className="px-3 py-2"><span className="px-1.5 py-0.5 bg-muted rounded text-xs">{it.categoria}</span></td>
                                <td className="px-3 py-2 text-right font-mono">{it.estoque_minimo ?? "—"} {it.estoque_minimo ? it.unidade_compra : ""}</td>
                                <td className="px-3 py-2 text-right">{it.lead_time_dias ?? 0}d</td>
                                <td className="px-3 py-2 text-right font-mono">
                                    {it.ultimo_preco_pago != null
                                        ? it.ultimo_preco_pago.toLocaleString("pt-BR", { style: "currency", currency: "BRL" })
                                        : "—"}
                                </td>
                                <td className="px-3 py-2"><ChevronRight className="h-4 w-4 text-muted-foreground" /></td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
            <NovoItemDialog open={novoOpen} onClose={() => setNovoOpen(false)} onCreated={() => carregar()} />
        </div>
    );
}
