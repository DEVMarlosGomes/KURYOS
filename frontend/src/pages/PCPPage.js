import { useState, useEffect, useCallback, useMemo } from "react";
import api from "@/lib/api";
import { formatApiError } from "@/lib/formatError";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
    Calendar, ChevronLeft, ChevronRight, Plus, Loader2, Settings,
    Factory, Play, CheckCircle2, XCircle, Clock, Wrench, Package,
    AlertTriangle, Layers, Coffee,
} from "lucide-react";

// ─── constants ───────────────────────────────────────────────────────────────
const HOURS = ["07:00","08:00","09:00","10:00","11:00","12:00","13:00","14:00","15:00","16:00","17:00"];
const DIAS_KEY = ["seg","ter","qua","qui","sex","sab","dom"];
const DAYS_PT  = ["Dom","Seg","Ter","Qua","Qui","Sex","Sáb"];
const TIPO_LINHA_LABEL = { manipulacao:"Manipulação", embalagem:"Embalagem", rotulagem:"Rotulagem", envase:"Envase", geral:"Geral" };
const TURNO_LABEL = { manha:"Manhã", tarde:"Tarde", noite:"Noite", integral:"Integral" };
const SLOT_STATUSES = ["planejado","em_execucao","concluido","cancelado"];
const LOTE_STATUSES = ["planejado","em_preparo","em_envase","concluido","cancelado"];
const LOTE_NEXT = { planejado:"em_preparo", em_preparo:"em_envase", em_envase:"concluido" };
const LOTE_STATUS_LABEL = { planejado:"Planejado", em_preparo:"Em Preparo", em_envase:"Em Envase", concluido:"Concluído", cancelado:"Cancelado" };
const LOTE_STATUS_CLS = {
    planejado:  "bg-slate-100 text-slate-700",
    em_preparo: "bg-blue-100 text-blue-700",
    em_envase:  "bg-purple-100 text-purple-700",
    concluido:  "bg-green-100 text-green-700",
    cancelado:  "bg-red-100 text-red-700",
};
const SLOT_STATUS_CFG = {
    planejado:   { label:"Planejado",   cls:"bg-slate-100 text-slate-700" },
    em_execucao: { label:"Em Execução", cls:"bg-amber-100 text-amber-700" },
    concluido:   { label:"Concluído",   cls:"bg-green-100 text-green-700" },
    cancelado:   { label:"Cancelado",   cls:"bg-red-100 text-red-700" },
};
const NEXT_SLOT = {
    planejado:   { to:"em_execucao", label:"Iniciar",   Icon:Play },
    em_execucao: { to:"concluido",   label:"Concluir",  Icon:CheckCircle2 },
};
const DEFAULT_DIA = { habilitado:true, hora_inicio:"07:00", hora_fim:"18:00", pausa_almoco:true, almoco_inicio:"12:00", almoco_fim:"13:00" };
const DEFAULT_SAB = { habilitado:false, hora_inicio:"07:00", hora_fim:"12:00", pausa_almoco:false, almoco_inicio:"12:00", almoco_fim:"13:00" };
const TIPOS_SETUP = ["assepsia","troca_volume","troca_maquina","geral"];
const TIPOS_SETUP_LABEL = { assepsia:"Assepsia", troca_volume:"Troca Volume", troca_maquina:"Troca Máquina", geral:"Geral" };

// ─── helpers ─────────────────────────────────────────────────────────────────
function startOfWeek(date) {
    const d = new Date(date);
    const day = d.getDay();
    d.setDate(d.getDate() - (day === 0 ? 6 : day - 1));
    d.setHours(0, 0, 0, 0);
    return d;
}
function addDays(date, n) {
    const d = new Date(date);
    d.setDate(d.getDate() + n);
    return d;
}
function toYMD(date) { return date.toISOString().slice(0, 10); }
function formatDateBR(ymd) {
    if (!ymd) return "—";
    const [, m, d] = ymd.split("-");
    return `${d}/${m}`;
}
function weekKey(date) {
    const d = new Date(date);
    d.setHours(0, 0, 0, 0);
    const day = d.getDay() || 7;
    d.setDate(d.getDate() + 4 - day);
    const year = d.getFullYear();
    const jan1 = new Date(year, 0, 1);
    const week = Math.ceil(((d - jan1) / 86400000 + 1) / 7);
    return `${year}-${String(week).padStart(2, "0")}`;
}
// dayIndex: 0=Mon,...,6=Sun (matching DIAS_KEY order)
function dayIndex(date) { return (date.getDay() + 6) % 7; }

// Client color hash
const CLIENT_COLORS = [
    { bg:"#dbeafe", border:"#93c5fd", text:"#1e40af" },
    { bg:"#ede9fe", border:"#c4b5fd", text:"#5b21b6" },
    { bg:"#dcfce7", border:"#86efac", text:"#166534" },
    { bg:"#fef3c7", border:"#fcd34d", text:"#92400e" },
    { bg:"#fce7f3", border:"#f9a8d4", text:"#9d174d" },
    { bg:"#ccfbf1", border:"#5eead4", text:"#134e4a" },
    { bg:"#ffedd5", border:"#fdba74", text:"#9a3412" },
    { bg:"#e0e7ff", border:"#a5b4fc", text:"#3730a3" },
];
function clientColor(name) {
    if (!name) return CLIENT_COLORS[0];
    let h = 0;
    for (let i = 0; i < name.length; i++) h = name.charCodeAt(i) + ((h << 5) - h);
    return CLIENT_COLORS[Math.abs(h) % CLIENT_COLORS.length];
}

function hourInt(hhmm) { return hhmm ? parseInt(hhmm.split(":")[0], 10) : 0; }

// ─── mini-components ─────────────────────────────────────────────────────────
function SlotBadge({ status }) {
    const cfg = SLOT_STATUS_CFG[status] || SLOT_STATUS_CFG.planejado;
    return <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium ${cfg.cls}`}>{cfg.label}</span>;
}
function LoteBadge({ status }) {
    const cls = LOTE_STATUS_CLS[status] || LOTE_STATUS_CLS.planejado;
    return <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium ${cls}`}>{LOTE_STATUS_LABEL[status] || status}</span>;
}

// ─── main component ───────────────────────────────────────────────────────────
const TABS = ["Programação","OPs Pendentes","Lotes","Calendário","Linhas","Necessidades"];

