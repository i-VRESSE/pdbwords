"""Checks for reproducible downloads and honest pilot evaluation."""

import csv
import importlib.util
import io
import json
import urllib.error
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

SPEC = importlib.util.spec_from_file_location(
    "digit_search", Path(__file__).parents[1] / "scripts/digit_search.py"
)
assert SPEC is not None and SPEC.loader is not None
search = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(search)


def catalogue():
    return {
        "2wcd": {
            "image_suffix": ["_image-200x200.png", "_image-800x800.png", ".molj"],
            "assembly": {
                "2": {
                    "image": [
                        {
                            "filename": "2wcd_assembly_2_chain_top",
                            "clean_description": "a protein",
                        },
                        {
                            "filename": "2wcd_assembly_2_chemically_distinct_molecules_top"
                        },
                    ]
                }
            },
            # Entity images are assemblies, not individual chain renders.
            "entity": {"1": {"image": [{"filename": "2wcd_entity_1_top"}]}},
        }
    }


def test_catalogue_uses_advertised_sizes_and_one_coloring():
    candidates = search.catalogue_candidates("2wcd", catalogue(), 200)
    assert len(candidates) == 1
    assert candidates[0]["kind"] == "assembly"
    assert candidates[0]["assembly"] == "2"
    assert candidates[0]["image_url"].endswith("_chain_top_image-200x200.png")
    assert candidates[0]["state_url"].endswith("_chain_top.molj")
    assert candidates[0]["caption_url"] is None
    data = catalogue()
    data["2wcd"]["image_suffix"] = ["_image-100x100.png"]
    assert search.catalogue_candidates("2wcd", data, 800)[0]["image_url"].endswith(
        "100x100.png"
    )


def test_cache_reuses_downloads_and_post_payloads(tmp_path, monkeypatch):
    calls = []

    def download(request, **kwargs):
        calls.append(request.data)
        return io.BytesIO(b'{"downloaded": true}')

    monkeypatch.setattr(search.urllib.request, "urlopen", download)
    cache = search.Cache(tmp_path)
    first = cache.fetch("https://example.test/query", {"count": 10})
    assert search.read_json(first) == {"downloaded": True}
    assert cache.fetch("https://example.test/query", {"count": 10}) == first
    assert (
        search.Cache(tmp_path, offline=True).fetch(
            "https://example.test/query", {"count": 10}
        )
        == first
    )
    cache.fetch("https://example.test/query", {"count": 20})
    assert len(calls) == 2
    with pytest.raises(FileNotFoundError, match="Not cached"):
        search.Cache(tmp_path, offline=True).fetch("https://example.test/uncached")
    assert len(calls) == 2


def test_missing_responses_are_cached_and_transient_errors_retry(tmp_path, monkeypatch):
    calls = []

    def missing(request, **kwargs):
        calls.append(request.full_url)
        raise urllib.error.HTTPError(request.full_url, 404, "missing", {}, None)

    monkeypatch.setattr(search.urllib.request, "urlopen", missing)
    cache = search.Cache(tmp_path)
    for _ in range(2):
        with pytest.raises(FileNotFoundError):
            cache.fetch("https://example.test/missing")
    assert len(calls) == 1
    with pytest.raises(FileNotFoundError):
        search.Cache(tmp_path, retry_missing=True).fetch("https://example.test/missing")
    assert len(calls) == 2

    def flaky(request, **kwargs):
        calls.append(request.full_url)
        if len(calls) == 3:
            raise urllib.error.HTTPError(request.full_url, 503, "unavailable", {}, None)
        return io.BytesIO(b"complete")

    monkeypatch.setattr(search.urllib.request, "urlopen", flaky)
    monkeypatch.setattr(search.time, "sleep", lambda _: None)
    path = cache.fetch("https://example.test/transient")
    assert path.read_bytes() == b"complete"
    assert len(calls) == 4


def test_partial_download_is_not_a_cache_hit(tmp_path, monkeypatch):
    class Interrupted(io.BytesIO):
        def read(self, size=-1):
            raise ConnectionError("interrupted")

    monkeypatch.setattr(
        search.urllib.request, "urlopen", lambda *a, **kw: Interrupted()
    )
    cache = search.Cache(tmp_path, retries=1)
    with pytest.raises(ConnectionError):
        cache.fetch("https://example.test/image")
    with pytest.raises(FileNotFoundError):
        search.Cache(tmp_path, offline=True).fetch("https://example.test/image")


