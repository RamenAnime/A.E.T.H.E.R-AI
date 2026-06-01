"""A.E.T.H.E.R. command-line interface."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from aether.config import Settings, ensure_dirs
from aether.harness import AgentHarness, AgentRole, Workflow
from aether.llm.ollama_client import OllamaClient
from aether.pipeline.orchestrator import MasterPipeline
from aether.traces.store import TraceStore
from aether.voice.manager import VoiceManager


def _package_root() -> Path:
    return Path(__file__).resolve().parents[1]


def cmd_doctor(settings: Settings) -> int:
    print("A.E.T.H.E.R. doctor\n")
    llm = OllamaClient(model=settings.ollama_model, host=settings.ollama_host)
    ok = llm.ping()
    print(f"  Ollama ({settings.ollama_host}): {'OK' if ok else 'NOT REACHABLE'}")
    if ok:
        models = llm.list_models()
        print(f"  Models: {', '.join(models[:8]) or '(none pulled)'}")
    print(f"  ElevenLabs key: {'set' if settings.elevenlabs_api_key else 'missing (console TTS fallback)'}")
    print(f"  Persona: {settings.persona} (name: {settings.assistant_name}, addresses you as '{settings.user_title}', wake word '{settings.wake_word}')")
    print(f"  AirLLM: {'enabled' if settings.use_airllm else 'disabled'}")
    if ok:
        from aether.llm.router import ModelRouter

        table = ModelRouter(settings, llm).routing_table()
        print(f"  Model routing: {table}")
    home_set = bool(settings.homeassistant_url and settings.homeassistant_token)
    print(f"  Smart home: {'configured' if home_set else 'not configured (set HOMEASSISTANT_* in .env)'}")
    print(f"  Build output dir: {settings.build_dir}")
    print(f"  Data dir: {settings.data_dir}")
    from aether.integrations.printer_factory import get_printer
    from aether.integrations.printer_profiles import get_profile

    prof = get_profile(settings.printer_profile)
    print(f"  Printer profile: {prof.name} ({prof.build_x_mm}x{prof.build_y_mm}x{prof.build_z_mm} mm)")
    pr = get_printer(settings)
    if pr.is_configured():
        print(f"  Printer API ({pr.backend_type}): {'OK' if pr.ping() else 'not reachable'} ({pr.base_url})")
    else:
        print("  Printer API: not configured (optional: see docs/ENDER3_V3.md)")
    if not ok:
        print("\nInstall Ollama: https://ollama.com/download")
        print(f"Then run: ollama pull {settings.ollama_model}")
        return 1
    return 0


def cmd_chat(settings: Settings, message: str, speak: bool) -> int:
    llm = OllamaClient(model=settings.ollama_model, host=settings.ollama_host)
    if not llm.ping():
        print("Ollama is not running. Start Ollama and run: aether doctor")
        return 1
    from aether.persona import boot_greeting, build_persona

    persona = build_persona(settings.persona, settings.assistant_name, settings.user_title)
    voice = VoiceManager(settings.elevenlabs_api_key, settings.elevenlabs_voice_id) if speak else None
    traces = TraceStore(settings.traces_db)
    if speak and voice:
        voice.speak(boot_greeting(persona))
    reply = llm.complete(message, system=persona.system_prompt)
    print(reply)
    traces.log("chat", "completed", payload=message[:500], agent="cli")
    if speak and voice:
        voice.speak(reply[:1500])
    return 0


def _build_learn_workflow(harness: AgentHarness, topic: str) -> Workflow:
    wf = harness.create_workflow("learn_topic")
    wf.add_task(AgentRole.PLANNER, "create plan", {"topic": topic}, task_key="plan")
    wf.add_task(
        AgentRole.RESEARCH,
        "research topic",
        {"topic": topic},
        depends_on=["plan"],
        task_key="research",
    )
    wf.add_task(
        AgentRole.VALIDATION,
        "validate facts",
        {"topic": topic},
        depends_on=["research"],
        task_key="validate",
    )
    wf.add_task(
        AgentRole.SYNTHESIZER,
        "build study sheet",
        {"topic": topic},
        depends_on=["validate"],
        task_key="synthesize",
    )
    wf.add_task(
        AgentRole.MEMORY,
        "store knowledge",
        {"topic": topic},
        depends_on=["synthesize"],
        task_key="memory",
    )
    return wf


async def cmd_workflow(settings: Settings, topic: str, toml: str | None, speak: bool) -> int:
    llm = OllamaClient(model=settings.ollama_model, host=settings.ollama_host)
    if not llm.ping():
        print("Ollama is not running. Run: aether doctor")
        return 1
    voice = VoiceManager(settings.elevenlabs_api_key, settings.elevenlabs_voice_id) if speak else None
    harness = AgentHarness(llm, voice_engine=voice, trace_store=TraceStore(settings.traces_db))
    if toml:
        path = Path(toml)
        if not path.is_absolute():
            path = _package_root() / "workflows" / toml
        wf = Workflow.from_toml(str(path), harness, base_input={"topic": topic})
    else:
        wf = _build_learn_workflow(harness, topic)
    print(f"Running workflow on topic: {topic}")
    result = await harness.execute_workflow(wf)
    print(f"\nStatus: {result['status']}")
    print(f"Completed: {result['tasks_completed']} / failed: {result['tasks_failed']}")
    sheet = result.get("shared_context", {}).get("study_sheet", "")
    if sheet:
        out = Path(settings.data_dir) / f"study_{topic.replace(' ', '_')[:40]}.md"
        out.write_text(sheet, encoding="utf-8")
        print(f"Study sheet saved: {out}")
    return 0 if result["status"] == "complete" else 1


async def cmd_learn(settings: Settings, topic: str) -> int:
    llm = OllamaClient(model=settings.ollama_model, host=settings.ollama_host)
    if not llm.ping():
        print("Ollama is not running. Run: aether doctor")
        return 1
    print(f"Deep learning (graduate level): {topic}")
    print("This runs 4 research passes: may take several minutes.\n")
    pipe = MasterPipeline(llm, settings)

    def progress(event: str, data: dict) -> None:
        print(f"  [{event}] {data.get('status', data.get('topic', ''))}")

    pipe.on_event = progress
    result = await pipe.learn(topic)
    print(f"\nDone. Topic stored. Slug: {result.get('slug')}")
    print(f"Memory: {result.get('memory_file')}")
    print(f"Curriculum size: {result.get('curriculum_chars', 0)} chars")
    print("\nNext: aether build --topic \"...\" --project \"your build description\"")
    return 0 if result.get("status") == "complete" else 1


async def cmd_build(
    settings: Settings,
    topic: str,
    project: str,
    printer: bool,
    auto_print: bool,
) -> int:
    llm = OllamaClient(model=settings.ollama_model, host=settings.ollama_host)
    if not llm.ping():
        print("Ollama is not running. Run: aether doctor")
        return 1
    print(f"Building project for topic: {topic}")
    print(f"Project: {project}\n")
    pipe = MasterPipeline(llm, settings)

    def progress(event: str, data: dict) -> None:
        print(f"  [{event}]")

    pipe.on_event = progress
    result = await pipe.build(topic, project, send_to_printer=printer, auto_print=auto_print)
    print(f"\nStatus: {result.get('status')}")
    print(f"Output folder: {result.get('build_dir')}")
    for name, path in (result.get("artifacts") or {}).items():
        print(f"  {name}: {path}")
    pr = result.get("printer") or {}
    print(f"Printer: {pr.get('message', pr.get('status', 'n/a'))}")
    return 0 if result.get("status") == "complete" else 1


def cmd_auto(
    settings: Settings,
    mission: str,
    restrictions: str,
    max_iters: int,
    minutes: int,
    allow_printing: bool,
    no_review: bool,
    yes_to_all: bool,
) -> int:
    from aether.autonomy.agent import AutonomousAgent
    from aether.autonomy.control import AutonomyControl
    from aether.autonomy.guardrails import Guardrails

    llm = OllamaClient(model=settings.ollama_model, host=settings.ollama_host)
    if not llm.ping():
        print("Ollama is not running. Run: aether doctor")
        return 1

    guardrails = Guardrails.from_prompt(
        restrictions,
        max_iterations=max_iters,
        max_runtime_minutes=minutes,
        allow_printing=allow_printing,
        use_llm_review=not no_review,
    )
    control = AutonomyControl(settings.data_dir)

    print("A.E.T.H.E.R. autonomous mode")
    print(f"  Mission: {mission}")
    print(f"  Restrictions: {restrictions or '(none)'}")
    print(f"  Limits: {max_iters} steps / {minutes} min / printing={'on' if allow_printing else 'off'}")
    print(f"  Stop anytime: run 'aether stop' in another terminal, or press Ctrl-C.\n")

    def on_event(kind: str, entry: dict) -> None:
        print(f"  [{kind}] {entry.get('message', '')}")
        # Auto-handle approvals on the CLI.
        if kind == "approval_request":
            if yes_to_all:
                control.submit_approval(True)
            else:
                try:
                    ans = input("    Approve this action? [y/N] > ").strip().lower()
                except EOFError:
                    ans = "n"
                control.submit_approval(ans in ("y", "yes"))

    agent = AutonomousAgent(llm, settings, guardrails, control=control, on_event=on_event)
    import threading

    runner = {"result": None}

    def _run() -> None:
        runner["result"] = agent.run(mission)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    try:
        while thread.is_alive():
            thread.join(timeout=0.5)
    except KeyboardInterrupt:
        print("\nCtrl-C: stopping the agent...")
        control.stop("ctrl-c")
        thread.join(timeout=10)

    result = runner.get("result") or {}
    print(f"\nFinished. State: {result.get('state')} · iterations: {result.get('iterations')}")
    return 0


def _cli_approve(yes_to_all: bool):
    """Return an approve(plan)->bool callback for build gating, or None if auto-approving."""
    if yes_to_all:
        return None

    def approve(plan: dict) -> bool:
        files = plan.get("files", [])
        print(f"\n  Proposed: {plan.get('project_name', 'app')}: {', '.join(plan.get('stack', []))}")
        for f in files[:30]:
            print(f"    - {f.get('path')}  ({f.get('purpose', '')})")
        try:
            ans = input(f"\n  Write these {len(files)} files? [Y/n] > ").strip().lower()
        except EOFError:
            return False
        return ans in ("", "y", "yes")

    return approve


def _summarize_result(settings: Settings, result: dict) -> str:
    intent = result.get("intent")
    title = settings.user_title
    if intent == "chat":
        return result.get("reply", "")
    if intent == "build_app":
        if result.get("status") == "cancelled":
            return f"Cancelled, {title}. Nothing was written."
        return (
            f"Done, {title}. Built {len(result.get('files', []))} files in {result.get('dir')}.\n"
            f"  Install: {result.get('install_command')}\n  Run: {result.get('run_command')}"
        )
    if intent == "build_cad":
        return f"CAD package ready, {title}: {result.get('build_dir')}"
    if intent == "learn":
        return f"I've finished studying {result.get('topic')}, {title} (slug {result.get('slug')})."
    if intent == "smart_home":
        return result.get("message") or f"{result.get('device', '')} {result.get('action', '')}".strip() or str(result.get("status"))
    return f"Done, {title}."


def cmd_do(settings: Settings, request: str, speak: bool, yes_to_all: bool = False) -> int:
    """Natural-language command: build, engineer, learn, control devices, or chat."""
    import asyncio as _asyncio

    from aether.brain.commander import Commander
    from aether.llm.router import ModelRouter
    from aether.persona import acknowledgement, build_persona

    router = ModelRouter(settings)
    if not router.ping():
        print("Ollama is not running. Run: aether doctor")
        return 1

    persona = build_persona(settings.persona, settings.assistant_name, settings.user_title)
    print(acknowledgement(persona))

    def on_event(kind: str, data: dict) -> None:
        if kind in ("intent", "planned", "file_start", "file_done", "build_done", "learn_done"):
            print(f"  [{kind}] {str(data)[:160]}")

    commander = Commander(settings, router, on_event=on_event, approve=_cli_approve(yes_to_all))
    result = _asyncio.run(commander.run(request))
    summary = _summarize_result(settings, result)
    print(f"\n{summary}")
    if speak:
        VoiceManager(settings.elevenlabs_api_key, settings.elevenlabs_voice_id).speak(summary[:1500])
    return 0


def cmd_assistant(settings: Settings, silent: bool, yes_to_all: bool) -> int:
    """Continuous assistant session with time-based greeting and optional TTS."""
    import asyncio as _asyncio

    from aether.brain.commander import Commander
    from aether.llm.router import ModelRouter
    from aether.persona import build_persona, time_greeting

    router = ModelRouter(settings)
    if not router.ping():
        print("Ollama is not running. Run: aether doctor")
        return 1

    persona = build_persona(settings.persona, settings.assistant_name, settings.user_title)
    voice = None if silent else VoiceManager(settings.elevenlabs_api_key, settings.elevenlabs_voice_id)

    greeting = time_greeting(persona, settings.user_title)
    print(f"\n  {persona.name}: {greeting}")
    if voice:
        voice.speak(greeting)
    print('  (type your request; say "goodbye" or press Ctrl-C to exit)\n')

    commander = Commander(settings, router, approve=_cli_approve(yes_to_all))
    farewell = f"Goodbye, {settings.user_title}."
    try:
        while True:
            try:
                request = input("  you > ").strip()
            except EOFError:
                break
            if not request:
                continue
            if request.lower() in ("goodbye", "exit", "quit", "stop", "that's all", "thats all"):
                break
            result = _asyncio.run(commander.run(request))
            summary = _summarize_result(settings, result)
            print(f"\n  {persona.name}: {summary}\n")
            if voice:
                voice.speak(summary[:1500])
    except KeyboardInterrupt:
        pass
    print(f"\n  {persona.name}: {farewell}")
    if voice:
        voice.speak(farewell)
    return 0


def cmd_build_app(settings: Settings, spec: str, name: str, yes_to_all: bool = False) -> int:
    import asyncio as _asyncio

    from aether.llm.router import ModelRouter
    from aether.pipeline.app_builder import AppBuilderPipeline

    router = ModelRouter(settings)
    if not router.ping():
        print("Ollama is not running. Run: aether doctor")
        return 1
    print(f"Engineering: {spec}\n  Models: {router.routing_table()}\n")

    def on_event(kind: str, data: dict) -> None:
        if kind != "await_approval":
            print(f"  [{kind}] {str(data)[:160]}")

    pipe = AppBuilderPipeline(router, settings, on_event=on_event)
    result = _asyncio.run(pipe.build(spec, project_name=name, approve=_cli_approve(yes_to_all)))
    if result.get("status") == "cancelled":
        print("\nCancelled. Nothing was written.")
        return 0
    if result.get("status") != "complete":
        print(f"Failed: {result.get('error')}")
        return 1
    print(f"\nProject ready: {result['dir']}")
    print(f"  Install: {result.get('install_command')}")
    print(f"  Run:     {result.get('run_command')}")
    return 0


def cmd_home(settings: Settings, action: str, device: str) -> int:
    from aether.integrations.smart_home import SmartHome

    home = SmartHome(settings.homeassistant_url, settings.homeassistant_token)
    if not home.is_configured():
        print("Smart home not configured. Set HOMEASSISTANT_URL and HOMEASSISTANT_TOKEN in .env.")
        return 1
    if not home.ping():
        print(f"Cannot reach Home Assistant at {settings.homeassistant_url}")
        return 1
    if action == "list":
        for e in home.entities()[:80]:
            print(f"  {e['state']:>10}  {e['entity_id']}  ({e['name']})")
        return 0
    match = home.find_entity(device)
    if not match:
        print(f"Device not found: {device}")
        return 1
    if action == "on":
        home.turn_on(match["entity_id"])
    elif action == "off":
        home.turn_off(match["entity_id"])
    print(f"{match['name']} -> {action}")
    return 0


def cmd_capabilities(settings: Settings) -> int:
    from aether.capabilities import describe_capabilities

    print("A.E.T.H.E.R. capabilities\n")
    for cap in describe_capabilities(settings):
        status = "ready" if cap["available"] else "needs setup"
        print(f"  [{status:>10}] {cap['name']}")
        print(f"               {cap['description']}")
        if cap.get("how"):
            print(f"               -> {cap['how']}")
    return 0


def cmd_stop(settings: Settings) -> int:
    from pathlib import Path as _Path

    stop_file = _Path(settings.data_dir) / "STOP"
    stop_file.parent.mkdir(parents=True, exist_ok=True)
    stop_file.write_text("cli stop", encoding="utf-8")
    print(f"Stop signal sent ({stop_file}). The autonomous agent will halt shortly.")
    return 0


def cmd_status(settings: Settings) -> int:
    traces = TraceStore(settings.traces_db)
    rows = traces.recent(10)
    print("Recent activity:")
    for row in rows:
        print(f"  [{row['kind']}] {row['agent']} {row['status']} {row.get('task_id', '')}")
    mem = Path(settings.data_dir) / "memory.json"
    if mem.exists():
        print(f"\nMemory store: {mem}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aether", description="A.E.T.H.E.R. local AI assistant")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="Check Ollama, API keys, paths")
    p_chat = sub.add_parser("chat", help="Single-turn chat")
    p_chat.add_argument("message", nargs="?", default="Hello!")
    p_chat.add_argument("--speak", action="store_true", help="Speak responses")

    p_wf = sub.add_parser("workflow", help="Run multi-agent learning workflow")
    p_wf.add_argument("topic", help="Topic to learn about")
    p_wf.add_argument("--toml", help="Workflow file in workflows/ (e.g. learn_topic.toml)")
    p_wf.add_argument("--speak", action="store_true")

    sub.add_parser("status", help="Show recent traces")

    p_learn = sub.add_parser("learn", help="Deep-learn a topic (multi-pass graduate curriculum)")
    p_learn.add_argument("topic", help='e.g. "robotic engineering and 3D modeling"')

    p_build = sub.add_parser("build", help="Build CAD + parts list + wiring from learned topic")
    p_build.add_argument("--topic", required=True, help="Topic you already learned")
    p_build.add_argument(
        "--project",
        required=True,
        help='Build description e.g. "habitable robot shell CAD for 3D print"',
    )
    p_build.add_argument("--printer", action="store_true", help="Upload STL to OctoPrint if configured")
    p_build.add_argument("--print", action="store_true", help="Start print after upload")

    p_auto = sub.add_parser("auto", help="Autonomous self-learning with your restrictions")
    p_auto.add_argument("mission", help='Overall goal, e.g. "become expert at robotics and design a robot"')
    p_auto.add_argument(
        "--restrictions",
        default="",
        help='Plain-language limits, e.g. "do not print, never spend money, stay on robotics"',
    )
    p_auto.add_argument("--max-iters", type=int, default=10, help="Max autonomous steps")
    p_auto.add_argument("--minutes", type=int, default=30, help="Max runtime in minutes")
    p_auto.add_argument("--allow-printing", action="store_true", help="Permit printing actions")
    p_auto.add_argument("--no-review", action="store_true", help="Disable the LLM safety reviewer")
    p_auto.add_argument("--yes", action="store_true", help="Auto-approve approval prompts (use with care)")

    p_do = sub.add_parser("do", help='Natural-language command: "build me a backend", "turn off the lights", etc.')
    p_do.add_argument("request", help="What you want, in plain words")
    p_do.add_argument("--speak", action="store_true", help="Speak the reply")
    p_do.add_argument("--yes", action="store_true", help="Skip the approval prompt before writing files")

    p_asst = sub.add_parser("assistant", help="Walk-in mode: greet + continuous conversation")
    p_asst.add_argument("--silent", action="store_true", help="Do not speak replies (text only)")
    p_asst.add_argument("--yes", action="store_true", help="Skip approval prompts before writing files")

    p_app = sub.add_parser("build-app", help="Engineer a full local application/backend from a spec")
    p_app.add_argument("spec", help='e.g. "FastAPI backend for an inventory system with SQLite"')
    p_app.add_argument("--name", default="", help="Optional project folder name")
    p_app.add_argument("--yes", action="store_true", help="Skip the approval prompt before writing files")

    p_home = sub.add_parser("home", help="Control smart home devices via Home Assistant")
    p_home.add_argument("action", choices=["list", "on", "off"], help="What to do")
    p_home.add_argument("device", nargs="?", default="", help="Device/entity name (for on/off)")

    sub.add_parser("capabilities", help="List everything A.E.T.H.E.R. can do")

    sub.add_parser("stop", help="Send the kill switch to a running autonomous agent")

    sub.add_parser("app", help="Launch the native desktop app (no browser)")

    p_web = sub.add_parser("web", help="Start the web UI")
    p_web.add_argument("--host", default="127.0.0.1")
    p_web.add_argument("--port", type=int, default=8787)
    p_web.add_argument(
        "--lan",
        action="store_true",
        help="Listen on all interfaces (0.0.0.0) so your phone on Wi-Fi can connect",
    )

    args = parser.parse_args(argv)
    settings = Settings.from_env()
    ensure_dirs(settings)

    if args.command == "doctor":
        return cmd_doctor(settings)
    if args.command == "chat":
        return cmd_chat(settings, args.message, args.speak)
    if args.command == "workflow":
        return asyncio.run(cmd_workflow(settings, args.topic, args.toml, args.speak))
    if args.command == "auto":
        return cmd_auto(
            settings,
            args.mission,
            args.restrictions,
            args.max_iters,
            args.minutes,
            args.allow_printing,
            args.no_review,
            args.yes,
        )
    if args.command == "do":
        return cmd_do(settings, args.request, args.speak, args.yes)
    if args.command == "assistant":
        return cmd_assistant(settings, args.silent, args.yes)
    if args.command == "build-app":
        return cmd_build_app(settings, args.spec, args.name, args.yes)
    if args.command == "home":
        return cmd_home(settings, args.action, args.device)
    if args.command == "capabilities":
        return cmd_capabilities(settings)
    if args.command == "app":
        from aether.desktop.app import run_app

        return run_app(settings)
    if args.command == "stop":
        return cmd_stop(settings)
    if args.command == "status":
        return cmd_status(settings)
    if args.command == "learn":
        return asyncio.run(cmd_learn(settings, args.topic))
    if args.command == "build":
        return asyncio.run(
            cmd_build(settings, args.topic, args.project, args.printer, args.print)
        )
    if args.command == "web":
        from aether.web.server import run_server

        host = "0.0.0.0" if args.lan else args.host
        print(f"A.E.T.H.E.R. web UI: http://{host}:{args.port}")
        if args.lan:
            print("  LAN mode: on your phone use http://<your-pc-ip>:%d" % args.port)
            print("  Install as app: Chrome → menu → Install app / Add to Home screen")
        run_server(host=host, port=args.port, lan=args.lan)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
