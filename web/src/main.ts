import "./style.css";
import "molstar/build/viewer/molstar.css";
import rawManifest from "../../src/pdbwords/assets/manifest.json";
import { createScene, validateManifest } from "./geometry";
import type { Background, Style } from "./geometry";
import { CoordinateCache, createViewer, download, frame, image, loadScene, png } from "./renderer";
import { WordExporter } from "./export";

document.querySelector<HTMLDivElement>("#app")!.innerHTML = `
  <main>
    <section class="workspace" aria-label="Protein word studio">
      <form id="form" class="controls">
        <div class="step"><span>01</span><h2>Write your words</h2></div>
        <label for="text">Your message</label><textarea id="text" maxlength="240" rows="4" spellcheck="false">PROTEIN</textarea>
        <div class="hint">A–Z · spaces · new lines <span id="count">7 / 240</span></div>
        <div class="settings"><div><label for="wrap">Letters per line</label><input id="wrap" type="number" min="1" max="80" value="20" required></div><div><label for="style">Cartoon colors</label><select id="style"><option value="rainbow">Residue rainbow</option><option value="ocean">Ocean blue</option></select></div></div>
        <div class="spacing-setting"><label for="spacing">Letter spacing <output id="spacing-value" for="spacing">20%</output></label><input id="spacing" type="range" min="0" max="100" step="5" value="20" aria-describedby="spacing-help"><p id="spacing-help" class="small">Slide to spread the protein letters apart.</p></div>
        <label for="background">Background</label><select id="background"><option value="white">Paper white</option><option value="#101c27">Midnight</option><option value="transparent">Transparent</option></select>
        <button class="primary" id="render" type="submit">Render protein words <span>→</span></button>
        <button id="example" class="example" type="button">Try all letters (A–Z)</button>
        <p class="small">Punctuation appears in the word PNG. The interactive view shows protein letters only.</p>
        <div class="export-panel"><div class="step"><span>02</span><h2>Make it yours</h2></div>
          <label for="resolution">PNG dimensions</label><select id="resolution"><option value="1600,900">1600 × 900</option><option value="2400,1350">2400 × 1350</option><option value="1200,1200">1200 × 1200</option></select>
          <button type="button" id="word" disabled>↓ Download word PNG</button><button type="button" id="screenshot" disabled>↓ Download scene PNG</button><button type="button" id="mvs" disabled>↓ Download MolViewSpec</button>
        </div>
        <p class="small attribution"><a href="https://www.howarthgroup.org/alphabet">Howarth protein alphabet</a> · non-commercial use<br>pdbwords · K. Lindorff-Larsen & S. Verhoeven · <a href="https://github.com/i-VRESSE/pdbwords">Source</a></p>
      </form>
      <div class="preview"><div class="preview-bar"><span><i></i> LIVE MOLECULAR VIEW</span><button type="button" id="reset" disabled>↺ Reset view</button></div><div id="viewer" aria-label="Interactive protein letters" tabindex="0"></div><div class="preview-footer"><span>Drag to rotate · scroll to zoom</span><span>Powered by Mol*</span></div><p id="status" role="status" aria-live="polite">Preparing the molecular viewer…</p><section class="structure-sources" aria-label="Source protein structures"><h2>Source protein structures</h2><div id="structures"></div></section></div>
    </section>
  </main>`;

const get = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const text = get<HTMLTextAreaElement>("text");
const status = get<HTMLParagraphElement>("status");
const controls = ["word", "screenshot", "mvs", "reset"].map((id) => get<HTMLButtonElement>(id));
const renderButton = get<HTMLButtonElement>("render");
const cache = new CoordinateCache();
let generation = 0,
  busy = false;
let completed: ReturnType<typeof createScene> | undefined;
let exporter: WordExporter | undefined;
let viewer: Awaited<ReturnType<typeof createViewer>> | undefined;
const message = (value: string, error = false) => {
  status.textContent = value;
  status.classList.toggle("error", error);
};
const enabled = () =>
  controls.forEach((button) => {
    button.disabled = busy || !completed;
  });
const settings = () => ({
  letterSpacing: get<HTMLInputElement>("spacing").valueAsNumber / 100,
  maxChars: get<HTMLInputElement>("wrap").valueAsNumber,
  background: get<HTMLSelectElement>("background").value as Background,
  style: get<HTMLSelectElement>("style").value as Style,
});
const invalidate = () => {
  generation++;
  completed = undefined;
  enabled();
  get("spacing-value").textContent = `${get<HTMLInputElement>("spacing").value}%`;
  get("count").textContent = `${text.value.length} / 240`;
  message("Message changed. Render to update the view and downloads.");
};
for (const id of ["text", "wrap", "background", "style", "spacing"])
  get(id).addEventListener("input", invalidate);

