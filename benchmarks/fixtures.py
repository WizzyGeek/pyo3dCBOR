"""Small, representative JSON-compatible values shared by benchmark runners."""

from __future__ import annotations


def fixtures() -> dict[str, object]:
    """Return ordinary JSON-compatible workloads for cross-codec comparison."""
    article_paragraphs = (
        "The town opened a new riverside path on Saturday, giving walkers and cyclists a quiet route between the market and the old rail bridge. The project took two years to plan, with residents choosing the trees, benches, and lighting along the way.",
        "Work crews kept one lane open through most of construction, and local shops reported steady foot traffic throughout the summer. A small viewing deck now marks the place where the canal meets the river, with signs describing the area's shipping history.",
        "City staff will inspect the path each morning and clear leaves after storms. The first maintenance review is scheduled for next spring, when engineers will check the surface and collect comments from people who use the route every day.",
        "Several schools have already added the river walk to their outdoor lessons. Students can compare water levels at marked posts, watch birds from the deck, and follow a short map that connects the path to the library and community garden.",
    )
    # Repeating complete plain ASCII paragraphs creates a realistic article-sized
    # text payload while keeping the fixture deterministic and easy to audit.
    article_body = "\n\n".join(article_paragraphs * 5)

    return {
        "small_record": {
            "id": 42,
            "name": "Ada",
            "active": True,
            "nickname": None,
        },
        "nested_document": {
            "user": {"id": 731, "name": "Mira"},
            "roles": ["reader", "editor"],
            "settings": {"theme": "dark", "alerts": False},
            "scores": [3, 8, 13],
        },
        "repeated_unicode_strings": [
            {"city": city, "label": "café", "unit": "km"}
            for city in ("Zürich", "Montréal", "Zürich", "Montréal") * 8
        ],
        "numeric_array": [
            -1000000, -257, -24, -1, 0, 1, 23, 256, 65536, 2**32,
            0.25, -1.5, 3.125, 1.1, 1e20,
        ] * 12,
        "compact_scientific_notation": [1e100, 1e-100],
        "large_collection": [
            {
                "item": index,
                "group": f"group-{index % 8}",
                "enabled": index % 3 != 0,
                "values": [index, index + 1, index + 2],
            }
            for index in range(128)
        ],
        "telemetry_batch": {
            "site_id": "north-campus",
            "samples": [
                {
                    "timestamp": 1_798_876_800 + index * 5,
                    "device_id": f"sensor-{index % 8:02d}",
                    "temperature_c": 18.125 + (index % 4) * 0.125,
                    "humidity_pct": 41.375 + (index % 4) * 0.125,
                    "online": index % 11 != 0,
                }
                for index in range(64)
            ],
        },
        "ascii_article": {
            "title": "A new path brings the river closer to town",
            "byline": "Community Desk",
            "section": "Local News",
            "body": article_body,
        },
    }
