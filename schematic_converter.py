#!/usr/bin/env python3
"""
Convertisseur de schematics Minecraft 1.6/1.7 entre deux tables d'IDs.

Usage rapide:
    python schematic_converter.py maison.schematic --from nationsglory --to earthquest
    python schematic_converter.py maison.schematic --from earthquest --to nationsglory

Le script convertit les IDs de blocs du tableau Blocks/Data/AddBlocks.
Les inventaires dans les TileEntities ne sont pas modifies.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
import struct
import sys
import unicodedata
import zlib
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


TAG_END = 0
TAG_BYTE = 1
TAG_SHORT = 2
TAG_INT = 3
TAG_LONG = 4
TAG_FLOAT = 5
TAG_DOUBLE = 6
TAG_BYTE_ARRAY = 7
TAG_STRING = 8
TAG_LIST = 9
TAG_COMPOUND = 10
TAG_INT_ARRAY = 11
TAG_LONG_ARRAY = 12


@dataclass
class Tag:
    type_id: int
    value: Any


class NbtReader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def read(self, size: int) -> bytes:
        out = self.data[self.pos : self.pos + size]
        if len(out) != size:
            raise ValueError("NBT tronque: fin de fichier inattendue")
        self.pos += size
        return out

    def u8(self) -> int:
        return self.read(1)[0]

    def i8(self) -> int:
        return struct.unpack(">b", self.read(1))[0]

    def i16(self) -> int:
        return struct.unpack(">h", self.read(2))[0]

    def i32(self) -> int:
        return struct.unpack(">i", self.read(4))[0]

    def i64(self) -> int:
        return struct.unpack(">q", self.read(8))[0]

    def f32(self) -> float:
        return struct.unpack(">f", self.read(4))[0]

    def f64(self) -> float:
        return struct.unpack(">d", self.read(8))[0]

    def string(self) -> str:
        size = self.i16()
        return self.read(size).decode("utf-8")

    def named_tag(self) -> tuple[int, str, Tag]:
        tag_type = self.u8()
        if tag_type == TAG_END:
            return tag_type, "", Tag(TAG_END, None)
        name = self.string()
        return tag_type, name, Tag(tag_type, self.payload(tag_type))

    def payload(self, tag_type: int) -> Any:
        if tag_type == TAG_BYTE:
            return self.i8()
        if tag_type == TAG_SHORT:
            return self.i16()
        if tag_type == TAG_INT:
            return self.i32()
        if tag_type == TAG_LONG:
            return self.i64()
        if tag_type == TAG_FLOAT:
            return self.f32()
        if tag_type == TAG_DOUBLE:
            return self.f64()
        if tag_type == TAG_BYTE_ARRAY:
            size = self.i32()
            return bytearray(self.read(size))
        if tag_type == TAG_STRING:
            return self.string()
        if tag_type == TAG_LIST:
            child_type = self.u8()
            size = self.i32()
            return (child_type, [Tag(child_type, self.payload(child_type)) for _ in range(size)])
        if tag_type == TAG_COMPOUND:
            items: list[tuple[str, Tag]] = []
            while True:
                child_type = self.u8()
                if child_type == TAG_END:
                    return items
                child_name = self.string()
                items.append((child_name, Tag(child_type, self.payload(child_type))))
        if tag_type == TAG_INT_ARRAY:
            size = self.i32()
            return [self.i32() for _ in range(size)]
        if tag_type == TAG_LONG_ARRAY:
            size = self.i32()
            return [self.i64() for _ in range(size)]
        raise ValueError(f"Type NBT non supporte: {tag_type}")


class NbtWriter:
    def __init__(self):
        self.parts: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.parts.append(data)

    def u8(self, value: int) -> None:
        self.write(bytes([value & 0xFF]))

    def i8(self, value: int) -> None:
        self.write(struct.pack(">b", value))

    def i16(self, value: int) -> None:
        self.write(struct.pack(">h", value))

    def i32(self, value: int) -> None:
        self.write(struct.pack(">i", value))

    def i64(self, value: int) -> None:
        self.write(struct.pack(">q", value))

    def f32(self, value: float) -> None:
        self.write(struct.pack(">f", value))

    def f64(self, value: float) -> None:
        self.write(struct.pack(">d", value))

    def string(self, value: str) -> None:
        raw = value.encode("utf-8")
        self.i16(len(raw))
        self.write(raw)

    def named_tag(self, name: str, tag: Tag) -> None:
        self.u8(tag.type_id)
        if tag.type_id == TAG_END:
            return
        self.string(name)
        self.payload(tag)

    def payload(self, tag: Tag) -> None:
        tag_type = tag.type_id
        value = tag.value
        if tag_type == TAG_BYTE:
            self.i8(value)
        elif tag_type == TAG_SHORT:
            self.i16(value)
        elif tag_type == TAG_INT:
            self.i32(value)
        elif tag_type == TAG_LONG:
            self.i64(value)
        elif tag_type == TAG_FLOAT:
            self.f32(value)
        elif tag_type == TAG_DOUBLE:
            self.f64(value)
        elif tag_type == TAG_BYTE_ARRAY:
            self.i32(len(value))
            self.write(bytes(value))
        elif tag_type == TAG_STRING:
            self.string(value)
        elif tag_type == TAG_LIST:
            child_type, children = value
            self.u8(child_type)
            self.i32(len(children))
            for child in children:
                self.payload(child)
        elif tag_type == TAG_COMPOUND:
            for child_name, child in value:
                self.named_tag(child_name, child)
            self.u8(TAG_END)
        elif tag_type == TAG_INT_ARRAY:
            self.i32(len(value))
            for item in value:
                self.i32(item)
        elif tag_type == TAG_LONG_ARRAY:
            self.i32(len(value))
            for item in value:
                self.i64(item)
        else:
            raise ValueError(f"Type NBT non supporte: {tag_type}")

    def bytes(self) -> bytes:
        return b"".join(self.parts)


def decode_nbt_file(path: Path) -> tuple[str, int, str, Tag]:
    raw = path.read_bytes()
    compression = "raw"
    try:
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
            compression = "gzip"
        else:
            try:
                raw = zlib.decompress(raw)
                compression = "zlib"
            except zlib.error:
                pass
        reader = NbtReader(raw)
        tag_type, name, tag = reader.named_tag()
    except Exception as exc:
        raise ValueError(f"Impossible de lire le schematic NBT: {exc}") from exc
    if tag_type != TAG_COMPOUND:
        raise ValueError("Le root tag du schematic n'est pas un compound NBT")
    return compression, tag_type, name, tag


def encode_nbt_file(path: Path, root_name: str, root_tag: Tag, compression: str) -> None:
    writer = NbtWriter()
    writer.named_tag(root_name, root_tag)
    raw = writer.bytes()
    if compression == "gzip":
        payload = gzip.compress(raw)
    elif compression == "zlib":
        payload = zlib.compress(raw)
    elif compression == "raw":
        payload = raw
    else:
        raise ValueError(f"Compression inconnue: {compression}")
    path.write_bytes(payload)


def compound_get(compound: Tag, name: str) -> Tag | None:
    if compound.type_id != TAG_COMPOUND:
        raise ValueError("compound_get appele sur un tag non compound")
    for child_name, child in compound.value:
        if child_name == name:
            return child
    return None


def compound_set(compound: Tag, name: str, tag: Tag) -> None:
    if compound.type_id != TAG_COMPOUND:
        raise ValueError("compound_set appele sur un tag non compound")
    for index, (child_name, _) in enumerate(compound.value):
        if child_name == name:
            compound.value[index] = (name, tag)
            return
    compound.value.append((name, tag))


def compound_remove(compound: Tag, name: str) -> None:
    if compound.type_id != TAG_COMPOUND:
        raise ValueError("compound_remove appele sur un tag non compound")
    compound.value = [(child_name, child) for child_name, child in compound.value if child_name != name]


def normalize_name(value: str) -> str:
    value = value.strip().lower()
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.replace("minecraft:", "")
    value = re.sub(r"['’`]", "", value)
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return re.sub(r"_+", "_", value).strip("_")


def parse_id_meta(value: str) -> tuple[int, int]:
    if ":" in value:
        block_id, meta = value.split(":", 1)
        return int(block_id), int(meta)
    return int(value), 0


@dataclass(frozen=True)
class BlockRow:
    name: str
    block_id: int
    meta: int
    internal_name: str
    source: str

    def keys(self) -> set[str]:
        out = {normalize_name(self.name), normalize_name(self.internal_name)}
        return {key for key in out if key}


def load_rows(path: Path) -> list[BlockRow]:
    rows: list[BlockRow] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            id_field = raw.get("id_numerique") or raw.get("id") or ""
            if not id_field:
                continue
            block_id, meta = parse_id_meta(id_field)
            name = raw.get("nom") or raw.get("name") or raw.get("nom_interne") or str(block_id)
            internal = raw.get("nom_interne") or name
            source = raw.get("source") or raw.get("source_config") or ""
            rows.append(BlockRow(name=name, block_id=block_id, meta=meta, internal_name=internal, source=source))
    return rows


def index_by_key(rows: list[BlockRow]) -> dict[str, list[BlockRow]]:
    index: dict[str, list[BlockRow]] = defaultdict(list)
    seen: set[tuple[str, int, int, str]] = set()
    for row in rows:
        for key in row.keys():
            dedupe_key = (key, row.block_id, row.meta, row.internal_name)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            index[key].append(row)
    return index


def build_conversion_map(
    source_rows: list[BlockRow], target_rows: list[BlockRow]
) -> tuple[dict[int, int], dict[int, list[BlockRow]], list[str], dict[int, list[BlockRow]]]:
    target_index = index_by_key(target_rows)
    source_known_by_id: dict[int, list[BlockRow]] = defaultdict(list)
    source_id_to_targets: dict[int, set[int]] = defaultdict(set)
    source_id_examples: dict[int, list[BlockRow]] = defaultdict(list)
    warnings: list[str] = []

    for row in source_rows:
        source_known_by_id[row.block_id].append(row)
        matches: list[BlockRow] = []
        for key in row.keys():
            candidates = target_index.get(key, [])
            if len({candidate.block_id for candidate in candidates}) == 1:
                matches.extend(candidates)
        target_ids = {match.block_id for match in matches}
        if len(target_ids) == 1:
            target_id = next(iter(target_ids))
            source_id_to_targets[row.block_id].add(target_id)
            source_id_examples[row.block_id].append(row)
        elif len(target_ids) > 1:
            warnings.append(
                f"Correspondance ambigue pour {row.name} ({row.block_id}:0): "
                + ", ".join(str(item) for item in sorted(target_ids))
            )

    conversion: dict[int, int] = {}
    ambiguous_source_ids: dict[int, list[BlockRow]] = {}
    for source_id, target_ids in source_id_to_targets.items():
        if len(target_ids) == 1:
            target_id = next(iter(target_ids))
            if target_id > 4095:
                warnings.append(f"ID cible impossible en .schematic classique: {target_id} pour source {source_id}")
                continue
            conversion[source_id] = target_id
        else:
            ambiguous_source_ids[source_id] = source_id_examples[source_id]
            warnings.append(
                f"ID source {source_id} ambigu: plusieurs IDs cibles possibles "
                + ", ".join(str(item) for item in sorted(target_ids))
            )
    return conversion, source_known_by_id, warnings, ambiguous_source_ids


def get_block_id(blocks: bytearray, add_blocks: bytearray | None, index: int) -> int:
    low = blocks[index] & 0xFF
    if add_blocks is None:
        return low
    packed = add_blocks[index >> 1] & 0xFF
    high = (packed & 0x0F) if index % 2 == 0 else ((packed >> 4) & 0x0F)
    return low | (high << 8)


def set_block_id(blocks: bytearray, add_blocks: bytearray, index: int, block_id: int) -> None:
    blocks[index] = block_id & 0xFF
    high = (block_id >> 8) & 0x0F
    packed = add_blocks[index >> 1] & 0xFF
    if index % 2 == 0:
        packed = (packed & 0xF0) | high
    else:
        packed = (packed & 0x0F) | (high << 4)
    add_blocks[index >> 1] = packed


def convert_schematic(
    input_path: Path,
    output_path: Path,
    conversion: dict[int, int],
    source_known_by_id: dict[int, list[BlockRow]],
    unmapped_known: str,
    compression_choice: str,
) -> dict[str, Any]:
    input_compression, _, root_name, root_tag = decode_nbt_file(input_path)
    compression = input_compression if compression_choice == "same" else compression_choice

    blocks_tag = compound_get(root_tag, "Blocks")
    data_tag = compound_get(root_tag, "Data")
    add_tag = compound_get(root_tag, "AddBlocks")
    if blocks_tag is None or blocks_tag.type_id != TAG_BYTE_ARRAY:
        raise ValueError("Tag Blocks absent ou invalide")
    if data_tag is None or data_tag.type_id != TAG_BYTE_ARRAY:
        raise ValueError("Tag Data absent ou invalide")

    blocks = blocks_tag.value
    data = data_tag.value
    if len(blocks) != len(data):
        raise ValueError(f"Tailles Blocks/Data incoherentes: {len(blocks)} != {len(data)}")

    add_blocks = add_tag.value if add_tag is not None and add_tag.type_id == TAG_BYTE_ARRAY else None
    new_add_blocks = bytearray((len(blocks) + 1) // 2)

    changed = 0
    known_unmapped_counts: Counter[int] = Counter()
    converted_counts: Counter[tuple[int, int]] = Counter()

    for index in range(len(blocks)):
        old_id = get_block_id(blocks, add_blocks, index)
        new_id = old_id
        if old_id in conversion:
            new_id = conversion[old_id]
        elif old_id in source_known_by_id:
            known_unmapped_counts[old_id] += 1
            if unmapped_known == "air":
                new_id = 0
                data[index] = 0
            elif unmapped_known == "error":
                examples = ", ".join(row.name for row in source_known_by_id[old_id][:3])
                raise ValueError(f"Bloc source sans correspondance: ID {old_id} ({examples})")

        if new_id != old_id:
            changed += 1
            converted_counts[(old_id, new_id)] += 1
        set_block_id(blocks, new_add_blocks, index, new_id)

    compound_set(root_tag, "Blocks", Tag(TAG_BYTE_ARRAY, blocks))
    compound_set(root_tag, "Data", Tag(TAG_BYTE_ARRAY, data))
    if any(value != 0 for value in new_add_blocks):
        compound_set(root_tag, "AddBlocks", Tag(TAG_BYTE_ARRAY, new_add_blocks))
    else:
        compound_remove(root_tag, "AddBlocks")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    encode_nbt_file(output_path, root_name, root_tag, compression)

    return {
        "input": str(input_path),
        "output": str(output_path),
        "input_compression": input_compression,
        "output_compression": compression,
        "total_blocks": len(blocks),
        "changed_blocks": changed,
        "known_unmapped_blocks": [
            {
                "source_id": block_id,
                "count": count,
                "names": sorted({row.name for row in source_known_by_id[block_id]})[:8],
            }
            for block_id, count in known_unmapped_counts.most_common()
        ],
        "converted_pairs": [
            {"from": old_id, "to": new_id, "count": count}
            for (old_id, new_id), count in converted_counts.most_common()
        ],
    }


def default_csv(pack: str, script_dir: Path) -> Path:
    return script_dir / f"{pack}_block_ids.csv"


def opposite_pack(pack: str) -> str:
    return "earthquest" if pack == "nationsglory" else "nationsglory"


def export_map(path: Path, conversion: dict[int, int], source_rows: list[BlockRow], target_rows: list[BlockRow]) -> None:
    source_by_id: dict[int, list[str]] = defaultdict(list)
    target_by_id: dict[int, list[str]] = defaultdict(list)
    for row in source_rows:
        source_by_id[row.block_id].append(row.name)
    for row in target_rows:
        target_by_id[row.block_id].append(row.name)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["source_id", "target_id", "source_names", "target_names"])
        writer.writeheader()
        for source_id, target_id in sorted(conversion.items()):
            writer.writerow(
                {
                    "source_id": f"{source_id}:0",
                    "target_id": f"{target_id}:0",
                    "source_names": "; ".join(sorted(set(source_by_id[source_id]))),
                    "target_names": "; ".join(sorted(set(target_by_id[target_id]))),
                }
            )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convertit un .schematic entre NationsGlory et EarthQuest.")
    parser.add_argument("schematic", nargs="?", help="Fichier .schematic a convertir")
    parser.add_argument("--from", dest="source_pack", required=True, choices=["earthquest", "nationsglory"])
    parser.add_argument("--to", dest="target_pack", choices=["earthquest", "nationsglory"])
    parser.add_argument("-o", "--output", help="Fichier .schematic de sortie")
    parser.add_argument("--earthquest-csv", type=Path, help="Table CSV EarthQuest")
    parser.add_argument("--nationsglory-csv", type=Path, help="Table CSV NationsGlory")
    parser.add_argument("--unmapped-known", choices=["keep", "air", "error"], default="keep")
    parser.add_argument("--compression", choices=["same", "gzip", "zlib", "raw"], default="same")
    parser.add_argument("--report", type=Path, help="Chemin du rapport JSON")
    parser.add_argument("--export-map", type=Path, help="Exporte la table source->cible en CSV")
    parser.add_argument("--show-map", action="store_true", help="Affiche seulement les statistiques de mapping")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    script_dir = Path(__file__).resolve().parent
    target_pack = args.target_pack or opposite_pack(args.source_pack)
    if target_pack == args.source_pack:
        print("Le pack source et le pack cible sont identiques.", file=sys.stderr)
        return 2

    csv_paths = {
        "earthquest": args.earthquest_csv or default_csv("earthquest", script_dir),
        "nationsglory": args.nationsglory_csv or default_csv("nationsglory", script_dir),
    }
    for pack, path in csv_paths.items():
        if not path.exists():
            print(f"Table introuvable pour {pack}: {path}", file=sys.stderr)
            return 2

    source_rows = load_rows(csv_paths[args.source_pack])
    target_rows = load_rows(csv_paths[target_pack])
    conversion, source_known_by_id, warnings, ambiguous = build_conversion_map(source_rows, target_rows)

    if args.export_map:
        export_map(args.export_map, conversion, source_rows, target_rows)

    print(f"Mapping {args.source_pack} -> {target_pack}: {len(conversion)} IDs de blocs correspondants.")
    if warnings:
        print(f"Avertissements mapping: {len(warnings)}")
        for warning in warnings[:8]:
            print(f"  - {warning}")
        if len(warnings) > 8:
            print(f"  - ... {len(warnings) - 8} autres")

    if args.show_map:
        return 0

    if not args.schematic:
        print("Il manque le fichier .schematic a convertir.", file=sys.stderr)
        return 2

    input_path = Path(args.schematic).resolve()
    if not input_path.exists():
        print(f"Fichier introuvable: {input_path}", file=sys.stderr)
        return 2

    output_path = (
        Path(args.output).resolve()
        if args.output
        else input_path.with_name(f"{input_path.stem}.converted-{target_pack}{input_path.suffix}")
    )
    report_path = args.report or output_path.with_suffix(output_path.suffix + ".report.json")

    report = convert_schematic(
        input_path=input_path,
        output_path=output_path,
        conversion=conversion,
        source_known_by_id=source_known_by_id,
        unmapped_known=args.unmapped_known,
        compression_choice=args.compression,
    )
    report["source_pack"] = args.source_pack
    report["target_pack"] = target_pack
    report["mapping_entries"] = len(conversion)
    report["ambiguous_source_ids"] = {
        str(block_id): sorted({row.name for row in rows})[:8] for block_id, rows in ambiguous.items()
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Sortie: {output_path}")
    print(f"Rapport: {report_path}")
    print(f"Blocs changes: {report['changed_blocks']} / {report['total_blocks']}")
    if report["known_unmapped_blocks"]:
        print(f"Blocs source connus sans correspondance: {len(report['known_unmapped_blocks'])}")
        for item in report["known_unmapped_blocks"][:10]:
            print(f"  - {item['source_id']}: {item['count']} blocs ({', '.join(item['names'])})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
