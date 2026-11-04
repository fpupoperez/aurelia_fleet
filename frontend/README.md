# Frontend

React 18 and Vite 6. Three screens, chosen from the path: `/` ask, `/library` upload and list, `/aliases` feature spellings.

`src/api.js` calls `/api/v1` and sends a `traceparent`. Vite proxies `/api` to `API_PROXY` or `http://127.0.0.1:8000`. The Docker image is a preview server on port 5173 with `API_PROXY=http://api:8000`.

Upload: choosing a file calls `POST /documents/identity` and fills maker, model, and title. The fields stay editable. An empty field is omitted so the API reads it from the file. Download links use `GET /documents/{id}/file`. Ask can copy the answer or save it as Markdown. Each citation links to the source file.

```bash
npm install
npm run dev
npm test
```

`npm test` is Vitest with happy-dom and v8 coverage. Thresholds in `vite.config.js`: lines and statements 85, branches 80, functions 75. `src/main.jsx` and `src/telemetry.js` are excluded from coverage.

The image copies source at build time. A UI change is not visible on port 5173 until the frontend image is rebuilt.
