import { describe, expect, it } from "vite-plus/test";
import { MVSData } from "molstar/lib/extensions/mvs/mvs-data";
import { CIF } from "molstar/lib/mol-io/reader/cif";
import manifestData from "./manifest.json";
import { createScene, matrix, validateManifest } from "./geometry";
import { digitGeometry, digitRotation, scaledDigitCoordinates } from "./digits";
import type { Vec3 } from "./geometry";

const manifest = validateManifest(manifestData);
const settings = { maxChars: 20, background: "white", style: "rainbow" } as const;

describe("protein digits", () => {
  it("embeds scaled coordinates while preserving residue identifiers and annotations", async () => {
    const parsed = await CIF.parseText(`data_test
loop_
_atom_site.id
_atom_site.Cartn_x
_atom_site.Cartn_y
_atom_site.Cartn_z
_atom_site.auth_seq_id
1 10 20 30 -2
2 20 40 60 7
loop_
_struct_conf.id
_struct_conf.conf_type_id
HELX1 HELX_P
loop_
_pdbx_struct_oper_list.id
_pdbx_struct_oper_list.vector[1]
_pdbx_struct_oper_list.vector[2]
_pdbx_struct_oper_list.vector[3]
1 10 -20 30
`).run();
    if (parsed.isError) throw new Error(parsed.message);
    const binary = scaledDigitCoordinates(parsed.result.blocks[0], 0.5);
    const decoded = await CIF.parseBinary(binary).run();
    if (decoded.isError) throw new Error(decoded.message);
    const block = decoded.result.blocks[0];
    expect(block.categories.atom_site.getField("Cartn_x")!.float(0)).toBe(5);
    expect(block.categories.atom_site.getField("Cartn_z")!.float(1)).toBe(30);
    expect(block.categories.atom_site.getField("auth_seq_id")!.int(0)).toBe(-2);
    expect(block.categories.struct_conf.getField("conf_type_id")!.str(0)).toBe("HELX_P");
    expect(block.categories.pdbx_struct_oper_list.getField("vector[2]")!.float(0)).toBe(-10);
  });
  it("maps the saved camera right, up, and toward-camera axes to the scene axes", () => {
    expect(digitRotation({ position: [0, 0, 10], target: [0, 0, 0], up: [0, 1, 0] })).toEqual([
      1, 0, 0, 0, 1, 0, 0, 0, 1,
    ]);
    const rotation = digitRotation({ position: [10, 0, 0], target: [0, 0, 0], up: [0, 0, 1] });
    expect(rotation).toEqual([0, 0, 1, 1, 0, 0, 0, 1, 0]);
  });
  it("applies PyMOL's saved image rotation clockwise exactly once", () => {
    const rotation = digitRotation({
      format: "pymol",
      view: [1, 0, 0, 0, 1, 0, 0, 0, 1, ...Array<number>(9).fill(0)],
      image_rotation_clockwise_deg: 90,
    });
    expect(rotation[0]).toBeCloseTo(0);
    expect(rotation[1]).toBeCloseTo(-1);
    expect(rotation[3]).toBeCloseTo(1);
    expect(rotation[4]).toBeCloseTo(0);
  });
  it("renders all digits alone and in mixed text using portable assemblies and independent instances", () => {
    const resolved = { ...manifest, letters: { ...manifest.letters } };
    const points: Vec3[] = [
      [10, 20, 30],
      [18, 34, 48],
      [12, 31, 44],
    ];
    for (const [ch, digit] of Object.entries(manifest.digits!)) {
      const geometry = digitGeometry(digit, points, { A: [1, 20] }, manifest.cap_height, 0);
      resolved.letters[ch] = geometry;
      expect(geometry.projected_size[1]).toBeCloseTo(manifest.cap_height);
      const transform = matrix(geometry, [0, 0]);
      const transformed = points.map((p) =>
        [0, 1, 2].map(
          (i) =>
            transform[i] * p[0] * geometry.coordinate_scale! +
            transform[i + 4] * p[1] * geometry.coordinate_scale! +
            transform[i + 8] * p[2] * geometry.coordinate_scale! +
            transform[i + 12],
        ),
      );
      for (let axis = 0; axis < 3; axis++) {
        const values = transformed.map((p) => p[axis]);
        expect(Math.min(...values) + Math.max(...values)).toBeCloseTo(0);
      }
      const { scene } = createScene(ch + ch, resolved, settings);
      const downloads = scene.root.children!.filter((n) => n.kind === "download");
      expect(downloads).toHaveLength(1);
      expect(downloads[0].params!.url).toBe(`https://models.rcsb.org/${digit.pdb_id}.bcif`);
      const parse = downloads[0].children![0];
      expect(parse.params!.format).toBe("bcif");
      const structure = parse.children![0];
      expect(structure.params).toMatchObject({ type: "assembly", assembly_id: digit.assembly });
      expect(structure.children!.filter((n) => n.kind === "instance")).toHaveLength(2);
      expect(structure.children!.find((n) => n.kind === "component")!.params!.selector).toBe(
        "protein",
      );
      expect(MVSData.validationIssues(MVSData.fromMVSJ(JSON.stringify(scene)))).toBeUndefined();
    }
    const mixed = createScene("a0123456789!", resolved, settings);
    expect(Object.keys(mixed.layout.placed)).toHaveLength(11);
    expect(mixed.omitted).toEqual(["!"]);
    expect(() => createScene("1", manifest, settings)).toThrow(/geometry is unavailable/);
  });
  it("rejects empty digit coordinate selections", () => {
    expect(() => digitGeometry(manifest.digits!["0"], [], {}, manifest.cap_height, 0)).toThrow(
      /No protein geometry/,
    );
  });
});
