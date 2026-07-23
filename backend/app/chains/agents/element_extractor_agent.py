"""项目级信息提取 Agent：ElementExtractorAgent"""

from __future__ import annotations

import re
from typing import Any

from langchain_core.prompts import PromptTemplate

from app.chains.agents.base import AgentBase
from app.schemas.skills.script_processing import StudioScriptExtractionDraft

# 模型偶尔会把枚举字段写成中文近义词或漏掉下划线的变体（如 "旁白"/"VOICEOVER"），
# 与 schema 要求的字面量（"VOICE_OVER"）不完全一致时 pydantic 会直接报错，导致
# 整份原本提取正确的草稿（场景/角色/对白都有内容）被当作校验失败整体丢弃。
# 这里在写入 pydantic 模型前做一次宽松归一化，只影响格式，不改变模型判断的语义。
_LINE_MODE_ALIASES: dict[str, str] = {
    "旁白": "VOICE_OVER",
    "旁白音": "VOICE_OVER",
    "VO": "VOICE_OVER",
    "V.O.": "VOICE_OVER",
    "画外音": "OFF_SCREEN",
    "OS": "OFF_SCREEN",
    "O.S.": "OFF_SCREEN",
    "OC": "OFF_SCREEN",
    "O.C.": "OFF_SCREEN",
    "电话": "PHONE",
    "电话音": "PHONE",
    "对白": "DIALOGUE",
    "台词": "DIALOGUE",
}
_VALID_LINE_MODES = ("DIALOGUE", "VOICE_OVER", "OFF_SCREEN", "PHONE")
_VALID_CAMERA_SHOTS = ("ECU", "CU", "MCU", "MS", "MLS", "LS", "ELS")
_VALID_ANGLES = ("EYE_LEVEL", "HIGH_ANGLE", "LOW_ANGLE", "BIRD_EYE", "DUTCH", "OVER_SHOULDER")
_VALID_MOVEMENTS = (
    "STATIC", "PAN", "TILT", "DOLLY_IN", "DOLLY_OUT", "TRACK",
    "CRANE", "HANDHELD", "STEADICAM", "ZOOM_IN", "ZOOM_OUT",
)


def _collapse(text: str) -> str:
    """去掉空格/下划线/连字符/点号后转大写，用于宽松比对（"V.O." / "VO" / "v_o" 视为同一个值）。"""
    return re.sub(r"[\s_.\-]", "", text).upper()


def _coerce_enum_value(
    value: Any,
    *,
    valid_values: tuple[str, ...],
    aliases: dict[str, str] | None = None,
) -> Any:
    """把近似枚举值（中文同义词/缩写/缺下划线/大小写不一致）纠正为合法字面量。

    无法识别时原样返回，交给 pydantic 校验按原有行为报错，不吞掉真正异常的输入。
    """
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if stripped in valid_values:
        return stripped
    collapsed = _collapse(stripped)
    for candidate in valid_values:
        if _collapse(candidate) == collapsed:
            return candidate
    if aliases:
        for alias, target in aliases.items():
            if _collapse(alias) == collapsed:
                return target
    return value


_SCRIPT_EXTRACTOR_SYSTEM_PROMPT = """\
你是\"Studio 信息提取员\"。你的任务是：基于章节原文、分镜结果（以及可选的一致性检查输出），输出可直接导入 Studio 的草稿结构 StudioScriptExtractionDraft（注意：ID 由导入 API 生成，因此这里全部使用 name 做引用键）。

输出 StudioScriptExtractionDraft：
- project_id（必填）
- chapter_id（必填）
- characters: [{name, description, costume_name?, prop_names[], tags[]}]
- scenes/props/costumes: [{name, description, tags[], prompt_template_id?, view_count}]
- shots: [{index, title, script_excerpt, scene_name?, character_names[], prop_names[], costume_names[], dialogue_lines[], actions[], semantic_suggestion?}]
  - dialogue_lines: [{index, text, line_mode, speaker_name?, target_name?}]
  - semantic_suggestion: {camera_shot?, angle?, movement?, duration?, action_beats[], notes?}

强约束：
- 同名实体在输出中只出现一次（全局去重）；shots 中引用必须使用同一名称
- shots.index 必须覆盖并对应输入分镜中的 index（不要跳号）
- 不要输出任何 id 字段（包括 char_001 等），由导入 API 生成

一致性强约束（必须严格遵守，否则导入会失败）：
- 先输出全局 characters/scenes/props/costumes 列表，再输出 shots；并把它们视为“字典”。
- shots[*].character_names / prop_names / costume_names / scene_name 只能从对应全局列表的 name 中选择（完全一致的字符串），禁止生成任何未在全局列表中出现的新名字。
- 禁止“同义名/括号变体/临时称呼”漂移：例如禁止在 shots 中写「女子（群）」但在 characters 中没有该条目；禁止「仙女A」与「仙女 A」混用。
- 遇到群体角色/泛指角色（如“女子（群）”“群众”“村民们”）：必须在 characters 列表中创建一条同名角色（name 完全一致），并在 shots 中引用该 name。
- 对于难以确定是否同一角色的称呼：宁可在 characters 里拆成两条不同 name，也不要在 shots 中凭空换名。
- 输出 shots 之前，必须做“全集校验”并补齐缺失：所有 shots[*] 中出现的 character_names/prop_names/costume_names/scene_name 的名字集合，必须都能在对应全局列表（characters/props/costumes/scenes）的 name 中找到；如果有缺失，必须在全局列表中补齐对应条目（描述可最小化，但 name 必须完全一致），禁止用别名替换来绕过。
- 角色名/场景名必须原样保留字符细节：包括全角/半角括号、空格、标点，不要自动做任何规范化或替换（例如不能把「女子（群）」改成「女子(群)」或「女子 （群）」）。
- 严格区分：shots[*].title 是“镜头标题”（一句话描述该镜头画面/动作），不要拿它当作 scenes 的 scene 名；shots[*].scene_name 才是场景名称，必须来自 scenes 全局列表的 name。
- 除实体与对白外，还必须尽量补充镜头语言默认建议：`camera_shot` / `angle` / `movement` / `duration`。
- `camera_shot` 只能输出：ECU / CU / MCU / MS / MLS / LS / ELS。
- `angle` 只能输出：EYE_LEVEL / HIGH_ANGLE / LOW_ANGLE / BIRD_EYE / DUTCH / OVER_SHOULDER。
- `movement` 只能输出：STATIC / PAN / TILT / DOLLY_IN / DOLLY_OUT / TRACK / CRANE / HANDHELD / STEADICAM / ZOOM_IN / ZOOM_OUT。
- `duration` 必须输出正整数秒数；若无法判断，可省略。
- `action_beats` 需要输出 2-4 条按镜头内部时间顺序排列的动作拍点；每一条只描述一个主要动作或状态变化，不要写成长段文学描述。
- `semantic_suggestion` 是“镜头默认语义建议”，不是最终生成提示词，不要输出提示词式修饰文本。

输入：
- project_id
- chapter_id
- script_text（章节原文；用于补充分镜摘要中缺失的角色、场景、道具和对白）
- script_division_json（ScriptDivisionResult）
- consistency_json（可选）

只输出 JSON。
"""