def test_normalization_preserves_holes_aspect_and_removes_axis():
    image = Image.new("RGBA", (200, 200), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((70, 45, 130, 155), outline="red", width=9)
    _, expected = search.normalize(image)
    draw.line((5, 180, 5, 195, 20, 195), fill="blue", width=2)
    cartoon, normalized = search.normalize(image)
    assert search.bits(normalized) == search.bits(expected)
    assert normalized.getpixel((32, 32)) == 0
    assert cartoon.getpixel((32, 32)) == (255, 255, 255)
    x1, y1, x2, y2 = normalized.getbbox()
    assert (x2 - x1) / (y2 - y1) == pytest.approx(61 / 111, abs=0.03)
    with pytest.raises(ValueError, match="no molecular foreground"):
        search.normalize(Image.new("RGB", (100, 100), "white"))


def test_pilot_runs_offline_from_cached_catalogue_through_benchmark(
    tmp_path, monkeypatch
):
    image = Image.new("RGB", (200, 200), "white")
    ImageDraw.Draw(image).ellipse((65, 25, 135, 175), outline="blue", width=12)
    image_bytes = io.BytesIO()
    image.save(image_bytes, format="PNG")
    calls = []

    def download(request, **kwargs):
        calls.append(request.full_url)
        return io.BytesIO(
            json.dumps(catalogue()).encode()
            if request.full_url.endswith(".json")
            else image_bytes.getvalue()
        )

    monkeypatch.setattr(search.urllib.request, "urlopen", download)
    prefix = ["--workdir", str(tmp_path)]
    assert search.main(prefix + ["collect", "--ids", "2wcd"]) == 0
    assert len(calls) == 2
    assert search.main(prefix + ["--offline", "collect", "--ids", "2wcd"]) == 0
    assert len(calls) == 2
    assert search.main(prefix + ["rank"]) == 0
    scores = search.read_json(tmp_path / "rankings.json")
    assert set(scores["records"][0]["template"]) == set(search.LABELS)
    assert scores["scores_are_probabilities"] is False
    assert search.main(prefix + ["sheets", "--top", "1"]) == 0
    reviews_path = tmp_path / "sheets/template/reviews.csv"
    original_reviews = reviews_path.read_bytes()
    assert search.main(prefix + ["sheets", "--top", "1"]) == 0
    assert reviews_path.read_bytes() == original_reviews
    assert (
        search.main(
            prefix + ["benchmark", "--reviews", str(reviews_path), "--top", "1"]
        )
        == 0
    )
    report = search.read_json(tmp_path / "benchmark.json")
    assert report["reviewed_pairs"] == 0
    assert report["methods"]["template"]["0"]["precision_at_k"] is None
    assert search.read_json(tmp_path / "reviewed-shortlist.json")["0"] == []
    with reviews_path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    rows[0].update(readable="yes", reviewer="Test reviewer", confusable="O")
    with reviews_path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    assert (
        search.main(
            prefix + ["benchmark", "--reviews", str(reviews_path), "--top", "1"]
        )
        == 0
    )
    assert (
        search.read_json(tmp_path / "benchmark.json")["methods"]["template"]["0"][
            "precision_at_k"
        ]
        == 0
    )
    assert search.read_json(tmp_path / "reviewed-shortlist.json")["0"] == []


def test_discovery_is_deterministic_and_larger_samples_reuse_query(
    tmp_path, monkeypatch
):
    calls = []

    def download(request, **kwargs):
        calls.append(request.full_url)
        return io.BytesIO(
            json.dumps(
                {"result_set": [{"identifier": f"{i:04d}_1"} for i in range(20)]}
            ).encode()
        )

    monkeypatch.setattr(search.urllib.request, "urlopen", download)
    cache = search.Cache(tmp_path)
    small = search.discover(cache, 10, 2026)
    large = search.discover(cache, 20, 2026)
    assert set(small["entries"]) <= set(large["entries"])
    assert len(calls) == 1
    assert search.discover(cache, 10, 2026) == small
