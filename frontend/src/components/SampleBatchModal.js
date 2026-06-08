import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Plus, Trash2 } from "lucide-react";
import { FieldHint } from "@/components/ui/FieldHint";

function formatSlugLabel(value) {
    if (!value) return "";
    return String(value)
        .split("_")
        .map((part) => part ? part[0].toUpperCase() + part.slice(1) : "")
        .join(" ");
}

export default function SampleBatchModal({
    open,
    onOpenChange,
    batchSamples,
    setBatchSamples,
    onSubmit,
    addVariacao,
    removeVariacao,
    updateVariacao,
    generateVariacaoLetters,
    constants,
    onAddSample,
}) {
    const sampleTypes = constants?.sample_tipos || [];
    const sampleUnits = constants?.sample_unidades || [];
    const variationParams = constants?.sample_parametros_variacao || [];

    const updateSample = (index, field, value) => {
        const next = [...batchSamples];
        next[index] = { ...next[index], [field]: value };
        setBatchSamples(next);
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-5xl max-h-[92vh] flex flex-col p-0 overflow-hidden">
                <DialogHeader className="p-6 pb-3 border-b bg-gradient-to-r from-primary/5 to-primary/10">
                    <DialogTitle className="font-heading text-2xl">Criar Amostras em Lote</DialogTitle>
                    <p className="text-sm text-muted-foreground">
                        Cada amostra recebe numeração global e pode gerar variações independentes.
                    </p>
                </DialogHeader>

                <div className="flex-1 min-h-0 overflow-y-auto px-6 py-4">
                    <div className="space-y-6">
                        {batchSamples.map((sample, sampleIndex) => (
                            <div key={sampleIndex} className="rounded-2xl border border-border bg-card p-5 space-y-5">
                                <div className="flex items-center justify-between">
                                    <div>
                                        <h3 className="text-lg font-semibold">Amostra {sampleIndex + 1}</h3>
                                        <p className="text-xs text-muted-foreground">
                                            {sample.variacoes?.length || 0} variação(ões)
                                        </p>
                                    </div>
                                    {batchSamples.length > 1 && (
                                        <Button
                                            variant="ghost"
                                            size="sm"
                                            onClick={() => setBatchSamples(batchSamples.filter((_, index) => index !== sampleIndex))}
                                        >
                                            <Trash2 className="h-4 w-4 text-red-500" />
                                        </Button>
                                    )}
                                </div>

                                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                                    <div className="space-y-2 md:col-span-2">
                                        <Label>Nome do produto *</Label>
                                        <Input
                                            placeholder="Ex: Body Splash 300ml"
                                            value={sample.nome_produto || ""}
                                            onChange={(event) => updateSample(sampleIndex, "nome_produto", event.target.value)}
                                        />
                                    </div>
                                    <div className="space-y-2">
                                        <Label>Tipo de amostra *</Label>
                                        <Select
                                            value={sample.tipo_amostra || ""}
                                            onValueChange={(value) => updateSample(sampleIndex, "tipo_amostra", value)}
                                        >
                                            <SelectTrigger><SelectValue placeholder="Selecionar" /></SelectTrigger>
                                            <SelectContent>
                                                {sampleTypes.map((option) => (
                                                    <SelectItem key={option} value={option}>{formatSlugLabel(option)}</SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                    <div className="space-y-2">
                                        <Label><FieldHint hint="Define o critério que diferencia cada variação de amostra: fragrância, cor, concentração, etc.">Parâmetro de variação</FieldHint></Label>
                                        <Select
                                            value={sample.parametro_variacao || "nenhuma"}
                                            onValueChange={(value) => updateSample(sampleIndex, "parametro_variacao", value === "nenhuma" ? "" : value)}
                                        >
                                            <SelectTrigger><SelectValue placeholder="Selecionar" /></SelectTrigger>
                                            <SelectContent>
                                                <SelectItem value="nenhuma">Nenhuma</SelectItem>
                                                {variationParams.map((option) => (
                                                    <SelectItem key={option} value={option}>{formatSlugLabel(option)}</SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                    {sample.parametro_variacao && sample.parametro_variacao !== "" && (
                                    <div className="space-y-2">
                                        <Label><FieldHint hint="Quantidade de unidades produzidas para cada variação desta amostra.">Quantidade por variação *</FieldHint></Label>
                                        <Input
                                            type="number"
                                            value={sample.quantidade_por_variacao || ""}
                                            onChange={(event) => updateSample(sampleIndex, "quantidade_por_variacao", event.target.value)}
                                        />
                                    </div>
                                    )}
                                    {sample.parametro_variacao && sample.parametro_variacao !== "" && (
                                    <div className="space-y-2">
                                        <Label><FieldHint hint="Unidade de medida da quantidade por variação (g = gramas, mL = mililitros, un = unidades).">Unidade</FieldHint></Label>
                                        <Select
                                            value={sample.unidade_quantidade || "g"}
                                            onValueChange={(value) => updateSample(sampleIndex, "unidade_quantidade", value)}
                                        >
                                            <SelectTrigger><SelectValue placeholder="Selecionar" /></SelectTrigger>
                                            <SelectContent>
                                                {sampleUnits.map((option) => (
                                                    <SelectItem key={option} value={option}>{option}</SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                    )}
                                    <div className="space-y-2">
                                        <Label>Prazo de entrega ao cliente *</Label>
                                        <Input
                                            type="date"
                                            value={sample.prazo_entrega_cliente || ""}
                                            onChange={(event) => updateSample(sampleIndex, "prazo_entrega_cliente", event.target.value)}
                                        />
                                    </div>
                                    <div className="space-y-2">
                                        <Label>Referência de fórmula</Label>
                                        <Input
                                            placeholder="Obrigatória em adaptação"
                                            value={sample.referencia_formula || ""}
                                            onChange={(event) => updateSample(sampleIndex, "referencia_formula", event.target.value)}
                                        />
                                    </div>
                                    <div className="space-y-2 md:col-span-2">
                                        <Label>Briefing base</Label>
                                        <Textarea
                                            rows={3}
                                            value={sample.briefing_base || ""}
                                            onChange={(event) => updateSample(sampleIndex, "briefing_base", event.target.value)}
                                        />
                                    </div>
                                    <div className="space-y-2 md:col-span-2">
                                        <Label>Briefing específico da amostra</Label>
                                        <Textarea
                                            rows={3}
                                            value={sample.briefing_especifico || ""}
                                            onChange={(event) => updateSample(sampleIndex, "briefing_especifico", event.target.value)}
                                        />
                                    </div>
                                </div>

                                <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-4 space-y-4">
                                    <div className="flex items-center justify-between">
                                        <div>
                                            <h4 className="text-sm font-semibold text-emerald-700">Variações</h4>
                                            <p className="text-xs text-emerald-700/80">
                                                Códigos previstos: {generateVariacaoLetters(sample.variacoes?.length || 0).map((letter) => `/${letter}`).join(" ")}
                                            </p>
                                        </div>
                                        <Button variant="outline" size="sm" onClick={() => addVariacao(sampleIndex)}>
                                            <Plus className="h-3.5 w-3.5 mr-1" /> Adicionar variação
                                        </Button>
                                    </div>

                                    <div className="space-y-3">
                                        {(sample.variacoes || []).map((variacao, variacaoIndex) => (
                                            <div key={variacaoIndex} className="rounded-lg border border-emerald-200 bg-background p-3 space-y-3">
                                                <div className="flex items-center justify-between">
                                                    <span className="text-xs font-semibold text-emerald-700">
                                                        Variação {generateVariacaoLetters(sample.variacoes.length)[variacaoIndex]}
                                                    </span>
                                                    {sample.variacoes.length > 1 && (
                                                        <Button variant="ghost" size="sm" onClick={() => removeVariacao(sampleIndex, variacaoIndex)}>
                                                            <Trash2 className="h-3.5 w-3.5 text-red-500" />
                                                        </Button>
                                                    )}
                                                </div>
                                                <Input
                                                    placeholder="Descrição da variação"
                                                    value={variacao.descricao_aplicacao || ""}
                                                    onChange={(event) => updateVariacao(sampleIndex, variacaoIndex, "descricao_aplicacao", event.target.value)}
                                                />
                                                <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
                                                    <Input
                                                        type="number"
                                                        placeholder="% fragrância"
                                                        value={variacao.percentual_fragrancia || ""}
                                                        onChange={(event) => updateVariacao(sampleIndex, variacaoIndex, "percentual_fragrancia", event.target.value)}
                                                    />
                                                    <Input
                                                        placeholder="Ref. fragrância"
                                                        value={variacao.referencia_fragrancia || ""}
                                                        onChange={(event) => updateVariacao(sampleIndex, variacaoIndex, "referencia_fragrancia", event.target.value)}
                                                    />
                                                    <Input
                                                        type="number"
                                                        placeholder="Custo"
                                                        value={variacao.custo_fragrancia || ""}
                                                        onChange={(event) => updateVariacao(sampleIndex, variacaoIndex, "custo_fragrancia", event.target.value)}
                                                    />
                                                </div>
                                                <Textarea
                                                    rows={2}
                                                    placeholder="Observações específicas"
                                                    value={variacao.observacoes_especificas || ""}
                                                    onChange={(event) => updateVariacao(sampleIndex, variacaoIndex, "observacoes_especificas", event.target.value)}
                                                />
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>

                    <Button variant="outline" className="w-full mt-6" onClick={() => onAddSample ? onAddSample() : setBatchSamples([...batchSamples, {
                        nome_produto: "",
                        categoria: "",
                        briefing_base: "",
                        responsavel_pd: "",
                        parametro_variacao: "",
                        tipo_amostra: "",
                        referencia_formula: "",
                        quantidade_por_variacao: "",
                        unidade_quantidade: "g",
                        prazo_entrega_cliente: "",
                        briefing_especifico: "",
                        feedback_cliente: "",
                        direcoes_retrabalho: "",
                        resultado: "",
                        produto: "",
                        objetivo_projeto: "",
                        aplicacoes_desenvolver: "",
                        ativos_claims: "",
                        referencias: "",
                        referencias_fotos: [],
                        orcamento_projeto: "",
                        textura_esperada: "",
                        aplicacao: "",
                        sensorial: "",
                        ph: "",
                        observacao_tecnica: "",
                        variacoes: [{ descricao_aplicacao: "", percentual_fragrancia: "", referencia_fragrancia: "", custo_fragrancia: "", observacoes_especificas: "" }],
                    }])}>
                        <Plus className="h-4 w-4 mr-2" /> Adicionar Outra Amostra
                    </Button>
                </div>

                <DialogFooter className="p-6 pt-3 border-t">
                    <Button variant="outline" onClick={() => onOpenChange(false)}>Cancelar</Button>
                    <Button onClick={onSubmit}>
                        Criar {batchSamples.filter((sample) => sample.nome_produto?.trim()).length} amostra(s)
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
