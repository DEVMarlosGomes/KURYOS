/**
 * Item 6 — Botão de retrocesso de PD Card com justificativa obrigatória.
 * Líder P&D / admin retrocedem direto; demais perfis abrem solicitação pendente.
 */
import React, { useState } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { ArrowLeftCircle } from "lucide-react";
import { toast } from "sonner";

const STATUS_LABELS = {
  solicitado: "Solicitado",
  em_desenvolvimento: "Em Desenvolvimento",
  em_testes: "Em Testes",
  aguardando_aprovacao: "Aguardando Aprovação CQ",
  aprovado_internamente: "Aprovado Internamente",
  entregue_ao_comercial: "Entregue ao Comercial",
  retrabalho_interno: "Retrabalho Interno",
};

export default function RetrocederPDCardButton({ cardId, statusAtual, onSuccess }) {
  const [open, setOpen] = useState(false);
  const [statusDestino, setStatusDestino] = useState("");
  const [justificativa, setJustificativa] = useState("");
  const [saving, setSaving] = useState(false);

  // Lista de status possíveis como destino de retrocesso (todos exceto o atual)
  const destinos = Object.keys(STATUS_LABELS).filter((s) => s !== statusAtual);

  const handleSubmit = async () => {
    if (!statusDestino) return toast.error("Selecione o status de destino");
    if (!justificativa || justificativa.trim().length < 10) {
      return toast.error("Justificativa deve ter no mínimo 10 caracteres");
    }
    setSaving(true);
    try {
      const { data } = await api.post(`/pd/cards/${cardId}/retroceder`, {
        status_destino: statusDestino,
        justificativa: justificativa.trim(),
      });
      if (data.status === "retrocedido") {
        toast.success(`Card retrocedido para ${STATUS_LABELS[data.novo_status] || data.novo_status}`);
      } else if (data.status === "aguardando_aprovacao") {
        toast.success("Solicitação de retrocesso criada — aguardando Líder P&D");
      }
      setOpen(false);
      setStatusDestino("");
      setJustificativa("");
      onSuccess?.();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Erro ao solicitar retrocesso");
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <Button
        size="sm"
        variant="outline"
        onClick={() => setOpen(true)}
        data-testid="btn-retroceder-card"
        className="gap-1.5"
      >
        <ArrowLeftCircle className="h-3.5 w-3.5" />
        Retroceder etapa
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-md" data-testid="dialog-retroceder">
          <DialogHeader>
            <DialogTitle>Retroceder card</DialogTitle>
            <DialogDescription>
              Status atual: <b>{STATUS_LABELS[statusAtual] || statusAtual}</b>. Líder P&D pode
              executar imediatamente — outros perfis criam uma solicitação pendente.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3 py-2">
            <div>
              <Label className="text-xs">Status de destino</Label>
              <select
                value={statusDestino}
                onChange={(e) => setStatusDestino(e.target.value)}
                className="w-full mt-1 border border-input rounded-md px-2 py-1.5 text-sm bg-background"
                data-testid="select-status-destino"
              >
                <option value="">Selecione…</option>
                {destinos.map((s) => (
                  <option key={s} value={s}>
                    {STATUS_LABELS[s]}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <Label className="text-xs">
                Justificativa (mínimo 10 caracteres) <span className="text-destructive">*</span>
              </Label>
              <Textarea
                value={justificativa}
                onChange={(e) => setJustificativa(e.target.value)}
                rows={3}
                placeholder="Descreva por que está retrocedendo este card…"
                className="mt-1"
                data-testid="input-justificativa"
              />
              <p className="text-[10px] text-muted-foreground mt-1">
                {justificativa.length}/10 caracteres mínimos
              </p>
            </div>
          </div>

          <DialogFooter>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancelar
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={saving || justificativa.trim().length < 10 || !statusDestino}
              data-testid="btn-confirmar-retrocesso"
            >
              {saving ? "Enviando…" : "Confirmar retrocesso"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
