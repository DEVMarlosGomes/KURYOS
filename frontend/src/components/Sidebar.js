import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { useTheme } from "@/App";
import {
    LayoutDashboard, Kanban, Users, LogOut, Moon, Sun, FlaskConical, Building2,
    Package, ChevronDown, ChevronRight, ShieldCheck, BarChart3, Warehouse, ClipboardList,
    CheckSquare, History, BookOpen, Database, Menu, X, ShoppingCart, FileText, Microscope, Factory,
    Truck, Receipt, Calendar, ArrowLeftRight
} from "lucide-react";
import { Separator } from "@/components/ui/separator";
import { TooltipProvider } from "@/components/ui/tooltip";
import NotificationPanel from "@/components/NotificationPanel";
import { useState, useEffect } from "react";

const NAV_MODULES = [
    {
        key: "tasks",
        type: "link",
        path: "/tasks",
        label: "Tarefas",
        icon: CheckSquare,
        roles: null, // all roles
    },
    {
        key: "dashboard",
        type: "link",
        path: "/dashboard",
        label: "Dashboard",
        icon: LayoutDashboard,
        roles: null,
    },
    {
        key: "crm",
        type: "group",
        label: "CRM Comercial",
        icon: Building2,
        basePaths: ["/crm/clients", "/crm/projects", "/crm/samples"],
        roles: ["admin", "vendedor", "sales_ops", "sucesso_cliente", "gestor"],
        children: [
            { path: "/crm/clients", label: "Pipeline Clientes" },
            { path: "/crm/projects", label: "Projetos" },
            { path: "/crm/samples", label: "Amostras" },
        ],
    },
    {
        key: "kickoffs",
        type: "link",
        path: "/kickoffs",
        label: "Kickoffs",
        icon: ClipboardList,
        roles: ["admin", "vendedor", "sales_ops", "formulador", "qa", "lider_pd", "engenharia_produto", "sucesso_cliente", "gestor"],
    },
    {
        key: "pd",
        type: "group",
        label: "P&D",
        icon: FlaskConical,
        basePaths: ["/pd", "/pd/formulas", "/pd/catalog", "/pd/estoque", "/crm/skus", "/pd/homologacao", "/pd/relatorios"],
        roles: ["admin", "lider_pd", "formulador", "qa", "engenharia_produto", "sales_ops", "gestor"],
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
        type: "group",
        label: "Estoque / WMS",
        icon: Warehouse,
        basePaths: ["/estoque"],
        roles: ["admin", "lider_pd", "formulador", "qa", "engenharia_produto", "compras", "gestor"],
        children: [
            { path: "/estoque",               label: "Estoque Geral",        icon: Warehouse },
            { path: "/estoque/movimentacao",   label: "Movimentação",         icon: ArrowLeftRight },
        ],
    },
    {
        key: "recebimento",
        type: "link",
        path: "/recebimento",
        label: "Recebimento",
        icon: Package,
        roles: ["admin", "lider_pd", "formulador", "qa", "engenharia_produto", "compras", "gestor"],
    },
    {
        key: "cq",
        type: "group",
        label: "Controle de Qualidade",
        icon: Microscope,
        basePaths: ["/cq", "/cq/retrabalho"],
        roles: ["admin", "qa", "lider_pd", "formulador", "engenharia_produto", "compras", "sales_ops"],
        children: [
            { path: "/cq",                       label: "Dashboard CQ" },
            { path: "/cq/registros-analise",     label: "Registros de Análise" },
            { path: "/cq/checklists",            label: "Checklists" },
            { path: "/cq/rncs",                  label: "Não Conformidades" },
            { path: "/cq/retencoes",             label: "Retenções" },
            { path: "/cq/instrumentos",          label: "Instrumentos" },
            { path: "/cq/retrabalho",            label: "Retrabalho" },
        ],
    },
    {
        key: "orders",
        type: "link",
        path: "/orders",
        label: "Pedidos (PI)",
        icon: ShoppingCart,
        roles: null,
    },
    {
        key: "ops",
        type: "link",
        path: "/ops",
        label: "Ordens de Produção",
        icon: Factory,
        roles: null,
    },
    {
        key: "pcp",
        type: "link",
        path: "/pcp",
        label: "PCP",
        icon: Calendar,
        roles: ["admin", "lider_pd", "formulador", "qa", "engenharia_produto", "compras", "gestor", "sales_ops"],
    },
    {
        key: "expedicao",
        type: "link",
        path: "/expedicao",
        label: "Expedição",
        icon: Truck,
        roles: ["admin", "compras", "engenharia_produto", "lider_pd", "qa", "sales_ops", "gestor"],
    },
    {
        key: "faturamento",
        type: "link",
        path: "/faturamento",
        label: "Faturamento",
        icon: Receipt,
        roles: ["admin", "sales_ops", "compras", "gestor"],
    },
    {
        key: "compras",
        type: "group",
        label: "Compras",
        icon: Package,
        basePaths: ["/compras"],
        roles: ["admin", "compras", "engenharia_produto", "lider_pd", "qa", "sales_ops"],
        children: [
            { path: "/compras", label: "Dashboard" },
            { path: "/compras/fornecedores", label: "Fornecedores" },
            { path: "/compras/itens", label: "Itens" },
            { path: "/compras/mrp", label: "MRP" },
            { path: "/compras/pos", label: "Pedidos de Compra" },
            { path: "/compras/estoque-projetado", label: "Estoque Projetado" },
        ],
    },
    {
        key: "contratos",
        type: "link",
        path: "/contratos",
        label: "Contratos CGI",
        icon: FileText,
        roles: ["admin", "sales_ops", "vendedor", "compras", "lider_pd", "qa", "engenharia_produto", "sucesso_cliente"],
    },
    {
        key: "audit",
        type: "link",
        path: "/audit",
        label: "Auditoria",
        icon: History,
        roles: ["admin", "lider_pd", "qa", "sales_ops", "gestor"],
    },
    {
        key: "team",
        type: "link",
        path: "/team",
        label: "Equipe",
        icon: Users,
        roles: ["admin"],
    },
];

