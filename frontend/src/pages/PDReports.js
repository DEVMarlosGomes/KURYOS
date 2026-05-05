import { useCallback, useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import PDSubNav from "@/components/PDSubNav";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { BarChart3, Clock3, CheckCircle2, ShieldCheck, FlaskConical, KanbanSquare } from "lucide-react";
import { toast } from "sonner";

const STATUS_LABELS = {
  OPEN: "Aberto",
  IN_PROGRESS: "Em Desenvolvimento",
  IN_TESTS: "Em Testes",
  WAITING_APPROVAL: "Aguardando Aprovação",
  APPROVED: "Aprovado",
  COMPLETED: "Concluído",
  REJECTED: "Rejeitado",
};

export default function PDReports() {
  const [metrics, setMetrics] = useState(null);
  const [requests, setRequests] = useState([]);
  const [homologation, setHomologation] = useState(null);
  const [formulaBank, setFormulaBank] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [metricsRes, requestsRes, homologationRes, formulasRes] = await Promise.all([
        api.get("/pd/metrics"),
        api.get("/pd/requests"),
        api.get("/pd/homologacao/dashboard"),
        api.get("/pd/formulas/bank", { params: { somente_registradas: true } }),
      ]);
      setMetrics(metricsRes.data || null);
      setRequests(Array.isArray(requestsRes.data) ? requestsRes.data : []);
      setHomologation(homologationRes.data || null);
      setFormulaBank(Array.isArray(formulasRes.data) ? formulasRes.data : []);
    } catch (err) {
      toast.error("Erro ao carregar relatórios de P&D");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const computed = useMemo(() => {
    const completedLike = requests.filter(req => ["APPROVED", "COMPLETED"].includes(req.status));
    const avgLeadTime = completedLike.length > 0
      ? completedLike.reduce((sum, req) => {
          const start = req.created_at ? new Date(req.created_at).getTime() : 0;
          const end = req.updated_at ? new Date(req.updated_at).getTime() : start;
          if (!start || !end || end < start) return sum;
          return sum + ((end - start) / (1000 * 60 * 60 * 24));
        }, 0) / completedLike.length
      : 0;

    const total = requests.length || 0;
    const approved = requests.filter(req => ["APPROVED", "COMPLETED"].includes(req.status)).length;
    const rejected = requests.filter(req => req.status === "REJECTED").length;
    const internal = requests.filter(req => req.is_internal_research).length;

    return {
      total,
      approvedRate: total > 0 ? (approved / total) * 100 : 0,
      rejectionRate: total > 0 ? (rejected / total) * 100 : 0,
      avgLeadTime,
      internal,
      clientDriven: Math.max(total - internal, 0),
    };
  }, [requests]);

  return (
    <div className="p-6 page-enter">
      <PDSubNav active="reports" />

      <div className="flex items-center justify-between mb-6 gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-heading font-semibold tracking-tight flex items-center gap-2">
            <BarChart3 className="h-7 w-7 text-primary" /> Relatórios P&D
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Visão consolidada de capacidade, tempo de desenvolvimento, aprovações e homologações.
          </p>
        </div>
        <Button variant="outline" onClick={load}>Atualizar</Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3 mb-6">
        <MetricCard icon={KanbanSquare} title="Demandas" value={computed.total} subtitle="solicitações registradas" loading={loading} />
        <MetricCard icon={CheckCircle2} title="Taxa de aprovação" value={`${computed.approvedRate.toFixed(1)}%`} subtitle="aprovado ou concluído" loading={loading} />
        <MetricCard icon={Clock3} title="Lead time médio" value={`${computed.avgLeadTime.toFixed(1)} d`} subtitle="até aprovação/conclusão" loading={loading} />
        <MetricCard icon={ShieldCheck} title="Fórmulas registradas" value={formulaBank.length} subtitle="CQ + cliente aprovados" loading={loading} />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Fila por etapa</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {loading ? (
              <p className="text-sm text-muted-foreground">Carregando métricas...</p>
            ) : (
              Object.entries(metrics?.by_status || {}).map(([status, count]) => (
                <div key={status} className="flex items-center gap-3">
                  <div className="w-44 shrink-0">
                    <p className="text-sm font-medium">{STATUS_LABELS[status] || status}</p>
                  </div>
                  <div className="flex-1 h-3 rounded-full bg-muted overflow-hidden">
                    <div
                      className="h-full bg-primary rounded-full"
                      style={{ width: `${Math.max(((count || 0) / Math.max(metrics?.total || 1, 1)) * 100, count ? 8 : 0)}%` }}
                    />
                  </div>
                  <Badge variant="outline" className="w-14 justify-center">{count || 0}</Badge>
                </div>
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Mix de origem</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <MiniStat label="Projetos de cliente" value={computed.clientDriven} />
            <MiniStat label="Pesquisa interna" value={computed.internal} />
            <MiniStat label="Taxa de rejeição" value={`${computed.rejectionRate.toFixed(1)}%`} />
            <MiniStat label="Pendentes de aprovação" value={(metrics?.by_status?.WAITING_APPROVAL || 0) + (metrics?.by_status?.IN_TESTS || 0)} />
          </CardContent>
        </Card>

        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Prioridades em aberto</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {Object.entries(metrics?.by_priority || {}).map(([priority, count]) => (
              <div key={priority} className="rounded-lg border p-4">
                <p className="text-xs uppercase tracking-wide text-muted-foreground">{priority}</p>
                <p className="text-2xl font-semibold mono-num mt-1">{count || 0}</p>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Homologações</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <MiniStat label="Fornecedores homologados" value={homologation?.fornecedores?.por_status?.homologado || 0} />
            <MiniStat label="Fornecedores pendentes" value={homologation?.fornecedores?.por_status?.pendente || 0} />
            <MiniStat label="MPs homologadas" value={homologation?.mps?.por_status?.homologada || 0} />
            <MiniStat label="MPs pendentes" value={homologation?.mps?.por_status?.pendente || 0} />
          </CardContent>
        </Card>

        <Card className="xl:col-span-3">
          <CardHeader>
            <CardTitle>Últimas fórmulas registradas</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-muted/50 border-b">
                    <th className="text-left p-3 font-semibold">Fórmula</th>
                    <th className="text-left p-3 font-semibold">Projeto</th>
                    <th className="text-left p-3 font-semibold">Origem</th>
                    <th className="text-left p-3 font-semibold">Formulador</th>
                    <th className="text-right p-3 font-semibold">Itens</th>
                    <th className="text-right p-3 font-semibold">Custo/kg</th>
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr>
                      <td colSpan={6} className="p-6 text-center text-muted-foreground">Carregando...</td>
                    </tr>
                  ) : formulaBank.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="p-6 text-center text-muted-foreground">Nenhuma fórmula registrada ainda.</td>
                    </tr>
                  ) : formulaBank.slice(0, 8).map((formula) => (
                    <tr key={formula.id} className="border-b">
                      <td className="p-3 font-medium">{formula.name} <span className="text-xs text-muted-foreground">v{formula.version}</span></td>
                      <td className="p-3">{formula.project_name || "—"}</td>
                      <td className="p-3">{formula.origin_label || "—"}</td>
                      <td className="p-3">{formula.created_by_name || "—"}</td>
                      <td className="p-3 text-right font-mono">{formula.item_count || 0}</td>
                      <td className="p-3 text-right font-mono">R$ {(formula.total_cost_per_kg || 0).toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function MetricCard({ icon: Icon, title, value, subtitle, loading }) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center">
            <Icon className="h-5 w-5 text-primary" />
          </div>
          <div>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">{title}</p>
            <p className="text-2xl font-semibold mono-num">{loading ? "—" : value}</p>
            <p className="text-xs text-muted-foreground">{subtitle}</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function MiniStat({ label, value }) {
  return (
    <div className="rounded-lg border p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-xl font-semibold mono-num mt-1">{value}</p>
    </div>
  );
}