export default function PCPPage() {
    const [tab, setTab] = useState("Programação");
    const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date()));
    const [compact, setCompact] = useState(true);

    // Data
    const [linhas, setLinhas] = useState([]);
    const [slots, setSlots] = useState([]);
    const [lotes, setLotes] = useState([]);
    const [calendarios, setCalendarios] = useState([]);
    const [opsPendentes, setOpsPendentes] = useState([]);
    const [dashboard, setDashboard] = useState(null);

    // R20 — Necessidades de material (PCP)
    const [necessidades, setNecessidades] = useState([]);
    const [loadingNec, setLoadingNec] = useState(false);

    // Loading
    const [loadingSlots, setLoadingSlots] = useState(true);
    const [loadingOps, setLoadingOps] = useState(false);
    const [loadingLotes, setLoadingLotes] = useState(false);
    const [saving, setSaving] = useState(false);
    const [actionLoading, setActionLoading] = useState(false);

    // Grid cell click → create slot
    const [cellClick, setCellClick] = useState(null); // { linha, ymd, hora }
    const [cellForm, setCellForm] = useState({ op_id:"", lote_id:"", tipo:"producao", hora_fim:"", qtd_planejada:"", setup_tipo:"assepsia", setup_tempo_min:"30", observacoes:"" });
    const [cellOps, setCellOps] = useState([]);
    const [cellLotes, setCellLotes] = useState([]);

    // Slot detail
    const [selectedSlot, setSelectedSlot] = useState(null);
    const [slotLote, setSlotLote] = useState(null);
    const [loadingSlotLote, setLoadingSlotLote] = useState(false);

    // Lote detail / create
    const [showLoteForm, setShowLoteForm] = useState(false);
    const [loteFormOp, setLoteFormOp] = useState(null);
    const [loteForm, setLoteForm] = useState({ op_id:"", data_manipulacao:"", data_envase:"", qtd_planejada:"", observacoes:"" });
    const [selectedLote, setSelectedLote] = useState(null);

    // Schedule from OPs tab
    const [scheduleOp, setScheduleOp] = useState(null);
    const [schedForm, setSchedForm] = useState({ linha_id:"", data_inicio:"", data_fim:"", turno:"integral", hora_inicio:"07:00", hora_fim:"17:00", tipo:"producao", qtd_planejada:"", observacoes:"" });

    // Linha form
    const [showLinhaForm, setShowLinhaForm] = useState(false);
    const [editLinha, setEditLinha] = useState(null);
    const [linhaForm, setLinhaForm] = useState({ nome:"", codigo:"", tipo:"geral", capacidade_diaria:"", unidade_capacidade:"kg", setup_minutos:30, observacoes:"" });

    // Calendar forms: { linha_id → { seg, ter, qua, qui, sex, sab, dom } }
    const [calForms, setCalForms] = useState({});
    const [savingCal, setSavingCal] = useState({});

    // Derived
    const weekDays = useMemo(() => Array.from({ length: 7 }, (_, i) => addDays(weekStart, i)), [weekStart]);
    const activeLinhas = useMemo(() => linhas.filter(l => l.status === "ativa"), [linhas]);

    // Calendar map: linha_id → calDoc
    const calMap = useMemo(() => {
        const m = {};
        for (const c of calendarios) m[c.linha_id] = c;
        return m;
    }, [calendarios]);

    // Slot index: linha_id → "YYYY-MM-DD:HH" → slot
    const slotIndex = useMemo(() => {
        const idx = {};
        for (const s of slots) {
            const data = s.data || s.data_inicio;
            if (!data) continue;
            const linhaIdx = idx[s.linha_id] || (idx[s.linha_id] = {});
            if (s.hora_inicio && s.hora_fim) {
                for (let h = hourInt(s.hora_inicio); h < hourInt(s.hora_fim); h++) {
                    linhaIdx[`${data}:${h}`] = s;
                }
            } else {
                // legacy: mark all hours
                for (const hr of HOURS) linhaIdx[`${data}:${hourInt(hr)}`] = s;
            }
        }
        return idx;
    }, [slots]);

    // ─── loaders ───────────────────────────────────────────────────────────
    const loadLinhas = useCallback(async () => {
        try { const { data } = await api.get("/pcp/linhas"); setLinhas(data || []); }
        catch (e) { toast.error(formatApiError(e)); }
    }, []);

    const loadSlots = useCallback(async () => {
        setLoadingSlots(true);
        try {
            const { data } = await api.get("/pcp/programacao", {
                params: { data_inicio: toYMD(weekStart), data_fim: toYMD(addDays(weekStart, 6)) },
            });
            setSlots(data || []);
        } catch (e) { toast.error(formatApiError(e)); }
        finally { setLoadingSlots(false); }
    }, [weekStart]);

    const loadCalendarios = useCallback(async () => {
        const semana = weekKey(weekStart);
        try {
            const { data } = await api.get("/pcp/calendario", { params: { semana } });
            setCalendarios(data || []);
        } catch { /* optional */ }
    }, [weekStart]);

    const loadOpsPendentes = useCallback(async () => {
        setLoadingOps(true);
        try {
            const { data } = await api.get("/ops", { params: { status: "aberta" } });
            setOpsPendentes((data || []).filter(op => !op.pcp_slot_id));
        } catch (e) { toast.error(formatApiError(e)); }
        finally { setLoadingOps(false); }
    }, []);

    const loadLotes = useCallback(async () => {
        setLoadingLotes(true);
        try {
            const { data } = await api.get("/pcp/lotes", {
                params: { data_inicio: toYMD(weekStart), data_fim: toYMD(addDays(weekStart, 6)) },
            });
            setLotes(data || []);
        } catch (e) { toast.error(formatApiError(e)); }
        finally { setLoadingLotes(false); }
    }, [weekStart]);

    const loadDashboard = useCallback(async () => {
        try { const { data } = await api.get("/pcp/dashboard"); setDashboard(data); }
        catch { /* optional */ }
    }, []);

    useEffect(() => { loadLinhas(); loadDashboard(); }, [loadLinhas, loadDashboard]);
    useEffect(() => { loadSlots(); loadCalendarios(); }, [loadSlots, loadCalendarios]);
    useEffect(() => { if (tab === "OPs Pendentes") loadOpsPendentes(); }, [tab, loadOpsPendentes]);
    useEffect(() => { if (tab === "Lotes") loadLotes(); }, [tab, loadLotes]);

    useEffect(() => {
        if (tab !== "Necessidades") return;
        setLoadingNec(true);
        api.get("/api/pcp/necessidades")
            .then(({ data }) => setNecessidades(data || []))
            .catch(() => {})
            .finally(() => setLoadingNec(false));
    }, [tab]);

    // Init calForms from loaded calendarios + active linhas
    useEffect(() => {
        const forms = {};
        for (const linha of activeLinhas) {
            const existing = calMap[linha.id];
            forms[linha.id] = existing
                ? { seg:existing.seg, ter:existing.ter, qua:existing.qua, qui:existing.qui, sex:existing.sex, sab:existing.sab, dom:existing.dom }
                : { seg:{...DEFAULT_DIA}, ter:{...DEFAULT_DIA}, qua:{...DEFAULT_DIA}, qui:{...DEFAULT_DIA}, sex:{...DEFAULT_DIA}, sab:{...DEFAULT_SAB}, dom:{...DEFAULT_SAB} };
        }
        setCalForms(forms);
    }, [calendarios, activeLinhas]); // eslint-disable-line

    // ─── grid helpers ──────────────────────────────────────────────────────
    const getCellSlot = (linhaId, ymd, hour) =>
        slotIndex[linhaId]?.[`${ymd}:${hourInt(hour)}`] || null;

    const isDayDisabled = (linhaId, d) => {
        const cal = calMap[linhaId];
        if (!cal) return false;
        const key = DIAS_KEY[dayIndex(d)];
        return cal[key]?.habilitado === false;
    };

    const isLunchHour = (linhaId, d, hour) => {
        const cal = calMap[linhaId];
        if (!cal) return false;
        const key = DIAS_KEY[dayIndex(d)];
        const dia = cal[key];
        if (!dia?.pausa_almoco) return false;
        const h = hourInt(hour);
        return h >= hourInt(dia.almoco_inicio || "12:00") && h < hourInt(dia.almoco_fim || "13:00");
    };

    const isSlotStart = (slot, hour) => slot && hourInt(slot.hora_inicio || "00:00") === hourInt(hour);

    // ─── handlers: grid ────────────────────────────────────────────────────
    const openCellCreate = async (linha, ymd, hora) => {
        setCellClick({ linha, ymd, hora });
        setCellForm({ op_id:"", lote_id:"", tipo:"producao", hora_fim:"", qtd_planejada:"", setup_tipo:"assepsia", setup_tempo_min:"30", observacoes:"" });
        // Load ops if needed
        if (opsPendentes.length === 0) {
            try { const { data } = await api.get("/ops", { params: { status: "aberta" } }); setCellOps((data||[]).filter(o=>!o.pcp_slot_id)); }
            catch { setCellOps([]); }
        } else { setCellOps(opsPendentes); }
        setCellLotes([]);
    };

    const onCellOpChange = async (opId) => {
        setCellForm(f => ({ ...f, op_id: opId, lote_id:"" }));
        if (!opId) { setCellLotes([]); return; }
        try { const { data } = await api.get("/pcp/lotes", { params: { op_id: opId } }); setCellLotes(data || []); }
        catch { setCellLotes([]); }
    };

    const handleCellSchedule = async () => {
        if (!cellClick) return;
        if (cellForm.tipo === "producao" && !cellForm.op_id) { toast.error("Selecione a OP"); return; }
        if (!cellForm.hora_fim) { toast.error("Hora fim obrigatória"); return; }
        setSaving(true);
        try {
            const opId = cellForm.op_id || (cellOps[0]?.id || "");
            if (!opId && cellForm.tipo === "producao") { toast.error("Selecione a OP"); setSaving(false); return; }
            await api.post("/pcp/programacao", {
                op_id: opId || cellOps[0]?.id || "",
                linha_id: cellClick.linha.id,
                data: cellClick.ymd,
                data_inicio: cellClick.ymd,
                data_fim: cellClick.ymd,
                hora_inicio: cellClick.hora,
                hora_fim: cellForm.hora_fim,
                tipo: cellForm.tipo,
                turno: "integral",
                setup_tipo: cellForm.setup_tipo,
                setup_tempo_min: cellForm.tipo === "setup" ? Number(cellForm.setup_tempo_min) || 30 : null,
                lote_id: cellForm.lote_id || null,
                qtd_planejada: Number(cellForm.qtd_planejada) || 0,
                observacoes: cellForm.observacoes,
            });
            toast.success("Bloco criado na grade");
            setCellClick(null);
            loadSlots(); loadDashboard();
        } catch (e) { toast.error(formatApiError(e)); }
        finally { setSaving(false); }
    };

    // ─── handlers: slot detail ─────────────────────────────────────────────
    const openSlotDetail = async (slot) => {
        setSelectedSlot(slot);
        setSlotLote(null);
        if (slot.lote_id) {
            setLoadingSlotLote(true);
            try { const { data } = await api.get(`/pcp/lotes/${slot.lote_id}`); setSlotLote(data); }
            catch { /* lote not found */ }
            finally { setLoadingSlotLote(false); }
        }
    };

    const handleAdvance = async (slot) => {
        const next = NEXT_SLOT[slot.status]; if (!next) return;
        setActionLoading(true);
        try {
            const { data: updated } = await api.put(`/pcp/programacao/${slot.id}`, { status: next.to });
            toast.success(`${next.label} — concluído`);
            setSelectedSlot(updated); loadSlots(); loadDashboard();
        } catch (e) { toast.error(formatApiError(e)); }
        finally { setActionLoading(false); }
    };

    const handleCancelSlot = async (slot) => {
        if (!window.confirm(`Cancelar ${slot.numero_prog}?`)) return;
        setActionLoading(true);
        try {
            await api.put(`/pcp/programacao/${slot.id}`, { status: "cancelado" });
            toast.success("Programação cancelada");
            setSelectedSlot(null); loadSlots(); loadDashboard();
        } catch (e) { toast.error(formatApiError(e)); }
        finally { setActionLoading(false); }
    };

    // ─── handlers: schedule from OPs tab ──────────────────────────────────
    const openSchedule = (op) => {
        setScheduleOp(op);
        setSchedForm({ linha_id: activeLinhas[0]?.id || "", data_inicio: toYMD(new Date()), data_fim: toYMD(new Date()), turno:"integral", hora_inicio:"07:00", hora_fim:"17:00", tipo:"producao", qtd_planejada: String(op.items?.[0]?.qtd_planejada || ""), observacoes:"" });
    };

    const handleSchedule = async () => {
        if (!schedForm.linha_id || !schedForm.data_inicio) { toast.error("Linha e data obrigatórios"); return; }
        setSaving(true);
        try {
            await api.post("/pcp/programacao", {
                op_id: scheduleOp.id,
                linha_id: schedForm.linha_id,
                data: schedForm.data_inicio,
                data_inicio: schedForm.data_inicio,
                data_fim: schedForm.data_fim || schedForm.data_inicio,
                hora_inicio: schedForm.hora_inicio,
                hora_fim: schedForm.hora_fim,
                turno: schedForm.turno,
                tipo: schedForm.tipo,
                qtd_planejada: Number(schedForm.qtd_planejada) || 0,
                observacoes: schedForm.observacoes,
            });
            toast.success("OP programada");
            setScheduleOp(null); loadSlots(); loadOpsPendentes(); loadDashboard();
        } catch (e) { toast.error(formatApiError(e)); }
        finally { setSaving(false); }
    };

    // ─── handlers: lotes ──────────────────────────────────────────────────
    const openLoteForm = (op = null) => {
        setLoteFormOp(op);
        setLoteForm({ op_id: op?.id || "", data_manipulacao: toYMD(new Date()), data_envase:"", qtd_planejada: String(op?.items?.[0]?.qtd_planejada || ""), observacoes:"" });
        setShowLoteForm(true);
    };

    const handleCreateLote = async () => {
        if (!loteForm.op_id || !loteForm.data_manipulacao) { toast.error("OP e data de manipulação obrigatórios"); return; }
        setSaving(true);
        try {
            await api.post("/pcp/lotes", {
                op_id: loteForm.op_id,
                data_manipulacao: loteForm.data_manipulacao,
                data_envase: loteForm.data_envase || null,
                qtd_planejada: Number(loteForm.qtd_planejada) || 0,
                observacoes: loteForm.observacoes,
            });
            toast.success("Lote criado");
            setShowLoteForm(false); loadLotes(); loadDashboard();
        } catch (e) { toast.error(formatApiError(e)); }
        finally { setSaving(false); }
    };

    const handleAdvanceLote = async (lote) => {
        const next = LOTE_NEXT[lote.status]; if (!next) return;
        setActionLoading(true);
        try {
            const { data: updated } = await api.put(`/pcp/lotes/${lote.id}`, { status: next });
            toast.success(`Lote avançado para ${LOTE_STATUS_LABEL[next]}`);
            setSelectedLote(updated); loadLotes(); loadDashboard();
        } catch (e) { toast.error(formatApiError(e)); }
        finally { setActionLoading(false); }
    };

    const handleCancelLote = async (lote) => {
        if (!window.confirm(`Cancelar lote ${lote.numero_lote}?`)) return;
        setActionLoading(true);
        try {
            await api.put(`/pcp/lotes/${lote.id}`, { status: "cancelado" });
            toast.success("Lote cancelado");
            setSelectedLote(null); loadLotes(); loadDashboard();
        } catch (e) { toast.error(formatApiError(e)); }
        finally { setActionLoading(false); }
    };

    // ─── handlers: linhas ─────────────────────────────────────────────────
    const openLinhaForm = (linha = null) => {
        setEditLinha(linha);
        setLinhaForm(linha ? { nome:linha.nome, codigo:linha.codigo||"", tipo:linha.tipo||"geral", capacidade_diaria:String(linha.capacidade_diaria||""), unidade_capacidade:linha.unidade_capacidade||"kg", setup_minutos:linha.setup_minutos||30, observacoes:linha.observacoes||"" }
            : { nome:"", codigo:"", tipo:"geral", capacidade_diaria:"", unidade_capacidade:"kg", setup_minutos:30, observacoes:"" });
        setShowLinhaForm(true);
    };

    const handleSaveLinha = async () => {
        if (!linhaForm.nome.trim()) { toast.error("Nome obrigatório"); return; }
        setSaving(true);
        try {
            const payload = { nome:linhaForm.nome.trim(), codigo:linhaForm.codigo, tipo:linhaForm.tipo, capacidade_diaria:Number(linhaForm.capacidade_diaria)||0, unidade_capacidade:linhaForm.unidade_capacidade, setup_minutos:Number(linhaForm.setup_minutos)||30, observacoes:linhaForm.observacoes };
            if (editLinha) await api.put(`/pcp/linhas/${editLinha.id}`, payload);
            else await api.post("/pcp/linhas", payload);
            toast.success(editLinha ? "Linha atualizada" : "Linha criada");
            setShowLinhaForm(false); loadLinhas(); loadDashboard();
        } catch (e) { toast.error(formatApiError(e)); }
        finally { setSaving(false); }
    };

    const handleToggleLinha = async (linha) => {
        try {
            await api.put(`/pcp/linhas/${linha.id}`, { status: linha.status === "ativa" ? "inativa" : "ativa" });
            toast.success(linha.status === "ativa" ? "Linha inativada" : "Linha ativada");
            loadLinhas();
        } catch (e) { toast.error(formatApiError(e)); }
    };

    // ─── handlers: calendário ─────────────────────────────────────────────
    const updateCalDia = (linhaId, dia, field, value) => {
        setCalForms(prev => ({
            ...prev,
            [linhaId]: { ...(prev[linhaId] || {}), [dia]: { ...(prev[linhaId]?.[dia] || DEFAULT_DIA), [field]: value } },
        }));
    };

    const handleSaveCalendario = async (linhaId) => {
        const form = calForms[linhaId];
        const semana = weekKey(weekStart);
        setSavingCal(p => ({ ...p, [linhaId]: true }));
        try {
            const payload = { semana, linha_id: linhaId, ...form };
            const existing = calMap[linhaId];
            if (existing) await api.put(`/pcp/calendario/${semana}/${linhaId}`, payload);
            else await api.post("/pcp/calendario", payload);
            toast.success("Calendário salvo");
            loadCalendarios();
        } catch (e) { toast.error(formatApiError(e)); }
        finally { setSavingCal(p => ({ ...p, [linhaId]: false })); }
    };

    // ─── render: hour grid cell ────────────────────────────────────────────
    const cellH = compact ? 22 : 40;

    const renderCell = (linha, d, hour) => {
        const ymd = toYMD(d);
        const disabled = isDayDisabled(linha.id, d);
        const slot = getCellSlot(linha.id, ymd, hour);
        const isStart = isSlotStart(slot, hour);
        const lunch = !slot && !disabled && isLunchHour(linha.id, d, hour);

        if (disabled) {
            return (
                <td key={`${ymd}-${hour}`} style={{ height: cellH, minWidth: 90 }}
                    className="border border-border bg-muted/40 relative overflow-hidden"
                    title="Dia desabilitado no calendário">
                    <div className="absolute inset-0" style={{ backgroundImage:"repeating-linear-gradient(45deg,#ccc 0,#ccc 1px,transparent 0,transparent 50%)", backgroundSize:"6px 6px", opacity:0.4 }} />
                </td>
            );
        }

        if (lunch) {
            return (
                <td key={`${ymd}-${hour}`} style={{ height: cellH, minWidth: 90 }}
                    className="border border-border bg-muted/20 text-center align-middle cursor-default"
                    title="Pausa almoço">
                    <Coffee className="h-3 w-3 mx-auto text-muted-foreground/50" />
                </td>
            );
        }

        if (!slot) {
            return (
                <td key={`${ymd}-${hour}`} style={{ height: cellH, minWidth: 90 }}
                    className="border border-border hover:bg-primary/5 cursor-pointer transition-colors"
                    onClick={() => openCellCreate(linha, ymd, hour)}
                    title={`Criar bloco — ${hour} ${ymd}`}>
                </td>
            );
        }

        const isSetup = slot.tipo === "setup";
        const isAlmoco = slot.tipo === "almoco";

        let bgStyle = {};
        let borderColor = "#94a3b8";
        let textColor = "#1e293b";

        if (isSetup) { bgStyle = { backgroundColor:"#e5e7eb" }; borderColor = "#9ca3af"; textColor = "#374151"; }
        else if (isAlmoco) { bgStyle = { backgroundColor:"#fef9c3" }; borderColor = "#fde047"; textColor = "#713f12"; }
        else {
            const cc = clientColor(slot.cliente_nome);
            bgStyle = { backgroundColor: cc.bg };
            borderColor = cc.border;
            textColor = cc.text;
        }

        return (
            <td key={`${ymd}-${hour}`} style={{ height: cellH, minWidth: 90, borderColor, ...bgStyle, color: textColor }}
                className="border cursor-pointer hover:opacity-80 transition-opacity overflow-hidden align-top"
                onClick={() => openSlotDetail(slot)}>
                {isStart && (
                    <div className="px-1 py-0.5 leading-tight" style={{ fontSize: 10 }}>
                        {isSetup ? (
                            <span className="flex items-center gap-0.5">⚙ {compact ? "" : `Setup ${TIPOS_SETUP_LABEL[slot.setup_tipo] || ""}`}</span>
                        ) : isAlmoco ? (
                            <span>☕ {compact ? "" : "Almoço"}</span>
                        ) : (
                            <>
                                <div className="font-bold truncate">{compact ? (slot.cliente_nome?.split(" ")[0] || slot.op_numero) : slot.cliente_nome}</div>
                                {!compact && <div className="truncate opacity-80">{slot.produto_nome || slot.op_numero}</div>}
                                {!compact && <div className="opacity-60">{slot.numero_prog}</div>}
                            </>
                        )}
                    </div>
                )}
            </td>
        );
    };

    // ─── JSX ──────────────────────────────────────────────────────────────
    return (
        <div className="h-full overflow-auto">
            <div className="max-w-[1400px] mx-auto p-6 space-y-5">

                {/* Header */}
                <div className="flex items-start justify-between gap-4 flex-wrap">
                    <div>
                        <h1 className="text-2xl font-heading font-semibold tracking-tight flex items-center gap-2">
                            <Calendar className="h-6 w-6" /> PCP — Programação da Produção
                        </h1>
                        <p className="text-sm text-muted-foreground mt-1">Grade horária de alocação de OPs em linhas de produção</p>
                    </div>
                </div>

                {/* Dashboard strip */}
                {dashboard && (
                    <div className="grid grid-cols-3 md:grid-cols-7 gap-2">
                        {[
                            { label:"Linhas Ativas",     value:dashboard.linhas_ativas,          cls:"text-foreground" },
                            { label:"Planejados",        value:dashboard.planejados,              cls:"text-slate-600" },
                            { label:"Em Execução",       value:dashboard.em_execucao,             cls:"text-amber-600" },
                            { label:"Conc. Hoje",        value:dashboard.concluidos_hoje,         cls:"text-green-600" },
                            { label:"OPs s/ PCP",        value:dashboard.ops_sem_pcp,             cls:"text-red-600" },
                            { label:"Lotes Ativos",      value:dashboard.lotes_ativos ?? "—",     cls:"text-purple-600" },
                            { label:"Calendários",       value:dashboard.calendarios_semana_atual ?? "—", cls:"text-blue-600" },
                        ].map(s => (
                            <Card key={s.label}><CardContent className="p-3">
                                <div className="text-[10px] text-muted-foreground uppercase tracking-wider leading-tight">{s.label}</div>
                                <div className={`text-xl font-bold mt-0.5 ${s.cls}`}>{s.value}</div>
                            </CardContent></Card>
                        ))}
                    </div>
                )}

                {/* Tabs */}
                <div className="flex border-b border-border overflow-x-auto">
                    {TABS.map(t => (
                        <button key={t} onClick={() => setTab(t)}
                            className={`px-4 py-2 text-sm font-medium border-b-2 whitespace-nowrap transition-colors ${
                                tab === t ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"
                            }`}>{t}</button>
                    ))}
                </div>

                {/* ══════════ Tab: Programação ══════════ */}
                {tab === "Programação" && (
                    <div className="space-y-4">
                        {/* Week nav + compact toggle */}
                        <div className="flex items-center gap-3 flex-wrap">
                            <Button variant="outline" size="icon" onClick={() => setWeekStart(w => addDays(w, -7))}><ChevronLeft className="h-4 w-4" /></Button>
                            <span className="text-sm font-medium min-w-[200px] text-center">
                                Semana {weekKey(weekStart)} — {formatDateBR(toYMD(weekStart))} a {formatDateBR(toYMD(addDays(weekStart, 6)))}
                            </span>
                            <Button variant="outline" size="icon" onClick={() => setWeekStart(w => addDays(w, 7))}><ChevronRight className="h-4 w-4" /></Button>
                            <Button variant="outline" size="sm" onClick={() => setWeekStart(startOfWeek(new Date()))}>Hoje</Button>
                            <div className="flex items-center gap-2 ml-auto">
                                <span className="text-xs text-muted-foreground">Compacto</span>
                                <Switch checked={compact} onCheckedChange={setCompact} />
                                <span className="text-xs text-muted-foreground">Detalhado</span>
                            </div>
                        </div>

                        {loadingSlots ? (
                            <div className="flex justify-center py-20"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
                        ) : activeLinhas.length === 0 ? (
                            <Card className="border-dashed"><CardContent className="py-12 text-center">
                                <Wrench className="h-12 w-12 mx-auto mb-3 text-muted-foreground/30" />
                                <p className="font-semibold">Nenhuma linha de produção ativa</p>
                                <Button className="mt-4" size="sm" onClick={() => setTab("Linhas")}>Gerenciar Linhas</Button>
                            </CardContent></Card>
                        ) : (
                            <div className="space-y-6">
                                {activeLinhas.map(linha => (
                                    <div key={linha.id}>
                                        {/* Line header */}
                                        <div className="flex items-center gap-2 mb-1">
                                            <Factory className="h-4 w-4 text-muted-foreground" />
                                            <span className="text-sm font-semibold">{linha.nome}</span>
                                            <span className="text-xs text-muted-foreground">({TIPO_LINHA_LABEL[linha.tipo] || linha.tipo})</span>
                                            {!calMap[linha.id] && (
                                                <span className="flex items-center gap-1 text-xs text-amber-600 ml-2">
                                                    <AlertTriangle className="h-3 w-3" /> Sem calendário para esta semana
                                                </span>
                                            )}
                                        </div>
                                        {/* Hour grid */}
                                        <div className="overflow-x-auto rounded-lg border border-border">
                                            <table className="border-collapse" style={{ tableLayout:"fixed", minWidth: 800 }}>
                                                <colgroup>
                                                    <col style={{ width:52 }} />
                                                    {weekDays.map(d => <col key={toYMD(d)} style={{ width:110 }} />)}
                                                </colgroup>
                                                <thead>
                                                    <tr className="bg-muted/40">
                                                        <th className="border border-border px-1 py-1.5 text-[10px] text-muted-foreground font-medium text-right pr-2">Hora</th>
                                                        {weekDays.map(d => {
                                                            const ymd = toYMD(d);
                                                            const isToday = ymd === toYMD(new Date());
                                                            const dis = isDayDisabled(linha.id, d);
                                                            return (
                                                                <th key={ymd} className={`border border-border px-1 py-1.5 text-center ${isToday ? "text-primary" : "text-muted-foreground"} ${dis ? "opacity-40" : ""}`}>
                                                                    <div className="text-[10px]">{DAYS_PT[d.getDay()]}</div>
                                                                    <div className={`text-sm font-bold ${isToday ? "text-primary" : "text-foreground"}`}>{d.getDate()}</div>
                                                                </th>
                                                            );
                                                        })}
                                                    </tr>
                                                </thead>
                                                <tbody>
                                                    {HOURS.map(hour => (
                                                        <tr key={hour}>
                                                            <td className="border border-border px-1 text-right text-[10px] text-muted-foreground font-mono bg-muted/20" style={{ height: cellH }}>
                                                                {hour}
                                                            </td>
                                                            {weekDays.map(d => renderCell(linha, d, hour))}
                                                        </tr>
                                                    ))}
                                                </tbody>
                                            </table>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}

                        {/* Legend */}
                        <div className="flex items-center gap-4 flex-wrap text-xs text-muted-foreground pt-1">
                            <span className="flex items-center gap-1"><span className="w-4 h-3 rounded inline-block bg-blue-200 border border-blue-400" /> Produção (cor = cliente)</span>
                            <span className="flex items-center gap-1"><span className="w-4 h-3 rounded inline-block bg-gray-200 border border-gray-400" /> Setup ⚙</span>
                            <span className="flex items-center gap-1"><span className="w-4 h-3 rounded inline-block bg-yellow-50 border border-yellow-300" /> Almoço ☕</span>
                            <span className="flex items-center gap-1"><span className="w-4 h-3 rounded inline-block bg-muted/40 border border-border opacity-60" style={{ backgroundImage:"repeating-linear-gradient(45deg,#ccc 0,#ccc 1px,transparent 0,transparent 50%)", backgroundSize:"6px 6px" }} /> Dia desabilitado</span>
                            <span className="ml-auto flex items-center gap-1"><Plus className="h-3 w-3" /> Clique em célula vazia para criar bloco</span>
                        </div>
                    </div>
                )}

                {/* ══════════ Tab: OPs Pendentes ══════════ */}
                {tab === "OPs Pendentes" && (
                    <div className="space-y-2">
                        {loadingOps ? (
                            <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
                        ) : opsPendentes.length === 0 ? (
                            <Card className="border-dashed"><CardContent className="py-12 text-center">
                                <CheckCircle2 className="h-12 w-12 mx-auto mb-3 text-green-500/40" />
                                <p className="font-semibold">Todas as OPs estão programadas</p>
                            </CardContent></Card>
                        ) : opsPendentes.map(op => (
                            <Card key={op.id} className="hover:border-primary/40 transition-colors">
                                <CardContent className="p-4 flex items-start justify-between gap-4">
                                    <div className="space-y-1 flex-1 min-w-0">
                                        <div className="flex items-center gap-2 flex-wrap">
                                            <span className="font-mono text-sm font-bold text-primary">{op.numero_op}</span>
                                            <Badge variant="outline" className="text-[10px]">{op.status}</Badge>
                                        </div>
                                        <p className="font-semibold text-sm">{op.cliente_nome || "—"}</p>
                                        <p className="text-xs text-muted-foreground">{op.items?.[0]?.item || op.project_name || "—"}</p>
                                        {op.items?.[0]?.qtd_planejada > 0 && <p className="text-xs text-muted-foreground">Qtd: {op.items[0].qtd_planejada}</p>}
                                    </div>
                                    <div className="flex flex-col gap-1">
                                        <Button size="sm" disabled={activeLinhas.length === 0} onClick={() => openSchedule(op)}>
                                            <Calendar className="h-3.5 w-3.5 mr-1" /> Programar
                                        </Button>
                                        <Button size="sm" variant="outline" onClick={() => openLoteForm(op)}>
                                            <Layers className="h-3.5 w-3.5 mr-1" /> Criar Lote
                                        </Button>
                                    </div>
                                </CardContent>
                            </Card>
                        ))}
                    </div>
                )}

                {/* ══════════ Tab: Lotes ══════════ */}
                {tab === "Lotes" && (
                    <div className="space-y-3">
                        <div className="flex items-center justify-between gap-3">
                            <div className="flex items-center gap-3">
                                <Button variant="outline" size="icon" onClick={() => setWeekStart(w => addDays(w, -7))}><ChevronLeft className="h-4 w-4" /></Button>
                                <span className="text-sm font-medium">Semana {weekKey(weekStart)}</span>
                                <Button variant="outline" size="icon" onClick={() => setWeekStart(w => addDays(w, 7))}><ChevronRight className="h-4 w-4" /></Button>
                            </div>
                            <Button onClick={() => openLoteForm()}>
                                <Plus className="h-4 w-4 mr-1" /> Novo Lote
                            </Button>
                        </div>
                        {loadingLotes ? (
                            <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
                        ) : lotes.length === 0 ? (
                            <Card className="border-dashed"><CardContent className="py-12 text-center">
                                <Package className="h-12 w-12 mx-auto mb-3 text-muted-foreground/30" />
                                <p className="font-semibold">Nenhum lote para esta semana</p>
                            </CardContent></Card>
                        ) : (
                            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
                                {lotes.map(lote => (
                                    <Card key={lote.id} className="cursor-pointer hover:border-primary/40 transition-colors" onClick={() => setSelectedLote(lote)}>
                                        <CardContent className="p-4 space-y-2">
                                            <div className="flex items-start justify-between gap-2">
                                                <div>
                                                    <p className="font-mono text-sm font-bold text-primary">{lote.numero_lote}</p>
                                                    <p className="text-xs text-muted-foreground">{lote.op_numero}</p>
                                                </div>
                                                <LoteBadge status={lote.status} />
                                            </div>
                                            <p className="font-semibold text-sm truncate">{lote.cliente_nome}</p>
                                            <p className="text-xs text-muted-foreground truncate">{lote.produto_nome}</p>
                                            <div className="grid grid-cols-2 gap-1 text-xs text-muted-foreground">
                                                <div>Manip: {formatDateBR(lote.data_manipulacao)}</div>
                                                <div>Envase: {formatDateBR(lote.data_envase) || "—"}</div>
                                                <div>Plan: {lote.qtd_planejada}</div>
                                                <div>Prod: {lote.qtd_produzida || 0}</div>
                                            </div>
                                        </CardContent>
                                    </Card>
                                ))}
                            </div>
                        )}
                    </div>
                )}

                {/* ══════════ Tab: Calendário ══════════ */}
                {tab === "Calendário" && (
                    <div className="space-y-4">
                        <div className="flex items-center gap-3">
                            <Button variant="outline" size="icon" onClick={() => setWeekStart(w => addDays(w, -7))}><ChevronLeft className="h-4 w-4" /></Button>
                            <span className="text-sm font-medium min-w-[160px] text-center">Semana {weekKey(weekStart)}</span>
                            <Button variant="outline" size="icon" onClick={() => setWeekStart(w => addDays(w, 7))}><ChevronRight className="h-4 w-4" /></Button>
                            <Button variant="outline" size="sm" onClick={() => setWeekStart(startOfWeek(new Date()))}>Hoje</Button>
                        </div>
                        <p className="text-xs text-muted-foreground">Configure os horários de trabalho de cada linha para a semana selecionada. Esta configuração é obrigatória antes de programar OPs (RN-PCP-03).</p>
                        {activeLinhas.length === 0 ? (
                            <Card className="border-dashed"><CardContent className="py-12 text-center">
                                <Factory className="h-12 w-12 mx-auto mb-3 text-muted-foreground/30" />
                                <p className="font-semibold">Nenhuma linha ativa</p>
                                <Button className="mt-4" size="sm" onClick={() => setTab("Linhas")}>Criar Linhas</Button>
                            </CardContent></Card>
                        ) : (
                            <div className="space-y-6">
                                {activeLinhas.map(linha => {
                                    const form = calForms[linha.id] || {};
                                    const hasExisting = !!calMap[linha.id];
                                    return (
                                        <Card key={linha.id}>
                                            <CardHeader className="pb-3">
                                                <CardTitle className="flex items-center justify-between text-base">
                                                    <span className="flex items-center gap-2">
                                                        <Factory className="h-4 w-4" />{linha.nome}
                                                        {hasExisting && <Badge variant="outline" className="text-[10px] text-green-700 border-green-300">Configurado</Badge>}
                                                    </span>
                                                    <Button size="sm" disabled={savingCal[linha.id]} onClick={() => handleSaveCalendario(linha.id)}>
                                                        {savingCal[linha.id] ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" /> : null}
                                                        Salvar Semana
                                                    </Button>
                                                </CardTitle>
                                            </CardHeader>
                                            <CardContent>
                                                <div className="overflow-x-auto">
                                                    <table className="w-full text-xs border-collapse min-w-[600px]">
                                                        <thead>
                                                            <tr className="bg-muted/30">
                                                                <th className="text-left px-2 py-1.5 border border-border font-medium">Campo</th>
                                                                {DIAS_KEY.map((dia, i) => (
                                                                    <th key={dia} className="text-center px-2 py-1.5 border border-border font-medium">
                                                                        {["Seg","Ter","Qua","Qui","Sex","Sáb","Dom"][i]}
                                                                    </th>
                                                                ))}
                                                            </tr>
                                                        </thead>
                                                        <tbody>
                                                            <tr>
                                                                <td className="px-2 py-1.5 border border-border text-muted-foreground font-medium">Ativo</td>
                                                                {DIAS_KEY.map(dia => (
                                                                    <td key={dia} className="px-2 py-1.5 border border-border text-center">
                                                                        <Switch checked={!!(form[dia]?.habilitado)} onCheckedChange={v => updateCalDia(linha.id, dia, "habilitado", v)} />
                                                                    </td>
                                                                ))}
                                                            </tr>
                                                            <tr>
                                                                <td className="px-2 py-1.5 border border-border text-muted-foreground font-medium">Início</td>
                                                                {DIAS_KEY.map(dia => (
                                                                    <td key={dia} className="px-2 py-1.5 border border-border">
                                                                        <Input type="time" value={form[dia]?.hora_inicio || "07:00"} disabled={!form[dia]?.habilitado}
                                                                            onChange={e => updateCalDia(linha.id, dia, "hora_inicio", e.target.value)} className="h-7 text-xs px-1" />
                                                                    </td>
                                                                ))}
                                                            </tr>
                                                            <tr>
                                                                <td className="px-2 py-1.5 border border-border text-muted-foreground font-medium">Fim</td>
                                                                {DIAS_KEY.map(dia => (
                                                                    <td key={dia} className="px-2 py-1.5 border border-border">
                                                                        <Input type="time" value={form[dia]?.hora_fim || "18:00"} disabled={!form[dia]?.habilitado}
                                                                            onChange={e => updateCalDia(linha.id, dia, "hora_fim", e.target.value)} className="h-7 text-xs px-1" />
                                                                    </td>
                                                                ))}
                                                            </tr>
                                                            <tr>
                                                                <td className="px-2 py-1.5 border border-border text-muted-foreground font-medium">Almoço</td>
                                                                {DIAS_KEY.map(dia => (
                                                                    <td key={dia} className="px-2 py-1.5 border border-border text-center">
                                                                        <Switch checked={!!(form[dia]?.pausa_almoco)} disabled={!form[dia]?.habilitado}
                                                                            onCheckedChange={v => updateCalDia(linha.id, dia, "pausa_almoco", v)} />
                                                                    </td>
                                                                ))}
                                                            </tr>
                                                            <tr>
                                                                <td className="px-2 py-1.5 border border-border text-muted-foreground font-medium">Alm. Início</td>
                                                                {DIAS_KEY.map(dia => (
                                                                    <td key={dia} className="px-2 py-1.5 border border-border">
                                                                        <Input type="time" value={form[dia]?.almoco_inicio || "12:00"} disabled={!form[dia]?.habilitado || !form[dia]?.pausa_almoco}
                                                                            onChange={e => updateCalDia(linha.id, dia, "almoco_inicio", e.target.value)} className="h-7 text-xs px-1" />
                                                                    </td>
                                                                ))}
                                                            </tr>
                                                            <tr>
                                                                <td className="px-2 py-1.5 border border-border text-muted-foreground font-medium">Alm. Fim</td>
                                                                {DIAS_KEY.map(dia => (
                                                                    <td key={dia} className="px-2 py-1.5 border border-border">
                                                                        <Input type="time" value={form[dia]?.almoco_fim || "13:00"} disabled={!form[dia]?.habilitado || !form[dia]?.pausa_almoco}
                                                                            onChange={e => updateCalDia(linha.id, dia, "almoco_fim", e.target.value)} className="h-7 text-xs px-1" />
                                                                    </td>
                                                                ))}
                                                            </tr>
                                                        </tbody>
                                                    </table>
                                                </div>
                                            </CardContent>
                                        </Card>
                                    );
                                })}
                            </div>
                        )}
                    </div>
                )}

                {/* ══════════ Tab: Necessidades ══════════ */}
                {tab === "Necessidades" && (
                    <div className="space-y-4">
                        <div className="flex items-center justify-between">
                            <h2 className="font-semibold flex items-center gap-2 text-sm">
                                <Package className="h-4 w-4 text-blue-600" /> Necessidades de Material — PCP
                            </h2>
                            <Button size="sm" variant="outline" onClick={() => {
                                setLoadingNec(true);
                                api.get("/api/pcp/necessidades")
                                    .then(({ data }) => setNecessidades(data || []))
                                    .catch(() => {})
                                    .finally(() => setLoadingNec(false));
                            }}>
                                <Layers className="h-3.5 w-3.5 mr-1" /> Atualizar
                            </Button>
                        </div>

                        {loadingNec ? (
                            <div className="py-12 flex justify-center"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
                        ) : necessidades.length === 0 ? (
                            <Card className="border-dashed">
                                <CardContent className="py-12 text-center">
                                    <Package className="h-10 w-10 mx-auto mb-3 text-muted-foreground/30" />
                                    <p className="font-semibold text-muted-foreground">Nenhuma necessidade de material para PCP</p>
                                    <p className="text-xs text-muted-foreground mt-1">As necessidades aparecem aqui após a confirmação de pedidos no CRM.</p>
                                </CardContent>
                            </Card>
                        ) : necessidades.map((doc) => {
                            const itens = doc.materiais || [];
                            return (
                                <Card key={doc.proposta_id || doc._id} className="overflow-hidden">
                                    <CardHeader className="py-3 px-4 bg-muted/40 border-b">
                                        <div className="flex items-center justify-between">
                                            <CardTitle className="text-sm font-medium flex items-center gap-2">
                                                <span className="font-mono text-muted-foreground text-xs">
                                                    Pedido {doc.proposta_id?.slice(-8) || "—"}
                                                </span>
                                                {doc.projeto_id && (
                                                    <Badge variant="outline" className="text-xs">{doc.projeto_id.slice(-8)}</Badge>
                                                )}
                                            </CardTitle>
                                            <span className="text-xs text-muted-foreground">
                                                Gerado em {doc.gerado_em?.slice(0, 10) || "—"}
                                            </span>
                                        </div>
                                    </CardHeader>
                                    <CardContent className="p-0">
                                        <table className="w-full text-xs">
                                            <thead className="bg-muted/20 border-b">
                                                <tr>
                                                    {["Código", "Descrição", "Qtd. Necessária", "Un. Compra", ""].map(h => (
                                                        <th key={h} className="px-3 py-2 text-left font-medium text-muted-foreground">{h}</th>
                                                    ))}
                                                </tr>
                                            </thead>
                                            <tbody className="divide-y">
                                                {itens.map((m, idx) => (
                                                    <tr key={idx} className={m.pendente_info ? "bg-amber-50/60" : "hover:bg-muted/20"}>
                                                        <td className="px-3 py-2 font-mono">{m.codigo_material || "—"}</td>
                                                        <td className="px-3 py-2">{m.descricao}</td>
                                                        <td className="px-3 py-2 text-right tabular-nums font-medium">{m.qtd_necessaria_compra}</td>
                                                        <td className="px-3 py-2 text-muted-foreground">{m.unidade_compra}</td>
                                                        <td className="px-3 py-2">
                                                            {m.pendente_info && (
                                                                <span className="flex items-center gap-1 text-amber-600">
                                                                    <AlertTriangle className="h-3 w-3" /> Incompleto
                                                                </span>
                                                            )}
                                                        </td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </CardContent>
                                </Card>
                            );
                        })}
                    </div>
                )}

                {/* ══════════ Tab: Linhas ══════════ */}
                {tab === "Linhas" && (
                    <div className="space-y-3">
                        <div className="flex justify-end">
                            <Button onClick={() => openLinhaForm()}><Plus className="h-4 w-4 mr-1" /> Nova Linha</Button>
                        </div>
                        {linhas.length === 0 ? (
                            <Card className="border-dashed"><CardContent className="py-12 text-center">
                                <Factory className="h-12 w-12 mx-auto mb-3 text-muted-foreground/30" />
                                <p className="font-semibold">Nenhuma linha cadastrada</p>
                            </CardContent></Card>
                        ) : (
                            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
                                {linhas.map(linha => (
                                    <Card key={linha.id} className={linha.status !== "ativa" ? "opacity-60" : ""}>
                                        <CardContent className="p-4 space-y-2">
                                            <div className="flex items-start justify-between gap-2">
                                                <div>
                                                    <p className="font-semibold">{linha.nome}</p>
                                                    {linha.codigo && <p className="text-xs text-muted-foreground font-mono">{linha.codigo}</p>}
                                                </div>
                                                <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium ${linha.status === "ativa" ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
                                                    {linha.status === "ativa" ? "Ativa" : "Inativa"}
                                                </span>
                                            </div>
                                            <div className="text-xs text-muted-foreground space-y-0.5">
                                                <div>{TIPO_LINHA_LABEL[linha.tipo] || linha.tipo}</div>
                                                {linha.capacidade_diaria > 0 && <div>Cap: {linha.capacidade_diaria} {linha.unidade_capacidade}/dia</div>}
                                                <div className="flex items-center gap-1"><Clock className="h-3 w-3" /> Setup: {linha.setup_minutos} min</div>
                                            </div>
                                            <div className="flex gap-1.5 pt-1">
                                                <Button variant="outline" size="sm" className="flex-1 h-7 text-xs" onClick={() => openLinhaForm(linha)}>
                                                    <Settings className="h-3 w-3 mr-1" />Editar
                                                </Button>
                                                <Button variant="outline" size="sm" className="flex-1 h-7 text-xs" onClick={() => handleToggleLinha(linha)}>
                                                    {linha.status === "ativa" ? "Inativar" : "Ativar"}
                                                </Button>
                                            </div>
                                        </CardContent>
                                    </Card>
                                ))}
                            </div>
                        )}
                    </div>
                )}
            </div>

            {/* ══════════ Dialog: Slot Detail ══════════ */}
            {selectedSlot && (
                <Dialog open onOpenChange={() => setSelectedSlot(null)}>
                    <DialogContent className="max-w-lg">
                        <DialogHeader>
                            <DialogTitle className="flex items-center gap-2">
                                <Calendar className="h-5 w-5" /> {selectedSlot.numero_prog}
                            </DialogTitle>
                        </DialogHeader>
                        <div className="space-y-3 text-sm">
                            <div className="flex items-center gap-2 flex-wrap">
                                <SlotBadge status={selectedSlot.status} />
                                <Badge variant="outline" className="text-[10px]">{selectedSlot.tipo || "producao"}</Badge>
                                {selectedSlot.hora_inicio && <span className="text-xs text-muted-foreground">{selectedSlot.hora_inicio}–{selectedSlot.hora_fim}</span>}
                            </div>
                            <div className="grid grid-cols-2 gap-2">
                                <div><span className="text-muted-foreground text-xs">OP:</span> <span className="font-mono text-xs">{selectedSlot.op_numero || "—"}</span></div>
                                <div><span className="text-muted-foreground text-xs">Linha:</span> <span className="text-xs">{selectedSlot.linha_nome}</span></div>
                                <div><span className="text-muted-foreground text-xs">Produto:</span> <span className="text-xs">{selectedSlot.produto_nome || "—"}</span></div>
                                <div><span className="text-muted-foreground text-xs">Cliente:</span> <span className="text-xs">{selectedSlot.cliente_nome || "—"}</span></div>
                                <div><span className="text-muted-foreground text-xs">Data:</span> <span className="text-xs">{formatDateBR(selectedSlot.data || selectedSlot.data_inicio)}</span></div>
                                <div><span className="text-muted-foreground text-xs">Turno:</span> <span className="text-xs">{TURNO_LABEL[selectedSlot.turno] || selectedSlot.turno}</span></div>
                                <div><span className="text-muted-foreground text-xs">Qtd Plan.:</span> <span className="text-xs">{selectedSlot.qtd_planejada}</span></div>
                                <div><span className="text-muted-foreground text-xs">Qtd Prod.:</span> <span className="text-xs">{selectedSlot.qtd_produzida}</span></div>
                            </div>
                            {/* Lote info */}
                            {selectedSlot.lote_id && (
                                <div className="rounded-md border border-border p-2 bg-muted/20">
                                    <p className="text-xs font-semibold text-muted-foreground mb-1 flex items-center gap-1"><Layers className="h-3 w-3" /> Lote</p>
                                    {loadingSlotLote ? <Loader2 className="h-4 w-4 animate-spin" /> : slotLote ? (
                                        <div className="grid grid-cols-2 gap-1 text-xs">
                                            <div><span className="text-muted-foreground">Número:</span> <span className="font-mono font-bold">{slotLote.numero_lote}</span></div>
                                            <div><LoteBadge status={slotLote.status} /></div>
                                            <div><span className="text-muted-foreground">Manip.:</span> {formatDateBR(slotLote.data_manipulacao)}</div>
                                            <div><span className="text-muted-foreground">Envase:</span> {formatDateBR(slotLote.data_envase) || "—"}</div>
                                            <div><span className="text-muted-foreground">Qtd:</span> {slotLote.qtd_planejada}</div>
                                        </div>
                                    ) : <p className="text-xs text-muted-foreground">Lote não encontrado</p>}
                                </div>
                            )}
                            {selectedSlot.observacoes && <p className="text-xs text-muted-foreground border-t border-border pt-2">{selectedSlot.observacoes}</p>}
                            {(selectedSlot.historico || []).length > 0 && (
                                <>
                                    <Separator />
                                    <div>
                                        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">Histórico</p>
                                        {selectedSlot.historico.map((h, i) => (
                                            <div key={i} className="text-xs text-muted-foreground flex gap-2 flex-wrap">
                                                <span>{new Date(h.em).toLocaleString("pt-BR")}</span>
                                                <span>·</span>
                                                <span>{h.de ? `${SLOT_STATUS_CFG[h.de]?.label || h.de} → ${SLOT_STATUS_CFG[h.para]?.label || h.para}` : "Criado"}</span>
                                                <span>· {h.por}</span>
                                            </div>
                                        ))}
                                    </div>
                                </>
                            )}
                        </div>
                        <DialogFooter className="flex flex-wrap gap-2 justify-between">
                            <div className="flex gap-2">
                                {NEXT_SLOT[selectedSlot.status] && (() => {
                                    const n = NEXT_SLOT[selectedSlot.status];
                                    return (
                                        <Button size="sm" disabled={actionLoading} onClick={() => handleAdvance(selectedSlot)}>
                                            {actionLoading ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <n.Icon className="h-4 w-4 mr-1" />}
                                            {n.label}
                                        </Button>
                                    );
                                })()}
                                {["planejado","em_execucao"].includes(selectedSlot.status) && (
                                    <Button size="sm" variant="outline" className="text-destructive border-destructive/30" disabled={actionLoading}
                                        onClick={() => handleCancelSlot(selectedSlot)}>
                                        <XCircle className="h-4 w-4 mr-1" /> Cancelar
                                    </Button>
                                )}
                            </div>
                            <Button variant="outline" onClick={() => setSelectedSlot(null)}>Fechar</Button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>
            )}

            {/* ══════════ Dialog: Cell click → Create Slot ══════════ */}
            {cellClick && (
                <Dialog open onOpenChange={() => setCellClick(null)}>
                    <DialogContent className="max-w-md">
                        <DialogHeader>
                            <DialogTitle>Novo Bloco — {cellClick.linha.nome}</DialogTitle>
                        </DialogHeader>
                        <div className="text-xs text-muted-foreground mb-1">{formatDateBR(cellClick.ymd)} às {cellClick.hora}</div>
                        <div className="space-y-3">
                            <div>
                                <Label>Tipo de Bloco</Label>
                                <Select value={cellForm.tipo} onValueChange={v => setCellForm(f => ({ ...f, tipo: v }))}>
                                    <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="producao">Produção</SelectItem>
                                        <SelectItem value="setup">Setup</SelectItem>
                                        <SelectItem value="almoco">Almoço</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                            {cellForm.tipo === "producao" && (
                                <>
                                    <div>
                                        <Label>OP *</Label>
                                        <Select value={cellForm.op_id} onValueChange={onCellOpChange}>
                                            <SelectTrigger className="mt-1"><SelectValue placeholder="Selecionar OP…" /></SelectTrigger>
                                            <SelectContent>
                                                {cellOps.map(op => (
                                                    <SelectItem key={op.id} value={op.id}>{op.numero_op} — {op.cliente_nome}</SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                    {cellLotes.length > 0 && (
                                        <div>
                                            <Label>Lote (opcional)</Label>
                                            <Select value={cellForm.lote_id} onValueChange={v => setCellForm(f => ({ ...f, lote_id: v }))}>
                                                <SelectTrigger className="mt-1"><SelectValue placeholder="Sem lote" /></SelectTrigger>
                                                <SelectContent>
                                                    <SelectItem value="">Sem lote</SelectItem>
                                                    {cellLotes.map(l => (
                                                        <SelectItem key={l.id} value={l.id}>{l.numero_lote} — {LOTE_STATUS_LABEL[l.status]}</SelectItem>
                                                    ))}
                                                </SelectContent>
                                            </Select>
                                        </div>
                                    )}
                                    <div>
                                        <Label>Qtd Planejada</Label>
                                        <Input type="number" value={cellForm.qtd_planejada} onChange={e => setCellForm(f => ({ ...f, qtd_planejada: e.target.value }))} placeholder="0" className="mt-1" />
                                    </div>
                                </>
                            )}
                            {cellForm.tipo === "setup" && (
                                <div className="grid grid-cols-2 gap-3">
                                    <div>
                                        <Label>Tipo de Setup</Label>
                                        <Select value={cellForm.setup_tipo} onValueChange={v => setCellForm(f => ({ ...f, setup_tipo: v }))}>
                                            <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                                            <SelectContent>
                                                {TIPOS_SETUP.map(t => <SelectItem key={t} value={t}>{TIPOS_SETUP_LABEL[t]}</SelectItem>)}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                    <div>
                                        <Label>Tempo (min)</Label>
                                        <Input type="number" value={cellForm.setup_tempo_min} onChange={e => setCellForm(f => ({ ...f, setup_tempo_min: e.target.value }))} className="mt-1" />
                                    </div>
                                </div>
                            )}
                            <div>
                                <Label>Hora Fim *</Label>
                                <Input type="time" value={cellForm.hora_fim} onChange={e => setCellForm(f => ({ ...f, hora_fim: e.target.value }))} className="mt-1" />
                            </div>
                            <div>
                                <Label>Observações</Label>
                                <Input value={cellForm.observacoes} onChange={e => setCellForm(f => ({ ...f, observacoes: e.target.value }))} placeholder="Opcional" className="mt-1" />
                            </div>
                        </div>
                        <DialogFooter>
                            <Button variant="outline" onClick={() => setCellClick(null)} disabled={saving}>Cancelar</Button>
                            <Button onClick={handleCellSchedule} disabled={saving}>
                                {saving ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Plus className="h-4 w-4 mr-1" />}
                                Criar Bloco
                            </Button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>
            )}

            {/* ══════════ Dialog: Schedule from OPs tab ══════════ */}
            {scheduleOp && (
                <Dialog open onOpenChange={() => setScheduleOp(null)}>
                    <DialogContent className="max-w-md">
                        <DialogHeader>
                            <DialogTitle>Programar OP — {scheduleOp.numero_op}</DialogTitle>
                        </DialogHeader>
                        <p className="text-xs text-muted-foreground">{scheduleOp.cliente_nome} · {scheduleOp.items?.[0]?.item || scheduleOp.project_name || "—"}</p>
                        <div className="space-y-3">
                            <div>
                                <Label>Linha *</Label>
                                <Select value={schedForm.linha_id} onValueChange={v => setSchedForm(f => ({ ...f, linha_id: v }))}>
                                    <SelectTrigger className="mt-1"><SelectValue placeholder="Selecionar linha…" /></SelectTrigger>
                                    <SelectContent>
                                        {activeLinhas.map(l => <SelectItem key={l.id} value={l.id}>{l.nome} ({TIPO_LINHA_LABEL[l.tipo] || l.tipo})</SelectItem>)}
                                    </SelectContent>
                                </Select>
                            </div>
                            <div className="grid grid-cols-2 gap-3">
                                <div><Label>Data *</Label><Input type="date" value={schedForm.data_inicio} onChange={e => setSchedForm(f => ({ ...f, data_inicio: e.target.value }))} className="mt-1" /></div>
                                <div><Label>Data Fim</Label><Input type="date" value={schedForm.data_fim} onChange={e => setSchedForm(f => ({ ...f, data_fim: e.target.value }))} className="mt-1" /></div>
                            </div>
                            <div className="grid grid-cols-2 gap-3">
                                <div><Label>Hora Início</Label><Input type="time" value={schedForm.hora_inicio} onChange={e => setSchedForm(f => ({ ...f, hora_inicio: e.target.value }))} className="mt-1" /></div>
                                <div><Label>Hora Fim</Label><Input type="time" value={schedForm.hora_fim} onChange={e => setSchedForm(f => ({ ...f, hora_fim: e.target.value }))} className="mt-1" /></div>
                            </div>
                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <Label>Turno</Label>
                                    <Select value={schedForm.turno} onValueChange={v => setSchedForm(f => ({ ...f, turno: v }))}>
                                        <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                                        <SelectContent>{Object.entries(TURNO_LABEL).map(([k,v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent>
                                    </Select>
                                </div>
                                <div><Label>Qtd Planejada</Label><Input type="number" value={schedForm.qtd_planejada} onChange={e => setSchedForm(f => ({ ...f, qtd_planejada: e.target.value }))} placeholder="0" className="mt-1" /></div>
                            </div>
                            <div><Label>Observações</Label><Input value={schedForm.observacoes} onChange={e => setSchedForm(f => ({ ...f, observacoes: e.target.value }))} placeholder="Opcional" className="mt-1" /></div>
                        </div>
                        <DialogFooter>
                            <Button variant="outline" onClick={() => setScheduleOp(null)} disabled={saving}>Cancelar</Button>
                            <Button onClick={handleSchedule} disabled={saving}>
                                {saving ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Calendar className="h-4 w-4 mr-1" />}
                                Confirmar
                            </Button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>
            )}

            {/* ══════════ Dialog: Lote Detail ══════════ */}
            {selectedLote && (
                <Dialog open onOpenChange={() => setSelectedLote(null)}>
                    <DialogContent className="max-w-md">
                        <DialogHeader>
                            <DialogTitle className="flex items-center gap-2">
                                <Layers className="h-5 w-5" /> Lote {selectedLote.numero_lote}
                            </DialogTitle>
                        </DialogHeader>
                        <div className="space-y-3 text-sm">
                            <div className="flex items-center gap-2"><LoteBadge status={selectedLote.status} /></div>
                            <div className="grid grid-cols-2 gap-2 text-xs">
                                <div><span className="text-muted-foreground">OP:</span> <span className="font-mono">{selectedLote.op_numero}</span></div>
                                <div><span className="text-muted-foreground">Pedido:</span> {selectedLote.pedido_numero || "—"}</div>
                                <div><span className="text-muted-foreground">Cliente:</span> {selectedLote.cliente_nome}</div>
                                <div><span className="text-muted-foreground">Produto:</span> {selectedLote.produto_nome}</div>
                                <div><span className="text-muted-foreground">Manipulação:</span> {formatDateBR(selectedLote.data_manipulacao)}</div>
                                <div><span className="text-muted-foreground">Envase:</span> {formatDateBR(selectedLote.data_envase) || "—"}</div>
                                <div><span className="text-muted-foreground">Qtd Plan.:</span> {selectedLote.qtd_planejada}</div>
                                <div><span className="text-muted-foreground">Qtd Prod.:</span> {selectedLote.qtd_produzida || 0}</div>
                            </div>
                            {selectedLote.observacoes && <p className="text-xs text-muted-foreground border-t border-border pt-2">{selectedLote.observacoes}</p>}
                            {(selectedLote.historico || []).length > 0 && (
                                <>
                                    <Separator />
                                    <div>
                                        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">Histórico</p>
                                        {selectedLote.historico.map((h, i) => (
                                            <div key={i} className="text-xs text-muted-foreground flex gap-2 flex-wrap">
                                                <span>{new Date(h.em).toLocaleString("pt-BR")}</span> · <span>{h.de ? `${LOTE_STATUS_LABEL[h.de] || h.de} → ${LOTE_STATUS_LABEL[h.para] || h.para}` : "Criado"}</span> · <span>{h.por}</span>
                                            </div>
                                        ))}
                                    </div>
                                </>
                            )}
                        </div>
                        <DialogFooter className="flex flex-wrap gap-2 justify-between">
                            <div className="flex gap-2">
                                {LOTE_NEXT[selectedLote.status] && (
                                    <Button size="sm" disabled={actionLoading} onClick={() => handleAdvanceLote(selectedLote)}>
                                        {actionLoading ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Play className="h-4 w-4 mr-1" />}
                                        {LOTE_STATUS_LABEL[LOTE_NEXT[selectedLote.status]]}
                                    </Button>
                                )}
                                {["planejado","em_preparo","em_envase"].includes(selectedLote.status) && (
                                    <Button size="sm" variant="outline" className="text-destructive border-destructive/30" disabled={actionLoading}
                                        onClick={() => handleCancelLote(selectedLote)}>
                                        <XCircle className="h-4 w-4 mr-1" /> Cancelar
                                    </Button>
                                )}
                            </div>
                            <Button variant="outline" onClick={() => setSelectedLote(null)}>Fechar</Button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>
            )}

            {/* ══════════ Dialog: Criar Lote ══════════ */}
            {showLoteForm && (
                <Dialog open onOpenChange={() => setShowLoteForm(false)}>
                    <DialogContent className="max-w-md">
                        <DialogHeader>
                            <DialogTitle>Criar Lote{loteFormOp ? ` — ${loteFormOp.numero_op}` : ""}</DialogTitle>
                        </DialogHeader>
                        {loteFormOp && <p className="text-xs text-muted-foreground">{loteFormOp.cliente_nome} · {loteFormOp.items?.[0]?.item || "—"}</p>}
                        <div className="space-y-3">
                            {!loteFormOp && (
                                <div>
                                    <Label>OP *</Label>
                                    <Select value={loteForm.op_id} onValueChange={v => setLoteForm(f => ({ ...f, op_id: v }))}>
                                        <SelectTrigger className="mt-1"><SelectValue placeholder="Selecionar OP…" /></SelectTrigger>
                                        <SelectContent>
                                            {opsPendentes.map(op => <SelectItem key={op.id} value={op.id}>{op.numero_op} — {op.cliente_nome}</SelectItem>)}
                                        </SelectContent>
                                    </Select>
                                </div>
                            )}
                            <div className="grid grid-cols-2 gap-3">
                                <div><Label>Data Manipulação *</Label><Input type="date" value={loteForm.data_manipulacao} onChange={e => setLoteForm(f => ({ ...f, data_manipulacao: e.target.value }))} className="mt-1" /></div>
                                <div><Label>Data Envase</Label><Input type="date" value={loteForm.data_envase} onChange={e => setLoteForm(f => ({ ...f, data_envase: e.target.value }))} className="mt-1" /></div>
                            </div>
                            <div><Label>Qtd Planejada</Label><Input type="number" value={loteForm.qtd_planejada} onChange={e => setLoteForm(f => ({ ...f, qtd_planejada: e.target.value }))} placeholder="0" className="mt-1" /></div>
                            <div><Label>Observações</Label><Input value={loteForm.observacoes} onChange={e => setLoteForm(f => ({ ...f, observacoes: e.target.value }))} placeholder="Opcional" className="mt-1" /></div>
                        </div>
                        <DialogFooter>
                            <Button variant="outline" onClick={() => setShowLoteForm(false)} disabled={saving}>Cancelar</Button>
                            <Button onClick={handleCreateLote} disabled={saving}>
                                {saving ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Layers className="h-4 w-4 mr-1" />}
                                Criar Lote
                            </Button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>
            )}

            {/* ══════════ Dialog: Linha form ══════════ */}
            <Dialog open={showLinhaForm} onOpenChange={v => { if (!v) setShowLinhaForm(false); }}>
                <DialogContent className="max-w-md">
                    <DialogHeader>
                        <DialogTitle>{editLinha ? "Editar Linha" : "Nova Linha de Produção"}</DialogTitle>
                    </DialogHeader>
                    <div className="space-y-3">
                        <div className="grid grid-cols-2 gap-3">
                            <div><Label>Nome *</Label><Input value={linhaForm.nome} onChange={e => setLinhaForm(f => ({ ...f, nome: e.target.value }))} placeholder="Ex: Linha 01" className="mt-1" /></div>
                            <div><Label>Código</Label><Input value={linhaForm.codigo} onChange={e => setLinhaForm(f => ({ ...f, codigo: e.target.value }))} placeholder="L01" className="mt-1" /></div>
                        </div>
                        <div>
                            <Label>Tipo</Label>
                            <Select value={linhaForm.tipo} onValueChange={v => setLinhaForm(f => ({ ...f, tipo: v }))}>
                                <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                                <SelectContent>{Object.entries(TIPO_LINHA_LABEL).map(([k,v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent>
                            </Select>
                        </div>
                        <div className="grid grid-cols-2 gap-3">
                            <div><Label>Cap. Diária</Label><Input type="number" value={linhaForm.capacidade_diaria} onChange={e => setLinhaForm(f => ({ ...f, capacidade_diaria: e.target.value }))} placeholder="0" className="mt-1" /></div>
                            <div>
                                <Label>Unidade</Label>
                                <Select value={linhaForm.unidade_capacidade} onValueChange={v => setLinhaForm(f => ({ ...f, unidade_capacidade: v }))}>
                                    <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                                    <SelectContent>{["kg","L","un","cx","lotes"].map(u => <SelectItem key={u} value={u}>{u}</SelectItem>)}</SelectContent>
                                </Select>
                            </div>
                        </div>
                        <div><Label>Setup (minutos)</Label><Input type="number" value={linhaForm.setup_minutos} onChange={e => setLinhaForm(f => ({ ...f, setup_minutos: e.target.value }))} className="mt-1" /></div>
                        <div><Label>Observações</Label><Input value={linhaForm.observacoes} onChange={e => setLinhaForm(f => ({ ...f, observacoes: e.target.value }))} placeholder="Opcional" className="mt-1" /></div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setShowLinhaForm(false)} disabled={saving}>Cancelar</Button>
                        <Button onClick={handleSaveLinha} disabled={saving}>
                            {saving ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Factory className="h-4 w-4 mr-1" />}
                            {editLinha ? "Salvar" : "Criar Linha"}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
