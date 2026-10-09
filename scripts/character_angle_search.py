"""Search character shapes across rigid rotations of cached PDBe assembly views."""

from __future__ import annotations

import argparse
import csv
import math
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

import character_search as search


def fit(mask: Image.Image) -> Image.Image:
    bounds = mask.getbbox()
    canvas = Image.new("L", (64, 64))
    if bounds:
        mask = mask.crop(bounds)
        mask.thumbnail((56, 56), Image.Resampling.NEAREST)
        canvas.paste(mask, ((64 - mask.width) // 2, (64 - mask.height) // 2))
    return canvas


def references(labels, font_paths=None):
    fonts = [ImageFont.truetype(str(path), 90) for path in (font_paths or [])]
    if not fonts:
        fonts = [ImageFont.load_default(size=90)]
    for name in ("DejaVuSans.ttf", "DejaVuSansMono.ttf", "DejaVuSerif.ttf"):
        try:
            fonts.append(ImageFont.truetype(name, 90))
        except OSError:
            pass
    result = {label: [] for label in labels}
    for label in labels:
        for font in fonts:
            im = search.render_glyph(label, font)
            _, mask = search.normalize(im)
            for variant in (
                mask,
                mask.filter(ImageFilter.MinFilter(3)),
                mask.filter(ImageFilter.MaxFilter(3)),
            ):
                b = search.bits(fit(variant))
                result[label].append(b)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workdir", type=Path, default=Path("digit-pilot"))
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--step", type=search.positive, default=15)
    parser.add_argument("--top", type=search.positive, default=10)
    parser.add_argument("--workers", type=search.positive, default=1)
    parser.add_argument(
        "--max-occupancy",
        type=float,
        default=0.68,
        help="maximum foreground fraction in the silhouette bounds; lower values favor open shapes",
    )
    search.add_targets(parser)
    parser.add_argument("--font", type=Path, action="append", default=[])
    parser.add_argument(
        "--rankings",
        type=Path,
        help="alternate ranking snapshot with cached silhouettes",
    )
    args = parser.parse_args(argv)
    if not 0 < args.max_occupancy <= 1:
        parser.error("--max-occupancy must be greater than 0 and at most 1")
    root = args.workdir.resolve()
    out = args.output.resolve() if args.output else root / "angle-search"
    out.mkdir(parents=True, exist_ok=True)
    reviewed_path = root / "reviewed-shortlist.json"
    approved = search.read_json(reviewed_path) if reviewed_path.exists() else {}
    rankings = search.read_json(args.rankings or root / "rankings.json")
    try:
        targets = search.target_characters(
            args, rankings.get("characters", "0123456789")
        )
    except ValueError as error:
        parser.error(str(error))
    digits = [d for d in targets if not approved.get(d)]
    approved_ids = {
        row["id"].split("_")[0] for rows in approved.values() for row in rows
    }
    source = rankings["records"]
    labels = list(dict.fromkeys((*targets, *search.LABELS[:-1])))
    reference = references(labels, args.font)
    ranked = {d: [] for d in digits}
    progress = search.Progress("Rotation search", len(source))

    def report(index):
        if index % 500 == 0 or index == len(source):
            progress.update(index)

    def score_record(record):
        if record["pdb_id"] in approved_ids:
            return None
        with Image.open(root / record["silhouette_path"]) as im:
            mask = ImageOps.invert(im.convert("L")).point(
                lambda v: 255 if v >= 128 else 0
            )
        # Close tiny gaps, but preserve digit-sized openings.
        mask = mask.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
        bounds = mask.getbbox()
        if not bounds:
            return None
        occupancy = search.bits(mask).bit_count() / (
            (bounds[2] - bounds[0]) * (bounds[3] - bounds[1])
        )
        if occupancy > args.max_occupancy:
            return None
        best = {d: (-1, None, None) for d in digits}
        for clockwise in range(0, 360, args.step):
            b = search.bits(
                fit(
                    mask.rotate(
                        -clockwise, expand=True, resample=Image.Resampling.NEAREST
                    )
                )
            )
            scores = {
                label: max((b & t).bit_count() / (b | t).bit_count() for t in variants)
                for label, variants in reference.items()
            }
            for digit in digits:
                # Reward matching the target and penalize similarly strong competitors.
                competitor = max(v for k, v in scores.items() if k != digit)
                score = scores[digit] + 1.0 * (scores[digit] - competitor)
                if score > best[digit][0]:
                    best[digit] = (score, clockwise, scores)
        return {
            digit: {
                **record,
                "rotation_clockwise_deg": angle,
                "angle_score": score,
                "glyph_iou": scores[digit],
                "competing_label": max(
                    (label for label in scores if label != digit),
                    key=scores.__getitem__,
                ),
                "occupancy": occupancy,
            }
            for digit, (score, angle, scores) in best.items()
        }

    retained = 0
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        for index, result in enumerate(executor.map(score_record, source), 1):
            if result is not None:
                retained += 1
                for digit, record in result.items():
                    ranked[digit].append(record)
            report(index)
    top = {}
    for digit in digits:
        seen = set()
        top[digit] = []
        for record in sorted(ranked[digit], key=lambda r: (-r["angle_score"], r["id"])):
            if record["pdb_id"] in seen:
                continue
            seen.add(record["pdb_id"])
            top[digit].append(record)
            if len(top[digit]) == args.top:
                break
    search.write_json(out / "shortlist.json", top)
    search.write_json(
        out / "search.json",
        {
            "source_images": len(source),
            "retained_sparse_views": retained,
            "characters": digits,
            "digits": [d for d in digits if d.isdigit()],
            "excluded_characters": [d for d in targets if approved.get(d)],
            "excluded_pdb_ids": sorted(approved_ids),
            "rotation_step_degrees": args.step,
            "max_occupancy": args.max_occupancy,
            "method": "thin glyph IoU + 1.0 target/competitor margin; silhouettes filtered by foreground occupancy; rigid rotations only",
            "scores_are_probabilities": False,
        },
    )
    with (out / "review-template.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            (
                "character",
                "rank",
                "id",
                "rotation_clockwise_deg",
                "readable",
                "confusable",
                "reviewer",
                "notes",
            )
        )
        for digit, records in top.items():
            sheet = Image.new(
                "RGB", (1000, math.ceil(len(records) / 4) * 290 + 35), "white"
            )
            draw = ImageDraw.Draw(sheet)
            draw.text(
                (10, 8),
                f"Character {digit}: new rigid-angle candidates; scores are not probabilities",
                fill="black",
            )
            for rank, r in enumerate(records, 1):
                with Image.open(root / r["image_path"]) as im:
                    cartoon, _ = search.normalize(im, 220)
                cartoon = cartoon.rotate(
                    -r["rotation_clockwise_deg"], expand=True, fillcolor="white"
                )
                cartoon.thumbnail((220, 220))
                x = (rank - 1) % 4 * 250
                y = (rank - 1) // 4 * 290 + 35
                sheet.paste(
                    cartoon,
                    (x + (250 - cartoon.width) // 2, y + (220 - cartoon.height) // 2),
                )
                draw.text(
                    (x + 5, y + 222),
                    f"#{rank}: {r['pdb_id']} asm {r['assembly']} {r['view']}",
                    fill="black",
                )
                draw.text(
                    (x + 5, y + 239),
                    f"rotate {r['rotation_clockwise_deg']} deg clockwise; IoU {r['glyph_iou']:.3f}",
                    fill="black",
                )
                draw.text(
                    (x + 5, y + 255),
                    f"competing shape: {r['competing_label']}",
                    fill="black",
                )
                destination = (
                    out
                    / "candidates"
                    / f"{search.character_filename(digit)}-{rank:02d}-{r['id']}.png"
                )
                destination.parent.mkdir(exist_ok=True)
                cartoon.save(destination)
                writer.writerow(
                    (digit, rank, r["id"], r["rotation_clockwise_deg"], "", "", "", "")
                )
            sheet.save(out / f"{search.character_filename(digit)}.png")
    print(f"Saved new candidate sheets to {out}", flush=True)


if __name__ == "__main__":
    main()
