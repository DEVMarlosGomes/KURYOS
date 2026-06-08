import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import api from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Users, Target, ListTodo, DollarSign, Loader2, FlaskConical,
  ArrowRight, AlertTriangle, Clock3, CalendarDays, Building2,
  ShoppingCart, Microscope, Package, CheckCircle2, Clock, FileText,
  Beaker, ShieldCheck, BarChart3, ChevronRight, TrendingUp, Hourglass,
  Activity,
} from "lucide-react";
import { toast } from "sonner";

function StatTile({ label, value, sub, Icon, color, accent, onClick }) {
  const cls = `rounded-xl border px-4 py-3 flex items-center gap-3 ${accent || "bg-card"} ${onClick ? "cursor-pointer hover:brightness-95 transition-all" : ""}`;
  return (
    <div className={cls} onClick={onClick}>
      {Icon && <Icon className={`h-5 w-5 shrink-0 ${color || "text-muted-foreground"}`} />}
      <div className="min-w-0">
        <p className="font-mono text-xl font-bold leading-none">{value ?? "—"}</p>
        <p className="text-[11px] text-muted-foreground mt-0.5 truncate">{label}</p>
        {sub !== undefined && <p className="text-[10px] text-muted-foreground">{sub}</p>}
      </div>
    </div>
  );
}

