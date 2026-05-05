import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import api from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from "recharts";
import {
  Users,
  Target,
  ListTodo,
  DollarSign,
  FileSpreadsheet,
  Loader2,
  FlaskConical,
  ArrowRight,
  AlertTriangle,
  Clock3,
  CalendarDays,
} from "lucide-react";
import { toast } from "sonner";

const STATUS_COLORS = { frio: "#0284C7", morno: "#EA580C", quente: "#DC2626" };
const STATUS_LABELS = { frio: "Frio", morno: "Morno", quente: "Quente" };

export default function DashboardPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [metrics, setMetrics] = useState(null);
  const [pdMetrics, setPdMetrics] = useState(null);
  const [myTasks, setMyTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    Promise.all([
      api.get("/dashboard/metrics").then(({ data }) => setMetrics(data)).catch(console.error),
      api.get("/pd/metrics").then(({ data }) => setPdMetrics(data)).catch(() => setPdMetrics(null)),
      api.get("/workflow/tasks", { params: { mine: true } }).then(({ data }) => setMyTasks(data || [])).catch(() => setMyTasks([])),
    ]).finally(() => setLoading(false));
  }, []);

  const exportExcel = async () => {
    setExporting(true);
    try {
      const response = await api.get("/reports/excel", { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement("a");
      link.href = url;
      link.download = `relatorio_kuryos_${new Date().toISOString().slice(0, 10)}.xlsx`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      toast.success("Relatorio exportado com sucesso");
    } catch {
      toast.error("Erro ao exportar relatorio");
    } finally {
      setExporting(false);
    }
  };

  const myTaskMetrics = useMemo(() => {
    const now = Date.now();
    const openTasks = myTasks.filter((task) => task.status !== "concluida");
    const overdue = openTasks.filter((task) => task.due_date && new Date(task.due_date).getTime() < now);
    const week = openTasks.filter((task) => {
      if (!task.due_date) return false;
      const diff = new Date(task.due_date).getTime() - now;
      return diff >= 0 && diff <= 7 * 24 * 3600 * 1000;
    });
    const blocking = openTasks.filter((task) => task.blocking);
    return { openTasks, overdue, week, blocking };
  }, [myTasks]);

  if (loading) {
    return (
      <div className="p-8 page-enter" data-testid="dashboard-loading">
        <div className="animate-pulse space-y-6">
          <div className="h-8 w-48 rounded bg-muted" />
          <div className="grid grid-cols-4 gap-4">
            {[1, 2, 3, 4].map((item) => (
              <div key={item} className="h-28 rounded-lg bg-muted" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (!metrics) return null;

  const statCards = [
    { label: "Total Leads", value: metrics.total_cards, icon: Users, color: "text-foreground" },
    { label: "Leads Quentes", value: metrics.cards_by_status?.quente || 0, icon: Target, color: "text-red-500" },
    { label: "Tarefas Pendentes", value: metrics.pending_tasks, icon: ListTodo, color: "text-orange-500" },
    {
      label: "Receita Total",
      value: `R$ ${(metrics.total_revenue || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2 })}`,
      icon: DollarSign,
      color: "text-green-500",
    },
  ];

  const taskCards = [
    { label: "Minha Fila", value: myTaskMetrics.openTasks.length, icon: ListTodo, color: "text-primary" },
    { label: "Atrasadas", value: myTaskMetrics.overdue.length, icon: AlertTriangle, color: "text-red-500" },
    { label: "Esta Semana", value: myTaskMetrics.week.length, icon: CalendarDays, color: "text-amber-500" },
    { label: "Bloqueantes", value: myTaskMetrics.blocking.length, icon: Clock3, color: "text-fuchsia-500" },
  ];

  const funnelData = [...(metrics.cards_by_stage || [])].sort((a, b) => a.order - b.order);
  const pieData = Object.entries(metrics.cards_by_status || {}).map(([key, value]) => ({
    name: STATUS_LABELS[key],
    value,
    fill: STATUS_COLORS[key],
  }));

  return (
    <div className="p-8 page-enter" data-testid="dashboard-page">
      <div className="flex items-center justify-between mb-8 gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-heading font-semibold tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Painel inicial de {user?.role || "usuario"} com tarefas pendentes em destaque.
          </p>
        </div>
        <Button variant="outline" onClick={exportExcel} disabled={exporting} data-testid="export-excel-btn">
          {exporting ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <FileSpreadsheet className="h-4 w-4 mr-2" />}
          Exportar Excel
        </Button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {statCards.map(({ label, value, icon: Icon, color }) => (
          <Card key={label}>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-body font-medium text-muted-foreground">{label}</CardTitle>
              <Icon className={`h-4 w-4 ${color}`} />
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-heading font-semibold mono-num">{value}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card className="mb-8 border-primary/20">
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle className="text-base font-heading">Fila Pessoal</CardTitle>
            <p className="text-sm text-muted-foreground mt-1">Resumo operacional para acelerar follow-ups e aprovacoes.</p>
          </div>
          <Button variant="outline" size="sm" onClick={() => navigate("/tasks")}>
            Abrir Tarefas
          </Button>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {taskCards.map(({ label, value, icon: Icon, color }) => (
              <div key={label} className="rounded-lg border border-border bg-card p-4">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">{label}</span>
                  <Icon className={`h-4 w-4 ${color}`} />
                </div>
                <p className="text-2xl font-heading font-semibold mono-num mt-3">{value}</p>
              </div>
            ))}
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-medium">Proximas tarefas</h3>
              <Badge variant="outline">{myTaskMetrics.openTasks.length} abertas</Badge>
            </div>
            {myTaskMetrics.openTasks.slice(0, 5).map((task) => (
              <button
                key={task.id}
                onClick={() => navigate("/tasks")}
                className="w-full rounded-lg border border-border px-4 py-3 text-left hover:bg-accent transition-colors"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium">{task.title}</p>
                    <p className="text-xs text-muted-foreground mt-1">
                      {task.responsible_name || "Sem responsavel"} · {task.entity_type}
                    </p>
                  </div>
                  <Badge variant={task.blocking ? "destructive" : "outline"}>
                    {task.due_date ? new Date(task.due_date).toLocaleDateString("pt-BR") : "Sem prazo"}
                  </Badge>
                </div>
              </button>
            ))}
            {myTaskMetrics.openTasks.length === 0 && (
              <p className="text-sm text-muted-foreground">Nenhuma tarefa pendente para voce no momento.</p>
            )}
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2" data-testid="funnel-chart">
          <CardHeader>
            <CardTitle className="text-base font-heading">Funil de Vendas</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={funnelData}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis dataKey="stage" tick={{ fontSize: 11 }} interval={0} angle={-15} textAnchor="end" height={60} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 13 }} />
                <Bar dataKey="count" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} name="Leads" />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card data-testid="status-chart">
          <CardHeader>
            <CardTitle className="text-base font-heading">Temperatura dos Leads</CardTitle>
          </CardHeader>
          <CardContent className="flex items-center justify-center">
            {pieData.every((item) => item.value === 0) ? (
              <p className="text-muted-foreground text-sm py-12">Sem dados ainda</p>
            ) : (
              <ResponsiveContainer width="100%" height={240}>
                <PieChart>
                  <Pie data={pieData} cx="50%" cy="50%" innerRadius={55} outerRadius={85} paddingAngle={3} dataKey="value">
                    {pieData.map((entry, index) => (
                      <Cell key={index} fill={entry.fill} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 13 }} />
                </PieChart>
              </ResponsiveContainer>
            )}
          </CardContent>
          <div className="px-6 pb-4 flex gap-4 justify-center">
            {pieData.map((item) => (
              <div key={item.name} className="flex items-center gap-1.5 text-xs">
                <span className="w-2.5 h-2.5 rounded-full" style={{ background: item.fill }} />
                {item.name}: <span className="font-medium mono-num">{item.value}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {metrics.recent_history?.length > 0 && (
        <Card className="mt-6" data-testid="recent-activity">
          <CardHeader>
            <CardTitle className="text-base font-heading">Atividade Recente</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {metrics.recent_history.map((item, index) => (
                <div key={index} className="flex items-start gap-3 text-sm">
                  <div className="w-2 h-2 rounded-full bg-primary mt-1.5 shrink-0" />
                  <div>
                    <span className="font-medium">{item.action}</span>
                    <span className="text-muted-foreground"> - {item.details}</span>
                    <p className="text-xs text-muted-foreground mt-0.5 mono-num">
                      {new Date(item.created_at).toLocaleString("pt-BR")}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {pdMetrics && pdMetrics.total > 0 && (
        <div className="mt-8">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-heading font-semibold flex items-center gap-2">
              <FlaskConical className="h-5 w-5" />
              P&D - Pesquisa & Desenvolvimento
            </h2>
            <Button variant="outline" size="sm" onClick={() => navigate("/pd")} className="gap-1">
              Ver Pipeline <ArrowRight className="h-3.5 w-3.5" />
            </Button>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3 mb-4">
            {[
              { key: "OPEN", label: "Aberto", color: "bg-blue-500" },
              { key: "IN_PROGRESS", label: "Em Dev", color: "bg-amber-500" },
              { key: "IN_TESTS", label: "Em Testes", color: "bg-purple-500" },
              { key: "WAITING_APPROVAL", label: "Aprovacao", color: "bg-orange-500" },
              { key: "APPROVED", label: "Aprovado", color: "bg-green-500" },
              { key: "COMPLETED", label: "Concluido", color: "bg-emerald-600" },
              { key: "REJECTED", label: "Rejeitado", color: "bg-red-500" },
            ].map(({ key, label, color }) => (
              <Card key={key} className="relative overflow-hidden">
                <CardContent className="p-3 text-center">
                  <div className={`absolute top-0 left-0 right-0 h-1 ${color}`} />
                  <p className="text-xl font-bold mono-num mt-1">{pdMetrics.by_status?.[key] || 0}</p>
                  <p className="text-[11px] text-muted-foreground">{label}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
