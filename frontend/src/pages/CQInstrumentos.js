import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Plus, Loader2, Wrench } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

const STATUS_COLORS = {
    calibrado: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
    vencido: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
    em_calibracao: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
    bloqueado: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
};

const STATUS_LABELS = {
    calibrado: "Calibrado",
    vencido: "Vencido",
    em_calibracao: "Em Calibração",
    bloqueado: "Bloqueado",
};

const TIPO_LABELS = {
    phmetro: "pHmetro",
    balanca: "Balança",
    torquimetro: "Torquímetro",
    densimetro: "Densímetro",
    termohigrometro: "Termohigrômetro",
};

const EMPTY_INSTR = {
    nome: "",
    codigo_interno: "",
    tipo: "",
    localizacao: "",
    frequencia_calibracao_dias: "365",
    ultima_calibracao: "",
    certificado_file_id: "",
};

function todayStr() {
    return new Date().toISOString().split("T")[0];
}

export default function CQInstrumentos() {
    const { user } = useAuth();
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showModal, setShowModal] = useState(false);
    const [form, setForm] = useState(EMPTY_INSTR);
    const [saving, setSaving] = useState(false);
    const [showCalibrar, setShowCalibrar] = useState(false);
    const [calibrarId, setCalibrarId] = useState(null);
    const [calibrarForm, setCalibrarForm] = useState({
        data_calibracao: todayStr(),
        laboratorio: "",
        certificado_numero: "",
        resultado: "aprovado",
        certificado_file_id: "",
    });
    const [calibrarSaving, setCalibrarSaving] = useState(false);

    const load = useCallback(async () => {
        setLoading(true);
        try {
            const { data } = await api.get("/cq/instrumentos");
            setItems(Array.isArray(data) ? data : (data?.items ?? data?.data ?? []));
        } catch (e) {
            toast.error("Erro ao carregar instrumentos");
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { load(); }, [load]);

    const handleCreate = async () => {
        if (!form.nome.trim() || !form.tipo) {
            toast.error("Nome e tipo são obrigatórios");
            return;
        }
        setSaving(true);
        try {
            const payload = {
                ...form,
                frequencia_calibracao_dias: form.frequencia_calibracao_dias ? parseInt(form.frequencia_calibracao_dias, 10) : 365,
                certificado_file_id: form.certificado_file_id || null,
            };
            await api.post("/cq/instrumentos", payload);
            toast.success("Instrumento cadastrado!");
            setShowModal(false);
            setForm(EMPTY_INSTR);
            load();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Erro ao criar instrumento");
        } finally {
            setSaving(false);
        }
    };

    const openCalibrar = (instr) => {
        setCalibrarId(instr.id);
        setCalibrarForm({
            data_calibracao: todayStr(),
            laboratorio: "",
            certificado_numero: "",
            resultado: "aprovado",
            certificado_file_id: "",
        });
        setShowCalibrar(true);
    };

    const handleCalibrar = async () => {
        if (!calibrarId) return;
        setCalibrarSaving(true);
        try {
            await api.post(`/cq/instrumentos/${calibrarId}/registrar-calibracao`, {
                ...calibrarForm,
                certificado_file_id: calibrarForm.certificado_file_id || null,
            });
            toast.success("Calibração registrada!");
            setShowCalibrar(false);
            setCalibrarId(null);
            load();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Erro ao registrar calibração");
        } finally {
            setCalibrarSaving(false);
        }
    };

    return (
        <div className="p-6 page-enter" data-testid="cq-instrumentos">
            <div className="flex items-center justify-between mb-6">
                <div>
                    <h1 className="text-3xl font-heading font-semibold tracking-tight">Instrumentos de Medição</h1>
                    <p className="text-sm text-muted-foreground mt-1">Gestão de calibração e rastreabilidade</p>
                </div>
                <Button onClick={() => { setForm(EMPTY_INSTR); setShowModal(true); }} data-testid="btn-novo-instrumento">
                    <Plus className="h-4 w-4 mr-2" /> Novo Instrumento
                </Button>
            </div>

            {/* Table */}
            {loading ? (
                <div className="flex items-center justify-center h-48">
                    <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
            ) : (
                <div className="rounded-lg border border-border overflow-hidden" data-testid="table-instrumentos">
                    <table className="w-full text-sm">
                        <thead className="bg-muted/50">
                            <tr>
                                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Nome</th>
                                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Código</th>
                                <th className="text-left px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">Tipo</th>
                                <th className="text-left px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">Localização</th>
                                <th className="text-left px-4 py-3 font-medium text-muted-foreground hidden lg:table-cell">Últ. Calibração</th>
                                <th className="text-left px-4 py-3 font-medium text-muted-foreground hidden lg:table-cell">Próx. Calibração</th>
                                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Status</th>
                                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Ações</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-border">
                            {items.length === 0 ? (
                                <tr>
                                    <td colSpan={8} className="text-center py-10 text-muted-foreground">
                                        Nenhum instrumento cadastrado.
                                    </td>
                                </tr>
                            ) : items.map((instr) => (
                                <tr key={instr.id} className="hover:bg-accent/20 transition-colors" data-testid={`row-instr-${instr.id}`}>
                                    <td className="px-4 py-3 font-medium">{instr.nome}</td>
                                    <td className="px-4 py-3 font-mono text-xs">{instr.codigo_interno || "—"}</td>
                                    <td className="px-4 py-3 text-xs hidden md:table-cell">{TIPO_LABELS[instr.tipo] || instr.tipo || "—"}</td>
                                    <td className="px-4 py-3 text-xs hidden md:table-cell">{instr.localizacao || "—"}</td>
                                    <td className="px-4 py-3 text-xs hidden lg:table-cell mono-num">
                                        {instr.ultima_calibracao ? new Date(instr.ultima_calibracao).toLocaleDateString("pt-BR") : "—"}
                                    </td>
                                    <td className="px-4 py-3 text-xs hidden lg:table-cell mono-num">
                                        {instr.proxima_calibracao ? new Date(instr.proxima_calibracao).toLocaleDateString("pt-BR") : "—"}
                                    </td>
                                    <td className="px-4 py-3">
                                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${STATUS_COLORS[instr.status] || "bg-gray-100 text-gray-700"}`}>
                                            {STATUS_LABELS[instr.status] || instr.status || "—"}
                                        </span>
                                    </td>
                                    <td className="px-4 py-3">
                                        <Button
                                            variant="outline"
                                            size="sm"
                                            onClick={() => openCalibrar(instr)}
                                            data-testid={`btn-calibrar-${instr.id}`}
                                        >
                                            <Wrench className="h-3.5 w-3.5 mr-1" /> Calibrar
                                        </Button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            {/* Create Modal */}
            <Dialog open={showModal} onOpenChange={setShowModal}>
                <DialogContent className="max-w-md max-h-[85vh] flex flex-col p-0 overflow-hidden" data-testid="modal-novo-instrumento">
                    <DialogHeader className="p-6 pb-2">
                        <DialogTitle className="font-heading">Novo Instrumento</DialogTitle>
                    </DialogHeader>
                    <div className="flex-1 min-h-0 overflow-y-auto px-6 pb-2">
                        <div className="space-y-4">
                            <div className="space-y-2">
                                <Label>Nome *</Label>
                                <Input value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} placeholder="Nome do instrumento" />
                            </div>
                            <div className="grid grid-cols-2 gap-3">
                                <div className="space-y-2">
                                    <Label>Código Interno</Label>
                                    <Input value={form.codigo_interno} onChange={(e) => setForm({ ...form, codigo_interno: e.target.value })} placeholder="EQ-001" />
                                </div>
                                <div className="space-y-2">
                                    <Label>Tipo *</Label>
                                    <Select value={form.tipo} onValueChange={(v) => setForm({ ...form, tipo: v })}>
                                        <SelectTrigger><SelectValue placeholder="Selecionar" /></SelectTrigger>
                                        <SelectContent>
                                            <SelectItem value="phmetro">pHmetro</SelectItem>
                                            <SelectItem value="balanca">Balança</SelectItem>
                                            <SelectItem value="torquimetro">Torquímetro</SelectItem>
                                            <SelectItem value="densimetro">Densímetro</SelectItem>
                                            <SelectItem value="termohigrometro">Termohigrômetro</SelectItem>
                                        </SelectContent>
                                    </Select>
                                </div>
                            </div>
                            <div className="space-y-2">
                                <Label>Localização</Label>
                                <Input value={form.localizacao} onChange={(e) => setForm({ ...form, localizacao: e.target.value })} placeholder="Ex: Lab CQ - Bancada 3" />
                            </div>
                            <div className="grid grid-cols-2 gap-3">
                                <div className="space-y-2">
                                    <Label>Freq. Calibração (dias)</Label>
                                    <Input
                                        type="number"
                                        value={form.frequencia_calibracao_dias}
                                        onChange={(e) => setForm({ ...form, frequencia_calibracao_dias: e.target.value })}
                                    />
                                </div>
                                <div className="space-y-2">
                                    <Label>Última Calibração</Label>
                                    <Input
                                        type="date"
                                        value={form.ultima_calibracao}
                                        onChange={(e) => setForm({ ...form, ultima_calibracao: e.target.value })}
                                    />
                                </div>
                            </div>
                            <div className="space-y-2">
                                <Label>ID do Certificado (opcional)</Label>
                                <Input
                                    value={form.certificado_file_id}
                                    onChange={(e) => setForm({ ...form, certificado_file_id: e.target.value })}
                                    placeholder="ID do arquivo anexo"
                                />
                            </div>
                        </div>
                    </div>
                    <DialogFooter className="p-6 pt-3 border-t">
                        <Button variant="outline" onClick={() => setShowModal(false)}>Cancelar</Button>
                        <Button onClick={handleCreate} disabled={saving}>
                            {saving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                            Cadastrar
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            {/* Calibrar Modal */}
            <Dialog open={showCalibrar} onOpenChange={setShowCalibrar}>
                <DialogContent className="max-w-md" data-testid="modal-calibrar">
                    <DialogHeader>
                        <DialogTitle className="font-heading">Registrar Calibração</DialogTitle>
                    </DialogHeader>
                    <div className="space-y-4">
                        <div className="grid grid-cols-2 gap-3">
                            <div className="space-y-2">
                                <Label>Data da Calibração *</Label>
                                <Input
                                    type="date"
                                    value={calibrarForm.data_calibracao}
                                    onChange={(e) => setCalibrarForm({ ...calibrarForm, data_calibracao: e.target.value })}
                                />
                            </div>
                            <div className="space-y-2">
                                <Label>Laboratório</Label>
                                <Input
                                    value={calibrarForm.laboratorio}
                                    onChange={(e) => setCalibrarForm({ ...calibrarForm, laboratorio: e.target.value })}
                                    placeholder="Nome do lab."
                                />
                            </div>
                        </div>
                        <div className="space-y-2">
                            <Label>Nº do Certificado</Label>
                            <Input
                                value={calibrarForm.certificado_numero}
                                onChange={(e) => setCalibrarForm({ ...calibrarForm, certificado_numero: e.target.value })}
                                placeholder="CAL-2025-001"
                            />
                        </div>
                        <div className="space-y-2">
                            <Label>Resultado *</Label>
                            <div className="flex flex-col gap-2" data-testid="select-resultado-calibracao">
                                <label className="flex items-center gap-2 cursor-pointer">
                                    <input
                                        type="radio"
                                        name="calibResult"
                                        value="aprovado"
                                        checked={calibrarForm.resultado === "aprovado"}
                                        onChange={() => setCalibrarForm({ ...calibrarForm, resultado: "aprovado" })}
                                    />
                                    <span className="text-sm">Aprovado</span>
                                </label>
                                <label className="flex items-center gap-2 cursor-pointer">
                                    <input
                                        type="radio"
                                        name="calibResult"
                                        value="reprovado"
                                        checked={calibrarForm.resultado === "reprovado"}
                                        onChange={() => setCalibrarForm({ ...calibrarForm, resultado: "reprovado" })}
                                    />
                                    <span className="text-sm">Reprovado</span>
                                </label>
                            </div>
                        </div>
                        <div className="space-y-2">
                            <Label>ID do Certificado (opcional)</Label>
                            <Input
                                value={calibrarForm.certificado_file_id}
                                onChange={(e) => setCalibrarForm({ ...calibrarForm, certificado_file_id: e.target.value })}
                                placeholder="ID do arquivo"
                            />
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setShowCalibrar(false)}>Cancelar</Button>
                        <Button onClick={handleCalibrar} disabled={calibrarSaving}>
                            {calibrarSaving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                            <Wrench className="h-4 w-4 mr-2" /> Registrar
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