let spacingTimer: ReturnType<typeof setTimeout> | undefined;
function scheduleRender() {
  clearTimeout(spacingTimer);
  spacingTimer = setTimeout(() => {
    if (busy) scheduleRender();
    else void render();
  }, 250);
}
get("spacing").addEventListener("input", scheduleRender);
get("example").addEventListener("click", () => {
  text.value = "ABCDEFG\nHIJKLMN\nOPQRSTU\nVWXYZ";
  invalidate();
  scheduleRender();
});

async function render() {
  if (busy || !viewer) return;
  const version = ++generation;
  completed = undefined;
  busy = true;
  enabled();
  renderButton.disabled = true;
  try {
    const manifest = validateManifest(rawManifest);
    const result = createScene(text.value, manifest, settings());
    const prepared = await cache.prepare(result.scene, (value) => {
      if (version === generation) message(value);
    });
    if (version !== generation) return;
    message("Building protein cartoons…");
    await loadScene(viewer, prepared, result.layout.bounds);
    if (version !== generation) {
      await viewer.plugin.clear();
      return;
    }
    completed = result;
    const count = Object.values(result.layout.placed).reduce((n, points) => n + points.length, 0);
    message(
      `${count} protein letters ready.${result.omitted.length ? ` Punctuation omitted from 3D: ${result.omitted.join(" ")}` : ""}`,
    );
    const structures = get("structures");
    structures.replaceChildren();
    for (const char of Object.keys(result.layout.placed)) {
      const pdb = manifest.letters[char].pdb_id;
      const link = document.createElement("a");
      link.href = `https://www.rcsb.org/structure/${pdb}`;
      link.textContent = `${char} · ${pdb}`;
      link.target = "_blank";
      link.rel = "noopener";
      structures.append(link);
    }
  } catch (error) {
    if (version === generation)
      message(error instanceof Error ? error.message : String(error), true);
  } finally {
    busy = false;
    renderButton.disabled = !viewer;
    enabled();
  }
}
get<HTMLFormElement>("form").addEventListener("submit", (event) => {
  event.preventDefault();
  void render();
});
get("reset").addEventListener("click", () => {
  if (viewer && completed) frame(viewer, completed.layout.bounds);
});
get("mvs").addEventListener("click", () => {
  if (completed)
    download(
      new Blob([JSON.stringify(completed.scene, null, 2)], { type: "application/json" }),
      "pdbwords.mvsj",
    );
});

async function exportImage(composed: boolean) {
  if (!viewer || !completed || busy) return;
  const current = completed,
    version = generation;
  const [width, height] = get<HTMLSelectElement>("resolution").value.split(",").map(Number);
  const config = settings();
  busy = true;
  enabled();
  renderButton.disabled = true;
  try {
    message(composed ? "Rendering normalized letter tiles…" : "Exporting the current scene…");
    const canvas = composed
      ? await exporter!.compose(
          current.lines,
          {
            width,
            height,
            background: config.background,
            style: config.style,
            letterSpacing: config.letterSpacing,
          },
          (value) => {
            if (version === generation) message(value);
          },
        )
      : await image(viewer, width, height, config.background === "transparent");
    if (version !== generation) return;
    download(await png(canvas), composed ? "pdbwords-word.png" : "pdbwords-scene.png");
    message("PNG downloaded.");
  } catch (error) {
    if (version === generation)
      message(`Export failed: ${error instanceof Error ? error.message : String(error)}`, true);
  } finally {
    busy = false;
    renderButton.disabled = false;
    enabled();
  }
}
get("word").addEventListener("click", () => {
  void exportImage(true);
});
get("screenshot").addEventListener("click", () => {
  void exportImage(false);
});

async function initialize() {
  renderButton.disabled = true;
  try {
    const manifest = validateManifest(rawManifest);
    viewer = await createViewer(get("viewer"));
    exporter = new WordExporter(manifest, cache);
    renderButton.disabled = false;
    await render();
  } catch (error) {
    message(error instanceof Error ? error.message : String(error), true);
  }
}
window.addEventListener("pagehide", () => {
  generation++;
  clearTimeout(spacingTimer);
  exporter?.dispose();
  viewer?.dispose();
  cache.dispose();
});
void initialize();
