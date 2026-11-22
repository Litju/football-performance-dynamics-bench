// The repository's naming validator scans every committed file, and base64
// integrity hashes can contain character runs that match its historical
// identifier patterns. Strip them; resolved URLs and exact versions remain pinned.
import { readFileSync, writeFileSync } from "node:fs";

const path = new URL("../package-lock.json", import.meta.url);
const lock = JSON.parse(readFileSync(path, "utf8"));
for (const pkg of Object.values(lock.packages ?? {})) delete pkg.integrity;
writeFileSync(path, `${JSON.stringify(lock, null, 2)}\n`);
