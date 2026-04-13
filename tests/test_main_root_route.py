import sys
import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch

from fastapi.responses import FileResponse, HTMLResponse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main


class MainRootRouteTests(unittest.TestCase):
    def test_ensure_frontend_static_bootstraps_build(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root_dir = Path(tmp_dir)
            frontend_dir = root_dir / "frontend"
            static_dir = root_dir / "static"
            frontend_dir.mkdir()
            static_dir.mkdir()
            (frontend_dir / "package.json").write_text("{}", encoding="utf-8")

            calls = []

            def fake_run(args, cwd=None, check=None):
                calls.append((list(args), cwd, check))
                if args == ["npm", "run", "build"]:
                    (static_dir / "index.html").write_text("<!doctype html>", encoding="utf-8")
                return None

            with (
                patch.object(main, "_ROOT_DIR", str(root_dir)),
                patch.object(main, "_FRONTEND_DIR", str(frontend_dir)),
                patch.object(main, "_static_index", str(static_dir / "index.html")),
                patch.object(main.os.path, "isfile", side_effect=lambda path: Path(path).is_file()),
                patch.object(main.os.path, "isdir", side_effect=lambda path: Path(path).is_dir()),
                patch.object(main.subprocess, "run", side_effect=fake_run),
            ):
                result = main._ensure_frontend_static()

            self.assertTrue(result)
            self.assertEqual(
                calls,
                [
                    (["npm", "install"], str(frontend_dir), True),
                    (["npm", "run", "build"], str(frontend_dir), True),
                ],
            )

    def test_root_returns_diagnostic_page_when_frontend_is_missing(self):
        real_isfile = main.os.path.isfile

        with patch.object(
            main.os.path,
            "isfile",
            side_effect=lambda path: False if path == main._static_index else real_isfile(path),
        ):
            response = main.root()

        self.assertIsInstance(response, HTMLResponse)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Account Manager backend is running", response.body)

    def test_root_serves_frontend_when_static_index_exists(self):
        real_isfile = main.os.path.isfile

        with patch.object(
            main.os.path,
            "isfile",
            side_effect=lambda path: True if path == main._static_index else real_isfile(path),
        ):
            response = main.root()

        self.assertIsInstance(response, FileResponse)
        self.assertEqual(response.path, main._static_index)

    def test_static_asset_routes_resolve_files_inside_static_tree(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root_dir = Path(tmp_dir)
            static_dir = root_dir / "static"
            assets_dir = static_dir / "assets"
            assets_dir.mkdir(parents=True)
            index_path = static_dir / "index.html"
            logo_path = static_dir / "logo.png"
            chunk_path = assets_dir / "index-abc.js"
            index_path.write_text("<!doctype html>", encoding="utf-8")
            logo_path.write_bytes(b"logo")
            chunk_path.write_text("console.log('ok')", encoding="utf-8")

            with (
                patch.object(main, "_static_dir", str(static_dir)),
                patch.object(main, "_static_assets_dir", str(assets_dir)),
                patch.object(main, "_static_index", str(index_path)),
            ):
                logo_response = main._serve_static_asset("logo.png")
                chunk_response = main._serve_static_asset("assets/index-abc.js")
                root_response = main._serve_static_asset("")

            self.assertIsInstance(logo_response, FileResponse)
            self.assertEqual(logo_response.path, str(logo_path))
            self.assertIsInstance(chunk_response, FileResponse)
            self.assertEqual(chunk_response.path, str(chunk_path))
            self.assertIsInstance(root_response, FileResponse)
            self.assertEqual(root_response.path, str(index_path))


if __name__ == "__main__":
    unittest.main()
