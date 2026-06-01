"""Japanese deep-research track detection."""

from aether.agents.deep_research import DeepResearchAgent, JAPANESE_PASSES, _JA_TOPIC


def test_japanese_topic_detection():
    assert _JA_TOPIC.search("learn Japanese language")
    assert _JA_TOPIC.search("JLPT N2 grammar")
    assert _JA_TOPIC.search("日本語")
    assert not _JA_TOPIC.search("robotic engineering")


def test_japanese_pass_count():
    assert len(JAPANESE_PASSES) == 6


class _FakeLLM:
    def complete(self, prompt, system="", model=None, task="general"):
        return "content"


def test_japanese_track_in_output():
    agent = DeepResearchAgent(_FakeLLM())
    # Patch _llm_prompt to avoid long loop
    agent._llm_prompt = lambda _s, _u: "concept: test\n- fact one"
    result = agent.execute({"topic": "Japanese language mastery", "planner_output": {"plan": ""}})
    assert result.output["synthesis"]["track"] == "japanese"
    assert "writing_systems" in result.output["curriculum"].lower() or "Writing Systems" in result.output["curriculum"]
