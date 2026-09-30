# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow>=11.0"]
# ///
"""Build and rank a cached protein-image pilot; never accept digits automatically."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

BASE = "https://www.ebi.ac.uk/pdbe/static/entry/"
SEARCH = "https://search.rcsb.org/rcsbsearch/v2/query"
LABELS = tuple("0123456789OISBZ") + ("none",)
VIEWS = ("front", "side", "top")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


class Cache:
    """URL/content addressed disk cache, including permanent missing responses.

    Read downloaded files, not response streams. Successful files are immutable;
    interrupted transfers never become cache hits. 404/410 are remembered until
    --retry-missing; transient failures are retried but are not negative-cached.
    """

    def __init__(
        self,
        root: Path,
        *,
        offline: bool = False,
        retry_missing: bool = False,
        retries: int = 3,
    ) -> None:
        self.root = root
        self.offline = offline
        self.retry_missing = retry_missing
        self.retries = retries
        self.lock = threading.Lock()

    def fetch(self, url: str, body: Any = None) -> Path:
        payload = None if body is None else json.dumps(body, sort_keys=True).encode()
        key = hashlib.sha256(url.encode() + (payload or b"")).hexdigest()
        directory = self.root / key[:2]
        target = directory / key
        missing = directory / (key + ".missing.json")
        # Holding the lock prevents duplicate downloads for concurrent callers.
        # Each entry worker uses its own Cache; shared shortlist downloads are serial.
        with self.lock:
            if target.is_file():
                return target
            if self.offline:
                raise FileNotFoundError(f"Not cached: {url}")
            if missing.exists() and not self.retry_missing:
                raise FileNotFoundError(f"Cached missing response: {url}")
            directory.mkdir(parents=True, exist_ok=True)
            temporary = directory / (key + ".part")
            for attempt in range(self.retries):
                request = urllib.request.Request(
                    url,
                    data=payload,
                    headers={
                        "User-Agent": "pdbwords-digit-pilot/1",
                        "Content-Type": "application/json",
                    },
                )
                try:
                    with urllib.request.urlopen(request, timeout=40) as response:
                        with temporary.open("wb") as output:
                            while chunk := response.read(1024 * 1024):
                                output.write(chunk)
                    temporary.replace(target)
                    write_json(
                        directory / (key + ".source.json"),
                        {
                            "url": url,
                            "request": body,
                            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                        },
                    )
                    return target
                except urllib.error.HTTPError as error:
                    if error.code in (404, 410):
                        write_json(missing, {"url": url, "status": error.code})
                        raise FileNotFoundError(f"HTTP {error.code}: {url}") from error
                    if error.code not in (408, 429, 500, 502, 503, 504):
                        raise
                    if attempt + 1 == self.retries:
                        raise
                    delay = error.headers.get("Retry-After", "")
                    time.sleep(min(30, float(delay)) if delay.isdigit() else 2**attempt)
                except (urllib.error.URLError, TimeoutError, ConnectionError):
                    if attempt + 1 == self.retries:
                        raise
                    time.sleep(2**attempt)
            raise RuntimeError("No download attempts")


def search_query() -> dict[str, Any]:
    return {
        "query": {
            "type": "terminal",
            "service": "text",
            "parameters": {
                "attribute": "entity_poly.rcsb_entity_polymer_type",
                "operator": "exact_match",
                "value": "Protein",
            },
        },
        "return_type": "polymer_entity",
        "request_options": {
            "results_content_type": ["experimental"],
            "return_all_hits": True,
            "group_by": {
                "aggregation_method": "sequence_identity",
                "similarity_cutoff": 30,
            },
            "group_by_return_type": "representatives",
        },
    }


def discover(cache: Cache, count: int, seed: int) -> dict[str, Any]:
    query = search_query()
    response_path = cache.fetch(SEARCH, query)
    response = read_json(response_path)
    identifiers = sorted(hit["identifier"] for hit in response.get("result_set", []))
    if not identifiers:
        raise ValueError("RCSB returned no protein sequence-cluster representatives")
    random.Random(seed).shuffle(identifiers)
    entries: dict[str, list[str]] = {}
    for identifier in identifiers:
        pdb_id, entity = identifier.split("_", 1)
        pdb_id = pdb_id.lower()
        if pdb_id in entries:
            entries[pdb_id].append(entity)
        elif len(entries) < count:
            entries[pdb_id] = [entity]
    return {
        "query": query,
        "response_cache": str(response_path),
        "seed": seed,
        "diversity": "30% sequence identity representatives; structural diversity proxy",
        "entries": entries,
    }


def catalogue_candidates(
    pdb_id: str, catalogue: dict[str, Any], size: int
) -> list[dict[str, Any]]:
    """Assembly images only: entity images can contain multiple chain copies."""
    entry = catalogue[pdb_id]
    suffixes = entry.get("image_suffix", [])
    available = [
        (int(match[1]), suffix)
        for suffix in suffixes
        if (match := re.fullmatch(r"_image-(\d+)x\1\.png", suffix))
    ]
    if not available:
        return []
    _, suffix = min(available, key=lambda item: (abs(item[0] - size), item[0]))
    result = []
    for assembly, scene in sorted(entry.get("assembly", {}).items()):
        for view in VIEWS:
            # Pick one coloring only, using advertised filenames.
            records = [
                record
                for record in scene.get("image", [])
                if record["filename"].endswith("_" + view)
            ]
            records.sort(
                key=lambda item: ("_chain_" not in item["filename"], item["filename"])
            )
            if not records:
                continue
            record = records[0]
            filename = record["filename"]
            if not re.fullmatch(r"[\w.-]+", filename):
                raise ValueError(f"Unsafe catalogue filename: {filename}")
            result.append(
                {
                    "id": filename,
                    "pdb_id": pdb_id,
                    "kind": "assembly",
                    "assembly": assembly,
                    "view": view,
                    "model": 1,
                    "image_url": BASE + filename + suffix,
                    "state_url": BASE + filename + ".molj"
                    if ".molj" in suffixes
                    else None,
                    "caption_url": BASE + filename + ".caption.json"
                    if ".caption.json" in suffixes
                    else None,
                    "caption": record.get("clean_description", record.get("alt", "")),
                    "catalogue_url": BASE + pdb_id + ".json",
                }
            )
    return result


def download_entry(
    root: Path, pdb_id: str, size: int, offline: bool, retry_missing: bool
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    cache = Cache(root / "cache", offline=offline, retry_missing=retry_missing)
    records, failures = [], []
    catalogue_url = BASE + pdb_id + ".json"
    try:
        catalogue_path = cache.fetch(catalogue_url)
        candidates = catalogue_candidates(pdb_id, read_json(catalogue_path), size)
        if not candidates:
            failures.append(
                {
                    "pdb_id": pdb_id,
                    "url": catalogue_url,
                    "error": "No assembly PNG views",
                }
            )
        for candidate in candidates:
            try:
                path = cache.fetch(candidate["image_url"])
                with Image.open(path) as image:
                    image.verify()
                candidate["image_path"] = str(path.relative_to(root))
                candidate["catalogue_path"] = str(catalogue_path.relative_to(root))
                candidate["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
                records.append(candidate)
            except (OSError, ValueError) as error:
                failures.append(
                    {
                        "pdb_id": pdb_id,
                        "url": candidate["image_url"],
                        "error": str(error),
                    }
                )
    except (OSError, ValueError, KeyError) as error:
        failures.append({"pdb_id": pdb_id, "url": catalogue_url, "error": str(error)})
    return records, failures


def collect(args: argparse.Namespace) -> None:
    root = args.workdir
    selection_path = root / "selection.json"
    if args.ids:
        ids = sorted({value.strip().lower() for value in args.ids.split(",")})
        if any(not re.fullmatch(r"[a-z0-9]{4}", value) for value in ids):
            raise ValueError("--ids must be comma-separated four-character PDB IDs")
        selection = {"entries": dict.fromkeys(ids, []), "source": "explicit IDs"}
    else:
        selection = discover(
            Cache(
                root / "cache", offline=args.offline, retry_missing=args.retry_missing
            ),
            args.count,
            args.seed,
        )
    write_json(selection_path, selection)
    records, failures = [], []
    ids = sorted(selection["entries"])
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        tasks = executor.map(
            lambda pdb: download_entry(
                root, pdb, args.size, args.offline, args.retry_missing
            ),
            ids,
        )
        for index, (downloaded, errors) in enumerate(tasks, 1):
            records.extend(downloaded)
            failures.extend(errors)
            if index % 25 == 0 or index == len(ids):
                print(
                    f"{index}/{len(ids)} entries; {len(records)} images; {len(failures)} missing/errors",
                    flush=True,
                )
    write_json(root / "images.json", records)
    write_json(root / "missing.json", failures)
    if not records:
        raise ValueError("No usable images; inspect missing.json")


def normalize(image: Image.Image, size: int = 64) -> tuple[Image.Image, Image.Image]:
    """Remove disconnected small axis marks; preserve aspect ratio and silhouette holes.

    This conservative filter cannot remove an axis attached to the molecule.
    Both outputs are label-free: captions never enter the scoring functions.
    """
    rgba = image.convert("RGBA")
    rgb = Image.new("RGB", rgba.size, "white")
    rgb.paste(rgba, mask=rgba.getchannel("A"))
    # Restrict component analysis to the size needed for ranking.
    rgb.thumbnail((256, 256))
    width, height = rgb.size
    pixels_rgb = rgb.load()
    foreground = {
        y * width + x
        for y in range(height)
        for x in range(width)
        if min(pixels_rgb[x, y]) < 220
    }
    components = []
    while foreground:
        seed = foreground.pop()
        component, pending = {seed}, [seed]
        while pending:
            index = pending.pop()
            x, y = index % width, index // width
            for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                if 0 <= x + dx < width and 0 <= y + dy < height:
                    neighbor = (y + dy) * width + x + dx
                    if neighbor in foreground:
                        foreground.remove(neighbor)
                        component.add(neighbor)
                        pending.append(neighbor)
        components.append(component)
    if not components:
        raise ValueError("Image has no molecular foreground")
    largest = max(map(len, components))

    def is_axis(component: set[int]) -> bool:
        # PDBe's detached axis widget occupies the lower-left corner. Never
        # remove a component connected to, or comparable in size to, the molecule.
        return len(component) < largest * 0.25 and all(
            index % width < width * 0.3 and index // width > height * 0.7
            for index in component
        )

    kept = set().union(
        *(
            component
            for component in components
            if len(component) >= max(4, largest * 0.02) and not is_axis(component)
        )
    )
    mask = Image.new("L", rgb.size)
    pixels = mask.load()
    for index in kept:
        pixels[index % width, index // width] = 255
    bounds = mask.getbbox()
    assert bounds is not None
    rgb = rgb.crop(bounds)
    mask = mask.crop(bounds)
    # Remove filtered components from the cartoon too.
    clean = Image.new("RGB", rgb.size, "white")
    clean.paste(rgb, mask=mask)
    target = (size - 8, size - 8)
    clean.thumbnail(target, Image.Resampling.LANCZOS)
    mask = mask.resize(clean.size, Image.Resampling.NEAREST)
    offset = ((size - clean.width) // 2, (size - clean.height) // 2)
    cartoon = Image.new("RGB", (size, size), "white")
    cartoon.paste(clean, offset)
    silhouette = Image.new("L", (size, size))
    silhouette.paste(mask, offset)
    return cartoon, silhouette


def bits(mask: Image.Image) -> int:
    return int.from_bytes(
        mask.point(lambda value: 255 if value >= 128 else 0).convert("1").tobytes(),
        "big",
    )


def templates(font_paths: list[Path]) -> dict[str, list[int]]:
    fonts = [ImageFont.truetype(str(path), 90) for path in font_paths]
    if not fonts:
        fonts = [ImageFont.load_default(size=90)]
    result: dict[str, list[int]] = {label: [] for label in LABELS if label != "none"}
    for font in fonts:
        for label in result:
            image = Image.new("RGB", (160, 160), "white")
            ImageDraw.Draw(image).text((25, 10), label, font=font, fill="black")
            _, mask = normalize(image)
            # Width variants accommodate protein cartoons without deforming candidates.
            result[label].extend(
                bits(mask.filter(ImageFilter.MaxFilter(width))) for width in (3, 7, 11)
            )
    return result


def template_scores(
    mask: Image.Image, reference: dict[str, list[int]]
) -> dict[str, float]:
    candidate = bits(mask)
    scores = {
        label: max(
            (candidate & template).bit_count() / (candidate | template).bit_count()
            for template in variants
        )
        for label, variants in reference.items()
    }
    # Explicit abstention heuristic, not a calibrated model probability.
    scores["none"] = 1.0 - max(scores.values())
    return scores


class Progress:
    """Report progress periodically, with immediate output for redirected runs."""

    def __init__(self, stage: str, total: int) -> None:
        self.stage = stage
        self.total = total
        self.started = self.last_report = time.monotonic()
        print(f"{stage}: starting {total} images", flush=True)

    def update(self, completed: int, failures: int | None = None) -> None:
        now = time.monotonic()
        if (
            completed != self.total
            and completed % 25 != 0
            and now - self.last_report < 5
        ):
            return
        elapsed = now - self.started
        percent = 100 * completed / self.total if self.total else 100
        eta = elapsed * (self.total - completed) / completed if completed else 0
        errors = f"; failures {failures}" if failures is not None else ""
        print(
            f"{self.stage}: {completed}/{self.total} ({percent:.1f}%); "
            f"elapsed {elapsed:.1f}s; ETA {eta:.0f}s{errors}",
            flush=True,
        )
        self.last_report = now


def clip_scores(
    pairs: list[tuple[Image.Image, Image.Image]], model_name: str, offline: bool
) -> list[dict[str, dict[str, float]]]:
    """Optional local CLIP comparison, with no captions and no softmax probabilities."""
    print(f"Loading vision model: {model_name}", flush=True)
    try:
        import torch
        from transformers import CLIPModel, CLIPProcessor
    except ImportError as error:
        raise ValueError(
            "Vision ranking requires torch and transformers; see docs/digit-search.md"
        ) from error
    model = CLIPModel.from_pretrained(model_name, local_files_only=offline).eval()
    processor = CLIPProcessor.from_pretrained(model_name, local_files_only=offline)
    prompts = [
        f"a protein cartoon shaped like the {'digit' if label.isdigit() else 'letter'} {label}"
        if label != "none"
        else "a protein cartoon with no recognizable digit or letter"
        for label in LABELS
    ]
    result = []
    progress = Progress("Vision scoring", len(pairs))
    with torch.inference_mode():
        for index, (cartoon, mask) in enumerate(pairs, 1):
            silhouette = ImageOps.invert(mask).convert("RGB")
            inputs = processor(
                text=prompts,
                images=[cartoon, silhouette],
                return_tensors="pt",
                padding=True,
            )
            scores = model(**inputs).logits_per_image.tolist()
            result.append(
                {
                    variant: dict(zip(LABELS, values, strict=True))
                    for variant, values in zip(
                        ("cartoon", "silhouette"), scores, strict=True
                    )
                }
            )
            progress.update(index)
    return result


def rank(args: argparse.Namespace) -> None:
    root = args.workdir
    records = read_json(root / "images.json")
    progress = Progress("Template ranking", len(records))
    reference = templates(args.font)
    ranked, pairs, failures = [], [], []
    for index, record in enumerate(records, 1):
        try:
            with Image.open(root / record["image_path"]) as image:
                cartoon, mask = normalize(image)
            destination = root / "normalized" / (record["id"] + ".png")
            destination.parent.mkdir(parents=True, exist_ok=True)
            cartoon.save(destination)
            silhouette_path = root / "silhouettes" / (record["id"] + ".png")
            silhouette_path.parent.mkdir(parents=True, exist_ok=True)
            ImageOps.invert(mask).save(silhouette_path)
            ranked.append(
                {
                    **record,
                    "normalized_path": str(destination.relative_to(root)),
                    "silhouette_path": str(silhouette_path.relative_to(root)),
                    "template": template_scores(mask, reference),
                }
            )
            if args.vision_model:
                pairs.append((cartoon, mask))
        except (OSError, ValueError) as error:
            failures.append({"id": record["id"], "error": str(error)})
        progress.update(index, len(failures))
    if args.vision_model:
        for record, scores in zip(
            ranked, clip_scores(pairs, args.vision_model, args.offline), strict=True
        ):
            record["vision_cartoon"] = scores["cartoon"]
            record["vision_silhouette"] = scores["silhouette"]
    print(f"Writing rankings to {root / 'rankings.json'}", flush=True)
    write_json(
        root / "rankings.json",
        {
            "labels": LABELS,
            "scores_are_probabilities": False,
            "template_method": "best silhouette IoU across font/stroke templates; none = 1 - best IoU",
            "fonts": [str(path) for path in args.font] or ["Pillow bundled default"],
            "vision_model": args.vision_model,
            "records": ranked,
            "failures": failures,
        },
    )
    print(
        f"Ranked {len(ranked)} images; {len(failures)} normalization failures",
        flush=True,
    )


def top_records(
    records: list[dict[str, Any]], digit: str, method: str, count: int
) -> list[dict[str, Any]]:
    # One view per structure/selection so a single assembly cannot fill a sheet.
    seen, result = set(), []
    for record in sorted(records, key=lambda item: (-item[method][digit], item["id"])):
        key = (
            record["pdb_id"],
            record["kind"],
            record.get("assembly"),
            record.get("chain"),
        )
        if key not in seen:
            result.append(record)
            seen.add(key)
            if len(result) == count:
                break
    return result


def sheets(args: argparse.Namespace) -> None:
    root = args.workdir
    rankings = read_json(root / "rankings.json")
    records = rankings["records"]
    if not records or any(args.method not in record for record in records):
        raise ValueError(
            f"No {args.method} rankings; run rank with the corresponding backend"
        )
    directory = root / "sheets" / args.method
    directory.mkdir(parents=True, exist_ok=True)
    shortlist = {}
    for digit in "0123456789":
        top = top_records(records, digit, args.method, args.top)
        shortlist[digit] = [record["id"] for record in top]
        sheet = Image.new("RGB", (4 * 250, math.ceil(len(top) / 4) * 300 + 35), "white")
        draw = ImageDraw.Draw(sheet)
        draw.text(
            (8, 8),
            f"Digit {digit} / {args.method} / scores are not probabilities",
            fill="black",
        )
        for index, record in enumerate(top):
            x, y = index % 4 * 250, index // 4 * 300 + 35
            with Image.open(root / record["image_path"]) as image:
                cartoon, _ = normalize(image, 220)
            sheet.paste(cartoon, (x + 15, y))
            with Image.open(root / record["silhouette_path"]) as silhouette:
                sheet.paste(silhouette.resize((48, 48)), (x + 195, y + 172))
            confusable = max(
                (label for label in LABELS if label != digit),
                key=record[args.method].__getitem__,
            )
            draw.text(
                (x + 5, y + 223),
                f"{record['pdb_id']} assembly {record.get('assembly', '-')} {record['view']}",
                fill="black",
            )
            draw.text(
                (x + 5, y + 241),
                f"{digit}: {record[args.method][digit]:.3f}; {confusable}: {record[args.method][confusable]:.3f}",
                fill="black",
            )
            draw.text((x + 5, y + 259), f"candidate {index + 1}", fill="black")
        sheet.save(directory / (digit + ".png"))
    write_json(directory / "shortlist.json", shortlist)
    # Never overwrite a completed human review on reruns.
    review_path = directory / "reviews.csv"
    if not review_path.exists():
        with review_path.open("w", newline="", encoding="utf-8") as output:
            writer = csv.writer(output)
            writer.writerow(
                ("digit", "id", "readable", "confusable", "reviewer", "notes")
            )
            for digit, ids in shortlist.items():
                for identifier in ids:
                    writer.writerow((digit, identifier, "", "", "", ""))
    print(f"Contact sheets and review template: {directory}")


def benchmark(args: argparse.Namespace) -> None:
    root = args.workdir
    records = read_json(root / "rankings.json")["records"]
    with args.reviews.open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    judgments = {}
    ids = {record["id"] for record in records}
    for row in rows:
        if (
            row["id"] not in ids
            or row["digit"] not in "0123456789"
            or len(row["digit"]) != 1
        ):
            raise ValueError(f"Unknown review candidate or digit: {row}")
        if row["readable"].lower() in ("yes", "no"):
            if not row["reviewer"].strip():
                raise ValueError("Completed reviews require a reviewer")
            key = (row["digit"], row["id"])
            if key in judgments:
                raise ValueError(f"Duplicate review: {key}")
            judgments[key] = row
        elif row["readable"].strip():
            raise ValueError("readable must be yes, no, or empty")
    report = {"reviewed_pairs": len(judgments), "top_k": args.top, "methods": {}}
    for method in ("template", "vision_cartoon", "vision_silhouette"):
        if not records or method not in records[0]:
            continue
        report["methods"][method] = {}
        for digit in "0123456789":
            top = top_records(records, digit, method, args.top)
            reviewed = [
                judgments[(digit, item["id"])]
                for item in top
                if (digit, item["id"]) in judgments
            ]
            readable = sum(
                row["readable"].lower() == "yes" and not row["confusable"].strip()
                for row in reviewed
            )
            report["methods"][method][digit] = {
                "candidates": len(top),
                "reviewed": len(reviewed),
                "clearly_readable": readable,
                "precision_at_k": readable / len(top)
                if top and len(reviewed) == len(top)
                else None,
            }
    write_json(root / "benchmark.json", report)
    write_json(
        root / "reviewed-shortlist.json",
        {
            digit: [
                row
                for (label, _), row in judgments.items()
                if label == digit
                and row["readable"].lower() == "yes"
                and not row["confusable"].strip()
            ]
            for digit in "0123456789"
        },
    )
    print(
        f"Benchmarked {len(judgments)} human judgments; unreviewed precision remains null"
    )


def fetch_shortlist(args: argparse.Namespace) -> None:
    root = args.workdir
    shortlist = read_json(args.shortlist)
    ids = set()
    for values in shortlist.values():
        ids.update(value if isinstance(value, str) else value["id"] for value in values)
    records = {record["id"]: record for record in read_json(root / "images.json")}
    if ids - records.keys():
        raise ValueError(f"Unknown shortlisted IDs: {sorted(ids - records.keys())}")
    cache = Cache(
        root / "cache", offline=args.offline, retry_missing=args.retry_missing
    )
    downloads, errors = [], []
    for identifier in sorted(ids):
        record = records[identifier]
        urls = [record.get("state_url"), record.get("caption_url")]
        if args.coordinates:
            urls.append(
                f"https://files.rcsb.org/download/{record['pdb_id']}-assembly{record['assembly']}.cif"
            )
        for url in filter(None, urls):
            try:
                path = cache.fetch(url)
                downloads.append(
                    {"id": identifier, "url": url, "path": str(path.relative_to(root))}
                )
            except OSError as error:
                errors.append({"id": identifier, "url": url, "error": str(error)})
    write_json(
        root / "shortlist-downloads.json", {"downloads": downloads, "errors": errors}
    )
    print(f"{len(downloads)} cached shortlist files; {len(errors)} errors")


def positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workdir", type=Path, default=Path("digit-pilot"))
    parser.add_argument("--offline", action="store_true", help="read cached files only")
    parser.add_argument(
        "--retry-missing",
        action="store_true",
        help="retry cached HTTP 404/410 responses",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    collect_parser = commands.add_parser(
        "collect", help="cache pilot catalogues and assembly views"
    )
    collect_parser.add_argument("--count", type=positive, default=1000)
    collect_parser.add_argument("--seed", type=int, default=2026)
    collect_parser.add_argument(
        "--ids", help="explicit comma-separated IDs for a smoke test"
    )
    collect_parser.add_argument("--workers", type=positive, default=4)
    collect_parser.add_argument("--size", type=int, choices=(200, 800), default=200)
    collect_parser.set_defaults(run=collect)
    rank_parser = commands.add_parser(
        "rank", help="rank silhouettes and optionally a local CLIP model"
    )
    rank_parser.add_argument("--font", type=Path, action="append", default=[])
    rank_parser.add_argument(
        "--vision-model", help="Hugging Face CLIP model name or local directory"
    )
    rank_parser.set_defaults(run=rank)
    sheets_parser = commands.add_parser(
        "sheets", help="write ten contact sheets and blank human review CSV"
    )
    sheets_parser.add_argument(
        "--method",
        choices=("template", "vision_cartoon", "vision_silhouette"),
        default="template",
    )
    sheets_parser.add_argument("--top", type=positive, default=20)
    sheets_parser.set_defaults(run=sheets)
    benchmark_parser = commands.add_parser(
        "benchmark", help="measure readable top-k against human reviews"
    )
    benchmark_parser.add_argument("--reviews", type=Path, required=True)
    benchmark_parser.add_argument("--top", type=positive, default=20)
    benchmark_parser.set_defaults(run=benchmark)
    fetch_parser = commands.add_parser(
        "fetch-shortlist", help="cache advertised states and optionally coordinates"
    )
    fetch_parser.add_argument("--shortlist", type=Path, required=True)
    fetch_parser.add_argument("--coordinates", action="store_true")
    fetch_parser.set_defaults(run=fetch_shortlist)
    args = parser.parse_args(argv)
    args.workdir = args.workdir.resolve()
    try:
        args.run(args)
    except (OSError, ValueError, KeyError) as error:
        print(f"digit-search: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
