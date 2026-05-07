#!/usr/bin/env python3
"""Extract JSON metadata from PMTiles v3 archives for schema validation."""

from __future__ import annotations

import argparse
import gzip
import json
import sys
import zlib
from pathlib import Path

HEADER_LEN = 127
MAGIC = b"PMTiles"
COMPRESSION_NONE = 0x01
COMPRESSION_GZIP = 0x02
COMPRESSION_BROTLI = 0x03
COMPRESSION_ZSTD = 0x04
TILE_TYPES_REQUIRING_VECTOR_LAYERS = {
    0x01: "MVT Vector Tile",
    0x06: "MapLibre Vector Tile",
}


def read_u64_le(buf: bytes, offset: int) -> int:
    return int.from_bytes(buf[offset : offset + 8], byteorder="little", signed=False)


def maybe_unwrap_outer_gzip(data: bytes) -> bytes:
    """Support this repository's historical .pmtiles.gz extension.

    The generator currently renames .pmtiles to .pmtiles.gz without wrapping the
    full archive in gzip, but this keeps validation robust if that changes.
    """
    if data.startswith(b"\x1f\x8b"):
        return gzip.decompress(data)
    return data


def decompress_metadata(payload: bytes, compression: int) -> bytes:
    if compression == COMPRESSION_NONE:
        return payload
    if compression == COMPRESSION_GZIP:
        return zlib.decompress(payload, wbits=16 + zlib.MAX_WBITS)
    if compression == COMPRESSION_BROTLI:
        import brotli  # type: ignore[import-not-found]

        return brotli.decompress(payload)
    if compression == COMPRESSION_ZSTD:
        import zstandard  # type: ignore[import-not-found]

        return zstandard.ZstdDecompressor().decompress(payload)
    raise ValueError(f"Unsupported PMTiles internal compression value: 0x{compression:02x}")


def extract_metadata(pmtiles_path: Path) -> tuple[dict, int]:
    data = maybe_unwrap_outer_gzip(pmtiles_path.read_bytes())
    if len(data) < HEADER_LEN:
        raise ValueError(f"{pmtiles_path} is too small to be a PMTiles v3 archive")
    if data[:7] != MAGIC:
        raise ValueError(f"{pmtiles_path} does not start with the PMTiles magic number")
    version = data[7]
    if version != 3:
        raise ValueError(f"{pmtiles_path} is PMTiles v{version}, expected v3")

    metadata_offset = read_u64_le(data, 24)
    metadata_length = read_u64_le(data, 32)
    internal_compression = data[97]
    tile_type = data[99]

    if metadata_length == 0:
        raise ValueError(f"{pmtiles_path} has no JSON metadata section")
    metadata_end = metadata_offset + metadata_length
    if metadata_end > len(data):
        raise ValueError(f"{pmtiles_path} metadata section extends beyond the file size")

    metadata_bytes = decompress_metadata(
        data[metadata_offset:metadata_end], internal_compression
    )
    metadata = json.loads(metadata_bytes.decode("utf-8"))
    if not isinstance(metadata, dict):
        raise ValueError(f"{pmtiles_path} metadata must be a JSON object")

    if tile_type in TILE_TYPES_REQUIRING_VECTOR_LAYERS and "vector_layers" not in metadata:
        tile_type_name = TILE_TYPES_REQUIRING_VECTOR_LAYERS[tile_type]
        raise ValueError(
            f"{pmtiles_path} has tile type {tile_type_name} but no vector_layers metadata"
        )

    return metadata, tile_type


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pmtiles", nargs="+", type=Path, help="PMTiles archive(s) to inspect")
    parser.add_argument(
        "--out-dir",
        type=Path,
        required=True,
        help="Directory where extracted metadata JSON files are written",
    )
    parser.add_argument(
        "--github-output",
        type=Path,
        help="Optional GitHub Actions output file receiving jsons=<comma-separated paths>",
    )
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    output_paths: list[Path] = []

    for pmtiles_path in args.pmtiles:
        metadata, tile_type = extract_metadata(pmtiles_path)
        output_path = args.out_dir / f"{pmtiles_path.name}.metadata.json"
        output_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        output_paths.append(output_path)
        print(f"✓ {pmtiles_path}: extracted metadata (tile type 0x{tile_type:02x})")

    jsons = ",".join(str(path) for path in output_paths)
    print(jsons)

    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as github_output:
            github_output.write(f"jsons={jsons}\n")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
