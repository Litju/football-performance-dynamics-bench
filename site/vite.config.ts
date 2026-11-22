import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The site reads the published aggregate results directly from the repository's
// docs/ tree, so there is exactly one copy of every measured number.
const repoRoot = fileURLToPath(new URL("..", import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@evidence": `${repoRoot}docs` } },
  server: { fs: { allow: [repoRoot] } },
  build: { target: "es2022", chunkSizeWarningLimit: 1200 },
});
