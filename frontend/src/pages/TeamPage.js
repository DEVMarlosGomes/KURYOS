import { useState, useEffect, useMemo } from "react";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { Separator } from "@/components/ui/separator";
import { toast } from "sonner";
import {
    UserPlus, Shield, Trash2, Mail, Copy, Plus, Pencil, ToggleLeft, ToggleRight,
    KeyRound, Users, Search, X, Check, AlertTriangle, MoreHorizontal,
    Crown, UserCheck, ChevronDown
} from "lucide-react";

const ROLE_OPTIONS = [
    { value: "admin",               label: "Admin",           color: "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900" },
    { value: "gestor",              label: "Gestor",          color: "bg-blue-600 text-white" },
    { value: "lider_pd",            label: "Líder P&D",       color: "bg-pink-600 text-white" },
    { value: "formulador",          label: "Formulador",      color: "bg-purple-600 text-white" },
    { value: "qa",                  label: "Qualidade",       color: "bg-orange-500 text-white" },
    { value: "engenharia_produto",  label: "Eng. Produto",    color: "bg-cyan-600 text-white" },
    { value: "vendedor",            label: "Vendedor",        color: "bg-green-600 text-white" },
    { value: "sales_ops",           label: "Sales Ops",       color: "bg-yellow-500 text-black" },
    { value: "sucesso_cliente",     label: "Sucesso Cliente", color: "bg-emerald-600 text-white" },
];

const ROLE_MAP = Object.fromEntries(ROLE_OPTIONS.map(r => [r.value, r]));

function RoleBadge({ role, className = "" }) {
    const r = ROLE_MAP[role];
    if (!r) return <Badge variant="outline" className={className}>{role}</Badge>;
    return (
        <span className={`inline-flex items-center gap-1 text-[11px] font-semibold px-2.5 py-0.5 rounded-full ${r.color} ${className}`}>
            <Shield className="h-2.5 w-2.5" />
            {r.label}
        </span>
    );
}

function AvatarCircle({ name, size = "md", className = "" }) {
    const initials = (name || "?").split(" ").map(w => w[0]).slice(0, 2).join("").toUpperCase();
    const colors = [
        "from-violet-500 to-purple-600",
        "from-blue-500 to-cyan-600",
        "from-green-500 to-emerald-600",
        "from-orange-500 to-amber-600",
        "from-pink-500 to-rose-600",
        "from-indigo-500 to-blue-600",
    ];
    const color = colors[(name || "?").charCodeAt(0) % colors.length];
    const sz = size === "lg" ? "w-16 h-16 text-xl" : size === "sm" ? "w-8 h-8 text-xs" : "w-11 h-11 text-sm";
    return (
        <div className={`${sz} rounded-full bg-gradient-to-br ${color} flex items-center justify-center font-bold text-white shrink-0 ${className}`}>
            {initials}
        </div>
    );
}

function RoleSelect({ value, onChange, disabled, placeholder }) {
    return (
        <Select value={value} onValueChange={onChange} disabled={disabled}>
            <SelectTrigger>
                <SelectValue placeholder={placeholder || "Selecione uma role"} />
            </SelectTrigger>
            <SelectContent>
                {ROLE_OPTIONS.map(r => (
                    <SelectItem key={r.value} value={r.value}>
                        <div className="flex items-center gap-2">
                            <span className={`inline-block w-2 h-2 rounded-full ${r.color.split(" ")[0]}`} />
                            {r.label}
                        </div>
                    </SelectItem>
                ))}
            </SelectContent>
        </Select>
    );
}

function CopyButton({ text, label }) {
    const [copied, setCopied] = useState(false);
    const handleCopy = () => {
        if (navigator.clipboard?.writeText) {
            navigator.clipboard.writeText(text).then(() => {
                setCopied(true);
                setTimeout(() => setCopied(false), 2000);
            }).catch(() => window.prompt("Copie manualmente:", text));
        } else {
            window.prompt("Copie manualmente:", text);
        }
    };
    return (
        <button onClick={handleCopy}
            className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors">
            {copied ? <Check className="h-3 w-3 text-green-500" /> : <Copy className="h-3 w-3" />}
            {copied ? "Copiado!" : (label || "Copiar")}
        </button>
    );
}

