# IRB Copilot MVP (AI IRB Assistance Tool)

Minimal MVP for an IRB assistance tool focused on pre-screening and drafting support for studies like your AI grading research project.

This is **not** an IRB approval tool. It helps users:

- run a rule-based IRB risk pre-screen
- generate draft consent / recruitment / data-handling language
- rewrite draft text to be less coercive or clearer
- export a draft bundle for human review

## What is included

- `server.py`: dependency-free Python server (static UI + JSON API)
- `static/index.html`: wizard interface
- `static/app.js`: UI logic (form capture, flags, drafting, rewrite, export)
- `static/styles.css`: MVP styling

## Run locally

Requirements: Python 3.10+ (works with standard library only)

```bash
python3 server.py
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000)

## AI modes

The app supports two modes:

1. `Template fallback` (default)
- No API key required
- Generates structured draft templates and rule-based rewrites
- Useful for demos and workflow testing

2. `OpenAI-backed drafting/rewrite` (optional)
- Set environment variables before running:

```bash
export OPENAI_API_KEY="your_key_here"
export OPENAI_MODEL="gpt-4.1-mini"   # optional
python3 server.py
```

Optional advanced override:

- `OPENAI_CHAT_API_URL` (defaults to `https://api.openai.com/v1/chat/completions`)

## MVP workflow (implemented)

1. `Project Intake`
- Study details + collection methods

2. `Recruitment & Participants`
- Power dynamics, extra credit, grade impact, minors

3. `Data & Privacy`
- Identifiers, education records, de-identification, storage/access/retention

4. `IRB Risk Flags`
- Rule-based pre-screen flags (FERPA risk, coercion, grade impact, etc.)

5. `Drafting Studio`
- Generate `consent`, `recruitment`, `data handling`
- Rewrite draft text: `Less Coercive`, `Clearer`
- Export draft bundle (`.txt`) after human review acknowledgement

## Current limitations (expected for MVP)

- No authentication / multi-user accounts
- No database persistence (uses browser localStorage only)
- No institution-specific IRB form mapping yet
- No direct upload/parse of IRB PDF forms
- No auto-submission to IRB portals

## Recommended next build steps

1. Add institution-specific form mapping (field-by-field)
2. Add project persistence (Postgres / Supabase)
3. Add document upload + section comparison
4. Add advisor review workflow and version tracking
5. Add role-based access and secure storage controls

## Deployment (simple path)

- Frontend + backend together on a small VM/container (Python)
- Or split later into:
  - Frontend: Next.js (Vercel)
  - Backend: FastAPI/Node (Render/Railway/Fly)
  - DB: Postgres (Supabase/Neon)

If you want, the next step can be a `production-oriented architecture` version (Next.js + API + DB schema) while preserving this MVP workflow and rules.
