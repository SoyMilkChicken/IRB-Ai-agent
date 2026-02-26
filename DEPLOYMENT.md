# Deployment Guide (Frontend + Backend)

This project supports two deployment patterns.

## 1. Single-Service Deploy (Simplest)

Deploy the entire app (`server.py` + `static/`) on one host.

Examples:

- Render web service
- Railway service
- Fly.io app
- Any VM with Python 3

Run command:

```bash
python3 server.py --host 0.0.0.0 --port $PORT
```

Notes:

- No CORS setup needed (same origin)
- Frontend automatically calls the same host's `/api/*`

## 2. GitHub Pages (Frontend) + Render (Backend)

This is the best option if you want a public demo UI without running the backend on your machine.

### Architecture

- `GitHub Pages` hosts the static frontend from `static/`
- `Render` hosts the Python API service (`/api/health`, `/api/evaluate`, `/api/draft`, `/api/rewrite`)

### A. Deploy the Backend on Render

This repo includes `/Users/stanfeng/Documents/IRB-Agent/render.yaml`.

Steps:

1. Create a new Render Blueprint service (or Web Service) from this GitHub repo.
2. Confirm the `startCommand` is:

```bash
python3 server.py --host 0.0.0.0 --port $PORT
```

3. Set environment variables in Render:

- `CORS_ALLOW_ORIGINS=https://soymilkchicken.github.io`
- `OPENAI_API_KEY=...` (optional)
- `OPENAI_MODEL=gpt-4.1-mini` (optional)

4. Deploy and copy your backend URL, for example:

- `https://irb-copilot-api.onrender.com`

5. Confirm backend health:

- `https://your-backend-url/api/health`

### B. Deploy the Frontend on GitHub Pages

This repo includes `/Users/stanfeng/Documents/IRB-Agent/.github/workflows/deploy-pages.yml` which publishes the `static/` folder to Pages.

Steps:

1. In GitHub repo settings, enable Pages with `Build and deployment -> Source: GitHub Actions`.
2. (Recommended) Add repository secret:

- `PAGES_API_BASE_URL=https://your-backend-url`

If this secret is set, the Pages workflow will inject the API base URL into `static/config.js` during deployment.

3. Push to `main`.
4. After the workflow completes, open your Pages site:

- `https://soymilkchicken.github.io/IRB-Ai-agent/`

### C. Manual Frontend API Config (Alternative to Secret)

If you do not want to use a GitHub secret, edit `/Users/stanfeng/Documents/IRB-Agent/static/config.js`:

```js
window.IRB_COPILOT_CONFIG = {
  apiBaseUrl: "https://your-backend-url",
};
```

Commit + push, then GitHub Pages will use that backend.

### D. Quick Testing Without Editing `config.js`

The frontend also supports an `apiBaseUrl` query parameter:

```text
https://soymilkchicken.github.io/IRB-Ai-agent/?apiBaseUrl=https://your-backend-url
```

The app stores that value in browser localStorage for future visits.

## CORS Notes

The backend now supports cross-origin requests for `/api/*` when `CORS_ALLOW_ORIGINS` is set.

Examples:

- Single origin:
  - `CORS_ALLOW_ORIGINS=https://soymilkchicken.github.io`
- Multiple origins:
  - `CORS_ALLOW_ORIGINS=https://soymilkchicken.github.io,https://your-custom-domain.com`

Do not use `*` in production if you later add authentication/cookies.

## Troubleshooting

### Frontend loads but banner says "Unable to reach backend"

Check:

1. Backend URL is correct (`/api/health` works directly)
2. `static/config.js` or `PAGES_API_BASE_URL` is set correctly
3. Render backend has `CORS_ALLOW_ORIGINS` set
4. The backend is awake (free-tier services may sleep)

### Drafting works locally but not on hosted backend

Check:

1. `OPENAI_API_KEY` is set on the backend host (if you want AI mode)
2. Without API key, template fallback mode should still work

### GitHub Pages deployed but assets look broken

This repo is configured to publish the `static/` directory via GitHub Actions; do not switch Pages to a different source directory unless you also update paths.
