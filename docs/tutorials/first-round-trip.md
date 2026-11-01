# Your first dCBOR round trip

This tutorial walks through installing the package, encoding a small Python
value, and decoding it again. The encoded result is the CBOR
{term}`wire bytes`; the decoder checks that those bytes follow the dCBOR
{term}`canonical encoding` rules.

## Install the package

Stable package releases are distributed through
[GitHub Releases](https://github.com/WizzyGeek/pyo3dCBOR/releases); PyPI
publication is not configured. Download the wheel that matches your Python
version, operating system, and CPU architecture, then install that local file
in your virtual environment:

```sh
python -m venv .venv
```

Activate the environment. On macOS or Linux:

```sh
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Install the wheel you downloaded, using its actual path:

```sh
python -m pip install /path/to/downloaded/dcbor-wheel.whl
```

If no wheel is available for your platform, build from a source checkout with
Git, Rust, and Cargo installed. In the active environment you created above,
clone the repository and enter its root:

```sh
git clone https://github.com/WizzyGeek/pyo3dCBOR.git
cd pyo3dCBOR
```

Install Maturin and build the extension into that environment:

```sh
python -m pip install maturin
maturin develop --release --locked
```

The source checkout's version may differ from the available release assets.
Check the [release page](https://github.com/WizzyGeek/pyo3dCBOR/releases) for
the packaged versions, and install a wheel that matches your Python version
and platform.

## Encode a Python value

Start with a dictionary containing text keys, a string, an integer, and a
list. {py:func}`dcbor.dumps` returns a `bytes` object:

```{doctest}
>>> import dcbor
>>> record = {"name": "Ada", "scores": [7, 8]}
>>> wire = dcbor.dumps(record)
>>> type(wire).__name__
'bytes'
```

The bytes are compact and can be stored or sent through an application
protocol that carries binary payloads. The protocol still needs to define
message {term}`framing` when the transport is a stream; see the how-to guides
for [file persistence](../how-to/persist-values.md). To inspect the value in a
readable form, use {py:func}`dcbor.diagnostic_flat`:

```{doctest}
>>> import dcbor
>>> wire = dcbor.dumps({"name": "Ada", "scores": [7, 8]})
>>> dcbor.diagnostic_flat(wire)
'{"name": "Ada", "scores": [7, 8]}'
```

Diagnostic notation is useful for inspection, but the returned string is not
the encoded payload. Keep and pass the original bytes when you need to decode
or transmit the value.

## Decode and check the result

{py:func}`dcbor.loads` accepts one complete byte string and returns Python
values. For ordinary maps, the result is a `dict`:

```{doctest}
>>> import dcbor
>>> record = {"name": "Ada", "scores": [7, 8]}
>>> wire = dcbor.dumps(record)
>>> restored = dcbor.loads(wire)
>>> restored == record
True
>>> type(restored).__name__
'dict'
```

That check is a {term}`round trip`: encode a value, decode the bytes, and
compare the result with the input. Text values are normalized to Unicode
{term}`NFC` before encoding, so the equality you should expect follows the
documented [Python type mapping and limits](../reference/types-and-limits.md).

## See the deterministic bytes

Equivalent maps encode to the same bytes even if their Python insertion order
differs. This fixed example checks the expected wire representation directly:

```{doctest}
>>> import dcbor
>>> dcbor.dumps({"b": 2, "a": 1}).hex()
'a2616101616202'
>>> dcbor.dumps({"a": 1, "b": 2}) == bytes.fromhex("a2616101616202")
True
```

The values and map keys supported by the package are listed in the
[type reference](../reference/types-and-limits.md). Next, use the focused
[how-to guides](../how-to/index.md) for persistence, stable digests, input
validation, and maps with keys Python dictionaries cannot preserve.
