export type Vec3 = [number, number, number];
export interface LetterGeometry {
  pdb_id: string;
  chains: Record<string, [number, number]>;
  rotation: number[];
  projected_center: Vec3;
  projected_size: Vec3;
  advance: number;
}
export interface Manifest {
  version: 1;
  source: string;
  cap_height: number;
  line_height: number;
  space_advance: number;
  letters: Record<string, LetterGeometry>;
}
export type Background = "white" | "#101c27" | "transparent";
export type Style = "rainbow" | "ocean";
export interface LayoutSettings {
  maxChars: number;
  background: Background;
  style: Style;
  /** Extra gap as a fraction of the scene's native cap height. */
  letterSpacing?: number;
}
export interface SceneNode {
  kind: string;
  params?: Record<string, unknown>;
  children?: SceneNode[];
}
export interface Scene {
  kind: "single";
  root: SceneNode;
  metadata: { title: string; description: string; timestamp: string; version: string };
}
export const punctuation: Record<string, string> = {
  ".": "stop",
  ",": "comma",
  ":": "colon",
  "!": "exclamation",
  "?": "question",
  "-": "hyphen",
};
export const rainbow = [
  "#0000FF",
  "#0066FF",
  "#00CCFF",
  "#00DD88",
  "#33CC33",
  "#AADD00",
  "#FFFF00",
  "#FFBB00",
  "#FF7700",
  "#FF2200",
];

export function validateManifest(value: unknown): Manifest {
  const fail = (field: string): never => {
    throw new Error(
      `Invalid alphabet manifest (${field}). Regenerate it with src/extract_manifest.py.`,
    );
  };
  if (!value || typeof value !== "object") return fail("expected an object");
  const m = value as Record<string, unknown>;
  if (m.version !== 1) return fail("only version 1 is supported");
  if (typeof m.source !== "string" || !m.source.startsWith("https://")) return fail("source");
  for (const key of ["cap_height", "line_height", "space_advance"]) {
    if (typeof m[key] !== "number" || !Number.isFinite(m[key]) || m[key] <= 0) return fail(key);
  }
  if (!m.letters || typeof m.letters !== "object") return fail("letters");
  for (const ch of "ABCDEFGHIJKLMNOPQRSTUVWXYZ") {
    const l = (m.letters as Record<string, LetterGeometry>)[ch];
    if (!l || !/^[0-9A-Z]{4}$/.test(l.pdb_id)) return fail(`${ch}.pdb_id`);
    for (const [key, count] of [
      ["rotation", 9],
      ["projected_center", 3],
      ["projected_size", 3],
    ] as const) {
      if (!Array.isArray(l[key]) || l[key].length !== count || !l[key].every(Number.isFinite))
        return fail(`${ch}.${key}`);
    }
    if (!l.projected_size.every((v) => v > 0) || !Number.isFinite(l.advance) || l.advance <= 0)
      return fail(`${ch}.bounds`);
    if (!l.chains || typeof l.chains !== "object" || !Object.keys(l.chains).length)
      return fail(`${ch}.chains`);
    for (const range of Object.values(l.chains)) {
      if (
        !Array.isArray(range) ||
        range.length !== 2 ||
        !range.every(Number.isInteger) ||
        range[0] > range[1]
      )
        return fail(`${ch}.residue range`);
    }
  }
  return value as Manifest;
}

export function wordsToLines(text: string, maxChars = 20): string[][] {
  if (!Number.isInteger(maxChars) || maxChars < 1)
    throw new Error("Wrap width must be a positive integer.");
  if (/\p{Nd}/u.test(text)) throw new Error("Digits are not supported by the protein alphabet.");
  const unsupported = [
    ...new Set(Array.from(text.replaceAll("xLBx", "")).filter((c) => !/[a-zA-Z\s.,:!?-]/.test(c))),
  ];
  if (unsupported.length)
    throw new Error(
      `Unsupported characters: ${unsupported.join(" ")}. Use A–Z, spaces, or . , : ! ? -`,
    );
  if (text.length > 240) throw new Error("Please use at most 240 characters.");
  const tokens = text
    .replace(/\r\n?/g, "\n")
    .replace(/\n/g, " xLBx ")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  const lines: string[][] = [];
  let line: string[] = [],
    length = 0;
  for (const word of tokens) {
    if (word === "xLBx") {
      lines.push(line);
      line = [];
      length = 0;
      continue;
    }
    const added = word.length + (line.length ? 1 : 0);
    if (line.length && length + added > maxChars) {
      lines.push(line);
      line = [word];
      length = word.length;
    } else {
      line.push(word);
      length += added;
    }
  }
  if (line.length || !lines.length) lines.push(line);
  return lines;
}

export function matrix(letter: LetterGeometry, [x, y]: [number, number]): number[] {
  const r = letter.rotation,
    c = letter.projected_center;
  return [
    r[0],
    r[1],
    r[2],
    0,
    r[3],
    r[4],
    r[5],
    0,
    r[6],
    r[7],
    r[8],
    0,
    x - c[0],
    y - c[1],
    -c[2],
    1,
  ];
}