function isVisibleForRole(item, role) {
    if (!item.roles) return true;
    if (role === "admin") return true;
    return item.roles.includes(role);
}

export default function Sidebar() {
    const location = useLocation();
    const navigate = useNavigate();
    const { user, logout } = useAuth();
    const { dark, setDark } = useTheme();
    const [mobileOpen, setMobileOpen] = useState(false);

    const filteredModules = NAV_MODULES.filter((m) => isVisibleForRole(m, user?.role));

    const computeInitialOpen = () => {
        const opens = {};
        for (const mod of filteredModules) {
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
            for (const mod of filteredModules) {
                if (mod.type === "group") {
                    const isIn = mod.basePaths.some(bp => location.pathname === bp || location.pathname.startsWith(bp));
                    if (isIn) next[mod.key] = true;
                }
            }
            return next;
        });
        // close mobile menu on route change
        setMobileOpen(false);
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

    const handleNavigate = (path) => {
        navigate(path);
        setMobileOpen(false);
    };

    const sidebarContent = (
        <>
            <div className="p-5 flex items-center justify-between gap-2">
                <div className="min-w-0">
                    <h2 className="font-heading font-semibold text-lg tracking-tight" data-testid="sidebar-logo">
                        Kuryos
                    </h2>
                    <p className="text-xs text-muted-foreground mt-0.5 truncate">
                        {user?.name} <span className="opacity-70">· {user?.role}</span>
                    </p>
                </div>
                <button
                    type="button"
                    className="md:hidden p-2 rounded-md hover:bg-accent text-muted-foreground"
                    onClick={() => setMobileOpen(false)}
                    data-testid="sidebar-close-mobile"
                    aria-label="Fechar menu"
                >
                    <X className="h-4 w-4" />
                </button>
            </div>

            <Separator />

            <nav className="flex-1 p-3 space-y-1 overflow-y-auto" data-testid="sidebar-nav">
                {filteredModules.map((mod) => {
                    const Icon = mod.icon;
                    if (mod.type === "link") {
                        const active = isActive(mod.path);
                        return (
                            <button
                                key={mod.key}
                                onClick={() => handleNavigate(mod.path)}
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
                                                onClick={() => handleNavigate(child.path)}
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
        </>
    );

    return (
        <TooltipProvider delayDuration={200}>
            {/* Mobile top bar */}
            <div className="md:hidden fixed top-0 left-0 right-0 z-40 h-14 bg-card border-b border-border flex items-center justify-between px-4" data-testid="mobile-topbar">
                <button
                    type="button"
                    onClick={() => setMobileOpen(true)}
                    data-testid="mobile-menu-btn"
                    aria-label="Abrir menu"
                    className="p-2 rounded-md hover:bg-accent text-foreground"
                >
                    <Menu className="h-5 w-5" />
                </button>
                <h2 className="font-heading font-semibold text-base tracking-tight">Kuryos</h2>
                <div className="w-9" />
            </div>

            {/* Desktop sidebar */}
            <aside
                className="hidden md:flex w-[240px] h-screen flex-col border-r border-border bg-card shrink-0"
                data-testid="sidebar"
            >
                {sidebarContent}
            </aside>

            {/* Mobile drawer */}
            {mobileOpen && (
                <div className="md:hidden fixed inset-0 z-50 flex" data-testid="mobile-sidebar-drawer">
                    <div
                        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
                        onClick={() => setMobileOpen(false)}
                        aria-hidden="true"
                    />
                    <aside className="relative w-[280px] h-screen flex flex-col border-r border-border bg-card shadow-2xl">
                        {sidebarContent}
                    </aside>
                </div>
            )}
        </TooltipProvider>
    );
}
