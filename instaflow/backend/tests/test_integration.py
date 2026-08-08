import os
import sys
import json
import urllib.request
import urllib.parse
import concurrent.futures
import pytest
from backend.app.core.config import settings
from backend.app.models.response import ErrorCode

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_URL = f"http://localhost:{settings.PORT}"

# Test URLs covering all media types
TEST_REEL_URL = "https://www.instagram.com/reel/DZZIsENhLTQ/"
TEST_CAROUSEL_URL = "https://www.instagram.com/p/DbqaXCyFO1S/"
TEST_SINGLE_PHOTO_URL = "https://www.instagram.com/p/DbXbYBxu_GX/"
TEST_INVALID_URL = "https://www.instagram.com/invalid_path_123456789/"

class TestInstaFlowBackendIntegration:

    def test_01_health_endpoint(self):
        """Test /health endpoint status, cookies, and FFmpeg binary presence."""
        resp = urllib.request.urlopen(f"{BASE_URL}/health")
        assert resp.status == 200
        data = json.loads(resp.read().decode('utf-8'))
        assert data["status"] == "ok"
        assert data["cookies_active"] is True
        assert data["ffmpeg_available"] is True

    def test_02_analyze_reel(self):
        """Test /api/v1/analyze for an Instagram Reel."""
        req = urllib.request.Request(
            f"{BASE_URL}/api/v1/analyze",
            data=json.dumps({"url": TEST_REEL_URL}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        resp = urllib.request.urlopen(req)
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["success"] is True
        assert data["type"] == "reel"
        assert len(data["items"]) >= 1
        assert data["items"][0]["is_video"] is True

    def test_03_analyze_carousel(self):
        """Test /api/v1/analyze for an Instagram Photo Carousel."""
        req = urllib.request.Request(
            f"{BASE_URL}/api/v1/analyze",
            data=json.dumps({"url": TEST_CAROUSEL_URL}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        resp = urllib.request.urlopen(req)
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["success"] is True
        assert data["type"] in ["carousel", "single"]
        assert len(data["items"]) >= 2

    def test_04_analyze_single_photo(self):
        """Test /api/v1/analyze for a Single Photo Post."""
        req = urllib.request.Request(
            f"{BASE_URL}/api/v1/analyze",
            data=json.dumps({"url": TEST_SINGLE_PHOTO_URL}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        resp = urllib.request.urlopen(req)
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["success"] is True

    def test_05_analyze_invalid_url(self):
        """Test /api/v1/analyze with an invalid URL format for typed 400 error."""
        req = urllib.request.Request(
            f"{BASE_URL}/api/v1/analyze",
            data=json.dumps({"url": "https://not-instagram.com/abc"}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req)
        assert exc_info.value.code == 400

    def test_06_download_reel_stream(self):
        """Test /api/v1/download streaming Reel video with proper MIME type."""
        query = urllib.parse.urlencode({"url": TEST_REEL_URL})
        resp = urllib.request.urlopen(f"{BASE_URL}/api/v1/download?{query}")
        assert resp.status == 200
        assert resp.headers.get("Content-Type") == "video/mp4"
        assert "attachment" in resp.headers.get("Content-Disposition", "")
        
        data = resp.read()
        assert len(data) > 100000  # Should be substantial size for video

    def test_07_download_carousel_item_stream(self):
        """Test /api/v1/download streaming a photo item with proper MIME type."""
        query = urllib.parse.urlencode({"url": TEST_CAROUSEL_URL, "item": 1})
        resp = urllib.request.urlopen(f"{BASE_URL}/api/v1/download?{query}")
        assert resp.status == 200
        assert resp.headers.get("Content-Type") in ["image/jpeg", "image/webp", "image/png"]
        
        data = resp.read()
        assert len(data) > 1000  # Should be valid photo size

    def test_08_concurrent_client_downloads(self):
        """Test concurrent requests from multiple simultaneous clients."""
        def download_job(url):
            q = urllib.parse.urlencode({"url": url})
            r = urllib.request.urlopen(f"{BASE_URL}/api/v1/download?{q}")
            return r.status, len(r.read())

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(download_job, TEST_REEL_URL),
                executor.submit(download_job, TEST_CAROUSEL_URL)
            ]
            results = [f.result() for f in futures]
            for status, length in results:
                assert status == 200
                assert length > 0

    def test_09_temp_disk_cleanup(self):
        """Verify that temporary task directories are purged after all downloads complete."""
        import time
        time.sleep(2)  # Allow background cleanup tasks to finalize
        temp_dir = settings.TEMP_DIR
        if os.path.exists(temp_dir):
            entries = os.listdir(temp_dir)
            orphans = [e for e in entries if os.path.isdir(os.path.join(temp_dir, e))]
            assert len(orphans) == 0, f"Found orphaned temp task directories: {orphans}"
