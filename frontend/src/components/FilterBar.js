import { useMemo } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import {
    Popover,
    PopoverContent,
    PopoverTrigger,
} from "@/components/ui/popover";
import { Search, X, Filter } from "lucide-react";

/**
 * Barra de filtros dinâmica com chips de filtros ativos.
 *
 * Props:
 *  - filters: objeto controlado { [key]: valor }
 *  - onChange: (newFilters) => void
 *  - fields: array de configs:
 *      { key, type: "search"|"select"|"multi", label, placeholder, options: [{value,label}] }
 *  - testIdPrefix: string
 */
export default function FilterBar({ filters, onChange, fields, testIdPrefix = "filter" }) {
    const setValue = (key, value) => onChange({ ...filters, [key]: value });

    const clearKey = (key) => {
        const next = { ...filters };
        delete next[key];
        onChange(next);
    };

    const clearAll = () => onChange({});

    const searchField = fields.find((f) => f.type === "search");
    const otherFields = fields.filter((f) => f.type !== "search");

    const activeChips = useMemo(() => {
        const chips = [];
        for (const field of fields) {
            const val = filters[field.key];
            if (val === undefined || val === null || val === "" || val === "all") continue;
            if (field.type === "multi") {
                if (!Array.isArray(val) || val.length === 0) continue;
                val.forEach((v) => {
                    const opt = field.options?.find((o) => o.value === v);
                    chips.push({
                        fieldKey: field.key,
                        label: `${field.label}: ${opt?.label || v}`,
                        onRemove: () => setValue(field.key, val.filter((x) => x !== v)),
                    });
                });
            } else if (field.type === "select") {
                const opt = field.options?.find((o) => o.value === val);
                chips.push({
                    fieldKey: field.key,
                    label: `${field.label}: ${opt?.label || val}`,
                    onRemove: () => clearKey(field.key),
                });
            } else if (field.type === "search") {
                chips.push({
                    fieldKey: field.key,
                    label: `Busca: "${val}"`,
                    onRemove: () => clearKey(field.key),
                });
            }
        }
        return chips;
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [filters, fields]);

    return (
        <div className="space-y-2 mb-4" data-testid={`${testIdPrefix}-bar`}>
            <div className="flex flex-wrap items-center gap-2">
                {searchField && (
                    <div className="relative flex-1 min-w-[220px] max-w-md">
                        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                        <Input
                            value={filters[searchField.key] || ""}
                            onChange={(e) => setValue(searchField.key, e.target.value)}
                            placeholder={searchField.placeholder || "Buscar..."}
                            className="pl-9"
                            data-testid={`${testIdPrefix}-search`}
                        />
                    </div>
                )}

                {otherFields.map((field) => {
                    if (field.type === "select") {
                        const current = filters[field.key] ?? "all";
                        return (
                            <Select
                                key={field.key}
                                value={current}
                                onValueChange={(v) => setValue(field.key, v === "all" ? "" : v)}
                            >
                                <SelectTrigger
                                    className="w-auto min-w-[140px] h-9"
                                    data-testid={`${testIdPrefix}-${field.key}`}
                                >
                                    <SelectValue placeholder={field.label} />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="all">Todos — {field.label}</SelectItem>
                                    {(field.options || []).map((opt) => (
                                        <SelectItem key={opt.value} value={opt.value}>
                                            {opt.label}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        );
                    }

                    if (field.type === "multi") {
                        const current = Array.isArray(filters[field.key]) ? filters[field.key] : [];
                        return (
                            <Popover key={field.key}>
                                <PopoverTrigger asChild>
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        className="h-9 gap-1.5"
                                        data-testid={`${testIdPrefix}-${field.key}-trigger`}
                                    >
                                        <Filter className="h-3.5 w-3.5" />
                                        {field.label}
                                        {current.length > 0 && (
                                            <span className="ml-1 inline-flex items-center justify-center rounded-full bg-primary text-primary-foreground text-[10px] h-4 min-w-[16px] px-1 font-semibold">
                                                {current.length}
                                            </span>
                                        )}
                                    </Button>
                                </PopoverTrigger>
                                <PopoverContent className="w-56 p-1" align="start">
                                    <div className="max-h-64 overflow-y-auto">
                                        {(field.options || []).map((opt) => {
                                            const checked = current.includes(opt.value);
                                            return (
                                                <button
                                                    key={opt.value}
                                                    type="button"
                                                    onClick={() => {
                                                        const next = checked
                                                            ? current.filter((v) => v !== opt.value)
                                                            : [...current, opt.value];
                                                        setValue(field.key, next);
                                                    }}
                                                    className={`w-full text-left px-2.5 py-1.5 rounded-sm text-sm flex items-center gap-2 ${
                                                        checked ? "bg-accent" : "hover:bg-accent/60"
                                                    }`}
                                                    data-testid={`${testIdPrefix}-${field.key}-opt-${opt.value}`}
                                                >
                                                    <span
                                                        className={`h-3.5 w-3.5 rounded-sm border flex items-center justify-center text-[10px] ${
                                                            checked
                                                                ? "bg-primary border-primary text-primary-foreground"
                                                                : "border-border"
                                                        }`}
                                                    >
                                                        {checked && "✓"}
                                                    </span>
                                                    {opt.label}
                                                </button>
                                            );
                                        })}
                                    </div>
                                </PopoverContent>
                            </Popover>
                        );
                    }

                    return null;
                })}

                {activeChips.length > 0 && (
                    <Button
                        variant="ghost"
                        size="sm"
                        onClick={clearAll}
                        className="h-9 text-muted-foreground"
                        data-testid={`${testIdPrefix}-clear-all`}
                    >
                        Limpar filtros
                    </Button>
                )}
            </div>

            {activeChips.length > 0 && (
                <div
                    className="flex flex-wrap items-center gap-1.5"
                    data-testid={`${testIdPrefix}-chips`}
                >
                    {activeChips.map((chip, idx) => (
                        <span
                            key={`${chip.fieldKey}-${idx}`}
                            className="inline-flex items-center gap-1 rounded-full bg-primary/10 border border-primary/20 text-primary px-2 py-0.5 text-xs"
                        >
                            {chip.label}
                            <button
                                type="button"
                                onClick={chip.onRemove}
                                className="hover:bg-primary/20 rounded-full p-0.5"
                                aria-label="Remover filtro"
                            >
                                <X className="h-3 w-3" />
                            </button>
                        </span>
                    ))}
                </div>
            )}
        </div>
    );
}

/**
 * Helper para aplicar filtros sobre um array de itens.
 * fieldsConfig com:
 *  - getter(item): valor a comparar
 *  - searchKeys (para search): [(item) => string]
 */
export function applyFilters(items, filters, fieldsConfig) {
    return items.filter((item) => {
        for (const field of fieldsConfig) {
            const val = filters[field.key];
            if (val === undefined || val === null || val === "" || val === "all") continue;

            if (field.type === "search") {
                const term = String(val).toLowerCase().trim();
                if (!term) continue;
                const haystacks = (field.searchKeys || []).map((fn) => String(fn(item) || "").toLowerCase());
                if (!haystacks.some((h) => h.includes(term))) return false;
            } else if (field.type === "select") {
                const itemVal = field.getter ? field.getter(item) : item[field.key];
                if (String(itemVal ?? "") !== String(val)) return false;
            } else if (field.type === "multi") {
                if (!Array.isArray(val) || val.length === 0) continue;
                const itemVal = field.getter ? field.getter(item) : item[field.key];
                if (Array.isArray(itemVal)) {
                    if (!val.some((v) => itemVal.includes(v))) return false;
                } else {
                    if (!val.includes(itemVal)) return false;
                }
            }
        }
        return true;
    });
}
