# fixedwidth-transit

Move legacy fixed-width exports to UTF-8 CSV and back using **byte widths**, an
explicit encoding and one small layout file. Multibyte names must not shift the
next field. Overlong values and split characters are errors, never truncations.

Python 3.11+, MIT, no runtime dependencies, network calls or type inference.
Useful for repeatable batch handoffs with a documented fixed record layout.
[中文说明](README.zh-CN.md)

## Install and try

```sh
git clone https://github.com/KanadeK/fixedwidth-transit.git
cd fixedwidth-transit
python -m venv .venv
```

Activate with `source .venv/bin/activate` on Linux/macOS or
`.venv\Scripts\Activate.ps1` in Windows PowerShell, then:

```sh
python -m pip install .
fixedwidth-transit encode examples/people.csv --layout examples/layout.json --output people.dat
fixedwidth-transit decode people.dat --layout examples/layout.json --output roundtrip.csv
```

Both commands exit 0 and report 2 records. Each encoded record is 20 bytes plus
LF, even though `東京` is two characters and six UTF-8 bytes. `roundtrip.csv`
contains the original cell values, including `0001`. These files are ordinary
local output; delete `people.dat` and `roundtrip.csv` after the demo. Repeating a
command refuses to overwrite its output; `--force` replaces it only on success.
`python -m fixedwidth_transit` is the equivalent module entry point.

A release wheel can also be installed with `python -m pip install <wheel-file>`.
This package is not published on PyPI. Uninstall using
`python -m pip uninstall fixedwidth-transit`; remove your virtual environment
when finished. No settings or caches are created by the tool.

## Layout contract

```json
{
  "version": 1,
  "encoding": "utf-8",
  "separator": "lf",
  "fields": [
    {"name": "id", "width": 4, "padding": "none"},
    {"name": "name", "width": 12, "padding": "right"},
    {"name": "code", "width": 4, "padding": "left"}
  ]
}
```

- Fields are contiguous in listed order. `width` counts encoded bytes, excluding
  the record separator. Gaps must be represented as explicit fields.
- `padding` is `right` (default), `left` or `none`; `pad` defaults to a space and
  must be one printable ASCII character. Declared padding is stripped when
  decoding and restored when encoding. With `none`, values must fill the width
  exactly and no characters are stripped.
- CSV values ending/starting with the padding character on the stripped side
  are rejected as ambiguous. Use `none` when those characters are meaningful.
  All-padding fields decode to an empty string. No NULL or numeric semantics.
- Encodings: `utf-8`, `ascii`, `latin-1`, `cp1252`, `shift_jis`, `cp932` only.
  Decode/encode equivalence is checked to reject non-round-tripping codec mappings.
- Separators: `lf`, `crlf` or `none` (concatenated fixed-size records). Decode
  permits a final record without its separator. Encode always writes the selected
  separator, including after the last record. Mixed separators are rejected.
- CSV is comma-delimited, double-quote escaped, UTF-8 (an input BOM is allowed).
  The header must exactly match the layout order. Quotes and commas in fields
  work. CR, LF and NUL inside fields are rejected. No blank records are skipped.
- Unknown/duplicate JSON keys, duplicate or empty names, ragged rows, invalid
  encoding, truncated records and overflow fail. Schema size is limited to
  64 KiB and JSON nesting to 128 levels; record width and individual CSV field
  length to 1 MiB; 1–1024 columns.

For example, changing the name width to 5 makes `東京` fail: its UTF-8 bytes
cannot fit. No output is published, including when earlier records were valid.

## Operational behavior

Exit 0 means conversion succeeded; exit 2 means an input, usage or I/O error.
Success prints a JSON summary to stdout, errors a JSON diagnostic to stderr
(argparse usage errors are text). Record/column positions are one-based;
diagnostics do not echo cell contents.

Data streams one record at a time into a temporary file beside the output.
Successful conversion publishes with an atomic hard link (no overwrite) or
atomic replacement (`--force`). A filesystem supporting hard links is required
for default publication; unsupported filesystems fail without publishing. Input
and schema paths, including existing hard-link aliases, cannot be output paths.
Outputs that are symlinks are rejected. Use a trusted output directory and static
inputs; concurrently modified inputs and hostile directory races are out of scope.
A killed process may leave `.transit-*.tmp`; remove only such files from your
own interrupted jobs. This is not a crash-durable transaction across directories.

## Scope and alternatives

[csvkit in2csv](https://csvkit.readthedocs.io/en/latest/scripts/in2csv.html) is a
better fit for broad tabular imports. [pandas read_fwf](https://pandas.pydata.org/docs/reference/api/pandas.read_fwf.html)
fits dataframe analysis; [evologi/fixed-width](https://github.com/evologi/fixed-width)
provides a configurable JavaScript library. This tool focuses on a byte layout
shared by both conversion directions and refusing lossy writes.

Version 0.1.1 does not parse COBOL copybooks, packed decimals, EBCDIC, UTF-16,
mixed record types, compression, remote URLs or stdin. It does not infer layouts,
sanitize spreadsheet formulas or preserve CSV quoting/line-ending style. Fixed
record padding follows the declared policy, not the unknowable original intent.

## Development

```sh
python -m pip install -e . build==1.6.1 ruff==0.17.2
python -m unittest discover -s tests -v
python -m ruff check .
python -m ruff format --check .
python -m build
```

Tests cover byte layouts, Unicode/codec boundaries, 500 seeded round trips,
malformed input, CLI use, no-clobber races and rollback. CI runs the same suite
on Python 3.11/3.13 across Linux, Windows and macOS. CI never commits files.
