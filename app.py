"""Web app that renames EverQuest character files and returns a zip.

Uploaded bytes stay in memory for the request and are not written to disk.
When the page is opened on this computer, the Live folder is listed here and
only character INI files are read.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import zipfile
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file

from rename import is_eqclient_ini, output_relpath, parse_character_ini

MAX_BYTES = 20 * 1024 * 1024
MAX_FILES = 5000

README_TEXT = """\
EverQuest Beta character files
==============================

Close EverQuest before you replace any files.

1. Copy the INI files in this zip (the files next to this readme) into your
   EverQuest Beta folder. Replace files that are already there.

   The usual folder is:
   C:\\Users\\Public\\Daybreak Game Company\\Installed Games\\EverQuest Beta

   eqclient.ini in this zip keeps that name. Copy it into the same Beta
   folder and replace the file that is already there. Other eqclient files
   are not included.

2. If this zip has a userdata folder, copy it into:
   EverQuest Beta\\userdata

   Replace files that are already there. These are your audio-trigger files.
   The server name in each filename has already been changed to beta.

Custom UIs
----------

Custom UI files are not in this zip. If you use a custom UI, copy the Live
folder yourself:

   EverQuest\\uifiles
   into
   EverQuest Beta\\uifiles

Replace the files that are already there.
"""

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_BYTES

_live_root: Path | None = None
_live_sources: dict[str, Path] = {}


class UploadError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health():
    response = jsonify(ok=True, localFolder=_local_folder_available())
    response.headers["Cache-Control"] = "no-store"
    return response


@app.post("/pick-folder")
def pick_folder():
    if not _local_folder_available():
        response = jsonify(error="Folder browsing on this computer is only available at 127.0.0.1.")
        response.headers["Cache-Control"] = "no-store"
        return response, 404
    try:
        chosen = _choose_ini_files()
        if not chosen:
            response = jsonify(cancelled=True)
            response.headers["Cache-Control"] = "no-store"
            return response
        payload = remember_selected_files([Path(item) for item in chosen])
    except UploadError as exc:
        response = jsonify(error=str(exc))
        response.headers["Cache-Control"] = "no-store"
        return response, exc.status
    response = jsonify(payload)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.post("/rename-local")
def rename_local():
    if not _local_folder_available():
        response = jsonify(error="Local rename is only available at 127.0.0.1.")
        response.headers["Cache-Control"] = "no-store"
        return response, 404
    body = request.get_json(silent=True) or {}
    requested = body.get("paths", [])
    if not isinstance(requested, list):
        response = jsonify(error="Select at least one character.")
        response.headers["Cache-Control"] = "no-store"
        return response, 400
    try:
        paths, uploads = _read_local_selection([str(item) for item in requested])
        payload = _build_zip(paths, uploads)
    except UploadError as exc:
        response = jsonify(error=str(exc))
        response.headers["Cache-Control"] = "no-store"
        return response, exc.status
    response = send_file(
        io.BytesIO(payload),
        mimetype="application/zip",
        as_attachment=True,
        download_name="eq-beta-files.zip",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@app.post("/rename")
def rename_files():
    uploads = request.files.getlist("files")
    paths = request.form.getlist("paths")
    try:
        payload = _build_zip(paths, uploads)
    except UploadError as exc:
        response = jsonify(error=str(exc))
        response.headers["Cache-Control"] = "no-store"
        return response, exc.status

    response = send_file(
        io.BytesIO(payload),
        mimetype="application/zip",
        as_attachment=True,
        download_name="eq-beta-files.zip",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@app.errorhandler(413)
def too_large(_error):
    response = jsonify(error="Upload is larger than 20 MB.")
    response.headers["Cache-Control"] = "no-store"
    return response, 413


def _build_zip(paths: list[str], uploads) -> bytes:
    if not paths and not uploads:
        raise UploadError("Select at least one character.")
    if len(paths) != len(uploads):
        raise UploadError("Each file needs a path.")
    if len(paths) > MAX_FILES:
        raise UploadError(f"Too many files. The limit is {MAX_FILES}.")

    rels: list[str] = []
    kept: list = []
    seen: set[str] = set()
    for path, upload in zip(paths, uploads):
        rel = output_relpath(path)
        if rel is None:
            raise UploadError(f"Rejected {_brief(path)}.")
        folded = rel.casefold()
        if folded in seen:
            if folded == "eqclient.ini":
                continue
            raise UploadError(f"More than one file would be named {rel}.")
        seen.add(folded)
        rels.append(rel)
        kept.append(upload)

    buffer = io.BytesIO()
    total = 0
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for rel, upload in zip(rels, kept):
            data = upload.read()
            total += len(data)
            if total > MAX_BYTES:
                raise UploadError("Upload is larger than 20 MB.", status=413)
            archive.writestr(rel, data)
        archive.writestr("readme.txt", README_TEXT.replace("\n", "\r\n").encode("utf-8"))
    app.logger.info("Renamed %s files (%s bytes)", len(rels), total)
    return buffer.getvalue()


def remember_live_folder(folder: Path) -> dict:
    """List character INI files in a Live folder and remember them for the zip."""
    global _live_root, _live_sources
    try:
        root = folder.expanduser().resolve(strict=True)
    except OSError as exc:
        raise UploadError("That folder was not found.") from exc
    if not root.is_dir():
        raise UploadError("That folder was not found.")

    listed, client_name = _scan_character_files(root)
    sources: dict[str, Path] = {}
    for item in listed:
        path = root / item["name"] if item["kind"] == "root" else root / "userdata" / item["name"]
        sources[item["source"]] = path
    eqclient = None
    if client_name:
        eqclient = f"root/{client_name}"
        sources[eqclient] = root / client_name
    _live_root = root
    _live_sources = sources
    app.logger.info("Listed %s character INI files in %s", len(listed), root.name)
    return {"folder": str(root), "name": root.name, "files": listed, "eqclient": eqclient}


def _scan_character_files(root: Path) -> tuple[list[dict], str | None]:
    found = _scan_one_directory(root, "root")
    client_name = _eqclient_name(root)
    userdata = root / "userdata"
    if userdata.is_dir():
        found.extend(_scan_one_directory(userdata, "userdata"))
    found.sort(
        key=lambda item: (
            item["character"].casefold(),
            item["server"].casefold(),
            item["kind"],
            item["name"].casefold(),
        )
    )
    return found, client_name


def _eqclient_name(folder: Path) -> str | None:
    try:
        children = list(folder.iterdir())
    except OSError as exc:
        raise UploadError(f"Could not read {folder.name}.") from exc
    for path in children:
        if path.is_file() and is_eqclient_ini(path.name):
            return path.name
    return None


def _scan_one_directory(folder: Path, kind: str) -> list[dict]:
    found: list[dict] = []
    try:
        children = list(folder.iterdir())
    except OSError as exc:
        raise UploadError(f"Could not read {folder.name}.") from exc
    for path in children:
        if not path.is_file():
            continue
        parsed = parse_character_ini(path.name)
        if parsed is None or parsed.server.lower() == "beta":
            continue
        found.append(
            {
                "kind": kind,
                "name": path.name,
                "source": f"{kind}/{path.name}",
                "betaFilename": parsed.beta_filename,
                "character": parsed.name,
                "server": parsed.server,
                "cls": parsed.cls,
            }
        )
    return found


def _allowed_live_file(filename: str) -> bool:
    return parse_character_ini(filename) is not None or is_eqclient_ini(filename)


def _read_local_selection(requested: list[str]) -> tuple[list[str], list[_BytesUpload]]:
    if _live_root is None or not _live_sources:
        raise UploadError("Choose the Live folder first.")
    if not requested:
        raise UploadError("Select at least one character.")
    paths: list[str] = []
    uploads: list[_BytesUpload] = []
    for source in requested:
        allowed = _live_sources.get(source)
        if allowed is None:
            raise UploadError(f"Rejected {_brief(source)}.")
        try:
            file_path = allowed.resolve(strict=True)
            file_path.relative_to(_live_root)
        except (OSError, ValueError) as exc:
            raise UploadError(f"Rejected {_brief(source)}.") from exc
        if not file_path.is_file() or not _allowed_live_file(file_path.name):
            raise UploadError(f"Rejected {_brief(source)}.")
        paths.append(source)
        uploads.append(_BytesUpload(file_path.read_bytes()))
    return paths, uploads


def remember_selected_files(paths: list[Path]) -> dict:
    """Keep the selected character INI files and one eqclient.ini for the zip."""
    global _live_root, _live_sources
    resolved: list[Path] = []
    for path in paths:
        try:
            file_path = path.expanduser().resolve(strict=True)
        except OSError:
            continue
        if file_path.is_file():
            resolved.append(file_path)
    if not resolved:
        raise UploadError("No character INI files found.")

    roots: list[Path] = []
    for file_path in resolved:
        parent = file_path.parent
        roots.append(parent.parent if parent.name.casefold() == "userdata" else parent)
    try:
        root = Path(os.path.commonpath(str(item) for item in roots))
    except ValueError as exc:
        raise UploadError("Choose INI files from one EverQuest folder.") from exc

    listed: list[dict] = []
    sources: dict[str, Path] = {}
    eqclient = None
    for file_path in resolved:
        parent = file_path.parent
        kind = "userdata" if parent.name.casefold() == "userdata" else "root"
        if is_eqclient_ini(file_path.name):
            if kind != "root" or eqclient is not None:
                continue
            eqclient = f"root/{file_path.name}"
            sources[eqclient] = file_path
            continue
        parsed = parse_character_ini(file_path.name)
        if parsed is None or parsed.server.lower() == "beta":
            continue
        source = f"{kind}/{file_path.name}"
        if source in sources:
            continue
        sources[source] = file_path
        listed.append(
            {
                "kind": kind,
                "name": file_path.name,
                "source": source,
                "betaFilename": parsed.beta_filename,
                "character": parsed.name,
                "server": parsed.server,
                "cls": parsed.cls,
            }
        )
    if not listed:
        raise UploadError("No character INI files found.")
    listed.sort(
        key=lambda item: (
            item["character"].casefold(),
            item["server"].casefold(),
            item["kind"],
            item["name"].casefold(),
        )
    )
    _live_root = root
    _live_sources = sources
    app.logger.info("Listed %s selected character INI files in %s", len(listed), root.name)
    return {"folder": str(root), "name": root.name, "files": listed, "eqclient": eqclient}


def _choose_ini_files() -> list[str] | None:
    initial = r"D:\Everquest" if os.path.isdir(r"D:\Everquest") else ""
    code = """
