import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { CIF } = require("molstar/lib/commonjs/mol-io/reader/cif");
const manifest = JSON.parse(
  await readFile(new URL("../src/manifest.json", import.meta.url), "utf8"),
);
const entries = Object.entries(manifest.letters);
let next = 0;
const measurements = [];
await Promise.all(
  Array.from({ length: 3 }, async () => {
    while (next < entries.length) {
      const [letter, geometry] = entries[next++];
      const url = `https://models.rcsb.org/${geometry.pdb_id}.bcif`;
      const start = performance.now();
      const response = await fetch(url, { signal: AbortSignal.timeout(60000) });
      if (!response.ok) throw new Error(`${letter}: HTTP ${response.status}`);
      const bytes = new Uint8Array(await response.arrayBuffer());
      const parsed = await CIF.parseBinary(bytes).run();
      if (parsed.isError) throw new Error(String(parsed));
      const block = parsed.result.blocks[0],
        atoms = block.categories.atom_site;
      const field = (name) => atoms.getField(name);
      const ranges = {};
      for (let i = 0; i < atoms.rowCount; i++) {
        if (
          field("label_atom_id").str(i) !== "CA" ||
          field("group_PDB").str(i) !== "ATOM" ||
          field("pdbx_PDB_model_num").int(i) !== 1
        )
          continue;
        const chain = field("auth_asym_id").str(i),
          seq = field("auth_seq_id").int(i);
        if (!ranges[chain]) ranges[chain] = [seq, seq];
        else {
          ranges[chain][0] = Math.min(ranges[chain][0], seq);
          ranges[chain][1] = Math.max(ranges[chain][1], seq);
        }
      }
      measurements.push({
        letter,
        pdb_id: geometry.pdb_id,
        url,
        bytes: bytes.length,
        sha256: createHash("sha256").update(bytes).digest("hex"),
        elapsed_ms: Math.round(performance.now() - start),
        cors: response.headers.get("access-control-allow-origin"),
        manifest_chains: geometry.chains,
        observed_ca_ranges: ranges,
        helices: block.categories.struct_conf?.rowCount ?? 0,
        sheets: block.categories.struct_sheet_range?.rowCount ?? 0,
      });
    }
  }),
);
measurements.sort((a, b) => a.letter.localeCompare(b.letter));
const report = {
  measured_at: new Date().toISOString(),
  total_bytes: measurements.reduce((n, m) => n + m.bytes, 0),
  measurements,
};
await writeFile(
  new URL("../measurements/coordinates.json", import.meta.url),
  JSON.stringify(report, null, 2) + "\n",
);
console.log(
  `Measured ${measurements.length} structures, ${(report.total_bytes / 1e6).toFixed(2)} MB total.`,
);
