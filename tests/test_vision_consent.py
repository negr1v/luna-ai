import asyncio
import logging
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from aiohttp import CookieJar, web
from aiohttp.test_utils import TestClient, TestServer

# Import-time storage is isolated too.
test_data = tempfile.TemporaryDirectory()
unittest.addModuleCleanup(test_data.cleanup)
with patch.dict(os.environ, {"LUNA_DATA_DIR": test_data.name}):
    import luna_server as server
for handler in logging.getLogger("luna").handlers:
    if getattr(handler, "baseFilename", "").startswith(test_data.name):
        unittest.addModuleCleanup(handler.close)


class VisionConsentTest(unittest.IsolatedAsyncioTestCase):
    async def test_session_destination_expiry_and_concurrent_consumption(self):
        app = web.Application()
        app.router.add_get("/api/vision/destination", server.handle_vision_destination)
        app.router.add_post("/api/vision/approval", server.handle_vision_approval)
        app.router.add_post("/api/vision", server.handle_vision_scan)
        cfg = {"openrouter_api_key": "test-only"}
        calls = []

        class ProviderResponse:
            status = 200

            async def __aenter__(self):
                await asyncio.sleep(0.02)
                return self

            async def __aexit__(self, *args):
                pass

            async def json(self):
                return {"choices": [{"message": {"content": "Örnek yanıt"}}]}

        def provider_post(_client, url, *, json, **kwargs):
            calls.append((url, json))
            self.assertEqual(url, "https://openrouter.ai/api/v1/chat/completions")
            self.assertFalse(kwargs["allow_redirects"])
            return ProviderResponse()

        async with TestClient(TestServer(app), cookie_jar=CookieJar(unsafe=True)) as client:
            origin = {"Origin": str(client.make_url("/")).rstrip("/")}
            route = {"provider": "openrouter", "model": "openai/gpt-4o"}
            frame = {**route, "image_base64": "dGVzdA=="}
            approval = {**route, "confirmed": True, "allow_paid": True}

            async def post(url, data):
                return await client.request("POST", url, json=data, headers=origin)

            async def token():
                response = await post("/api/vision/approval", approval)
                self.assertEqual(response.status, 200)
                return (await response.json())["approval_token"]

            with (patch.object(server, "load_config", return_value=cfg),
                  patch.object(server.aiohttp.ClientSession, "post", provider_post),
                  patch.object(server, "generate_tts", AsyncMock(return_value=None)) as tts,
                  patch.object(server, "PAID_MODEL_AUTHORIZATIONS", {})):
                self.assertEqual((await post("/api/vision", frame)).status, 403)
                self.assertEqual((await post("/api/vision/approval", approval)).status, 403)
                self.assertEqual((await client.get("/api/vision/destination")).status, 200)
                self.assertEqual((await post("/api/vision", frame)).status, 403)
                self.assertEqual((await post("/api/vision/approval", {**approval, "allow_paid": False})).status, 403)
                expired = await token()
                server.PAID_MODEL_AUTHORIZATIONS[expired]["expires_at"] = 0
                self.assertEqual((await post("/api/vision", {**frame, "approval_token": expired})).status, 403)
                valid = {**frame, "approval_token": await token()}
                self.assertEqual((await post("/api/vision", {**valid, "provider": "groq"})).status, 409)
                replacement = {"provider": "test-alternate", "model": "different-model", "paid": True}
                with patch.object(server, "vision_destination", return_value=replacement):
                    self.assertEqual((await post("/api/vision", valid)).status, 409)
                    self.assertEqual((await post("/api/vision", {**valid, **replacement})).status, 403)
                self.assertEqual((await client.request("POST", "/api/vision", json=valid)).status, 403)
                async with server.aiohttp.ClientSession(cookie_jar=CookieJar(unsafe=True)) as other:
                    async with other.get(client.make_url("/api/vision/destination")) as response:
                        self.assertEqual(response.status, 200)
                    async with other.request("POST", client.make_url("/api/vision"), json=valid, headers=origin) as response:
                        self.assertEqual(response.status, 403)
                cfg.clear()
                cfg["groq_api_key"] = "retired-model-test"
                self.assertEqual((await client.get("/api/vision/destination")).status, 503)
                self.assertEqual((await post("/api/vision", valid)).status, 503)
                self.assertEqual(calls, [])
                cfg["openrouter_api_key"] = "test-only"
                results = await asyncio.gather(post("/api/vision", valid), post("/api/vision", valid))
                self.assertEqual(sorted(r.status for r in results), [200, 403])
                success = next(r for r in results if r.status == 200)
                self.assertEqual((await success.json())["reply"], "Örnek yanıt")
                self.assertEqual((await post("/api/vision", valid)).status, 403)
                self.assertEqual(len(calls), 1)
                self.assertEqual(calls[0][1]["model"], route["model"])
                self.assertEqual(tts.await_count, 1)
                print("Outbound Vision calls: OpenRouter=1, Groq=0; concurrent responses=200,403")


if __name__ == "__main__":
    unittest.main()
