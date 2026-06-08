import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import { Plus, Search, Loader2, RefreshCw, ShieldCheck, ShieldAlert, ShieldOff, ChevronRight } from "lucide-react";
import { useNavigate } from "react-router-dom";

const HOM_CFG = {
    nao_iniciada:  { label: "Não iniciada",  cls: "bg-slate-100 text-slate-600" },
    em_processo:   { label: "Em processo",   cls: "bg-blue-100 text-blue-700" },
    homologado:    { label: "Homologado",    cls: "bg-green-100 text-green-700" },
    suspenso:      { label: "Suspenso",      cls: "bg-orange-100 text-orange-700" },
    reprovado:     { label: "Reprovado",     cls: "bg-red-100 text-red-700" },
};

function HomBadge({ status }) {
    const cfg = HOM_CFG[status] || HOM_CFG.nao_iniciada;
    return <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${cfg.cls}`}>{cfg.label}</span>;
}

const CATEGORIAS = ["MP Química", "Fragrância", "Frasco", "Tampa", "Válvula", "Rótulo", "Cartucho", "Display", "Caixa", "Celofane", "Outros"];

function NovoFornecedorDialog({ open, onClose, onCreated }) {
    const [form, setForm] = useState({ razao_social: "", nome_fantasia: "", cnpj: "", ie: "", categorias: [] });
    const [saving, setSaving] = useState(false);
    const toggle = (cat) => setForm(f => ({ ...f, categorias: f.categorias.includes(cat) ? f.categorias.filter(c => c !== cat) : [...f.categorias, cat] }));
    const salvar = async () => {
        if (!form.razao_social.trim() || !form.cnpj.trim()) { toast.error("Razão social e CNPJ são obrigatórios"); return; }
        setSaving(true);
        try {
            const { data } = await api.post("/compras/fornecedores", form);
            toast.success(`Fornecedor ${data.codigo_interno} criado`);
            onCreated(data);
            onClose();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Erro ao criar fornecedor");
        } finally { setSaving(false); }
    };
    return (
        <Dialog open={open} onOpenChange={onClose}>
            <DialogContent className="max-w-lg">
                <DialogHeader><DialogTitle>Novo Fornecedor</DialogTitle></DialogHeader>
                <div className="space-y-3">
                    {[["Razão Social *", "razao_social"], ["Nome Fantasia", "nome_fantasia"], ["CNPJ *", "cnpj"], ["IE", "ie"]].map(([label, key]) => (
                        <div key={key}>
                            <Label className="text-xs">{label}</Label>
                            <Input className="h-8 text-sm mt-1" value={form[key]} onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))} />
                        </div>
                    ))}
                    <div>
                        <Label className="text-xs">Categorias</Label>
                        <div className="flex flex-wrap gap-1.5 mt-1">
                            {CATEGORIAS.map(c => (
                                <button key={c} type="button"
                                    className={`px-2 py-0.5 rounded-full text-xs border transition ${form.categorias.includes(c) ? "bg-primary text-primary-foreground border-primary" : "border-border text-muted-foreground hover:border-primary"}`}
                                    onClick={() => toggle(c)}>{c}</button>
                            ))}
                        </div>
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" size="sm" onClick={onClose}>Cancelar</Button>
                    <Button size="sm" onClick={salvar} disabled={saving}>
                        {saving && <Loader2 className="h-3 w-3 animate-spin mr-1" />} Criar Fornecedor
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

export default function ComprasFornecedores() {
    const nav = useNavigate();
    const [items, setItems] = useState([]);
    const [total, setTotal] = useState(0);
    const [loading, setLoading] = useState(false);
    const [q, setQ] = useState("");
    const [statusHom, setStatusHom] = useState("all");
    const [novoOpen, setNovoOpen] = useState(false);

    const carregar = useCallback(async () => {
        setLoading(true);
        try {
            const params = { limit: 100 };
            if (q) params.q = q;
            if (statusHom && statusHom !== "all") params.status_homologacao = statusHom;
            const { data } = await api.get("/compras/fornecedores", { params });
            setItems(data.fornecedores || []);
            setTotal(data.total || 0);
        } catch { toast.error("Erro ao carregar fornecedores"); }
        finally { setLoading(false); }
    }, [q, statusHom]);

    useEffect(() => { carregar(); }, [carregar]);

    return (
        <div className="p-4 md:p-6 max-w-6xl mx-auto space-y-4">
            <div className="flex items-center justify-between">
                <h1 className="text-xl font-bold">Fornecedores <span className="text-muted-foreground text-sm font-normal">({total})</span></h1>
                <div className="flex gap-2">
                    <Button size="sm" variant="outline" onClick={carregar}><RefreshCw className="h-4 w-4" /></Button>
                    <Button size="sm" data-testid="btn-novo-fornecedor" onClick={() => setNovoOpen(true)}><Plus className="h-4 w-4 mr-1" /> Novo</Button>
                </div>
            </div>

            <div className="flex flex-wrap gap-2">
                <div className="relative flex-1 min-w-48">
                    <Search className="absolute left-2.5 top-2 h-4 w-4 text-muted-foreground" />
                    <Input className="pl-8 h-8 text-sm" placeholder="Buscar..." value={q} onChange={e => setQ(e.target.value)} />
                </div>
                <Select value={statusHom} onValueChange={setStatusHom}>
                    <SelectTrigger className="h-8 w-44 text-xs"><SelectValue placeholder="Homologação" /></SelectTrigger>
                    <SelectContent>
                        <SelectItem value="all">Todas</SelectItem>
                        {Object.entries(HOM_CFG).map(([k, v]) => <SelectItem key={k} value={k}>{v.label}</SelectItem>)}
                    </SelectContent>
                </Select>
            </div>

            <div className="rounded-lg border overflow-hidden">
                <table className="w-full text-xs">
                    <thead className="bg-muted/60 border-b">
                        <tr>
                            <th className="text-left px-3 py-2 font-medium text-muted-foreground">Código</th>
                            <th className="text-left px-3 py-2 font-medium text-muted-foreground">Razão Social</th>
                            <th className="text-left px-3 py-2 font-medium text-muted-foreground">CNPJ</th>
                            <th className="text-left px-3 py-2 font-medium text-muted-foreground">Categorias</th>
                            <th className="text-center px-3 py-2 font-medium text-muted-foreground">Homologação</th>
                            <th className="text-center px-3 py-2 font-medium text-muted-foreground">RNCs</th>
                            <th className="px-3 py-2" />
                        </tr>
                    </thead>
                    <tbody>
                        {loading ? (
                            <tr><td colSpan={7} className="text-center py-10"><Loader2 className="h-5 w-5 animate-spin mx-auto text-muted-foreground" /></td></tr>
                        ) : items.length === 0 ? (
                            <tr><td colSpan={7} className="text-center py-10 text-muted-foreground">Nenhum fornecedor encontrado.</td></tr>
                        ) : items.map(f => (
                            <tr key={f.id} data-testid={`fornecedor-row-${f.id}`} data-homologacao={f.homologacao?.status}
                                className="border-b last:border-0 hover:bg-muted/30 cursor-pointer" onClick={() => nav(`/compras/fornecedores/${f.id}`)}>
                                <td className="px-3 py-2 font-mono font-medium">{f.codigo_interno}</td>
                                <td className="px-3 py-2">
                                    <div className="font-medium">{f.razao_social}</div>
                                    {f.nome_fantasia && <div className="text-muted-foreground">{f.nome_fantasia}</div>}
                                </td>
                                <td className="px-3 py-2 font-mono">{f.cnpj}</td>
                                <td className="px-3 py-2">
                                    <div className="flex flex-wrap gap-1">
                                        {(f.categorias || []).slice(0, 3).map(c => (
                                            <span key={c} className="px-1.5 py-0.5 bg-muted rounded text-xs">{c}</span>
                                        ))}
                                        {(f.categorias || []).length > 3 && <span className="text-muted-foreground">+{f.categorias.length - 3}</span>}
                                    </div>
                                </td>
                                <td className="px-3 py-2 text-center"><HomBadge status={f.homologacao?.status} /></td>
                                <td className="px-3 py-2 text-center">
                                    <span className={f.homologacao?.historico_rncs_criticas_12m >= 3 ? "text-red-600 font-semibold" : ""}>
                                        {f.homologacao?.historico_rncs_count ?? 0} ({f.homologacao?.historico_rncs_criticas_12m ?? 0} críticas)
                                    </span>
                                </td>
                                <td className="px-3 py-2"><ChevronRight className="h-4 w-4 text-muted-foreground" /></td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            <NovoFornecedorDialog open={novoOpen} onClose={() => setNovoOpen(false)} onCreated={() => carregar()} />
        </div>
    );
}
