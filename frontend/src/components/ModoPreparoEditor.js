/**
 * Item 8 — Editor de Modo de Preparo estruturado (fase a fase).
 * Salva via PUT /api/pd/formulas/{id} com campo modo_preparo (lista de objetos).
 */
import React, { useState, useEffect, useMemo } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Plus, Trash2, Save, AlertTriangle } from "lucide-react";
import { toast } from "sonner";

const FASES = ["", "A", "B", "C", "Fragrância", "Ativo", "Conservante", "Final"];

export default function ModoPreparoEditor({ formula, canEdit = true, onSaved }) {
  const initialPassos = useMemo(() => {
    const raw = formula?.modo_preparo || [];
    return raw.map((p, i) =>
      typeof p === "string"
        ? {
            ordem: i + 1,
            descricao: p,
            fase: "",
            temperatura_c: null,
            tempo_minutos: null,
            equipamento: "",
            rpm: null,
            alerta: "",
          }
        : { ...p, ordem: p.ordem ?? i + 1 }
    );
  }, [formula?.id, formula?.modo_preparo]);

  const [passos, setPassos] = useState(initialPassos);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setPassos(initialPassos);
    setDirty(false);
  }, [initialPassos]);

  const addPasso = () => {
    setPassos((prev) => [
      ...prev,
      {
        ordem: prev.length + 1,
        descricao: "",
        fase: "",
        temperatura_c: null,
        tempo_minutos: null,
        equipamento: "",
        rpm: null,
        alerta: "",
      },
    ]);
    setDirty(true);
  };

  const updatePasso = (idx, field, value) => {
    setPassos((prev) =>
      prev.map((p, i) => (i === idx ? { ...p, [field]: value } : p))
    );
    setDirty(true);
  };

  const removePasso = (idx) => {
    setPassos((prev) =>
      prev.filter((_, i) => i !== idx).map((p, i) => ({ ...p, ordem: i + 1 }))
    );
    setDirty(true);
  };

  const handleSave = async () => {
    if (!formula?.id) return;
    setSaving(true);
    try {
      await api.put(`/pd/formulas/${formula.id}`, { modo_preparo: passos });
      toast.success("Modo de preparo salvo");
      setDirty(false);
      onSaved?.();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Erro ao salvar modo de preparo");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-3" data-testid="modo-preparo-editor">
      <div className="flex items-center justify-between">
        <div>
          <h4 className="text-sm font-semibold">Modo de Preparo</h4>
          <p className="text-xs text-muted-foreground">
            Passos numerados em ordem de execução. Inclua fase, temperatura, equipamento e alertas.
          </p>
        </div>
        {canEdit && (
          <div className="flex items-center gap-2">
            {dirty && (
              <Button
                size="sm"
                onClick={handleSave}
                disabled={saving}
                data-testid="btn-salvar-modo-preparo"
              >
                <Save className="h-3.5 w-3.5 mr-1" />
                Salvar
              </Button>
            )}
            <Button
              size="sm"
              variant="outline"
              onClick={addPasso}
              data-testid="btn-add-passo"
            >
              <Plus className="h-3.5 w-3.5 mr-1" />
              Passo
            </Button>
          </div>
        )}
      </div>

      {passos.length === 0 && (
        <p className="text-xs text-muted-foreground italic border border-dashed border-input rounded-md p-3 text-center">
          Nenhum passo registrado. Clique em "+ Passo" para adicionar.
        </p>
      )}

      <div className="space-y-2">
        {passos.map((passo, idx) => (
          <div
            key={idx}
            className="border border-input rounded-lg p-3 bg-muted/30"
            data-testid={`passo-${idx + 1}`}
          >
            <div className="flex items-center gap-2 mb-2 flex-wrap">
              <span className="text-xs font-semibold w-7 shrink-0 text-muted-foreground">
                {passo.ordem}.
              </span>
              <select
                value={passo.fase || ""}
                onChange={(e) => updatePasso(idx, "fase", e.target.value)}
                disabled={!canEdit}
                className="text-xs border border-input rounded px-2 py-1 bg-background h-7"
                data-testid={`passo-fase-${idx}`}
              >
                {FASES.map((f) => (
                  <option key={f} value={f}>
                    {f ? `Fase ${f}` : "Sem fase"}
                  </option>
                ))}
              </select>
              <Input
                type="number"
                step="1"
                placeholder="°C"
                value={passo.temperatura_c ?? ""}
                onChange={(e) =>
                  updatePasso(
                    idx,
                    "temperatura_c",
                    e.target.value ? Number(e.target.value) : null
                  )
                }
                disabled={!canEdit}
                className="w-16 h-7 text-xs"
                data-testid={`passo-temp-${idx}`}
              />
              <Input
                type="number"
                step="0.5"
                placeholder="min"
                value={passo.tempo_minutos ?? ""}
                onChange={(e) =>
                  updatePasso(
                    idx,
                    "tempo_minutos",
                    e.target.value ? Number(e.target.value) : null
                  )
                }
                disabled={!canEdit}
                className="w-16 h-7 text-xs"
                data-testid={`passo-tempo-${idx}`}
              />
              <Input
                type="number"
                step="100"
                placeholder="rpm"
                value={passo.rpm ?? ""}
                onChange={(e) =>
                  updatePasso(idx, "rpm", e.target.value ? Number(e.target.value) : null)
                }
                disabled={!canEdit}
                className="w-20 h-7 text-xs"
                data-testid={`passo-rpm-${idx}`}
              />
              <Input
                placeholder="Equipamento (agitador, banho-maria…)"
                value={passo.equipamento || ""}
                onChange={(e) => updatePasso(idx, "equipamento", e.target.value)}
                disabled={!canEdit}
                className="flex-1 min-w-[140px] h-7 text-xs"
                data-testid={`passo-equip-${idx}`}
              />
              {canEdit && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 w-7 p-0"
                  onClick={() => removePasso(idx)}
                  data-testid={`btn-remove-passo-${idx}`}
                >
                  <Trash2 className="h-3.5 w-3.5 text-destructive" />
                </Button>
              )}
            </div>
            <Textarea
              value={passo.descricao || ""}
              onChange={(e) => updatePasso(idx, "descricao", e.target.value)}
              disabled={!canEdit}
              placeholder="Descreva este passo…"
              rows={2}
              className="text-sm"
              data-testid={`passo-descricao-${idx}`}
            />
            <div className="mt-1 flex items-center gap-1">
              <AlertTriangle className="h-3 w-3 text-amber-500 shrink-0" />
              <Input
                value={passo.alerta || ""}
                onChange={(e) => updatePasso(idx, "alerta", e.target.value)}
                disabled={!canEdit}
                placeholder="Alerta / cuidado (opcional)"
                className="h-7 text-xs border-amber-200 bg-amber-50/40 placeholder:text-amber-700/40"
                data-testid={`passo-alerta-${idx}`}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
