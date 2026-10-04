import type { DigitDefinition, LetterGeometry, Vec3 } from "./geometry";
import type { CifBlock } from "molstar/lib/mol-io/reader/cif";
import { CifWriter } from "molstar/lib/mol-io/writer/cif";

export function digitCoordinatesUrl(digit: DigitDefinition): string {
  return `https://models.rcsb.org/${digit.pdb_id}.bcif`;
}

/** Camera axes become the columns of the world-to-view rotation. */
export function digitRotation(camera: DigitDefinition["camera"]): number[] {
  if ("format" in camera) {
    const r = camera.view.slice(0, 9);
    const angle = (camera.image_rotation_clockwise_deg * Math.PI) / 180;
    const c = Math.cos(angle),
      s = Math.sin(angle);
    return r.flatMap((_v, i) =>
      i % 3 === 0 ? [c * r[i] + s * r[i + 1], -s * r[i] + c * r[i + 1], r[i + 2]] : [],
    );
  }
  const normalize = (v: Vec3): Vec3 => {
    const length = Math.hypot(...v);
    return v.map((n) => n / length) as Vec3;
  };
  const cross = (a: Vec3, b: Vec3): Vec3 => [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  ];
  const z = normalize(camera.position.map((v, i) => v - camera.target[i]) as Vec3);
  const x = normalize(cross(camera.up, z));
  const y = cross(z, x);
  return [x[0], y[0], z[0], x[1], y[1], z[1], x[2], y[2], z[2]];
}

/** Measure the selected protein in its approved view and match the letter cap height. */
export function digitGeometry(
  digit: DigitDefinition,
  points: Iterable<Vec3>,
  chains: LetterGeometry["chains"],
  capHeight: number,
  modelIndex: number,
): LetterGeometry {
  const rotation = digitRotation(digit.camera);
  const min = [Infinity, Infinity, Infinity],
    max = [-Infinity, -Infinity, -Infinity];
  for (const p of points) {
    for (let axis = 0; axis < 3; axis++) {
      const value = rotation[axis] * p[0] + rotation[axis + 3] * p[1] + rotation[axis + 6] * p[2];
      min[axis] = Math.min(min[axis], value);
      max[axis] = Math.max(max[axis], value);
    }
  }
  const height = max[1] - min[1];
  if (!Number.isFinite(height) || height <= 0)
    throw new Error(`No protein geometry found for digit structure ${digit.pdb_id}.`);
  const scale = capHeight / height;
  const size = min.map((v, i) => Math.max((max[i] - v) * scale, 0.01)) as Vec3;
  return {
    pdb_id: digit.pdb_id,
    chains,
    rotation,
    projected_center: min.map((v, i) => ((max[i] + v) / 2) * scale) as Vec3,
    projected_size: size,
    advance: size[0] / size[1],
    coordinates_url: digitCoordinatesUrl(digit),
    model_index: modelIndex,
    coordinate_scale: scale,
    source_url: `https://files.rcsb.org/download/${digit.pdb_id.toLowerCase()}-assembly${digit.assembly}.cif`,
    assembly_id: digit.assembly,
  };
}

/** Mol* instances require rigid transforms, so scale the coordinates themselves. */
export function scaledDigitCoordinates(block: CifBlock, scale: number): Uint8Array {
  const encoder = CifWriter.createEncoder({ binary: true, binaryAutoClassifyEncoding: true });
  encoder.startDataBlock(block.header);
  for (const category of Object.values(block.categories)) {
    const fields = category.fieldNames.map((name) => {
      const field = category.getField(name)!;
      if (
        (category.name === "atom_site" && ["Cartn_x", "Cartn_y", "Cartn_z"].includes(name)) ||
        (category.name === "pdbx_struct_oper_list" && /^vector\[[123]\]$/.test(name))
      )
        return CifWriter.Field.float(name, (row: number) => field.float(row) * scale, {
          valueKind: (row: number) => field.valueKind(row),
        });
      return CifWriter.Field.str(name, (row: number) => field.str(row), {
        valueKind: (row: number) => field.valueKind(row),
      });
    });
    encoder.writeCategory({
      name: category.name,
      instance: () => ({ fields, source: [{ rowCount: category.rowCount }] }),
    });
  }
  return encoder.getData() as Uint8Array;
}
