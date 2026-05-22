"""§6.2 — DNA-Trace property-based oracle (Layer 2).

The barcode codec must be a bijection over all valid segment strings, not just
the spec example (TESTING_DOCTRINE §2, §6.2). Awaiting F0-T2d.
"""
from __future__ import annotations

import string

import pytest
from hypothesis import given
from hypothesis import strategies as st

from data_engineering.gold.dna_trace import Barcode, decode_barcode, encode_barcode

pytestmark = [pytest.mark.critical, pytest.mark.property]

# Barcode segments in the spec are alphanumeric and, crucially, dash/dot-free
# (the dash is the segment separator, the dot is reserved by WebDataset).
_segment = st.text(alphabet=string.ascii_uppercase + string.digits, min_size=1, max_size=8)


@given(_segment, _segment, _segment, _segment, _segment, _segment)
def test_decode_is_left_inverse_of_encode(s0, s1, s2, s3, s4, s5) -> None:
    barcode = Barcode(s0, s1, s2, s3, s4, s5)
    assert decode_barcode(encode_barcode(barcode)) == barcode


@given(_segment, _segment, _segment, _segment, _segment, _segment)
def test_encoded_key_has_exactly_five_separators(s0, s1, s2, s3, s4, s5) -> None:
    # Six dash-free segments -> exactly five '-' separators.
    key = encode_barcode(Barcode(s0, s1, s2, s3, s4, s5))
    assert key.count("-") == 5
    assert "." not in key
