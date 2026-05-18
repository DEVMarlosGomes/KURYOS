import axios from "axios";
import { BACKEND_URL, BACKEND_URL_CANDIDATES, rememberBackendUrl } from "@/lib/backend";

const candidateApiBaseUrls = [...new Set(
    BACKEND_URL_CANDIDATES.map((url) => `${url}/api`)
)];

const api = axios.create({
    baseURL: `${BACKEND_URL}/api`,
    withCredentials: true,
    headers: { "Content-Type": "application/json" },
});

function isNetworkError(error) {
    return !error?.response && (!!error?.request || error?.code === "ERR_NETWORK");
}

function rememberFromBaseUrl(baseUrl) {
    if (!baseUrl) return;
    rememberBackendUrl(baseUrl.replace(/\/api$/, ""));
}

api.interceptors.response.use(
    (response) => {
        rememberFromBaseUrl(response.config?.baseURL || api.defaults.baseURL);
        return response;
    },
    async (error) => {
        const config = error?.config;

        if (!config || config._backendFallbackTried || !isNetworkError(error)) {
            return Promise.reject(error);
        }

        const currentBaseUrl = config.baseURL || api.defaults.baseURL;
        const fallbackBaseUrl = candidateApiBaseUrls.find((url) => url !== currentBaseUrl);

        if (!fallbackBaseUrl) {
            return Promise.reject(error);
        }

        config._backendFallbackTried = true;
        config.baseURL = fallbackBaseUrl;
        const previousBaseUrl = api.defaults.baseURL;
        api.defaults.baseURL = fallbackBaseUrl;

        try {
            return await api.request(config);
        } catch (fallbackError) {
            api.defaults.baseURL = previousBaseUrl;
            return Promise.reject(fallbackError);
        }
    }
);

export function formatApiError(detail) {
    if (detail == null) return "Nao foi possivel conectar ao backend.";
    if (detail?.code === "ERR_NETWORK" || detail?.request) return "Nao foi possivel conectar ao backend.";
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail))
        return detail.map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e))).filter(Boolean).join(" ");
    if (detail && typeof detail.msg === "string") return detail.msg;
    if (detail && typeof detail.message === "string") return detail.message;
    return String(detail);
}

export default api;
