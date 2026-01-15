# Suzent Frontend (SPA)

Development:

1. Install deps
```bash
npm install
```
2. Run dev server
```bash
npm run dev
```

API expectations (proxy or backend additions):
- POST /api/chat  (streaming, Server-Sent Events style lines starting with `data:` containing JSON objects like current Streamlit backend)
- GET /api/plan   -> { objective, tasks: [...] }

Adjust Vite proxy in `vite.config.ts` if backend runs on a different port.
