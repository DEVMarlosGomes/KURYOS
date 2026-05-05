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
import SKUsPage from "@/pages/SKUsPage";
import TasksPage from "@/pages/TasksPage";
import AuditLogPage from "@/pages/AuditLogPage";
import Sidebar from "@/components/Sidebar";
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
    return (
        <div className="flex h-screen overflow-hidden bg-background">
            <Sidebar />
            <main className="flex-1 overflow-auto">
                <Routes>
                    <Route path="/" element={<Navigate to="/dashboard" replace />} />
                    <Route path="/dashboard" element={<DashboardPage />} />
                    <Route path="/pipeline" element={<PipelinePage />} />
                    <Route path="/crm/clients" element={<CRM1Page />} />
                    <Route path="/crm/projects" element={<CRM2Page />} />
                    <Route path="/crm/samples" element={<CRM3Page />} />
                    <Route path="/crm/skus" element={<SKUsPage />} />
                    <Route path="/pd" element={<PDPage />} />
                    <Route path="/pd/formulas" element={<PDFormulaBank />} />
                    <Route path="/pd/homologacao" element={<PDHomologacao />} />
                    <Route path="/pd/catalog" element={<PDCatalog />} />
                    <Route path="/pd/estoque" element={<PDStock />} />
                    <Route path="/pd/relatorios" element={<PDReports />} />
                    <Route path="/pd/:id" element={<PDDetail />} />
                    <Route path="/tasks" element={<TasksPage />} />
                    <Route path="/audit" element={<AuditLogPage />} />
                    <Route path="/team" element={<TeamPage />} />
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
