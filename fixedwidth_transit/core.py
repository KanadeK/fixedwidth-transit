"""Explicit byte layouts; no inference, numeric casts or truncation."""

import csv
import io
from dataclasses import dataclass

from ._files import InputError, integer, keys, load_config, names, publish, regular

ENCODINGS = {"utf-8", "ascii", "latin-1", "cp1252", "shift_jis", "cp932"}
SEPARATORS = {"lf": b"\n", "crlf": b"\r\n", "none": b""}
MAX_WIDTH = 1024 * 1024


@dataclass(frozen=True)
class Field:
    name: str
    width: int
    padding: str
    pad: str

    def unpack(self, raw, encoding):
        try:
            value = raw.decode(encoding, errors="strict")
            if value.encode(encoding) != raw:
                raise InputError("encoding does not round-trip these bytes")
        except UnicodeError as exc:
            raise InputError("invalid or split encoded character") from exc
        if any(c in value for c in "\r\n\0"):
            raise InputError("record contains CR, LF or NUL in a field")
        if self.padding == "right":
            return value.rstrip(self.pad)
        if self.padding == "left":
            return value.lstrip(self.pad)
        return value

    def pack(self, value, encoding):
        if any(c in value for c in "\r\n\0"):
            raise InputError("field contains CR, LF or NUL")
        if (self.padding == "right" and value.endswith(self.pad)) or (
            self.padding == "left" and value.startswith(self.pad)
        ):
            raise InputError("value has ambiguous padding on the stripped side")
        try:
            raw = value.encode(encoding, errors="strict")
            if raw.decode(encoding) != value:
                raise InputError("encoding would change the text")
        except UnicodeError as exc:
            raise InputError("value is not representable in the layout encoding") from exc
        if len(raw) > self.width:
            raise InputError("encoded value exceeds field byte width")
        missing = self.width - len(raw)
        if self.padding == "none":
            if missing:
                raise InputError("unpadded value must exactly fill its byte width")
            return raw
        pad = self.pad.encode(encoding) * missing
        return pad + raw if self.padding == "left" else raw + pad


@dataclass(frozen=True)
class Layout:
    fields: tuple[Field, ...]
    encoding: str
    separator: bytes

    @property
    def width(self):
        return sum(f.width for f in self.fields)

    @classmethod
    def from_dict(cls, data):
        keys(
            data,
            {"version", "encoding", "separator", "fields"},
            {"version", "encoding", "separator", "fields"},
        )
        integer(data["version"], 1, 1)
        if not isinstance(data["encoding"], str) or data["encoding"] not in ENCODINGS:
            raise InputError("unsupported layout encoding")
        if not isinstance(data["separator"], str) or data["separator"] not in SEPARATORS:
            raise InputError("separator must be lf, crlf or none")
        if not isinstance(data["fields"], list) or not data["fields"]:
            raise InputError("fields must be a nonempty list")
        fields = []
        for item in data["fields"]:
            keys(item, {"name", "width", "padding", "pad"}, {"name", "width"})
            width = integer(item["width"], 1, MAX_WIDTH)
            padding = item.get("padding", "right")
            pad = item.get("pad", " ")
            if padding not in ("left", "right", "none"):
                raise InputError("padding must be left, right or none")
            if not isinstance(pad, str) or len(pad) != 1 or not 32 <= ord(pad) <= 126:
                raise InputError("pad must be one printable ASCII character")
            fields.append(Field(item["name"], width, padding, pad))
        names([f.name for f in fields])
        if sum(f.width for f in fields) > MAX_WIDTH:
            raise InputError("total record width exceeds 1 MiB")
        return cls(tuple(fields), data["encoding"], SEPARATORS[data["separator"]])

    def decode(self, source):
        width = self.width
        size = width + len(self.separator)
        record = 0
        while block := source.read(size):
            record += 1
            if len(block) < width:
                raise InputError(f"record {record}: truncated record")
            if len(block) > width and block[width:] != self.separator:
                raise InputError(f"record {record}: invalid separator or excess bytes")
            # An unterminated final record is allowed, but a partial CRLF is not.
            row, offset = [], 0
            for field in self.fields:
                try:
                    row.append(field.unpack(block[offset : offset + field.width], self.encoding))
                except InputError as exc:
                    raise InputError(f"record {record}, column {len(row) + 1}: {exc}") from exc
                offset += field.width
            yield row

    def encode(self, row, record):
        if len(row) != len(self.fields):
            raise InputError(f"record {record}: column count differs from layout")
        parts = []
        for index, (field, value) in enumerate(zip(self.fields, row, strict=True), 1):
            try:
                parts.append(field.pack(value, self.encoding))
            except InputError as exc:
                raise InputError(f"record {record}, column {index}: {exc}") from exc
        return b"".join(parts) + self.separator


def convert(mode, layout_path, input_path, output_path, force=False):
    layout = Layout.from_dict(load_config(layout_path))
    source_path = regular(input_path)
    count = 0
    with publish(output_path, [source_path, layout_path], force) as target:
        if mode == "decode":

            def write_csv(row):
                buffer = io.StringIO(newline="")
                csv.writer(buffer, lineterminator="\n").writerow(row)
                target.write(buffer.getvalue().encode("utf-8"))

            write_csv([f.name for f in layout.fields])
            with source_path.open("rb") as source:
                for row in layout.decode(source):
                    write_csv(row)
                    count += 1
        elif mode == "encode":
            previous = csv.field_size_limit(MAX_WIDTH)
            try:
                with source_path.open(encoding="utf-8-sig", newline="") as source:
                    reader = csv.reader(source, strict=True)
                    if next(reader, None) != [f.name for f in layout.fields]:
                        raise InputError(
                            "CSV header must exactly match layout field names and order"
                        )
                    for count, row in enumerate(reader, 1):
                        target.write(layout.encode(row, count))
            finally:
                csv.field_size_limit(previous)
        else:
            raise InputError("mode must be decode or encode")
    return {"status": "ok", "mode": mode, "records": count, "record_bytes": layout.width}
