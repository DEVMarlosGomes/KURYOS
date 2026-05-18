import { useAuth } from "@/contexts/AuthContext";
import { ShieldOff } from "lucide-react";

// Canonical role groups (mirror backend rbac.py)
export const ROLE_GROUPS = {
    COMERCIAL_FULL: ["admin", "vendedor", "sales_ops", "sucesso_cliente", "gestor"],
    PD_FULL: ["admin", "lider_pd", "formulador", "qa", "engenharia_produto", "gestor"],
    PD_READ: ["admin", "lider_pd", "formulador", "qa", "engenharia_produto", "sales_ops", "gestor"],
    DOC_REVIEWERS: ["admin", "lider_pd", "qa", "engenharia_produto", "formulador", "gestor"],
    QA_APPROVERS: ["admin", "qa", "lider_pd", "gestor"],
    ADMIN_ONLY: ["admin"],
};

export function hasRole(user, allowed) {
    if (!user) return false;
    if (user.role === "admin") return true;
    if (!allowed || allowed.length === 0) return true;
    return allowed.includes(user.role);
}

export default function RoleGuard({ allowed, children, fallback = null, hideOnDeny = false }) {
    const { user } = useAuth();
    const ok = hasRole(user, allowed);
    if (ok) return children;
    if (hideOnDeny) return null;
    if (fallback) return fallback;
    return (
        <div
            data-testid="role-guard-denied"
            className="min-h-[60vh] flex flex-col items-center justify-center text-center px-6 gap-3"
        >
            <div className="h-14 w-14 rounded-full bg-destructive/10 text-destructive flex items-center justify-center">
                <ShieldOff className="h-7 w-7" />
            </div>
            <h2 className="text-lg font-semibold tracking-tight">Acesso restrito</h2>
            <p className="text-sm text-muted-foreground max-w-md">
                Sua função (<span className="font-medium">{user?.role || "?"}</span>) não tem permissão
                para este módulo. Fale com um administrador caso precise de acesso.
            </p>
        </div>
    );
}
