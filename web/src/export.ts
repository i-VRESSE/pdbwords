import type { Viewer } from "molstar/lib/apps/viewer/app";
import { createScene, punctuation } from "./geometry";
import type { Background, Manifest, Style } from "./geometry";
import { CoordinateCache, createViewer, image, loadScene } from "./renderer";

export interface ExportOptions {
  width: number;
  height: number;
  background: Background;
  style: Style;
  letterSpacing?: number;
}
const assetUrls = import.meta.glob(
  ["../../src/pdbwords/assets/{stop,comma,colon,exclamation,question,hyphen}.png"],
  {
    query: "?url",
    import: "default",
    eager: true,
  },
) as Record<string, string>;

/** Crop genuine renderer alpha, keeping a small border for antialiased edges. */
export function cropAlpha(source: HTMLCanvasElement): HTMLCanvasElement {
  const { width, height } = source;
  const data = source.getContext("2d")!.getImageData(0, 0, width, height).data;
  let left = width,
    top = height,
    right = -1,
    bottom = -1;
  for (let y = 0; y < height; y++)
    for (let x = 0; x < width; x++) {
      if (data[(y * width + x) * 4 + 3] > 0) {
        left = Math.min(left, x);
        right = Math.max(right, x);
        top = Math.min(top, y);
        bottom = Math.max(bottom, y);
      }
    }
  if (right < 0)
    throw new Error("The letter rendered empty. Check WebGL and the coordinate source.");
  left = Math.max(0, left - 4);
  top = Math.max(0, top - 4);
  right = Math.min(width - 1, right + 4);
  bottom = Math.min(height - 1, bottom + 4);
  const result = document.createElement("canvas");
  result.width = right - left + 1;
  result.height = bottom - top + 1;
  result
    .getContext("2d")!
    .drawImage(source, left, top, result.width, result.height, 0, 0, result.width, result.height);
  return result;
}

export class WordExporter {
  private viewer?: Viewer;
  private host?: HTMLElement;
  private readonly tiles = new Map<string, HTMLCanvasElement>();
  constructor(
    private readonly manifest: Manifest,
    private readonly coordinates: CoordinateCache,
  ) {}
  async compose(lines: string[][], options: ExportOptions, progress: (message: string) => void) {
    if (!this.viewer) {
      this.host = document.createElement("div");
      this.host.className = "tile-renderer";
      document.body.append(this.host);
      this.viewer = await createViewer(this.host);
    }
    const strings = lines.map((l) => l.join(" ").toUpperCase());
    const letters = [...new Set(strings.join("").replaceAll(" ", ""))];
    const resolution = Math.min(2048, Math.max(512, options.height));
    const tiles = new Map<string, HTMLCanvasElement>();
    for (let i = 0; i < letters.length; i++) {
      const char = letters[i],
        key = `${char}/${options.style}/${resolution}/${options.background}`;
      progress(`Rendering tile ${i + 1}/${letters.length}: ${char}`);
      let tile = this.tiles.get(key);
      if (!tile) {
        if (punctuation[char]) {
          const img = new Image();
          img.src = assetUrls[`../../src/pdbwords/assets/${punctuation[char]}.png`];
          await img.decode();
          tile = document.createElement("canvas");
          tile.width = img.width;
          tile.height = img.height;
          tile.getContext("2d")!.drawImage(img, 0, 0);
          // The legacy punctuation tiles are white-matted RGB images. Unmatte
          // those assets only; Mol* letter alpha comes directly from WebGL.
          const context = tile.getContext("2d")!;
          const pixels = context.getImageData(0, 0, tile.width, tile.height);
          for (let p = 0; p < pixels.data.length; p += 4) {
            const r = pixels.data[p],
              g = pixels.data[p + 1],
              b = pixels.data[p + 2];
            const alpha = 255 - Math.min(r, g, b);
            pixels.data[p + 3] = alpha < 8 ? 0 : alpha;
            for (let channel = 0; channel < 3; channel++) {
              pixels.data[p + channel] =
                options.background === "#101c27"
                  ? 235
                  : alpha
                    ? Math.max(0, ((pixels.data[p + channel] - (255 - alpha)) * 255) / alpha)
                    : 0;
            }
          }
          context.putImageData(pixels, 0, 0);
        } else {
          const { scene, layout } = createScene(char, this.manifest, {
            maxChars: 20,
            style: options.style,
            background: "transparent",
          });
          await loadScene(
            this.viewer,
            await this.coordinates.prepare(scene, progress),
            layout.bounds,
          );
          tile = cropAlpha(await image(this.viewer, resolution, resolution, true));
        }
        // Keep the tile cache bounded even after repeated style/resolution changes.
        if (this.tiles.size >= 104) this.tiles.delete(this.tiles.keys().next().value!);
        this.tiles.set(key, tile);
      }
      tiles.set(char, tile);
    }
    const space = this.manifest.space_advance / this.manifest.cap_height;
    const widths = strings.map((line) =>
      Array.from(line).reduce(
        (sum, c) =>
          sum +
          (c === " "
            ? space
            : tiles.get(c)!.width / tiles.get(c)!.height +
              (this.manifest.letters[c] ? (options.letterSpacing ?? 0) : 0)),
        0,
      ),
    );
    const lineHeight = this.manifest.line_height / this.manifest.cap_height;
    const unitsHeight = Math.max(1, (strings.length - 1) * lineHeight + 1);
    const padding = 24;
    const scale = Math.min(
      (options.width - padding * 2) / Math.max(...widths),
      (options.height - padding * 2) / unitsHeight,
    );
    const canvas = document.createElement("canvas");
    canvas.width = options.width;
    canvas.height = options.height;
    const ctx = canvas.getContext("2d")!;
    if (options.background !== "transparent") {
      ctx.fillStyle = options.background;
      ctx.fillRect(0, 0, canvas.width, canvas.height);
    }
    const top = (options.height - unitsHeight * scale) / 2;
    strings.forEach((line, index) => {
      let x = (options.width - widths[index] * scale) / 2;
      for (const c of line) {
        const tile = tiles.get(c),
          width = c === " " ? space * scale : (tile!.width / tile!.height) * scale;
        const gap = this.manifest.letters[c] ? (options.letterSpacing ?? 0) * scale : 0;
        if (tile) ctx.drawImage(tile, x + gap / 2, top + index * lineHeight * scale, width, scale);
        x += width + gap;
      }
    });
    return canvas;
  }
  dispose() {
    this.viewer?.dispose();
    this.host?.remove();
    this.tiles.clear();
  }
}
