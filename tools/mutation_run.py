"""Mutation-gate runner — mutmut with string-literal mutation disabled.

TESTING_DOCTRINE §3 policy (Decision Lock 2026-05-22). mutmut mutates *every*
string literal; on fail-loud code that is dense with diagnostic exception
messages this produces a flood of **equivalent mutants** — e.g.

    raise RecipeError(f"{ctx}: missing field '{key}'")
    raise RecipeError("XXmissing fieldXX")        # mutmut string mutant

The data contract is the exception *type*, which the suite asserts; the message
wording is diagnostic, not behaviour. Counting message mutants would make the
kill-rate measure punctuation coverage, not behavioural coverage.

mutmut 3.x exposes no per-operator switch, so this runner drops the string
operator from its registry (in place, before the CLI imports it) and then
delegates unchanged. Every other operator — numbers, names, comparison and
boolean operators, argument removal, keywords — is kept: real behaviour is
still mutated and still gated at >= 90 % (critical) / >= 85 % (core).

Run from the repo root, inside the Linux mutation environment:
    python tools/mutation_run.py run
See tools/run_mutation.sh for the OrbStack wrapper.
"""
from __future__ import annotations

import mutmut.node_mutation as node_mutation

# Drop the string-literal operator in place, so modules that already did
# `from mutmut.node_mutation import mutation_operators` observe the change.
_removed = [op for op in node_mutation.mutation_operators if op[1] is node_mutation.operator_string]
node_mutation.mutation_operators[:] = [
    op for op in node_mutation.mutation_operators if op[1] is not node_mutation.operator_string
]
if not _removed:  # fail loud if a mutmut upgrade renamed the operator
    raise SystemExit(
        "mutation_run: operator_string not found in mutmut's registry — "
        "the TESTING_DOCTRINE §3 string-mutation policy is no longer applied. "
        "Re-check mutmut.node_mutation after the upgrade."
    )

from mutmut.__main__ import cli  # noqa: E402 — must import after the patch

if __name__ == "__main__":
    cli()
