import os
import sys
import unittest
import tempfile
import sqlite3

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from gateway.utils import fix_location_header, build_upstream_headers
from health_doctor import check_sqlite_integrity
from starlette.requests import Request

try:
    from tg_streamer import parse_media_type
    HAS_TG_STREAMER = True
except ImportError:
    HAS_TG_STREAMER = False


class TestGatewayUtils(unittest.TestCase):
    def test_fix_location_header(self):
        loc1 = fix_location_header("http://127.0.0.1:20128/dashboard", default_prefix="")
        self.assertNotIn(":20128", loc1)

        loc2 = fix_location_header("/login", default_prefix="/omniroute")
        self.assertTrue(loc2.startswith("/omniroute"))

    def test_build_upstream_headers(self):
        scope = {
            "type": "http",
            "headers": [
                (b"host", b"localhost"),
                (b"transfer-encoding", b"chunked"),
                (b"authorization", b"Bearer test-key"),
                (b"x-custom-header", b"value"),
            ],
            "client": ("127.0.0.1", 12345),
        }
        req = Request(scope)
        clean = build_upstream_headers(req)
        lower_clean = {k.lower(): v for k, v in clean.items()}
        self.assertNotIn("transfer-encoding", lower_clean)
        self.assertEqual(lower_clean.get("authorization"), "Bearer test-key")
        self.assertEqual(lower_clean.get("x-custom-header"), "value")


@unittest.skipUnless(HAS_TG_STREAMER, "tg_streamer dependencies not present")
class TestMediaParser(unittest.TestCase):
    def test_parse_media_type_movie(self):
        is_tv, title, show_name, season, episode = parse_media_type("Inception.2010.1080p.mp4")
        self.assertFalse(is_tv)
        self.assertIn("Inception", title)

    def test_parse_media_type_tv(self):
        is_tv, title, show_name, season, episode = parse_media_type("Breaking.Bad.S02E05.720p.mkv")
        self.assertTrue(is_tv)
        self.assertEqual(season, 2)
        self.assertEqual(episode, 5)


class TestHealthDoctor(unittest.TestCase):
    def test_check_sqlite_integrity_healthy(self):
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            conn = sqlite3.connect(tmp_path)
            conn.execute("CREATE TABLE test (id INT);")
            conn.commit()
            conn.close()

            self.assertTrue(check_sqlite_integrity(tmp_path))
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_check_sqlite_integrity_missing(self):
        self.assertTrue(check_sqlite_integrity("/path/does/not/exist.sqlite"))


if __name__ == "__main__":
    unittest.main()
