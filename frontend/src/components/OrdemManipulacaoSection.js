/**
 * Item 3 — Ordens de Manipulação (OM) Section
 * Permite gerar OMs em lote para variações que compartilham a mesma base.
 */
import React, { useState, useEffect } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Beaker, Plus, FileText, Trash2, Loader2, Download } from "lucide-react";
import { toast } from "sonner";
import { BACKEND_URL } from "@/lib/backend";

const STATUS_COLORS = {
  rascunho: "bg-slate-100 text-slate-700 border-slate-300",
  emitida: "bg-blue-100 text-blue-800 border-blue-300",
  executada: "bg-green-100 text-green-800 border-green-300",
};

export default function OrdemManipulacaoSection({ sampleId, formulas = [], variacoes = [] }) {
  const [ordens, setOrdens] = useState([]);
  const [criando, setCriando] = useState(false);
  const [selectedVariacoes, setSelectedVariacoes] = useState([]);
  const [formulaBaseId, setFormulaBaseId] = useState("");
  const [volumeAmostra, setVolumeAmostra] = useState(15);
  const [fatorPerda, setFatorPerda] = useState(10);
  const [observacoes, setObservacoes] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const fetchOMs = async () => {
    if (!sampleId) return;
    setLoading(true);
    try {
      const { data } = await api.get(`/pd/ordens-manipulacao?sample_id=${sampleId}`);
      setOrdens(Array.isArray(data) ? data : []);
    } catch (e) {
      console.error("Erro buscando OMs", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOMs();
  }, [sampleId]);

  const handleCriar = async () => {
    if (!formulaBaseId) return toast.error("Selecione a fórmula base");
    if (selectedVariacoes.length === 0) return toast.error("Selecione ao menos uma variação");
    setSaving(true);
    try {
      const { data } = await api.post("/pd/ordens-manipulacao", {
        sample_id: sampleId,
        variacao_ids: selectedVariacoes,
        formula_base_id: formulaBaseId,
        volume_amostra_ml: parseFloat(volumeAmostra) || 15,
        fator_perda_pct: parseFloat(fatorPerda) || 10,
        observacoes: observacoes || null,
      });
      toast.success(`OM ${data.numero_om} criada!`);
      setOrdens((prev) => [data, ...prev]);
      setCriando(false);
      setSelectedVariacoes([]);
      setObservacoes("");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Erro ao criar OM");
    } finally {
      setSaving(false);
    }
  };

  const handleStatusChange = async (omId, novoStatus) => {
    try {
      await api.put(`/pd/ordens-manipulacao/${omId}/status`, { status: novoStatus });
      toast.success(`OM ${novoStatus}`);
      fetchOMs();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Erro");
    }
  };

  const handleDelete = async (omId, numero) => {
    if (!window.confirm(`Remover ${numero}?`)) return;
    try {
      await api.delete(`/pd/ordens-manipulacao/${omId}`);
      toast.success("OM removida");
      fetchOMs();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Erro ao remover");
    }
  };

  const pdfUrl = (omId) => `${BACKEND_URL}/api/pd/ordens-manipulacao/${omId}/pdf`;

  if (!sampleId) {
    return (
      <Card data-testid="om-section-empty">
        <CardContent className="pt-6 text-sm text-muted-foreground">
          OMs ficam disponíveis quando há amostra vinculada (CRM).
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4" data-testid="ordem-manipulacao-section">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold flex items-center gap-2">
            <Beaker className="h-4 w-4" />
            Ordens de Manipulação
          </h3>
          <p className="text-xs text-muted-foreground">
            Gere OMs em lote para variações que compartilham a mesma base (ex: 4 fragrâncias de body splash).
          </p>
        </div>
        <Button
          size="sm"
          onClick={() => setCriando(!criando)}
          variant={criando ? "outline" : "default"}
          data-testid="btn-nova-om"
        >
          <Plus className="h-3.5 w-3.5 mr-1" />
          Nova OM
        </Button>
      </div>

      {criando && (
        <Card className="border-blue-200 bg-blue-50/40" data-testid="om-form">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm">Criar nova Ordem de Manipulação</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Fórmula base */}
            <div>
              <Label className="text-xs">Fórmula base (sem fragrância)</Label>
              <select
                value={formulaBaseId}
                onChange={(e) => setFormulaBaseId(e.target.value)}
                className="w-full mt-1 border border-input rounded-md px-2 py-1.5 text-sm bg-background"
                data-testid="om-formula-select"
              >
                <option value="">Selecione...</option>
                {formulas.map((f) => (
                  <option key={f.id} value={f.id}>
                    v{f.version} — {f.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Variações */}
            <div>
              <Label className="text-xs">Variações que compartilham a base</Label>
              <div className="mt-1 space-y-1.5 max-h-40 overflow-y-auto border border-input rounded-md p-2 bg-background">
                {variacoes.length === 0 ? (
                  <p className="text-xs text-muted-foreground">Nenhuma variação disponível.</p>
                ) : (
                  variacoes.map((v) => (
                    <label
                      key={v.id}
                      className="flex items-center gap-2 text-sm cursor-pointer hover:bg-slate-50 rounded px-1.5 py-1"
                      data-testid={`om-variacao-check-${v.id}`}
                    >
                      <input
                        type="checkbox"
                        checked={selectedVariacoes.includes(v.id)}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setSelectedVariacoes((p) => [...p, v.id]);
                          } else {
                            setSelectedVariacoes((p) => p.filter((x) => x !== v.id));
                          }
                        }}
                      />
                      <span className="font-mono text-xs font-medium">{v.numero_completo || v.codigo}</span>
                      <span className="text-slate-600 flex-1">{v.descricao_aplicacao || v.referencia_fragrancia || "—"}</span>
                      {v.percentual_fragrancia != null && (
                        <span className="text-purple-600 text-xs font-mono">
                          {v.percentual_fragrancia}% frag
                        </span>
                      )}
                    </label>
                  ))
                )}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Volume por amostra (mL)</Label>
                <Input
                  type="number"
                  min="1"
                  step="1"
                  value={volumeAmostra}
                  onChange={(e) => setVolumeAmostra(e.target.value)}
                  className="mt-1 h-8 text-sm"
                  data-testid="om-volume-input"
                />
              </div>
              <div>
                <Label className="text-xs">Fator de perda (%)</Label>
                <Input
                  type="number"
                  min="0"
                  max="50"
                  step="1"
                  value={fatorPerda}
                  onChange={(e) => setFatorPerda(e.target.value)}
                  className="mt-1 h-8 text-sm"
                  data-testid="om-perda-input"
                />
              </div>
            </div>

            <div>
              <Label className="text-xs">Observações (opcional)</Label>
              <Textarea
                value={observacoes}
                onChange={(e) => setObservacoes(e.target.value)}
                rows={2}
                className="mt-1 text-sm"
                placeholder="Notas para o formulador..."
                data-testid="om-observacoes"
              />
            </div>

            <div className="flex items-center gap-2 pt-1">
              <Button
                size="sm"
                onClick={handleCriar}
                disabled={saving || selectedVariacoes.length === 0 || !formulaBaseId}
                data-testid="btn-confirmar-om"
              >
                {saving ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> : <Plus className="h-3.5 w-3.5 mr-1" />}
                Gerar OM ({selectedVariacoes.length} variações)
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setCriando(false)}>
                Cancelar
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Lista de OMs */}
      <div className="space-y-2">
        {loading && <p className="text-xs text-muted-foreground">Carregando…</p>}
        {!loading && ordens.length === 0 && !criando && (
          <Card>
            <CardContent className="pt-6 text-center">
              <Beaker className="h-8 w-8 mx-auto text-muted-foreground/40 mb-2" />
              <p className="text-sm text-muted-foreground">Nenhuma OM gerada para esta amostra.</p>
              <p className="text-xs text-muted-foreground mt-1">
                Clique em "+ Nova OM" para criar a primeira ordem.
              </p>
            </CardContent>
          </Card>
        )}
        {ordens.map((om) => (
          <Card key={om.id} data-testid={`om-card-${om.id}`}>
            <CardContent className="pt-4 pb-3">
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold font-mono">{om.numero_om}</span>
                    <Badge variant="outline" className={`text-xs ${STATUS_COLORS[om.status] || ""}`}>
                      {om.status}
                    </Badge>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {om.n_variacoes} variações · {om.volume_amostra_ml}mL · perda {om.fator_perda_pct}% ·
                    base total: <b>{om.volume_total_base_ml} mL</b>
                  </p>
                </div>
                <div className="flex items-center gap-1">
                  {om.status === "rascunho" && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleStatusChange(om.id, "emitida")}
                      data-testid={`om-emitir-${om.id}`}
                    >
                      Emitir
                    </Button>
                  )}
                  {om.status === "emitida" && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleStatusChange(om.id, "executada")}
                      data-testid={`om-executar-${om.id}`}
                    >
                      Marcar como executada
                    </Button>
                  )}
                  <a
                    href={pdfUrl(om.id)}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-xs px-2 py-1 border border-input rounded-md hover:bg-accent"
                    data-testid={`om-pdf-${om.id}`}
                  >
                    <Download className="h-3 w-3" />
                    PDF
                  </a>
                  {om.status !== "executada" && (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => handleDelete(om.id, om.numero_om)}
                      data-testid={`om-delete-${om.id}`}
                    >
                      <Trash2 className="h-3.5 w-3.5 text-destructive" />
                    </Button>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
