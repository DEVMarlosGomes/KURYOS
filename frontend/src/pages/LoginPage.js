import { useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { Navigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const HERO_BG = "https://static.prod-images.emergentagent.com/jobs/19c57ff8-68c4-4faf-a657-3fa1c5f88325/images/5f28b7762e8cf043112e395479622397b2bf72076fc5cd0bf5186d12c784ff37.png";

export default function LoginPage() {
    const { user, loading, login, register } = useAuth();
    const [tab, setTab] = useState("login");
    const [error, setError] = useState("");
    const [submitting, setSubmitting] = useState(false);

    const [loginForm, setLoginForm] = useState({ email: "", password: "" });
    const [regForm, setRegForm] = useState({ email: "", password: "", name: "", org_name: "" });

    if (loading) return (
        <div className="h-screen flex items-center justify-center bg-background" data-testid="login-loading">
            <div className="animate-spin h-8 w-8 border-2 border-primary border-t-transparent rounded-full" />
        </div>
    );
    if (user) return <Navigate to="/tasks" replace />;

    const handleLogin = async (e) => {
        e.preventDefault();
        setError("");
        setSubmitting(true);
        const res = await login(loginForm.email, loginForm.password);
        if (!res.success) setError(res.error);
        setSubmitting(false);
    };

    const handleRegister = async (e) => {
        e.preventDefault();
        setError("");
        setSubmitting(true);
        const res = await register(regForm.email, regForm.password, regForm.name, regForm.org_name);
        if (!res.success) setError(res.error);
        setSubmitting(false);
    };

    return (
        <div className="min-h-screen flex" data-testid="login-page">
            <div className="hidden lg:flex lg:w-1/2 relative overflow-hidden">
                <img src={HERO_BG} alt="" className="absolute inset-0 w-full h-full object-cover" />
                <div className="absolute inset-0 bg-black/50" />
                <div className="relative z-10 flex flex-col justify-end p-12">
                    <h1 className="text-5xl font-heading font-light text-white tracking-tight leading-tight">
                        CRM<br />
                        <span className="font-semibold">Kuryos</span>
                    </h1>
                    <p className="mt-4 text-white/70 text-lg font-body max-w-md leading-relaxed">
                        Pipeline inteligente para cosmeticos, perfumaria e desenvolvimento de produtos.
                    </p>
                </div>
            </div>

            <div className="flex-1 flex items-center justify-center p-8 bg-background">
                <div className="w-full max-w-md">
                    <div className="mb-8 lg:hidden">
                        <h1 className="text-3xl font-heading font-semibold tracking-tight">CRM Kuryos</h1>
                    </div>

                    <Tabs value={tab} onValueChange={(v) => { setTab(v); setError(""); }} data-testid="auth-tabs">
                        <TabsList className="grid w-full grid-cols-2 mb-6">
                            <TabsTrigger value="login" data-testid="login-tab">Entrar</TabsTrigger>
                            <TabsTrigger value="register" data-testid="register-tab">Criar Conta</TabsTrigger>
                        </TabsList>

                        <TabsContent value="login">
                            <form onSubmit={handleLogin} className="space-y-5">
                                <div className="space-y-2">
                                    <Label htmlFor="login-email">Email</Label>
                                    <Input id="login-email" data-testid="login-email-input" type="email" placeholder="seu@email.com"
                                        value={loginForm.email} onChange={(e) => setLoginForm({ ...loginForm, email: e.target.value })} required />
                                </div>
                                <div className="space-y-2">
                                    <Label htmlFor="login-password">Senha</Label>
                                    <Input id="login-password" data-testid="login-password-input" type="password" placeholder="********"
                                        value={loginForm.password} onChange={(e) => setLoginForm({ ...loginForm, password: e.target.value })} required />
                                </div>
                                {error && <p className="text-sm text-destructive" data-testid="auth-error">{error}</p>}
                                <Button type="submit" className="w-full" disabled={submitting} data-testid="login-submit-btn">
                                    {submitting ? "Entrando..." : "Entrar"}
                                </Button>
                            </form>

                            <div className="mt-6 pt-6 border-t border-border" data-testid="demo-users-section">
                                <p className="text-xs uppercase tracking-wider text-muted-foreground mb-3 font-medium">
                                    Acesso rapido — 8 perfis demo
                                </p>
                                <div className="grid grid-cols-2 gap-2">
                                    {[
                                        { email: "admin@kuryos.com", pwd: "admin123", label: "Admin" },
                                        { email: "vendedor@kuryos.com", pwd: "kuryos123", label: "Vendedor" },
                                        { email: "salesops@kuryos.com", pwd: "kuryos123", label: "Sales Ops" },
                                        { email: "formulador@kuryos.com", pwd: "kuryos123", label: "Formulador" },
                                        { email: "qa@kuryos.com", pwd: "kuryos123", label: "Qualidade" },
                                        { email: "liderpd@kuryos.com", pwd: "kuryos123", label: "Lider P&D" },
                                        { email: "engenharia@kuryos.com", pwd: "kuryos123", label: "Eng. Produto" },
                                        { email: "sucesso@kuryos.com", pwd: "kuryos123", label: "Sucesso Cliente" },
                                    ].map((u) => (
                                        <button
                                            key={u.email}
                                            type="button"
                                            data-testid={`demo-login-${u.label.toLowerCase().replace(/[^a-z]/g, "-")}`}
                                            onClick={() => setLoginForm({ email: u.email, password: u.pwd })}
                                            className="text-xs rounded-md border border-border px-2 py-1.5 hover:bg-accent text-left transition-colors"
                                        >
                                            <span className="block font-medium truncate">{u.label}</span>
                                            <span className="block text-[10px] text-muted-foreground truncate">{u.email}</span>
                                        </button>
                                    ))}
                                </div>
                            </div>
                        </TabsContent>

                        <TabsContent value="register">
                            <form onSubmit={handleRegister} className="space-y-4">
                                <div className="space-y-2">
                                    <Label htmlFor="reg-name">Nome</Label>
                                    <Input id="reg-name" data-testid="register-name-input" placeholder="Seu nome"
                                        value={regForm.name} onChange={(e) => setRegForm({ ...regForm, name: e.target.value })} required />
                                </div>
                                <div className="space-y-2">
                                    <Label htmlFor="reg-org">Organizacao</Label>
                                    <Input id="reg-org" data-testid="register-org-input" placeholder="Nome da empresa"
                                        value={regForm.org_name} onChange={(e) => setRegForm({ ...regForm, org_name: e.target.value })} required />
                                </div>
                                <div className="space-y-2">
                                    <Label htmlFor="reg-email">Email</Label>
                                    <Input id="reg-email" data-testid="register-email-input" type="email" placeholder="seu@email.com"
                                        value={regForm.email} onChange={(e) => setRegForm({ ...regForm, email: e.target.value })} required />
                                </div>
                                <div className="space-y-2">
                                    <Label htmlFor="reg-password">Senha</Label>
                                    <Input id="reg-password" data-testid="register-password-input" type="password" placeholder="Min. 6 caracteres"
                                        value={regForm.password} onChange={(e) => setRegForm({ ...regForm, password: e.target.value })} required />
                                </div>
                                {error && <p className="text-sm text-destructive" data-testid="auth-error">{error}</p>}
                                <Button type="submit" className="w-full" disabled={submitting} data-testid="register-submit-btn">
                                    {submitting ? "Criando conta..." : "Criar Conta"}
                                </Button>
                            </form>
                        </TabsContent>
                    </Tabs>
                </div>
            </div>
        </div>
    );
}
