import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { HelpCircle } from "lucide-react";

/**
 * Wraps a label with a small info icon that shows a tooltip on hover.
 * Usage: <FieldHint hint="Explain the field here">Label text</FieldHint>
 */
export function FieldHint({ children, hint }) {
    return (
        <TooltipProvider delayDuration={200}>
            <Tooltip>
                <span className="flex items-center gap-1">
                    {children}
                    <TooltipTrigger asChild>
                        <HelpCircle className="h-3.5 w-3.5 text-muted-foreground cursor-help shrink-0" />
                    </TooltipTrigger>
                </span>
                <TooltipContent side="top" className="max-w-xs text-xs">
                    {hint}
                </TooltipContent>
            </Tooltip>
        </TooltipProvider>
    );
}
