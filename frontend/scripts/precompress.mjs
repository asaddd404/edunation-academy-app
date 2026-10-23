// Writes .br and .gz next to every compressible file in dist/assets, so Caddy
// (file_server `precompressed`) serves maximum-level Brotli without spending
// the server's single CPU compressing on every request. Run after `vite build`.
import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { brotliCompressSync, constants, gzipSync } from "node:zlib";

const dir = new URL("../dist/assets/", import.meta.url).pathname;
const compressible = /\.(js|css|svg|json|txt)$/;
let saved = 0;

for (const name of readdirSync(dir)) {
  if (!compressible.test(name)) continue;
  const file = join(dir, name);
  const raw = readFileSync(file);
  if (raw.length < 1024) continue;
  const br = brotliCompressSync(raw, {
    params: { [constants.BROTLI_PARAM_QUALITY]: 11, [constants.BROTLI_PARAM_SIZE_HINT]: raw.length },
  });
  writeFileSync(`${file}.br`, br);
  writeFileSync(`${file}.gz`, gzipSync(raw, { level: 9 }));
  saved += raw.length - br.length;
}
console.log(`precompressed dist/assets: ${(saved / 1024).toFixed(0)} kB saved with brotli`);
