import React, { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { ClipboardList, Search, Loader2, FileText, ArrowRight, Building2, Calendar, DollarSign } from "lucide-react";

const STATUS_CONFIG = {
  rascunho: { label: "Rascunho", color: "bg-slate-500/10 text-slate-600 border-slate-300 dark:text-slate-300" },
  confirmado: { label: "Confirmado", color: "bg-blue-500/10 text-blue-600 border-blue-300 dark:text-blue-300" },
  em_producao: { label: "Em Produção", color: "bg-amber-500/10 text-amber-700 border-amber-300 dark:text-amber-300" },
  concluido: { label: "Concluído", color: "bg-green-500/10 text-green-700 border-green-300 dark:text-green-300" },
  cancelado: { label: "Cancelado", color: "bg-red-500/10 text-red-700 border-red-300 dark:text-red-300" },
};

function formatCurrencyBR(value) {
  if (!value && value !== 0) return "R$ 0,00";
  return `R$ ${Number(value).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatDateBR(iso) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleDateString("pt-BR"); } catch { return iso; }
}

export default function OrdersPage() {
  const navigate = useNavigate();
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  const fetchOrders = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (statusFilter !== "all") params.status = statusFilter;
      if (search.trim()) params.q = search.trim();
      const res = await api.get("/orders", { params });
      setOrders(res.data || []);
    } catch (err) {
      toast.error("Erro ao carregar pedidos");
    } finally {
      setLoading(false);
    }
  }, [statusFilter, search]);

  useEffect(() => { fetchOrders(); }, [fetchOrders]);

  const counts = {
    total: orders.length,
    rascunho: orders.filter(o => o.status === "rascunho").length,
    confirmado: orders.filter(o => o.status === "confirmado").length,
    em_producao: orders.filter(o => o.status === "em_producao").length,
    concluido: orders.filter(o => o.status === "concluido").length,
    valor_total: orders.reduce((s, o) => s + (o.total_pedido || 0), 0),
  };

  return (
    <div className="h-full overflow-auto">
      <div className="max-w-7xl mx-auto p-6 space-y-5">
        {/* Header */}
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-2xl font-heading font-semibold tracking-tight flex items-center gap-2">
              <ClipboardList className="h-6 w-6" />
              Pedidos
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              Ordens de produção criadas a partir de projetos P&D aprovados
            </p>
          </div>
        </div>

        {/* Mini stats */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <StatCard label="Total" value={counts.total} icon={ClipboardList} color="text-slate-600 dark:text-slate-300" />
          <StatCard label="Rascunho" value={counts.rascunho} color="text-slate-500" />
          <StatCard label="Confirmado" value={counts.confirmado} color="text-blue-600" />
          <StatCard label="Em Produção" value={counts.em_producao} color="text-amber-600" />
          <StatCard label="Valor Total" value={formatCurrencyBR(counts.valor_total)} color="text-green-600" icon={DollarSign} isText />
        </div>

        {/* Filters */}
        <div className="flex gap-2 items-center flex-wrap">
          <div className="relative flex-1 min-w-[240px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Buscar por nº, cliente, projeto..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9"
              data-testid="orders-search-input"
            />
          </div>
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-44" data-testid="orders-status-filter">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todos os Status</SelectItem>
              <SelectItem value="rascunho">Rascunho</SelectItem>
              <SelectItem value="confirmado">Confirmado</SelectItem>
              <SelectItem value="em_producao">Em Produção</SelectItem>
              <SelectItem value="concluido">Concluído</SelectItem>
              <SelectItem value="cancelado">Cancelado</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* List */}
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : orders.length === 0 ? (
          <Card className="border-dashed">
            <CardContent className="py-16 text-center">
              <ClipboardList className="h-14 w-14 mx-auto mb-4 text-muted-foreground/30" />
              <h3 className="text-lg font-semibold mb-1">Nenhum pedido ainda</h3>
              <p className="text-sm text-muted-foreground max-w-md mx-auto">
                Quando um projeto P&D for aprovado pelo cliente (status APROVADO), uma Ordem de Produção será criada automaticamente aqui.
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-2">
            {orders.map(order => {
              const cfg = STATUS_CONFIG[order.status] || STATUS_CONFIG.rascunho;
              return (
                <Card
                  key={order.id}
                  className="hover:border-primary/40 hover:shadow-sm transition-all cursor-pointer group"
                  onClick={() => navigate(`/orders/${order.id}`)}
                  data-testid={`order-card-${order.id}`}
                >
                  <CardContent className="p-4">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                          <span className="font-mono text-sm font-bold text-primary">#{order.numero_pedido}</span>
                          <Badge className={`${cfg.color} text-[10px]`}>{cfg.label}</Badge>
                          {order.auto_created && (
                            <Badge variant="outline" className="text-[10px] gap-1">
                              <FileText className="h-2.5 w-2.5" />
                              Auto-gerado
                            </Badge>
                          )}
                        </div>
                        <h3 className="font-semibold text-base truncate">
                          {order.project_name || order.cliente?.nome || "Pedido sem nome"}
                        </h3>
                        <div className="flex items-center gap-4 mt-1.5 text-xs text-muted-foreground flex-wrap">
                          <span className="flex items-center gap-1">
                            <Building2 className="h-3 w-3" />
                            {order.cliente?.razao_social || order.cliente?.nome || "—"}
                          </span>
                          <span className="flex items-center gap-1">
                            <Calendar className="h-3 w-3" />
                            {formatDateBR(order.data_pedido)}
                          </span>
                          <span>{(order.items || []).length} item(ns)</span>
                        </div>
                      </div>
                      <div className="text-right shrink-0">
                        <div className="text-xs text-muted-foreground">Total</div>
                        <div className="text-lg font-bold text-green-600">
                          {formatCurrencyBR(order.total_pedido)}
                        </div>
                        <ArrowRight className="h-4 w-4 ml-auto mt-1 text-muted-foreground group-hover:text-primary transition-colors" />
                      </div>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({ label, value, icon: Icon, color, isText }) {
  return (
    <Card>
      <CardContent className="p-3">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-[11px] text-muted-foreground uppercase tracking-wider">{label}</div>
            <div className={`font-bold mt-0.5 ${color || ""} ${isText ? "text-base" : "text-2xl"}`}>{value}</div>
          </div>
          {Icon && <Icon className={`h-5 w-5 ${color || "text-muted-foreground"} opacity-60`} />}
        </div>
      </CardContent>
    </Card>
  );
}
