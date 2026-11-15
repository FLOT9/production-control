import importlib
from pathlib import Path
from unittest import TestCase, skipUnless
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.core.config import settings


@skipUnless(
    (Path(__file__).resolve().parents[2] / "frontend/public").is_dir(),
    "Local frontend is optional",
)
class LocalFrontendTests(TestCase):
    def test_local_ui_and_api_share_origin_without_exposing_env(self):
        from src import main

        try:
            with (
                patch.object(settings, "assistant_local_enabled", True),
                patch.object(settings, "rate_limit_enabled", False),
            ):
                application = importlib.reload(main).app
                client = TestClient(
                    application,
                    base_url="http://127.0.0.1",
                    client=("127.0.0.1", 50000),
                )
                self.addCleanup(client.close)
                self.assertEqual(client.get("/").status_code, 200)
                js = client.get("/assistant.js")
                self.assertEqual(js.status_code, 200)
                self.assertIn('fetch("/api/v1/assistant/ask"', js.text)
                self.assertNotIn("X-API-Key", js.text)
                self.assertNotIn("GIGACHAT_AUTH_KEY", js.text)
                self.assertEqual(client.get("/health").json(), {"status": "ok"})
                for path in ("/.env", "/src/core/config.py", "/api/v1/missing"):
                    self.assertEqual(client.get(path).status_code, 404)
        finally:
            importlib.reload(main)

    def test_ui_is_not_mounted_when_local_mode_is_disabled(self):
        from src import main

        try:
            with patch.object(settings, "assistant_local_enabled", False):
                application = importlib.reload(main).app
                self.assertFalse(
                    any(
                        getattr(route, "name", None) == "frontend"
                        for route in application.routes
                    )
                )
        finally:
            importlib.reload(main)
