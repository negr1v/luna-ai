"""
openluna_bridge.py
LUNA-AI ve OpenLuna Modülleri Arasındaki API ve Entegrasyon Köprüsü.

Bu modül:
- `openluna_executor` (Python CodeAct)
- `openluna_researcher` (Deep Research)
- `openluna_digest` (Morning Digest)

bileşenlerini tek bir çatı altında birleştirir ve aiohttp (luna_server.py)
uyumlu handler'lar sunar.
"""

from __future__ import annotations

import json
from aiohttp import web
from openluna_executor import OpenLunaExecutor
from openluna_researcher import OpenLunaResearcher
from openluna_digest import OpenLunaDigest

executor = OpenLunaExecutor(timeout_sec=15)
researcher = OpenLunaResearcher()
digest = OpenLunaDigest()

async def handle_openluna_execute(request: web.Request) -> web.Response:
    """
    POST /api/openluna/execute
    JSON gövdesi: {"code": "print('hello')"} veya {"text": "```python\nprint(1+1)\n```"}
    """
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"success": False, "error": "Geçersiz JSON"}, status=400)

    code = data.get("code")
    text = data.get("text")

    if code:
        res = executor.execute_code(code)
    elif text:
        res = executor.run_agent_turn(text)
        if res is None:
            return web.json_response({"success": False, "error": "Metin içinde python kodu bulunamadı."}, status=400)
    else:
        return web.json_response({"success": False, "error": "'code' veya 'text' alanı gereklidir."}, status=400)

    return web.json_response(res)


async def handle_openluna_research(request: web.Request) -> web.Response:
    """
    POST /api/openluna/research
    JSON gövdesi: {"topic": "araştırma konusu"}
    """
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"success": False, "error": "Geçersiz JSON"}, status=400)

    topic = data.get("topic")
    if not topic:
        return web.json_response({"success": False, "error": "'topic' alanı gereklidir."}, status=400)

    report = researcher.generate_research_report(topic)
    return web.json_response({
        "success": True,
        "topic": topic,
        "report": report
    })


async def handle_openluna_digest(request: web.Request) -> web.Response:
    """
    GET /api/openluna/digest
    Sabah brifingini sesli metin (TTS) ve görsel markdown rapor olarak döner.
    """
    spoken = digest.generate_spoken_briefing()
    report = digest.generate_markdown_report()
    data = digest.collect_digest_data()

    return web.json_response({
        "success": True,
        "spoken_text": spoken,
        "markdown_report": report,
        "data": data
    })


def register_openluna_routes(app: web.Application) -> None:
    """luna_server.py aiohttp uygulamasına OpenLuna rotalarını ekler."""
    app.router.add_post("/api/openluna/execute", handle_openluna_execute)
    app.router.add_post("/api/openluna/research", handle_openluna_research)
    app.router.add_get("/api/openluna/digest", handle_openluna_digest)
    print("[OpenLuna Bridge] Rotalar başarıyla kaydedildi: /api/openluna/(execute|research|digest)")


if __name__ == "__main__":
    app = web.Application()
    register_openluna_routes(app)
    print("OpenLuna Bridge tekil çalıştırma testi başarılı.")