import sys
import tkinter as tk
from tkinter import filedialog
initial = sys.argv[1]
root = tk.Tk()
root.withdraw()
try:
    root.attributes("-topmost", True)
except tk.TclError:
    pass
path = filedialog.askopenfilenames(
    title="Select INI files",
    initialdir=initial or None,
    filetypes=[("INI File", "*.ini")],
    parent=root,
)
root.destroy()
sys.stdout.write("\\n".join(path))
"""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run(
            [sys.executable, "-c", code, initial],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
            creationflags=flags,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise UploadError("The folder dialog was left open too long.") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or "").strip() or "Could not open the folder dialog."
        raise UploadError(detail)
    chosen = [line for line in completed.stdout.splitlines() if line.strip()]
    if not chosen:
        return None
    return chosen


def _local_folder_available() -> bool:
    if os.environ.get("RENDER"):
        return False
    host = request.host.split(":")[0].lower()
    remote = request.remote_addr or ""
    return host in {"127.0.0.1", "localhost", "::1"} and remote in {"127.0.0.1", "::1"}


class _BytesUpload:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


def _brief(path: str) -> str:
    cleaned = " ".join(path.replace("\\", "/").split())
    if len(cleaned) > 180:
        return cleaned[:180] + "..."
    return cleaned or "(empty path)"


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
