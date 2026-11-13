"""Strict Spectre PSF-ASCII operating-point reader for the HW09 BSIM4 MOSes.

Field names and order come from the file's TYPE/TYPES STRUCT declaration.
Numeric VALUE records must match that declaration exactly. Nonfinite values
are omitted with an explicit warning, rather than converted into plausible
operating-point numbers. No simulator or PDK database is modified.
"""
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
import warnings

_TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|[()]|[^\s()"]+')
_NUMBER = re.compile(r'[-+]?(?:(?:\d+(?:\.\d*)?|\.\d+)(?:[eEdD][-+]?\d+)?|nan|inf(?:inity)?)', re.I)
_REQUIRED = {"id", "gm", "gds", "vgs", "vds", "vth", "vdsat", "region"}


@dataclass(frozen=True)
class _Token:
    value: str
    quoted: bool
    line: int


def _tokens(text, first_line=1):
    output = []
    previous = 0
    line = first_line
    for match in _TOKEN.finditer(text):
        gap = text[previous:match.start()]
        if gap.strip():
            raise ValueError("Unrecognized PSF text near line %s" % line)
        line += gap.count("\n")
        raw = match.group()
        quoted = raw.startswith('"')
        if quoted:
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError("Invalid quoted PSF string near line %s" % line) from exc
        else:
            value = raw
        output.append(_Token(value, quoted, line))
        line += raw.count("\n")
        previous = match.end()
    if text[previous:].strip():
        raise ValueError("Unrecognized trailing PSF text")
    return output


class _Reader:
    def __init__(self, tokens, context):
        self.tokens = tokens
        self.index = 0
        self.context = context

    def peek(self):
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def take(self, expected=None, quoted=None):
        token = self.peek()
        if token is None:
            raise ValueError("Truncated PSF %s" % self.context)
        if expected is not None and (token.quoted or token.value != expected):
            raise ValueError("Expected %s in PSF %s at line %s, found %r" %
                             (expected, self.context, token.line, token.value))
        if quoted is not None and token.quoted != quoted:
            raise ValueError("Unexpected token form in PSF %s at line %s" % (self.context, token.line))
        self.index += 1
        return token

    def group(self):
        self.take("(")
        depth = 1
        while depth:
            token = self.take()
            if not token.quoted:
                if token.value == "(":
                    depth += 1
                elif token.value == ")":
                    depth -= 1

    def properties(self):
        self.take("PROP")
        self.group()


def _read_types(text, first_line):
    reader = _Reader(_tokens(text, first_line), "type declarations")
    types = {}
    while reader.peek() is not None:
        typename = reader.take(quoted=True).value
        reader.take("STRUCT")
        reader.take("(")
        fields = []
        seen = set()
        while reader.peek() is not None and reader.peek().value != ")":
            field = reader.take(quoted=True).value
            if field in seen:
                raise ValueError("Duplicate field %s in PSF type %s" % (field, typename))
            seen.add(field)
            numeric_type = reader.take(quoted=False).value
            if numeric_type not in {"FLOAT", "INT"}:
                raise ValueError("Unsupported PSF field type %s for %s.%s" % (numeric_type, typename, field))
            width = reader.take(quoted=False).value
            if width not in {"DOUBLE", "SINGLE", "BYTE", "SHORT", "LONG", "INT"}:
                raise ValueError("Unsupported PSF numeric width %s" % width)
            reader.properties()
            fields.append((field, numeric_type))
        reader.take(")")
        reader.properties()
        if typename in types:
            raise ValueError("Duplicate PSF type declaration: " + typename)
        if not fields:
            raise ValueError("Empty PSF type declaration: " + typename)
        types[typename] = fields
    return types


def read_operating_points(path):
    """Return {MOS_instance: {field_name: finite_number}} from dcOpInfo.info.

    BSIM4 records are selected by their declared type, including hierarchical
    instance names. Other declared device records are count-validated but not
    returned. A field such as ``id`` is never guessed from a fixed array index.
    Integer fields remain integers, including the numeric ``region`` code;
    this parser does not invent a textual operating-region interpretation.
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="strict")
    type_marks = list(re.finditer(r"(?m)^TYPES?\s*$", text))
    value_marks = list(re.finditer(r"(?m)^VALUE\s*$", text))
    if len(type_marks) != 1 or len(value_marks) != 1:
        raise ValueError("Expected exactly one TYPE/TYPES and one VALUE section in " + str(path))
    type_mark, value_mark = type_marks[0], value_marks[0]
    if type_mark.end() >= value_mark.start():
        raise ValueError("PSF VALUE section precedes the type declaration")
    types = _read_types(text[type_mark.end():value_mark.start()], text[:type_mark.end()].count("\n") + 1)
    if "bsim4" not in types:
        raise ValueError("No bsim4 STRUCT declaration in " + str(path))
    missing = _REQUIRED - {field for field, _ in types["bsim4"]}
    if missing:
        raise ValueError("BSIM4 declaration lacks required operating-point fields: " + ", ".join(sorted(missing)))
    reader = _Reader(_tokens(text[value_mark.end():], text[:value_mark.end()].count("\n") + 1), "instance values")
    points, omitted, instances = {}, {}, set()
    while reader.peek() is not None and reader.peek().value != "END":
        instance = reader.take(quoted=True).value
        typename = reader.take(quoted=True).value
        if instance in instances:
            raise ValueError("Duplicate PSF instance: " + instance)
        instances.add(instance)
        if typename not in types:
            raise ValueError("Undeclared PSF instance type %s for %s" % (typename, instance))
        reader.take("(")
        values = []
        while reader.peek() is not None and reader.peek().value != ")":
            token = reader.take(quoted=False)
            if not _NUMBER.fullmatch(token.value):
                raise ValueError("Invalid numeric value for %s at line %s: %r" % (instance, token.line, token.value))
            values.append(float(token.value.replace("D", "e").replace("d", "e")))
        reader.take(")")
        reader.properties()
        fields = types[typename]
        if len(values) != len(fields):
            raise ValueError("PSF field/value count mismatch for %s (%s): %s declared, %s values" %
                             (instance, typename, len(fields), len(values)))
        record = {}
        for (field, numeric_type), value in zip(fields, values):
            if not math.isfinite(value):
                if typename == "bsim4":
                    omitted.setdefault(instance, []).append(field)
                continue
            if numeric_type == "INT":
                if not value.is_integer():
                    raise ValueError("Nonintegral PSF integer field %s.%s: %s" % (instance, field, value))
                value = int(value)
            record[field] = value
        if typename == "bsim4":
            points[instance] = record
    reader.take("END")
    if reader.peek() is not None:
        raise ValueError("Unexpected PSF data after END")
    if not points:
        raise ValueError("No BSIM4 MOS operating-point instances in " + str(path))
    if omitted:
        detail = "; ".join(name + ": " + ", ".join(fields) for name, fields in sorted(omitted.items()))
        warnings.warn("Omitted nonfinite BSIM4 operating-point values from %s (%s)" % (path.name, detail),
                      RuntimeWarning, stacklevel=2)
    return points
