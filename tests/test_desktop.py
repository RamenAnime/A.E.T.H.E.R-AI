"""Desktop + offline-voice tests that do not require PySide6 or Vosk installed."""

from aether.desktop import app as desktop_app
from aether.voice import listen


def test_stt_available_is_bool():
    assert isinstance(listen.stt_available(), bool)


def test_find_model_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("AETHER_VOSK_MODEL", raising=False)
    # An empty/nonexistent explicit path should not resolve.
    assert listen.find_model(str(tmp_path / "nope")) in (None, *_existing_defaults())


def _existing_defaults():
    # On some machines a default path might exist; allow it but it must be a str then.
    found = listen.find_model("")
    return (found,) if found else ()


def test_find_model_env(tmp_path, monkeypatch):
    model = tmp_path / "vosk"
    model.mkdir()
    (model / "conf").write_text("x", encoding="utf-8")
    monkeypatch.setenv("AETHER_VOSK_MODEL", str(model))
    assert listen.find_model("") == str(model)


def test_voice_listener_unavailable_without_model(monkeypatch):
    monkeypatch.delenv("AETHER_VOSK_MODEL", raising=False)
    vl = listen.VoiceListener(model_path="/definitely/not/here")
    # Either Vosk is not installed or the model is missing -> not available.
    assert vl.available() is False


def test_is_action_classifier():
    assert desktop_app._is_action("build me a backend") is True
    assert desktop_app._is_action("turn off the lights") is True
    assert desktop_app._is_action("how are you today") is False


def test_main_without_pyside_is_graceful(monkeypatch, capsys):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("PySide6"):
            raise ImportError("no pyside")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    rc = desktop_app.main()
    assert rc == 1
    assert "PySide6" in capsys.readouterr().out
