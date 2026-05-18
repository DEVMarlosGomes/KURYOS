const envBackendUrl = process.env.REACT_APP_BACKEND_URL?.trim();
const STORAGE_KEY = "kuryos.backend_url";

function normalizeUrl(url) {
    return typeof url === "string" ? url.trim().replace(/\/+$/, "") : "";
}

function getStoredBackendUrl() {
    if (typeof window === "undefined") return "";
    try {
        return normalizeUrl(window.localStorage.getItem(STORAGE_KEY));
    } catch {
        return "";
    }
}

export function rememberBackendUrl(url) {
    const normalized = normalizeUrl(url);
    if (!normalized || typeof window === "undefined") return;
    try {
        window.localStorage.setItem(STORAGE_KEY, normalized);
    } catch {}
}

function getLocalDevBackendUrls() {
    if (typeof window === "undefined") {
        return ["http://127.0.0.1:8000", "http://127.0.0.1:8001"];
    }

    const { protocol, hostname, port, origin } = window.location;
    const hosts = hostname === "localhost"
        ? ["localhost", "127.0.0.1"]
        : hostname === "127.0.0.1"
            ? ["127.0.0.1", "localhost"]
            : [hostname];

    if (port === "3000") {
        return hosts.flatMap((host) => [
            `${protocol}//${host}:8000`,
            `${protocol}//${host}:8001`,
        ]);
    }

    return [origin];
}

function unique(values) {
    return [...new Set(values.map(normalizeUrl).filter(Boolean))];
}

export function getBackendCandidates() {
    return unique([
        envBackendUrl,
        getStoredBackendUrl(),
        ...getLocalDevBackendUrls(),
    ]);
}

export function getCurrentBackendUrl() {
    return getBackendCandidates()[0] || "";
}

export function toWebSocketUrl(baseUrl) {
    const normalized = normalizeUrl(baseUrl);
    return normalized
        ? normalized.replace("https://", "wss://").replace("http://", "ws://")
        : "";
}

export const BACKEND_URL_CANDIDATES = getBackendCandidates();
export const BACKEND_URL = getCurrentBackendUrl();
export const WS_BACKEND_URL = toWebSocketUrl(BACKEND_URL);
