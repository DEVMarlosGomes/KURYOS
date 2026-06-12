import { Input } from "@/components/ui/input";

/**
 * CurrencyInput — number input paired with a BRL/USD toggle button.
 *
 * Props:
 *   value            string | number   raw input value
 *   currency         "BRL" | "USD"     selected currency
 *   onValueChange    (val: string) => void
 *   onCurrencyChange (currency: "BRL" | "USD") => void
 *   cotacao          number   USD→BRL rate for conversion hint (default 5.80)
 *   showHint         boolean  show converted value below input (default true)
 *   disabled         boolean
 *   placeholder      string
 *   className        string   wrapper div className
 *   inputClassName   string   input className
 *   size             "sm" | "default"
 */
export function CurrencyInput({
  value,
  currency = "BRL",
  onValueChange,
  onCurrencyChange,
  onBlur,
  cotacao = 5.80,
  showHint = true,
  disabled = false,
  placeholder,
  className = "",
  inputClassName = "",
  size = "default",
}) {
  const isBRL = currency === "BRL";
  const numVal = parseFloat(value) || 0;

  const hintText = showHint && numVal > 0
    ? isBRL
      ? `≈ US$ ${(numVal / cotacao).toFixed(2)}`
      : `≈ R$ ${(numVal * cotacao).toFixed(2)}`
    : null;

  const h = size === "sm" ? "h-8 text-sm" : "h-9 text-sm";

  return (
    <div className={`space-y-0.5 ${className}`}>
      <div className="flex gap-1">
        <Input
          type="number"
          step="0.01"
          value={value}
          onChange={(e) => onValueChange?.(e.target.value)}
          onBlur={onBlur}
          placeholder={placeholder ?? (isBRL ? "0,00" : "0.00")}
          disabled={disabled}
          className={`${h} font-mono text-right ${inputClassName}`}
        />
        <button
          type="button"
          disabled={disabled}
          onClick={() => onCurrencyChange?.(isBRL ? "USD" : "BRL")}
          title={isBRL ? "Clique para alternar para Dólar (US$)" : "Clique para alternar para Real (R$)"}
          className={`shrink-0 px-2 rounded border text-xs font-bold transition-colors ${
            isBRL
              ? "bg-emerald-600 text-white border-emerald-600 hover:bg-emerald-700"
              : "bg-blue-600 text-white border-blue-600 hover:bg-blue-700"
          } ${size === "sm" ? "h-8" : "h-9"} ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}
        >
          {isBRL ? "R$" : "US$"}
        </button>
      </div>
      {hintText && (
        <p className="text-[10px] text-muted-foreground pl-1">{hintText}</p>
      )}
    </div>
  );
}

/** Format a monetary value according to currency. */
export function fmtCurrency(amount, currency = "BRL") {
  if (amount == null || isNaN(amount)) return "—";
  if (currency === "USD") {
    return `US$ ${Number(amount).toFixed(2)}`;
  }
  return `R$ ${Number(amount).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** Currency badge label for display. */
export function CurrencyBadge({ currency = "BRL", className = "" }) {
  const isBRL = currency === "BRL";
  return (
    <span
      className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold ${
        isBRL
          ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300"
          : "bg-blue-100 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300"
      } ${className}`}
    >
      {isBRL ? "R$" : "US$"}
    </span>
  );
}
