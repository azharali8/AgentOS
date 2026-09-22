"""Server-owned AssemblyAI v3 audio relay. Client text is never a transcript source."""
from __future__ import annotations

import asyncio
import anyio
import json
import time
import re
from contextlib import suppress
from urllib.parse import urlencode

from fastapi import HTTPException, WebSocket, WebSocketDisconnect
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from backend.app.auth.service import get_current_user, UserRole
from backend.app.config.settings import settings
from backend.app.security.rate_limit import RateLimiter
from backend.app.voice.service import VoiceService

MODEL = "universal-3-5-pro"
URL = "wss://streaming.assemblyai.com/v3/ws?" + urlencode({
    "sample_rate": 16000, "encoding": "pcm_s16le", "speech_model": MODEL,
})


class StreamFailure(Exception):
    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


def provider_failure(code: int | None) -> StreamFailure:
    if code in (401, 403, 1008):
        return StreamFailure("AssemblyAI authentication/account failure. Check the server key and account balance.")
    if code in (402, 429, 3009):
        return StreamFailure("AssemblyAI quota or concurrent-session limit reached.")
    return StreamFailure("AssemblyAI disconnected. Unfinished speech was discarded; submitted commands are not replayed.", code in (None, 1006, 1011, 3005))


class FinalTurns:
    """Provider-local turn identity; formatting revisions cannot execute twice."""
    def __init__(self):
        self.session_id = None
        self.seen = set()

    def accept(self, event: dict) -> str | None:
        if event.get("type") == "Begin":
            if self.session_id is not None or not isinstance(event.get("id"), str) or not event["id"]:
                raise StreamFailure("Invalid AssemblyAI session start.")
            self.session_id = event["id"]
            model = event.get("configuration", {}).get("model")
            if model and model != MODEL:
                raise StreamFailure("AssemblyAI returned an unexpected speech model.")
            return None
        if event.get("type") != "Turn":
            return None
        order, final, text = event.get("turn_order"), event.get("end_of_turn"), event.get("transcript")
        if self.session_id is None or type(order) is not int or order < 0 or type(final) is not bool or not isinstance(text, str) or len(text) > 2000:
            raise StreamFailure("Malformed AssemblyAI turn; no command was submitted.")
        if not final or order in self.seen:
            return None
        if len(self.seen) >= 100:
            raise StreamFailure("Voice turn limit reached. Start a new voice session.")
        self.seen.add(order)  # reserve BEFORE dispatch, including empty final turns
        return text.strip()


class PlaybackEchoGuard:
    """Suppress exact spoken-response fragments, never turn text into commands."""
    def __init__(self):
        self.recent = []

    @staticmethod
    def normalize(text):
        return " ".join(re.findall(r"[a-z0-9]+", text.lower()))

    def remember(self, text):
        self.recent = [(t, at) for t, at in self.recent if time.monotonic() - at < 20][-3:]
        self.recent.append((self.normalize(text), time.monotonic()))

    def matches(self, text):
        normalized = self.normalize(text)
        if len(normalized.split()) < 2:
            return False
        return any(time.monotonic() - at < 20 and f" {normalized} " in f" {spoken} " for spoken, at in self.recent)


