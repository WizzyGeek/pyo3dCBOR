# Python API reference

```{py:module} dcbor
```

`dcbor` exposes a small API for deterministic {term}`CBOR` ({term}`dCBOR`):
encode Python values, decode a complete byte string or file, inspect wire bytes,
and use lossless map and tag objects where built-in Python types are not enough.

```{py:data} __version__
```

The package version is a string. It follows the installed distribution version;
the value in this source tree is `0.1.1`.

```{doctest}
>>> import dcbor
>>> isinstance(dcbor.__version__, str)
True
>>> dcbor.dumps({"answer": 42}).hex()
'a166616e73776572182a'
>>> dcbor.diagnostic_flat(dcbor.dumps({"answer": 42}))
'{"answer": 42}'
```

## Pages

```{toctree}
:maxdepth: 1

serialization
inspection
cbor-map
cbor-tag
errors
types-and-limits
```

Each page describes the Python binding's behavior. The linked terms explain the
wire concepts used by the API.
