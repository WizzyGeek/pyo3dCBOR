"""Shared accessible colors and small SVG helpers for benchmark figures."""

from __future__ import annotations

import hashlib
import math
from html import escape
from pathlib import Path


PALETTE = {
    "ink": "#172B3A",
    "muted": "#607482",
    "line": "#D8E1E4",
    "paper": "#FFFFFF",
    "canvas": "#F5F7F6",
    "track": "#E8EDEE",
    "json": "#315C7D",
    "dcbor": "#087E78",
    "cbor2_default": "#477EA8",
    "cbor2_canonical": "#8AAAC1",
    "cborx_default": "#D96B57",
    "cborx_canonical": "#A54844",
    "fast_pale": "#A9D9CE",
    "parity": "#EFF2F1",
    "slow_pale": "#E8B2A9",
}


COMMON_STYLE = """
  text { font-family: Inter, ui-sans-serif, system-ui, -apple-system, sans-serif; fill: #172B3A; }
  .title { font-size: 23px; font-weight: 700; letter-spacing: -0.35px; }
  .subtitle { font-size: 13px; fill: #435B6A; }
  .caption { font-size: 11.5px; fill: #607482; }
  .fixture { font-size: 13px; font-weight: 650; }
  .small { font-size: 11.5px; fill: #435B6A; }
  .value { font-size: 12px; font-weight: 560; font-variant-numeric: tabular-nums; }
  .muted { fill: #607482; }
  .card { fill: #FFFFFF; stroke: #D8E1E4; stroke-width: 1; }
  .rule { stroke: #D8E1E4; stroke-width: 1; }
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
