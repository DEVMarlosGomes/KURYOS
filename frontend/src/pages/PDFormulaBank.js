import { useCallback, useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import PDSubNav from "@/components/PDSubNav";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Search, FlaskConical, ShieldCheck, BookOpen, Building2, Lock, CheckCircle2, AlertTriangle } from "lucide-react";
import { toast } from "sonner";

function ApprovalBadge({ ok, label }) {
  return (
    <Badge variant={ok ? "default" : "outline"} className={ok ? "bg-green-600 hover:bg-green-600" : ""}>
      {label}: {ok ? "OK" : "Pendente"}
    </Badge>
  );
}

export default function PDFormulaBank() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [origin, setOrigin] = useState("all");
  const [registeredOnly, setRegisteredOnly] = useState("all");
  const [selected, setSelected] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (search.trim()) params.q = search.trim();
      if (origin !== "all") params.origem = origin;
      if (registeredOnly === "registered") params.somente_registradas = true;
      const { data } = await api.get("/pd/formulas/bank", { params });
      setItems(Array.isArray(data) ? data : []);
    } catch (err) {
      toast.error("Erro ao carregar banco de formulas");
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [origin, registeredOnly, search]);

  useEffect(() => {
    load();
  }, [load]);

  const stats = useMemo(() => ({
    total: items.length,
    registered: items.filter(item => item.is_registered).length,
    portfolio: items.filter(item => item.origin_type === "portfolio").length,
    client: items.filter(item => item.origin_type === "cliente").length,
  }), [items]);

  const restrictedView = items.some((item) => item.restricted_view);

  return (
    <div className="p-4 sm:p-6 page-enter">
      <PDSubNav active="formulaBank" />

      {restrictedView && (
        <div
          className="mb-4 flex items-start gap-3 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-200"
          data-testid="formula-bank-restricted-banner"
        >
          <Lock className="h-4 w-4 mt-0.5 shrink-0" />
          <div>
            <p className="font-medium">Visao restrita do banco de formulas</p>
            <p className="text-xs mt-0.5">Seu perfil ({restrictedView ? "comercial" : "—"}) ve apenas metadados das formulas — composicao, percentuais e custos sao restritos a P&D, CQ e Engenharia.</p>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between mb-6 gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-heading font-semibold tracking-tight flex items-center gap-2">
            <BookOpen className="h-7 w-7 text-primary" /> Banco de Formulas
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Repositorio versionado das formulas do P&D com origem, aprovacoes e composicao.
          </p>
        </div>
        <Button variant="outline" onClick={load}>Atualizar</Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-5">
        <StatCard icon={BookOpen} title="Formulas" value={stats.total} subtitle="versoes listadas" />
        <StatCard icon={ShieldCheck} title="Registradas" value={stats.registered} subtitle="CQ + cliente aprovados" />
        <StatCard icon={FlaskConical} title="Portfólio" value={stats.portfolio} subtitle="origem interna" />
        <StatCard icon={Building2} title="Cliente" value={stats.client} subtitle="derivadas de briefing" />
      </div>

      <div className="flex gap-3 mb-4 flex-wrap">
        <div className="relative flex-1 min-w-[240px] max-w-lg">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Buscar por formula, projeto, cliente ou ingrediente..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <Select value={origin} onValueChange={setOrigin}>
          <SelectTrigger className="w-48">
            <SelectValue placeholder="Origem" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todas as origens</SelectItem>
            <SelectItem value="cliente">Projetos de cliente</SelectItem>
            <SelectItem value="portfolio">Portfólio Kuryos</SelectItem>
          </SelectContent>
        </Select>
        <Select value={registeredOnly} onValueChange={setRegisteredOnly}>
          <SelectTrigger className="w-52">
            <SelectValue placeholder="Registro" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todas as formulas</SelectItem>
            <SelectItem value="registered">Somente registradas</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-muted/50 border-b">
                  <th className="text-left p-3 font-semibold">Formula</th>
                  <th className="text-left p-3 font-semibold">Projeto</th>
                  <th className="text-left p-3 font-semibold">Origem</th>
                  <th className="text-left p-3 font-semibold">Formulador</th>
                  <th className="text-left p-3 font-semibold">Aprovacoes</th>
                  <th className="text-right p-3 font-semibold">Itens</th>
                  <th className="text-right p-3 font-semibold text-purple-700">% Fragr.</th>
                  <th className="text-right p-3 font-semibold text-purple-500">Target</th>
                  <th className="text-right p-3 font-semibold">Custo/kg</th>
                  <th className="w-28"></th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={9} className="p-6 text-center text-muted-foreground">Carregando...</td>
                  </tr>
                ) : items.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="p-6 text-center text-muted-foreground">Nenhuma formula encontrada.</td>
                  </tr>
                ) : items.map((item) => (
                  <tr key={item.id} className="border-b hover:bg-muted/20">
                    <td className="p-3">
                      <div className="font-medium">{item.name}</div>
                      <div className="text-[11px] text-muted-foreground">
                        v{item.version} • {item.volume || 0} {item.volume_unit || "mL"}
                      </div>
                    </td>
                    <td className="p-3">
                      <div>{item.project_name || "Sem projeto"}</div>
                      <div className="text-[11px] text-muted-foreground">{item.request_status || "—"}</div>
                    </td>
                    <td className="p-3">
                      <Badge variant="outline">{item.origin_label}</Badge>
                    </td>
                    <td className="p-3">
                      <div>{item.created_by_name || "—"}</div>
                      <div className="text-[11px] text-muted-foreground">
                        {item.created_at ? new Date(item.created_at).toLocaleDateString("pt-BR") : "—"}
                      </div>
                    </td>
                    <td className="p-3">
                      <div className="flex gap-1.5 flex-wrap">
                        <ApprovalBadge ok={item.approved_by_internal} label="CQ" />
                        <ApprovalBadge ok={item.approved_by_client} label="Cliente" />
                      </div>
                    </td>
                    <td className="p-3 text-right font-mono">
                      {item.item_count}
                      <div className="text-[10px] text-muted-foreground">{(item.total_percentage || 0).toFixed(3)}%</div>
                    </td>
                    <td className="p-3 text-right font-mono">
                      {item.fragrance_percentage != null ? (
                        <span className={`font-semibold ${item.fragrance_percentage > 0 ? "text-purple-700" : "text-muted-foreground"}`}>
                          {item.fragrance_percentage > 0 ? `${item.fragrance_percentage.toFixed(2)}%` : "—"}
                        </span>
                      ) : <span className="text-muted-foreground text-xs">restrito</span>}
                    </td>
                    <td className="p-3 text-right font-mono">
                      {item.fragrance_target != null ? (() => {
                        const actual = item.fragrance_percentage;
                        const target = item.fragrance_target;
                        const onTarget = actual != null && Math.abs(actual - target) <= 0.5;
                        return (
                          <span className={`inline-flex items-center gap-1 font-semibold ${onTarget ? "text-green-600" : "text-amber-600"}`}>
                            {onTarget
                              ? <CheckCircle2 className="h-3.5 w-3.5" />
                              : <AlertTriangle className="h-3.5 w-3.5" />}
                            {target.toFixed(2)}%
                          </span>
                        );
                      })() : <span className="text-muted-foreground text-xs">—</span>}
                    </td>
                    <td className="p-3 text-right font-mono">R$ {(item.total_cost_per_kg || 0).toFixed(2)}</td>
                    <td className="p-3 text-right">
                      <Button size="sm" variant="outline" onClick={() => setSelected(item)}>Ver</Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <Sheet open={!!selected} onOpenChange={(open) => !open && setSelected(null)}>
        <SheetContent side="right" className="w-[720px] sm:w-[760px] overflow-y-auto">
          {selected && (
            <>
              <SheetHeader>
                <SheetTitle className="flex items-center gap-2">
                  <BookOpen className="h-5 w-5" />
                  {selected.name} • v{selected.version}
                </SheetTitle>
              </SheetHeader>

              <div className="mt-6 space-y-5">
                <div className="grid grid-cols-2 gap-3">
                  <MetaCard label="Projeto" value={selected.project_name || "—"} />
                  <MetaCard label="Origem" value={selected.origin_label || "—"} />
                  <MetaCard label="Formulador" value={selected.created_by_name || "—"} />
                  <MetaCard label="Data" value={selected.created_at ? new Date(selected.created_at).toLocaleString("pt-BR") : "—"} />
                  <MetaCard label="Custo total / kg" value={`R$ ${(selected.total_cost_per_kg || 0).toFixed(2)}`} />
                  <MetaCard label="Itens / % total" value={`${selected.item_count} / ${(selected.total_percentage || 0).toFixed(3)}%`} />
                  <MetaCard label="% Fragrância (real)" value={selected.fragrance_percentage != null ? `${selected.fragrance_percentage.toFixed(2)}%` : "—"} />
                  <MetaCard label="% Fragrância (target)" value={selected.fragrance_target != null ? `${selected.fragrance_target.toFixed(2)}%` : "Sem target"} />
                </div>

                <Card>
                  <CardContent className="p-4 space-y-2">
                    <div className="flex items-center gap-2 flex-wrap">
                      <ApprovalBadge ok={selected.approved_by_internal} label="Aprovacao CQ" />
                      <ApprovalBadge ok={selected.approved_by_client} label="Aprovacao cliente" />
                      {selected.is_registered && (
                        <Badge className="bg-emerald-600 hover:bg-emerald-600">Formula registrada</Badge>
                      )}
                    </div>
                    {selected.notes ? (
                      <p className="text-sm whitespace-pre-wrap">{selected.notes}</p>
                    ) : (
                      <p className="text-sm text-muted-foreground italic">Sem observacoes registradas.</p>
                    )}
                  </CardContent>
                </Card>

                <Card>
                  <CardContent className="p-0">
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="bg-muted/50 border-b">
                            <th className="text-left p-3 font-semibold">Ingrediente</th>
                            <th className="text-left p-3 font-semibold">Fase</th>
                            <th className="text-left p-3 font-semibold">Funcao</th>
                            <th className="text-right p-3 font-semibold">% </th>
                            <th className="text-right p-3 font-semibold">R$/kg</th>
                            <th className="text-right p-3 font-semibold">Custo</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(selected.items || []).map((row) => (
                            <tr key={row.id} className="border-b">
                              <td className="p-3 font-medium">{row.ingredient_name}</td>
                              <td className="p-3">{row.phase || "—"}</td>
                              <td className="p-3">{row.function || "—"}</td>
                              <td className="p-3 text-right font-mono">{(row.percentage || 0).toFixed(3)}</td>
                              <td className="p-3 text-right font-mono">{(row.price_per_kg || 0).toFixed(2)}</td>
                              <td className="p-3 text-right font-mono">{(row.cost_brl || 0).toFixed(4)}</td>
                            </tr>
                          ))}
                          {(selected.items || []).length === 0 && (
                            <tr>
                              <td colSpan={6} className="p-6 text-center text-muted-foreground">Sem composicao cadastrada.</td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </CardContent>
                </Card>
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}

function StatCard({ icon: Icon, title, value, subtitle }) {
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
            <p className="text-xs text-muted-foreground">{subtitle}</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function MetaCard({ label, value }) {
  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-xs text-muted-foreground mb-1">{label}</p>
        <p className="text-sm font-medium">{value}</p>
      </CardContent>
    </Card>
  );
}
