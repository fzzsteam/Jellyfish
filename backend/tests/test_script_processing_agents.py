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


def test_element_extractor_coerces_speech_line_mode_alias() -> None:
    """deepseek 系模型习惯把普通对白标成 "SPEECH"（不在 schema 字面量里），

    实测对该模型的真实输出 100% 复现：一旦命中就导致校验失败、草稿被整体丢弃，
    表现为"一键分镜拆分完成但没有提取出任何资产"。这里回归验证 "SPEECH" 会被
    归一化为合法的 "DIALOGUE"，不再触发 pydantic 校验错误。
    """
    raw = """
    {
      "project_id": "project-1",
      "chapter_id": "chapter-1",
      "characters": [{"name": "苏东坡", "description": "文人", "tags": []}],
      "scenes": [{"name": "合江楼", "description": "居所", "tags": [], "view_count": 1}],
      "props": [],
      "costumes": [],
      "shots": [
        {
          "index": 1,
          "title": "苏东坡感叹",
          "script_excerpt": "苏东坡说：方有空寓岭海之叹啊……",
          "scene_name": "合江楼",
          "character_names": ["苏东坡"],
          "prop_names": [],
          "costume_names": [],
          "dialogue_lines": [
            {"index": 1, "text": "方有空寓岭海之叹啊……", "line_mode": "SPEECH", "speaker_name": "苏东坡"}
          ],
          "actions": ["苏东坡感叹"]
        }
      ]
    }
    """

    result = _element_extractor(raw).format_output(raw)

    assert isinstance(result, StudioScriptExtractionDraft)
    assert result.shots[0].dialogue_lines[0].line_mode == "DIALOGUE"


def test_element_extractor_defaults_unknown_line_mode_to_dialogue() -> None:
    """deepseek 系模型的 line_mode 漂移不是固定几个别名能穷举完的——同一条 pipeline

    先后见过 "SPEECH"、"NORMAL" 等不同写法。这里回归验证：即便遇到一个完全没有
    收录进别名表的新值（如 "NORMAL"），也会兜底成 DIALOGUE 而不是让 pydantic
    校验失败、把整份原本正确的草稿（角色/场景/道具都提取到了）整体丢弃。
    """
    raw = """
    {
      "project_id": "project-1",
      "chapter_id": "chapter-1",
      "characters": [{"name": "苏东坡", "description": "文人", "tags": []}],
      "scenes": [{"name": "合江楼", "description": "居所", "tags": [], "view_count": 1}],
      "props": [],
      "costumes": [],
      "shots": [
        {
          "index": 1,
          "title": "苏东坡感叹",
          "script_excerpt": "苏东坡说：方有空寓岭海之叹啊……",
          "scene_name": "合江楼",
          "character_names": ["苏东坡"],
          "prop_names": [],
          "costume_names": [],
          "dialogue_lines": [
            {"index": 1, "text": "方有空寓岭海之叹啊……", "line_mode": "NORMAL", "speaker_name": "苏东坡"}
          ],
          "actions": ["苏东坡感叹"]
        }
      ]
    }
    """

    result = _element_extractor(raw).format_output(raw)

    assert isinstance(result, StudioScriptExtractionDraft)
    assert result.shots[0].dialogue_lines[0].line_mode == "DIALOGUE"

