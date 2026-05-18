import React, { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { toast } from "sonner";
import { ArrowLeft, FlaskConical, Search, UserCircle, X } from "lucide-react";

export default function PDNewRequest() {
  const navigate = useNavigate();
  const [saving, setSaving] = useState(false);
  const [clientSearch, setClientSearch] = useState("");
  const [clientResults, setClientResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [showClientDropdown, setShowClientDropdown] = useState(false);

  const [form, setForm] = useState({
    client_card_id: null,
    client_name: "",
    project_name: "",
    request_type: "Produto Novo",
    category: "",
    description: "",
    references: "",
    restrictions: "",
    volume: "",
    packaging: "",
    priority: "Normal",
    deadline: "",
  });

  const searchClients = useCallback(async (q) => {
    if (!q || q.length < 2) {
      setClientResults([]);
      return;
    }
    setSearching(true);
    try {
      const res = await api.get(`/pd/clients/search?q=${encodeURIComponent(q)}`);
      setClientResults(res.data);
      setShowClientDropdown(true);
    } catch {
      setClientResults([]);
    } finally {
      setSearching(false);
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => searchClients(clientSearch), 300);
    return () => clearTimeout(timer);
  }, [clientSearch, searchClients]);

  const selectClient = (client) => {
    setForm(prev => ({
      ...prev,
      client_card_id: client.id,
      client_name: client.nome_cliente,
    }));
    setClientSearch(client.nome_cliente);
    setShowClientDropdown(false);
  };

  const clearClient = () => {
    setForm(prev => ({ ...prev, client_card_id: null, client_name: "" }));
    setClientSearch("");
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.project_name.trim()) {
      toast.error("Nome do projeto é obrigatório");
      return;
    }

    // If client_name was typed manually (not selected from CRM)
    const payload = { ...form };
    if (!payload.client_card_id && clientSearch) {
      payload.client_name = clientSearch;
    }

    setSaving(true);
    try {
      const res = await api.post("/pd/requests", payload);
      toast.success("Solicitação criada com sucesso!");
      navigate(`/pd/${res.data.id}`);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Erro ao criar solicitação");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="h-full overflow-auto">
      <div className="max-w-3xl mx-auto p-6">
        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <Button variant="ghost" size="icon" onClick={() => navigate("/pd")}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <h1 className="text-xl font-bold flex items-center gap-2">
              <FlaskConical className="h-5 w-5" />
              Nova Solicitação P&D
            </h1>
            <p className="text-sm text-muted-foreground">Registre uma nova solicitação de desenvolvimento</p>
          </div>
        </div>

        <form onSubmit={handleSubmit}>
          {/* Client Selection */}
          <Card className="mb-4">
            <CardHeader className="pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <UserCircle className="h-4 w-4" />
                Cliente
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="relative">
                <Label className="text-xs text-muted-foreground mb-1.5 block">
                  Buscar no CRM ou digitar manualmente
                </Label>
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder="Nome do cliente..."
                    value={clientSearch}
                    onChange={(e) => {
                      setClientSearch(e.target.value);
                      if (form.client_card_id) {
                        setForm(prev => ({ ...prev, client_card_id: null }));
                      }
                    }}
                    onFocus={() => clientResults.length > 0 && setShowClientDropdown(true)}
                    className="pl-9 pr-8"
                  />
                  {clientSearch && (
                    <button type="button" onClick={clearClient} className="absolute right-3 top-1/2 -translate-y-1/2">
                      <X className="h-4 w-4 text-muted-foreground hover:text-foreground" />
                    </button>
                  )}
                </div>
                {form.client_card_id && (
                  <p className="text-xs text-green-600 mt-1">✓ Cliente vinculado ao CRM</p>
                )}
                {clientSearch && !form.client_card_id && clientSearch.length >= 2 && !searching && clientResults.length === 0 && (
                  <p className="text-xs text-muted-foreground mt-1">Cliente não encontrado no CRM — será cadastrado manualmente</p>
                )}
                {showClientDropdown && clientResults.length > 0 && (
                  <div className="absolute z-50 top-full left-0 right-0 mt-1 bg-popover border rounded-md shadow-lg max-h-48 overflow-y-auto">
                    {clientResults.map(c => (
                      <button
                        key={c.id}
                        type="button"
                        onClick={() => selectClient(c)}
                        className="w-full text-left px-3 py-2 hover:bg-accent text-sm flex items-center justify-between"
                      >
                        <span className="font-medium">{c.nome_cliente}</span>
                        <span className="text-xs text-muted-foreground">{c.email || c.telefone || ""}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Main Info */}
          <Card className="mb-4">
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Informações do Projeto</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label>Nome do Projeto *</Label>
                <Input
                  value={form.project_name}
                  onChange={(e) => setForm(prev => ({ ...prev, project_name: e.target.value }))}
                  placeholder="Ex: Creme Anti-idade Premium"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Tipo</Label>
                  <Select value={form.request_type} onValueChange={(v) => setForm(prev => ({ ...prev, request_type: v }))}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="Produto Novo">Produto Novo</SelectItem>
                      <SelectItem value="Reformulação">Reformulação</SelectItem>
                      <SelectItem value="Extensão de Linha">Extensão de Linha</SelectItem>
                      <SelectItem value="Adequação Regulatória">Adequação Regulatória</SelectItem>
                      <SelectItem value="Outro">Outro</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Categoria</Label>
                  <Select value={form.category} onValueChange={(v) => setForm(prev => ({ ...prev, category: v }))}>
                    <SelectTrigger>
                      <SelectValue placeholder="Selecionar..." />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="Skincare">Skincare</SelectItem>
                      <SelectItem value="Haircare">Haircare</SelectItem>
                      <SelectItem value="Bodycare">Bodycare</SelectItem>
                      <SelectItem value="Perfumaria">Perfumaria</SelectItem>
                      <SelectItem value="Maquiagem">Maquiagem</SelectItem>
                      <SelectItem value="Higiene">Higiene</SelectItem>
                      <SelectItem value="Outro">Outro</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div>
                <Label>Descrição</Label>
                <Textarea
                  value={form.description}
                  onChange={(e) => setForm(prev => ({ ...prev, description: e.target.value }))}
                  placeholder="Descreva o produto desejado, características, público-alvo..."
                  rows={3}
                />
              </div>

              <div>
                <Label>Referências</Label>
                <Textarea
                  value={form.references}
                  onChange={(e) => setForm(prev => ({ ...prev, references: e.target.value }))}
                  placeholder="Produtos de referência, marcas concorrentes..."
                  rows={2}
                />
              </div>

              <div>
                <Label>Restrições</Label>
                <Textarea
                  value={form.restrictions}
                  onChange={(e) => setForm(prev => ({ ...prev, restrictions: e.target.value }))}
                  placeholder="Ingredientes proibidos, alérgenos, vegano, etc..."
                  rows={2}
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Volume Estimado</Label>
                  <Input
                    value={form.volume}
                    onChange={(e) => setForm(prev => ({ ...prev, volume: e.target.value }))}
                    placeholder="Ex: 5.000 unidades/mês"
                  />
                </div>
                <div>
                  <Label>Embalagem</Label>
                  <Input
                    value={form.packaging}
                    onChange={(e) => setForm(prev => ({ ...prev, packaging: e.target.value }))}
                    placeholder="Ex: Frasco 200ml, Bisnaga 100g"
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Priority & Deadline */}
          <Card className="mb-6">
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Prioridade & Prazo</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Prioridade</Label>
                  <Select value={form.priority} onValueChange={(v) => setForm(prev => ({ ...prev, priority: v }))}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="Baixa">Baixa</SelectItem>
                      <SelectItem value="Normal">Normal</SelectItem>
                      <SelectItem value="Alta">Alta</SelectItem>
                      <SelectItem value="Urgente">Urgente</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Prazo</Label>
                  <Input
                    type="date"
                    value={form.deadline}
                    onChange={(e) => setForm(prev => ({ ...prev, deadline: e.target.value }))}
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Actions */}
          <div className="flex justify-end gap-3">
            <Button type="button" variant="outline" onClick={() => navigate("/pd")}>
              Cancelar
            </Button>
            <Button type="submit" disabled={saving}>
              {saving ? "Criando..." : "Criar Solicitação"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
