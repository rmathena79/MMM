from __future__ import annotations

from pathlib import Path

import requests

from common import add_source_manifest, log
from config import RAW_SOURCE_DIR, SOURCES, USER_AGENT


def fetch_all_sources() -> dict[str, Path]:
    RAW_SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    saved_paths: dict[str, Path] = {}

    for source in SOURCES:
        output_path = RAW_SOURCE_DIR / source["filename"]
        mode = source.get("mode")
        if mode == "barttorvik":
            session.get(source["url"], timeout=30)
            response = session.post(
                source["url"],
                data={"js_test_submitted": "1"},
                headers={"Referer": source["url"]},
                timeout=30,
            )
        else:
            response = session.get(source["url"], timeout=30)
        response.raise_for_status()

        if source["content_type"] == "binary":
            output_path.write_bytes(response.content)
        else:
            output_path.write_text(response.text, encoding="utf-8")

        add_source_manifest(
            source_id=source["id"],
            url=source["url"],
            file_path=output_path,
            description=source["description"],
        )
        log(f"Fetched {source['id']} -> {output_path}")
        saved_paths[source["id"]] = output_path

    return saved_paths
