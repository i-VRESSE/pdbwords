import { Viewer } from "molstar/lib/apps/viewer/app";
import { MVSData } from "molstar/lib/extensions/mvs/mvs-data";
import { RuntimeContext } from "molstar/lib/mol-task";
import { Vec3 } from "molstar/lib/mol-math/linear-algebra";
import type { Scene, Vec3 as Bounds } from "./geometry";

/** Blob URLs survive scene replacement; failed downloads are evicted for retry. */
export class CoordinateCache {
  private readonly entries = new Map<string, Promise<string>>();
  async prepare(scene: Scene, progress: (message: string) => void): Promise<Scene> {
    const copy = structuredClone(scene);
    const nodes = copy.root.children!.filter((n) => n.kind === "download");
    let next = 0,
      done = 0;
    await Promise.all(
      Array.from({ length: Math.min(3, nodes.length) }, async () => {
        while (next < nodes.length) {
          const node = nodes[next++],
            url = node.params!.url as string;
          let entry = this.entries.get(url);
          if (!entry) {
            entry = this.fetch(url);
            this.entries.set(url, entry);
            entry.catch(() => this.entries.delete(url));
          }
          node.params!.url = await entry;
          progress(`Coordinates ${++done}/${nodes.length} loaded`);
        }
      }),
    );
    return copy;
  }
  private async fetch(url: string): Promise<string> {
    const response = await fetch(url, { signal: AbortSignal.timeout(60000) });
    if (!response.ok)
      throw new Error(`Structure download failed (${response.status}): ${url}. Please retry.`);
    return URL.createObjectURL(await response.blob());
  }
  dispose() {
    for (const entry of this.entries.values())
      void entry.then(
        (url) => URL.revokeObjectURL(url),
        () => {},
      );
    this.entries.clear();
  }
}

export async function createViewer(element: HTMLElement): Promise<Viewer> {
  const probe = document.createElement("canvas");
  if (!probe.getContext("webgl2") && !probe.getContext("webgl"))
    throw new Error("WebGL is unavailable. Enable hardware acceleration or try another browser.");
  const viewer = await Viewer.create(element, {
    extensions: ["mvs"],
    layoutIsExpanded: false,
    layoutShowControls: false,
    layoutShowSequence: false,
    layoutShowLog: false,
    layoutShowLeftPanel: false,
    viewportShowExpand: false,
    viewportShowScreenshotControls: false,
    viewportShowControls: false,
    viewportShowSettings: false,
    viewportShowSelectionMode: false,
    viewportShowAnimation: false,
    volumeStreamingDisabled: true,
  });
  viewer.plugin.canvas3d!.setProps({
    camera: { mode: "orthographic" },
  });
  return viewer;
}

export async function loadScene(viewer: Viewer, scene: Scene, bounds: Bounds) {
  const data = MVSData.fromMVSJ(JSON.stringify(scene));
  const issues = MVSData.validationIssues(data);
  if (issues?.length) throw new Error(`Invalid MolViewSpec: ${issues.join("; ")}`);
  await viewer.loadMvsData(JSON.stringify(scene), "mvsj", { sanityChecks: false });
  // This app owns scene navigation and provenance; avoid an extra snapshot UI.
  viewer.plugin.managers.snapshot.clear();
  frame(viewer, bounds);
  viewer.plugin.canvas3d!.commit(true);
}

export function frame(viewer: Viewer, bounds: Bounds) {
  const c = viewer.plugin.canvas3d!;
  const aspect = Math.max(0.1, c.camera.viewport.width / c.camera.viewport.height);
  const span = Math.max(bounds[1], bounds[0] / aspect, 10) * 1.18;
  const distance = span / (2 * Math.tan(c.camera.state.fov / 2));
  c.camera.setState(
    {
      mode: "orthographic",
      target: Vec3.create(0, 0, 0),
      position: Vec3.create(0, 0, distance),
      up: Vec3.create(0, 1, 0),
      radius: Math.max(span, bounds[2]) * 2,
      radiusMax: Math.max(span, bounds[2]) * 2,
      minNear: 0.1,
      minFar: bounds[2] + distance + 100,
      clipFar: false,
      fog: 0,
    },
    0,
  );
  c.requestDraw();
}

export async function image(
  viewer: Viewer,
  width: number,
  height: number,
  transparent: boolean,
): Promise<HTMLCanvasElement> {
  if (
    !Number.isInteger(width) ||
    !Number.isInteger(height) ||
    width < 1 ||
    height < 1 ||
    width > 4096 ||
    height > 4096
  )
    throw new Error("PNG dimensions must be between 1 and 4096 pixels.");
  const c = viewer.plugin.canvas3d!;
  c.commit(true);
  const pass = viewer.plugin.helpers.viewportScreenshot!.imagePass;
  pass.setProps({
    transparentBackground: transparent,
    cameraHelper: { axes: { name: "off", params: {} } },
  });
  const pixels = await pass.getImageData(RuntimeContext.Synchronous, width, height);
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  canvas.getContext("2d")!.putImageData(pixels, 0, 0);
  return canvas;
}

export function png(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) =>
    canvas.toBlob(
      (blob) => (blob ? resolve(blob) : reject(new Error("PNG encoding failed."))),
      "image/png",
    ),
  );
}

export function download(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob),
    anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
