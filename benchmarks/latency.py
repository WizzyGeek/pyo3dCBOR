"""Compare encode, decode, and round-trip latency for JSON-compatible values.

From the repository root, install the pinned comparator and run against a
release-built extension::

    python -m pip install -r benchmarks/requirements.txt
    CARGO_BUILD_JOBS=2 maturin develop --release --locked
    PYTHONPATH=python python benchmarks/latency.py

The runner launches one fresh Python process per repetition. It writes raw
measurements to ``benchmarks/latency/results.json`` and replaces the stable
chart at ``.github/assets/graphs/latency.svg``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.machinery
import importlib.metadata
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

from chart_style import sha256_file
from fixtures import fixtures


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = Path(__file__).resolve().parent / "latency"
ARTIFACT_DIR = Path(os.environ.get("DCBOR_BENCHMARK_ARTIFACT_DIR", ROOT / ".github" / "assets" / "graphs"))
PACKAGE_ROOT = Path(os.environ.get("DCBOR_PACKAGE_ROOT", ROOT / "python"))
RELEASE_ARTIFACT = Path(os.environ.get("DCBOR_RELEASE_ARTIFACT", ROOT / "target" / "release" / "lib_dcbor.so"))
SVG_PATH = Path(os.environ.get("DCBOR_LATENCY_SVG_PATH", ARTIFACT_DIR / "latency.svg"))
EXPECTED_DCBOR_VERSION = "0.1.1"
sys.path.insert(0, str(PACKAGE_ROOT))
PINNED_CBOR2 = "6.1.5"
PINNED_CBORX = "0.2.5"
PINNED_ORJSON = "3.13.0"
PINNED_MSGSPEC = "0.22.0"
PINNED_CBRRR = "1.1.0"
DEFAULT_WARMUP = 500
DEFAULT_ROUNDS = 1_000
DEFAULT_REPETITIONS = 9
IMPLEMENTATIONS = (
    "json", "dcbor", "cbor2_default", "cbor2_canonical",
    "cborx_default", "cborx_canonical", "orjson_default", "orjson_sorted",
    "msgspec_msgpack", "msgspec_msgpack_deterministic", "cbrrr_strictdagcbor",
)

OUTPUTS = {
    b"benchmarks/encoded_size/results.json",
    b"benchmarks/wire_size/results.json",
    b"benchmarks/latency/results.json",
    b"benchmarks/profile/results.json",
    b".github/assets/graphs/encoded-size.svg",
    b".github/assets/graphs/wire-size.svg",
    b".github/assets/graphs/latency.svg",
    b".github/assets/graphs/profile.svg",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def type_sensitive_equal(left: object, right: object) -> bool:
    """Compare JSON-compatible values without Python's bool/int equality trap."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        if len(left) != len(right):  # type: ignore[arg-type]
            return False
        unmatched = list(right.items())  # type: ignore[union-attr]
        for left_key, left_value in left.items():
            for index, (right_key, right_value) in enumerate(unmatched):
                if type_sensitive_equal(left_key, right_key):
                    if not type_sensitive_equal(left_value, right_value):
                        return False
                    unmatched.pop(index)
                    break
            else:
                return False
        return not unmatched
    if isinstance(left, (list, tuple)):
        return len(left) == len(right) and all(  # type: ignore[arg-type]
            type_sensitive_equal(a, b) for a, b in zip(left, right)  # type: ignore[arg-type]
        )
    if isinstance(left, float):
        return left.hex() == right.hex()  # type: ignore[union-attr]
    return left == right


