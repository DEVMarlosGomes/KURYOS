const envBackendUrl = process.env.REACT_APP_BACKEND_URL?.trim();

function getLocalDevBackendUrl() {
    if (typeof window === "undefined") return "http://127.0.0.1:8000";

    const { protocol, hostname, port, origin } = window.location;

    if (port === "3000") {
        return `${protocol}//${hostname}:8000`;
    }

    return origin;
}

export const BACKEND_URL = envBackendUrl || getLocalDevBackendUrl();

export const WS_BACKEND_URL = BACKEND_URL
    ? BACKEND_URL.replace("https://", "wss://").replace("http://", "ws://")
    : "";
