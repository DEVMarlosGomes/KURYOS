import { useCallback, useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import PDSubNav from "@/components/PDSubNav";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Plus, Search, ShieldCheck, Factory, FlaskConical, AlertTriangle, Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";

const SUPPLIER_STATUS_OPTIONS = [
  { value: "all", label: "Todos os status" },
  { value: "pendente", label: "Em avaliação" },
  { value: "homologado", label: "Homologado" },
  { value: "rejeitado", label: "Reprovado" },
];

const MP_STATUS_OPTIONS = [
  { value: "all", label: "Todos os status" },
  { value: "pendente", label: "Em avaliação" },
  { value: "homologada", label: "Homologada" },
  { value: "rejeitada", label: "Reprovada" },
];

const MP_TYPE_OPTIONS = [
  { value: "all", label: "Todos os tipos" },
  { value: "FORMULACAO", label: "Formulação" },
  { value: "ROTULO", label: "Rótulo" },
  { value: "EMBALAGEM", label: "Embalagem" },
];

const emptySupplier = {
  razao_social: "",
  cnpj: "",
  nome_fantasia: "",
  contato_nome: "",
  contato_email: "",
  contato_telefone: "",
  endereco: "",
  categoria: "",
  observacoes: "",
};

const emptyMp = {
  nome: "",
  codigo_interno: "",
  inci: "",
  tipo_mp: "FORMULACAO",
  fornecedor_id: "none",
  fornecedor_nome: "",
  funcao: "",
  custo_referencia: "",
  unidade: "kg",
  especificacoes_tecnicas: "",
  certificados: "",
  msds_url: "",
  validade_laudo: "",
  observacoes: "",
};

const supplierStatusLabel = {
  pendente: "Em avaliação",
  homologado: "Homologado",
  rejeitado: "Reprovado",
};

const mpStatusLabel = {
  pendente: "Em avaliação",
  homologada: "Homologada",
  rejeitada: "Reprovada",
};

export default function PDHomologacao() {
  const [activeTab, setActiveTab] = useState("fornecedores");
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [supplierStatus, setSupplierStatus] = useState("all");
  const [mpStatus, setMpStatus] = useState("all");
  const [mpType, setMpType] = useState("all");
  const [dashboard, setDashboard] = useState(null);
  const [suppliers, setSuppliers] = useState([]);
  const [allSuppliers, setAllSuppliers] = useState([]);
  const [mps, setMps] = useState([]);
  const [allMps, setAllMps] = useState([]);
  const [showSupplierForm, setShowSupplierForm] = useState(false);
  const [showMpForm, setShowMpForm] = useState(false);
  const [supplierForm, setSupplierForm] = useState(emptySupplier);
  const [mpForm, setMpForm] = useState(emptyMp);
  const [editingSupplier, setEditingSupplier] = useState(null);
  const [editingMp, setEditingMp] = useState(null);
  const [statusDialog, setStatusDialog] = useState(null);
  const [parecer, setParecer] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const supplierParams = {};
      if (supplierStatus !== "all") supplierParams.status = supplierStatus;
      if (search.trim()) supplierParams.search = search.trim();

      const mpParams = {};
      if (mpStatus !== "all") mpParams.status = mpStatus;
      if (mpType !== "all") mpParams.tipo_mp = mpType;
      if (search.trim()) mpParams.search = search.trim();

      const [dashboardRes, suppliersRes, mpsRes, allSuppliersRes, allMpsRes] = await Promise.all([
        api.get("/pd/homologacao/dashboard"),
        api.get("/pd/homologacao/fornecedores", { params: supplierParams }),
        api.get("/pd/homologacao/mps", { params: mpParams }),
        api.get("/pd/homologacao/fornecedores"),
        api.get("/pd/homologacao/mps"),
      ]);
      setDashboard(dashboardRes.data || null);
      setSuppliers(Array.isArray(suppliersRes.data) ? suppliersRes.data : []);
      setMps(Array.isArray(mpsRes.data) ? mpsRes.data : []);
      setAllSuppliers(Array.isArray(allSuppliersRes.data) ? allSuppliersRes.data : []);
      setAllMps(Array.isArray(allMpsRes.data) ? allMpsRes.data : []);
    } catch (err) {
      toast.error("Erro ao carregar homologações");
    } finally {
      setLoading(false);
    }
  }, [mpStatus, mpType, search, supplierStatus]);

  useEffect(() => {
    load();
  }, [load]);

  const homologatedSuppliersByMp = useMemo(() => {
    const map = {};
    allMps
      .filter(item => item.status === "homologada")
      .forEach((item) => {
        const key = (item.nome || "").trim().toLowerCase();
        if (!key) return;
        if (!map[key]) map[key] = new Set();
        map[key].add(item.fornecedor_id || item.fornecedor_nome || item.id);
      });
    return map;
  }, [allMps]);

  const openSupplierCreate = () => {
    setEditingSupplier(null);
    setSupplierForm(emptySupplier);
    setShowSupplierForm(true);
  };

  const openSupplierEdit = (supplier) => {
    setEditingSupplier(supplier);
    setSupplierForm({
      razao_social: supplier.razao_social || "",
      cnpj: supplier.cnpj || "",
      nome_fantasia: supplier.nome_fantasia || "",
      contato_nome: supplier.contato_nome || "",
      contato_email: supplier.contato_email || "",
      contato_telefone: supplier.contato_telefone || "",
      endereco: supplier.endereco || "",
      categoria: supplier.categoria || "",
      observacoes: supplier.observacoes || "",
    });
    setShowSupplierForm(true);
  };

  const openMpCreate = () => {
    setEditingMp(null);
    setMpForm(emptyMp);
    setShowMpForm(true);
  };

  const openMpEdit = (mp) => {
    setEditingMp(mp);
    setMpForm({
      nome: mp.nome || "",
      codigo_interno: mp.codigo_interno || "",
      inci: mp.inci || "",
      tipo_mp: mp.tipo_mp || "FORMULACAO",
      fornecedor_id: mp.fornecedor_id || "none",
      fornecedor_nome: mp.fornecedor_nome || "",
      funcao: mp.funcao || "",
      custo_referencia: mp.custo_referencia != null ? String(mp.custo_referencia) : "",
      unidade: mp.unidade || "kg",
      especificacoes_tecnicas: mp.especificacoes_tecnicas || "",
      certificados: Array.isArray(mp.certificados) ? mp.certificados.join("\n") : "",
      msds_url: mp.msds_url || "",
      validade_laudo: mp.validade_laudo ? mp.validade_laudo.slice(0, 10) : "",
      observacoes: mp.observacoes || "",
    });
    setShowMpForm(true);
  };

  const saveSupplier = async () => {
    if (!supplierForm.razao_social.trim()) {
      return toast.error("Razão social é obrigatória");
    }
    setSaving(true);
    try {
      if (editingSupplier) {
        await api.put(`/pd/homologacao/fornecedores/${editingSupplier.id}`, supplierForm);
        toast.success("Fornecedor atualizado");
      } else {
        await api.post("/pd/homologacao/fornecedores", supplierForm);
        toast.success("Fornecedor cadastrado");
      }
      setShowSupplierForm(false);
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Erro ao salvar fornecedor");
    } finally {
      setSaving(false);
    }
  };

  const saveMp = async () => {
    if (!mpForm.nome.trim()) {
      return toast.error("Nome da MP é obrigatório");
    }
    setSaving(true);
    try {
      const payload = {
        ...mpForm,
        fornecedor_id: mpForm.fornecedor_id === "none" ? "" : mpForm.fornecedor_id,
        custo_referencia: mpForm.custo_referencia ? parseFloat(mpForm.custo_referencia) : null,
        certificados: mpForm.certificados
          .split("\n")
          .map(item => item.trim())
          .filter(Boolean),
        validade_laudo: mpForm.validade_laudo || null,
      };
      if (editingMp) {
        await api.put(`/pd/homologacao/mps/${editingMp.id}`, payload);
        toast.success("MP atualizada");
      } else {
        await api.post("/pd/homologacao/mps", payload);
        toast.success("MP cadastrada");
      }
      setShowMpForm(false);
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Erro ao salvar MP");
    } finally {
      setSaving(false);
    }
  };

  const removeSupplier = async (supplier) => {
    if (!window.confirm(`Remover fornecedor ${supplier.razao_social}?`)) return;
    try {
      await api.delete(`/pd/homologacao/fornecedores/${supplier.id}`);
      toast.success("Fornecedor removido");
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Erro ao remover fornecedor");
    }
  };

  const removeMp = async (mp) => {
    if (!window.confirm(`Remover MP ${mp.nome}?`)) return;
    try {
      await api.delete(`/pd/homologacao/mps/${mp.id}`);
      toast.success("MP removida");
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Erro ao remover MP");
    }
  };

  const openStatusDialog = (entityType, entity, approved) => {
    setStatusDialog({ entityType, entity, approved });
    setParecer(entity.parecer_homologacao || "");
  };

  const submitStatus = async () => {
    if (!statusDialog) return;
    setSaving(true);
    try {
      const { entityType, entity, approved } = statusDialog;
      const endpoint = entityType === "supplier"
        ? `/pd/homologacao/fornecedores/${entity.id}/homologar`
        : `/pd/homologacao/mps/${entity.id}/homologar`;
      await api.post(endpoint, { aprovado: approved, parecer });
      toast.success(approved ? "Homologação registrada" : "Reprovação registrada");
      setStatusDialog(null);
      setParecer("");
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Erro ao atualizar status");
    } finally {
      setSaving(false);
    }
  };

  const supplierOptions = allSuppliers;

  return (
    <div className="p-6 page-enter">
      <PDSubNav active="homologacao" />

      <div className="flex items-center justify-between mb-6 gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-heading font-semibold tracking-tight flex items-center gap-2">
            <ShieldCheck className="h-7 w-7 text-primary" /> Homologações
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Gestão de fornecedores e matérias-primas aprovadas para compras e escala produtiva.
          </p>
        </div>
        <div className="flex gap-2">
          {activeTab === "fornecedores" ? (
            <Button onClick={openSupplierCreate} className="gap-1.5">
              <Plus className="h-4 w-4" /> Novo Fornecedor
            </Button>
          ) : (
            <Button onClick={openMpCreate} className="gap-1.5">
              <Plus className="h-4 w-4" /> Nova MP
            </Button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-5">
        <DashCard icon={Factory} title="Fornecedores" value={dashboard?.fornecedores?.total || 0} />
        <DashCard icon={ShieldCheck} title="Fornec. homologados" value={dashboard?.fornecedores?.por_status?.homologado || 0} />
        <DashCard icon={FlaskConical} title="MPs" value={dashboard?.mps?.total || 0} />
        <DashCard icon={AlertTriangle} title="MPs pendentes" value={dashboard?.mps?.por_status?.pendente || 0} />
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <div className="flex gap-3 mb-4 flex-wrap">
          <TabsList>
            <TabsTrigger value="fornecedores" className="gap-1.5">
              <Factory className="h-3.5 w-3.5" /> Fornecedores
            </TabsTrigger>
            <TabsTrigger value="mps" className="gap-1.5">
              <FlaskConical className="h-3.5 w-3.5" /> Matérias-primas
            </TabsTrigger>
          </TabsList>

          <div className="relative flex-1 min-w-[240px] max-w-lg">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder={activeTab === "fornecedores" ? "Buscar fornecedor..." : "Buscar MP, INCI ou fornecedor..."}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9"
            />
          </div>

          {activeTab === "fornecedores" ? (
            <Select value={supplierStatus} onValueChange={setSupplierStatus}>
              <SelectTrigger className="w-48">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                {SUPPLIER_STATUS_OPTIONS.map(option => (
                  <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : (
            <>
              <Select value={mpStatus} onValueChange={setMpStatus}>
                <SelectTrigger className="w-48">
                  <SelectValue placeholder="Status" />
                </SelectTrigger>
                <SelectContent>
                  {MP_STATUS_OPTIONS.map(option => (
                    <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select value={mpType} onValueChange={setMpType}>
                <SelectTrigger className="w-44">
                  <SelectValue placeholder="Tipo" />
                </SelectTrigger>
                <SelectContent>
                  {MP_TYPE_OPTIONS.map(option => (
                    <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </>
          )}
        </div>

        <TabsContent value="fornecedores">
          <Card>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-muted/50 border-b">
                      <th className="text-left p-3 font-semibold">Fornecedor</th>
                      <th className="text-left p-3 font-semibold">Contato</th>
                      <th className="text-left p-3 font-semibold">Categoria</th>
                      <th className="text-left p-3 font-semibold">Status</th>
                      <th className="text-left p-3 font-semibold">Homologação</th>
                      <th className="w-56"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading ? (
                      <tr>
                        <td colSpan={6} className="p-6 text-center text-muted-foreground">Carregando...</td>
                      </tr>
                    ) : suppliers.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="p-6 text-center text-muted-foreground">Nenhum fornecedor encontrado.</td>
                      </tr>
                    ) : suppliers.map((supplier) => (
                      <tr key={supplier.id} className="border-b hover:bg-muted/20">
                        <td className="p-3">
                          <div className="font-medium">{supplier.razao_social}</div>
                          <div className="text-[11px] text-muted-foreground">
                            {supplier.nome_fantasia || "Sem nome fantasia"} {supplier.cnpj ? `• ${supplier.cnpj}` : ""}
                          </div>
                        </td>
                        <td className="p-3">
                          <div>{supplier.contato_nome || "—"}</div>
                          <div className="text-[11px] text-muted-foreground">{supplier.contato_email || supplier.contato_telefone || "—"}</div>
                        </td>
                        <td className="p-3">{supplier.categoria || "—"}</td>
                        <td className="p-3">
                          <StatusBadge type="supplier" status={supplier.status} />
                        </td>
                        <td className="p-3">
                          {supplier.data_homologacao
                            ? new Date(supplier.data_homologacao).toLocaleDateString("pt-BR")
                            : "—"}
                        </td>
                        <td className="p-3">
                          <div className="flex items-center justify-end gap-1 flex-wrap">
                            <Button size="sm" variant="outline" onClick={() => openStatusDialog("supplier", supplier, true)}>Homologar</Button>
                            <Button size="sm" variant="outline" onClick={() => openStatusDialog("supplier", supplier, false)}>Reprovar</Button>
                            <IconButton icon={Pencil} onClick={() => openSupplierEdit(supplier)} title="Editar" />
                            <IconButton icon={Trash2} onClick={() => removeSupplier(supplier)} title="Remover" className="hover:text-red-500" />
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="mps">
          <Card>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-muted/50 border-b">
                      <th className="text-left p-3 font-semibold">MP</th>
                      <th className="text-left p-3 font-semibold">Fornecedor</th>
                      <th className="text-left p-3 font-semibold">Tipo</th>
                      <th className="text-left p-3 font-semibold">Status</th>
                      <th className="text-left p-3 font-semibold">Risco fornecedores</th>
                      <th className="w-56"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading ? (
                      <tr>
                        <td colSpan={6} className="p-6 text-center text-muted-foreground">Carregando...</td>
                      </tr>
                    ) : mps.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="p-6 text-center text-muted-foreground">Nenhuma MP encontrada.</td>
                      </tr>
                    ) : mps.map((mp) => {
                      const normalizedName = (mp.nome || "").trim().toLowerCase();
                      const homologatedSuppliers = homologatedSuppliersByMp[normalizedName]?.size || 0;
                      const risk = getRiskBadge(homologatedSuppliers, mp.status);
                      return (
                        <tr key={mp.id} className="border-b hover:bg-muted/20">
                          <td className="p-3">
                            <div className="font-medium">{mp.nome}</div>
                            <div className="text-[11px] text-muted-foreground">
                              {mp.codigo_interno || "Sem código"} {mp.inci ? `• ${mp.inci}` : ""}
                            </div>
                          </td>
                          <td className="p-3">{mp.fornecedor_nome || "Fornecedor não vinculado"}</td>
                          <td className="p-3">{mp.tipo_mp || "—"}</td>
                          <td className="p-3">
                            <StatusBadge type="mp" status={mp.status} />
                          </td>
                          <td className="p-3">
                            {risk}
                          </td>
                          <td className="p-3">
                            <div className="flex items-center justify-end gap-1 flex-wrap">
                              <Button size="sm" variant="outline" onClick={() => openStatusDialog("mp", mp, true)}>Homologar</Button>
                              <Button size="sm" variant="outline" onClick={() => openStatusDialog("mp", mp, false)}>Reprovar</Button>
                              <IconButton icon={Pencil} onClick={() => openMpEdit(mp)} title="Editar" />
                              <IconButton icon={Trash2} onClick={() => removeMp(mp)} title="Remover" className="hover:text-red-500" />
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
        </TabsContent>
      </Tabs>

      <Dialog open={showSupplierForm} onOpenChange={setShowSupplierForm}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>{editingSupplier ? "Editar fornecedor" : "Novo fornecedor"}</DialogTitle>
            <DialogDescription>
              Cadastro base para homologação e liberação futura para compras.
            </DialogDescription>
          </DialogHeader>

          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <Label>Razão social *</Label>
              <Input value={supplierForm.razao_social} onChange={(e) => setSupplierForm(p => ({ ...p, razao_social: e.target.value }))} />
            </div>
            <div>
              <Label>CNPJ</Label>
              <Input value={supplierForm.cnpj} onChange={(e) => setSupplierForm(p => ({ ...p, cnpj: e.target.value }))} />
            </div>
            <div>
              <Label>Nome fantasia</Label>
              <Input value={supplierForm.nome_fantasia} onChange={(e) => setSupplierForm(p => ({ ...p, nome_fantasia: e.target.value }))} />
            </div>
            <div>
              <Label>Contato</Label>
              <Input value={supplierForm.contato_nome} onChange={(e) => setSupplierForm(p => ({ ...p, contato_nome: e.target.value }))} />
            </div>
            <div>
              <Label>E-mail</Label>
              <Input value={supplierForm.contato_email} onChange={(e) => setSupplierForm(p => ({ ...p, contato_email: e.target.value }))} />
            </div>
            <div>
              <Label>Telefone / WhatsApp</Label>
              <Input value={supplierForm.contato_telefone} onChange={(e) => setSupplierForm(p => ({ ...p, contato_telefone: e.target.value }))} />
            </div>
            <div>
              <Label>Categoria</Label>
              <Input value={supplierForm.categoria} onChange={(e) => setSupplierForm(p => ({ ...p, categoria: e.target.value }))} placeholder="MP formulação, embalagem, serviço..." />
            </div>
            <div className="col-span-2">
              <Label>Endereço</Label>
              <Input value={supplierForm.endereco} onChange={(e) => setSupplierForm(p => ({ ...p, endereco: e.target.value }))} />
            </div>
            <div className="col-span-2">
              <Label>Observações</Label>
              <Textarea value={supplierForm.observacoes} onChange={(e) => setSupplierForm(p => ({ ...p, observacoes: e.target.value }))} rows={3} />
            </div>
          </div>

          <DialogFooter>
            <Button variant="ghost" onClick={() => setShowSupplierForm(false)}>Cancelar</Button>
            <Button onClick={saveSupplier} disabled={saving}>{saving ? "Salvando..." : "Salvar fornecedor"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={showMpForm} onOpenChange={setShowMpForm}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editingMp ? "Editar MP" : "Nova MP"}</DialogTitle>
            <DialogDescription>
              Cadastro da matéria-prima por fornecedor, com evidências e vínculo para homologação.
            </DialogDescription>
          </DialogHeader>

          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <Label>Nome da MP *</Label>
              <Input value={mpForm.nome} onChange={(e) => setMpForm(p => ({ ...p, nome: e.target.value }))} />
            </div>
            <div>
              <Label>Código interno</Label>
              <Input value={mpForm.codigo_interno} onChange={(e) => setMpForm(p => ({ ...p, codigo_interno: e.target.value }))} />
            </div>
            <div>
              <Label>INCI</Label>
              <Input value={mpForm.inci} onChange={(e) => setMpForm(p => ({ ...p, inci: e.target.value }))} />
            </div>
            <div>
              <Label>Tipo</Label>
              <Select value={mpForm.tipo_mp} onValueChange={(value) => setMpForm(p => ({ ...p, tipo_mp: value }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="FORMULACAO">Formulação</SelectItem>
                  <SelectItem value="ROTULO">Rótulo</SelectItem>
                  <SelectItem value="EMBALAGEM">Embalagem</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Fornecedor vinculado</Label>
              <Select value={mpForm.fornecedor_id} onValueChange={(value) => {
                const supplier = supplierOptions.find(item => item.id === value);
                setMpForm(p => ({
                  ...p,
                  fornecedor_id: value,
                  fornecedor_nome: supplier?.nome_fantasia || supplier?.razao_social || p.fornecedor_nome,
                }));
              }}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Sem vínculo</SelectItem>
                  {supplierOptions.map(supplier => (
                    <SelectItem key={supplier.id} value={supplier.id}>
                      {supplier.nome_fantasia || supplier.razao_social}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Fornecedor (snapshot)</Label>
              <Input value={mpForm.fornecedor_nome} onChange={(e) => setMpForm(p => ({ ...p, fornecedor_nome: e.target.value }))} />
            </div>
            <div>
              <Label>Função</Label>
              <Input value={mpForm.funcao} onChange={(e) => setMpForm(p => ({ ...p, funcao: e.target.value }))} />
            </div>
            <div>
              <Label>Custo de referência</Label>
              <Input type="number" step="0.01" value={mpForm.custo_referencia} onChange={(e) => setMpForm(p => ({ ...p, custo_referencia: e.target.value }))} />
            </div>
            <div>
              <Label>Unidade</Label>
              <Input value={mpForm.unidade} onChange={(e) => setMpForm(p => ({ ...p, unidade: e.target.value }))} />
            </div>
            <div>
              <Label>Validade do laudo</Label>
              <Input type="date" value={mpForm.validade_laudo} onChange={(e) => setMpForm(p => ({ ...p, validade_laudo: e.target.value }))} />
            </div>
            <div className="col-span-2">
              <Label>Especificações técnicas</Label>
              <Textarea value={mpForm.especificacoes_tecnicas} onChange={(e) => setMpForm(p => ({ ...p, especificacoes_tecnicas: e.target.value }))} rows={3} />
            </div>
            <div className="col-span-2">
              <Label>Certificados / laudos (um por linha)</Label>
              <Textarea value={mpForm.certificados} onChange={(e) => setMpForm(p => ({ ...p, certificados: e.target.value }))} rows={3} />
            </div>
            <div className="col-span-2">
              <Label>FISPQ / MSDS URL</Label>
              <Input value={mpForm.msds_url} onChange={(e) => setMpForm(p => ({ ...p, msds_url: e.target.value }))} />
            </div>
            <div className="col-span-2">
              <Label>Observações</Label>
              <Textarea value={mpForm.observacoes} onChange={(e) => setMpForm(p => ({ ...p, observacoes: e.target.value }))} rows={3} />
            </div>
          </div>

          <DialogFooter>
            <Button variant="ghost" onClick={() => setShowMpForm(false)}>Cancelar</Button>
            <Button onClick={saveMp} disabled={saving}>{saving ? "Salvando..." : "Salvar MP"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!statusDialog} onOpenChange={(open) => !open && setStatusDialog(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{statusDialog?.approved ? "Confirmar homologação" : "Registrar reprovação"}</DialogTitle>
            <DialogDescription>
              {statusDialog?.entityType === "supplier" ? "Fornecedor" : "MP"}: {statusDialog?.entity?.razao_social || statusDialog?.entity?.nome}
            </DialogDescription>
          </DialogHeader>

          <div>
            <Label>Parecer</Label>
            <Textarea value={parecer} onChange={(e) => setParecer(e.target.value)} rows={4} placeholder="Motivo, observações, restrições ou justificativa..." />
          </div>

          <DialogFooter>
            <Button variant="ghost" onClick={() => setStatusDialog(null)}>Cancelar</Button>
            <Button onClick={submitStatus} disabled={saving}>{saving ? "Salvando..." : "Confirmar"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function DashCard({ icon: Icon, title, value }) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center">
            <Icon className="h-5 w-5 text-primary" />
          </div>
          <div>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">{title}</p>
            <p className="text-2xl font-semibold mono-num">{value}</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function IconButton({ icon: Icon, className = "", title, onClick }) {
  return (
    <Button variant="ghost" size="icon" className={`h-8 w-8 ${className}`} title={title} onClick={onClick}>
      <Icon className="h-3.5 w-3.5" />
    </Button>
  );
}

function StatusBadge({ type, status }) {
  const label = type === "supplier" ? supplierStatusLabel[status] : mpStatusLabel[status];
  const className = status === "homologado" || status === "homologada"
    ? "bg-green-600 hover:bg-green-600"
    : status === "rejeitado" || status === "rejeitada"
      ? "bg-red-600 hover:bg-red-600"
      : "";
  return <Badge className={className}>{label || status || "—"}</Badge>;
}

function getRiskBadge(homologatedSuppliers, status) {
  if (status !== "homologada") {
    return <span className="text-xs text-muted-foreground">Aguardando homologação</span>;
  }
  if (homologatedSuppliers <= 1) {
    return <Badge variant="destructive">Crítico: fornecedor único</Badge>;
  }
  if (homologatedSuppliers < 3) {
    return <Badge className="bg-amber-500 hover:bg-amber-500">Risco: menos de 3 fornecedores</Badge>;
  }
  return <Badge className="bg-green-600 hover:bg-green-600">Cobertura adequada</Badge>;
}
