import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter
} from "@/components/ui/dialog";
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from "@/components/ui/select";
import {
    Table, TableBody, TableCell, TableHead, TableHeader, TableRow
} from "@/components/ui/table";
import { Search, PackageCheck, Plus, Building2 } from "lucide-react";
import { toast } from "sonner";

const STATUS_COLORS = {
    ativo: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300",
    suspenso: "bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300",
    descontinuado: "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300",
};

export default function SKUsPage() {
    const [skus, setSkus] = useState([]);
    const [loading, setLoading] = useState(true);
    const [search, setSearch] = useState("");
    const [filterStatus, setFilterStatus] = useState("");
    const [selectedSku, setSelectedSku] = useState(null);
    const [showAddOrder, setShowAddOrder] = useState(false);
    const [newOrder, setNewOrder] = useState({ data_pedido: "", quantidade: 0, valor_total: 0, observacao: "" });
    const [tab, setTab] = useState("info");

    const loadSkus = useCallback(async () => {
        try {
            const params = {};
            if (search) params.search = search;
            if (filterStatus && filterStatus !== "all") params.status = filterStatus;
            const { data } = await api.get("/crm/skus", { params });
            setSkus(data);
        } catch (e) {
            console.error("Failed to load SKUs", e);
        } finally {
            setLoading(false);
        }
    }, [search, filterStatus]);

    useEffect(() => { loadSkus(); }, [loadSkus]);

    const handleUpdateSku = async (skuId, updates) => {
        try {
            const resp = await api.put(`/crm/skus/${skuId}`, updates);
            toast.success("SKU atualizado!");
            setSelectedSku(resp.data);
            loadSkus();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Erro ao atualizar");
        }
    };

    const handleAddOrder = async () => {
        if (!selectedSku || !newOrder.data_pedido || !newOrder.quantidade) return;
        try {
            const resp = await api.post(`/crm/skus/${selectedSku.id}/orders`, newOrder);
            toast.success("Pedido registrado!");
            setSelectedSku(resp.data);
            setShowAddOrder(false);
            setNewOrder({ data_pedido: "", quantidade: 0, valor_total: 0, observacao: "" });
            loadSkus();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Erro");
        }
    };

    if (loading) return (
        <div className="p-8 page-enter">
            <div className="animate-pulse space-y-4">
                <div className="h-8 w-48 bg-muted rounded" />
                <div className="h-96 bg-muted rounded-lg" />
            </div>
        </div>
    );

    return (
        <div className="p-6 page-enter" data-testid="skus-page">
            <div className="flex items-center justify-between mb-6">
                <div>
                    <h1 className="text-3xl font-heading font-semibold tracking-tight">SKUs</h1>
                    <p className="text-sm text-muted-foreground mt-1">{skus.length} SKU(s) cadastrado(s)</p>
                </div>
                <div className="flex items-center gap-3">
                    <Select value={filterStatus} onValueChange={setFilterStatus}>
                        <SelectTrigger className="w-36"><SelectValue placeholder="Status" /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="all">Todos</SelectItem>
                            <SelectItem value="ativo">Ativo</SelectItem>
                            <SelectItem value="suspenso">Suspenso</SelectItem>
                            <SelectItem value="descontinuado">Descontinuado</SelectItem>
                        </SelectContent>
                    </Select>
                    <div className="relative">
                        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                        <Input placeholder="Buscar SKU..." value={search} onChange={(e) => setSearch(e.target.value)} className="pl-9 w-64" />
                    </div>
                </div>
            </div>

            {skus.length === 0 ? (
                <div className="text-center py-20">
                    <PackageCheck className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
                    <p className="text-muted-foreground">Nenhum SKU encontrado.</p>
                    <p className="text-sm text-muted-foreground mt-1">SKUs são gerados automaticamente ao aprovar amostras no CRM 3.</p>
                </div>
            ) : (
                <div className="border rounded-lg">
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead className="font-heading">Código</TableHead>
                                <TableHead className="font-heading">Produto</TableHead>
                                <TableHead className="font-heading">Cliente</TableHead>
                                <TableHead className="font-heading">Categoria</TableHead>
                                <TableHead className="font-heading">Status</TableHead>
                                <TableHead className="font-heading text-right">Preço Unit.</TableHead>
                                <TableHead className="font-heading text-right">MOQ</TableHead>
                                <TableHead className="font-heading text-right">Pedidos</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {skus.map(sku => (
                                <TableRow key={sku.id} className="cursor-pointer hover:bg-accent/50" onClick={() => { setSelectedSku(sku); setTab("info"); }}>
                                    <TableCell className="font-medium mono-num">{sku.codigo_interno}</TableCell>
                                    <TableCell>{sku.nome_produto}</TableCell>
                                    <TableCell className="text-muted-foreground">{sku.cliente_nome}</TableCell>
                                    <TableCell>{sku.categoria || "—"}</TableCell>
                                    <TableCell>
                                        <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-[0.08em] ${STATUS_COLORS[sku.status] || ""}`}>
                                            {sku.status}
                                        </span>
                                    </TableCell>
                                    <TableCell className="text-right mono-num">{sku.preco_unitario ? `R$ ${sku.preco_unitario.toFixed(2)}` : "—"}</TableCell>
                                    <TableCell className="text-right mono-num">{sku.moq || "—"}</TableCell>
                                    <TableCell className="text-right mono-num">{(sku.historico_pedidos || []).length}</TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                </div>
            )}

            {/* SKU Detail Sheet */}
            <Sheet open={!!selectedSku} onOpenChange={(v) => { if (!v) { setSelectedSku(null); loadSkus(); } }}>
                <SheetContent className="w-[500px] sm:w-[550px] p-0 flex flex-col" side="right">
                    {selectedSku && (
                        <>
                            <SheetHeader className="p-6 pb-3">
                                <SheetTitle className="font-heading text-xl flex items-center gap-2">
                                    <PackageCheck className="h-5 w-5" />
                                    {selectedSku.codigo_interno}
                                </SheetTitle>
                                <p className="text-sm text-muted-foreground">{selectedSku.nome_produto}</p>
                                <div className="flex items-center gap-2 mt-1">
                                    <Badge variant="outline" className="text-xs">{selectedSku.cliente_nome}</Badge>
                                    <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-semibold uppercase ${STATUS_COLORS[selectedSku.status] || ""}`}>
                                        {selectedSku.status}
                                    </span>
                                </div>
                            </SheetHeader>
                            <Separator />
                            <Tabs value={tab} onValueChange={setTab} className="flex-1 flex flex-col min-h-0">
                                <TabsList className="mx-6 mt-3">
                                    <TabsTrigger value="info">Dados</TabsTrigger>
                                    <TabsTrigger value="orders">Pedidos ({(selectedSku.historico_pedidos || []).length})</TabsTrigger>
                                </TabsList>

                                <TabsContent value="info" className="flex-1 min-h-0 overflow-y-auto px-6 pb-6 mt-3">
                                    <div className="space-y-4">
                                        <div className="grid grid-cols-2 gap-3">
                                            <div className="space-y-1">
                                                <Label className="text-xs">Preço Unitário (R$)</Label>
                                                <Input type="number" step="0.01" defaultValue={selectedSku.preco_unitario || 0}
                                                    onBlur={(e) => handleUpdateSku(selectedSku.id, { preco_unitario: parseFloat(e.target.value) || 0 })} />
                                            </div>
                                            <div className="space-y-1">
                                                <Label className="text-xs">MOQ</Label>
                                                <Input type="number" defaultValue={selectedSku.moq || 0}
                                                    onBlur={(e) => handleUpdateSku(selectedSku.id, { moq: parseInt(e.target.value) || 0 })} />
                                            </div>
                                        </div>
                                        <div className="space-y-1">
                                            <Label className="text-xs">Status</Label>
                                            <Select defaultValue={selectedSku.status} onValueChange={(v) => handleUpdateSku(selectedSku.id, { status: v })}>
                                                <SelectTrigger><SelectValue /></SelectTrigger>
                                                <SelectContent>
                                                    <SelectItem value="ativo">Ativo</SelectItem>
                                                    <SelectItem value="suspenso">Suspenso</SelectItem>
                                                    <SelectItem value="descontinuado">Descontinuado</SelectItem>
                                                </SelectContent>
                                            </Select>
                                        </div>
                                        <Separator />
                                        <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">ANVISA</h4>
                                        <div className="grid grid-cols-2 gap-3">
                                            <div className="space-y-1">
                                                <Label className="text-xs">Número</Label>
                                                <Input defaultValue={selectedSku.anvisa?.numero || ""}
                                                    onBlur={(e) => handleUpdateSku(selectedSku.id, { anvisa_numero: e.target.value })} />
                                            </div>
                                            <div className="space-y-1">
                                                <Label className="text-xs">Validade</Label>
                                                <Input type="date" defaultValue={selectedSku.anvisa?.validade ? selectedSku.anvisa.validade.split("T")[0] : ""}
                                                    onBlur={(e) => handleUpdateSku(selectedSku.id, { anvisa_validade: e.target.value ? e.target.value + "T00:00:00+00:00" : null })} />
                                            </div>
                                        </div>
                                        <Separator />
                                        <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Métricas</h4>
                                        <div className="grid grid-cols-2 gap-4">
                                            <div className="bg-muted/50 rounded-lg p-3">
                                                <p className="text-xs text-muted-foreground">Último Pedido</p>
                                                <p className="font-medium mono-num text-sm">
                                                    {selectedSku.data_ultimo_pedido ? new Date(selectedSku.data_ultimo_pedido).toLocaleDateString("pt-BR") : "—"}
                                                </p>
                                            </div>
                                            <div className="bg-muted/50 rounded-lg p-3">
                                                <p className="text-xs text-muted-foreground">Freq. Recompra</p>
                                                <p className="font-medium mono-num text-sm">
                                                    {selectedSku.frequencia_media_recompra_dias ? `${selectedSku.frequencia_media_recompra_dias} dias` : "—"}
                                                </p>
                                            </div>
                                        </div>
                                    </div>
                                </TabsContent>

                                <TabsContent value="orders" className="flex-1 min-h-0 overflow-y-auto px-6 pb-6 mt-3">
                                    <div className="space-y-3">
                                        <Button size="sm" onClick={() => { setNewOrder({ data_pedido: "", quantidade: 0, valor_total: 0, observacao: "" }); setShowAddOrder(true); }}>
                                            <Plus className="h-3.5 w-3.5 mr-1" /> Registrar Pedido
                                        </Button>
                                        {(selectedSku.historico_pedidos || []).slice().reverse().map((order, idx) => (
                                            <div key={idx} className="border border-border rounded-lg p-3">
                                                <div className="flex justify-between items-start">
                                                    <div>
                                                        <p className="text-sm font-medium">Qtd: <span className="mono-num">{order.quantidade}</span></p>
                                                        <p className="text-xs text-muted-foreground mono-num">R$ {order.valor_total?.toFixed(2)}</p>
                                                    </div>
                                                    <span className="text-xs text-muted-foreground mono-num">
                                                        {order.data_pedido ? new Date(order.data_pedido).toLocaleDateString("pt-BR") : "—"}
                                                    </span>
                                                </div>
                                                {order.observacao && <p className="text-xs text-muted-foreground mt-1">{order.observacao}</p>}
                                            </div>
                                        ))}
                                        {(selectedSku.historico_pedidos || []).length === 0 && (
                                            <p className="text-sm text-muted-foreground">Nenhum pedido registrado.</p>
                                        )}
                                    </div>
                                </TabsContent>
                            </Tabs>
                        </>
                    )}
                </SheetContent>
            </Sheet>

            {/* Add Order Dialog */}
            <Dialog open={showAddOrder} onOpenChange={setShowAddOrder}>
                <DialogContent className="max-w-md">
                    <DialogHeader>
                        <DialogTitle className="font-heading">Registrar Pedido</DialogTitle>
                    </DialogHeader>
                    <div className="space-y-3">
                        <div className="space-y-1">
                            <Label>Data do Pedido *</Label>
                            <Input type="date" value={newOrder.data_pedido}
                                onChange={(e) => setNewOrder({ ...newOrder, data_pedido: e.target.value ? e.target.value + "T00:00:00+00:00" : "" })} />
                        </div>
                        <div className="grid grid-cols-2 gap-3">
                            <div className="space-y-1">
                                <Label>Quantidade *</Label>
                                <Input type="number" value={newOrder.quantidade}
                                    onChange={(e) => setNewOrder({ ...newOrder, quantidade: parseInt(e.target.value) || 0 })} />
                            </div>
                            <div className="space-y-1">
                                <Label>Valor Total (R$)</Label>
                                <Input type="number" step="0.01" value={newOrder.valor_total}
                                    onChange={(e) => setNewOrder({ ...newOrder, valor_total: parseFloat(e.target.value) || 0 })} />
                            </div>
                        </div>
                        <div className="space-y-1">
                            <Label>Observação</Label>
                            <Input value={newOrder.observacao}
                                onChange={(e) => setNewOrder({ ...newOrder, observacao: e.target.value })} />
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setShowAddOrder(false)}>Cancelar</Button>
                        <Button onClick={handleAddOrder} disabled={!newOrder.data_pedido || !newOrder.quantidade}>Registrar</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
