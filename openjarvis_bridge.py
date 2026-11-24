"""
openjarvis_bridge.py
ACCIO-JARVIS ve OpenJarvis Modülleri Arasındaki API ve Entegrasyon Köprüsü.

Bu modül:
- Python CodeAct route (disabled until an OS-level sandbox is available)
- `openjarvis_researcher` (Deep Research)
- `openjarvis_digest` (Morning Digest)

bileşenlerini tek bir çatı altında birleştirir ve aiohttp (jarvis_server.py)
uyumlu handler'lar sunar.
"""

from __future__ import annotations

from aiohttp import web
from openjarvis_researcher import OpenJarvisResearcher
from openjarvis_digest import OpenJarvisDigest

researcher = OpenJarvisResearcher()
digest = OpenJarvisDigest()

async def handle_openjarvis_execute(request: web.Request) -> web.Response:
    """
    POST /api/openjarvis/execute
    JSON gövdesi: {"code": "print('hello')"} veya {"text": "```python\nprint(1+1)\n```"}
    """
    return web.json_response({
        "success": False,
        "error_code": "PYTHON_EXECUTION_DISABLED",
        "error": "Genel Python yürütme, işletim sistemi düzeyinde sandbox sağlanana kadar devre dışıdır.",
    }, status=501)


async def handle_openjarvis_research(request: web.Request) -> web.Response:
    """
    POST /api/openjarvis/research
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


async def handle_openjarvis_digest(request: web.Request) -> web.Response:
    """
    GET /api/openjarvis/digest
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


def register_openjarvis_routes(app: web.Application) -> None:
    """jarvis_server.py aiohttp uygulamasına OpenJarvis rotalarını ekler."""
    app.router.add_post("/api/openjarvis/execute", handle_openjarvis_execute)
    app.router.add_post("/api/openjarvis/research", handle_openjarvis_research)
    app.router.add_get("/api/openjarvis/digest", handle_openjarvis_digest)
    print("[OpenJarvis Bridge] Rotalar başarıyla kaydedildi: /api/openjarvis/(execute|research|digest)")


if __name__ == "__main__":
    app = web.Application()
    register_openjarvis_routes(app)
    print("OpenJarvis Bridge tekil çalıştırma testi başarılı.")
