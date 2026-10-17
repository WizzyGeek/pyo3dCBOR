"""Shared accessible colors and small SVG helpers for benchmark figures."""

from __future__ import annotations

import hashlib
import math
from html import escape
from pathlib import Path


PALETTE = {
    "ink": "#142B39",
    "muted": "#586D79",
    "line": "#E0E7EA",
    "line_strong": "#B8C7CE",
    "paper": "#FFFFFF",
    "canvas": "#FFFFFF",
    "track": "#E8EEF0",
    "json": "#255B75",
    "dcbor": "#08766F",
    "coral": "#C94E47",
    "generic_range": "#738B9D",
    "cbor2_default": "#477EA8",
    "cbor2_canonical": "#8AAAC1",
    "cborx_default": "#D96B57",
    "cborx_canonical": "#A54844",
    "fast_pale": "#A9D9CE",
    "parity": "#EFF2F1",
    "slow_pale": "#E8B2A9",
}


COMMON_STYLE = """
  text { font-family: Inter, ui-sans-serif, system-ui, -apple-system, sans-serif; fill: #142B39; }
  .title { font-size: 27px; font-weight: 740; letter-spacing: -0.45px; }
  .subtitle { font-size: 15px; fill: #586D79; }
  .caption { font-size: 13px; fill: #586D79; }
  .fixture { font-size: 16px; font-weight: 650; }
  .small { font-size: 14px; fill: #586D79; }
  .value { font-size: 15px; font-weight: 600; font-variant-numeric: tabular-nums; }
  .muted { fill: #586D79; }
  .card { fill: #FFFFFF; stroke: #E0E7EA; stroke-width: 1; }
  .rule { stroke: #E0E7EA; stroke-width: 1; }
  .legend { font-size: 15px; fill: #435967; }
  .column-head { font-size: 14px; fill: #586D79; font-weight: 650; }
  .axis { font-size: 14px; fill: #586D79; font-variant-numeric: tabular-nums; }
"""


def xml_text(value: object) -> str:
    """Escape text content before inserting it into SVG markup."""
    return escape(str(value), quote=False)


def sha256_file(path: Path) -> str:
    """Hash a source helper for benchmark report provenance."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ratio_fill(ratio: float) -> str:
    """Return an accessible pale teal/neutral/coral fill around a 1× baseline."""
    if ratio <= 0 or not math.isfinite(ratio):
        return PALETTE["parity"]
    if ratio < 1:
        intensity = min(1.0, abs(math.log2(ratio)) / 3.0)
        start, end = PALETTE["parity"], PALETTE["fast_pale"]
    else:
        intensity = min(1.0, math.log2(ratio) / 3.0)
        start, end = PALETTE["parity"], PALETTE["slow_pale"]
    start_rgb = tuple(int(start[index:index + 2], 16) for index in (1, 3, 5))
    end_rgb = tuple(int(end[index:index + 2], 16) for index in (1, 3, 5))
    channels = tuple(
        round(left + (right - left) * intensity)
        for left, right in zip(start_rgb, end_rgb)
    )
    return "#" + "".join(f"{channel:02X}" for channel in channels)
