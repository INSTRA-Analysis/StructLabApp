# StructLab — Roadmap

## Online / Web Hosting Strategy

### Context
The desktop app is growing (466 MB packaged) and distribution via .exe is becoming impractical for wide peer/client access. The goal is to make StructLab accessible online — no installation, just a URL — for both technical users (API/scripts) and non-technical engineers (interactive canvas in browser). The solver core is already clean and Qt-free, making the backend layer straightforward. The interactive canvas is the main challenge.

---

### Phase 1 — FastAPI backend (1–2 days)

Wrap `sdk.py` in a FastAPI server. Gives engineers an API URL immediately, and is the foundation for the web frontend. No changes to the desktop app.

**Endpoints (`api/main.py`):**
```
POST /solve          → { model_json } → { reactions, displacements, member_forces }
POST /solve/diagram  → { model_json, kind } → PNG image (BMD/SFD/AFD)
POST /solve/report   → { model_json } → PDF bytes
GET  /health         → { status: "ok", version: "1.1" }
```

**Input:** same `.slab` JSON format the desktop app already saves (`ModelState.to_dict()`).

**Deployment:** Railway or Render (free tier, ~512 MB RAM is enough for the solver).

**Files to create:**
| File | Purpose |
|------|---------|
| `api/main.py` | FastAPI app — routes and request handling |
| `api/schemas.py` | Pydantic models for request/response validation |
| `api/solver_bridge.py` | `ModelState.from_dict` → solve → serialise results |

---

### Phase 2 — Web frontend with interactive canvas (weeks)

A browser-based structural editor that calls the Phase 1 API to solve.

**Tech stack:**
- **React** — UI framework
- **Konva.js** — 2D interactive canvas (nodes, members, loads, supports)
- **Three.js** — 3D view (replicates `projection.py` az-el logic in JS)
- **Vercel** — frontend hosting (free tier)

**Canvas features (priority order):**
1. Draw nodes (click to place)
2. Draw members (click node → click node)
3. Set supports (right-click menu)
4. Add loads (panel form)
5. Solve button → POST to API → display reactions/diagrams
6. BMD/SFD overlay on members (SVG paths)
7. 3D isometric view

**Data bridge:** canvas state serialises to `.slab` JSON → sent to API → results back. No new format needed.

**Deployment:** backend on Railway/Render (~$5–7/month after free tier), frontend on Vercel (free).

**Files to create:**
| File | Purpose |
|------|---------|
| `web/src/canvas/Canvas2D.jsx` | Konva.js 2D editor |
| `web/src/canvas/Canvas3D.jsx` | Three.js 3D view |
| `web/src/api/client.js` | fetch wrapper for the FastAPI endpoints |

---

### What stays the same
- Desktop app continues to work exactly as-is
- `sdk.py` unchanged — used by both API and desktop app
- `.slab` file format is the API's JSON contract — no duplication

---

### Recommended order
1. **Phase 1** — FastAPI backend + deploy → share API URL with reviewers immediately
2. **Phase 2a** — React + Konva.js 2D canvas (basic node/member/solve loop)
3. **Phase 2b** — 3D view, load combinations, PDF report, user accounts
