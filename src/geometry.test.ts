import { describe, expect, it } from "vite-plus/test";
import manifestData from "./manifest.json";
import {
  colorNodes,
  createScene,
  matrix,
  positions,
  validateManifest,
  wordsToLines,
} from "./geometry";
const manifest = validateManifest(manifestData);
const settings = { maxChars: 20, background: "white", style: "rainbow" } as const;

describe("scene geometry", () => {
  it("keeps column-major rotations and subtracts the projected center", () => {
    const letter = manifest.letters.B;
    expect(matrix(letter, [30, -20])).toEqual([
      ...letter.rotation.slice(0, 3),
      0,
      ...letter.rotation.slice(3, 6),
      0,
      ...letter.rotation.slice(6, 9),
      0,
      30 - letter.projected_center[0],
      -20 - letter.projected_center[1],
      -letter.projected_center[2],
      1,
    ]);
  });
  it("groups repeated letters into one download with independent instances", () => {
    const { scene } = createScene("AAA", manifest, settings);
    expect(scene.root.children!.filter((n) => n.kind === "download")).toHaveLength(1);
    expect(
      scene.root.children![0].children![0].children![0].children!.filter(
        (n) => n.kind === "instance",
      ),
    ).toHaveLength(3);
  });
  it("includes native depth for D and O", () => {
    const { bounds } = positions([["DO"]], manifest);
    expect(bounds[2]).toBe(
      Math.max(manifest.letters.D.projected_size[2], manifest.letters.O.projected_size[2]),
    );
  });
});

describe("text and validation", () => {
  it("increases letter distances without rotating or recoloring the geometry", () => {
    const tight = positions([["AA"]], manifest, 0);
    const loose = positions([["AA"]], manifest, 0.5);
    expect(loose.placed.A[1][0] - loose.placed.A[0][0]).toBeGreaterThan(
      tight.placed.A[1][0] - tight.placed.A[0][0],
    );
    expect(loose.width - tight.width).toBeCloseTo(manifest.letters.A.projected_size[1]);
    expect(() => positions([["A"]], manifest, -1)).toThrow(/spacing/);
  });
  it("wraps whole words and preserves multiline command imports", () => {
    expect(wordsToLines("hello world\nAB xLBx O", 8)).toEqual([
      ["hello"],
      ["world"],
      ["AB"],
      ["O"],
    ]);
    expect(wordsToLines("AB\n\nCD")).toEqual([["AB"], [], ["CD"]]);
    expect(wordsToLines("")).toEqual([[]]);
    expect(wordsToLines("LONGWORD", 2)).toEqual([["LONGWORD"]]);
  });
  it("accepts ASCII digits and wraps mixed messages", () => {
    expect(wordsToLines("0123456789")).toEqual([["0123456789"]]);
    expect(wordsToLines("A2 B3\n2026 xLBx 42!", 4)).toEqual([["A2"], ["B3"], ["2026"], ["42!"]]);
  });
  it("rejects unsupported text and invalid layout", () => {
    for (const input of ["A٢", "A２", "é", "<script>"]) expect(() => wordsToLines(input)).toThrow();
    expect(() => wordsToLines("A", 0)).toThrow();
    expect(() => createScene("?!", manifest, settings)).toThrow(/letter/);
  });
  it("reports punctuation and keeps author residue selectors", () => {
    expect(createScene("A!", manifest, settings).omitted).toEqual(["!"]);
    const colors = colorNodes({ X: [-2, 7] }, "rainbow");
    expect(colors[0].params!.selector).toEqual({
      auth_asym_id: "X",
      beg_auth_seq_id: -2,
      end_auth_seq_id: -2,
    });
  });
  it("rejects corrupt manifests with actionable errors", () => {
    expect(() => validateManifest({ ...manifest, version: 2 })).toThrow(/version/);
    const broken = structuredClone(manifest);
    broken.letters.A.rotation = [1];
    expect(() => validateManifest(broken)).toThrow(/A.rotation/);
    const range = structuredClone(manifest);
    range.letters.A.chains.A = [10, 1];
    expect(() => validateManifest(range)).toThrow(/residue range/);
    const digit = structuredClone(manifest);
    digit.digits!["0"].camera = { position: [0, 0, 0], target: [0, 0, 0], up: [0, 1, 0] };
    expect(() => validateManifest(digit)).toThrow(/digits.0.camera/);
  });
});
