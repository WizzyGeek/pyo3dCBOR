"""Focused, JSON-shaped values for measuring dCBOR profile work paths."""

from __future__ import annotations

import math
import random
import struct
import unicodedata
from collections.abc import Callable


def _float_vector(
    name: str,
    value: float,
    wire_hex: str,
    decoded_type: str,
    expected: str,
) -> dict[str, object]:
    return {
        "name": name,
        "value": value,
        "input_bits": struct.pack(">d", value).hex(),
        "wire_hex": wire_hex,
        "decoded_type": decoded_type,
        "expected": expected,
    }


def build_workloads(
    encode_key: Callable[[str], bytes],
    cbor_map_factory: Callable[[object], object] | None = None,
) -> dict[str, dict[str, object]]:
    """Build benchmark inputs; key encoding supplies canonical order."""
    cases: dict[str, dict[str, object]] = {}

    def canonicalized(value: object) -> object:
        if isinstance(value, dict):
            return {
                key: canonicalized(value[key])
                for key in sorted(value, key=encode_key)
            }
        if isinstance(value, list):
            return [canonicalized(item) for item in value]
        return value

    for size in (10, 100, 1_000, 10_000):
        keys = [f"field-{index:04d}" for index in range(size)]
        canonical_keys = sorted(keys, key=encode_key)
        values_by_key = {key: index for index, key in enumerate(keys)}
        seed = 0xDCB0 + size
        shuffled_keys = list(canonical_keys)
        random.Random(seed).shuffle(shuffled_keys)
        orders = {
            "sorted": canonical_keys,
            "reverse": list(reversed(canonical_keys)),
            "shuffled": shuffled_keys,
        }
        expected = {key: values_by_key[key] for key in canonical_keys}
        for order, ordered_keys in orders.items():
            case_id = f"map_{size}_{order}"
            cases[case_id] = {
                "family": "map_order",
                "category": "map_order",
                "size": size,
                "order": order,
                "shuffle_seed": seed if order == "shuffled" else None,
                "key_format": "field-{index:04d}",
                "key_width_chars": 10,
                "value_rule": "integer index in 0..size-1",
                "key_order_basis": "dcbor.dumps(key) bytes",
                "map_order_scope": "All keys have equal encoded length; this isolates insertion-order sorting cost and does not compare bytewise with length-first ordering.",
                "work_units": size,
                "normalization": (
                    "Map entries are serialized by encoded-key-byte order, regardless of input insertion order."
                ),
                "expected_type_rule": "Decoded keys remain strings and values remain integers; decoded keys follow canonical byte order.",
                "input": {key: values_by_key[key] for key in ordered_keys},
                "expected": expected,
            }

    integer_boundaries = [
        -(2**64), -(2**63) - 1, -(2**63), -(2**32), -25, -1, 0, 23, 24,
        255, 256, 2**32 - 1, 2**32, 2**63 - 1, 2**64 - 1,
    ] * 32
    cases["integer_width_boundaries"] = {
        "family": "integer",
        "category": "integer",
        "case_type": "explicit_integer_width_boundaries",
        "size": len(integer_boundaries),
        "work_units": len(integer_boundaries),
        "normalization": "Explicit integers span dCBOR negative and unsigned preferred-width boundaries through the supported [-2**64, 2**64-1] range.",
        "expected_type_rule": "Every decoded element remains an int equal to the input; floats are not used in this workload.",
        "input": integer_boundaries,
        "expected": list(integer_boundaries),
    }

    colliding_keys: dict[str, int] = {}
    collision_expected: dict[str, int] = {}
    for index in range(64):
        nfc = f"item-{index:03d}-é"
        nfd = unicodedata.normalize("NFD", nfc)
        colliding_keys[nfd] = index * 2
        colliding_keys[nfc] = index * 2 + 1
        collision_expected[nfc] = index * 2 + 1
    collision_expected = {
        key: collision_expected[key]
        for key in sorted(collision_expected, key=encode_key)
    }
    cases["dict_nfc_key_collisions"] = {
        "family": "map_collision",
        "category": "map_collision",
        "case_type": "dict_nfc_last_entry_wins",
        "size": len(colliding_keys),
        "work_units": len(colliding_keys),
        "normalization": "Each NFD key is followed by its distinct NFC-equivalent Python key; canonical-key collisions retain the later value.",
        "expected_type_rule": "The decoded dict has 64 NFC string keys, each mapped to the later value, in canonical encoded-key order.",
        "input": colliding_keys,
        "expected": collision_expected,
    }

    nested: object = 0
    for level in range(24):
        nested = {"level": level, "items": [nested, level + 1, {"leaf": level + 2}]}
    cases["nested_scalar_tree"] = {
        "family": "nested",
        "category": "nested",
        "case_type": "nested_dict_list_scalar_tree",
        "size": 24,
        "work_units": 192,
        "normalization": "A bounded 24-level dict/list/scalar tree exercises recursive traversal without approaching the depth limit.",
        "expected_type_rule": "The nested decoded value has the same container and scalar types and values as the input.",
        "input": nested,
        "expected": canonicalized(nested),
    }

    if cbor_map_factory is not None:
        snapshot_pairs = [
            (f"snapshot-{index:03d}", {"value": index, "enabled": index % 2 == 0})
            for index in reversed(range(64))
        ]
        snapshot_expected = canonicalized({key: value for key, value in snapshot_pairs})
        cases["cbor_map_snapshot"] = {
            "family": "cbor_map",
            "category": "cbor_map",
            "case_type": "immutable_snapshot_64_entries",
            "size": len(snapshot_pairs),
            "work_units": len(snapshot_pairs),
            "normalization": "A CBORMap snapshot with reversed string-key insertion order serializes from its frozen Rust snapshot.",
            "expected_type_rule": "Decoded entries preserve values and appear in canonical encoded-key order.",
            "input": cbor_map_factory(snapshot_pairs),
            "expected": snapshot_expected,
        }

    fractional_values = [0.1, -0.1, 0.25, -1.5, 3.125, 1.1] * 64
    cases["float_fractional"] = {
        "family": "float",
        "category": "float",
        "case_type": "fractional",
        "size": len(fractional_values),
        "work_units": len(fractional_values),
        "normalization": "Finite non-integral binary64 values retain their exact value and decode as floats; the wire uses the shortest exact float width.",
        "expected_type_rule": "Each decoded element remains a float with the same float.hex() value.",
        "input": fractional_values,
        "expected": fractional_values,
        "_profile_vectors": [
            _float_vector("positive_zero_point_five", 0.5, "f93800", "float", "0x1.0000000000000p-1"),
            _float_vector("negative_zero_point_five", -0.5, "f9b800", "float", "-0x1.0000000000000p-1"),
        ],
    }

    integral_values = [float(value) for value in range(-128, 128)] * 2
    cases["float_integral"] = {
        "family": "float",
        "category": "float",
        "case_type": "integral",
        "size": len(integral_values),
        "work_units": len(integral_values),
        "normalization": "Integral floats in the dCBOR float-reduction interval decode as integers.",
        "expected_type_rule": "Every decoded element is an integer equal to int(input).",
        "input": integral_values,
        "expected": [int(value) for value in integral_values],
    }

    positive_nan = struct.unpack(">d", bytes.fromhex("7ff8000000000001"))[0]
    negative_nan = struct.unpack(">d", bytes.fromhex("fff8000000000042"))[0]
    mixed_values = [
        -0.0, 0.0, 1.0, -42.0, 0.5,
        math.inf, -math.inf, positive_nan, negative_nan,
    ] * 32
    cases["float_mixed_special"] = {
        "family": "float",
        "category": "float",
        "case_type": "mixed_special",
        "size": len(mixed_values),
        "work_units": len(mixed_values),
        "normalization": "Integral finite floats, including signed zero, reduce to integers; infinities remain floats; every NaN uses the canonical half-width NaN and decodes as NaN.",
        "expected_type_rule": "Integers for reduced values (both signed zeros decode as integer 0); floats for infinities and NaNs; exact float.hex() for infinities and math.isnan() for NaNs.",
        "input": mixed_values,
        "expected": [
            int(value) if math.isfinite(value) and value.is_integer() else value
            for value in mixed_values
        ],
        "_profile_vectors": [
            _float_vector("negative_zero", -0.0, "00", "int", "0"),
            _float_vector("positive_zero", 0.0, "00", "int", "0"),
            _float_vector("integral_float", 1.0, "01", "int", "1"),
            _float_vector("positive_infinity", math.inf, "f97c00", "float", "inf"),
            _float_vector("negative_infinity", -math.inf, "f9fc00", "float", "-inf"),
            _float_vector("positive_nan_payload", positive_nan, "f97e00", "float", "isnan"),
            _float_vector("negative_nan_payload", negative_nan, "f97e00", "float", "isnan"),
        ],
    }

    lower_i64 = -float(2**63)
    upper_u64 = float(2**64)
    boundary_values = [
        lower_i64,
        math.nextafter(lower_i64, 0.0),
        math.nextafter(lower_i64, -math.inf),
        math.nextafter(upper_u64, 0.0),
        upper_u64,
        math.nextafter(upper_u64, math.inf),
        -float(2**64),
        math.inf,
        -math.inf,
    ]
    boundary_vectors = [
        _float_vector("negative_i64_boundary", boundary_values[0], "3b7fffffffffffffff", "int", str(-(2**63))),
        _float_vector("just_inside_negative_i64", boundary_values[1], "3b7ffffffffffffbff", "int", str(int(boundary_values[1]))),
        _float_vector("just_below_negative_i64", boundary_values[2], "fbc3e0000000000001", "float", boundary_values[2].hex()),
        _float_vector("just_below_unsigned_u64_boundary", boundary_values[3], "1bfffffffffffff800", "int", str(int(boundary_values[3]))),
        _float_vector("unsigned_u64_boundary", boundary_values[4], "fa5f800000", "float", boundary_values[4].hex()),
        _float_vector("just_above_unsigned_u64_boundary", boundary_values[5], "fb43f0000000000001", "float", boundary_values[5].hex()),
        _float_vector("negative_u64_magnitude_float", boundary_values[6], "fadf800000", "float", boundary_values[6].hex()),
        _float_vector("positive_infinity", boundary_values[7], "f97c00", "float", "inf"),
        _float_vector("negative_infinity", boundary_values[8], "f9fc00", "float", "-inf"),
    ]
    boundary_values = boundary_values * 32
    cases["float_boundaries"] = {
        "family": "float",
        "category": "float",
        "case_type": "boundaries",
        "size": len(boundary_values),
        "work_units": len(boundary_values),
        "normalization": "Finite integral floats in [-2**63, 2**64) reduce to integers; floats immediately outside those endpoints remain floats; infinities remain floats.",
        "expected_type_rule": "Types and values follow the independent scalar CBOR hex vectors in profile_vectors.",
        "input": boundary_values,
        "expected": [
            int(value) if math.isfinite(value) and value.is_integer() and -(2**63) <= value < 2**64 else value
            for value in boundary_values
        ],
        "_profile_vectors": boundary_vectors,
    }

    ascii_text = "Room 17 reports a stable reading of 21.5 C."
    nfc_text = "Málaga café déjà vu Ångström"
    if not unicodedata.is_normalized("NFC", nfc_text):
        raise AssertionError("the precomposed Unicode workload must already be NFC")
    decomposed_text = unicodedata.normalize("NFD", nfc_text)
    expanding_text = "marker-\u0344"
    normalized_expanding_text = unicodedata.normalize("NFC", expanding_text)
    if len(normalized_expanding_text.encode("utf-8")) <= len(expanding_text.encode("utf-8")):
        raise AssertionError("the expanding Unicode workload must grow when normalized")

    for category, text, normalization in (
        ("ascii", ascii_text, "ASCII text is already NFC and is serialized unchanged."),
        ("nfc", nfc_text, "Precomposed text is already NFC and is serialized unchanged."),
        ("decomposed", decomposed_text, "NFD input strings normalize to NFC before serialization and decode as NFC."),
        ("expanding_nfc", expanding_text, "U+0344 expands to U+0308 U+0301 under NFC before serialization."),
    ):
        values = [text] * 256
        expected_text = unicodedata.normalize("NFC", text)
        case_id = f"unicode_{category}"
        cases[case_id] = {
            "family": "unicode",
            "category": "unicode",
            "case_type": category,
            "size": len(values),
            "work_units": sum(len(value) for value in values),
            "normalization": normalization,
            "expected_type_rule": "The decoded list has 256 strings, each equal to unicodedata.normalize('NFC', input_string).",
            "input": values,
            "expected": [expected_text] * len(values),
        }

    return cases
