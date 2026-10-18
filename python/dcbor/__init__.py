"""Deterministic CBOR (dCBOR) encoding and decoding.

Thin, Pythonic wrapper around the native `_dcbor` extension module, which
binds to Blockchain Commons' `dcbor` Rust crate via PyO3. See the project
README for the Python <-> dCBOR type mapping.
"""

from ._dcbor import CBORError, CBORMap, CBORTag, diagnostic, diagnostic_flat, dumps, loads, validate

__all__ = [
    "CBORError",
    "CBORTag",
    "CBORMap",
    "diagnostic",
    "diagnostic_flat",
    "dumps",
    "loads",
    "validate",
]

__version__ = "0.1.1"
