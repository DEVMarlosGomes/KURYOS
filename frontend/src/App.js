import { useEffect, useState } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "@/contexts/AuthContext";
import LoginPage from "@/pages/LoginPage";
import DashboardPage from "@/pages/DashboardPage";
import PipelinePage from "@/pages/PipelinePage";
import TeamPage from "@/pages/TeamPage";
import PDPage from "@/pages/PDPage";
import PDDetail from "@/pages/PDDetail";
import PDCatalog from "@/pages/PDCatalog";
import PDStock from "@/pages/PDStock";
import PDFormulaBank from "@/pages/PDFormulaBank";
import PDHomologacao from "@/pages/PDHomologacao";
import PDReports from "@/pages/PDReports";
import CRM1Page from "@/pages/CRM1Page";
import CRM2Page from "@/pages/CRM2Page";
import CRM3Page from "@/pages/CRM3Page";
import KickoffPage from "@/pages/KickoffPage";
import KickoffsListPage from "@/pages/KickoffsListPage";
import SKUsPage from "@/pages/SKUsPage";
import TasksPage from "@/pages/TasksPage";
import AuditLogPage from "@/pages/AuditLogPage";
import CQDashboard from "@/pages/CQDashboard";
import CQListaRA from "@/pages/CQListaRA";
import CQDetalheRA from "@/pages/CQDetalheRA";
import CQListaChecklists from "@/pages/CQListaChecklists";
import CQPreencherChecklist from "@/pages/CQPreencherChecklist";
import CQListaRNCs from "@/pages/CQListaRNCs";
import CQDetalheRNC from "@/pages/CQDetalheRNC";
import CQRetencoes from "@/pages/CQRetencoes";
import CQDetalheRetencao from "@/pages/CQDetalheRetencao";
import CQInstrumentos from "@/pages/CQInstrumentos";
import OrdersPage from "@/pages/OrdersPage";
import OrderDetail from "@/pages/OrderDetail";
import OPPage from "@/pages/OPPage";
import OPDetail from "@/pages/OPDetail";
import ComprasPage from "@/pages/ComprasPage";
import ComprasDashboard from "@/pages/ComprasDashboard";
import ComprasFornecedores from "@/pages/ComprasFornecedores";
import ComprasFornecedorDetalhe from "@/pages/ComprasFornecedorDetalhe";
import ComprasItens from "@/pages/ComprasItens";
import ComprasItemDetalhe from "@/pages/ComprasItemDetalhe";
import ComprasMRP from "@/pages/ComprasMRP";
import ComprasMRPRevisao from "@/pages/ComprasMRPRevisao";
import ComprasCotacao from "@/pages/ComprasCotacao";
import ComprasPOLista from "@/pages/ComprasPOLista";
import ComprasPODetalhe from "@/pages/ComprasPODetalhe";
import ComprasEstoqueProjetado from "@/pages/ComprasEstoqueProjetado";
import EstoquePage from "@/pages/EstoquePage";
import MovimentacaoPage from "@/pages/MovimentacaoPage";
import RecebimentoPage from "@/pages/RecebimentoPage";
import CQRetrabalho from "@/pages/CQRetrabalho";
import ExpedicaoPage from "@/pages/ExpedicaoPage";
import FaturamentoPage from "@/pages/FaturamentoPage";
import PCPPage from "@/pages/PCPPage";
import ContratosPage from "@/pages/ContratosPage";
import Sidebar from "@/components/Sidebar";
import RoleGuard, { ROLE_GROUPS } from "@/components/RoleGuard";
import { Toaster } from "@/components/ui/sonner";

function ThemeProvider({ children }) {
    const [dark, setDark] = useState(() => localStorage.getItem("theme") === "dark");

    useEffect(() => {
        document.documentElement.classList.toggle("dark", dark);
        localStorage.setItem("theme", dark ? "dark" : "light");
    }, [dark]);

    return (
        <ThemeCtx.Provider value={{ dark, setDark }}>
            {children}
        </ThemeCtx.Provider>
    );
}

import { createContext, useContext } from "react";
const ThemeCtx = createContext({ dark: false, setDark: () => {} });
export const useTheme = () => useContext(ThemeCtx);

