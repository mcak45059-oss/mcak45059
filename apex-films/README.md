# Apex Films — Landing Page

Done-for-you video editing studio landing page with a waitlist signup.

## Run locally

```bash
cd apex-films
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python waitlist_server.py
```

Open http://localhost:5000. Form submissions are appended to `waitlist.jsonl` (gitignored).

Env vars: `PORT` (default `5000`), `WAITLIST_FILE` (default `./waitlist.jsonl`).

## Inspect the waitlist

```bash
cat waitlist.jsonl | jq .
```

## Deploy

### Static-only (Netlify, Vercel, GitHub Pages, S3, Cloudflare Pages)
Upload `index.html`, `styles.css`, `app.js`. The form will fall back to a `mailto:` link when no backend is reachable, so you still capture leads.

### Static + backend
Run `waitlist_server.py` behind any process manager (systemd, Docker, fly.io, Render). The server also serves the static files, so a single process is enough. Put it behind a reverse proxy with TLS for production.

## File map

| File | Purpose |
|------|---------|
| `index.html` | Hero, services, process, pricing, waitlist, FAQ |
| `styles.css` | Dark cinematic theme, mobile-first |
| `app.js` | Form submit → `POST /api/waitlist`, `mailto:` fallback |
| `waitlist_server.py` | Flask backend, stores submissions to `waitlist.jsonl` |

## Customizing

- Update the fallback email in `app.js` (`FALLBACK_EMAIL`) and the footer in `index.html`.
- Pricing and copy live entirely in `index.html` — no build step.
