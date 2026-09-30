"""Rename EverQuest character INI files so the server segment is beta.

Live files look like UI_Name_Server_CLASS.ini, Name_Server_CLASS.ini, and
AT_default_Name_Server_CLASS.ini. Older files may omit the class suffix.
Only the server piece of the filename changes. File contents are not modified.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

CLASS_ABBREVS = frozenset(
    {
        "BER",
        "BRD",
        "BST",
        "CLR",
        "DRU",
        "ENC",
        "MAG",
        "MNK",
        "NEC",
        "PAL",
        "RNG",
        "ROG",
        "SHD",
        "SHM",
        "WAR",
        "WIZ",
    }
)

_TOKEN = re.compile(r"^[A-Za-z0-9]+$")


@dataclass(frozen=True)
class CharacterIni:
    prefix: str
    name: str
    server: str
    cls: str
    extra: str = ""

    @property
    def beta_filename(self) -> str:
        cls = f"_{self.cls}" if self.cls else ""
        extra = f"_{self.extra}" if self.extra else ""
        return f"{self.prefix}{self.name}_beta{cls}{extra}.ini"


def parse_character_ini(filename: str) -> CharacterIni | None:
    """Return the name, server, and class pieces of a character INI, or None."""
    if not filename.lower().endswith(".ini"):
        return None
    stem = filename[:-4]
    lowered = stem.lower()
    if lowered.startswith("at_default_"):
        prefix, rest = stem[:11], stem[11:]
    elif lowered.startswith("ui_"):
        prefix, rest = stem[:3], stem[3:]
    else:
        prefix, rest = "", stem

    parts = rest.split("_")
    extra = ""
    if len(parts) == 2:
        name, server = parts
        cls = ""
    elif len(parts) == 3:
        name, server, cls = parts
        if cls.upper() not in CLASS_ABBREVS:
            return None
    elif len(parts) == 4 and parts[3].lower() == "shrd":
        name, server, cls, extra = parts
        if cls.upper() not in CLASS_ABBREVS:
            return None
    else:
        return None

    if server.lower() == "characters":
        return None
    if not _TOKEN.fullmatch(name) or not _TOKEN.fullmatch(server):
        return None
    if cls and not _TOKEN.fullmatch(cls):
        return None
    if extra and not _TOKEN.fullmatch(extra):
        return None
    return CharacterIni(prefix=prefix, name=name, server=server, cls=cls, extra=extra)


def output_relpath(upload_path: str) -> str | None:
    """Build a zip path for an uploaded file, or None if it is not allowed.

    Accepted inputs:
    - root/UI_Name_Server_CLASS.ini
    - userdata/AT_default_Name_Server_CLASS.ini
    """
    normalized = upload_path.replace("\\", "/").strip()
    if not normalized or normalized.startswith("/"):
        return None
    parts = normalized.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return None

    kind = parts[0].lower()
    rest = parts[1:]
    if kind == "root":
        return _ini_output(rest, folder="")
    if kind == "userdata":
        return _ini_output(rest, folder="userdata")
    return None


def _ini_output(rest: list[str], folder: str) -> str | None:
    if len(rest) != 1:
        return None
    parsed = parse_character_ini(rest[0])
    if parsed is None:
        return None
    filename = parsed.beta_filename
    if folder:
        return f"{folder}/{filename}"
    return filename