def git_value(*args: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=ROOT, stderr=subprocess.DEVNULL, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def dirty_from_porcelain(status: bytes) -> bool:
    """Ignore generated benchmark reports/charts, but flag source changes."""
    for entry in status.split(b"\0"):
        if entry and entry[3:] not in OUTPUTS:
            return True
    return False


def source_worktree_dirty() -> bool | None:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all", "-z"],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return dirty_from_porcelain(result.stdout)


def command_version(*args: str) -> str | None:
    try:
        return subprocess.check_output(
            list(args), cwd=ROOT, stderr=subprocess.STDOUT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def build_provenance() -> dict[str, str | None]:
    lockfile = ROOT / "Cargo.lock"
    return {
        "rustc_version_verbose": command_version("rustc", "--version", "--verbose"),
        "cargo_version": command_version("cargo", "--version"),
        "cargo_lock_sha256": sha256(lockfile.read_bytes()) if lockfile.is_file() else None,
    }


def processor_name() -> str | None:
    name = platform.processor()
    if name:
        return name
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition(":")
            if separator and key.strip().lower() in {"model name", "hardware"}:
                return value.strip()
    except OSError:
        pass
    return None


def release_build_evidence(extension_path: Path) -> dict[str, object]:
    """Verify the loaded extension is byte-identical to Cargo's release artifact."""
    release_artifact = RELEASE_ARTIFACT.resolve()
    extension_hash = sha256(extension_path.read_bytes())
    artifact_hash = sha256(release_artifact.read_bytes()) if release_artifact.is_file() else None
    return {
        "profile": "release" if artifact_hash == extension_hash else "unverified",
        "verified_by": "SHA-256 equality with configured release artifact",
        "release_artifact": str(release_artifact),
        "release_artifact_sha256": artifact_hash,
        "extension_sha256": extension_hash,
    }


def native_extensions(module: object) -> list[dict[str, str]]:
    """Return native modules loaded by this package, with their file hashes."""
    suffixes = tuple(importlib.machinery.EXTENSION_SUFFIXES)
    module_name = getattr(module, "__name__", "")
    names = {module_name, *(name for name in sys.modules if name.startswith(module_name + "."))}
    found: list[dict[str, str]] = []
    for name in sorted(names):
        loaded = sys.modules.get(name)
        module_file = getattr(loaded, "__file__", None) if loaded is not None else None
        if module_file and str(module_file).endswith(suffixes):
            path = Path(module_file).resolve()
            found.append({"module": name, "path": str(path), "sha256": sha256(path.read_bytes())})
    return found


def extension_active(module: object) -> bool:
    """Report whether this package has its own native extension loaded."""
    return bool(native_extensions(module))


def cbor2_version(module: object) -> str:
    try:
        return importlib.metadata.version("cbor2")
    except importlib.metadata.PackageNotFoundError:
        return str(getattr(module, "__version__", "unknown"))


def environment(
    dcbor: object,
    cbor2: object,
    cborx: object,
    orjson: object,
    msgspec: object,
    cbrrr: object,
) -> dict[str, object]:
    extension_path = Path(dcbor._dcbor.__file__).resolve()  # type: ignore[attr-defined]
    native_backends = {
        name: native_extensions(module)
        for name, module in (
            ("cbor2", cbor2),
            ("cborx", cborx),
            ("orjson", orjson),
            ("msgspec", msgspec),
            ("cbrrr", cbrrr),
        )
    }
    return {
        "python_version": sys.version,
        "python_implementation": platform.python_implementation(),
        "python_executable": str(Path(sys.executable).resolve()),
        "stdlib_json_version": getattr(json, "__version__", "bundled with Python"),
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": processor_name(),
        **build_provenance(),
        "dcbor_version": dcbor.__version__,  # type: ignore[attr-defined]
        "dcbor_extension_path": str(extension_path),
        "dcbor_extension_sha256": sha256(extension_path.read_bytes()),
        "dcbor_build": release_build_evidence(extension_path),
        "cbor2_version": cbor2_version(cbor2),
        "cbor2_module_path": getattr(cbor2, "__file__", None),
        "cbor2_native_extension_active": bool(native_backends["cbor2"]),
        "orjson_version": importlib.metadata.version("orjson"),
        "orjson_module_path": getattr(orjson, "__file__", None),
        "orjson_native_extension_active": bool(native_backends["orjson"]),
        "msgspec_version": importlib.metadata.version("msgspec"),
        "msgspec_module_path": getattr(msgspec, "__file__", None),
        "msgspec_native_extension_active": bool(native_backends["msgspec"]),
        "cbrrr_version": importlib.metadata.version("cbrrr"),
        "cbrrr_module_path": getattr(cbrrr, "__file__", None),
        "cbrrr_native_extension_active": bool(native_backends["cbrrr"]),
        "native_backends": native_backends,
        "cborx_version": importlib.metadata.version("cborx"),
        "cborx_module_path": getattr(cborx, "__file__", None),
        "cborx_native_extension_active": bool(native_backends["cborx"]),
    }


def logical_fixture_hashes() -> dict[str, str]:
    return {
        name: sha256(
            json.dumps(
                value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        )
        for name, value in fixtures().items()
    }


def worker(warmup: int, rounds: int, order_offset: int) -> dict[str, object]:
    import cbor2
    import cborx
    import dcbor
    import cbrrr
    import msgspec
    import orjson

    if cbor2_version(cbor2) != PINNED_CBOR2:
        raise RuntimeError(
            f"expected cbor2=={PINNED_CBOR2}, found {cbor2_version(cbor2)}"
        )
    cborx_version = importlib.metadata.version("cborx")
    if cborx_version != PINNED_CBORX:
        raise RuntimeError(f"expected cborx=={PINNED_CBORX}, found {cborx_version}")
    for package, expected in (
        ("orjson", PINNED_ORJSON),
        ("msgspec", PINNED_MSGSPEC),
        ("cbrrr", PINNED_CBRRR),
    ):
        observed = importlib.metadata.version(package)
        if observed != expected:
            raise RuntimeError(f"expected {package}=={expected}, found {observed}")
    env = environment(dcbor, cbor2, cborx, orjson, msgspec, cbrrr)
    if dcbor.__version__ != EXPECTED_DCBOR_VERSION:  # type: ignore[attr-defined]
        raise RuntimeError(f"expected dcbor=={EXPECTED_DCBOR_VERSION}, found {dcbor.__version__}")  # type: ignore[attr-defined]
    if env["dcbor_build"]["profile"] != "release":  # type: ignore[index]
        raise RuntimeError("loaded dcbor extension does not match configured release artifact")

    msgpack_encoder = msgspec.msgpack.Encoder()
    msgpack_deterministic_encoder = msgspec.msgpack.Encoder(order="deterministic")
    msgpack_decoder = msgspec.msgpack.Decoder()

    rows: dict[str, object] = {}
    encoded_hashes: dict[str, dict[str, str]] = {}
    for name, value in fixtures().items():
        json_bytes = json.dumps(
            value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        dcbor_bytes = dcbor.dumps(value)  # type: ignore[attr-defined]
        cbor2_default_bytes = cbor2.dumps(value)
        cbor2_canonical_bytes = cbor2.dumps(value, canonical=True)
        cborx_default_bytes = cborx.dumps(value)
        cborx_canonical_bytes = cborx.dumps(value, canonical=True)
        orjson_default_bytes = orjson.dumps(value)
        orjson_sorted_bytes = orjson.dumps(value, option=orjson.OPT_SORT_KEYS)
        msgspec_msgpack_bytes = msgpack_encoder.encode(value)
        msgspec_deterministic_bytes = msgpack_deterministic_encoder.encode(value)
        cbrrr_bytes = cbrrr.encode_dag_cbor(value)
        encoded_bytes = {
            "json": json_bytes,
            "dcbor": dcbor_bytes,
            "cbor2_default": cbor2_default_bytes,
            "cbor2_canonical": cbor2_canonical_bytes,
            "cborx_default": cborx_default_bytes,
            "cborx_canonical": cborx_canonical_bytes,
            "orjson_default": orjson_default_bytes,
            "orjson_sorted": orjson_sorted_bytes,
            "msgspec_msgpack": msgspec_msgpack_bytes,
            "msgspec_msgpack_deterministic": msgspec_deterministic_bytes,
            "cbrrr_strictdagcbor": cbrrr_bytes,
        }
        if not type_sensitive_equal(json.loads(json_bytes.decode("utf-8")), value):
            raise ValueError(f"JSON changed fixture {name}")
        if not type_sensitive_equal(dcbor.loads(dcbor_bytes), value):  # type: ignore[attr-defined]
            raise ValueError(f"dCBOR changed fixture {name}")
        if not type_sensitive_equal(cbor2.loads(cbor2_default_bytes), value):
            raise ValueError(f"cbor2 default mode changed fixture {name}")
        if not type_sensitive_equal(cbor2.loads(cbor2_canonical_bytes), value):
            raise ValueError(f"cbor2 canonical mode changed fixture {name}")
        if not type_sensitive_equal(cborx.loads(cborx_default_bytes), value):
            raise ValueError(f"cborx default mode changed fixture {name}")
        if not type_sensitive_equal(cborx.loads(cborx_canonical_bytes), value):
            raise ValueError(f"cborx canonical mode changed fixture {name}")
        if not type_sensitive_equal(orjson.loads(orjson_default_bytes), value):
            raise ValueError(f"orjson default mode changed fixture {name}")
        if not type_sensitive_equal(orjson.loads(orjson_sorted_bytes), value):
            raise ValueError(f"orjson sorted mode changed fixture {name}")
        if not type_sensitive_equal(msgpack_decoder.decode(msgspec_msgpack_bytes), value):
            raise ValueError(f"msgspec MessagePack default mode changed fixture {name}")
        if not type_sensitive_equal(msgpack_decoder.decode(msgspec_deterministic_bytes), value):
            raise ValueError(f"msgspec MessagePack deterministic mode changed fixture {name}")
        if not type_sensitive_equal(cbrrr.decode_dag_cbor(cbrrr_bytes), value):
            raise ValueError(f"cbrrr strict DAG-CBOR mode changed fixture {name}")

        encoded_hashes[name] = {
            "json_utf8_sha256": sha256(encoded_bytes["json"]),
            **{
                f"{implementation}_sha256": sha256(encoded_bytes[implementation])
                for implementation in IMPLEMENTATIONS
                if implementation != "json"
            },
        }

        implementations: dict[str, dict[str, Callable[[], object]]] = {
            "json": {
                "encode": lambda value=value: json.dumps(
                    value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
                ).encode("utf-8"),
                "decode": lambda data=json_bytes: json.loads(data.decode("utf-8")),
                "round_trip": lambda value=value: json.loads(
                    json.dumps(
                        value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
                    ).encode("utf-8").decode("utf-8")
                ),
            },
            "dcbor": {
                "encode": lambda value=value: dcbor.dumps(value),  # type: ignore[attr-defined]
                "decode": lambda data=dcbor_bytes: dcbor.loads(data),  # type: ignore[attr-defined]
                "round_trip": lambda value=value: dcbor.loads(dcbor.dumps(value)),  # type: ignore[attr-defined]
            },
            "cbor2_default": {
                "encode": lambda value=value: cbor2.dumps(value),
                "decode": lambda data=cbor2_default_bytes: cbor2.loads(data),
                "round_trip": lambda value=value: cbor2.loads(cbor2.dumps(value)),
            },
            "cbor2_canonical": {
                "encode": lambda value=value: cbor2.dumps(value, canonical=True),
                "decode": lambda data=cbor2_canonical_bytes: cbor2.loads(data),
                "round_trip": lambda value=value: cbor2.loads(
                    cbor2.dumps(value, canonical=True)
                ),
            },
            "cborx_default": {
                "encode": lambda value=value: cborx.dumps(value),
                "decode": lambda data=cborx_default_bytes: cborx.loads(data),
                "round_trip": lambda value=value: cborx.loads(cborx.dumps(value)),
            },
            "cborx_canonical": {
                "encode": lambda value=value: cborx.dumps(value, canonical=True),
                "decode": lambda data=cborx_canonical_bytes: cborx.loads(data),
                "round_trip": lambda value=value: cborx.loads(
                    cborx.dumps(value, canonical=True)
                ),
            },
            "orjson_default": {
                "encode": lambda value=value: orjson.dumps(value),
                "decode": lambda data=orjson_default_bytes: orjson.loads(data),
                "round_trip": lambda value=value: orjson.loads(orjson.dumps(value)),
            },
            "orjson_sorted": {
                "encode": lambda value=value: orjson.dumps(
                    value, option=orjson.OPT_SORT_KEYS
                ),
                "decode": lambda data=orjson_sorted_bytes: orjson.loads(data),
                "round_trip": lambda value=value: orjson.loads(
                    orjson.dumps(value, option=orjson.OPT_SORT_KEYS)
                ),
            },
            "msgspec_msgpack": {
                "encode": lambda value=value: msgpack_encoder.encode(value),
                "decode": lambda data=msgspec_msgpack_bytes: msgpack_decoder.decode(data),
                "round_trip": lambda value=value: msgpack_decoder.decode(
                    msgpack_encoder.encode(value)
                ),
            },
            "msgspec_msgpack_deterministic": {
                "encode": lambda value=value: msgpack_deterministic_encoder.encode(value),
                "decode": lambda data=msgspec_deterministic_bytes: msgpack_decoder.decode(data),
                "round_trip": lambda value=value: msgpack_decoder.decode(
                    msgpack_deterministic_encoder.encode(value)
                ),
            },
            "cbrrr_strictdagcbor": {
                "encode": lambda value=value: cbrrr.encode_dag_cbor(value),
                "decode": lambda data=cbrrr_bytes: cbrrr.decode_dag_cbor(data),
                "round_trip": lambda value=value: cbrrr.decode_dag_cbor(
                    cbrrr.encode_dag_cbor(value)
                ),
            },
        }
        measured: dict[str, object] = {}
        implementation_order = IMPLEMENTATIONS
        offset = order_offset % len(implementation_order)
        implementation_order = implementation_order[offset:] + implementation_order[:offset]
        for implementation in implementation_order:
            operations = implementations[implementation]
            measured[implementation] = {}
            for operation, function in operations.items():
                for _ in range(warmup):
                    function()
                start = time.perf_counter_ns()
                for _ in range(rounds):
                    function()
                elapsed_ns = time.perf_counter_ns() - start
                measured[implementation][operation] = elapsed_ns / rounds  # type: ignore[index]
        rows[name] = measured

    return {
        "pid": os.getpid(),
        "started_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "implementation_order": implementation_order,
        "measurements_ns_per_operation": rows,
        "encoded_hashes": encoded_hashes,
        "environment": env,
    }


def summarize(samples: list[float]) -> dict[str, object]:
    median = statistics.median(samples)
    return {
        "samples_ns_per_operation": samples,
        "median_ns_per_operation": median,
        "mad_ns_per_operation": statistics.median(abs(value - median) for value in samples),
        "minimum_ns_per_operation": min(samples),
        "maximum_ns_per_operation": max(samples),
    }


def aggregate(worker_runs: list[dict[str, object]]) -> dict[str, object]:
    fixture_rows: dict[str, object] = {}
    for name in fixtures():
        fixture_rows[name] = {}
        for implementation in IMPLEMENTATIONS:
            fixture_rows[name][implementation] = {}  # type: ignore[index]
            for operation in ("encode", "decode", "round_trip"):
                samples = [
                    run["measurements_ns_per_operation"][name][implementation][operation]
                    for run in worker_runs
                ]
                fixture_rows[name][implementation][operation] = summarize(samples)  # type: ignore[index]
    return fixture_rows


def metadata(warmup: int, rounds: int, repetitions: int) -> dict[str, object]:
    source_path = Path(__file__)
    return {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": {
            "git_commit": git_value("rev-parse", "HEAD"),
            "git_worktree_dirty": source_worktree_dirty(),
            "generator_path": source_path.resolve().relative_to(ROOT).as_posix(),
            "generator_sha256": sha256(source_path.read_bytes()),
            "fixtures_sha256": sha256(Path(__file__).with_name("fixtures.py").read_bytes()),
            "chart_style_path": "benchmarks/chart_style.py",
            "chart_style_sha256": sha256_file(Path(__file__).with_name("chart_style.py")),
            "chart_path": SVG_PATH.relative_to(ROOT).as_posix(),
        },
        "methodology": {
            "timed_operations": ["encode", "decode", "round_trip"],
            "warmup_calls_per_operation_per_process": warmup,
            "timed_calls_per_operation_per_process": rounds,
            "independent_process_repetitions": repetitions,
            "implementation_order": "rotates json/dcbor/cbor2_default/cbor2_canonical/cborx_default/cborx_canonical/orjson_default/orjson_sorted/msgspec_msgpack/msgspec_msgpack_deterministic/cbrrr_strictdagcbor start order across fresh processes",
            "summary": "median of per-process batch means; dispersion is median absolute deviation (MAD)",
            "clock": "time.perf_counter_ns",
            "decode_input": "precomputed encoded bytes for that implementation and fixture",
            "round_trip": "one encode followed by one decode within each timed call",
            "json": "UTF-8, ensure_ascii=False, compact separators, allow_nan=False",
            "cbor_comparators": {
                "dcbor": f"dcbor source extension version {EXPECTED_DCBOR_VERSION}, required release artifact",
                "cbor2_default": f"generic CBOR library cbor2=={PINNED_CBOR2}, dumps() default canonical=False",
                "cbor2_canonical": f"generic CBOR library cbor2=={PINNED_CBOR2}, dumps(canonical=True), length-first key order (legacy RFC 8949 section 4.2.3)",
                "cborx_default": f"generic CBOR library cborx=={PINNED_CBORX}, dumps() default canonical=False; backend recorded",
                "cborx_canonical": f"generic CBOR library cborx=={PINNED_CBORX}, dumps(canonical=True), bytewise encoded-key order per project documentation",
            },
            "other_codecs": {
                "orjson_default": f"JSON library orjson=={PINNED_ORJSON}, dumps() defaults; native extension recorded",
                "orjson_sorted": f"orjson=={PINNED_ORJSON}, dumps(option=orjson.OPT_SORT_KEYS); sorted JSON object keys",
                "msgspec_msgpack": f"msgspec=={PINNED_MSGSPEC}, preconstructed msgspec.msgpack.Encoder()/Decoder() objects; insertion-order maps",
                "msgspec_msgpack_deterministic": f"msgspec=={PINNED_MSGSPEC}, preconstructed Encoder(order='deterministic') and Decoder(); deterministic unordered-container order",
                "cbrrr_strictdagcbor": f"cbrrr=={PINNED_CBRRR}, encode_dag_cbor()/decode_dag_cbor() wrappers for its documented strict DAG-CBOR API, measured as shipped; native extension recorded",
            },
            "map_key_order": "dcbor, cbrrr strict DAG-CBOR, and cborx canonical=True use bytewise ordering; cbor2 canonical=True uses length-first ordering (legacy RFC 8949 section 4.2.3); orjson sorted uses sorted JSON string keys; msgspec deterministic sorts unordered maps",
            "cbor_scope": "cbor2 and cborx are generic CBOR comparators, not dCBOR implementations; cbrrr uses its strict DAG-CBOR API; defaults and named modes are reported separately",
            "api_lifecycle": "msgspec uses preconstructed Encoder/Decoder objects per worker; json, dcbor, cbor2, cborx, orjson, and cbrrr use their documented function wrappers directly",
            "profile_differences": "MessagePack and DAG-CBOR are distinct wire formats; generic cbor2/cborx modes are not dCBOR conformance claims; JSON libraries retain their own formatting and numeric behavior",
            "cbrrr_scope": "This measures cbrrr's documented strict DAG-CBOR API as shipped, not an independent conformance certification; cbrrr==1.1.0 accepts and emits negative zero (absent from these common fixtures) and rejects NaN/Infinity. Profile guarantees differ.",
            "excluded": "a separate validation-only operation is excluded; each decoder keeps its own semantics, including cbrrr's documented strict DAG-CBOR API",
        },
        "fixture_hashes": logical_fixture_hashes(),
    }


def blocked_results(reason: str, warmup: int, rounds: int, repetitions: int) -> dict[str, object]:
    report = metadata(warmup, rounds, repetitions)
    try:
        import dcbor

        blocked_environment: dict[str, object] = {
            "python_version": sys.version,
            "python_implementation": platform.python_implementation(),
            "python_executable": str(Path(sys.executable).resolve()),
            "stdlib_json_version": getattr(json, "__version__", "bundled with Python"),
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": processor_name(),
            **build_provenance(),
            "dcbor_version": dcbor.__version__,
            "dcbor_extension_path": str(Path(dcbor._dcbor.__file__).resolve()),  # type: ignore[attr-defined]
            "dcbor_extension_sha256": sha256(Path(dcbor._dcbor.__file__).read_bytes()),  # type: ignore[attr-defined]
            "dcbor_build": release_build_evidence(Path(dcbor._dcbor.__file__).resolve()),  # type: ignore[attr-defined]
            "cbor2_expected_version": PINNED_CBOR2,
            "cbor2_version": None,
            "cbor2_native_extension_active": None,
            "cborx_expected_version": PINNED_CBORX,
            "cborx_version": None,
            "cborx_native_extension_active": None,
            "orjson_expected_version": PINNED_ORJSON,
            "orjson_version": None,
            "orjson_native_extension_active": None,
            "msgspec_expected_version": PINNED_MSGSPEC,
            "msgspec_version": None,
            "msgspec_native_extension_active": None,
            "cbrrr_expected_version": PINNED_CBRRR,
            "cbrrr_version": None,
            "cbrrr_native_extension_active": None,
        }
    except ImportError:
        blocked_environment = {
            "python_version": sys.version,
            "python_implementation": platform.python_implementation(),
            "python_executable": str(Path(sys.executable).resolve()),
            "stdlib_json_version": getattr(json, "__version__", "bundled with Python"),
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": processor_name(),
            **build_provenance(),
            "cbor2_expected_version": PINNED_CBOR2,
            "cbor2_version": None,
            "cbor2_native_extension_active": None,
            "cborx_expected_version": PINNED_CBORX,
            "cborx_version": None,
            "cborx_native_extension_active": None,
            "orjson_expected_version": PINNED_ORJSON,
            "orjson_version": None,
            "orjson_native_extension_active": None,
            "msgspec_expected_version": PINNED_MSGSPEC,
            "msgspec_version": None,
            "msgspec_native_extension_active": None,
            "cbrrr_expected_version": PINNED_CBRRR,
            "cbrrr_version": None,
            "cbrrr_native_extension_active": None,
        }
    report.update(
        {
            "status": "blocked",
            "blocker": reason,
            "environment": blocked_environment,
            "fixtures": None,
            "raw_process_runs": [],
        }
    )
    return report


def chart(results: dict[str, object]) -> str:
    from comparison_charts import latency_chart

    return latency_chart(results)


def write_report(report: dict[str, object], output_dir: Path) -> None:
    svg = chart(report)
    from comparison_charts import stamp_chart_provenance

    stamp_chart_provenance(report, svg, SVG_PATH.relative_to(ROOT).as_posix())
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "results.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8"
    )
    SVG_PATH.parent.mkdir(parents=True, exist_ok=True)
    SVG_PATH.write_text(svg, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--warmup", type=int, default=DEFAULT_WARMUP)
    parser.add_argument("--rounds", type=int, default=DEFAULT_ROUNDS)
    parser.add_argument("--repetitions", type=int, default=DEFAULT_REPETITIONS)
    parser.add_argument("--order-offset", type=int, default=0, help=argparse.SUPPRESS)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if min(args.warmup, args.rounds, args.repetitions) < 1:
        parser.error("warmup, rounds, and repetitions must be positive")
    if args.worker:
        print(json.dumps(worker(args.warmup, args.rounds, args.order_offset), allow_nan=False))
        return 0

    try:
        import cbor2
        import cborx
        import dcbor
        import orjson
        import msgspec
        import cbrrr
    except ImportError as exc:
        report = blocked_results(
            f"required benchmark package is unavailable: {exc.name}; install benchmarks/requirements.txt and build dcbor",
            args.warmup, args.rounds, args.repetitions,
        )
        write_report(report, args.output_dir)
        print(f"Blocked: {report['blocker']}")
        return 2

    env = environment(dcbor, cbor2, cborx, orjson, msgspec, cbrrr)
    blocker = None
    if cbor2_version(cbor2) != PINNED_CBOR2:
        blocker = f"expected cbor2=={PINNED_CBOR2}, found {cbor2_version(cbor2)}"
    elif importlib.metadata.version("cborx") != PINNED_CBORX:
        blocker = f"expected cborx=={PINNED_CBORX}, found {importlib.metadata.version('cborx')}"
    elif dcbor.__version__ != EXPECTED_DCBOR_VERSION:  # type: ignore[attr-defined]
        blocker = f"expected dcbor=={EXPECTED_DCBOR_VERSION}, found {dcbor.__version__}"  # type: ignore[attr-defined]
    elif env["orjson_version"] != PINNED_ORJSON:
        blocker = f"expected orjson=={PINNED_ORJSON}, found {env['orjson_version']}"
    elif env["msgspec_version"] != PINNED_MSGSPEC:
        blocker = f"expected msgspec=={PINNED_MSGSPEC}, found {env['msgspec_version']}"
    elif env["cbrrr_version"] != PINNED_CBRRR:
        blocker = f"expected cbrrr=={PINNED_CBRRR}, found {env['cbrrr_version']}"
    elif env["dcbor_build"]["profile"] != "release":  # type: ignore[index]
        blocker = "loaded dcbor extension does not match configured release artifact"
    if blocker:
        report = blocked_results(blocker, args.warmup, args.rounds, args.repetitions)
        report["environment"] = env
        write_report(report, args.output_dir)
        print(f"Blocked: {blocker}")
        return 2

    runs: list[dict[str, object]] = []
    worker_command = [
        sys.executable, str(Path(__file__).resolve()), "--worker",
        "--warmup", str(args.warmup), "--rounds", str(args.rounds),
    ]
    worker_env = os.environ.copy()
    worker_env["PYTHONHASHSEED"] = "0"
    worker_env["PYTHONPATH"] = os.pathsep.join(
        (str(PACKAGE_ROOT), str(ROOT / "benchmarks"), worker_env.get("PYTHONPATH", ""))
    )
    for repetition in range(args.repetitions):
        process_command = worker_command + ["--order-offset", str(repetition)]
        try:
            completed = subprocess.run(
                process_command, cwd=ROOT, env=worker_env, check=True,
                capture_output=True, text=True,
            )
            run = json.loads(completed.stdout)
        except subprocess.CalledProcessError as exc:
            report = blocked_results(
                f"worker process {repetition + 1} failed with exit code {exc.returncode}",
                args.warmup, args.rounds, args.repetitions,
            )
            report.update({
                "status": "failed",
                "failure": {
                    "repetition": repetition + 1,
                    "returncode": exc.returncode,
                    "stdout": exc.stdout,
                    "stderr": exc.stderr,
                },
                "raw_process_runs": runs,
            })
            write_report(report, args.output_dir)
            print(f"Failed: {report['blocker']}")
            return 1
        except (json.JSONDecodeError, OSError) as exc:
            report = blocked_results(
                f"worker process {repetition + 1} output could not be read: {type(exc).__name__}: {exc}",
                args.warmup, args.rounds, args.repetitions,
            )
            report.update({"status": "failed", "raw_process_runs": runs})
            write_report(report, args.output_dir)
            print(f"Failed: {report['blocker']}")
            return 1
        run["repetition"] = repetition + 1
        runs.append(run)

    report = metadata(args.warmup, args.rounds, args.repetitions)
    report.update({
        "status": "complete",
        "environment": env,
        "fixture_encoded_hashes": runs[0]["encoded_hashes"],
        "fixtures": aggregate(runs),
        "raw_process_runs": runs,
    })
    write_report(report, args.output_dir)
    print(f"Wrote {args.output_dir / 'results.json'} and {SVG_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
