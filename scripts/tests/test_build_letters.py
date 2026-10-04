import importlib
from pathlib import Path

import pytest


class FakePyMOLCommand:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def hide(self, representation: str, selection: str) -> None:
        self.calls.append(("hide", representation, selection))

    def show(self, representation: str, selection: str) -> None:
        self.calls.append(("show", representation, selection))

    def cartoon(self, style: str, selection: str) -> None:
        self.calls.append(("cartoon", style, selection))


def test_builder_applies_distinct_pymol_theme() -> None:
    builder = importlib.import_module("build_letters")
    command = FakePyMOLCommand()

    builder.apply_theme(command, "tube")

    assert command.calls == [
        ("hide", "everything", "all"),
        ("show", "cartoon", "polymer.protein"),
        ("cartoon", "tube", "polymer.protein"),
    ]


def test_builder_accepts_letters_and_validates_themes() -> None:
    builder = importlib.import_module("build_letters")
    args = builder.parse_args(["--letters", "ABC", "--theme", "loop"])

    assert args.letters == "ABC"
    assert args.theme == "loop"


def test_builder_rejects_digits() -> None:
    builder = importlib.import_module("build_letters")

    with pytest.raises(ValueError, match="--letters must contain only A-Z"):
        builder.main(["--letters", "42"])


def test_builder_defaults_to_repository_assets() -> None:
    builder = importlib.import_module("build_letters")
    args = builder.parse_args([])

    assert builder.__file__ is not None
    assert (
        args.manifest
        == Path(builder.__file__).resolve().parent.parent / "src/manifest.json"
    )
    assert args.output_dir is None
