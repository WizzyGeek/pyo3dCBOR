"""Compare JSON and Python CBOR codecs by serialized bytes for shared fixtures.

Run from the repository root with the pinned comparators installed and dcbor
release-built::

    python -m pip install -r benchmarks/requirements.txt
    CARGO_BUILD_JOBS=2 maturin develop --release --locked
    PYTHONPATH=python python benchmarks/wire_size.py
"""

from __future__ import annotations

import datetime as dt
import hashlib
import importlib.machinery
import importlib.metadata
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Callable

from chart_style import sha256_file
from encoded_size import fixtures, equivalent_value


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = Path(__file__).resolve().parent / "wire_size"
SVG_PATH = ROOT / ".github" / "assets" / "graphs" / "wire-size.svg"
PINNED_CBOR2 = "6.1.5"
PINNED_CBORX = "0.2.5"
PINNED_ORJSON = "3.13.0"
PINNED_MSGSPEC = "0.22.0"
PINNED_CBRRR = "1.1.0"
SERIES = (
    "json",
    "dcbor",
    "cbor2_default",
    "cbor2_canonical",
    "cborx_default",
    "cborx_canonical",
    "orjson_default",
    "orjson_sorted",
    "msgspec_msgpack",
    "msgspec_msgpack_deterministic",
    "cbrrr_strictdagcbor",
)
OUTPUTS = {
    b"benchmarks/encoded_size/results.json",
    b"benchmarks/wire_size/results.json",
    b"benchmarks/latency/results.json",
    b"benchmarks/profile/results.json",
    b"benchmarks/rust_core/results.json",
    b".github/assets/graphs/encoded-size.svg",
    b".github/assets/graphs/wire-size.svg",
    b".github/assets/graphs/latency.svg",
    b".github/assets/graphs/profile.svg",
    b".github/assets/graphs/rust-core.svg",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_value(*args: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=ROOT, stderr=subprocess.DEVNULL, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


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
    if result.returncode:
        return None
    return any(entry and entry[3:] not in OUTPUTS for entry in result.stdout.split(b"\0"))


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


def command_version(*args: str) -> str | None:
    try:
        return subprocess.check_output(
            list(args), cwd=ROOT, stderr=subprocess.STDOUT, text=True, timeout=5
        ).strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


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


def release_build(dcbor: object) -> dict[str, object]:
    extension_path = Path(dcbor._dcbor.__file__).resolve()  # type: ignore[attr-defined]
    extension_hash = sha256(extension_path.read_bytes())
    artifact = ROOT / "target" / "release" / "lib_dcbor.so"
    artifact_hash = sha256(artifact.read_bytes()) if artifact.is_file() else None
    return {
        "profile": "release" if extension_hash == artifact_hash else "unverified",
        "extension_path": str(extension_path),
        "extension_sha256": extension_hash,
        "release_artifact_path": artifact.relative_to(ROOT).as_posix() if artifact_hash else None,
        "release_artifact_sha256": artifact_hash,
    }


def environment(
    dcbor: object,
    cbor2: object,
    cborx: object,
    orjson: object,
    msgspec: object,
    cbrrr: object,
) -> dict[str, object]:
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
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": processor_name(),
        "rustc_version_verbose": command_version("rustc", "--version", "--verbose"),
        "cargo_version": command_version("cargo", "--version"),
        "cargo_lock_sha256": sha256((ROOT / "Cargo.lock").read_bytes()),
        "dcbor_version": dcbor.__version__,  # type: ignore[attr-defined]
        "dcbor_build": release_build(dcbor),
        "cbor2_version": importlib.metadata.version("cbor2"),
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


def codec_functions(
    dcbor: object,
    cbor2: object,
    cborx: object,
    orjson: object,
    msgspec: object,
    cbrrr: object,
) -> tuple[dict[str, Callable[[object], bytes]], dict[str, Callable[[bytes], object]]]:
    """Prepare wrappers once, including msgspec's reusable encoder objects."""
    msgpack_encoder = msgspec.msgpack.Encoder()  # type: ignore[attr-defined]
    msgpack_deterministic_encoder = msgspec.msgpack.Encoder(  # type: ignore[attr-defined]
        order="deterministic"
    )
    msgpack_decoder = msgspec.msgpack.Decoder()  # type: ignore[attr-defined]
    encoders: dict[str, Callable[[object], bytes]] = {
        "json": lambda value: json.dumps(
            value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode("utf-8"),
        "dcbor": lambda value: dcbor.dumps(value),  # type: ignore[attr-defined]
        "cbor2_default": lambda value: cbor2.dumps(value),  # type: ignore[attr-defined]
        "cbor2_canonical": lambda value: cbor2.dumps(value, canonical=True),  # type: ignore[attr-defined]
        "cborx_default": lambda value: cborx.dumps(value),  # type: ignore[attr-defined]
        "cborx_canonical": lambda value: cborx.dumps(value, canonical=True),  # type: ignore[attr-defined]
        "orjson_default": lambda value: orjson.dumps(value),  # type: ignore[attr-defined]
        "orjson_sorted": lambda value: orjson.dumps(  # type: ignore[attr-defined]
            value, option=orjson.OPT_SORT_KEYS  # type: ignore[attr-defined]
        ),
        "msgspec_msgpack": lambda value: msgpack_encoder.encode(value),
        "msgspec_msgpack_deterministic": lambda value: msgpack_deterministic_encoder.encode(value),
        "cbrrr_strictdagcbor": lambda value: cbrrr.encode_dag_cbor(value),  # type: ignore[attr-defined]
    }
    decoders: dict[str, Callable[[bytes], object]] = {
        "json": lambda data: json.loads(data.decode("utf-8")),
        "dcbor": lambda data: dcbor.loads(data),  # type: ignore[attr-defined]
        "cbor2_default": lambda data: cbor2.loads(data),  # type: ignore[attr-defined]
        "cbor2_canonical": lambda data: cbor2.loads(data),  # type: ignore[attr-defined]
        "cborx_default": lambda data: cborx.loads(data),  # type: ignore[attr-defined]
        "cborx_canonical": lambda data: cborx.loads(data),  # type: ignore[attr-defined]
        "orjson_default": lambda data: orjson.loads(data),  # type: ignore[attr-defined]
        "orjson_sorted": lambda data: orjson.loads(data),  # type: ignore[attr-defined]
        "msgspec_msgpack": lambda data: msgpack_decoder.decode(data),
        "msgspec_msgpack_deterministic": lambda data: msgpack_decoder.decode(data),
        "cbrrr_strictdagcbor": lambda data: cbrrr.decode_dag_cbor(data),  # type: ignore[attr-defined]
    }
    return encoders, decoders


def encode_all(value: object, encoders: dict[str, Callable[[object], bytes]]) -> dict[str, bytes]:
    return {series: encoders[series](value) for series in SERIES}


def make_report(
    dcbor: object,
    cbor2: object,
    cborx: object,
    orjson: object,
    msgspec: object,
    cbrrr: object,
) -> dict[str, object]:
    env = environment(dcbor, cbor2, cborx, orjson, msgspec, cbrrr)
    encoders, decoders = codec_functions(dcbor, cbor2, cborx, orjson, msgspec, cbrrr)
    rows: dict[str, object] = {}
    for name, value in fixtures().items():
        encoded = encode_all(value, encoders)
        rows[name] = {}
        for series in SERIES:
            if not equivalent_value(decoders[series](encoded[series]), value):
                raise ValueError(f"{series} round-trip changed fixture {name}")
            rows[name][series] = {
                "status": "complete",
                "bytes": len(encoded[series]),
                "sha256": sha256(encoded[series]),
                "percent_vs_json": round(
                    (len(encoded[series]) - len(encoded["json"])) * 100
                    / len(encoded["json"]),
                    2,
                ),
            }  # type: ignore[index]

    source_path = Path(__file__)
    return {
        "status": "complete",
        "measurement": "serialized payload bytes; excludes process memory, database storage, and indexes",
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
            "json": "UTF-8 compact separators, ensure_ascii=False, allow_nan=False",
            "dcbor": "dCBOR profile codec, release extension required",
            "cbor2_default": f"cbor2=={PINNED_CBOR2}, default dumps() options",
            "cbor2_canonical": f"cbor2=={PINNED_CBOR2}, canonical=True; length-first ordering (RFC 8949 section 4.2.3)",
            "cborx_default": f"cborx=={PINNED_CBORX}, default dumps() options",
            "cborx_canonical": f"cborx=={PINNED_CBORX}, canonical=True; bytewise encoded-key ordering per project documentation",
            "orjson_default": f"orjson=={PINNED_ORJSON}, dumps()/loads() wrappers; compact UTF-8 JSON defaults",
            "orjson_sorted": f"orjson=={PINNED_ORJSON}, dumps(option=orjson.OPT_SORT_KEYS); sorted JSON string keys",
            "msgspec_msgpack": f"msgspec=={PINNED_MSGSPEC}, preconstructed MessagePack Encoder()/Decoder() objects",
            "msgspec_msgpack_deterministic": f"msgspec=={PINNED_MSGSPEC}, preconstructed Encoder(order='deterministic') and Decoder() objects",
            "cbrrr_strictdagcbor": f"cbrrr=={PINNED_CBRRR}, encode_dag_cbor()/decode_dag_cbor() wrappers for its documented strict DAG-CBOR API, measured as shipped",
            "scope": "all fixtures are JSON-compatible; each codec is checked with type-sensitive round trips; generic CBOR modes are not dCBOR conformance claims",
            "percent_vs_json": "(series bytes - compact JSON bytes) / compact JSON bytes * 100; negative means fewer bytes than JSON",
            "api_lifecycle": "msgspec uses preconstructed Encoder/Decoder objects; json, dcbor, cbor2, cborx, orjson, and cbrrr use their function wrappers directly",
            "profile_differences": "MessagePack, DAG-CBOR, JSON, generic CBOR, and dCBOR use distinct formats and are not interchangeable conformance modes",
            "cbrrr_scope": "This measures cbrrr's documented strict DAG-CBOR API as shipped, not an independent conformance certification; cbrrr==1.1.0 accepts and emits negative zero (absent from these common fixtures) and rejects NaN/Infinity. Profile guarantees differ.",
        },
        "environment": env,
        "fixtures": rows,
    }


def chart(report: dict[str, object]) -> str:
    from comparison_charts import wire_size_chart

    return wire_size_chart(report)


def write_report(report: dict[str, object]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    svg = chart(report)
    from comparison_charts import stamp_chart_provenance

    stamp_chart_provenance(report, svg, SVG_PATH.relative_to(ROOT).as_posix())
    (OUTPUT_DIR / "results.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8"
    )
    SVG_PATH.parent.mkdir(parents=True, exist_ok=True)
    SVG_PATH.write_text(svg, encoding="utf-8")


def main() -> int:
    try:
        import cbor2
        import cborx
        import dcbor
        import orjson
        import msgspec
        import cbrrr
    except ImportError as exc:
        reason = f"required benchmark package is unavailable: {exc.name}"
        report = {
            "status": "blocked",
            "blocker": reason,
            "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "source": {
                "git_commit": git_value("rev-parse", "HEAD"),
                "git_worktree_dirty": source_worktree_dirty(),
                "generator_path": Path(__file__).resolve().relative_to(ROOT).as_posix(),
                "generator_sha256": sha256(Path(__file__).read_bytes()),
                "fixtures_sha256": sha256(Path(__file__).with_name("fixtures.py").read_bytes()),
                "chart_style_path": "benchmarks/chart_style.py",
                "chart_style_sha256": sha256_file(Path(__file__).with_name("chart_style.py")),
                "chart_path": SVG_PATH.relative_to(ROOT).as_posix(),
            },
            "expected_versions": {
                "dcbor": "0.1.0",
                "cbor2": PINNED_CBOR2,
                "cborx": PINNED_CBORX,
                "orjson": PINNED_ORJSON,
                "msgspec": PINNED_MSGSPEC,
                "cbrrr": PINNED_CBRRR,
            },
            "environment": {
                "python_version": sys.version,
                "platform": platform.platform(),
                "machine": platform.machine(),
                "rustc_version_verbose": command_version("rustc", "--version", "--verbose"),
                "cargo_version": command_version("cargo", "--version"),
            },
            "fixtures": None,
        }
        report["source"]["chart_sha256"] = sha256(chart(report).encode("utf-8"))
        write_report(report)
        print(f"Blocked: {reason}; install benchmarks/requirements.txt")
        return 2

    env = environment(dcbor, cbor2, cborx, orjson, msgspec, cbrrr)
    blockers = []
    for package, expected, observed in (
        ("dcbor", "0.1.0", dcbor.__version__),
        ("cbor2", PINNED_CBOR2, env["cbor2_version"]),
        ("cborx", PINNED_CBORX, env["cborx_version"]),
        ("orjson", PINNED_ORJSON, env["orjson_version"]),
        ("msgspec", PINNED_MSGSPEC, env["msgspec_version"]),
        ("cbrrr", PINNED_CBRRR, env["cbrrr_version"]),
    ):
        if observed != expected:
            blockers.append(f"expected {package}=={expected}, found {observed}")
    if env["dcbor_build"]["profile"] != "release":
        blockers.append("loaded dcbor extension does not match target/release/lib_dcbor.so")
    if blockers:
        report = {
            "status": "blocked",
            "blocker": "; ".join(blockers),
            "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "source": {
                "git_commit": git_value("rev-parse", "HEAD"),
                "git_worktree_dirty": source_worktree_dirty(),
                "generator_path": Path(__file__).resolve().relative_to(ROOT).as_posix(),
                "generator_sha256": sha256(Path(__file__).read_bytes()),
                "fixtures_sha256": sha256(Path(__file__).with_name("fixtures.py").read_bytes()),
                "chart_style_path": "benchmarks/chart_style.py",
                "chart_style_sha256": sha256_file(Path(__file__).with_name("chart_style.py")),
                "chart_path": SVG_PATH.relative_to(ROOT).as_posix(),
            },
            "environment": env,
            "fixtures": None,
        }
        report["source"]["chart_sha256"] = sha256(chart(report).encode("utf-8"))
        write_report(report)
        print(f"Blocked: {report['blocker']}")
        return 2

    try:
        report = make_report(dcbor, cbor2, cborx, orjson, msgspec, cbrrr)
    except Exception as exc:
        report = {
            "status": "failed",
            "blocker": f"fixture validation failed: {type(exc).__name__}: {exc}",
            "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "source": {
                "git_commit": git_value("rev-parse", "HEAD"),
                "git_worktree_dirty": source_worktree_dirty(),
                "generator_path": Path(__file__).resolve().relative_to(ROOT).as_posix(),
                "generator_sha256": sha256(Path(__file__).read_bytes()),
                "fixtures_sha256": sha256(Path(__file__).with_name("fixtures.py").read_bytes()),
                "chart_style_path": "benchmarks/chart_style.py",
                "chart_style_sha256": sha256_file(Path(__file__).with_name("chart_style.py")),
                "chart_path": SVG_PATH.relative_to(ROOT).as_posix(),
            },
            "environment": env,
            "fixtures": None,
        }
        report["source"]["chart_sha256"] = sha256(chart(report).encode("utf-8"))
        write_report(report)
        print(f"Failed: {report['blocker']}")
        return 1
    write_report(report)
    print(f"Wrote {OUTPUT_DIR / 'results.json'} and {SVG_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
