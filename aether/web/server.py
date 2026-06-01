"""FastAPI web server for A.E.T.H.E.R."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from aether.config import Settings, ensure_dirs
from aether.harness import AgentHarness, AgentRole, Workflow
from aether.integrations.printer_factory import get_printer
from aether.integrations.printer_profiles import get_profile
from aether.knowledge.store import KnowledgeStore
from aether.capabilities import describe_capabilities
from aether.llm.ollama_client import OllamaClient
from aether.llm.router import ModelRouter
from aether.constants import AETHER_ACRONYM_FULL, AETHER_ACRONYM_LINE, AETHER_NAME
from aether.persona import boot_greeting, build_persona, time_greeting
from aether.pipeline.orchestrator import MasterPipeline
from aether.traces.store import TraceStore
from aether.voice.manager import VoiceManager

STATIC_DIR = Path(__file__).resolve().parent / "static"


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    model: Optional[str] = None
    stream: bool = True
    speak: bool = False


class WorkflowRequest(BaseModel):
    topic: str
    toml: Optional[str] = None
    speak: bool = False


class LearnRequest(BaseModel):
    topic: str


class BuildRequest(BaseModel):
    topic: str
    project: str
    printer: bool = False
    auto_print: bool = False


class SettingsUpdate(BaseModel):
    ollama_model: Optional[str] = None
    elevenlabs_api_key: Optional[str] = None


class AutoRequest(BaseModel):
    mission: str
    restrictions: str = ""
    max_iterations: int = 10
    max_runtime_minutes: int = 30
    allow_printing: bool = False
    use_llm_review: bool = True


class ApprovalRequest(BaseModel):
    approved: bool


class CommandRequest(BaseModel):
    request: str


class BuildAppRequest(BaseModel):
    spec: str
    name: str = ""


class SmartHomeControl(BaseModel):
    device: str
    command: str = "toggle"


def _sse(event: str, data: Any) -> str:
    payload = json.dumps(data) if not isinstance(data, str) else data
    return f"event: {event}\ndata: {payload}\n\n"


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or Settings.from_env()
    ensure_dirs(settings)

    app = FastAPI(title="A.E.T.H.E.R.", version="3.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.settings = settings
    app.state.llm = OllamaClient(model=settings.ollama_model, host=settings.ollama_host)
    app.state.traces = TraceStore(settings.traces_db)
    app.state.sessions: Dict[str, List[Dict[str, str]]] = {}
    app.state.workflow_running = False
    app.state.auto_control = None
    app.state.auto_thread = None

    @app.get("/api/health")
    async def health() -> Dict[str, Any]:
        llm: OllamaClient = app.state.llm
        ok = await asyncio.to_thread(llm.ping)
        return {
            "status": "ok" if ok else "degraded",
            "ollama": ok,
            "model": settings.ollama_model,
            "version": "3.0.0",
        }

    @app.get("/api/models")
    async def models() -> Dict[str, Any]:
        llm: OllamaClient = app.state.llm
        names = await asyncio.to_thread(llm.list_models)
        return {
            "data": [{"id": n, "name": n} for n in names],
            "default": settings.ollama_model,
        }

    @app.get("/api/agents/status")
    async def agents_status() -> Dict[str, Any]:
        harness = AgentHarness(app.state.llm, trace_store=app.state.traces)
        return harness.get_team_status()

    @app.get("/api/traces")
    async def traces(limit: int = 30) -> Dict[str, Any]:
        store: TraceStore = app.state.traces
        return {"traces": store.recent(limit)}

    @app.get("/api/memory")
    async def memory() -> Dict[str, Any]:
        store = KnowledgeStore(settings.data_dir)
        data = store._load_all()
        return data

    @app.get("/api/printer/status")
    async def printer_status() -> Dict[str, Any]:
        printer = get_printer(settings)
        profile = get_profile(settings.printer_profile)
        base = {
            "configured": printer.is_configured(),
            "profile": profile.id,
            "profile_name": profile.name,
            "build_volume_mm": [profile.build_x_mm, profile.build_y_mm, profile.build_z_mm],
            "backend": printer.backend_type,
        }
        if not printer.is_configured():
            return {**base, "online": False, "message": "Set OCTOPRINT_* or MOONRAKER_* in .env"}
        try:
            st = await asyncio.to_thread(printer.status)
            return {**base, "online": printer.ping(), **st}
        except Exception as exc:
            return {**base, "online": False, "error": str(exc)}

    @app.post("/api/auto/start")
    async def auto_start(body: AutoRequest) -> Dict[str, Any]:
        import threading

        from aether.autonomy.agent import AutonomousAgent
        from aether.autonomy.control import AutonomyControl
        from aether.autonomy.guardrails import Guardrails

        control = app.state.auto_control
        if control is not None and control.state.value in ("running", "paused", "stopping"):
            raise HTTPException(409, "Autonomous agent already running")

        llm: OllamaClient = app.state.llm
        if not await asyncio.to_thread(llm.ping):
            raise HTTPException(503, "Ollama is not running")

        guardrails = Guardrails.from_prompt(
            body.restrictions,
            max_iterations=body.max_iterations,
            max_runtime_minutes=body.max_runtime_minutes,
            allow_printing=body.allow_printing,
            use_llm_review=body.use_llm_review,
        )
        control = AutonomyControl(settings.data_dir)
        app.state.auto_control = control
        agent = AutonomousAgent(llm, settings, guardrails, control=control)

        def _run() -> None:
            try:
                agent.run(body.mission)
            except Exception as exc:  # never crash the server thread silently
                control.log("error", f"Run crashed: {exc}")
                control.finish()

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        app.state.auto_thread = thread
        return {"started": True, "guardrails": guardrails.to_dict()}

    @app.post("/api/auto/stop")
    async def auto_stop() -> Dict[str, Any]:
        control = app.state.auto_control
        if control is None:
            return {"stopped": True, "message": "No agent running"}
        control.stop("web stop button")
        return {"stopped": True}

    @app.post("/api/auto/pause")
    async def auto_pause() -> Dict[str, Any]:
        control = app.state.auto_control
        if control is None:
            raise HTTPException(404, "No agent")
        control.pause()
        return {"paused": True}

    @app.post("/api/auto/resume")
    async def auto_resume() -> Dict[str, Any]:
        control = app.state.auto_control
        if control is None:
            raise HTTPException(404, "No agent")
        control.resume()
        return {"resumed": True}

    @app.post("/api/auto/approve")
    async def auto_approve(body: ApprovalRequest) -> Dict[str, Any]:
        control = app.state.auto_control
        if control is None:
            raise HTTPException(404, "No agent")
        control.submit_approval(body.approved)
        return {"ok": True}

    @app.get("/api/auto/status")
    async def auto_status(since: int = 0) -> Dict[str, Any]:
        control = app.state.auto_control
        if control is None:
            return {"state": "idle", "activity": [], "pending_approval": None}
        activity = control.activity(200)
        return {
            **control.status(),
            "activity": activity[since:] if since < len(activity) else [],
            "total": len(activity),
        }

    @app.get("/api/persona")
    async def persona_info() -> Dict[str, Any]:
        persona = build_persona(settings.persona, settings.assistant_name, settings.user_title)
        return {
            "persona": persona.id,
            "name": persona.name,
            "user_title": settings.user_title,
            "wake_word": settings.wake_word,
            "greeting": boot_greeting(persona),
            "time_greeting": time_greeting(persona, settings.user_title),
            "acronym": AETHER_ACRONYM_FULL,
            "acronym_line": AETHER_ACRONYM_LINE,
            "brand": AETHER_NAME,
        }

    @app.get("/api/system/diagnostics")
    async def diagnostics() -> Dict[str, Any]:
        """System status report for the host machine."""
        info: Dict[str, Any] = {}
        try:
            import psutil

            vm = psutil.virtual_memory()
            info = {
                "cpu_percent": psutil.cpu_percent(interval=0.2),
                "cpu_count": psutil.cpu_count(logical=True),
                "memory_percent": vm.percent,
                "memory_used_gb": round(vm.used / 1e9, 1),
                "memory_total_gb": round(vm.total / 1e9, 1),
            }
            try:
                batt = psutil.sensors_battery()
                if batt is not None:
                    info["battery_percent"] = round(batt.percent)
                    info["power_plugged"] = bool(batt.power_plugged)
            except (AttributeError, NotImplementedError):
                pass
        except Exception as exc:
            info["error"] = str(exc)

        llm: OllamaClient = app.state.llm
        info["ollama_online"] = await asyncio.to_thread(llm.ping)
        printer = get_printer(settings)
        info["printer_configured"] = printer.is_configured()
        return info

    @app.get("/api/capabilities")
    async def capabilities() -> Dict[str, Any]:
        return {"capabilities": describe_capabilities(settings)}

    @app.get("/api/llm/routing")
    async def llm_routing() -> Dict[str, Any]:
        router = ModelRouter(settings, app.state.llm)
        return {"routing": router.routing_table(), "installed": router.list_models()}

    @app.get("/api/smarthome/entities")
    async def smarthome_entities() -> Dict[str, Any]:
        from aether.integrations.smart_home import SmartHome

        home = SmartHome(settings.homeassistant_url, settings.homeassistant_token)
        if not home.is_configured():
            return {"configured": False, "entities": []}
        try:
            return {"configured": True, "online": await asyncio.to_thread(home.ping), "entities": await asyncio.to_thread(home.entities)}
        except Exception as exc:
            return {"configured": True, "online": False, "error": str(exc), "entities": []}

    @app.post("/api/smarthome/control")
    async def smarthome_control(body: SmartHomeControl) -> Dict[str, Any]:
        from aether.integrations.smart_home import SmartHome

        home = SmartHome(settings.homeassistant_url, settings.homeassistant_token)
        if not home.is_configured():
            raise HTTPException(400, "Home Assistant not configured")
        match = await asyncio.to_thread(home.find_entity, body.device)
        if not match:
            raise HTTPException(404, f"Device not found: {body.device}")
        cmd = body.command.lower()
        if cmd == "off" or (cmd == "toggle" and match["state"] == "on"):
            await asyncio.to_thread(home.turn_off, match["entity_id"])
            action = "off"
        else:
            await asyncio.to_thread(home.turn_on, match["entity_id"])
            action = "on"
        return {"device": match["name"], "action": action}

    @app.post("/api/build-app")
    async def build_app(body: BuildAppRequest) -> StreamingResponse:
        if app.state.workflow_running:
            raise HTTPException(409, "Busy")
        router = ModelRouter(settings, app.state.llm)
        if not await asyncio.to_thread(router.ping):
            raise HTTPException(503, "Ollama is not running")

        async def stream() -> AsyncGenerator[str, None]:
            from aether.pipeline.app_builder import AppBuilderPipeline

            app.state.workflow_running = True
            events: asyncio.Queue = asyncio.Queue()
            pipe = AppBuilderPipeline(router, settings, trace_store=app.state.traces, on_event=lambda e, d: events.put_nowait((e, d)))
            task = asyncio.create_task(pipe.build(body.spec, project_name=body.name))
            yield _sse("build_start", {"spec": body.spec})
            while not task.done():
                try:
                    e, d = await asyncio.wait_for(events.get(), timeout=0.5)
                    yield _sse(e, d)
                except asyncio.TimeoutError:
                    yield _sse("heartbeat", {})
            app.state.workflow_running = False
            yield _sse("done", await task)

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.post("/api/command")
    async def command(body: CommandRequest) -> StreamingResponse:
        router = ModelRouter(settings, app.state.llm)
        if not await asyncio.to_thread(router.ping):
            raise HTTPException(503, "Ollama is not running")

        async def stream() -> AsyncGenerator[str, None]:
            from aether.brain.commander import Commander

            events: asyncio.Queue = asyncio.Queue()
            commander = Commander(settings, router, on_event=lambda e, d: events.put_nowait((e, d)))
            task = asyncio.create_task(commander.run(body.request))
            yield _sse("command_start", {"request": body.request})
            while not task.done():
                try:
                    e, d = await asyncio.wait_for(events.get(), timeout=0.5)
                    yield _sse(e, d)
                except asyncio.TimeoutError:
                    yield _sse("heartbeat", {})
            yield _sse("command_done", await task)

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.get("/api/config/public")
    async def public_config() -> Dict[str, Any]:
        """Info safe to expose to the mobile app."""
        p = get_profile(settings.printer_profile)
        return {
            "printer_profile": p.name,
            "build_volume_mm": [p.build_x_mm, p.build_y_mm, p.build_z_mm],
            "version": "3.0.0",
        }

    @app.post("/api/learn")
    async def learn_deep(body: LearnRequest) -> StreamingResponse:
        if app.state.workflow_running:
            raise HTTPException(409, "Busy")
        llm: OllamaClient = app.state.llm
        if not await asyncio.to_thread(llm.ping):
            raise HTTPException(503, "Ollama is not running")

        async def stream() -> AsyncGenerator[str, None]:
            app.state.workflow_running = True
            events: asyncio.Queue = asyncio.Queue()
            pipe = MasterPipeline(
                llm,
                settings,
                trace_store=app.state.traces,
                on_event=lambda e, d: events.put_nowait((e, d)),
            )
            task = asyncio.create_task(pipe.learn(body.topic))
            yield _sse("learn_start", {"topic": body.topic})
            while not task.done():
                try:
                    e, d = await asyncio.wait_for(events.get(), timeout=0.5)
                    yield _sse(e, d)
                except asyncio.TimeoutError:
                    yield _sse("heartbeat", {})
            result = await task
            app.state.workflow_running = False
            yield _sse("learn_done", result)

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.post("/api/build")
    async def build_project(body: BuildRequest) -> StreamingResponse:
        if app.state.workflow_running:
            raise HTTPException(409, "Busy")
        llm: OllamaClient = app.state.llm
        if not await asyncio.to_thread(llm.ping):
            raise HTTPException(503, "Ollama is not running")

        async def stream() -> AsyncGenerator[str, None]:
            app.state.workflow_running = True
            events: asyncio.Queue = asyncio.Queue()
            pipe = MasterPipeline(
                llm,
                settings,
                trace_store=app.state.traces,
                on_event=lambda e, d: events.put_nowait((e, d)),
            )
            task = asyncio.create_task(
                pipe.build(
                    body.topic,
                    body.project,
                    send_to_printer=body.printer,
                    auto_print=body.auto_print,
                )
            )
            yield _sse("build_start", {"topic": body.topic, "project": body.project})
            while not task.done():
                try:
                    e, d = await asyncio.wait_for(events.get(), timeout=0.5)
                    yield _sse(e, d)
                except asyncio.TimeoutError:
                    yield _sse("heartbeat", {})
            result = await task
            app.state.workflow_running = False
            yield _sse("build_done", result)

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.post("/api/chat")
    async def chat(body: ChatRequest) -> StreamingResponse:
        llm: OllamaClient = app.state.llm
        if not await asyncio.to_thread(llm.ping):
            raise HTTPException(503, "Ollama is not running. Start Ollama and pull a model.")

        messages = [{"role": m.role, "content": m.content} for m in body.messages]
        if not messages:
            raise HTTPException(400, "No messages")
        model = body.model or settings.ollama_model
        persona = build_persona(settings.persona, settings.assistant_name, settings.user_title)
        system = persona.system_prompt
        if messages[0]["role"] != "system":
            messages = [{"role": "system", "content": system}, *messages]

        async def stream() -> AsyncGenerator[str, None]:
            full = []
            loop = asyncio.get_running_loop()
            queue: asyncio.Queue = asyncio.Queue()
            _DONE = object()

            def _producer() -> None:
                try:
                    import ollama

                    for chunk in ollama.chat(model=model, messages=messages, stream=True):
                        delta = chunk.get("message", {}).get("content", "")
                        if delta:
                            loop.call_soon_threadsafe(queue.put_nowait, delta)
                except Exception as exc:
                    loop.call_soon_threadsafe(queue.put_nowait, exc)
                finally:
                    loop.call_soon_threadsafe(queue.put_nowait, _DONE)

            try:
                await asyncio.to_thread(lambda: None)  # warm the threadpool
                producer = asyncio.create_task(asyncio.to_thread(_producer))
                while True:
                    item = await queue.get()
                    if item is _DONE:
                        break
                    if isinstance(item, Exception):
                        raise item
                    full.append(item)
                    yield _sse("message", {"choices": [{"delta": {"content": item}}]})
                await producer
                text = "".join(full)
                app.state.traces.log("chat", "completed", payload=messages[-1]["content"][:300])
                yield _sse("done", "[DONE]")
                if body.speak and text:
                    voice = VoiceManager(settings.elevenlabs_api_key, settings.elevenlabs_voice_id)
                    await voice._speak_async(text[:2000])
            except Exception as exc:
                yield _sse("error", {"message": str(exc)})

        if body.stream:
            return StreamingResponse(stream(), media_type="text/event-stream")
        text = await asyncio.to_thread(llm.chat, messages, model)
        return StreamingResponse(
            iter([_sse("message", {"choices": [{"delta": {"content": text}}]})]),
            media_type="text/event-stream",
        )

    @app.post("/api/workflow")
    async def workflow(body: WorkflowRequest) -> StreamingResponse:
        if app.state.workflow_running:
            raise HTTPException(409, "A workflow is already running")

        llm: OllamaClient = app.state.llm
        if not await asyncio.to_thread(llm.ping):
            raise HTTPException(503, "Ollama is not running")

        async def run_stream() -> AsyncGenerator[str, None]:
            app.state.workflow_running = True
            voice = (
                VoiceManager(settings.elevenlabs_api_key, settings.elevenlabs_voice_id)
                if body.speak
                else None
            )
            harness = AgentHarness(app.state.llm, voice_engine=voice, trace_store=app.state.traces)
            progress_events: asyncio.Queue = asyncio.Queue()

            def on_progress(data: Dict) -> None:
                progress_events.put_nowait(data)

            harness.register_callback("progress", on_progress)
            harness.register_callback("task_started", lambda d: progress_events.put_nowait({"type": "task_started", **d}))
            harness.register_callback("task_completed", lambda d: progress_events.put_nowait({"type": "task_completed", **d}))

            if body.toml:
                path = Path(body.toml)
                if not path.is_absolute():
                    path = Path(__file__).resolve().parents[2] / "workflows" / body.toml
                wf = Workflow.from_toml(str(path), harness, base_input={"topic": body.topic})
            else:
                wf = _default_workflow(harness, body.topic)

            yield _sse("workflow_start", {"topic": body.topic, "name": wf.name})

            run_task = asyncio.create_task(harness.execute_workflow(wf))

            while not run_task.done():
                try:
                    evt = await asyncio.wait_for(progress_events.get(), timeout=0.4)
                    yield _sse("workflow_progress", evt)
                except asyncio.TimeoutError:
                    yield _sse("heartbeat", {"ts": time.time()})

            result = await run_task
            app.state.workflow_running = False
            yield _sse("workflow_done", result)

        return StreamingResponse(run_stream(), media_type="text/event-stream")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    return app


def _default_workflow(harness: AgentHarness, topic: str) -> Workflow:
    wf = harness.create_workflow("learn_topic")
    wf.add_task(AgentRole.PLANNER, "create plan", {"topic": topic}, task_key="plan")
    wf.add_task(AgentRole.RESEARCH, "research", {"topic": topic}, depends_on=["plan"], task_key="research")
    wf.add_task(AgentRole.VALIDATION, "validate", {"topic": topic}, depends_on=["research"], task_key="validate")
    wf.add_task(AgentRole.SYNTHESIZER, "synthesize", {"topic": topic}, depends_on=["validate"], task_key="synthesize")
    wf.add_task(AgentRole.MEMORY, "store", {"topic": topic}, depends_on=["synthesize"], task_key="memory")
    return wf


def run_server(host: str = "127.0.0.1", port: int = 8787, reload: bool = False, lan: bool = False) -> None:
    if lan:
        host = "0.0.0.0"
    import uvicorn

    uvicorn.run("aether.web.server:create_app", host=host, port=port, reload=reload, factory=True)


__all__ = ["create_app", "run_server"]
