/**
 * Visão de Lista genérica para CRMs e Pipelines.
 *
 * Props:
 *  - items: array
 *  - columns: [{ key, label, render?(item), width?, className? }]
 *  - onRowClick?: (item) => void
 *  - emptyMessage?: string
 *  - testIdPrefix?: string
 *  - getRowId?: (item) => string  (default: item.id)
 */
export default function ListView({
    items,
    columns,
    onRowClick,
    emptyMessage = "Nenhum registro encontrado.",
    testIdPrefix = "list",
    getRowId = (item) => item.id,
}) {
    if (!items || items.length === 0) {
        return (
            <div
                className="rounded-lg border border-dashed border-border bg-muted/20 px-6 py-12 text-center text-sm text-muted-foreground"
                data-testid={`${testIdPrefix}-empty`}
            >
                {emptyMessage}
            </div>
        );
    }

    return (
        <div
            className="rounded-lg border border-border bg-card overflow-hidden"
            data-testid={`${testIdPrefix}-table-wrap`}
        >
            <div className="overflow-x-auto">
                <table className="w-full text-sm" data-testid={`${testIdPrefix}-table`}>
                    <thead>
                        <tr className="bg-muted/40 border-b border-border text-left">
                            {columns.map((col) => (
                                <th
                                    key={col.key}
                                    className={`px-3 py-2.5 font-semibold text-xs text-muted-foreground uppercase tracking-wider ${col.className || ""}`}
                                    style={col.width ? { width: col.width } : undefined}
                                >
                                    {col.label}
                                </th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {items.map((item, idx) => (
                            <tr
                                key={getRowId(item) || idx}
                                onClick={onRowClick ? () => onRowClick(item) : undefined}
                                className={`border-b border-border/60 last:border-b-0 transition-colors ${
                                    onRowClick ? "cursor-pointer hover:bg-accent/40" : ""
                                }`}
                                data-testid={`${testIdPrefix}-row-${getRowId(item) || idx}`}
                            >
                                {columns.map((col) => (
                                    <td
                                        key={col.key}
                                        className={`px-3 py-2.5 align-middle ${col.cellClassName || ""}`}
                                    >
                                        {col.render ? col.render(item) : item[col.key] ?? "—"}
                                    </td>
                                ))}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
