import { LayoutGrid, List as ListIcon } from "lucide-react";

/**
 * Toggle entre visão Kanban e Lista.
 * Props:
 *  - value: "kanban" | "list"
 *  - onChange: (value) => void
 *  - testIdPrefix: string (opcional) ex: "crm1"
 */
export default function ViewSwitcher({ value, onChange, testIdPrefix = "view" }) {
    const options = [
        { id: "kanban", label: "Kanban", icon: LayoutGrid },
        { id: "list", label: "Lista", icon: ListIcon },
    ];

    return (
        <div
            role="tablist"
            aria-label="Alternar visualização"
            className="inline-flex items-center rounded-lg border border-border bg-card p-0.5 shadow-sm"
            data-testid={`${testIdPrefix}-view-switcher`}
        >
            {options.map((opt) => {
                const Icon = opt.icon;
                const active = value === opt.id;
                return (
                    <button
                        key={opt.id}
                        role="tab"
                        aria-selected={active}
                        type="button"
                        onClick={() => onChange(opt.id)}
                        data-testid={`${testIdPrefix}-view-${opt.id}`}
                        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                            active
                                ? "bg-primary text-primary-foreground shadow-sm"
                                : "text-muted-foreground hover:text-foreground hover:bg-accent"
                        }`}
                    >
                        <Icon className="h-3.5 w-3.5" />
                        {opt.label}
                    </button>
                );
            })}
        </div>
    );
}
