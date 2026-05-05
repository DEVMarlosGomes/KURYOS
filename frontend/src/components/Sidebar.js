import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { useTheme } from "@/App";
import {
    LayoutDashboard, Kanban, Users, LogOut, Moon, Sun, FlaskConical, Building2,
    Package, ChevronDown, ChevronRight, ShieldCheck, BarChart3, Warehouse, ClipboardList,
    CheckSquare, History, BookOpen, Database
} from "lucide-react";
import { Separator } from "@/components/ui/separator";
import { TooltipProvider } from "@/components/ui/tooltip";
import NotificationPanel from "@/components/NotificationPanel";
import { useState, useEffect } from "react";

const NAV_MODULES = [
    {
        key: "dashboard",
        type: "link",
        path: "/dashboard",
        label: "Dashboard",
        icon: LayoutDashboard,
    },
    {
        key: "pipeline",
        type: "link",
        path: "/pipeline",
        label: "Pipeline",
        icon: Kanban,
    },
    {
        key: "crm",
        type: "group",
        label: "CRM Comercial",
        icon: Building2,
        basePaths: ["/crm/clients", "/crm/projects", "/crm/samples"],
        children: [
            { path: "/crm/clients", label: "Pipeline Clientes" },
            { path: "/crm/projects", label: "Projetos" },
            { path: "/crm/samples", label: "Amostras" },
        ],
    },
    {
        key: "pd",
        type: "group",
        label: "P&D",
        icon: FlaskConical,
        basePaths: ["/pd", "/pd/formulas", "/pd/catalog", "/pd/estoque", "/crm/skus", "/pd/homologacao", "/pd/relatorios"],
        children: [
            { path: "/pd", label: "Pipeline P&D", icon: ClipboardList },
            { path: "/pd/formulas", label: "Banco de Fórmulas", icon: BookOpen },
            { path: "/pd/homologacao", label: "Homologações", icon: ShieldCheck },
            { path: "/pd/catalog", label: "Banco de Custos", icon: Database },
            { path: "/pd/estoque", label: "Estoque Lab", icon: Warehouse },
            { path: "/crm/skus", label: "SKUs / Catálogo", icon: Package },
            { path: "/pd/relatorios", label: "Relatórios", icon: BarChart3 },
        ],
    },
    {
        key: "estoque",
        type: "link",
        path: "/estoque",
        label: "Estoque",
        icon: Warehouse,
    },
    {
        key: "tasks",
        type: "link",
        path: "/tasks",
        label: "Tarefas",
        icon: CheckSquare,
    },
    {
        key: "audit",
        type: "link",
        path: "/audit",
        label: "Auditoria",
        icon: History,
    },
    {
        key: "team",
        type: "link",
        path: "/team",
        label: "Equipe",
        icon: Users,
    },
];

