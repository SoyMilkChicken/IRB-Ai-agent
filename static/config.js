// Frontend runtime config.
// Leave apiBaseUrl empty for local same-origin usage (Python server serves UI + API together).
// For split deployment (GitHub Pages frontend + hosted backend), set apiBaseUrl to your backend URL.
// Optional: set backendApiKey only for private demos/testing. Do not expose production secrets in public static sites.
window.IRB_COPILOT_CONFIG = {
  apiBaseUrl: "",
  backendApiKey: "",
};
