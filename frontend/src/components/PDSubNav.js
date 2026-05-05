import { Button } from "@/components/ui/button";
import { useNavigate, useLocation } from "react-router-dom";
import { Kanban, Building2, Database, Package, ShieldCheck, BarChart3, BookOpen } from "lucide-react";

/**
 * Shared sub-navigation for all P&D related pages
 * (Pipeline P&D, Banco de Formulas, Homologacoes, Banco de Custos, Estoque Lab, Relatorios, CRM link)
 */
export default function PDSubNav({ active }) {
    const navigate = useNavigate();
    const location = useLocation();

    const tabs = [
        { id: "crm", label: "CRM Comercial", path: "/crm/clients", icon: Building2 },
        { id: "pd", label: "Pipeline P&D", path: "/pd", icon: Kanban },
        { id: "formulaBank", label: "Banco de Fórmulas", path: "/pd/formulas", icon: BookOpen },
        { id: "homologacao", label: "Homologações", path: "/pd/homologacao", icon: ShieldCheck },
        { id: "catalog", label: "Banco de Custos", path: "/pd/catalog", icon: Database },
        { id: "stock", label: "Estoque Lab", path: "/pd/estoque", icon: Package },
        { id: "reports", label: "Relatórios", path: "/pd/relatorios", icon: BarChart3 },
    ];

    const activeId = active || (() => {
        if (location.pathname.startsWith("/crm")) return "crm";
        if (location.pathname.startsWith("/pd/formulas")) return "formulaBank";
        if (location.pathname.startsWith("/pd/homologacao")) return "homologacao";
        if (location.pathname.startsWith("/pd/catalog")) return "catalog";
        if (location.pathname.startsWith("/pd/estoque")) return "stock";
        if (location.pathname.startsWith("/pd/relatorios")) return "reports";
        if (location.pathname === "/pd" || location.pathname.startsWith("/pd/")) return "pd";
        return "pd";
    })();

    return (
        <div className="flex gap-2 mb-6 border-b border-border pb-2 flex-wrap">
            {tabs.map(tab => {
                const Icon = tab.icon;
                const isActive = activeId === tab.id;
                return (
                    <Button
                        key={tab.id}
                        variant={isActive ? "default" : "ghost"}
                        size="sm"
                        onClick={() => navigate(tab.path)}
                        className="gap-1.5"
                    >
                        <Icon className="h-3.5 w-3.5" />
                        {tab.label}
                    </Button>
                );
            })}
        </div>
    );
}
