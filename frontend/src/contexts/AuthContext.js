import { createContext, useContext, useState, useEffect, useCallback } from "react";
import api, { formatApiError } from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);

    const checkAuth = useCallback(async () => {
        try {
            const { data } = await api.get("/auth/me");
            setUser(data);
        } catch {
            setUser(false);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { checkAuth(); }, [checkAuth]);

    const login = async (email, password) => {
        try {
            const { data } = await api.post("/auth/login", { email, password });
            setUser(data);
            return { success: true };
        } catch (e) {
            return { success: false, error: formatApiError(e.response?.data?.detail ?? e) };
        }
    };

    const register = async (email, password, name, org_name) => {
        try {
            const { data } = await api.post("/auth/register", { email, password, name, org_name });
            setUser(data);
            return { success: true };
        } catch (e) {
            return { success: false, error: formatApiError(e.response?.data?.detail ?? e) };
        }
    };

    const logout = async () => {
        try { await api.post("/auth/logout"); } catch {}
        setUser(false);
    };

    return (
        <AuthContext.Provider value={{ user, loading, login, register, logout }}>
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    const ctx = useContext(AuthContext);
    if (!ctx) throw new Error("useAuth must be used within AuthProvider");
    return ctx;
}
