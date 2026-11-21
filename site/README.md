# FPD Bench interactive research story

Live: <https://fpd-bench-showcase.vercel.app>

A static Vite + React + TypeScript site with one React Three Fiber scene. It is a
non-archival communication companion to Paper A and adds no analysis.

## Sources and boundaries

- Every displayed measurement is computed at build time from
  [`docs/res440/findings.json`](../docs/res440/findings.json) via `src/data/findings.ts`.
  Nothing numeric is retyped.
- Pitch motion (`src/data/scene.ts`) is a hand-authored deterministic schematic on the
  study's time grid. It is not tracking data, a reconstruction, or a model prediction.
- No backend, telemetry, raw SkillCorner data, predictions, checkpoints or private
  receipts. Fonts load from Google Fonts; nothing else leaves the page.

## Develop and check

```sh
npm ci
npm run dev              # http://localhost:5173
npm run build            # typecheck + production build into dist/
npm run check:content    # source-data, limitation-text and naming/file-rule checks
npx vite preview --port 4173 &
npm run check:browser    # desktop/phone/reduced-motion screenshots, interactions, axe
```

`check:browser` needs Playwright's Chromium (`npx playwright install chromium`);
screenshots go to `qa/` (ignored). After changing dependencies, run
`npm run lock:sanitize`: the repository naming validator scans committed files, and
base64 integrity hashes can match its historical-identifier patterns.

## Deploy

`vercel.json` at the repository root builds `site/` and serves `site/dist`;
`.vercelignore` uploads only `site/` and the findings file it reads.
