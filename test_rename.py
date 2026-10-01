"""Tests for character INI detection and the rename endpoint."""

from __future__ import annotations

import io
import struct
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path
from werkzeug.datastructures import MultiDict

import app as webapp
from rename import output_relpath, parse_character_ini


class ParseTests(unittest.TestCase):
    def test_ui_persona_file(self) -> None:
        parsed = parse_character_ini("UI_Bob_Vox_WAR.ini")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.beta_filename, "UI_Bob_beta_WAR.ini")
        self.assertEqual(parsed.name, "Bob")
        self.assertEqual(parsed.server, "Vox")
        self.assertEqual(parsed.cls, "WAR")

    def test_hotkey_persona_file(self) -> None:
        parsed = parse_character_ini("Bob_Vox_WAR.ini")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.beta_filename, "Bob_beta_WAR.ini")

    def test_audio_trigger_file(self) -> None:
        parsed = parse_character_ini("AT_default_Bob_Vox_CLR.ini")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.prefix, "AT_default_")
        self.assertEqual(parsed.beta_filename, "AT_default_Bob_beta_CLR.ini")

    def test_hotkey_without_class(self) -> None:
        parsed = parse_character_ini("Bob_Vox.ini")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.beta_filename, "Bob_beta.ini")
        self.assertEqual(parsed.cls, "")

    def test_ui_without_class(self) -> None:
        parsed = parse_character_ini("UI_Bob_Vox.ini")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.beta_filename, "UI_Bob_beta.ini")

    def test_class_and_prefix_case_are_preserved(self) -> None:
        parsed = parse_character_ini("ui_Bob_VOX_war.ini")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.beta_filename, "ui_Bob_beta_war.ini")

    def test_eqclient_is_rejected(self) -> None:
        self.assertIsNone(parse_character_ini("eqclient.ini"))

    def test_ui_default_is_rejected(self) -> None:
        self.assertIsNone(parse_character_ini("UI_Default.ini"))

    def test_bristle_persona_file(self) -> None:
        parsed = parse_character_ini("Bardlub_bristle_BRD.ini")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.beta_filename, "Bardlub_beta_BRD.ini")

    def test_shared_persona_suffix(self) -> None:
        parsed = parse_character_ini("UI_Deflub_bristle_BER_shrd.ini")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.beta_filename, "UI_Deflub_beta_BER_shrd.ini")

    def test_character_list_file_is_rejected(self) -> None:
        self.assertIsNone(parse_character_ini("120chevy_characters.ini"))

    def test_unknown_suffix_is_rejected(self) -> None:
        self.assertIsNone(parse_character_ini("Bob_Vox_NOPE.ini"))

    def test_extra_segments_are_rejected(self) -> None:
        self.assertIsNone(parse_character_ini("Bob_Vox_WAR_extra.ini"))


class OutputPathTests(unittest.TestCase):
    def test_root_and_userdata_paths(self) -> None:
        self.assertEqual(
            output_relpath("root/UI_Bob_Vox_WAR.ini"),
            "UI_Bob_beta_WAR.ini",
        )
        self.assertEqual(
            output_relpath("userdata/Bob_Vox_WAR.ini"),
            "userdata/Bob_beta_WAR.ini",
        )
        self.assertEqual(
            output_relpath("userdata\\AT_default_Bob_Vox_CLR.ini"),
            "userdata/AT_default_Bob_beta_CLR.ini",
        )

    def test_uifiles_are_rejected(self) -> None:
        self.assertIsNone(output_relpath("uifiles\\My UI\\EQUI.xml"))
        self.assertIsNone(output_relpath("uifiles/Default/EQUI.xml"))

    def test_unsafe_paths_are_rejected(self) -> None:
        self.assertIsNone(output_relpath("uifiles/../../secret.txt"))
        self.assertIsNone(output_relpath("root/../UI_Bob_Vox_WAR.ini"))
        self.assertIsNone(output_relpath("root/eqclient.ini"))
        self.assertIsNone(output_relpath("/root/UI_Bob_Vox_WAR.ini"))
        self.assertIsNone(output_relpath("maps/Bob_Vox_WAR.ini"))


class RenameEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = webapp.app.test_client()

    def test_home_page_has_the_controls(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        for text in (
            "Browse Live folder",
            "Download zip",
            "readme.txt",
            "Only character INI files are kept",
            "Leave the others unchecked",
            "https://shakahr.com/everquest-beta/",
        ):
            self.assertIn(text, page)
        for removed in (
            "Browse Beta folder",
            "Copy UIFiles folder",
            "Copy into Beta folder",
            "webkitdirectory",
            "Measure zip sizes",
            "measure-bandwidth",
            "If the zip has a userdata folder",
            "uifiles yourself",
        ):
            self.assertNotIn(removed, page)
        script = self.client.get("/static/app.js")
        try:
            self.assertEqual(script.status_code, 200)
            script_text = script.get_data(as_text=True)
            self.assertIn("*antonius*.ini", page)
            self.assertIn("*xegony*.ini", page)
            self.assertNotIn("*steel*.ini", page)
            self.assertNotIn("*tking*.ini", page)
            self.assertIn("parseCharacterIni", script_text)
            self.assertIn("/pick-folder", script_text)
            self.assertIn("webkitRelativePath", script_text)
            self.assertNotIn("webkitdirectory", script_text)
            self.assertNotIn("measure-bandwidth", script_text)
        finally:
            script.close()

    def test_health(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"ok": True, "localFolder": True})
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_zip_renames_files_and_keeps_bytes(self) -> None:
        ui_bytes = b"[UI]\r\nWindow=1\r\n"
        at_bytes = b"[Audio]\r\nTrigger=1\r\n"
        response = self._post(
            [
                ("root/UI_Bob_Vox_WAR.ini", ui_bytes),
                ("userdata/AT_default_Bob_Vox_WAR.ini", at_bytes),
            ]
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/zip")
        self.assertEqual(response.headers["Cache-Control"], "no-store")

        archive = zipfile.ZipFile(io.BytesIO(response.data))
        readme = archive.read("readme.txt")
        self.assertEqual(
            archive.read("UI_Bob_beta_WAR.ini"),
            ui_bytes,
        )
        self.assertEqual(
            archive.read("userdata/AT_default_Bob_beta_WAR.ini"),
            at_bytes,
        )
        readme_text = readme.decode("utf-8")
        self.assertIn("Close EverQuest", readme_text)
        self.assertIn(r"EverQuest Beta\userdata", readme_text)
        self.assertIn(r"EverQuest\uifiles", readme_text)
        self.assertEqual(
            _local_file_entries(response.data),
            [
                ("UI_Bob_beta_WAR.ini", ui_bytes),
                ("userdata/AT_default_Bob_beta_WAR.ini", at_bytes),
                ("readme.txt", readme),
            ],
        )

    def test_rejected_file_fails_the_request(self) -> None:
        response = self._post(
            [
                ("root/UI_Bob_Vox_WAR.ini", b"ok"),
                ("uifiles/../../secret.txt", b"nope"),
            ]
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Rejected", response.get_json()["error"])
        self.assertNotIn(b"nope", response.data)

    def test_uifiles_upload_is_rejected(self) -> None:
        response = self._post([("uifiles/Default/EQUI.xml", b"<XML>layout</XML>")])
        self.assertEqual(response.status_code, 400)
        self.assertIn("Rejected", response.get_json()["error"])

    def test_non_character_ini_is_rejected(self) -> None:
        response = self._post([("root/eqclient.ini", b"[Client]")])
        self.assertEqual(response.status_code, 400)

    def test_empty_request_is_rejected(self) -> None:
        response = self.client.post("/rename", data={})
        self.assertEqual(response.status_code, 400)

    def _post(self, items: list[tuple[str, bytes]]):
        payload: MultiDict = MultiDict()
        for path, contents in items:
            payload.add("paths", path)
            payload.add("files", (io.BytesIO(contents), "upload.bin"))
        return self.client.post("/rename", data=payload)


class LocalFolderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = webapp.app.test_client()
        webapp._live_root = None
        webapp._live_sources = {}

    def tearDown(self) -> None:
        webapp._live_root = None
        webapp._live_sources = {}

    def test_scan_keeps_character_files_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "UI_Bob_Vox_WAR.ini").write_bytes(b"[UI]")
            (root / "eqclient.ini").write_bytes(b"[Client]")
            (root / "120chevy_characters.ini").write_bytes(b"[Chars]")
            (root / "maps").mkdir()
            (root / "maps" / "UI_Bob_Vox_WAR.ini").write_bytes(b"map")
            (root / "userdata").mkdir()
            (root / "userdata" / "AT_default_Bob_Vox_WAR.ini").write_bytes(b"[Audio]")
            (root / "userdata" / "HB_Bob_Vox_WAR.ini").write_bytes(b"[Hotbar]")

            listed = webapp.remember_live_folder(root)

        sources = [item["source"] for item in listed["files"]]
        self.assertEqual(
            sources,
            [
                "root/UI_Bob_Vox_WAR.ini",
                "userdata/AT_default_Bob_Vox_WAR.ini",
            ],
        )
        self.assertEqual(listed["files"][0]["betaFilename"], "UI_Bob_beta_WAR.ini")

    def test_local_zip_reads_only_the_selected_character_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ui_bytes = b"[UI]\r\nWindow=1\r\n"
            (root / "UI_Bob_Vox_WAR.ini").write_bytes(ui_bytes)
            (root / "eqclient.ini").write_bytes(b"[Client]")
            webapp.remember_live_folder(root)
            response = self.client.post(
                "/rename-local",
                json={"paths": ["root/UI_Bob_Vox_WAR.ini"]},
            )

        self.assertEqual(response.status_code, 200)
        archive = zipfile.ZipFile(io.BytesIO(response.data))
        self.assertEqual(archive.read("UI_Bob_beta_WAR.ini"), ui_bytes)
        self.assertNotIn(b"[Client]", response.data)

    def test_local_zip_rejects_a_file_that_was_not_listed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "UI_Bob_Vox_WAR.ini").write_bytes(b"[UI]")
            webapp.remember_live_folder(root)
            response = self.client.post(
                "/rename-local",
                json={"paths": ["root/eqclient.ini"]},
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Rejected", response.get_json()["error"])


def _local_file_entries(payload: bytes) -> list[tuple[str, bytes]]:
    """Read local zip headers the same way the browser does."""
    entries: list[tuple[str, bytes]] = []
    offset = 0
    while offset + 30 <= len(payload):
        if payload[offset : offset + 4] != b"PK\x03\x04":
            break
        flags, method = struct.unpack_from("<HH", payload, offset + 6)
        comp_size = struct.unpack_from("<I", payload, offset + 18)[0]
        name_len, extra_len = struct.unpack_from("<HH", payload, offset + 26)
        name = payload[offset + 30 : offset + 30 + name_len].decode("utf-8")
        data_start = offset + 30 + name_len + extra_len
        compressed = payload[data_start : data_start + comp_size]
        if flags & 0x8:
            raise AssertionError("zip local header uses a data descriptor")
        if method == 0:
            raw = compressed
        elif method == 8:
            raw = zlib.decompress(compressed, -15)
        else:
            raise AssertionError(f"unexpected zip method {method}")
        entries.append((name, raw))
        offset = data_start + comp_size
    return entries


if __name__ == "__main__":
    unittest.main()
