"""Loopback-only Turkish speech recognition. Audio stays in memory."""

import asyncio
from importlib.util import find_spec
from ipaddress import ip_address
import json
from pathlib import Path
import shutil

from aiohttp import web

MODEL_PATH = Path(__file__).resolve().parent / "models" / "vosk-model-small-tr-0.3"
_model = None
_session = asyncio.Lock()
MAX_AUDIO_BYTES = 1024 * 1024
FORMATS = {"audio/webm": "matroska", "audio/ogg": "ogg", "audio/mp4": "mov", "audio/wav": "wav"}


def ready():
    return bool(shutil.which("ffmpeg")) and find_spec("vosk") is not None and any((MODEL_PATH / relative).is_file() for relative in ("final.mdl", "am/final.mdl"))


def check_local(request):
    if request.url.host not in {"localhost", "127.0.0.1", "::1"}:
        raise web.HTTPForbidden()
    origin = request.headers.get("Origin")
    if not request.remote or not ip_address(request.remote).is_loopback:
        raise web.HTTPForbidden()
    if origin and origin != f"{request.scheme}://{request.host}":
        raise web.HTTPForbidden()


async def status(request):
    check_local(request)
    return web.json_response({"ready": ready(), "engine": "vosk", "language": "tr"})


def make_recognizer():
    from vosk import KaldiRecognizer, Model, SetLogLevel

    global _model
    if _model is None:
        SetLogLevel(-1)
        _model = Model(str(MODEL_PATH))
    return KaldiRecognizer(_model, 16000)


def recognize(pcm):
    recognizer = make_recognizer()
    recognizer.AcceptWaveform(pcm)
    return json.loads(recognizer.FinalResult()).get("text", "").strip()


async def transcribe(request):
    check_local(request)
    if not ready():
        return web.json_response({"message": "Yerel Türkçe tanıma servisi hazır değil."}, status=503)
    if _session.locked():
        raise web.HTTPTooManyRequests()
    if request.content_type != "multipart/form-data":
        raise web.HTTPUnsupportedMediaType()

    async with _session:
        try:
            async with asyncio.timeout(12):
                reader = await request.multipart()
                part = await reader.next()
                if part is None or part.name != "audio":
                    raise web.HTTPBadRequest()
                mime = part.headers.get("Content-Type", "").split(";", 1)[0].lower()
                if mime not in FORMATS:
                    raise web.HTTPUnsupportedMediaType()
                data = bytearray()
                while chunk := await part.read_chunk():
                    data.extend(chunk)
                    if len(data) > MAX_AUDIO_BYTES:
                        raise web.HTTPRequestEntityTooLarge(max_size=MAX_AUDIO_BYTES, actual_size=len(data))
                if not data:
                    raise web.HTTPBadRequest()
                language = await reader.next()
                if language is not None and (
                    language.name != "language"
                    or await language.read_chunk() != b"tr"
                    or not language.at_eof()
                ):
                    return web.json_response({"message": "Yerel ses tanıma yalnızca Türkçe (tr) destekliyor."}, status=400)
        except TimeoutError:
            raise web.HTTPRequestTimeout()
        except (ValueError, AssertionError):
            raise web.HTTPBadRequest()

        process = await asyncio.create_subprocess_exec(
            shutil.which("ffmpeg"), "-nostdin", "-v", "error", "-protocol_whitelist", "pipe",
            "-f", FORMATS[mime], "-i", "pipe:0", "-vn", "-t", "16", "-ac", "1",
            "-ar", "16000", "-f", "s16le", "pipe:1",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            pcm, _ = await asyncio.wait_for(process.communicate(data), timeout=8)
        except (TimeoutError, asyncio.CancelledError) as error:
            if process.returncode is None:
                process.kill()
            await process.wait()
            if isinstance(error, TimeoutError):
                raise web.HTTPGatewayTimeout() from None
            raise
        if process.returncode or not pcm:
            return web.json_response({"message": "Ses biçimi okunamadı."}, status=422)
        job = asyncio.create_task(asyncio.to_thread(recognize, pcm))
        try:
            text = await asyncio.shield(job)
        except asyncio.CancelledError:
            await job
            raise
        return web.json_response({"text": text})
