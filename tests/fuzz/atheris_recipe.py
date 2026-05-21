#!/usr/bin/env python3
"""Atheris coverage-guided fuzz harness for the recipe parser (TESTING_DOCTRINE §6.4).

Atheris needs a native libFuzzer/clang build and is an OPTIONAL dependency (see
requirements-dev.txt). This script is NOT collected by pytest — it is a
standalone fuzz entrypoint. Run it directly, from the repo root, in the venv:

    .venv/bin/python tests/fuzz/atheris_recipe.py            # endless fuzzing
    .venv/bin/python tests/fuzz/atheris_recipe.py -runs=200000

Finding: once the F0-T2b parser lands, the only acceptable outcomes are a
parsed Recipe or a RecipeError. Any other uncaught exception is a defect.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the `src` package root importable when run as a standalone script.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

try:
    import atheris
except ImportError:  # pragma: no cover - optional dependency
    sys.exit(
        "atheris not installed — optional coverage-guided fuzz dependency.\n"
        "Hypothesis still covers Layer-3 fuzzing (tests/fuzz/test_fuzz_parsers.py)."
    )

with atheris.instrument_imports():
    from data_engineering.gold.recipe import RecipeError, parse_recipe


def _one_input(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    text = fdp.ConsumeUnicodeNoSurrogates(fdp.remaining_bytes())
    try:
        parse_recipe(text)
    except RecipeError:
        pass  # controlled, expected rejection
    except NotImplementedError:
        pass  # skeleton phase — parser owned by F0-T2b


def main() -> None:
    atheris.Setup(sys.argv, _one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
