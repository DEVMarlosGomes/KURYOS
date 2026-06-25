import { useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { Navigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import api from "@/lib/api";

export default function LoginPage() {
    const { user, loading, login } = useAuth();
    const [error, setError] = useState("");
    const [submitting, setSubmitting] = useState(false);
    const [loginForm, setLoginForm] = useState({ email: "", password: "" });
    const [showForgot, setShowForgot] = useState(false);
    const [forgotEmail, setForgotEmail] = useState("");
    const [forgotMsg, setForgotMsg] = useState("");
    const [forgotLoading, setForgotLoading] = useState(false);

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

    const handleForgot = async (e) => {
        e.preventDefault();
        setForgotLoading(true);
        try {
            await api.post("/auth/forgot-password", { email: forgotEmail });
        } catch {}
        setForgotMsg("Se o email estiver cadastrado, voce recebera uma nova senha temporaria. Entre em contato com o administrador se nao receber.");
        setForgotLoading(false);
    };

    return (
        <div className="min-h-screen flex" data-testid="login-page">
            <div className="hidden lg:flex lg:w-1/2 relative overflow-hidden bg-gradient-to-br from-stone-800 to-stone-950">
                <div className="relative z-10 flex flex-col justify-end p-12">
                    <h1 className="text-5xl font-heading font-light text-white tracking-tight leading-tight">
                        ERP<br />
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
                        <h1 className="text-3xl font-heading font-semibold tracking-tight">ERP Kuryos</h1>
                    </div>

                    {!showForgot ? (
                        <form onSubmit={handleLogin} className="space-y-5" data-testid="login-form">
                            <div className="mb-6">
                                <h2 className="text-xl font-heading font-semibold">Entrar</h2>
                                <p className="text-sm text-muted-foreground mt-1">Acesse sua conta para continuar.</p>
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="login-email">Email</Label>
                                <Input id="login-email" data-testid="login-email-input" type="email" placeholder="seu@email.com"
                                    value={loginForm.email} onChange={(e) => setLoginForm({ ...loginForm, email: e.target.value })} required />
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="login-password">Senha</Label>
                                <Input id="login-password" data-testid="login-password-input" type="password" placeholder="••••••••"
                                    value={loginForm.password} onChange={(e) => setLoginForm({ ...loginForm, password: e.target.value })} required />
                            </div>
                            {error && <p className="text-sm text-destructive" data-testid="auth-error">{error}</p>}
                            <Button type="submit" className="w-full" disabled={submitting} data-testid="login-submit-btn">
                                {submitting ? "Entrando..." : "Entrar"}
                            </Button>
                            <div className="text-center pt-1">
                                <button type="button" onClick={() => { setShowForgot(true); setError(""); }}
                                    className="text-sm text-muted-foreground hover:text-foreground underline underline-offset-4 transition-colors"
                                    data-testid="forgot-password-btn">
                                    Esqueci minha senha
                                </button>
                            </div>
                        </form>
                    ) : (
                        <div className="space-y-5" data-testid="forgot-password-form">
                            <div className="mb-6">
                                <h2 className="text-xl font-heading font-semibold">Redefinir senha</h2>
                                <p className="text-sm text-muted-foreground mt-1">
                                    Informe seu email. Uma senha temporaria sera gerada e aparecera nos logs de email da equipe.
                                </p>
                            </div>
                            {!forgotMsg ? (
                                <form onSubmit={handleForgot} className="space-y-4">
                                    <div className="space-y-2">
                                        <Label htmlFor="forgot-email">Email</Label>
                                        <Input id="forgot-email" data-testid="forgot-email-input" type="email" placeholder="seu@email.com"
                                            value={forgotEmail} onChange={(e) => setForgotEmail(e.target.value)} required />
                                    </div>
                                    <Button type="submit" className="w-full" disabled={forgotLoading}>
                                        {forgotLoading ? "Processando..." : "Solicitar nova senha"}
                                    </Button>
                                    <div className="text-center">
                                        <button type="button"
                                            onClick={() => { setShowForgot(false); setForgotEmail(""); setForgotMsg(""); }}
                                            className="text-sm text-muted-foreground hover:text-foreground underline underline-offset-4 transition-colors">
                                            Voltar ao login
                                        </button>
                                    </div>
                                </form>
                            ) : (
                                <div className="space-y-4">
                                    <p className="text-sm text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-950/30 p-3 rounded-md border border-green-200 dark:border-green-900">
                                        {forgotMsg}
                                    </p>
                                    <Button variant="outline" className="w-full"
                                        onClick={() => { setShowForgot(false); setForgotEmail(""); setForgotMsg(""); }}>
                                        Voltar ao login
                                    </Button>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