SCRIPT_EXTRACTOR_PROMPT = PromptTemplate(
    input_variables=["project_id", "chapter_id", "script_text", "script_division_json", "consistency_json"],
    template=(
        "## project_id\n{project_id}\n\n"
        "## chapter_id\n{chapter_id}\n\n"
        "## 章节原文\n{script_text}\n\n"
        "## 一致性检查（可选）\n{consistency_json}\n\n"
        "## 分镜结果\n{script_division_json}\n\n"
        "## 输出\n"
    ),
)


class ElementExtractorAgent(AgentBase[StudioScriptExtractionDraft]):
    """项目级信息提取（最终输出）：输入分镜结果，产出全局实体表 + 逐镜关联。"""

    @property
    def system_prompt(self) -> str:
        return _SCRIPT_EXTRACTOR_SYSTEM_PROMPT

    @property
    def prompt_template(self) -> PromptTemplate:
        return SCRIPT_EXTRACTOR_PROMPT

    @property
    def output_model(self) -> type[StudioScriptExtractionDraft]:
        return StudioScriptExtractionDraft

    def _unwrap_model_payload(self, data: dict[str, Any]) -> dict[str, Any]:
        """兼容 LLM 把结果包在模型名或通用 data/result 字段下的返回形状。"""

        for key in ("StudioScriptExtractionDraft", "studio_script_extraction_draft", "data", "result", "draft"):
            value = data.get(key)
            if isinstance(value, dict):
                return dict(value)
        return data

    def _normalize_shot(self, shot: Any, index: int) -> dict[str, Any]:
        """把常见旧字段名归一成 `StudioShotDraft` 需要的字段。"""

        if not isinstance(shot, dict):
            return {"index": index, "title": "", "script_excerpt": str(shot or "")}
        normalized = dict(shot)
        if "index" not in normalized:
            normalized["index"] = normalized.pop("shot_index", index)
        if "title" not in normalized:
            normalized["title"] = normalized.pop("shot_name", normalized.pop("shot_title", ""))
        normalized.setdefault("script_excerpt", "")
        for key in ("character_names", "prop_names", "costume_names", "dialogue_lines", "actions"):
            if not isinstance(normalized.get(key), list):
                normalized[key] = []
        normalized["dialogue_lines"] = [
            self._normalize_dialogue_line(line) for line in normalized["dialogue_lines"]
        ]
        suggestion = normalized.get("semantic_suggestion")
        if isinstance(suggestion, dict):
            normalized["semantic_suggestion"] = self._normalize_semantic_suggestion(suggestion)
        return normalized

    def _normalize_dialogue_line(self, line: Any) -> Any:
        """纠正对白行的 `line_mode`（常见漂移：中文同义词 / 漏下划线）。"""

        if not isinstance(line, dict):
            return line
        normalized = dict(line)
        if "line_mode" in normalized:
            normalized["line_mode"] = _coerce_enum_value(
                normalized["line_mode"],
                valid_values=_VALID_LINE_MODES,
                aliases=_LINE_MODE_ALIASES,
            )
        return normalized

    def _normalize_semantic_suggestion(self, suggestion: dict[str, Any]) -> dict[str, Any]:
        """纠正镜头语义建议里的景别/机位/运镜枚举值格式漂移。"""

        normalized = dict(suggestion)
        if "camera_shot" in normalized:
            normalized["camera_shot"] = _coerce_enum_value(normalized["camera_shot"], valid_values=_VALID_CAMERA_SHOTS)
        if "angle" in normalized:
            normalized["angle"] = _coerce_enum_value(normalized["angle"], valid_values=_VALID_ANGLES)
        if "movement" in normalized:
            normalized["movement"] = _coerce_enum_value(normalized["movement"], valid_values=_VALID_MOVEMENTS)
        return normalized

    def _normalize(self, data: dict[str, Any]) -> dict[str, Any]:
        data = self._unwrap_model_payload(dict(data))
        data.setdefault("project_id", "")
        data.setdefault("chapter_id", "")
        data.setdefault("script_text", "")
        for k in ("characters", "scenes", "props", "costumes", "shots"):
            if k not in data or not isinstance(data[k], list):
                data[k] = []
        data["shots"] = [self._normalize_shot(shot, idx + 1) for idx, shot in enumerate(data["shots"])]
        return data