function ModuleSection({ title, Icon, color, children, navPath, navigate }) {
  return (
    <div className="border rounded-xl overflow-hidden">
      <div className="flex items-center justify-between px-5 py-3.5 border-b bg-muted/20">
        <div className="flex items-center gap-2.5">
          <span className={`w-1 h-4 ${color} rounded-full`} />
          {Icon && <Icon className="h-3.5 w-3.5 text-muted-foreground" />}
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{title}</p>
        </div>
        {navPath && (
          <button
            onClick={() => navigate(navPath)}
            className="flex items-center gap-1 text-[10px] text-primary hover:underline font-medium"
          >
            Ver tudo <ChevronRight className="h-3 w-3" />
          </button>
        )}
      </div>
      <div className="px-5 py-4 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        {children}
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [erp, setErp] = useState(null);
  const [myTasks, setMyTasks] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.get("/erp-overview").then(({ data }) => setErp(data)).catch(() => setErp(null)),
      api.get("/workflow/tasks", { params: { mine: true } }).then(({ data }) => setMyTasks(data || [])).catch(() => setMyTasks([])),
    ]).finally(() => setLoading(false));
  }, []);

  const myTaskMetrics = useMemo(() => {
    const now = Date.now();
    const open = myTasks.filter(t => t.status !== "concluida");
    const overdue = open.filter(t => t.due_date && new Date(t.due_date).getTime() < now);
    const week = open.filter(t => {
      if (!t.due_date) return false;
      const diff = new Date(t.due_date).getTime() - now;
      return diff >= 0 && diff <= 7 * 24 * 3600 * 1000;
    });
    return { open, overdue, week };
  }, [myTasks]);

  if (loading) {
    return (
      <div className="p-8 page-enter">
        <div className="animate-pulse space-y-6">
          <div className="h-8 w-48 rounded bg-muted" />
          <div className="grid grid-cols-4 gap-4">
            {[1, 2, 3, 4].map(i => <div key={i} className="h-24 rounded-xl bg-muted" />)}
          </div>
          <div className="grid grid-cols-1 gap-4">
            {[1, 2, 3].map(i => <div key={i} className="h-32 rounded-xl bg-muted" />)}
          </div>
        </div>
      </div>
    );
  }

  const crm = erp?.crm || {};
  const pd = erp?.pd || {};
  const cq = erp?.cq || {};
  const compras = erp?.compras || {};
  const pedidos = erp?.pedidos || {};
  const tasks = erp?.tasks || {};

  const totalAlerts = (cq.rncs_abertas || 0) + (tasks.atrasadas || 0) + (cq.retencoes_ativas || 0);

  return (
    <div className="p-6 page-enter max-w-7xl mx-auto space-y-6">

      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-heading font-semibold tracking-tight">Dashboard ERP</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Visão consolidada de todos os módulos · {user?.name}
          </p>
        </div>
        {totalAlerts > 0 && (
          <Badge className="bg-red-500/15 text-red-600 border-red-200 dark:border-red-900 gap-1.5 text-xs px-3 py-1.5">
            <AlertTriangle className="h-3.5 w-3.5" />
            {totalAlerts} alerta{totalAlerts !== 1 ? "s" : ""} ativo{totalAlerts !== 1 ? "s" : ""}
          </Badge>
        )}
      </div>

      {/* Top KPI strip */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <StatTile label="Clientes Ativos" value={crm.clientes_ativos} Icon={Users} color="text-blue-500" accent="bg-blue-500/5 border-blue-200 dark:border-blue-900" onClick={() => navigate("/crm/clients")} />
        <StatTile label="Projetos Ativos" value={crm.projetos_ativos} Icon={Target} color="text-indigo-500" accent="bg-indigo-500/5 border-indigo-200 dark:border-indigo-900" onClick={() => navigate("/crm/projects")} />
        <StatTile label="P&D em Andamento" value={(pd.in_progress || 0) + (pd.in_tests || 0)} Icon={FlaskConical} color="text-violet-500" accent="bg-violet-500/5 border-violet-200 dark:border-violet-900" onClick={() => navigate("/pd")} />
        <StatTile label="Amostras Ativas" value={crm.amostras_andamento} Icon={Beaker} color="text-amber-500" accent="bg-amber-500/5 border-amber-200 dark:border-amber-900" onClick={() => navigate("/crm/samples")} />
        <StatTile label="Pedidos em Aberto" value={pedidos.abertos} Icon={ShoppingCart} color="text-emerald-600" accent="bg-emerald-500/5 border-emerald-200 dark:border-emerald-900" onClick={() => navigate("/orders")} />
        <StatTile label="Tarefas Pendentes" value={tasks.pendentes} sub={tasks.atrasadas > 0 ? `${tasks.atrasadas} atrasada(s)` : undefined} Icon={ListTodo} color={tasks.atrasadas > 0 ? "text-red-500" : "text-muted-foreground"} accent={tasks.atrasadas > 0 ? "bg-red-500/5 border-red-200 dark:border-red-900" : undefined} onClick={() => navigate("/tasks")} />
      </div>

      {/* My task queue */}
      <div className="border rounded-xl overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3.5 border-b bg-muted/20">
          <div className="flex items-center gap-2.5">
            <span className="w-1 h-4 bg-primary rounded-full" />
            <Activity className="h-3.5 w-3.5 text-muted-foreground" />
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Fila Pessoal</p>
          </div>
          <button onClick={() => navigate("/tasks")} className="flex items-center gap-1 text-[10px] text-primary hover:underline font-medium">
            Todas as tarefas <ChevronRight className="h-3 w-3" />
          </button>
        </div>
        <div className="px-5 py-4">
          <div className="grid grid-cols-3 gap-3 mb-4">
            <div className="rounded-lg border px-4 py-3 text-center">
              <p className="text-2xl font-bold mono-num">{myTaskMetrics.open.length}</p>
              <p className="text-[11px] text-muted-foreground mt-0.5">Em aberto</p>
            </div>
            <div className={`rounded-lg border px-4 py-3 text-center ${myTaskMetrics.overdue.length > 0 ? "border-red-200 bg-red-500/5 dark:border-red-900" : ""}`}>
              <p className={`text-2xl font-bold mono-num ${myTaskMetrics.overdue.length > 0 ? "text-red-500" : ""}`}>{myTaskMetrics.overdue.length}</p>
              <p className="text-[11px] text-muted-foreground mt-0.5">Atrasadas</p>
            </div>
            <div className="rounded-lg border px-4 py-3 text-center">
              <p className="text-2xl font-bold mono-num">{myTaskMetrics.week.length}</p>
              <p className="text-[11px] text-muted-foreground mt-0.5">Esta semana</p>
            </div>
          </div>
          {myTaskMetrics.open.length === 0 ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground py-2">
              <CheckCircle2 className="h-4 w-4 text-green-500" /> Nenhuma tarefa pendente para você no momento.
            </div>
          ) : (
            <div className="space-y-1.5">
              {myTaskMetrics.open.slice(0, 4).map(task => (
                <button key={task.id} onClick={() => navigate("/tasks")} className="w-full rounded-lg border px-3.5 py-2.5 text-left hover:bg-accent transition-colors flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate">{task.title}</p>
                    <p className="text-[10px] text-muted-foreground">{task.responsible_name || "—"} · {task.entity_type}</p>
                  </div>
                  <Badge variant={task.blocking ? "destructive" : "outline"} className="shrink-0 text-[10px]">
                    {task.due_date ? new Date(task.due_date).toLocaleDateString("pt-BR") : "Sem prazo"}
                  </Badge>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* CRM */}
      <ModuleSection title="CRM Comercial" Icon={Building2} color="bg-blue-500" navPath="/crm/clients" navigate={navigate}>
        <StatTile label="Total Clientes" value={crm.total_clientes} Icon={Users} color="text-blue-500" />
        <StatTile label="Clientes Ativos" value={crm.clientes_ativos} Icon={TrendingUp} color="text-green-500" />
        <StatTile label="Total Projetos" value={crm.total_projetos} Icon={FileText} color="text-indigo-500" />
        <StatTile label="Amostras Ativas" value={crm.amostras_andamento} Icon={Beaker} color="text-amber-500" />
      </ModuleSection>

      {/* P&D */}
      <ModuleSection title="Pesquisa & Desenvolvimento" Icon={FlaskConical} color="bg-violet-500" navPath="/pd" navigate={navigate}>
        <StatTile label="Aberto" value={pd.open} Icon={Clock} color="text-blue-500" />
        <StatTile label="Em Desenvolvimento" value={pd.in_progress} Icon={Beaker} color="text-amber-500" />
        <StatTile label="Em Testes" value={pd.in_tests} Icon={FlaskConical} color="text-purple-500" />
        <StatTile label="Aguard. Aprovação" value={pd.waiting_approval} Icon={Hourglass} color="text-orange-500" />
        <StatTile label="Aprovados" value={pd.approved} Icon={CheckCircle2} color="text-green-500" />
        <StatTile label="Concluídos" value={pd.completed} Icon={CheckCircle2} color="text-emerald-600" />
        <StatTile label="Fórmulas" value={pd.formulas} Icon={Beaker} color="text-violet-500" />
      </ModuleSection>

      {/* CQ + Compras + Pedidos row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

        {/* CQ */}
        <div className="border rounded-xl overflow-hidden">
          <div className="flex items-center justify-between px-5 py-3.5 border-b bg-muted/20">
            <div className="flex items-center gap-2.5">
              <span className="w-1 h-4 bg-cyan-500 rounded-full" />
              <Microscope className="h-3.5 w-3.5 text-muted-foreground" />
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Controle de Qualidade</p>
            </div>
            <button onClick={() => navigate("/cq")} className="flex items-center gap-1 text-[10px] text-primary hover:underline font-medium">
              Ver <ChevronRight className="h-3 w-3" />
            </button>
          </div>
          <div className="px-5 py-4 space-y-2.5">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground text-xs">RAs Pendentes</span>
              <span className={`font-semibold mono-num ${cq.ras_pendentes > 0 ? "text-amber-500" : "text-muted-foreground"}`}>{cq.ras_pendentes ?? 0}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground text-xs">RNCs Abertas</span>
              <span className={`font-semibold mono-num ${cq.rncs_abertas > 0 ? "text-red-500" : "text-muted-foreground"}`}>{cq.rncs_abertas ?? 0}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground text-xs">Retenções em Guarda</span>
              <span className="font-semibold mono-num">{cq.retencoes_ativas ?? 0}</span>
            </div>
          </div>
        </div>

        {/* Compras */}
        <div className="border rounded-xl overflow-hidden">
          <div className="flex items-center justify-between px-5 py-3.5 border-b bg-muted/20">
            <div className="flex items-center gap-2.5">
              <span className="w-1 h-4 bg-orange-500 rounded-full" />
              <Package className="h-3.5 w-3.5 text-muted-foreground" />
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Compras</p>
            </div>
            <button onClick={() => navigate("/compras")} className="flex items-center gap-1 text-[10px] text-primary hover:underline font-medium">
              Ver <ChevronRight className="h-3 w-3" />
            </button>
          </div>
          <div className="px-5 py-4 space-y-2.5">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground text-xs">Fornecedores Homologados</span>
              <span className="font-semibold mono-num text-green-600">{compras.fornecedores_homologados ?? 0}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground text-xs">POs em Aberto</span>
              <span className={`font-semibold mono-num ${compras.pos_abertas > 0 ? "text-amber-500" : "text-muted-foreground"}`}>{compras.pos_abertas ?? 0}</span>
            </div>
          </div>
        </div>

        {/* Pedidos */}
        <div className="border rounded-xl overflow-hidden">
          <div className="flex items-center justify-between px-5 py-3.5 border-b bg-muted/20">
            <div className="flex items-center gap-2.5">
              <span className="w-1 h-4 bg-emerald-500 rounded-full" />
              <ShoppingCart className="h-3.5 w-3.5 text-muted-foreground" />
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Pedidos</p>
            </div>
            <button onClick={() => navigate("/orders")} className="flex items-center gap-1 text-[10px] text-primary hover:underline font-medium">
              Ver <ChevronRight className="h-3 w-3" />
            </button>
          </div>
          <div className="px-5 py-4 space-y-2.5">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground text-xs">Em Aberto</span>
              <span className={`font-semibold mono-num ${pedidos.abertos > 0 ? "text-amber-500" : "text-muted-foreground"}`}>{pedidos.abertos ?? 0}</span>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}