function ProtectedRoute({ children }) {
    const { user, loading } = useAuth();
    if (loading) return (
        <div className="h-screen flex items-center justify-center bg-background" data-testid="loading-screen">
            <div className="animate-spin h-8 w-8 border-2 border-primary border-t-transparent rounded-full" />
        </div>
    );
    if (!user) return <Navigate to="/login" replace />;
    return children;
}

function AppLayout() {
    const COMERCIAL = ROLE_GROUPS.COMERCIAL_FULL;
    const PD_READ = ROLE_GROUPS.PD_READ;
    const PD_FULL = ROLE_GROUPS.PD_FULL;
    const ADMIN_ONLY = ROLE_GROUPS.ADMIN_ONLY;
    const AUDIT_ROLES = [...ROLE_GROUPS.DOC_REVIEWERS, "sales_ops"];
    const KICKOFF_ROLES = [...new Set([...COMERCIAL, ...PD_FULL])];
    const CQ_ROLES = ["admin", "qa", "lider_pd", "formulador", "engenharia_produto", "compras", "sales_ops"];
    const COMPRAS_ROLES = ["admin", "compras", "engenharia_produto", "lider_pd", "qa", "sales_ops"];
    const CONTRATOS_ROLES = ["admin", "sales_ops", "vendedor", "compras", "lider_pd", "qa", "engenharia_produto", "sucesso_cliente"];

    return (
        <div className="flex min-h-screen md:h-screen overflow-hidden bg-background">
            <Sidebar />
            <main className="flex-1 overflow-auto pt-14 md:pt-0">
                <Routes>
                    <Route path="/" element={<Navigate to="/tasks" replace />} />
                    <Route path="/dashboard" element={<DashboardPage />} />
                    <Route path="/pipeline" element={<RoleGuard allowed={COMERCIAL}><PipelinePage /></RoleGuard>} />
                    <Route path="/crm/clients" element={<RoleGuard allowed={COMERCIAL}><CRM1Page /></RoleGuard>} />
                    <Route path="/crm/projects" element={<RoleGuard allowed={COMERCIAL}><CRM2Page /></RoleGuard>} />
                    <Route path="/crm/samples" element={<RoleGuard allowed={COMERCIAL}><CRM3Page /></RoleGuard>} />
                    <Route path="/kickoffs" element={<RoleGuard allowed={KICKOFF_ROLES}><KickoffsListPage /></RoleGuard>} />
                    <Route path="/kickoff/:id" element={<RoleGuard allowed={KICKOFF_ROLES}><KickoffPage /></RoleGuard>} />
                    <Route path="/crm/skus" element={<RoleGuard allowed={[...PD_READ, ...COMERCIAL]}><SKUsPage /></RoleGuard>} />
                    <Route path="/pd" element={<RoleGuard allowed={PD_READ}><PDPage /></RoleGuard>} />
                    <Route path="/pd/formulas" element={<RoleGuard allowed={PD_READ}><PDFormulaBank /></RoleGuard>} />
                    <Route path="/pd/homologacao" element={<RoleGuard allowed={PD_FULL}><PDHomologacao /></RoleGuard>} />
                    <Route path="/homologacoes" element={<RoleGuard allowed={PD_FULL}><PDHomologacao /></RoleGuard>} />
                    <Route path="/pd/catalog" element={<RoleGuard allowed={PD_FULL}><PDCatalog /></RoleGuard>} />
                    <Route path="/pd/estoque" element={<RoleGuard allowed={PD_FULL}><PDStock /></RoleGuard>} />
                    <Route path="/pd/relatorios" element={<RoleGuard allowed={PD_READ}><PDReports /></RoleGuard>} />
                    <Route path="/pd/:id" element={<RoleGuard allowed={PD_READ}><PDDetail /></RoleGuard>} />
                    <Route path="/tasks" element={<TasksPage />} />
                    <Route path="/orders" element={<OrdersPage />} />
                    <Route path="/orders/:id" element={<OrderDetail />} />
                    <Route path="/ops" element={<OPPage />} />
                    <Route path="/ops/:id" element={<OPDetail />} />
                    <Route path="/pcp" element={<PCPPage />} />
                    <Route path="/expedicao" element={<ExpedicaoPage />} />
                    <Route path="/faturamento" element={<FaturamentoPage />} />
                    <Route path="/compras" element={<RoleGuard allowed={COMPRAS_ROLES}><ComprasDashboard /></RoleGuard>} />
                    <Route path="/compras/fornecedores" element={<RoleGuard allowed={COMPRAS_ROLES}><ComprasFornecedores /></RoleGuard>} />
                    <Route path="/compras/fornecedores/:id" element={<RoleGuard allowed={COMPRAS_ROLES}><ComprasFornecedorDetalhe /></RoleGuard>} />
                    <Route path="/compras/itens" element={<RoleGuard allowed={COMPRAS_ROLES}><ComprasItens /></RoleGuard>} />
                    <Route path="/compras/itens/:id" element={<RoleGuard allowed={COMPRAS_ROLES}><ComprasItemDetalhe /></RoleGuard>} />
                    <Route path="/compras/mrp" element={<RoleGuard allowed={COMPRAS_ROLES}><ComprasMRP /></RoleGuard>} />
                    <Route path="/compras/mrp/:id" element={<RoleGuard allowed={COMPRAS_ROLES}><ComprasMRPRevisao /></RoleGuard>} />
                    <Route path="/compras/cotacao/:demanda_id" element={<RoleGuard allowed={COMPRAS_ROLES}><ComprasCotacao /></RoleGuard>} />
                    <Route path="/compras/pos" element={<RoleGuard allowed={COMPRAS_ROLES}><ComprasPOLista /></RoleGuard>} />
                    <Route path="/compras/pos/:id" element={<RoleGuard allowed={COMPRAS_ROLES}><ComprasPODetalhe /></RoleGuard>} />
                    <Route path="/compras/estoque-projetado" element={<RoleGuard allowed={COMPRAS_ROLES}><ComprasEstoqueProjetado /></RoleGuard>} />
                    <Route path="/estoque" element={<EstoquePage />} />
                    <Route path="/estoque/movimentacao" element={<MovimentacaoPage />} />
                    <Route path="/recebimento" element={<RecebimentoPage />} />
                    <Route path="/contratos" element={<RoleGuard allowed={CONTRATOS_ROLES}><ContratosPage /></RoleGuard>} />
                    <Route path="/audit" element={<RoleGuard allowed={AUDIT_ROLES}><AuditLogPage /></RoleGuard>} />
                    <Route path="/cq" element={<RoleGuard allowed={CQ_ROLES}><CQDashboard /></RoleGuard>} />
                    <Route path="/cq/registros-analise" element={<RoleGuard allowed={CQ_ROLES}><CQListaRA /></RoleGuard>} />
                    <Route path="/cq/registros-analise/:id" element={<RoleGuard allowed={CQ_ROLES}><CQDetalheRA /></RoleGuard>} />
                    <Route path="/cq/checklists" element={<RoleGuard allowed={CQ_ROLES}><CQListaChecklists /></RoleGuard>} />
                    <Route path="/cq/checklists/:id" element={<RoleGuard allowed={CQ_ROLES}><CQPreencherChecklist /></RoleGuard>} />
                    <Route path="/cq/rncs" element={<RoleGuard allowed={CQ_ROLES}><CQListaRNCs /></RoleGuard>} />
                    <Route path="/cq/rncs/:id" element={<RoleGuard allowed={CQ_ROLES}><CQDetalheRNC /></RoleGuard>} />
                    <Route path="/cq/retencoes" element={<RoleGuard allowed={CQ_ROLES}><CQRetencoes /></RoleGuard>} />
                    <Route path="/cq/retencoes/:id" element={<RoleGuard allowed={CQ_ROLES}><CQDetalheRetencao /></RoleGuard>} />
                    <Route path="/cq/instrumentos" element={<RoleGuard allowed={CQ_ROLES}><CQInstrumentos /></RoleGuard>} />
                    <Route path="/cq/retrabalho" element={<RoleGuard allowed={CQ_ROLES}><CQRetrabalho /></RoleGuard>} />
                    <Route path="/team" element={<RoleGuard allowed={ADMIN_ONLY}><TeamPage /></RoleGuard>} />
                </Routes>
            </main>
        </div>
    );
}

function App() {
    return (
        <ThemeProvider>
            <AuthProvider>
                <BrowserRouter>
                    <Routes>
                        <Route path="/login" element={<LoginPage />} />
                        <Route path="/*" element={
                            <ProtectedRoute>
                                <AppLayout />
                            </ProtectedRoute>
                        } />
                    </Routes>
                </BrowserRouter>
                <Toaster position="top-right" />
            </AuthProvider>
        </ThemeProvider>
    );
}

export default App;
