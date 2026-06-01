"""A.E.T.H.E.R. native desktop app.

Runs the full AI locally (no browser): chat, voice, autonomy, builds, smart home.
System tray + global hotkey (Ctrl+Alt+A) to summon from anywhere on Linux.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Dict, Optional

from aether.config import Settings, ensure_dirs
from aether.constants import AETHER_ACRONYM_LINE, AETHER_NAME

_ACTION_HINT = (
    "build", "engineer", "make me", "create", "scaffold", "learn", "study",
    "research", "turn on", "turn off", "switch on", "switch off", "toggle",
    "light", "plug", "thermostat", "design", "print", "japanese", "nihongo",
)


def _is_action(text: str) -> bool:
    t = text.lower()
    return any(w in t for w in _ACTION_HINT)


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except Exception:
        print("The desktop app needs PySide6. Install it with:")
        print("  pip install 'aether[desktop]'        # or")
        print("  sudo pacman -S pyside6                # Manjaro / Arch")
        return 1

    settings = Settings.from_env()
    ensure_dirs(settings)
    app = QApplication.instance() or QApplication([])
    app.setApplicationName(AETHER_NAME)
    app.setQuitOnLastWindowClosed(False)
    window = _build_window(settings)
    window.show()
    return app.exec()


def run_app(settings: Optional[Settings] = None) -> int:
    return main()


def _build_window(settings: Settings):
    from PySide6.QtCore import QObject, Qt, QThread, Signal
    from PySide6.QtGui import QAction, QFont, QIcon, QKeySequence, QShortcut
    from PySide6.QtWidgets import (
        QCheckBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMenu,
        QMessageBox,
        QPushButton,
        QSpinBox,
        QSystemTrayIcon,
        QTabWidget,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )

    from aether.brain.commander import Commander
    from aether.constants import AETHER_ACRONYM_FULL
    from aether.llm.router import ModelRouter
    from aether.persona import build_persona, time_greeting
    from aether.voice.listen import VoiceListener
    from aether.voice.manager import VoiceManager

    persona = build_persona(settings.persona, settings.assistant_name, settings.user_title)

    class CommandWorker(QObject):
        event = Signal(str, dict)
        done = Signal(dict)
        approval_needed = Signal(dict)

        def __init__(self, request: str, ask_before_build: bool):
            super().__init__()
            self.request = request
            self.ask = ask_before_build
            self._approve_event = threading.Event()
            self._approve_result = False

        def provide_approval(self, ok: bool) -> None:
            self._approve_result = ok
            self._approve_event.set()

        def _approve(self, plan: Dict) -> bool:
            if not self.ask:
                return True
            self._approve_event.clear()
            self.approval_needed.emit(plan)
            self._approve_event.wait(timeout=300)
            return self._approve_result

        def run(self) -> None:
            try:
                router = ModelRouter(settings)
                commander = Commander(
                    settings,
                    router,
                    on_event=lambda e, d: self.event.emit(e, dict(d) if isinstance(d, dict) else {"data": str(d)}),
                    approve=self._approve,
                )
                result = asyncio.run(commander.run(self.request))
            except Exception as exc:
                result = {"intent": "error", "error": str(exc)}
            self.done.emit(result)

    class AutonomyWorker(QObject):
        log = Signal(str)
        done = Signal(dict)
        approval_needed = Signal(dict)

        def __init__(self, mission: str, restrictions: str, max_iters: int, minutes: int):
            super().__init__()
            self.mission = mission
            self.restrictions = restrictions
            self.max_iters = max_iters
            self.minutes = minutes
            self._control = None
            self._approve_event = threading.Event()
            self._approve_result = False

        def provide_approval(self, ok: bool) -> None:
            self._approve_result = ok
            self._approve_event.set()

        def stop(self) -> None:
            if self._control:
                self._control.stop("desktop stop")

        def _approve(self, action: Dict) -> bool:
            self._approve_event.clear()
            self.approval_needed.emit(action)
            self._approve_event.wait(timeout=120)
            return self._approve_result

        def run(self) -> None:
            from aether.autonomy.agent import AutonomousAgent
            from aether.autonomy.control import AutonomyControl
            from aether.autonomy.guardrails import Guardrails

            self._control = AutonomyControl(settings.data_dir)

            def _request_approval(action: Dict, timeout: float = 120) -> bool:
                self._approve_event.clear()
                self.approval_needed.emit(action)
                got = self._approve_event.wait(timeout=timeout)
                return got and self._approve_result

            self._control.request_approval = _request_approval  # type: ignore[method-assign]

            guardrails = Guardrails.from_prompt(
                self.restrictions,
                max_iterations=self.max_iters,
                max_runtime_minutes=self.minutes,
            )
            router = ModelRouter(settings)
            agent = AutonomousAgent(
                router,
                settings,
                guardrails,
                control=self._control,
                on_event=lambda kind, entry: self.log.emit(f"[{kind}] {entry.get('message', '')[:200]}"),
            )
            result = agent.run(self.mission)
            self.done.emit(result)

    class ListenThread(QThread):
        heard = Signal(str)

        def __init__(self, listener: VoiceListener):
            super().__init__()
            self.listener = listener

        def run(self) -> None:
            self.listener.listen_loop(
                lambda text: self.heard.emit(text),
                should_stop=lambda: self.isInterruptionRequested(),
            )

        def stop(self) -> None:
            self.requestInterruption()
            self.listener.stop()

    class Window(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle(AETHER_NAME)
            self.resize(900, 720)
            self.voice = VoiceManager(settings.elevenlabs_api_key, settings.elevenlabs_voice_id)
            self.listener = VoiceListener()
            self.listen_thread: Optional[ListenThread] = None
            self.thread: Optional[QThread] = None
            self.worker: Optional[CommandWorker] = None
            self.auto_thread: Optional[QThread] = None
            self.auto_worker: Optional[AutonomyWorker] = None
            self.busy = False
            self._hotkey_handle = None
            self._build_ui()
            self._setup_tray()
            self._setup_hotkey()
            self._greet()

        def _build_ui(self):
            central = QWidget()
            root = QVBoxLayout(central)

            brand = QLabel(AETHER_NAME)
            brand.setFont(QFont("monospace", 22, QFont.Bold))
            brand.setStyleSheet("color:#38bdf8;")
            acronym = QLabel(AETHER_ACRONYM_LINE)
            acronym.setStyleSheet("color:#6a8fa8; font-family:monospace; font-size:11px;")
            subtitle = QLabel(AETHER_ACRONYM_FULL)
            subtitle.setStyleSheet("color:#4a6070; font-size:10px;")
            root.addWidget(brand)
            root.addWidget(acronym)
            root.addWidget(subtitle)

            header = QHBoxLayout()
            self.status = QLabel("● ready")
            self.status.setStyleSheet("color:#38bdf8; font-family:monospace;")
            header.addStretch()
            header.addWidget(self.status)
            root.addLayout(header)

            self.tabs = QTabWidget()
            self.tabs.addTab(self._chat_tab(), "Assistant")
            self.tabs.addTab(self._autonomy_tab(), "Autonomy")
            root.addWidget(self.tabs, 1)

            self.setCentralWidget(central)
            self.setStyleSheet(
                "QMainWindow{background:#070a0e;} QTabWidget::pane{border:1px solid #1d2a36;}"
                "QTabBar::tab{background:#11161d;color:#8aa;padding:8px 16px;border:1px solid #243240;}"
                "QTabBar::tab:selected{background:#16212c;color:#cfe;}"
                "QPushButton{background:#16212c;color:#cfe;border:1px solid #243240;border-radius:8px;padding:9px 16px;}"
                "QPushButton:hover{background:#1d2c3a;} QCheckBox{color:#8aa;}"
            )

            QShortcut(QKeySequence("Ctrl+Alt+A"), self, self._summon)

        def _chat_tab(self) -> QWidget:
            w = QWidget()
            lay = QVBoxLayout(w)
            self.log = QTextEdit()
            self.log.setReadOnly(True)
            self.log.setStyleSheet(
                "background:#0b0f14;color:#d7e3ee;border:1px solid #1d2a36;border-radius:8px;padding:10px;"
            )
            lay.addWidget(self.log, 1)
            controls = QHBoxLayout()
            self.input = QLineEdit()
            self.input.setPlaceholderText(f"Tell {persona.name} what to do…")
            self.input.returnPressed.connect(self._on_submit)
            send = QPushButton("Send")
            send.clicked.connect(self._on_submit)
            self.mic = QPushButton("🎤 Listen")
            self.mic.setCheckable(True)
            self.mic.clicked.connect(self._toggle_listen)
            controls.addWidget(self.input, 1)
            controls.addWidget(send)
            controls.addWidget(self.mic)
            lay.addLayout(controls)
            opts = QHBoxLayout()
            self.speak_cb = QCheckBox("Speak replies")
            self.speak_cb.setChecked(True)
            self.ask_cb = QCheckBox("Ask before writing files")
            self.ask_cb.setChecked(True)
            opts.addWidget(self.speak_cb)
            opts.addWidget(self.ask_cb)
            opts.addStretch()
            lay.addLayout(opts)
            return w

        def _autonomy_tab(self) -> QWidget:
            w = QWidget()
            lay = QVBoxLayout(w)
            lay.addWidget(QLabel("Mission (what should it work toward?)"))
            self.auto_mission = QLineEdit()
            self.auto_mission.setPlaceholderText("Master Japanese and build a vocabulary flashcard app")
            lay.addWidget(self.auto_mission)
            lay.addWidget(QLabel("Restrictions (plain language limits)"))
            self.auto_restrict = QLineEdit()
            self.auto_restrict.setPlaceholderText("do not print, stay on japanese topics, ask before writing files")
            lay.addWidget(self.auto_restrict)
            limits = QHBoxLayout()
            limits.addWidget(QLabel("Max steps"))
            self.auto_iters = QSpinBox()
            self.auto_iters.setRange(1, 50)
            self.auto_iters.setValue(8)
            limits.addWidget(self.auto_iters)
            limits.addWidget(QLabel("Minutes"))
            self.auto_mins = QSpinBox()
            self.auto_mins.setRange(1, 240)
            self.auto_mins.setValue(20)
            limits.addWidget(self.auto_mins)
            limits.addStretch()
            lay.addLayout(limits)
            btns = QHBoxLayout()
            self.auto_start = QPushButton("Start")
            self.auto_start.clicked.connect(self._auto_start)
            self.auto_stop = QPushButton("STOP")
            self.auto_stop.setStyleSheet("background:#dc2626;color:#fff;font-weight:bold;")
            self.auto_stop.clicked.connect(self._auto_stop)
            self.auto_state = QLabel("idle")
            btns.addWidget(self.auto_start)
            btns.addWidget(self.auto_stop)
            btns.addWidget(self.auto_state)
            btns.addStretch()
            lay.addLayout(btns)
            self.auto_log = QTextEdit()
            self.auto_log.setReadOnly(True)
            self.auto_log.setStyleSheet("background:#0b0f14;color:#d7e3ee;border:1px solid #1d2a36;border-radius:8px;")
            lay.addWidget(self.auto_log, 1)
            return w

        def _setup_tray(self):
            self.tray = QSystemTrayIcon(self)
            self.tray.setToolTip(AETHER_NAME)
            menu = QMenu()
            show_act = QAction("Show A.E.T.H.E.R.", self)
            show_act.triggered.connect(self._summon)
            listen_act = QAction("Start listening", self)
            listen_act.triggered.connect(lambda: self._toggle_listen(force_on=True))
            quit_act = QAction("Quit", self)
            quit_act.triggered.connect(self._quit_app)
            menu.addAction(show_act)
            menu.addAction(listen_act)
            menu.addSeparator()
            menu.addAction(quit_act)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(self._tray_activated)
            self.tray.show()

        def _setup_hotkey(self):
            try:
                from pynput import keyboard

                def on_activate():
                    self._summon()

                self._hotkey_handle = keyboard.GlobalHotKeys({"<ctrl>+<alt>+a": on_activate})
                t = threading.Thread(target=self._hotkey_handle.start, daemon=True)
                t.start()
            except Exception:
                pass  # in-window Ctrl+Alt+A shortcut still works

        def _tray_activated(self, reason):
            from PySide6.QtWidgets import QSystemTrayIcon

            if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
                self._summon()

        def _summon(self):
            self.showNormal()
            self.raise_()
            self.activateWindow()
            self.input.setFocus()

        def _quit_app(self):
            if self.listen_thread:
                self.listen_thread.stop()
            if self.auto_worker:
                self.auto_worker.stop()
            if self._hotkey_handle:
                try:
                    self._hotkey_handle.stop()
                except Exception:
                    pass
            from PySide6.QtWidgets import QApplication

            QApplication.quit()

        def _append(self, who: str, text: str):
            color = "#38bdf8" if who == persona.name else "#9fb4c6" if who == "you" else "#5b6b7a"
            self.log.append(f'<span style="color:{color}"><b>{who}:</b> {text}</span>')

        def _auto_append(self, text: str):
            self.auto_log.append(text)
            self.auto_log.verticalScrollBar().setValue(self.auto_log.verticalScrollBar().maximum())

        def _set_status(self, text: str, color: str = "#38bdf8"):
            self.status.setText(f"● {text}")
            self.status.setStyleSheet(f"color:{color}; font-family:monospace;")

        def _speak(self, text: str):
            if self.speak_cb.isChecked() and text:
                threading.Thread(target=lambda: self.voice.speak(text[:1500]), daemon=True).start()

        def _greet(self):
            msg = time_greeting(persona, settings.user_title)
            self._append(persona.name, msg)
            self._speak(msg)

        def _on_submit(self):
            text = self.input.text().strip()
            if not text or self.busy:
                return
            self.input.clear()
            self._dispatch(text)

        def _dispatch(self, text: str):
            self._append("you", text)
            self.busy = True
            self._set_status("working…", "#fbbf24")
            self.thread = QThread()
            self.worker = CommandWorker(text, self.ask_cb.isChecked())
            self.worker.moveToThread(self.thread)
            self.thread.started.connect(self.worker.run)
            self.worker.event.connect(self._on_event)
            self.worker.approval_needed.connect(self._on_approval)
            self.worker.done.connect(self._on_done)
            self.worker.done.connect(self.thread.quit)
            self.thread.start()

        def _on_event(self, kind: str, data: dict):
            if kind == "intent":
                self._set_status(f"{data.get('intent', '')}…", "#fbbf24")
            elif kind == "file_done":
                self._append("·", f"wrote {data.get('path')}")
            elif kind == "planned":
                self._append("·", f"planning {data.get('project')} ({data.get('file_count')} files)")

        def _on_approval(self, plan: dict):
            files = "\n".join(f"  - {f.get('path')}" for f in plan.get("files", [])[:30])
            box = QMessageBox(self)
            box.setWindowTitle("Approve build")
            box.setText(f"{plan.get('project_name','app')}\n\nWrite these files?\n{files}")
            box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            ok = box.exec() == QMessageBox.Yes
            if self.worker:
                self.worker.provide_approval(ok)

        def _on_done(self, result: dict):
            self.busy = False
            self._set_status("ready", "#38bdf8")
            summary = self._summarize(result)
            self._append(persona.name, summary)
            self._speak(summary)

        def _summarize(self, r: dict) -> str:
            t = settings.user_title
            intent = r.get("intent")
            if intent == "error":
                return f"I hit a problem, {t}: {r.get('error')}"
            if intent == "chat":
                return r.get("reply", "")
            if intent == "build_app":
                if r.get("status") == "cancelled":
                    return f"Cancelled, {t}. Nothing was written."
                return f"Done, {t}. Built {len(r.get('files', []))} files in {r.get('dir')}."
            if intent == "learn":
                track = (r.get("synthesis") or {}).get("track") if isinstance(r.get("synthesis"), dict) else None
                extra = " (Japanese track)" if track == "japanese" else ""
                return f"I've finished studying {r.get('topic')}{extra}, {t}."
            if intent == "smart_home":
                if r.get("action"):
                    return f"{r.get('device')} is now {r.get('action')}, {t}."
                return r.get("message") or f"Done, {t}."
            return f"Done, {t}."

        def _toggle_listen(self, force_on: bool = False):
            if force_on:
                self.mic.setChecked(True)
            if self.mic.isChecked():
                if not self.listener.available():
                    self.mic.setChecked(False)
                    QMessageBox.information(self, "Voice not ready", "Install aether[stt] and a Vosk model.")
                    return
                self._set_status(f'listening for "{settings.wake_word}"…', "#34d399")
                self.mic.setText("🛑 Stop")
                self.listen_thread = ListenThread(self.listener)
                self.listen_thread.heard.connect(self._on_heard)
                self.listen_thread.start()
            else:
                self.mic.setText("🎤 Listen")
                self._set_status("ready")
                if self.listen_thread:
                    self.listen_thread.stop()
                    self.listen_thread = None

        def _on_heard(self, text: str):
            wake = settings.wake_word.lower()
            if wake not in text.lower():
                return
            after = text.lower().split(wake, 1)[1].strip(" ,.")
            cmd = after or text
            if cmd and not self.busy:
                self._summon()
                self._dispatch(cmd)

        def _auto_start(self):
            mission = self.auto_mission.text().strip()
            if not mission:
                QMessageBox.warning(self, "Mission required", "Enter a mission first.")
                return
            self.auto_start.setEnabled(False)
            self.auto_state.setText("running")
            self.auto_log.clear()
            self.auto_thread = QThread()
            self.auto_worker = AutonomyWorker(
                mission,
                self.auto_restrict.text(),
                self.auto_iters.value(),
                self.auto_mins.value(),
            )
            self.auto_worker.moveToThread(self.auto_thread)
            self.auto_thread.started.connect(self.auto_worker.run)
            self.auto_worker.log.connect(self._auto_append)
            self.auto_worker.approval_needed.connect(self._auto_approval)
            self.auto_worker.done.connect(self._auto_done)
            self.auto_worker.done.connect(self.auto_thread.quit)
            self.auto_thread.start()

        def _auto_stop(self):
            if self.auto_worker:
                self.auto_worker.stop()
            self.auto_state.setText("stopping…")
            self._auto_append("[control] STOP requested")

        def _auto_approval(self, action: dict):
            box = QMessageBox(self)
            box.setWindowTitle("Autonomy approval")
            box.setText(f"Allow: {action.get('action')}: {action.get('description', '')[:200]}")
            ok = box.exec() == QMessageBox.Yes
            if self.auto_worker:
                self.auto_worker.provide_approval(ok)

        def _auto_done(self, result: dict):
            self.auto_start.setEnabled(True)
            self.auto_state.setText(result.get("state", "stopped"))
            self._auto_append(f"Finished. Iterations: {result.get('iterations')}")
            self._speak(f"Autonomous run finished, {settings.user_title}.")

        def closeEvent(self, ev):
            from PySide6.QtWidgets import QSystemTrayIcon

            ev.ignore()
            self.hide()
            self.tray.showMessage(
                AETHER_NAME,
                "Still running in the tray. Press Ctrl+Alt+A to open.",
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )

    return Window()


if __name__ == "__main__":
    raise SystemExit(main())
