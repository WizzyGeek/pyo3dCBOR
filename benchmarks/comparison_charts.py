"""Readable SVG comparisons for the optional codec benchmark suite.

The figures summarize paired report data; they never fill in missing values or
select an unlabelled best-performing codec. Full samples and per-mode results
remain in the corresponding JSON reports.
"""

from __future__ import annotations

from hashlib import sha256
from math import ceil, floor, log2, log10
from pathlib import Path
from statistics import median
from typing import Any

from chart_style import COMMON_STYLE, PALETTE, sha256_file, xml_text


MODE_ORDER = (
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

MODE_COLORS = {
    "dcbor": PALETTE["dcbor"],
    "cbor2_default": PALETTE["cbor2_default"],
    "cbor2_canonical": PALETTE["cbor2_canonical"],
    "cborx_default": PALETTE["cborx_default"],
    "cborx_canonical": PALETTE["cborx_canonical"],
    "orjson_default": "#6E5AA6",
    "orjson_sorted": "#9A8CC2",
    "msgspec_msgpack": "#A06D22",
    "msgspec_msgpack_deterministic": "#C39A55",
    "cbrrr_strictdagcbor": "#435967",
}

MODE_LABELS = {
    "dcbor": "dCBOR",
    "cbor2_default": "cbor2 · default",
    "cbor2_canonical": "cbor2 · canonical",
    "cborx_default": "cborx · default",
    "cborx_canonical": "cborx · canonical",
    "orjson_default": "orjson · default",
    "orjson_sorted": "orjson · sorted keys",
    "msgspec_msgpack": "msgspec · MessagePack",
    "msgspec_msgpack_deterministic": "msgspec · deterministic",
    "cbrrr_strictdagcbor": "DAG-CBOR · cbrrr",
}

MODE_GROUPS = (
    ("dCBOR", ("dcbor",), MODE_COLORS["dcbor"]),
    (
        "CBOR profiles · cbor2/cborx",
        ("cbor2_default", "cbor2_canonical", "cborx_default", "cborx_canonical"),
        PALETTE["generic_range"],
    ),
    ("orjson · default/sorted", ("orjson_default", "orjson_sorted"), "#6E5AA6"),
    (
        "msgspec MessagePack · default/deterministic",
        ("msgspec_msgpack", "msgspec_msgpack_deterministic"),
        "#A06D22",
    ),
    ("DAG-CBOR", ("cbrrr_strictdagcbor",), "#435967"),
)

FIXTURE_LABELS = {
    "small_record": "Small record",
    "nested_document": "Nested document",
    "repeated_unicode_strings": "Repeated Unicode strings",
    "numeric_array": "Numeric array",
    "compact_scientific_notation": "Compact scientific notation",
    "large_collection": "Large collection",
    "telemetry_batch": "Telemetry batch",
    "ascii_article": "ASCII article",
}


def _fixture_label(name: str) -> str:
    return FIXTURE_LABELS.get(name, name.replace("_", " ").capitalize())


def _complete(report: dict[str, Any], title: str) -> str | None:
    if report.get("status") == "complete" and isinstance(report.get("fixtures"), dict):
        return None
    detail = report.get("blocker") or report.get("reason") or report.get("status") or "no complete report"
    return _unavailable(title, str(detail))


def _unavailable(title: str, reason: str) -> str:
    safe_title = xml_text(title)
    safe_reason = xml_text(reason)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="900" height="220" viewBox="0 0 900 220" role="img" aria-labelledby="title desc">
  <title id="title">{safe_title} unavailable</title>
  <desc id="desc">No comparison is inferred. The report records: {safe_reason}</desc>
  <style>{COMMON_STYLE}</style>
  <rect width="900" height="220" fill="{PALETTE["paper"]}" />
  <text x="32" y="54" class="title">{safe_title} unavailable</text>
  <text x="32" y="88" class="subtitle">No values are inferred: {safe_reason}</text>
</svg>
'''


def _power_range(values: list[float], *, base: float = 2.0) -> tuple[int, int]:
    positive = [value for value in values if value > 0]
    if not positive:
        return -3, 3
    if base == 2.0:
        low = min(-3, floor(log2(min(positive))))
        high = max(3, ceil(log2(max(positive))))
    else:
        low = floor(log10(min(positive)))
        high = ceil(log10(max(positive)))
        if low == high:
            high = low + 1
    return low, high


def _power_ticks(low: int, high: int) -> list[int]:
    span = high - low
    step = 1 if span <= 5 else 2 if span <= 16 else 3
    ticks = list(range(low, high + 1, step))
    if 0 not in ticks and low <= 0 <= high:
        ticks.append(0)
        ticks.sort()
    if high not in ticks:
        ticks.append(high)
    return ticks


def _format_ratio_tick(ratio: float) -> str:
    return f"{ratio:.2g}×"


def stamp_chart_provenance(report: dict[str, Any], svg: str, chart_path: str | Path) -> None:
    """Add chart and renderer/helper hashes to a benchmark report in place."""
    source = report.setdefault("source", {})
    if not isinstance(source, dict):
        raise TypeError("report['source'] must be an object")
    path = Path(chart_path)
    repo_root = Path(__file__).resolve().parents[1]
    if path.is_absolute():
        try:
            recorded_path = path.resolve().relative_to(repo_root).as_posix()
        except ValueError:
            recorded_path = path.as_posix()
    else:
        recorded_path = path.as_posix()
    source.update(
        {
            "chart_path": recorded_path,
            "chart_sha256": sha256(svg.encode("utf-8")).hexdigest(),
            "chart_generator_path": "benchmarks/comparison_charts.py",
            "chart_generator_sha256": sha256_file(Path(__file__).resolve()),
            "chart_style_path": "benchmarks/chart_style.py",
            "chart_style_sha256": sha256_file(Path(__file__).with_name("chart_style.py")),
        }
    )


def wire_size_chart(report: dict[str, Any]) -> str:
    """Plot JSON-relative payload sizes with explicit multi-mode family ranges."""
    unavailable = _complete(report, "Wire size comparison")
    if unavailable:
        return unavailable
    fixtures = report["fixtures"]
    assert isinstance(fixtures, dict)
    values_for_axis: list[float] = []
    for details in fixtures.values():
        if not isinstance(details, dict):
            continue
        baseline = details.get("json", {}).get("bytes")
        if not isinstance(baseline, (int, float)) or baseline <= 0:
            continue
        for _, modes, _ in MODE_GROUPS:
            for mode in modes:
                item = details.get(mode)
                if isinstance(item, dict) and item.get("status", "complete") == "complete":
                    byte_count = item.get("bytes")
                    if isinstance(byte_count, (int, float)) and byte_count >= 0:
                        values_for_axis.append(byte_count * 100 / baseline)
    if not values_for_axis:
        return _unavailable("Wire size comparison", "No successful codec values are present")

    low = min(50, int(min(values_for_axis) // 25) * 25)
    high = max(150, int((max(values_for_axis) + 24) // 25) * 25)
    if high <= low:
        high = low + 100
    width, height = 1320, max(686, 270 + len(fixtures) * 58 + 64)
    plot_x, plot_width = 296, 390
    row_top, row_pitch = 242, 58
    row_end = row_top + len(fixtures) * row_pitch

    def x_for_percent(percent: float) -> float:
        return plot_x + (percent - low) / (high - low) * plot_width

    column_x = {"json": 756, "dcbor": 847, "cbor": 938, "orjson": 1031, "msgspec": 1124, "dag": 1230}
    header = []
    for tick in range(low, high + 1, 25):
        x = x_for_percent(tick)
        baseline = tick == 100
        header.append(
            f'<line x1="{x:.2f}" y1="{row_top - 10}" x2="{x:.2f}" y2="{row_end - 5}" '
            f'stroke="{PALETTE["ink"] if baseline else PALETTE["line"]}" '
            f'stroke-width="{2 if baseline else 1}" stroke-dasharray="{"0" if baseline else "2 5"}" />'
            f'<text x="{x:.2f}" y="{row_end + 19}" text-anchor="middle" class="axis">{tick}%</text>'
        )
    marks: list[str] = []
    lane_offsets = (-20, -10, 0, 10, 20)
    for index, (fixture_name, details) in enumerate(fixtures.items()):
        if not isinstance(details, dict):
            continue
        baseline = details.get("json", {}).get("bytes")
        if not isinstance(baseline, (int, float)) or baseline <= 0:
            continue
        center = row_top + index * row_pitch + row_pitch / 2
        fixture_title = _fixture_label(fixture_name)
        marks.append(
            f'<line x1="48" y1="{center + 29}" x2="1284" y2="{center + 29}" class="rule" />'
            f'<text x="48" y="{center + 5}" class="row-label">{xml_text(fixture_title)}</text>'
        )
        json_item = details.get("json", {})
        json_bytes = json_item.get("bytes") if isinstance(json_item, dict) else None
        marks.append(
            f'<text x="{column_x["json"]}" y="{center + 5}" text-anchor="middle" class="bytes">{_format_bytes(json_bytes)}</text>'
        )
        family_summaries: dict[str, str] = {}
        for group_index, (group_label, modes, color) in enumerate(MODE_GROUPS):
            successful: list[tuple[str, int]] = []
            mode_states: list[str] = []
            for mode in modes:
                item = details.get(mode)
                if isinstance(item, dict) and item.get("status", "complete") == "complete" and isinstance(item.get("bytes"), (int, float)):
                    successful.append((mode, int(item["bytes"])))
                else:
                    status = item.get("status", "not measured") if isinstance(item, dict) else "not measured"
                    reason = item.get("reason") if isinstance(item, dict) else None
                    mode_states.append(f"{mode}: {status}" + (f" ({reason})" if reason else ""))
            if successful:
                sizes = [size for _, size in successful]
                minimum, maximum = min(sizes), max(sizes)
                ratio_low, ratio_high = minimum * 100 / baseline, maximum * 100 / baseline
                y = center + lane_offsets[group_index]
                family_tooltip = xml_text(
                    f"{fixture_title}: " + "; ".join(f"{mode} {size:,} B" for mode, size in successful)
                    + ("; " + "; ".join(mode_states) if mode_states else "")
                )
                if ratio_low == ratio_high:
                    mark = f'<circle cx="{x_for_percent(ratio_low):.2f}" cy="{y:.2f}" r="5" fill="{color}"><title>{family_tooltip}</title></circle>'
                else:
                    mark = (
                        f'<line x1="{x_for_percent(ratio_low):.2f}" y1="{y:.2f}" x2="{x_for_percent(ratio_high):.2f}" y2="{y:.2f}" '
                        f'stroke="{color}" stroke-width="6" stroke-linecap="round"><title>{family_tooltip}</title></line>'
                        f'<line x1="{x_for_percent(ratio_low):.2f}" y1="{y - 6:.2f}" x2="{x_for_percent(ratio_low):.2f}" y2="{y + 6:.2f}" stroke="{color}" stroke-width="2" />'
                        f'<line x1="{x_for_percent(ratio_high):.2f}" y1="{y - 6:.2f}" x2="{x_for_percent(ratio_high):.2f}" y2="{y + 6:.2f}" stroke="{color}" stroke-width="2" />'
                    )
                marks.append(mark)
                family_summaries[group_label] = _format_range(minimum, maximum)
            else:
                family_summaries[group_label] = "—"
        # Numeric columns match the legend order: dCBOR, CBOR, orjson, msgspec, DAG-CBOR.
        for key, group_label in (
            ("dcbor", "dCBOR"),
            ("cbor", "CBOR profiles · cbor2/cborx"),
            ("orjson", "orjson · default/sorted"),
            ("msgspec", "msgspec MessagePack · default/deterministic"),
            ("dag", "DAG-CBOR"),
        ):
            marks.append(
                f'<text x="{column_x[key]}" y="{center + 5}" text-anchor="middle" class="bytes">{xml_text(family_summaries.get(group_label, "—"))}</text>'
            )
    tick_labels = ''.join(header)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
  <title id="title">Wire size across codec families</title>
  <desc id="desc">Compact JSON is the 100 percent baseline. dCBOR and strict DAG-CBOR use exact points; the CBOR, orjson, and msgspec families use explicit min–max ranges across their named modes. Family lanes are vertically offset to keep overlapping measurements readable. Table columns show bytes, while plot tooltips retain each individual mode value and status.</desc>
  <style>{COMMON_STYLE}
    .hero {{ font-size: 30px; font-weight: 760; letter-spacing: -0.55px; }}
    .dek {{ font-size: 15px; fill: {PALETTE["muted"]}; }}
    .row-label {{ font-size: 15px; font-weight: 620; }}
    .bytes {{ font-size: 13px; font-variant-numeric: tabular-nums; }}
  </style>
  <rect width="{width}" height="{height}" fill="{PALETTE["paper"]}" />
  <text x="48" y="46" class="hero">Wire size across codec families</text>
  <text x="48" y="73" class="dek">Compact JSON = 100% · points and family ranges compare bytes per fixture</text>
  <circle cx="56" cy="106" r="6" fill="{MODE_COLORS["dcbor"]}" /><text x="70" y="111" class="legend">dCBOR</text>
  <line x1="159" y1="106" x2="190" y2="106" stroke="{PALETTE["generic_range"]}" stroke-width="7" stroke-linecap="round" /><text x="201" y="111" class="legend">CBOR profiles · cbor2/cborx default + canonical</text>
  <line x1="590" y1="106" x2="620" y2="106" stroke="#6E5AA6" stroke-width="7" stroke-linecap="round" /><text x="631" y="111" class="legend">orjson default/sorted</text>
  <line x1="826" y1="106" x2="856" y2="106" stroke="#A06D22" stroke-width="7" stroke-linecap="round" /><text x="867" y="111" class="legend">msgspec MessagePack default/deterministic</text>
  <circle cx="56" cy="133" r="6" fill="#435967" /><text x="70" y="138" class="legend">Strict DAG-CBOR</text>
  <text x="48" y="208" class="column-head">Fixture</text>
  <text x="{column_x["json"]}" y="208" text-anchor="middle" class="column-head">JSON B</text>
  <text x="{column_x["dcbor"]}" y="208" text-anchor="middle" class="column-head">dCBOR B</text>
  <text x="{column_x["cbor"]}" y="208" text-anchor="middle" class="column-head">CBOR B</text>
  <text x="{column_x["orjson"]}" y="208" text-anchor="middle" class="column-head">orjson B</text>
  <text x="{column_x["msgspec"]}" y="208" text-anchor="middle" class="column-head">msgspec B</text>
  <text x="{column_x["dag"]}" y="208" text-anchor="middle" class="column-head">DAG B</text>
  {tick_labels}
  {''.join(marks)}
  <text x="48" y="{height - 20}" class="caption">Ranges combine only named modes within each family. Unsupported or missing measurements remain visible as dashes and in report status; raw JSON keeps every mode and hash.</text>
</svg>
'''


def _format_bytes(value: Any) -> str:
    return f"{int(value):,}" if isinstance(value, (int, float)) else "—"


def _format_range(minimum: int, maximum: int) -> str:
    if minimum == maximum:
        return f"{minimum:,}"
    return f"{minimum:,}–{maximum:,}"


def latency_chart(report: dict[str, Any]) -> str:
    """Show per-mode latency ratios by operation, without best-of grouping."""
    unavailable = _complete(report, "Latency comparison")
    if unavailable:
        return unavailable
    fixtures = report["fixtures"]
    assert isinstance(fixtures, dict)
    operations = ("encode", "decode", "round_trip")
    operation_labels = {"encode": "Encode", "decode": "Decode", "round_trip": "Round trip"}
    ratios_by_operation: dict[str, dict[str, list[float]]] = {op: {} for op in operations}
    all_ratios: list[float] = []
    for operation in operations:
        for mode in MODE_ORDER:
            mode_ratios: list[float] = []
            for details in fixtures.values():
                if not isinstance(details, dict):
                    continue
                baseline = details.get("json", {}).get(operation, {}).get("median_ns_per_operation")
                value = details.get(mode, {}).get(operation, {}).get("median_ns_per_operation")
                if isinstance(baseline, (int, float)) and baseline > 0 and isinstance(value, (int, float)) and value > 0:
                    mode_ratios.append(value / baseline)
            if mode_ratios:
                ratios_by_operation[operation][mode] = mode_ratios
                all_ratios.extend(mode_ratios)
    if not all_ratios:
        return _unavailable("Latency comparison", "No paired JSON and codec timings are present")

    min_power, max_power = _power_range(all_ratios)
    width = 1280
    plot_x, plot_width = 366, 424
    summary_x = 818
    row_top, row_pitch = 70, 22
    mode_count = max(len(values) for values in ratios_by_operation.values())
    panel_height = row_top + mode_count * row_pitch + 14
    panel_gap = 17
    panel_y = tuple(150 + index * (panel_height + panel_gap) for index in range(len(operations)))
    height = panel_y[-1] + panel_height + 43

    def x_for_ratio(ratio: float) -> float:
        return plot_x + (log2(ratio) - min_power) / (max_power - min_power) * plot_width

    powers = _power_ticks(min_power, max_power)
    panels: list[str] = []
    for operation, panel_top in zip(operations, panel_y):
        panel: list[str] = [
            f'<text x="48" y="{panel_top + 25}" class="operation">{operation_labels[operation]}</text>',
            f'<text x="{summary_x}" y="{panel_top + 25}" class="column-head">Median ratio · fixture min–max</text>',
            f'<line x1="48" y1="{panel_top + panel_height}" x2="1232" y2="{panel_top + panel_height}" class="rule" />',
        ]
        for power in powers:
            ratio = 2 ** power
            x = x_for_ratio(ratio)
            baseline = power == 0
            panel.append(
                f'<line x1="{x:.2f}" y1="{panel_top + 40}" x2="{x:.2f}" y2="{panel_top + panel_height - 5}" '
                f'stroke="{PALETTE["ink"] if baseline else PALETTE["line"]}" stroke-width="{2 if baseline else 1}" '
                f'stroke-dasharray="{"0" if baseline else "2 5"}" />'
                f'<text x="{x:.2f}" y="{panel_top + 55}" text-anchor="middle" class="axis">{_format_ratio_tick(ratio)}</text>'
            )
        modes = ratios_by_operation[operation]
        for row_index, mode in enumerate(MODE_ORDER):
            ratios = modes.get(mode)
            if not ratios:
                continue
            center = panel_top + row_top + row_index * row_pitch
            low_ratio, high_ratio = min(ratios), max(ratios)
            median_ratio = median(ratios)
            color = MODE_COLORS[mode]
            mode_label = xml_text(MODE_LABELS.get(mode, mode))
            tooltip = xml_text(
                f"{mode}, {operation}: median paired ratio {median_ratio:.4f}×; fixture range {low_ratio:.4f}–{high_ratio:.4f}×; "
                f"n={len(ratios)} fixtures; each ratio compares this mode's reported median with the same fixture's JSON median"
            )
            panel.extend(
                [
                    f'<text x="48" y="{center + 5}" class="mode-label" fill="{color}">{mode_label}</text>',
                    f'<line x1="{x_for_ratio(low_ratio):.2f}" y1="{center}" x2="{x_for_ratio(high_ratio):.2f}" y2="{center}" stroke="{color}" stroke-width="3" stroke-linecap="round"><title>{tooltip}</title></line>',
                    f'<line x1="{x_for_ratio(low_ratio):.2f}" y1="{center - 5}" x2="{x_for_ratio(low_ratio):.2f}" y2="{center + 5}" stroke="{color}" stroke-width="1.5" />',
                    f'<line x1="{x_for_ratio(high_ratio):.2f}" y1="{center - 5}" x2="{x_for_ratio(high_ratio):.2f}" y2="{center + 5}" stroke="{color}" stroke-width="1.5" />',
                    f'<circle cx="{x_for_ratio(median_ratio):.2f}" cy="{center}" r="5.5" fill="{color}"><title>{tooltip}</title></circle>',
                    f'<text x="{summary_x}" y="{center + 5}" class="ratio-value">{median_ratio:.2f}× <tspan class="muted">({low_ratio:.2f}–{high_ratio:.2f}×)</tspan></text>',
                ]
            )
        panels.append("".join(panel))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
  <title id="title">Latency ratios by codec and operation</title>
  <desc id="desc">Each mode is shown separately. A point is the median of per-fixture ratios of that mode's reported median to the same fixture's Python JSON median; whiskers span the minimum and maximum ratios across fixtures, not timing uncertainty. The vertical 1× guide is JSON. No overall winner is inferred.</desc>
  <style>{COMMON_STYLE}
    .hero {{ font-size: 30px; font-weight: 760; letter-spacing: -0.55px; }}
    .dek {{ font-size: 15px; fill: {PALETTE["muted"]}; }}
    .operation {{ font-size: 20px; font-weight: 720; }}
    .mode-label {{ font-size: 14px; font-weight: 610; }}
    .ratio-value {{ font-size: 14px; font-weight: 620; font-variant-numeric: tabular-nums; }}
  </style>
  <rect width="{width}" height="{height}" fill="{PALETTE["paper"]}" />
  <text x="48" y="45" class="hero">Latency ratios by codec and operation</text>
  <text x="48" y="73" class="dek">Each named mode vs same-fixture Python JSON · point is median fixture ratio · whisker spans fixture min–max</text>
  <line x1="54" y1="105" x2="100" y2="105" stroke="{PALETTE["generic_range"]}" stroke-width="3" />
  <circle cx="77" cy="105" r="5.5" fill="{PALETTE["dcbor"]}" />
  <text x="113" y="110" class="legend">Per-mode median and workload range; below 1× is lower latency</text>
  {''.join(panels)}
  <text x="48" y="{height - 15}" class="caption">Ratios summarize fixtures, not process samples. MAD and all per-fixture medians/samples remain in the JSON report.</text>
</svg>
'''


def profile_chart(report: dict[str, Any]) -> str:
    """Plot map encode/decode scaling plus direct float and Unicode profiles."""
    if report.get("status") != "complete" or not isinstance(report.get("cases"), dict):
        detail = report.get("blocker") or report.get("reason") or report.get("status") or "no complete profile"
        return _unavailable("dCBOR workload profile", str(detail))
    cases = report["cases"]
    assert isinstance(cases, dict)
    order_colors = {"sorted": PALETTE["dcbor"], "reverse": PALETTE["json"], "shuffled": PALETTE["coral"]}
    order_labels = {"sorted": "Sorted", "reverse": "Reverse", "shuffled": "Shuffled"}
    map_rows: dict[str, dict[str, list[tuple[int, float, str]]]] = {
        operation: {order: [] for order in order_colors}
        for operation in ("encode", "decode")
    }
    direct_cases: dict[str, list[tuple[str, dict[str, Any]]]] = {"float": [], "unicode": []}
    for case_id, case in cases.items():
        if not isinstance(case, dict):
            continue
        category = case.get("category")
        if category == "map_order" or case.get("family") == "map_order":
            order = str(case.get("order", ""))
            size = case.get("size")
            operations = case.get("operations", {})
            if order in order_colors and isinstance(size, (int, float)) and size > 0 and isinstance(operations, dict):
                for operation in map_rows:
                    metric = operations.get(operation, {})
                    median_ns = metric.get("median_ns_per_operation") if isinstance(metric, dict) else None
                    if isinstance(median_ns, (int, float)) and median_ns > 0:
                        map_rows[operation][order].append((int(size), float(median_ns), str(case_id)))
        elif category in direct_cases:
            direct_cases[category].append((str(case_id), case))
    all_map_rows = [item for rows in map_rows.values() for values in rows.values() for item in values]
    direct_times: list[float] = []
    for rows in direct_cases.values():
        for _, case in rows:
            ops = case.get("operations", {})
            if not isinstance(ops, dict):
                continue
            for operation in ("encode", "decode"):
                metric = ops.get(operation, {})
                value = metric.get("median_ns_per_operation") if isinstance(metric, dict) else None
                if isinstance(value, (int, float)) and value > 0:
                    direct_times.append(float(value) / 1000)
    if not all_map_rows and not direct_times:
        return _unavailable("dCBOR workload profile", "No map, float, or Unicode measurements are present")

    width, height = 1300, 760
    map_plot_y, map_plot_h = 164, 218
    map_panels = {
        "encode": {"title": "Map encode scaling", "plot_x": 96, "plot_w": 490},
        "decode": {"title": "Map decode scaling", "plot_x": 756, "plot_w": 490},
    }
    sizes = sorted({size for size, _, _ in all_map_rows})
    map_min_x = log10(min(sizes)) if sizes else 0
    map_max_x = log10(max(sizes)) if sizes else 1
    if map_max_x == map_min_x:
        map_max_x = map_min_x + 1
    map_times_us = [ns / 1000 for _, ns, _ in all_map_rows]
    map_min_y_pow, map_max_y_pow = _power_range(map_times_us, base=10.0)

    def map_y(us: float) -> float:
        return map_plot_y + map_plot_h - (log10(us) - map_min_y_pow) / (map_max_y_pow - map_min_y_pow) * map_plot_h

    map_tick_sizes = sizes if len(sizes) <= 6 else [sizes[0], *[size for size in sizes[1:-1] if round(log10(size)) == log10(size)], sizes[-1]]
    map_grid: list[str] = []
    map_svg: list[str] = []
    for operation, panel in map_panels.items():
        plot_x = panel["plot_x"]
        plot_w = panel["plot_w"]

        def map_x(size: int, *, plot_x: int = plot_x, plot_w: int = plot_w) -> float:
            return plot_x + (log10(size) - map_min_x) / (map_max_x - map_min_x) * plot_w

        for size in map_tick_sizes:
            x = map_x(size)
            map_grid.append(
                f'<line x1="{x:.2f}" y1="{map_plot_y}" x2="{x:.2f}" y2="{map_plot_y + map_plot_h}" stroke="{PALETTE["line"]}" stroke-dasharray="2 5" />'
                f'<text x="{x:.2f}" y="{map_plot_y + map_plot_h + 20}" text-anchor="middle" class="axis">{size:,}</text>'
            )
        for power in _power_ticks(map_min_y_pow, map_max_y_pow):
            us = 10 ** power
            y = map_y(us)
            label = f"{us:g} µs" if us < 1000 else f"{us / 1000:g} ms"
            map_grid.append(
                f'<line x1="{plot_x}" y1="{y:.2f}" x2="{plot_x + plot_w}" y2="{y:.2f}" stroke="{PALETTE["line"]}" stroke-dasharray="2 5" />'
                f'<text x="{plot_x - 12}" y="{y + 4:.2f}" text-anchor="end" class="axis">{xml_text(label)}</text>'
            )
        for order, color in order_colors.items():
            rows = sorted(map_rows[operation][order])
            if not rows:
                continue
            points = " ".join(f"{map_x(size):.2f},{map_y(ns / 1000):.2f}" for size, ns, _ in rows)
            map_svg.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="3" stroke-linejoin="round" />')
            for size, ns, case_id in rows:
                metric = cases[case_id].get("operations", {}).get(operation, {})
                mad = metric.get("mad_ns_per_operation") if isinstance(metric, dict) else None
                tooltip = xml_text(
                    f"{order_labels[order]} source insertion order, {size:,}-entry map: "
                    f"{operation} median {ns:,.0f} ns/op"
                    + (f", MAD {mad:,.0f} ns" if isinstance(mad, (int, float)) else "")
                )
                x, y = map_x(size), map_y(ns / 1000)
                if order == "reverse":
                    marker = f'<rect x="{x - 4.5:.2f}" y="{y - 4.5:.2f}" width="9" height="9" fill="{color}"><title>{tooltip}</title></rect>'
                elif order == "shuffled":
                    marker = f'<polygon points="{x:.2f},{y - 6:.2f} {x + 6:.2f},{y + 5:.2f} {x - 6:.2f},{y + 5:.2f}" fill="{color}"><title>{tooltip}</title></polygon>'
                else:
                    marker = f'<circle cx="{x:.2f}" cy="{y:.2f}" r="5" fill="{color}"><title>{tooltip}</title></circle>'
                map_svg.append(marker)

    direct_min_pow, direct_max_pow = _power_range(direct_times, base=10.0) if direct_times else (-1, 1)
    lower_plot_w = 275
    lower_top = 501
    row_pitch = 34
    direct_axis: list[str] = []

    def format_us(value: float) -> str:
        return f"{value:g}"

    panels = []
    panel_specs = (("float", "Float cases", 48), ("unicode", "Unicode normalization", 670))
    for category, title, left in panel_specs:
        entries = direct_cases[category]
        entries.sort(key=lambda item: _profile_case_order(category, item[0]))
        top = lower_top
        plot_x = left + 154
        plot_y = top + 38
        plot_bottom = plot_y + len(entries) * row_pitch
        text_x = left + 452
        pieces = [
            f'<text x="{left}" y="{top + 19}" class="panel-title">{title}</text>',
            f'<text x="{text_x}" y="{top + 19}" text-anchor="middle" class="column-head">Wire B</text>',
        ]
        for power in _power_ticks(direct_min_pow, direct_max_pow):
            us = 10 ** power
            x = plot_x + (power - direct_min_pow) / (direct_max_pow - direct_min_pow) * lower_plot_w
            pieces.append(
                f'<line x1="{x:.2f}" y1="{plot_y - 8}" x2="{x:.2f}" y2="{plot_bottom}" stroke="{PALETTE["line"]}" stroke-dasharray="2 5" />'
                f'<text x="{x:.2f}" y="{plot_bottom + 18}" text-anchor="middle" class="axis">{format_us(us)}</text>'
            )
        for index, (case_id, case) in enumerate(entries):
            center = plot_y + index * row_pitch + row_pitch / 2
            label = _profile_case_label(category, case_id)
            operations = case.get("operations", {})
            encode = operations.get("encode", {}) if isinstance(operations, dict) else {}
            decode = operations.get("decode", {}) if isinstance(operations, dict) else {}
            encode_ns = encode.get("median_ns_per_operation") if isinstance(encode, dict) else None
            decode_ns = decode.get("median_ns_per_operation") if isinstance(decode, dict) else None
            bytes_value = case.get("wire_bytes")
            pieces.append(f'<text x="{left}" y="{center + 5}" class="case-label">{xml_text(label)}</text>')
            if isinstance(encode_ns, (int, float)) and encode_ns > 0:
                x = plot_x + (log10(encode_ns / 1000) - direct_min_pow) / (direct_max_pow - direct_min_pow) * lower_plot_w
                tip = xml_text(f"{case_id}: encode median {encode_ns:,.0f} ns/op; wire {bytes_value} B")
                pieces.append(f'<circle cx="{x:.2f}" cy="{center - 4:.2f}" r="5" fill="{PALETTE["dcbor"]}"><title>{tip}</title></circle>')
            if isinstance(decode_ns, (int, float)) and decode_ns > 0:
                x = plot_x + (log10(decode_ns / 1000) - direct_min_pow) / (direct_max_pow - direct_min_pow) * lower_plot_w
                tip = xml_text(f"{case_id}: decode median {decode_ns:,.0f} ns/op; wire {bytes_value} B")
                pieces.append(f'<polygon points="{x:.2f},{center - 1:.2f} {x + 5:.2f},{center + 4:.2f} {x:.2f},{center + 9:.2f} {x - 5:.2f},{center + 4:.2f}" fill="{PALETTE["coral"]}"><title>{tip}</title></polygon>')
            pieces.append(f'<text x="{text_x}" y="{center + 5}" text-anchor="middle" class="case-value">{_format_bytes(bytes_value)}</text>')
            pieces.append(f'<line x1="{left}" y1="{center + 15}" x2="{left + 566}" y2="{center + 15}" class="rule" />')
        pieces.append(f'<text x="{plot_x + lower_plot_w / 2}" y="{plot_bottom + 37}" text-anchor="middle" class="axis">Median time · µs, log</text>')
        panels.append("".join(pieces))

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
  <title id="title">dCBOR profile: map scale, floats, and Unicode</title>
  <desc id="desc">The top side-by-side map panels plot encode and decode medians against entry count using the same logarithmic entry-count and time limits. Each distinguishes sorted, reverse, and shuffled source insertion order; these orders produce identical canonical wire, so decode differences by order are measurement variation, not evidence of an order-dependent decoder. Lower float and Unicode panels show encode and decode medians on a shared logarithmic microsecond scale, with exact encoded wire bytes. Workloads have different semantics and payload sizes; ratios between them are not implied. Tooltips and the profile JSON retain exact medians and MAD.</desc>
  <style>{COMMON_STYLE}
    .hero {{ font-size: 30px; font-weight: 760; letter-spacing: -0.55px; }}
    .dek {{ font-size: 15px; fill: {PALETTE["muted"]}; }}
    .panel-title {{ font-size: 19px; font-weight: 720; }}
    .case-label {{ font-size: 14px; font-weight: 590; }}
    .case-value {{ font-size: 14px; font-variant-numeric: tabular-nums; }}
  </style>
  <rect width="{width}" height="{height}" fill="{PALETTE["paper"]}" />
  <text x="48" y="45" class="hero">dCBOR profile: map scale, floats, and Unicode</text>
  <text x="48" y="72" class="dek">Map operations share log-scaled entry-count and time limits · lower panels show each case directly, not as unequal-size ratios</text>
  <text x="48" y="126" class="legend">Source insertion order:</text>
  <circle cx="213" cy="121" r="5" fill="{order_colors["sorted"]}" /><text x="225" y="126" class="legend">Sorted</text>
  <rect x="326" y="116" width="10" height="10" fill="{order_colors["reverse"]}" /><text x="344" y="126" class="legend">Reverse</text>
  <polygon points="458,115 464,126 452,126" fill="{order_colors["shuffled"]}" /><text x="472" y="126" class="legend">Shuffled</text>
  <text x="48" y="151" class="panel-title">Map encode scaling</text>
  <text x="708" y="151" class="panel-title">Map decode scaling</text>
  {''.join(map_grid)}
  {''.join(map_svg)}
  <text x="341" y="{map_plot_y + map_plot_h + 43}" text-anchor="middle" class="axis">Map entries · log scale</text>
  <text x="1001" y="{map_plot_y + map_plot_h + 43}" text-anchor="middle" class="axis">Map entries · log scale</text>
  <text transform="translate(23 {map_plot_y + map_plot_h / 2}) rotate(-90)" text-anchor="middle" class="axis">Median · µs, log scale</text>
  <text transform="translate(683 {map_plot_y + map_plot_h / 2}) rotate(-90)" text-anchor="middle" class="axis">Median · µs, log scale</text>
  <circle cx="57" cy="470" r="5" fill="{PALETTE["dcbor"]}" /><text x="69" y="475" class="legend">Encode</text>
  <polygon points="163,464 169,470 163,476 157,470" fill="{PALETTE["coral"]}" /><text x="178" y="475" class="legend">Decode</text>
  <text x="275" y="475" class="caption">Shared log µs axis below · map panels share limits · input and output sizes differ across lower cases</text>
  {''.join(panels)}
  <text x="48" y="{height - 14}" class="caption">Points are medians of process batch means; hover for exact values. Raw samples, MAD, and workload hashes: profile/results.json.</text>
</svg>
'''


def _profile_case_order(category: str, case_id: str) -> int:
    order = {
        "float": ("float_fractional", "float_integral", "float_mixed_special", "float_boundaries"),
        "unicode": ("unicode_ascii", "unicode_nfc", "unicode_decomposed", "unicode_expanding_nfc"),
    }
    try:
        return order[category].index(case_id)
    except ValueError:
        return len(order.get(category, ()))


def _profile_case_label(category: str, case_id: str) -> str:
    labels = {
        "float_fractional": "Fractional",
        "float_integral": "Integral",
        "float_mixed_special": "Mixed special",
        "float_boundaries": "Boundaries",
        "unicode_ascii": "ASCII",
        "unicode_nfc": "NFC",
        "unicode_decomposed": "Decomposed",
        "unicode_expanding_nfc": "Expanding NFC",
    }
    return labels.get(case_id, case_id.replace("_", " ").capitalize())
