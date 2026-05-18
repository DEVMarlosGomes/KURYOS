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
import OrdersPage from "@/pages/OrdersPage";
import OrderDetail from "@/pages/OrderDetail";
import ComprasPage from "@/pages/ComprasPage";
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
                    <Route path="/compras" element={<RoleGuard allowed={COMPRAS_ROLES}><ComprasPage /></RoleGuard>} />
                    <Route path="/contratos" element={<RoleGuard allowed={CONTRATOS_ROLES}><ContratosPage /></RoleGuard>} />
                    <Route path="/audit" element={<RoleGuard allowed={AUDIT_ROLES}><AuditLogPage /></RoleGuard>} />
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
