// Auto-select API base URL based on the frontend host:
// - Local development (localhost / 127.0.0.1) -> local uvicorn on port 8080
// - Hosted frontend (e.g. Vercel) -> production backend
(function () {
    const host = window.location.hostname;
    const isLocal = host === "localhost" || host === "127.0.0.1" || host === "";
    window.API_BASE_URL = isLocal
        ? "http://localhost:8080"
        : "https://p01--signal--lghsj7pqqwxd.code.run";
})();
