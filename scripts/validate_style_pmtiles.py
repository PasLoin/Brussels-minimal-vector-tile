#!/usr/bin/env python3
"""Validate that style.json references existing PMTiles sources and layers."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def metadata_path_for_source(style_path: Path, metadata_dir: Path, source_url: str) -> Path:
    parsed = urlparse(source_url)
    if parsed.scheme or parsed.netloc:
        raise ValueError(
            f"Only local PMTiles source URLs are supported by this validation: {source_url}"
        )

    pmtiles_path = (style_path.parent / parsed.path).resolve()
    metadata_name = f"{pmtiles_path.name}.metadata.json"
    return metadata_dir / metadata_name


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--style", type=Path, required=True, help="MapLibre style JSON file")
    parser.add_argument(
        "--metadata-dir",
        type=Path,
        required=True,
        help="Directory produced by extract_pmtiles_metadata.py",
    )
    args = parser.parse_args()

    style = load_json(args.style)
    if not isinstance(style, dict):
        raise ValueError(f"{args.style} must contain a JSON object")

    sources = style.get("sources")
    layers = style.get("layers")
    if not isinstance(sources, dict):
        raise ValueError(f"{args.style} must contain a sources object")
    if not isinstance(layers, list):
        raise ValueError(f"{args.style} must contain a layers array")

    pmtiles_layers_by_source: dict[str, set[str]] = {}
    for source_id, source in sources.items():
        if not isinstance(source_id, str) or not isinstance(source, dict):
            raise ValueError("Style sources must be an object keyed by source id")
        if source.get("type") != "vector":
            continue

        source_url = source.get("url")
        if not isinstance(source_url, str) or not source_url.endswith(".pmtiles.gz"):
            raise ValueError(
                f"Vector source {source_id!r} must use a local .pmtiles.gz url"
            )

        metadata_path = metadata_path_for_source(args.style, args.metadata_dir, source_url)
        metadata = load_json(metadata_path)
        if not isinstance(metadata, dict):
            raise ValueError(f"{metadata_path} must contain a JSON object")

        vector_layers = metadata.get("vector_layers")
        if not isinstance(vector_layers, list) or not vector_layers:
            raise ValueError(f"{metadata_path} must contain a non-empty vector_layers array")

        layer_ids = {
            layer.get("id")
            for layer in vector_layers
            if isinstance(layer, dict) and isinstance(layer.get("id"), str)
        }
        if not layer_ids:
            raise ValueError(f"{metadata_path} does not define any vector layer ids")
        pmtiles_layers_by_source[source_id] = layer_ids

    for layer in layers:
        if not isinstance(layer, dict):
            raise ValueError("Every style layer must be a JSON object")

        layer_id = layer.get("id", "<unnamed>")
        source_id = layer.get("source")
        if source_id is None:
            continue
        if not isinstance(source_id, str) or source_id not in sources:
            raise ValueError(f"Style layer {layer_id!r} references unknown source {source_id!r}")

        source = sources[source_id]
        if not isinstance(source, dict) or source.get("type") != "vector":
            continue

        source_layer = layer.get("source-layer")
        if not isinstance(source_layer, str) or not source_layer:
            raise ValueError(
                f"Vector style layer {layer_id!r} must define a non-empty source-layer"
            )

        available_layers = pmtiles_layers_by_source[source_id]
        if source_layer not in available_layers:
            available = ", ".join(sorted(available_layers))
            raise ValueError(
                f"Style layer {layer_id!r} references source-layer {source_layer!r} "
                f"which is absent from PMTiles source {source_id!r}; available: {available}"
            )

    print(f"✓ {args.style}: vector sources and source-layer references match PMTiles metadata")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
