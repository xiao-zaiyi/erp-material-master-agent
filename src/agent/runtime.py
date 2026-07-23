from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from typing import Any

from langchain.agents import create_agent
from langchain_core.tools import tool

from materials.models import MaterialQuery
from materials.service import MaterialService


logger = logging.getLogger("material_agent.chat_stream")


def build_material_tools(service: MaterialService) -> list[Any]:
    @tool
    def get_material_by_id(material_id: str) -> str:
        """按物料 ID 精确查询。物料 ID 就是完整物料编码；本工具直接查询索引 ID，不执行向量相似检索。"""
        material = service.get_by_id(material_id)
        if material is None:
            return json.dumps(
                {"found": False, "material_id": material_id.strip(), "message": "未找到该物料"},
                ensure_ascii=False,
            )
        return json.dumps({"found": True, "material": material.model_dump()}, ensure_ascii=False, default=str)

    @tool
    def search_materials(name: str = "", specification: str = "") -> str:
        """按物料名称或规格型号查询已有物料编码。至少填写一个参数。调用前由 Agent 识别别名，多个候选名称必须用顿号分隔。"""
        result = service.search(MaterialQuery(name=name, specification=specification))
        return result.model_dump_json(ensure_ascii=False)

    @tool
    def validate_new_material(name: str = "", specification: str = "") -> str:
        """判断拟新建物料是否与已有物料相同或疑似重复，并返回录入建议。"""
        result = service.validate(MaterialQuery(name=name, specification=specification))
        return result.model_dump_json(ensure_ascii=False)

    return [get_material_by_id, search_materials, validate_new_material]


def build_material_agent(model: Any, service: MaterialService):
    """使用 LangChain 1.x create_agent 创建自然语言物料助手。"""
    return create_agent(
        model=model,
        tools=build_material_tools(service),
        system_prompt=(
            "你是 ERP 物料主数据助手。你必须先调用合适的物料工具，再回答用户。"
            "用户提供明确物料代码并查询对应信息时，必须把该编码作为 material_id 调用 get_material_by_id；"
            "用户不知道编码、想按名称或规格查已有编码时调用 search_materials；用户想新建或判断重复时调用 validate_new_material。"
            "检索前必须根据你的知识识别物料的别名、俗称和简称，并将原名称与别名用顿号拼接后传给 search_materials，"
            "例如用户查询番茄时传入“番茄、西红柿、蕃茄”。形态词（如苗、种子、粉、酱）不同不能直接判定为同一物料。"
            "不要编造物料编码、规格或行业标准。必须说明候选 code、名称、规格、启用状态和判断依据。"
            "启用状态必须使用工具返回的 status 和 state_label，禁止猜测或使用特定 ERP 的原始状态码。"
            "结论只能使用：已有可用物料、已有待启用物料、疑似重复，人工确认、未发现重复，可申请新建。"
            "停用物料只能提示人工确认，不能建议自动恢复。"
        ),
    )


def extract_agent_text(result: dict[str, Any]) -> str:
    for message in reversed(result.get("messages", [])):
        message_type = getattr(message, "type", None)
        is_assistant = message_type in {"ai", "assistant"}
        if isinstance(message, dict):
            is_assistant = message.get("role", message.get("type")) in {"assistant", "ai"}
        if not is_assistant:
            continue
        content = getattr(message, "content", None) if not isinstance(message, dict) else message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                block.get("text", "") if isinstance(block, dict) else str(block) for block in content
            )
    return "Agent 没有返回可展示的文本结果。"


def stream_agent_events(agent: Any, payload: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    """把 LangGraph 流转换为稳定的公开事件，不暴露模型内部隐藏推理。"""
    yield "status", {"stage": "understanding", "message": "正在理解物料需求"}
    streamed_text = ""
    final_text = ""
    started_calls: set[str] = set()
    finished_calls: set[str] = set()

    try:
        for mode, data in agent.stream(payload, stream_mode=["updates", "messages"]):
            if mode == "messages":
                message, _metadata = data
                if _message_type(message) not in {"ai", "assistant", "AIMessageChunk"}:
                    continue
                if _tool_calls(message):
                    continue
                text_value = _message_text(message)
                if text_value:
                    streamed_text += text_value
                    yield "token", {"content": text_value}
                continue

            for message in _update_messages(data):
                calls = _tool_calls(message)
                for call in calls:
                    call_id = str(call.get("id") or f"{call.get('name', 'tool')}-{len(started_calls) + 1}")
                    if call_id in started_calls:
                        continue
                    started_calls.add(call_id)
                    yield "tool_start", {
                        "id": call_id,
                        "name": str(call.get("name") or "unknown_tool"),
                        "args": call.get("args") or {},
                    }

                if _message_type(message) in {"tool", "ToolMessage"}:
                    call_id = str(_message_value(message, "tool_call_id") or _message_value(message, "id") or "tool")
                    if call_id in finished_calls:
                        continue
                    finished_calls.add(call_id)
                    yield "tool_end", {
                        "id": call_id,
                        "name": str(_message_value(message, "name") or "material_tool"),
                        "result": _json_value(_message_text(message)),
                    }
                    yield "status", {"stage": "synthesizing", "message": "工具查询完成，正在整理结论"}
                elif _message_type(message) in {"ai", "assistant", "AIMessage"} and not calls:
                    final_text = _message_text(message)

        if final_text:
            remainder = final_text[len(streamed_text) :] if final_text.startswith(streamed_text) else ""
            if remainder:
                streamed_text += remainder
                yield "token", {"content": remainder}
        if not streamed_text:
            yield "token", {"content": final_text or "Agent 没有返回可展示的文本结果。"}
        yield "done", {"message": "回答完成"}
    except Exception as exc:
        logger.exception("流式对话执行失败")
        yield "error", {"message": str(exc)[:500]}


def _update_messages(update: Any) -> Iterator[Any]:
    if not isinstance(update, dict):
        return
    for node_update in update.values():
        if not isinstance(node_update, dict):
            continue
        messages = node_update.get("messages", [])
        if not isinstance(messages, list):
            messages = [messages]
        yield from messages


def _message_type(message: Any) -> str:
    if isinstance(message, dict):
        return str(message.get("type") or message.get("role") or "")
    return str(getattr(message, "type", type(message).__name__))


def _message_value(message: Any, key: str) -> Any:
    return message.get(key) if isinstance(message, dict) else getattr(message, key, None)


def _tool_calls(message: Any) -> list[dict[str, Any]]:
    calls = _message_value(message, "tool_calls") or []
    return [call for call in calls if isinstance(call, dict)]


def _message_text(message: Any) -> str:
    content = _message_value(message, "content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return "" if content is None else str(content)
    return "".join(
        str(block.get("text", "")) if isinstance(block, dict) else str(block)
        for block in content
    )


def _json_value(value: str) -> Any:
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value
