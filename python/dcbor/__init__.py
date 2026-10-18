"""Deterministic CBOR (dCBOR) encoding and decoding.

Python API for the native `_dcbor` extension module. See the project README
for the Python <-> dCBOR type mapping.
"""

from ._dcbor import CBORError, CBORMap, CBORTag, diagnostic, diagnostic_flat, dumps, load, loads, validate

__all__ = [
    "CBORError",
    "CBORTag",
    "CBORMap",
    "diagnostic",
    "diagnostic_flat",
    "dumps",
    "loads",
    "load",
    "validate",
]

__version__ = "0.1.1"
