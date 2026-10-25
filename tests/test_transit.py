import copy
import csv
import io
import json
import os
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fixedwidth_transit._files import InputError, load_config, publish
from fixedwidth_transit.core import Field, Layout, convert


def config(separator="lf", encoding="utf-8"):
    return {
        "version": 1,
        "encoding": encoding,
        "separator": separator,
        "fields": [{"name": "id", "width": 3, "padding": "none"}, {"name": "text", "width": 12}],
    }


class LayoutTests(unittest.TestCase):
    def test_utf8_byte_offsets(self):
        layout = Layout.from_dict(config())
        raw = layout.encode(["001", "東京"], 1)
        self.assertEqual(raw, b"001" + "東京".encode() + b"      \n")
        self.assertEqual(list(layout.decode(io.BytesIO(raw))), [["001", "東京"]])

    def test_cp932(self):
        layout = Layout.from_dict(config(encoding="cp932"))
        raw = layout.encode(["001", "日本"], 1)
        self.assertEqual(len(raw), 16)
        self.assertEqual(list(layout.decode(io.BytesIO(raw)))[0][1], "日本")

    def test_all_separators_and_final_unterminated(self):
        for separator in ("lf", "crlf", "none"):
            layout = Layout.from_dict(config(separator))
            record = layout.encode(["001", "word"], 1)
            for raw in (record * 2, record + record[: layout.width]):
                self.assertEqual(len(list(layout.decode(io.BytesIO(raw)))), 2)

    def test_split_utf8(self):
        data = config()
        data["fields"][0]["width"] = 1
        layout = Layout.from_dict(data)
        with self.assertRaisesRegex(InputError, "split"):
            list(layout.decode(io.BytesIO(b"\xc3" + b"\xa9" + b" " * 11 + b"\n")))

    def test_truncated_and_excess_and_wrong_separator(self):
        layout = Layout.from_dict(config("crlf"))
        for data in (
            b"001short",
            b"001" + b" " * 12 + b"\r",
            b"001" + b" " * 12 + b"X\n",
            b"001" + b" " * 12 + b"\n",
        ):
            with self.subTest(data=data), self.assertRaises(InputError):
                list(layout.decode(io.BytesIO(data)))

    def test_no_padding_exact_width(self):
        field = Field("id", 4, "none", " ")
        self.assertEqual(field.pack("0001", "ascii"), b"0001")
        with self.assertRaises(InputError):
            field.pack("1", "ascii")

    def test_left_padding(self):
        field = Field("n", 5, "left", "0")
        self.assertEqual(field.pack("42", "ascii"), b"00042")
        self.assertEqual(field.unpack(b"00042", "ascii"), "42")
        self.assertEqual(field.pack("", "ascii"), b"00000")

    def test_ambiguous_padding(self):
        for field, value in [
            (Field("x", 5, "right", " "), "x "),
            (Field("x", 5, "left", "0"), "01"),
        ]:
            with self.assertRaisesRegex(InputError, "ambiguous"):
                field.pack(value, "utf-8")

    def test_multibyte_pad_byte_overlap(self):
        # A Shift-JIS character can end in an ASCII-looking byte. Strip text, not bytes.
        char = "ソ"
        self.assertEqual(char.encode("shift_jis")[-1], 0x5C)
        field = Field("x", 4, "right", "\\")
        self.assertEqual(field.unpack(char.encode("shift_jis") + b"\\\\", "shift_jis"), char)

    def test_overflow_does_not_truncate(self):
        with self.assertRaisesRegex(InputError, "exceeds"):
            Field("x", 5, "right", " ").pack("東京", "utf-8")

    def test_encoding_loss(self):
        with self.assertRaises(InputError):
            Field("x", 4, "right", " ").pack("€", "ascii")
        with self.assertRaises(InputError):
            Field("x", 4, "right", " ").pack("¥", "shift_jis")

    def test_controls_rejected(self):
        field = Field("x", 3, "right", " ")
        for value in ("\n", "\r", "\0"):
            with self.assertRaises(InputError):
                field.pack(value, "utf-8")
            with self.assertRaises(InputError):
                field.unpack(value.encode() + b"  ", "utf-8")

    def test_schema_errors(self):
        for key, value in [
            ("version", True),
            ("version", 2),
            ("encoding", "utf-16"),
            ("separator", []),
            ("extra", 1),
            ("fields", []),
        ]:
            data = config()
            data[key] = value
            with self.subTest(key=key), self.assertRaises(InputError):
                Layout.from_dict(data)
        for key, value in [
            ("width", 0),
            ("width", True),
            ("width", 1048577),
            ("padding", "both"),
            ("pad", "é"),
            ("name", ""),
        ]:
            data = config()
            data["fields"][0][key] = value
            with self.subTest(key=key), self.assertRaises(InputError):
                Layout.from_dict(data)

    def test_duplicate_names(self):
        data = config()
        data["fields"].append(copy.copy(data["fields"][0]))
        with self.assertRaises(InputError):
            Layout.from_dict(data)

    def test_empty_input(self):
        self.assertEqual(list(Layout.from_dict(config()).decode(io.BytesIO())), [])

    def test_seeded_roundtrips(self):
        rng = random.Random(814)
        layout = Layout.from_dict(config())
        for index in range(500):
            value = "".join(rng.choice('abé京😀,"') for _ in range(rng.randrange(4)))
            row = [str(index).zfill(3), value]
            self.assertEqual(list(layout.decode(io.BytesIO(layout.encode(row, 1)))), [row])


class FileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.layout = self.root / "layout.json"
        self.layout.write_text(json.dumps(config()), encoding="utf-8")
        self.source = self.root / "source.csv"
        self.source.write_text('id,text\n001,"a,b"\n002,東京\n', encoding="utf-8")
        self.output = self.root / "records.dat"

    def test_conversion_workflow(self):
        result = convert("encode", self.layout, self.source, self.output)
        self.assertEqual(result["records"], 2)
        decoded = self.root / "back.csv"
        convert("decode", self.layout, self.output, decoded)
        with decoded.open(encoding="utf-8", newline="") as source:
            self.assertEqual(
                list(csv.reader(source)), [["id", "text"], ["001", "a,b"], ["002", "東京"]]
            )

    def test_no_partial_file(self):
        self.source.write_text("id,text\n001,valid\n002," + "X" * 30, encoding="utf-8")
        with self.assertRaises(InputError):
            convert("encode", self.layout, self.source, self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob(".transit-*")), [])

    def test_force_failure_preserves_destination(self):
        self.output.write_bytes(b"original")
        self.source.write_text("wrong,header\n", encoding="utf-8")
        with self.assertRaises(InputError):
            convert("encode", self.layout, self.source, self.output, True)
        self.assertEqual(self.output.read_bytes(), b"original")

    def test_overwrite_and_same_input(self):
        self.output.write_bytes(b"old")
        with self.assertRaises(InputError):
            convert("encode", self.layout, self.source, self.output)
        convert("encode", self.layout, self.source, self.output, True)
        with self.assertRaises(InputError):
            convert("encode", self.layout, self.source, self.source, True)

    def test_atomic_no_clobber_race(self):
        with self.assertRaises(FileExistsError), publish(self.output, [self.source]) as stream:
            stream.write(b"new")
            self.output.write_bytes(b"racing writer")
        self.assertEqual(self.output.read_bytes(), b"racing writer")

    def test_hardlink_alias_rejected(self):
        os.link(self.source, self.output)
        with self.assertRaises(InputError):
            convert("encode", self.layout, self.source, self.output, True)

    def test_duplicate_json_and_size_limit(self):
        for raw in ('{"version":1,"version":1}', " " * 65537):
            self.layout.write_text(raw, encoding="utf-8")
            with self.assertRaises(InputError):
                load_config(self.layout)

    def test_ragged_and_bad_csv(self):
        for body in ("001\n", "001,x,y\n", '001,"unfinished', "\n"):
            self.source.write_text("id,text\n" + body, encoding="utf-8")
            with self.assertRaises((InputError, csv.Error)):
                convert("encode", self.layout, self.source, self.output)
            self.assertFalse(self.output.exists())

    def test_bom_header(self):
        self.source.write_text("id,text\n001,x\n", encoding="utf-8-sig")
        self.assertEqual(convert("encode", self.layout, self.source, self.output)["records"], 1)

    def test_cli_and_version(self):
        command = [sys.executable, "-m", "fixedwidth_transit"]
        version = subprocess.run(command + ["--version"], capture_output=True, text=True)
        self.assertEqual(version.stdout.strip(), "0.1.0")
        args = [
            "encode",
            str(self.source),
            "--layout",
            str(self.layout),
            "--output",
            str(self.output),
        ]
        good = subprocess.run(command + args, capture_output=True, text=True)
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertEqual(json.loads(good.stdout)["records"], 2)
        bad = subprocess.run(command + args, capture_output=True, text=True)
        self.assertEqual(bad.returncode, 2)
        self.assertNotIn("Traceback", bad.stderr)


if __name__ == "__main__":
    unittest.main()