async def relay(browser: WebSocket, provider, user, session_id: str, token: str | None = None, one_shot: bool = False):
    turns = FinalTurns()
    echo = PlaybackEchoGuard()
    pending = asyncio.Queue(maxsize=4)
    terminated = asyncio.Event()
    stopping = False
    last_speech = time.monotonic()
    warned = False
    accepted_one = False

    async def receive_audio():
        nonlocal stopping
        total = 0
        started = time.monotonic()
        while True:
            message = await browser.receive()
            if message["type"] == "websocket.disconnect":
                raise WebSocketDisconnect()
            audio = message.get("bytes")
            if audio is not None:
                if turns.session_id is None or not 1600 <= len(audio) <= 32000 or len(audio) % 2:
                    raise StreamFailure("Invalid audio frame. Expected 50–1000 ms of 16 kHz mono PCM16.")
                total += len(audio)
                if total > (time.monotonic() - started + 2) * 40000:
                    raise StreamFailure("Audio exceeded the real-time rate limit.")
                await provider.send(audio)
            elif message.get("text") == '{"type":"Stop"}':
                stopping = True
                await provider.send(json.dumps({"type": "Terminate"}))
                await asyncio.wait_for(terminated.wait(), timeout=3)
                return
            else:
                try:
                    if len(message.get("text", "")) > 4096:
                        raise ValueError()
                    control = json.loads(message.get("text", ""))
                    if control.get("type") != "Playback" or not isinstance(control.get("text"), str) or len(control["text"]) > 1800:
                        raise ValueError()
                    echo.remember(control["text"])
                except (ValueError, TypeError, AttributeError):
                    raise StreamFailure("Only audio, playback notices and Stop are accepted; client transcripts cannot execute.") from None

    async def receive_events():
        nonlocal last_speech, warned, accepted_one
        while True:
            raw = await asyncio.wait_for(provider.recv(), timeout=20 if turns.session_id is None else 90)
            try:
                event = json.loads(raw)
                if not isinstance(event, dict) or not isinstance(event.get("type"), str):
                    raise ValueError()
                kind = event["type"]
                text = turns.accept(event)
            except (ValueError, TypeError, AttributeError):
                raise StreamFailure("Malformed AssemblyAI event; no command was submitted.") from None
            if kind == "Error":
                raise provider_failure(event.get("error_code"))
            if kind == "Termination":
                terminated.set()
                await browser.send_json({"type": "Termination"})
                return
            if kind == "Begin":
                await browser.send_json({"type": "Begin", "id": turns.session_id})
            elif kind == "SpeechStarted":
                last_speech, warned = time.monotonic(), False
                await browser.send_json({"type": "SpeechStarted"})
            elif kind == "Turn":
                if event["transcript"].strip():
                    last_speech, warned = time.monotonic(), False
                await browser.send_json({"type": "Turn", "transcript": event["transcript"],
                                         "end_of_turn": event["end_of_turn"], "turn_order": event["turn_order"]})
                if text is not None and not stopping and not (one_shot and accepted_one):
                    if echo.matches(text):
                        await browser.send_json({"type": "Notice", "message": "Possible speaker echo ignored. Use headphones or mute speech if this repeats."})
                    elif not text:
                        await browser.send_json({"type": "Notice", "message": "No usable speech in that turn. Please try again."})
                    else:
                        try:
                            pending.put_nowait((event["turn_order"], text))
                            accepted_one = True
                        except asyncio.QueueFull:
                            raise StreamFailure("Too many pending voice requests. Check task activity before retrying.")

    async def execute_turns():
        while True:
            order, text = await pending.get()
            current_user = get_current_user(api_key=token, authorization=None)
            if current_user.user_id != user.user_id or current_user.role == UserRole.VIEWER:
                raise StreamFailure("Voice execution permission was revoked.")
            await browser.send_json({"type": "Processing", "turn_order": order})
            # Keep audio/event reception alive while the existing gateway runs.
            # No automatic retry: a disconnected response may already have created a task.
            try:
                result = await asyncio.to_thread(VoiceService.process_transcript, text,
                    user_id=current_user.user_id, user_role=current_user.role.value, session_id=session_id,
                    provider="assemblyai-streaming", confidence=None, sync=False)
                payload = result.model_dump()
            except Exception:
                import logging
                logging.getLogger(__name__).exception("Supervisor failed after a final voice transcript")
                payload = {"status": "failed", "error_type": "SUPERVISOR_ERROR",
                           "tts_summary": "Speech was received, but AgentOS execution failed. Check task Activity before retrying."}
            await browser.send_json({"type": "Result", "turn_order": order, **payload})
            if one_shot:
                return

    async def silence_watch():
        nonlocal warned
        while True:
            await asyncio.sleep(min(5, settings.VOICE_STREAM_IDLE_SECONDS / 2))
            idle = time.monotonic() - last_speech
            if idle >= settings.VOICE_STREAM_IDLE_SECONDS:
                raise StreamFailure("Voice stopped after silence to conserve speech credits. Submitted tasks continue; restart voice when ready.")
            if not warned and idle >= min(30, settings.VOICE_STREAM_IDLE_SECONDS / 2):
                warned = True
                await browser.send_json({"type": "Notice", "message": "No speech detected. Voice will stop automatically if silence continues; check your microphone."})

    tasks = [asyncio.create_task(fn()) for fn in (receive_audio, receive_events, execute_turns, silence_watch)]
    try:
        done, _ = await asyncio.wait(tasks, timeout=settings.VOICE_STREAM_MAX_SECONDS, return_when=asyncio.FIRST_COMPLETED)
        if not done:
            raise StreamFailure("Voice session reached its time limit to conserve speech credits. Submitted tasks continue; restart voice when ready.")
        for task in done:
            task.result()
    finally:
        # ASGI disconnect cancellation must not skip upstream Terminate.
        with anyio.CancelScope(shield=True):
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if not terminated.is_set():
                with suppress(Exception):
                    await asyncio.wait_for(provider.send(json.dumps({"type": "Terminate"})), timeout=2)
                    # Consume termination confirmation; never dispatch final text during shutdown.
                    async with asyncio.timeout(2):
                        while json.loads(await provider.recv()).get("type") != "Termination":
                            pass



