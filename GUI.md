# The AutoStorage GUI

A browser GUI for AutoStorage databases, started with `autostorage view my.db`.
This is a minimal starting point: one API endpoint and one React component.

- **Back end:** [FastAPI](https://fastapi.tiangolo.com/), in `src/autostorage/gui/`.
  `app.py` defines the JSON endpoints (under `/api/`) and serves the built front end; `cli.py` is the `autostorage view` command.
- **Front end:** [Vite](https://vite.dev/) + [React](https://react.dev/) + [Tailwind CSS](https://tailwindcss.com/), in JavaScript, in `frontend/`.
  `frontend/src/App.jsx` is the whole app for now.

Pixi installs everything, Node.js included (the `gui` environment).

## Try it

```bash
pixi run gui-demo-db   # once: write demo.db, a few small molecules
pixi run gui-api       # build the page and serve it: open http://127.0.0.1:8765
```

FastAPI's interactive API docs are at http://127.0.0.1:8765/docs.

## Edit with live reload

Keep `gui-api` running, and in a second terminal:

```bash
pixi run gui-dev   # the Vite dev server: open http://localhost:5173
```

This page reloads as you edit `frontend/src/`, and Vite forwards `/api/...` requests to FastAPI.
After editing the Python code, restart `gui-api` (which also rebuilds the page at port 8765).

## How users run it

Users run `autostorage view my.db` (`pixi run view demo.db` here). They need only Python: the built page ships inside the Python package (`autostorage[gui]`).

## Next steps

1. A detail view: click a geometry to show it, from a new `/api/geometries/{id}` endpoint.
2. A rotatable 3D view of the structure with [3Dmol.js](https://3dmol.org/) (`npm install 3dmol`, through `pixi run -e gui npm ...`).
3. [TanStack Query](https://tanstack.com/query) for data fetching, once there are several endpoints (loading and error states, caching).
4. TypeScript, with types generated from FastAPI's OpenAPI schema by `openapi-typescript`.
5. Opening it from an SSH session: a `--uds` option that serves on a Unix socket (`uvicorn.run(app, uds=...)`), forwarded with `ssh -L 8765:/path/to.sock host`.
