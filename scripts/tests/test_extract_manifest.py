import json
from pathlib import Path

import pytest
from PIL import Image

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


def test_partial_extraction_preserves_other_letters(tmp_path, monkeypatch):
    output = tmp_path / "manifest.json"
    output.write_text(
        json.dumps({"letters": {"A": {"kept": True}, "P": {"old": True}}})
    )
    monkeypatch.setattr(extract_manifest, "prepare_sessions", lambda *_args: tmp_path)
    monkeypatch.setattr(
        extract_manifest, "session_metadata", lambda *_args: {"updated": True}
    )
    extract_manifest.main(
        ["--sessions", str(tmp_path), "--letters", "ps", "--output", str(output)]
    )
    assert json.loads(output.read_text())["letters"] == {
        "A": {"kept": True},
        "P": {"updated": True},
        "S": {"updated": True},
    }


@pytest.mark.parametrize("letter,visible", [("P", "A"), ("S", "BD")])
def test_session_extraction_excludes_hidden_chains_from_selection_and_bounds(
    tmp_path, letter, visible
):
    from pymol import cmd

    cmd.reinitialize()
    atoms = []
    serial = 0
    for chain in "ABCD":
        offset = 0 if chain in visible else 1000
        for residue in range(1, 4):
            serial += 1
            x, y, z = offset + residue, residue * 2, residue * 3
            atoms.append(
                f"ATOM  {serial:5d}  CA  ALA {chain}{residue:4d}    "
                f"{x:8.3f}{y:8.3f}{z:8.3f}  1.00 20.00           C"
            )
        atoms.append("TER")
    cmd.read_pdbstr("\n".join(atoms), "3afc")
    cmd.hide("everything", "all")
    cmd.show("cartoon", " or ".join(f"chain {chain}" for chain in visible))
    session = tmp_path / f"{letter}.pse"
    cmd.save(str(session))
    Image.new("RGBA", (100, 200)).save(tmp_path / f"{letter.lower()}.png")

    geometry = extract_manifest.session_metadata(session, tmp_path, letter)
    assert geometry["chains"] == {chain: [1, 3] for chain in visible}
    assert geometry["projected_center"] == [2.0, 4.0, 6.0]
    assert geometry["projected_size"] == [2.0, 4.0, 6.0]
