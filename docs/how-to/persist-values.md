# Persist values in a binary file

Use this pattern to save a dCBOR value to a file and load it later. A
{term}`wire bytes` file should be opened in binary mode.

```{doctest}
>>> from pathlib import Path
>>> from tempfile import TemporaryDirectory
>>> import dcbor
>>> wire = bytes.fromhex("a2616101617a81f5")
>>> expected = {"a": 1, "z": [True]}
>>> with TemporaryDirectory() as directory:
...     path = Path(directory) / "record.cbor"
...     _ = path.write_bytes(wire)
...     with path.open("rb") as stream:
...         restored = dcbor.load(stream)
>>> restored == expected
True
```

`Path.write_bytes()` writes the exact bytes. {py:func}`dcbor.load` reads a
binary file object once and decodes its complete contents, using the same
checks as {py:func}`dcbor.loads`. It does not incrementally parse a large file;
the full encoded value is read into memory. The example's fixed bytes decode
to `{"a": 1, "z": [True]}`.

The input should contain exactly one complete dCBOR item. Appending another
item or arbitrary bytes makes the input invalid. If you store multiple values
in one file, define framing in your application—for example, a length prefix
for each value—and pass each complete frame to `load` or `loads` separately.

See the [serialization API](../reference/serialization.md) for file and byte
decoding, and [validate external data](validate-external-cbor.md) for strict
input checks.
