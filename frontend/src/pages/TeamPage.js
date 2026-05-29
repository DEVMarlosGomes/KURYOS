import { useState, useEffect } from "react";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Separator } from "@/components/ui/separator";
import { toast } from "sonner";
import { UserPlus, Shield, Trash2, Mail, Copy, Plus, Pencil, ToggleLeft, ToggleRight } from "lucide-react";

const ROLE_LABELS = { admin: "Admin", gestor: "Gestor", vendedor: "Vendedor" };
const ROLE_COLORS = { admin: "bg-primary text-primary-foreground", gestor: "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300", vendedor: "bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300" };

export default function TeamPage() {
    const { user } = useAuth();
    const [users, setUsers] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showInvite, setShowInvite] = useState(false);
    const [inviteForm, setInviteForm] = useState({ email: "", name: "", role: "vendedor" });
    const [inviteResult, setInviteResult] = useState(null);
    const [emailLogs, setEmailLogs] = useState([]);
    const [leadSources, setLeadSources] = useState([]);
    const [lsLoading, setLsLoading] = useState(false);
    const [showAddSource, setShowAddSource] = useState(false);
    const [addSourceForm, setAddSourceForm] = useState({ nome: "", valor: "", grupo: "" });
    const [editingSource, setEditingSource] = useState(null);
    const [editSourceForm, setEditSourceForm] = useState({ nome: "", grupo: "" });

    useEffect(() => {
        loadUsers();
        loadEmailLogs();
        loadLeadSources();
    }, []);

    const loadUsers = async () => {
        try {
            const { data } = await api.get("/users");
            setUsers(data);
        } catch {} finally { setLoading(false); }
    };

    const loadEmailLogs = async () => {
        try {
            const { data } = await api.get("/email-logs");
            setEmailLogs(data);
        } catch {}
    };

    const inviteUser = async () => {
        if (!inviteForm.email || !inviteForm.name) return;
        try {
            const { data } = await api.post("/users/invite", inviteForm);
            setInviteResult(data);
            toast.success(`${data.name} convidado como ${ROLE_LABELS[data.role]}`);
            loadUsers();
            loadEmailLogs();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Erro ao convidar");
        }
    };

    const changeRole = async (userId, newRole) => {
        try {
            await api.put(`/users/${userId}/role`, { role: newRole });
            toast.success("Role atualizada");
            loadUsers();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Erro ao atualizar role");
        }
    };

    const removeUser = async (userId, userName) => {
        if (!window.confirm(`Remover ${userName} da equipe?`)) return;
        try {
            await api.delete(`/users/${userId}`);
            toast.success("Usuario removido");
            loadUsers();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Erro ao remover");
        }
    };

    const loadLeadSources = async () => {
        setLsLoading(true);
        try {
            const { data } = await api.get("/crm/config/lead-sources");
            setLeadSources(data);
        } catch {} finally { setLsLoading(false); }
    };

    const createLeadSource = async () => {
        if (!addSourceForm.nome || !addSourceForm.valor) return;
        try {
            await api.post("/crm/config/lead-sources", addSourceForm);
            toast.success("Canal criado");
            setShowAddSource(false);
            setAddSourceForm({ nome: "", valor: "", grupo: "" });
            loadLeadSources();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Erro ao criar");
        }
    };

    const updateLeadSource = async (id, patch) => {
        try {
            await api.patch(`/crm/config/lead-sources/${id}`, patch);
            toast.success("Atualizado");
            setEditingSource(null);
            loadLeadSources();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Erro ao atualizar");
        }
    };

    const toggleLeadSource = async (src) => {
        try {
            await api.patch(`/crm/config/lead-sources/${src.id}`, { ativo: !src.ativo });
            loadLeadSources();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Erro");
        }
    };

    const isAdmin = user?.role === "admin";

    if (loading) return (
        <div className="p-8 page-enter" data-testid="team-loading">
            <div className="animate-pulse space-y-4">
                <div className="h-8 w-40 bg-muted rounded" />
                {[1,2,3].map(i => <div key={i} className="h-16 bg-muted rounded-lg" />)}
            </div>
        </div>
    );

    return (
        <div className="p-8 page-enter" data-testid="team-page">
            <div className="flex items-center justify-between mb-6">
                <div>
                    <h1 className="text-3xl font-heading font-semibold tracking-tight">Equipe</h1>
                    <p className="text-sm text-muted-foreground mt-1">{users.length} membros</p>
                </div>
                {isAdmin && (
                    <Button onClick={() => { setShowInvite(true); setInviteResult(null); setInviteForm({ email: "", name: "", role: "vendedor" }); }}
                        data-testid="invite-btn">
                        <UserPlus className="h-4 w-4 mr-2" /> Convidar
                    </Button>
                )}
            </div>

            <div className="space-y-2 mb-8">
                {users.map(u => (
                    <Card key={u.id} data-testid={`user-${u.id}`}>
                        <CardContent className="p-4 flex items-center gap-4">
                            <div className="w-10 h-10 rounded-full bg-muted flex items-center justify-center text-sm font-heading font-semibold">
                                {u.name?.charAt(0)?.toUpperCase()}
                            </div>
                            <div className="flex-1 min-w-0">
                                <p className="text-sm font-body font-medium">{u.name}</p>
                                <p className="text-xs text-muted-foreground">{u.email}</p>
                            </div>
                            <Badge className={`${ROLE_COLORS[u.role] || ""} text-xs`} data-testid={`role-badge-${u.id}`}>
                                <Shield className="h-3 w-3 mr-1" />{ROLE_LABELS[u.role] || u.role}
                            </Badge>
                            {isAdmin && u.id !== user.id && (
                                <div className="flex items-center gap-2">
                                    <Select value={u.role} onValueChange={(v) => changeRole(u.id, v)}>
                                        <SelectTrigger className="w-28 h-8 text-xs" data-testid={`role-select-${u.id}`}>
                                            <SelectValue />
                                        </SelectTrigger>
                                        <SelectContent>
                                            <SelectItem value="admin">Admin</SelectItem>
                                            <SelectItem value="gestor">Gestor</SelectItem>
                                            <SelectItem value="vendedor">Vendedor</SelectItem>
                                        </SelectContent>
                                    </Select>
                                    <Button variant="ghost" size="icon" className="h-8 w-8"
                                        onClick={() => removeUser(u.id, u.name)} data-testid={`remove-user-${u.id}`}>
                                        <Trash2 className="h-4 w-4 text-destructive" />
                                    </Button>
                                </div>
                            )}
                        </CardContent>
                    </Card>
                ))}
            </div>

            {emailLogs.length > 0 && (
                <>
                    <Separator className="mb-6" />
                    <h2 className="text-lg font-heading font-semibold mb-4">Emails Enviados (Mock)</h2>
                    <div className="space-y-2">
                        {emailLogs.slice(0, 10).map(log => (
                            <Card key={log.id} data-testid={`email-log-${log.id}`}>
                                <CardContent className="p-3 flex items-start gap-3">
                                    <Mail className="h-4 w-4 text-muted-foreground mt-0.5 shrink-0" />
                                    <div className="min-w-0">
                                        <p className="text-sm font-medium">{log.subject}</p>
                                        <p className="text-xs text-muted-foreground">Para: {log.to}</p>
                                        <p className="text-xs text-muted-foreground mt-1 truncate">{log.body}</p>
                                        <Badge variant="outline" className="mt-1 text-[10px]">{log.status}</Badge>
                                    </div>
                                    <span className="text-[10px] text-muted-foreground mono-num shrink-0">
                                        {new Date(log.created_at).toLocaleString("pt-BR")}
                                    </span>
                                </CardContent>
                            </Card>
                        ))}
                    </div>
                </>
            )}

            {isAdmin && (
                <>
                    <Separator className="mb-6" />
                    <div className="flex items-center justify-between mb-4">
                        <h2 className="text-lg font-heading font-semibold">Canais de Origem do Lead</h2>
                        <Button size="sm" variant="outline" onClick={() => setShowAddSource(true)}>
                            <Plus className="h-3.5 w-3.5 mr-1" /> Novo Canal
                        </Button>
                    </div>
                    {lsLoading ? (
                        <div className="h-8 w-32 bg-muted animate-pulse rounded" />
                    ) : (
                        <div className="space-y-1 mb-8">
                            {leadSources.map(src => (
                                <div key={src.id} className={`flex items-center gap-3 p-2 rounded-md border text-sm ${!src.ativo ? "opacity-50" : ""}`}>
                                    <code className="text-xs bg-muted px-1.5 py-0.5 rounded font-mono flex-shrink-0">{src.valor}</code>
                                    {editingSource === src.id ? (
                                        <>
                                            <Input className="h-7 text-xs flex-1" value={editSourceForm.nome}
                                                onChange={e => setEditSourceForm(f => ({ ...f, nome: e.target.value }))} />
                                            <Input className="h-7 text-xs w-36" value={editSourceForm.grupo} placeholder="grupo"
                                                onChange={e => setEditSourceForm(f => ({ ...f, grupo: e.target.value }))} />
                                            <Button size="sm" className="h-7 text-xs" onClick={() => updateLeadSource(src.id, editSourceForm)}>Salvar</Button>
                                            <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => setEditingSource(null)}>Cancelar</Button>
                                        </>
                                    ) : (
                                        <>
                                            <span className="flex-1 font-medium">{src.nome}</span>
                                            <span className="text-xs text-muted-foreground">{src.grupo || "—"}</span>
                                            <button className="text-muted-foreground hover:text-foreground" onClick={() => { setEditingSource(src.id); setEditSourceForm({ nome: src.nome, grupo: src.grupo || "" }); }}>
                                                <Pencil className="h-3.5 w-3.5" />
                                            </button>
                                            <button className={`${src.ativo ? "text-green-500" : "text-muted-foreground"} hover:opacity-70`} onClick={() => toggleLeadSource(src)} title={src.ativo ? "Desativar" : "Ativar"}>
                                                {src.ativo ? <ToggleRight className="h-4 w-4" /> : <ToggleLeft className="h-4 w-4" />}
                                            </button>
                                        </>
                                    )}
                                </div>
                            ))}
                        </div>
                    )}
                    <Dialog open={showAddSource} onOpenChange={setShowAddSource}>
                        <DialogContent>
                            <DialogHeader><DialogTitle className="font-heading">Novo Canal de Origem</DialogTitle></DialogHeader>
                            <div className="space-y-4">
                                <div className="space-y-1.5">
                                    <Label>Nome de exibição *</Label>
                                    <Input value={addSourceForm.nome} onChange={e => setAddSourceForm(f => ({ ...f, nome: e.target.value }))} placeholder="Ex: Indicação de parceiro" />
                                </div>
                                <div className="space-y-1.5">
                                    <Label>Valor/slug * <span className="text-xs text-muted-foreground">(imutável após criação)</span></Label>
                                    <Input value={addSourceForm.valor} onChange={e => setAddSourceForm(f => ({ ...f, valor: e.target.value.toLowerCase().replace(/\s+/g, "_").replace(/[^a-z0-9_]/g, "") }))} placeholder="ex: indicacao_parceiro_tech" />
                                </div>
                                <div className="space-y-1.5">
                                    <Label>Grupo</Label>
                                    <Input value={addSourceForm.grupo} onChange={e => setAddSourceForm(f => ({ ...f, grupo: e.target.value }))} placeholder="ex: indicacao" />
                                </div>
                            </div>
                            <DialogFooter>
                                <Button variant="outline" onClick={() => setShowAddSource(false)}>Cancelar</Button>
                                <Button onClick={createLeadSource} disabled={!addSourceForm.nome || !addSourceForm.valor}>Criar Canal</Button>
                            </DialogFooter>
                        </DialogContent>
                    </Dialog>
                </>
            )}

            <Dialog open={showInvite} onOpenChange={setShowInvite}>
                <DialogContent data-testid="invite-dialog">
                    <DialogHeader>
                        <DialogTitle className="font-heading">Convidar Membro</DialogTitle>
                    </DialogHeader>
                    {inviteResult ? (
                        <div className="space-y-4">
                            <p className="text-sm text-green-600 dark:text-green-400 font-medium">
                                {inviteResult.name} convidado com sucesso!
                            </p>
                            <div className="p-3 bg-muted rounded-md space-y-2">
                                <p className="text-xs text-muted-foreground">Credenciais temporarias:</p>
                                <p className="text-sm"><b>Email:</b> {inviteResult.email}</p>
                                <p className="text-sm"><b>Senha:</b> {inviteResult.temp_password}</p>
                            </div>
                            <Button variant="outline" size="sm" onClick={() => {
                                const text = `Email: ${inviteResult.email}\nSenha: ${inviteResult.temp_password}`;
                                if (navigator.clipboard && navigator.clipboard.writeText) {
                                    navigator.clipboard.writeText(text).then(() => toast.success("Copiado!")).catch(() => {
                                        window.prompt("Copie manualmente:", text);
                                    });
                                } else {
                                    window.prompt("Copie manualmente:", text);
                                }
                            }} data-testid="copy-credentials-btn">
                                <Copy className="h-3.5 w-3.5 mr-1" /> Copiar Credenciais
                            </Button>
                        </div>
                    ) : (
                        <div className="space-y-4">
                            <div className="space-y-2">
                                <Label>Nome *</Label>
                                <Input data-testid="invite-name" value={inviteForm.name}
                                    onChange={(e) => setInviteForm({ ...inviteForm, name: e.target.value })} placeholder="Nome completo" />
                            </div>
                            <div className="space-y-2">
                                <Label>Email *</Label>
                                <Input type="email" data-testid="invite-email" value={inviteForm.email}
                                    onChange={(e) => setInviteForm({ ...inviteForm, email: e.target.value })} placeholder="email@exemplo.com" />
                            </div>
                            <div className="space-y-2">
                                <Label>Role</Label>
                                <Select value={inviteForm.role} onValueChange={(v) => setInviteForm({ ...inviteForm, role: v })}>
                                    <SelectTrigger data-testid="invite-role"><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="vendedor">Vendedor</SelectItem>
                                        <SelectItem value="gestor">Gestor</SelectItem>
                                        <SelectItem value="admin">Admin</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                        </div>
                    )}
                    <DialogFooter>
                        {inviteResult ? (
                            <Button onClick={() => setShowInvite(false)}>Fechar</Button>
                        ) : (
                            <>
                                <Button variant="outline" onClick={() => setShowInvite(false)}>Cancelar</Button>
                                <Button onClick={inviteUser} data-testid="send-invite-btn" disabled={!inviteForm.email || !inviteForm.name}>
                                    Enviar Convite
                                </Button>
                            </>
                        )}
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
