"""Checks for intact geometry and exclusion of already approved digits/structures."""

import json
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont, ImageOps


@pytest.mark.parametrize("targets, expected", [("0123456789", "1234569"), ("45", "45")])
def test_angle_search_preserves_inputs_and_excludes_approved(
    tmp_path, monkeypatch, targets, expected
):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "scripts"))
    import digit_angle_search as angles
    import digit_search as search

    image = Image.new("RGB", (100, 100), "white")
    ImageDraw.Draw(image).text(
        (20, 10), "2", font=ImageFont.load_default(size=70), fill="blue"
    )
    image.save(tmp_path / "candidate.png")
    _, mask = search.normalize(image)
    ImageOps.invert(mask).save(tmp_path / "mask.png")
    records = [
        {
            "id": p + "_assembly_1_chain_front",
            "pdb_id": p,
            "assembly": "1",
            "view": "front",
            "image_path": "candidate.png",
            "silhouette_path": "mask.png",
        }
        for p in ("9qg9", "2wad")
    ]
    search.write_json(tmp_path / "rankings.json", {"records": records})
    approved = {
        d: [{"id": p + "_assembly_1_chain_side"}]
        for d, p in [("0", "9qg9"), ("7", "9gck"), ("8", "8g2z")]
    }
    search.write_json(tmp_path / "reviewed-shortlist.json", approved)
    original = (tmp_path / "reviewed-shortlist.json").read_bytes()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "digit_angle_search",
            "--workdir",
            str(tmp_path),
            "--output",
            str(tmp_path / "results"),
            "--step",
            "90",
            "--top",
            "1",
            "--digits",
            targets,
        ],
    )
    angles.main()
    result = json.loads((tmp_path / "results/shortlist.json").read_text())
    assert set(result) == set(expected)
    assert all(r["pdb_id"] == "2wad" for rows in result.values() for r in rows)
    assert all(
        r["rotation_clockwise_deg"] in (0, 90, 180, 270)
        for rows in result.values()
        for r in rows
    )
    assert (tmp_path / "reviewed-shortlist.json").read_bytes() == original
    assert json.loads((tmp_path / "rankings.json").read_text())["records"] == records
