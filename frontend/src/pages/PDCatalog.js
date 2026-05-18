import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Card, CardContent } from "@/components/ui/card";
import { Plus, Search, Pencil, Trash2, Database, History, Tag, TrendingUp, TrendingDown, X } from "lucide-react";
import { toast } from "sonner";
import PDSubNav from "@/components/PDSubNav";

const CATEGORIAS = [
  "Ativo",
  "Solvente",
  "Conservante",
  "Emoliente",
  "Fragrância",
  "Espessante",
  "Tensoativo",
  "Corante",
  "Acidulante",
  "Quelante",
  "Umectante",
  "Outro",
];

const emptyFornecedor = { nome: "", codigo: "", preco_rs_kg: "", moeda: "BRL" };

const emptyForm = {
  nome: "",
  inci: "",
  codigo_interno: "",
  fornecedor: "",
  preco_rs_kg: "",
  moeda: "BRL",
  unidade: "kg",
  categoria: "",
  observacoes: "",
  fornecedores: [],
};

export default function PDCatalog() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [filterCat, setFilterCat] = useState("all");
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [historyItem, setHistoryItem] = useState(null);
  const [priceHistory, setPriceHistory] = useState([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (search) params.q = search;
      if (filterCat && filterCat !== "all") params.categoria = filterCat;
      const { data } = await api.get("/pd/catalog", { params });
      setItems(Array.isArray(data) ? data : []);
    } catch (e) {
      toast.error("Erro ao carregar banco de custos");
    } finally {
      setLoading(false);
    }
  }, [search, filterCat]);

  useEffect(() => { load(); }, [load]);

  const openCreate = () => {
    setEditingId(null);
    setForm(emptyForm);
    setShowForm(true);
  };

  const openEdit = (item) => {
    setEditingId(item.id);
    setForm({
      nome: item.nome || "",
      inci: item.inci || "",
      codigo_interno: item.codigo_interno || "",
      fornecedor: item.fornecedor || "",
      preco_rs_kg: String(item.preco_rs_kg ?? ""),
      moeda: item.moeda || "BRL",
      unidade: item.unidade || "kg",
      categoria: item.categoria || "",
      observacoes: item.observacoes || "",
      fornecedores: (item.fornecedores || []).map(s => ({
        nome: s.nome || "",
        codigo: s.codigo || "",
        preco_rs_kg: String(s.preco_rs_kg ?? ""),
        moeda: s.moeda || "BRL",
      })),
    });
    setShowForm(true);
  };

  const save = async () => {
    if (!form.nome.trim()) return toast.error("Nome é obrigatório");
    setSaving(true);
    try {
      const payload = {
        ...form,
        preco_rs_kg: parseFloat(form.preco_rs_kg) || 0,
        fornecedores: form.fornecedores
          .filter(s => s.nome.trim())
          .map(s => ({ nome: s.nome.trim(), codigo: s.codigo.trim() || null, preco_rs_kg: parseFloat(s.preco_rs_kg) || 0, moeda: s.moeda })),
      };
      if (editingId) {
        await api.put(`/pd/catalog/${editingId}`, payload);
        toast.success("Ingrediente atualizado");
      } else {
        await api.post("/pd/catalog", payload);
        toast.success("Ingrediente cadastrado");
      }
      setShowForm(false);
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Erro ao salvar");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (id) => {
    if (!window.confirm("Remover este ingrediente do banco de custos?")) return;
    try {
      await api.delete(`/pd/catalog/${id}`);
      toast.success("Removido");
      load();
    } catch (e) {
      toast.error("Erro ao remover");
    }
  };

  const openHistory = async (item) => {
    setHistoryItem(item);
    try {
      const { data } = await api.get(`/pd/catalog/${item.id}/price-history`);
      setPriceHistory(Array.isArray(data) ? data : []);
    } catch (e) {
      setPriceHistory([]);
    }
  };

  return (
    <div className="p-6 page-enter">
      <PDSubNav active="catalog" />

      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-heading font-semibold tracking-tight flex items-center gap-2">
            <Database className="h-7 w-7 text-primary" /> Banco de Custos
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Cadastro de ingredientes/MPs com preços. Usado para sugerir custos automaticamente na Manipulação.
          </p>
        </div>
        <Button onClick={openCreate} className="gap-1.5"><Plus className="h-4 w-4" /> Novo Ingrediente</Button>
      </div>

      {/* Filters */}
      <div className="flex gap-3 mb-4 flex-wrap">
        <div className="relative flex-1 min-w-[240px] max-w-md">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input placeholder="Buscar por nome, INCI, fornecedor..." value={search} onChange={(e) => setSearch(e.target.value)} className="pl-9" />
        </div>
        <Select value={filterCat} onValueChange={setFilterCat}>
          <SelectTrigger className="w-48"><SelectValue placeholder="Todas categorias" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todas categorias</SelectItem>
            {CATEGORIAS.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-muted/50 border-b">
                  <th className="text-left p-3 font-semibold">Ingrediente</th>
                  <th className="text-left p-3 font-semibold">INCI / Código</th>
                  <th className="text-left p-3 font-semibold">Fornecedores</th>
                  <th className="text-left p-3 font-semibold">Categoria</th>
                  <th className="text-left p-3 font-semibold w-32">Atualizado</th>
                  <th className="w-28"></th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={6} className="p-6 text-center text-muted-foreground">Carregando...</td></tr>
                ) : items.length === 0 ? (
                  <tr><td colSpan={6} className="p-6 text-center text-muted-foreground">Nenhum ingrediente cadastrado. Clique em "Novo Ingrediente".</td></tr>
                ) : items.map(item => {
                  const fns = (item.fornecedores || []).slice().sort((a, b) => (a.preco_rs_kg || 0) - (b.preco_rs_kg || 0));
                  const rankColor = (i) => i === 0 ? "text-green-700 bg-green-50" : i === 1 ? "text-yellow-700 bg-yellow-50" : i === 2 ? "text-orange-600 bg-orange-50" : "text-red-600 bg-red-50";
                  return (
                    <tr key={item.id} className="border-b hover:bg-muted/20">
                      <td className="p-3">
                        <div className="font-medium">{item.nome}</div>
                        {item.codigo_interno && <div className="text-[10px] text-muted-foreground">{item.codigo_interno}</div>}
                      </td>
                      <td className="p-3 text-xs text-muted-foreground">
                        {item.inci || "—"}
                      </td>
                      <td className="p-3">
                        {fns.length > 0 ? (
                          <div className="flex flex-wrap gap-1">
                            {fns.map((s, i) => (
                              <span key={i} className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium ${rankColor(i)}`}>
                                {s.nome}
                                <span className="font-mono opacity-80">{s.moeda === "USD" ? "US$" : "R$"}{(s.preco_rs_kg || 0).toFixed(2)}</span>
                              </span>
                            ))}
                          </div>
                        ) : (
                          <span className="text-xs text-muted-foreground">{item.fornecedor || "—"}</span>
                        )}
                      </td>
                      <td className="p-3">{item.categoria && <Badge variant="outline" className="text-xs">{item.categoria}</Badge>}</td>
                      <td className="p-3 text-xs text-muted-foreground">
                        {item.ultima_atualizacao ? new Date(item.ultima_atualizacao).toLocaleDateString("pt-BR") : "—"}
                        {item.atualizado_por && <div className="text-[10px]">por {item.atualizado_por}</div>}
                      </td>
                      <td className="p-3">
                        <div className="flex items-center gap-1 justify-end">
                          <Button variant="ghost" size="icon" className="h-7 w-7" title="Histórico de preço" onClick={() => openHistory(item)}>
                            <History className="h-3.5 w-3.5" />
                          </Button>
                          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => openEdit(item)}>
                            <Pencil className="h-3.5 w-3.5" />
                          </Button>
                          <Button variant="ghost" size="icon" className="h-7 w-7 hover:text-red-500" onClick={() => remove(item.id)}>
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Create/Edit Dialog */}
      <Dialog open={showForm} onOpenChange={setShowForm}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{editingId ? "Editar Ingrediente" : "Novo Ingrediente"}</DialogTitle>
            <DialogDescription>
              Cadastre o ingrediente com preço atualizado. Ele aparecerá no autocomplete da Manipulação.
            </DialogDescription>
          </DialogHeader>

          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <Label>Nome do Ingrediente *</Label>
              <Input value={form.nome} onChange={(e) => setForm(p => ({ ...p, nome: e.target.value }))} placeholder="Ex: Óleo de Coco" />
            </div>
            <div>
              <Label>INCI Name</Label>
              <Input value={form.inci} onChange={(e) => setForm(p => ({ ...p, inci: e.target.value }))} placeholder="Ex: Cocos Nucifera Oil" />
            </div>
            <div>
              <Label>Código Interno</Label>
              <Input value={form.codigo_interno} onChange={(e) => setForm(p => ({ ...p, codigo_interno: e.target.value }))} placeholder="Ex: MP-042" />
            </div>
            <div>
              <Label>Categoria</Label>
              <Select value={form.categoria} onValueChange={(v) => setForm(p => ({ ...p, categoria: v }))}>
                <SelectTrigger><SelectValue placeholder="Selecione..." /></SelectTrigger>
                <SelectContent>
                  {CATEGORIAS.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Unidade</Label>
              <Select value={form.unidade} onValueChange={(v) => setForm(p => ({ ...p, unidade: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="kg">kg</SelectItem>
                  <SelectItem value="L">Litro</SelectItem>
                  <SelectItem value="g">grama</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="col-span-2">
              <Label>Observações</Label>
              <Textarea value={form.observacoes} onChange={(e) => setForm(p => ({ ...p, observacoes: e.target.value }))} rows={2} placeholder="Lote, validade, condições..." />
            </div>

            {/* Multi-supplier section */}
            <div className="col-span-2 border-t pt-3">
              <div className="flex items-center justify-between mb-2">
                <Label className="text-sm font-semibold">Fornecedores e Preços</Label>
                <Button type="button" size="sm" variant="outline" className="h-7 text-xs gap-1"
                  onClick={() => setForm(p => ({ ...p, fornecedores: [...p.fornecedores, { ...emptyFornecedor }] }))}>
                  <Plus className="h-3 w-3" /> Adicionar Fornecedor
                </Button>
              </div>
              {form.fornecedores.length === 0 ? (
                <p className="text-xs text-muted-foreground italic">Nenhum fornecedor cadastrado. Clique em "Adicionar Fornecedor" para incluir opções de compra com preços comparativos.</p>
              ) : (
                <div className="space-y-2">
                  {form.fornecedores.map((sup, idx) => (
                    <div key={idx} className="grid grid-cols-[1fr_auto_auto_auto_auto] gap-2 items-end bg-muted/30 rounded p-2">
                      <div>
                        <Label className="text-[10px] text-muted-foreground">Nome do Fornecedor</Label>
                        <Input value={sup.nome} onChange={e => setForm(p => ({ ...p, fornecedores: p.fornecedores.map((s, i) => i === idx ? { ...s, nome: e.target.value } : s) }))} placeholder="Ex: Croda Brasil" className="h-7 text-xs" />
                      </div>
                      <div className="w-28">
                        <Label className="text-[10px] text-muted-foreground">Código do Forn.</Label>
                        <Input value={sup.codigo} onChange={e => setForm(p => ({ ...p, fornecedores: p.fornecedores.map((s, i) => i === idx ? { ...s, codigo: e.target.value } : s) }))} placeholder="Ref. fornecedor" className="h-7 text-xs" />
                      </div>
                      <div className="w-24">
                        <Label className="text-[10px] text-muted-foreground">Preço / {form.unidade}</Label>
                        <Input type="number" step="0.01" value={sup.preco_rs_kg} onChange={e => setForm(p => ({ ...p, fornecedores: p.fornecedores.map((s, i) => i === idx ? { ...s, preco_rs_kg: e.target.value } : s) }))} placeholder="0.00" className="h-7 text-xs font-mono" />
                      </div>
                      <div className="w-20">
                        <Label className="text-[10px] text-muted-foreground">Moeda</Label>
                        <Select value={sup.moeda} onValueChange={v => setForm(p => ({ ...p, fornecedores: p.fornecedores.map((s, i) => i === idx ? { ...s, moeda: v } : s) }))}>
                          <SelectTrigger className="h-7 text-xs"><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="BRL">R$</SelectItem>
                            <SelectItem value="USD">US$</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <button type="button" onClick={() => setForm(p => ({ ...p, fornecedores: p.fornecedores.filter((_, i) => i !== idx) }))} className="h-7 w-7 flex items-center justify-center text-muted-foreground hover:text-red-500 transition-colors mt-4">
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          <DialogFooter>
            <Button variant="ghost" onClick={() => setShowForm(false)}>Cancelar</Button>
            <Button onClick={save} disabled={saving}>{saving ? "Salvando..." : (editingId ? "Salvar alterações" : "Cadastrar")}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Price History Sheet */}
      <Sheet open={!!historyItem} onOpenChange={(open) => !open && setHistoryItem(null)}>
        <SheetContent side="right" className="w-[480px] sm:w-[520px]">
          <SheetHeader>
            <SheetTitle className="flex items-center gap-2"><History className="h-5 w-5" /> Histórico de Preços</SheetTitle>
          </SheetHeader>
          {historyItem && (
            <div className="mt-6 space-y-4">
              <Card>
                <CardContent className="p-4">
                  <p className="font-semibold">{historyItem.nome}</p>
                  <p className="text-xs text-muted-foreground">{historyItem.fornecedor || "Sem fornecedor"}</p>
                  <p className="text-2xl font-bold mt-2">
                    {historyItem.moeda === "USD" ? "US$ " : "R$ "}{(historyItem.preco_rs_kg || 0).toFixed(2)}
                    <span className="text-xs font-normal text-muted-foreground ml-1">/ {historyItem.unidade}</span>
                  </p>
                </CardContent>
              </Card>
              <div>
                <h4 className="text-sm font-semibold mb-2">Alterações</h4>
                {priceHistory.length === 0 ? (
                  <p className="text-sm text-muted-foreground italic">Sem alterações de preço registradas.</p>
                ) : (
                  <div className="space-y-2">
                    {priceHistory.map(h => {
                      const up = h.preco_novo > h.preco_anterior;
                      const diff = h.preco_novo - h.preco_anterior;
                      const pct = h.preco_anterior > 0 ? (diff / h.preco_anterior * 100) : 0;
                      return (
                        <div key={h.id} className="border rounded-md p-3 text-sm">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                              {up ? <TrendingUp className="h-4 w-4 text-red-500" /> : <TrendingDown className="h-4 w-4 text-green-500" />}
                              <span className="font-mono">
                                R$ {h.preco_anterior?.toFixed(2)} → R$ {h.preco_novo?.toFixed(2)}
                              </span>
                            </div>
                            <Badge variant={up ? "destructive" : "default"} className="text-[10px]">
                              {up ? "+" : ""}{pct.toFixed(1)}%
                            </Badge>
                          </div>
                          <p className="text-xs text-muted-foreground mt-1">
                            {h.atualizado_por || "—"} • {new Date(h.created_at).toLocaleString("pt-BR")}
                          </p>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
