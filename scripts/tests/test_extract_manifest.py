import json
from pathlib import Path

import extract_manifest


def test_extraction_preserves_digit_reviews_and_updates_letters(tmp_path, monkeypatch):
    output = tmp_path / "manifest.json"
    digits = {"8": {"pdb_id": "3PON", "review": {"status": "accepted"}}}
    output.write_text(json.dumps({"digits": digits, "letters": {"A": {"old": True}}}))
    monkeypatch.setattr(extract_manifest, "ALPHABET", "A")
    monkeypatch.setattr(extract_manifest, "prepare_sessions", lambda *_args: tmp_path)
    monkeypatch.setattr(
        extract_manifest, "session_metadata", lambda *_args: {"pdb_id": "3IFZ"}
    )
    assert (
        extract_manifest.main(["--sessions", str(tmp_path), "--output", str(output)])
        == 0
    )
    manifest = json.loads(output.read_text())
    assert manifest["digits"] == digits
    assert manifest["letters"] == {"A": {"pdb_id": "3IFZ"}}


def test_extractor_defaults_to_manifest_beside_app_entrypoint():
    args = extract_manifest.parse_args([])
    root = Path(extract_manifest.__file__).resolve().parent.parent
    assert args.output == root / "src/manifest.json"
    assert args.images == root / "assets"