async def stream_voice(websocket: WebSocket):
    origin = websocket.headers.get("origin")
    if origin and origin not in settings.cors_origins_list:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        RateLimiter.check_rate_limit(websocket.client.host if websocket.client else "unknown", domain="voice_stream", limit=5, window_seconds=60)
        # First frame authentication avoids credentials in URL/access logs.
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=5)
        if len(raw) > 4096:
            raise StreamFailure("Invalid voice handshake.")
        hello = json.loads(raw)
        if not isinstance(hello, dict) or hello.get("type") != "Start":
            raise StreamFailure("Invalid voice handshake.")
        mode = hello.get("mode", "live")
        if mode not in ("live", "once"):
            raise StreamFailure("Invalid voice mode.")
        session = hello.get("session_id")
        if not isinstance(session, str) or not 1 <= len(session) <= 128:
            raise StreamFailure("Invalid conversation session.")
        token = hello.get("token")
        if token is not None and not isinstance(token, str):
            raise StreamFailure("Invalid voice authentication.")
        user = get_current_user(api_key=token, authorization=None)
        if user.role == UserRole.VIEWER:
            raise StreamFailure("Voice execution requires user role or higher.")
        if not settings.ASSEMBLYAI_API_KEY.strip():
            raise StreamFailure("Configure the AssemblyAI API key on the server before starting voice.")
        async with connect(URL, additional_headers={"Authorization": settings.ASSEMBLYAI_API_KEY.strip()},
                           open_timeout=10, close_timeout=3, max_size=65536, max_queue=16) as provider:
            await relay(websocket, provider, user, session, token, one_shot=mode == "once")
    except WebSocketDisconnect:
        return
    except Exception as exc:
        if isinstance(exc, InvalidStatus):
            failure = provider_failure(exc.response.status_code)
        elif isinstance(exc, ConnectionClosed):
            failure = provider_failure(exc.rcvd.code if exc.rcvd else None)
        elif isinstance(exc, StreamFailure):
            failure = exc
        elif isinstance(exc, HTTPException):
            failure = StreamFailure("Voice access denied or rate limited. Sign in and check your permissions.")
        elif isinstance(exc, (OSError, TimeoutError)):
            failure = StreamFailure("Voice connection timed out or is unavailable. Check task activity before retrying.", True)
        else:
            failure = StreamFailure("Voice processing failed. Check task activity before retrying; no success is assumed.")
        # Never forward raw provider exceptions, headers, or arbitrary error text.
        with suppress(Exception):
            await websocket.send_json({"type": "Error", "message": str(failure), "retryable": failure.retryable})
    finally:
        with suppress(Exception):
            await websocket.close()