export default function Sidebar() {
    const location = useLocation();
    const navigate = useNavigate();
    const { user, logout } = useAuth();
    const { dark, setDark } = useTheme();

    const computeInitialOpen = () => {
        const opens = {};
        for (const mod of NAV_MODULES) {
            if (mod.type === "group") {
                const isIn = mod.basePaths.some(bp => location.pathname === bp || location.pathname.startsWith(bp));
                opens[mod.key] = isIn;
            }
        }
        return opens;
    };
    const [openGroups, setOpenGroups] = useState(computeInitialOpen);

    useEffect(() => {
        setOpenGroups((prev) => {
            const next = { ...prev };
            for (const mod of NAV_MODULES) {
                if (mod.type === "group") {
                    const isIn = mod.basePaths.some(bp => location.pathname === bp || location.pathname.startsWith(bp));
                    if (isIn) next[mod.key] = true;
                }
            }
            return next;
        });
    }, [location.pathname]);

    const isActive = (path) => {
        if (location.pathname === path) return true;
        if (path === "/pd" && (location.pathname.startsWith("/pd/") || location.pathname === "/pd")) {
            return location.pathname === "/pd";
        }
        return location.pathname.startsWith(path + "/") && path !== "/";
    };

    const toggleGroup = (key) => {
        setOpenGroups((prev) => ({ ...prev, [key]: !prev[key] }));
    };

    return (
        <TooltipProvider delayDuration={200}>
            <aside className="w-[240px] h-screen flex flex-col border-r border-border bg-card shrink-0" data-testid="sidebar">
                <div className="p-5">
                    <h2 className="font-heading font-semibold text-lg tracking-tight" data-testid="sidebar-logo">
                        Kuryos
                    </h2>
                    <p className="text-xs text-muted-foreground mt-0.5 truncate">{user?.name}</p>
                </div>

                <Separator />

                <nav className="flex-1 p-3 space-y-1 overflow-y-auto" data-testid="sidebar-nav">
                    {NAV_MODULES.map((mod) => {
                        const Icon = mod.icon;
                        if (mod.type === "link") {
                            const active = isActive(mod.path);
                            return (
                                <button
                                    key={mod.key}
                                    onClick={() => navigate(mod.path)}
                                    data-testid={`nav-${mod.key}`}
                                    className={`sidebar-item w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-sm ${
                                        active ? "active bg-accent text-foreground font-medium" : "text-muted-foreground hover:text-foreground"
                                    }`}
                                >
                                    <Icon className="h-4 w-4 shrink-0" />
                                    {mod.label}
                                </button>
                            );
                        }

                        const isOpen = openGroups[mod.key];
                        const hasActiveChild = mod.basePaths.some(bp => location.pathname === bp || location.pathname.startsWith(bp + "/"));
                        return (
                            <div key={mod.key} className="space-y-0.5">
                                <button
                                    onClick={() => toggleGroup(mod.key)}
                                    data-testid={`nav-group-${mod.key}`}
                                    className={`sidebar-item w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-sm ${
                                        hasActiveChild ? "text-foreground font-medium" : "text-muted-foreground hover:text-foreground"
                                    }`}
                                >
                                    <Icon className="h-4 w-4 shrink-0" />
                                    <span className="flex-1 text-left">{mod.label}</span>
                                    {isOpen ? (
                                        <ChevronDown className="h-3.5 w-3.5 shrink-0" />
                                    ) : (
                                        <ChevronRight className="h-3.5 w-3.5 shrink-0" />
                                    )}
                                </button>
                                {isOpen && (
                                    <div className="ml-4 pl-3 border-l border-border/60 space-y-0.5">
                                        {mod.children.map((child) => {
                                            const childActive = isActive(child.path);
                                            const ChildIcon = child.icon;
                                            return (
                                                <button
                                                    key={child.path}
                                                    onClick={() => navigate(child.path)}
                                                    data-testid={`nav-${mod.key}-${child.path.split("/").pop()}`}
                                                    className={`sidebar-item w-full flex items-center gap-2 px-3 py-2 rounded-md text-xs ${
                                                        childActive ? "active bg-accent text-foreground font-medium" : "text-muted-foreground hover:text-foreground"
                                                    }`}
                                                >
                                                    {ChildIcon && <ChildIcon className="h-3.5 w-3.5 shrink-0" />}
                                                    <span className="truncate">{child.label}</span>
                                                </button>
                                            );
                                        })}
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </nav>

                <div className="p-3 space-y-1">
                    <Separator className="mb-2" />
                    <NotificationPanel />
                    <button
                        onClick={() => setDark(!dark)}
                        data-testid="theme-toggle"
                        className="sidebar-item w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-sm text-muted-foreground hover:text-foreground"
                    >
                        {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
                        {dark ? "Modo Claro" : "Modo Escuro"}
                    </button>
                    <button
                        onClick={logout}
                        data-testid="logout-btn"
                        className="sidebar-item w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-sm text-muted-foreground hover:text-foreground"
                    >
                        <LogOut className="h-4 w-4" />
                        Sair
                    </button>
                </div>
            </aside>
        </TooltipProvider>
    );
}