export function positions(lines: string[][], manifest: Manifest, letterSpacing = 0) {
  if (!Number.isFinite(letterSpacing) || letterSpacing < 0 || letterSpacing > 1) {
    throw new Error("Letter spacing must be between 0 and 1.");
  }
  const rendered = lines.map((l) => l.join(" ").toUpperCase());
  const heights = rendered.flatMap((l) =>
    Array.from(l)
      .filter((c) => manifest.letters[c])
      .map((c) => manifest.letters[c].projected_size[1]),
  );
  const cap = Math.max(manifest.cap_height, ...heights);
  const lineHeight = (cap * manifest.line_height) / manifest.cap_height;
  const space = (cap * manifest.space_advance) / manifest.cap_height;
  const placed: Record<string, [number, number][]> = {};
  let width = 0,
    boundX = 0,
    boundY = 0,
    depth = 0;
  rendered.forEach((line, index) => {
    const advances = Array.from(line).map((c) =>
      manifest.letters[c]
        ? manifest.letters[c].advance * manifest.letters[c].projected_size[1] + cap * letterSpacing
        : space,
    );
    const w = advances.reduce((a, b) => a + b, 0);
    width = Math.max(width, w);
    let cursor = -w / 2;
    Array.from(line).forEach((c, i) => {
      const l = manifest.letters[c],
        x = cursor + advances[i] / 2,
        y = ((lines.length - 1) / 2 - index) * lineHeight;
      if (l) {
        (placed[c] ??= []).push([x, y]);
        boundX = Math.max(boundX, Math.abs(x) + l.projected_size[0] / 2);
        boundY = Math.max(boundY, Math.abs(y) + l.projected_size[1] / 2);
        depth = Math.max(depth, l.projected_size[2]);
      }
      cursor += advances[i];
    });
  });
  return {
    placed,
    width,
    height: lines.length * lineHeight,
    bounds: [boundX * 2, boundY * 2, depth] as Vec3,
  };
}

export function colorNodes(chains: LetterGeometry["chains"], style: Style): SceneNode[] {
  if (style === "ocean") return [{ kind: "color", params: { color: "#159da5" } }];
  return Object.entries(chains).flatMap(([chain, [first, last]]) =>
    rainbow.flatMap((color, i) => {
      const count = last - first + 1,
        begin = first + Math.floor((count * i) / rainbow.length),
        end = first + Math.floor((count * (i + 1)) / rainbow.length) - 1;
      return begin <= end
        ? [
            {
              kind: "color",
              params: {
                color,
                selector: { auth_asym_id: chain, beg_auth_seq_id: begin, end_auth_seq_id: end },
              },
            },
          ]
        : [];
    }),
  );
}

export function createScene(text: string, manifest: Manifest, settings: LayoutSettings) {
  const lines = wordsToLines(text, settings.maxChars),
    layout = positions(lines, manifest, settings.letterSpacing);
  if (!Object.keys(layout.placed).length)
    throw new Error("Enter at least one protein letter (A–Z).");
  const children: SceneNode[] = Object.entries(layout.placed).map(([character, points]) => {
    const l = manifest.letters[character];
    return {
      kind: "download",
      params: { url: `https://models.rcsb.org/${l.pdb_id}.bcif` },
      children: [
        {
          kind: "parse",
          params: { format: "bcif" },
          children: [
            {
              kind: "structure",
              params: { type: "model" },
              children: [
                ...points.map((p) => ({ kind: "instance", params: { matrix: matrix(l, p) } })),
                {
                  kind: "component",
                  params: {
                    selector: Object.keys(l.chains).map((chain) => ({ auth_asym_id: chain })),
                  },
                  children: [
                    {
                      kind: "representation",
                      params: { type: "cartoon" },
                      children: colorNodes(l.chains, settings.style),
                    },
                    { kind: "tooltip", params: { text: `${character}: PDB ${l.pdb_id}` } },
                  ],
                },
              ],
            },
          ],
        },
      ],
    };
  });
  const distance = Math.max(...layout.bounds, 10) * 1.5;
  children.push(
    {
      kind: "canvas",
      params: {
        background_color: settings.background === "transparent" ? "white" : settings.background,
      },
    },
    {
      kind: "camera",
      params: {
        target: [0, 0, 0],
        position: [0, 0, distance],
        up: [0, 1, 0],
        near: Math.max(0.1, distance - layout.bounds[2] / 2 - 10),
      },
    },
  );
  const omitted = [...new Set(Array.from(text).filter((c) => c in punctuation))];
  const scene: Scene = {
    kind: "single",
    root: { kind: "root", children },
    metadata: {
      title: `pdbwords: ${lines.map((l) => l.join(" ")).join(" / ")}`,
      description: `Created with pdbwords from Mark Howarth's protein alphabet (${manifest.source}); geometry manifest v${manifest.version}. Coordinates: RCSB PDB. Style: ${settings.style}. Extra letter spacing: ${settings.letterSpacing ?? 0} cap heights. Punctuation omitted from 3D: ${omitted.join(" ") || "none"}.`,
      timestamp: new Date().toISOString(),
      version: "1.8",
    },
  };
  return { scene, lines, layout, omitted };
}