function CredentialBox({ email, password, label }) {
    return (
        <div className="rounded-lg border border-border bg-muted/40 p-4 space-y-3">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">{label || "Credenciais de Acesso"}</p>
            <div className="space-y-2">
                <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">Email</span>
                    <div className="flex items-center gap-2">
                        <code className="text-xs font-mono">{email}</code>
                        <CopyButton text={email} />
                    </div>
                </div>
                <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">Senha temp.</span>
                    <div className="flex items-center gap-2">
                        <code className="text-xs font-mono font-bold tracking-wider">{password}</code>
                        <CopyButton text={password} />
                    </div>
                </div>
            </div>
            <div className="pt-1">
                <CopyButton text={`Email: ${email}\nSenha: ${password}`} label="Copiar tudo" />
            </div>
        </div>
    );
}

// ─── MODALS ───────────────────────────────────────────────────────────────────

function InviteModal({ open, onClose, onSuccess }) {
    const [step, setStep] = useState("form"); // "form" | "success"
    const [form, setForm] = useState({ email: "", name: "", role: "vendedor" });
    const [result, setResult] = useState(null);
    const [loading, setLoading] = useState(false);

    const reset = () => { setStep("form"); setForm({ email: "", name: "", role: "vendedor" }); setResult(null); };

    const handleClose = () => { reset(); onClose(); };

    const handleSubmit = async () => {
        if (!form.email || !form.name) return;
        setLoading(true);
        try {
            const { data } = await api.post("/users/invite", form);
            setResult(data);
            setStep("success");
            toast.success(`${data.name} convidado com sucesso!`);
            onSuccess?.();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Erro ao convidar");
        } finally { setLoading(false); }
    };

    return (
        <Dialog open={open} onOpenChange={handleClose}>
            <DialogContent className="sm:max-w-md">
                <DialogHeader>
                    <DialogTitle className="font-heading flex items-center gap-2">
                        <UserPlus className="h-5 w-5 text-primary" />
                        {step === "form" ? "Convidar Membro" : "Membro Convidado!"}
                    </DialogTitle>
                    {step === "form" && (
                        <DialogDescription>
                            O novo membro receberá credenciais de acesso temporárias.
                        </DialogDescription>
                    )}
                </DialogHeader>

                {step === "form" ? (
                    <div className="space-y-4 py-2">
                        <div className="space-y-1.5">
                            <Label>Nome completo *</Label>
                            <Input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                                placeholder="Ex: João Silva" autoFocus />
                        </div>
                        <div className="space-y-1.5">
                            <Label>Email *</Label>
                            <Input type="email" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                                placeholder="joao@empresa.com" />
                        </div>
                        <div className="space-y-1.5">
                            <Label>Perfil de Acesso</Label>
                            <RoleSelect value={form.role} onChange={v => setForm(f => ({ ...f, role: v }))} />
                        </div>
                    </div>
                ) : (
                    <div className="space-y-4 py-2">
                        <div className="flex items-center gap-3 p-3 rounded-lg bg-green-50 dark:bg-green-950/30 border border-green-200 dark:border-green-800">
                            <div className="w-8 h-8 rounded-full bg-green-500 flex items-center justify-center shrink-0">
                                <Check className="h-4 w-4 text-white" />
                            </div>
                            <div>
                                <p className="text-sm font-semibold">{result?.name}</p>
                                <p className="text-xs text-muted-foreground">Convidado como <RoleBadge role={result?.role} className="inline" /></p>
                            </div>
                        </div>
                        <CredentialBox email={result?.email} password={result?.temp_password}
                            label="Compartilhe estas credenciais com o novo membro" />
                        <p className="text-xs text-muted-foreground text-center">
                            Oriente o membro a trocar a senha após o primeiro acesso.
                        </p>
                    </div>
                )}

                <DialogFooter>
                    {step === "form" ? (
                        <>
                            <Button variant="outline" onClick={handleClose}>Cancelar</Button>
                            <Button onClick={handleSubmit} disabled={loading || !form.email || !form.name}>
                                {loading ? "Convidando..." : "Enviar Convite"}
                            </Button>
                        </>
                    ) : (
                        <>
                            <Button variant="outline" onClick={() => { reset(); }}>Convidar Outro</Button>
                            <Button onClick={handleClose}>Concluir</Button>
                        </>
                    )}
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

function EditUserModal({ open, onClose, targetUser, onSuccess }) {
    const [form, setForm] = useState({ name: "", email: "", role: "" });
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (targetUser) setForm({ name: targetUser.name || "", email: targetUser.email || "", role: targetUser.role || "vendedor" });
    }, [targetUser]);

    const handleSubmit = async () => {
        setLoading(true);
        try {
            await api.put(`/users/${targetUser.id}`, form);
            toast.success("Usuário atualizado com sucesso!");
            onSuccess?.();
            onClose();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Erro ao atualizar");
        } finally { setLoading(false); }
    };

    return (
        <Dialog open={open} onOpenChange={onClose}>
            <DialogContent className="sm:max-w-md">
                <DialogHeader>
                    <DialogTitle className="font-heading flex items-center gap-2">
                        <Pencil className="h-5 w-5 text-primary" />
                        Editar Membro
                    </DialogTitle>
                </DialogHeader>

                {targetUser && (
                    <div className="flex items-center gap-3 py-2">
                        <AvatarCircle name={targetUser.name} size="sm" />
                        <div>
                            <p className="text-sm font-medium">{targetUser.name}</p>
                            <p className="text-xs text-muted-foreground">{targetUser.email}</p>
                        </div>
                    </div>
                )}

                <Separator />

                <div className="space-y-4 py-2">
                    <div className="space-y-1.5">
                        <Label>Nome</Label>
                        <Input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
                    </div>
                    <div className="space-y-1.5">
                        <Label>Email</Label>
                        <Input type="email" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} />
                    </div>
                    <div className="space-y-1.5">
                        <Label>Perfil de Acesso</Label>
                        <RoleSelect value={form.role} onChange={v => setForm(f => ({ ...f, role: v }))} />
                    </div>
                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={onClose}>Cancelar</Button>
                    <Button onClick={handleSubmit} disabled={loading || !form.name || !form.email}>
                        {loading ? "Salvando..." : "Salvar Alterações"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

function ResetPasswordModal({ open, onClose, targetUser, onSuccess }) {
    const [step, setStep] = useState("confirm"); // "confirm" | "result"
    const [result, setResult] = useState(null);
    const [loading, setLoading] = useState(false);

    useEffect(() => { if (!open) { setStep("confirm"); setResult(null); } }, [open]);

    const handleReset = async () => {
        setLoading(true);
        try {
            const { data } = await api.post(`/users/${targetUser.id}/reset-password`);
            setResult(data);
            setStep("result");
            toast.success("Senha redefinida!");
            onSuccess?.();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Erro ao redefinir");
        } finally { setLoading(false); }
    };

    return (
        <Dialog open={open} onOpenChange={onClose}>
            <DialogContent className="sm:max-w-md">
                <DialogHeader>
                    <DialogTitle className="font-heading flex items-center gap-2">
                        <KeyRound className="h-5 w-5 text-amber-500" />
                        {step === "confirm" ? "Redefinir Senha" : "Senha Redefinida!"}
                    </DialogTitle>
                </DialogHeader>

                {step === "confirm" ? (
                    <div className="space-y-4 py-2">
                        <div className="flex gap-3 p-4 rounded-lg bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800">
                            <AlertTriangle className="h-5 w-5 text-amber-500 shrink-0 mt-0.5" />
                            <div className="space-y-1">
                                <p className="text-sm font-medium">Confirmar redefinição de senha?</p>
                                <p className="text-xs text-muted-foreground">
                                    A senha atual de <strong>{targetUser?.name}</strong> será substituída por uma senha temporária. O usuário precisará trocar no próximo acesso.
                                </p>
                            </div>
                        </div>
                    </div>
                ) : (
                    <div className="space-y-4 py-2">
                        <CredentialBox email={result?.email} password={result?.temp_password}
                            label="Nova senha temporária — compartilhe com o membro" />
                    </div>
                )}

                <DialogFooter>
                    {step === "confirm" ? (
                        <>
                            <Button variant="outline" onClick={onClose}>Cancelar</Button>
                            <Button variant="destructive" onClick={handleReset} disabled={loading}>
                                {loading ? "Redefinindo..." : "Redefinir Senha"}
                            </Button>
                        </>
                    ) : (
                        <Button onClick={onClose}>Fechar</Button>
                    )}
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

function DeleteUserModal({ open, onClose, targetUser, onSuccess }) {
    const [loading, setLoading] = useState(false);
    const [confirm, setConfirm] = useState("");

    useEffect(() => { if (!open) setConfirm(""); }, [open]);

    const handleDelete = async () => {
        setLoading(true);
        try {
            await api.delete(`/users/${targetUser.id}`);
            toast.success(`${targetUser.name} removido da equipe.`);
            onSuccess?.();
            onClose();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Erro ao remover");
        } finally { setLoading(false); }
    };

    return (
        <Dialog open={open} onOpenChange={onClose}>
            <DialogContent className="sm:max-w-md">
                <DialogHeader>
                    <DialogTitle className="font-heading flex items-center gap-2 text-destructive">
                        <Trash2 className="h-5 w-5" />
                        Remover Membro
                    </DialogTitle>
                </DialogHeader>

                <div className="space-y-4 py-2">
                    <div className="flex gap-3 p-4 rounded-lg bg-destructive/5 border border-destructive/20">
                        <AlertTriangle className="h-5 w-5 text-destructive shrink-0 mt-0.5" />
                        <div className="space-y-1">
                            <p className="text-sm font-medium">Esta ação não pode ser desfeita.</p>
                            <p className="text-xs text-muted-foreground">
                                <strong>{targetUser?.name}</strong> perderá acesso imediato ao sistema. Registros criados por ele serão mantidos.
                            </p>
                        </div>
                    </div>
                    <div className="space-y-1.5">
                        <Label className="text-xs text-muted-foreground">
                            Digite <strong className="text-foreground">{targetUser?.name?.split(" ")[0]}</strong> para confirmar
                        </Label>
                        <Input value={confirm} onChange={e => setConfirm(e.target.value)}
                            placeholder="Nome do membro..." />
                    </div>
                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={onClose}>Cancelar</Button>
                    <Button variant="destructive" onClick={handleDelete}
                        disabled={loading || confirm !== (targetUser?.name?.split(" ")[0] || "")}>
                        {loading ? "Removendo..." : "Remover Membro"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

// ─── MEMBER CARD ─────────────────────────────────────────────────────────────

function MemberCard({ member, isCurrentUser, isAdmin, onEdit, onResetPassword, onDelete }) {
    const [menuOpen, setMenuOpen] = useState(false);

    return (
        <div className="group relative bg-card border border-border rounded-xl p-5 flex flex-col gap-4 hover:border-border/80 hover:shadow-md transition-all duration-200">
            {/* Header */}
            <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3 min-w-0">
                    <div className="relative">
                        <AvatarCircle name={member.name} size="md" />
                        {isCurrentUser && (
                            <span className="absolute -bottom-1 -right-1 w-4 h-4 rounded-full bg-primary flex items-center justify-center ring-2 ring-card">
                                <UserCheck className="h-2.5 w-2.5 text-primary-foreground" />
                            </span>
                        )}
                    </div>
                    <div className="min-w-0">
                        <div className="flex items-center gap-1.5 flex-wrap">
                            <p className="text-sm font-semibold truncate">{member.name}</p>
                            {isCurrentUser && (
                                <span className="text-[10px] font-medium text-primary bg-primary/10 px-1.5 py-0.5 rounded-full">Você</span>
                            )}
                        </div>
                        <p className="text-xs text-muted-foreground truncate">{member.email}</p>
                    </div>
                </div>

                {isAdmin && !isCurrentUser && (
                    <div className="relative">
                        <button
                            onClick={() => setMenuOpen(o => !o)}
                            className="w-7 h-7 rounded-md flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted transition-colors opacity-0 group-hover:opacity-100"
                        >
                            <MoreHorizontal className="h-4 w-4" />
                        </button>
                        {menuOpen && (
                            <>
                                <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
                                <div className="absolute right-0 top-8 z-20 w-44 bg-popover border border-border rounded-lg shadow-lg py-1 text-sm">
                                    <button onClick={() => { setMenuOpen(false); onEdit(member); }}
                                        className="w-full flex items-center gap-2 px-3 py-2 hover:bg-muted text-left">
                                        <Pencil className="h-3.5 w-3.5 text-muted-foreground" /> Editar dados
                                    </button>
                                    <button onClick={() => { setMenuOpen(false); onResetPassword(member); }}
                                        className="w-full flex items-center gap-2 px-3 py-2 hover:bg-muted text-left">
                                        <KeyRound className="h-3.5 w-3.5 text-amber-500" /> Redefinir senha
                                    </button>
                                    <div className="my-1 border-t border-border" />
                                    <button onClick={() => { setMenuOpen(false); onDelete(member); }}
                                        className="w-full flex items-center gap-2 px-3 py-2 hover:bg-destructive/10 text-destructive text-left">
                                        <Trash2 className="h-3.5 w-3.5" /> Remover
                                    </button>
                                </div>
                            </>
                        )}
                    </div>
                )}
            </div>

            {/* Role */}
            <div className="flex items-center justify-between">
                <RoleBadge role={member.role} />
                {member.created_at && (
                    <span className="text-[10px] text-muted-foreground">
                        {new Date(member.created_at).toLocaleDateString("pt-BR", { month: "short", year: "numeric" })}
                    </span>
                )}
            </div>
        </div>
    );
}

// ─── LEAD SOURCES SECTION ─────────────────────────────────────────────────────

function LeadSourcesSection() {
    const [sources, setSources] = useState([]);
    const [loading, setLoading] = useState(false);
    const [showAdd, setShowAdd] = useState(false);
    const [addForm, setAddForm] = useState({ nome: "", valor: "", grupo: "" });
    const [editingId, setEditingId] = useState(null);
    const [editForm, setEditForm] = useState({ nome: "", grupo: "" });

    const load = async () => {
        setLoading(true);
        try { const { data } = await api.get("/crm/config/lead-sources"); setSources(data); } catch {}
        finally { setLoading(false); }
    };

    useEffect(() => { load(); }, []);

    const handleCreate = async () => {
        if (!addForm.nome || !addForm.valor) return;
        try {
            await api.post("/crm/config/lead-sources", addForm);
            toast.success("Canal criado");
            setShowAdd(false); setAddForm({ nome: "", valor: "", grupo: "" }); load();
        } catch (e) { toast.error(e.response?.data?.detail || "Erro ao criar"); }
    };

    const handleUpdate = async (id) => {
        try {
            await api.patch(`/crm/config/lead-sources/${id}`, editForm);
            toast.success("Canal atualizado"); setEditingId(null); load();
        } catch (e) { toast.error(e.response?.data?.detail || "Erro"); }
    };

    const handleToggle = async (src) => {
        try { await api.patch(`/crm/config/lead-sources/${src.id}`, { ativo: !src.ativo }); load(); }
        catch (e) { toast.error(e.response?.data?.detail || "Erro"); }
    };

    return (
        <div>
            <div className="flex items-center justify-between mb-4">
                <div>
                    <h2 className="text-lg font-heading font-semibold">Canais de Origem do Lead</h2>
                    <p className="text-sm text-muted-foreground">Gerencie os canais que alimentam o pipeline comercial</p>
                </div>
                <Button size="sm" variant="outline" onClick={() => setShowAdd(true)}>
                    <Plus className="h-3.5 w-3.5 mr-1.5" /> Novo Canal
                </Button>
            </div>

            {loading ? (
                <div className="space-y-2">
                    {[1, 2, 3].map(i => <div key={i} className="h-10 bg-muted animate-pulse rounded-lg" />)}
                </div>
            ) : sources.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground text-sm">Nenhum canal cadastrado</div>
            ) : (
                <div className="space-y-1.5">
                    {sources.map(src => (
                        <div key={src.id}
                            className={`flex items-center gap-3 px-3 py-2.5 rounded-lg border text-sm transition-opacity ${!src.ativo ? "opacity-50" : "border-border bg-card"}`}>
                            <code className="text-xs bg-muted px-2 py-0.5 rounded font-mono shrink-0">{src.valor}</code>
                            {editingId === src.id ? (
                                <>
                                    <Input className="h-7 text-xs flex-1" value={editForm.nome}
                                        onChange={e => setEditForm(f => ({ ...f, nome: e.target.value }))} />
                                    <Input className="h-7 text-xs w-28" value={editForm.grupo} placeholder="grupo"
                                        onChange={e => setEditForm(f => ({ ...f, grupo: e.target.value }))} />
                                    <Button size="sm" className="h-7 text-xs px-2" onClick={() => handleUpdate(src.id)}>
                                        <Check className="h-3 w-3" />
                                    </Button>
                                    <Button size="sm" variant="ghost" className="h-7 text-xs px-2" onClick={() => setEditingId(null)}>
                                        <X className="h-3 w-3" />
                                    </Button>
                                </>
                            ) : (
                                <>
                                    <span className="flex-1 font-medium">{src.nome}</span>
                                    {src.grupo && <span className="text-xs text-muted-foreground">{src.grupo}</span>}
                                    <button className="text-muted-foreground hover:text-foreground transition-colors p-1"
                                        onClick={() => { setEditingId(src.id); setEditForm({ nome: src.nome, grupo: src.grupo || "" }); }}>
                                        <Pencil className="h-3.5 w-3.5" />
                                    </button>
                                    <button className={`p-1 transition-colors ${src.ativo ? "text-green-500 hover:text-green-400" : "text-muted-foreground hover:text-foreground"}`}
                                        onClick={() => handleToggle(src)}>
                                        {src.ativo ? <ToggleRight className="h-4 w-4" /> : <ToggleLeft className="h-4 w-4" />}
                                    </button>
                                </>
                            )}
                        </div>
                    ))}
                </div>
            )}

            <Dialog open={showAdd} onOpenChange={setShowAdd}>
                <DialogContent className="sm:max-w-sm">
                    <DialogHeader>
                        <DialogTitle className="font-heading">Novo Canal de Origem</DialogTitle>
                    </DialogHeader>
                    <div className="space-y-4 py-2">
                        <div className="space-y-1.5">
                            <Label>Nome de exibição *</Label>
                            <Input value={addForm.nome} onChange={e => setAddForm(f => ({ ...f, nome: e.target.value }))}
                                placeholder="Ex: Indicação de parceiro" autoFocus />
                        </div>
                        <div className="space-y-1.5">
                            <Label>Slug / Valor * <span className="text-xs text-muted-foreground font-normal">(imutável)</span></Label>
                            <Input value={addForm.valor}
                                onChange={e => setAddForm(f => ({ ...f, valor: e.target.value.toLowerCase().replace(/\s+/g, "_").replace(/[^a-z0-9_]/g, "") }))}
                                placeholder="indicacao_parceiro" />
                        </div>
                        <div className="space-y-1.5">
                            <Label>Grupo <span className="text-xs text-muted-foreground font-normal">(opcional)</span></Label>
                            <Input value={addForm.grupo} onChange={e => setAddForm(f => ({ ...f, grupo: e.target.value }))}
                                placeholder="Ex: indicacao" />
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setShowAdd(false)}>Cancelar</Button>
                        <Button onClick={handleCreate} disabled={!addForm.nome || !addForm.valor}>Criar Canal</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}

// ─── MAIN PAGE ────────────────────────────────────────────────────────────────

export default function TeamPage() {
    const { user: authUser } = useAuth();
    const [users, setUsers] = useState([]);
    const [loading, setLoading] = useState(true);
    const [search, setSearch] = useState("");
    const [roleFilter, setRoleFilter] = useState("all");

    // Modals
    const [inviteOpen, setInviteOpen] = useState(false);
    const [editTarget, setEditTarget] = useState(null);
    const [resetTarget, setResetTarget] = useState(null);
    const [deleteTarget, setDeleteTarget] = useState(null);

    const isAdmin = authUser?.role === "admin";

    const loadUsers = async () => {
        try {
            const { data } = await api.get("/users");
            setUsers(data);
        } catch {} finally { setLoading(false); }
    };

    useEffect(() => { loadUsers(); }, []);

    const filtered = useMemo(() => {
        let list = users;
        if (roleFilter !== "all") list = list.filter(u => u.role === roleFilter);
        if (search.trim()) {
            const q = search.toLowerCase();
            list = list.filter(u =>
                u.name?.toLowerCase().includes(q) || u.email?.toLowerCase().includes(q)
            );
        }
        return list;
    }, [users, search, roleFilter]);

    const stats = useMemo(() => {
        const byRole = {};
        users.forEach(u => { byRole[u.role] = (byRole[u.role] || 0) + 1; });
        const admins = (byRole["admin"] || 0);
        const topRole = Object.entries(byRole).sort((a, b) => b[1] - a[1])[0];
        return { total: users.length, admins, topRole, byRole };
    }, [users]);

    if (loading) return (
        <div className="p-8 page-enter">
            <div className="animate-pulse space-y-6">
                <div className="h-9 w-48 bg-muted rounded-lg" />
                <div className="grid grid-cols-3 gap-4">
                    {[1, 2, 3].map(i => <div key={i} className="h-24 bg-muted rounded-xl" />)}
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    {[1, 2, 3, 4, 5, 6].map(i => <div key={i} className="h-36 bg-muted rounded-xl" />)}
                </div>
            </div>
        </div>
    );

    return (
        <div className="p-6 lg:p-8 page-enter max-w-7xl mx-auto space-y-8">
            {/* ── Header ── */}
            <div className="flex items-start justify-between gap-4 flex-wrap">
                <div>
                    <h1 className="text-3xl font-heading font-semibold tracking-tight">Equipe</h1>
                    <p className="text-sm text-muted-foreground mt-1">
                        Gerencie os membros e perfis de acesso da organização
                    </p>
                </div>
                {isAdmin && (
                    <Button onClick={() => setInviteOpen(true)} className="shrink-0">
                        <UserPlus className="h-4 w-4 mr-2" /> Convidar Membro
                    </Button>
                )}
            </div>

            {/* ── Stats ── */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="rounded-xl border border-border bg-card p-4">
                    <p className="text-xs text-muted-foreground uppercase tracking-wider font-medium mb-1">Total</p>
                    <p className="text-2xl font-bold font-heading">{stats.total}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">membros ativos</p>
                </div>
                <div className="rounded-xl border border-border bg-card p-4">
                    <p className="text-xs text-muted-foreground uppercase tracking-wider font-medium mb-1">Admins</p>
                    <p className="text-2xl font-bold font-heading">{stats.admins}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">com acesso total</p>
                </div>
                {ROLE_OPTIONS.slice(2, 4).map(r => (
                    <div key={r.value} className="rounded-xl border border-border bg-card p-4">
                        <p className="text-xs text-muted-foreground uppercase tracking-wider font-medium mb-1">{r.label}</p>
                        <p className="text-2xl font-bold font-heading">{stats.byRole[r.value] || 0}</p>
                        <p className="text-xs text-muted-foreground mt-0.5">membros</p>
                    </div>
                ))}
            </div>

            {/* ── Filters ── */}
            <div className="flex flex-col sm:flex-row gap-3">
                <div className="relative flex-1 max-w-sm">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input value={search} onChange={e => setSearch(e.target.value)}
                        placeholder="Buscar por nome ou email..."
                        className="pl-9 pr-8" />
                    {search && (
                        <button onClick={() => setSearch("")}
                            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
                            <X className="h-3.5 w-3.5" />
                        </button>
                    )}
                </div>
                <Select value={roleFilter} onValueChange={setRoleFilter}>
                    <SelectTrigger className="w-44">
                        <SelectValue placeholder="Todos os perfis" />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="all">Todos os perfis</SelectItem>
                        {ROLE_OPTIONS.map(r => (
                            <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>
                        ))}
                    </SelectContent>
                </Select>
            </div>

            {/* ── Member Grid ── */}
            {filtered.length === 0 ? (
                <div className="text-center py-16 text-muted-foreground">
                    <Users className="h-10 w-10 mx-auto mb-3 opacity-30" />
                    <p className="font-medium">Nenhum membro encontrado</p>
                    <p className="text-sm mt-1">Tente ajustar os filtros de busca</p>
                </div>
            ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    {filtered.map(u => (
                        <MemberCard
                            key={u.id}
                            member={u}
                            isCurrentUser={u.id === authUser?.id}
                            isAdmin={isAdmin}
                            onEdit={setEditTarget}
                            onResetPassword={setResetTarget}
                            onDelete={setDeleteTarget}
                        />
                    ))}
                </div>
            )}

            {/* ── Lead Sources ── */}
            {isAdmin && (
                <>
                    <Separator />
                    <LeadSourcesSection />
                </>
            )}

            {/* ── Modals ── */}
            <InviteModal
                open={inviteOpen}
                onClose={() => setInviteOpen(false)}
                onSuccess={loadUsers}
            />
            <EditUserModal
                open={!!editTarget}
                onClose={() => setEditTarget(null)}
                targetUser={editTarget}
                onSuccess={loadUsers}
            />
            <ResetPasswordModal
                open={!!resetTarget}
                onClose={() => setResetTarget(null)}
                targetUser={resetTarget}
                onSuccess={loadUsers}
            />
            <DeleteUserModal
                open={!!deleteTarget}
                onClose={() => setDeleteTarget(null)}
                targetUser={deleteTarget}
                onSuccess={loadUsers}
            />
        </div>
    );
}
