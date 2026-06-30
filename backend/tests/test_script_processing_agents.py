"""Script processing agents parsing regression tests."""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.chains.agents import ConsistencyCheckerAgent, ElementExtractorAgent
from app.schemas.skills.script_processing import ScriptConsistencyCheckResult, StudioScriptExtractionDraft


class _MockChatModel(BaseChatModel):
    def __init__(self, response: str) -> None:
        super().__init__()
        self._response = response

    @property
    def _llm_type(self) -> str:  # pragma: no cover
        return "mock-chat-model"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:  # type: ignore[override]
        msg = AIMessage(content=self._response)
        return ChatResult(generations=[ChatGeneration(message=msg)])


def _checker() -> ConsistencyCheckerAgent:
    return ConsistencyCheckerAgent(_MockChatModel('{"issues": [], "has_issues": false, "summary": null}'))


def _element_extractor(raw: str) -> ElementExtractorAgent:
    return ElementExtractorAgent(_MockChatModel(raw))


def test_consistency_format_output_accepts_unquoted_keys() -> None:
    agent = _checker()
    raw = "{issues: [], has_issues: false, summary: null}"

    result = agent.format_output(raw)

    assert isinstance(result, ScriptConsistencyCheckResult)
    assert result.has_issues is False
    assert result.issues == []


def test_consistency_format_output_accepts_python_literal_style() -> None:
    agent = _checker()
    raw = "{'issues': [], 'has_issues': False, 'summary': None}"

    result = agent.format_output(raw)

    assert isinstance(result, ScriptConsistencyCheckResult)
    assert result.has_issues is False
    assert result.summary is None


def test_consistency_format_output_accepts_model_call_style() -> None:
    agent = _checker()
    raw = "ScriptConsistencyCheckResult(issues=[], has_issues=False, summary=None)"

    result = agent.format_output(raw)

    assert isinstance(result, ScriptConsistencyCheckResult)
    assert result.has_issues is False
    assert result.issues == []


def test_element_extractor_unwraps_model_named_payload() -> None:
    """ElementExtractorAgent should keep candidates when LLM wraps the draft by model name."""
    raw = """
    {
      "StudioScriptExtractionDraft": {
        "project_id": "project-1",
        "chapter_id": "chapter-1",
        "script_text": "朝云端茶入室。苏东坡说：辛苦你了。",
        "characters": [
          {"name": "朝云", "description": "端茶入室的女子", "tags": []},
          {"name": "苏东坡", "description": "室内落座的文人", "tags": []}
        ],
        "scenes": [
          {"name": "室内茶席", "description": "古风室内茶席", "tags": [], "view_count": 1}
        ],
        "props": [
          {"name": "茶盏", "description": "朝云端着的茶盏", "tags": [], "view_count": 1}
        ],
        "costumes": [],
        "shots": [
          {
            "index": 1,
            "title": "朝云端茶",
            "script_excerpt": "朝云端茶入室。苏东坡说：辛苦你了。",
            "scene_name": "室内茶席",
            "character_names": ["朝云", "苏东坡"],
            "prop_names": ["茶盏"],
            "costume_names": [],
            "dialogue_lines": [
              {"index": 1, "text": "辛苦你了。", "line_mode": "DIALOGUE", "speaker_name": "苏东坡"}
            ],
            "actions": ["朝云端茶入室"]
          }
        ]
      }
    }
    """

    result = _element_extractor(raw).format_output(raw)

    assert isinstance(result, StudioScriptExtractionDraft)
    assert result.characters[0].name == "朝云"
    assert result.scenes[0].name == "室内茶席"
    assert result.props[0].name == "茶盏"
    assert result.shots[0].scene_name == "室内茶席"
    assert result.shots[0].dialogue_lines[0].text == "辛苦你了。"

