from __future__ import annotations

import json
from dataclasses import dataclass
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from config import (
    CHAT_MODEL,
    DEFAULT_USER_ID,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
)
from long_memory import MultiLayerMemory
from reminder_module import ReminderManager
from system_memory import SystemMemoryManager


@dataclass
class RiskEvaluation:
    score: int
    level: str
    reasons: List[str]


class CareMacroEngine:
    def __init__(self, reminder_manager: ReminderManager):
        self.reminder_manager = reminder_manager

    def run(self, evaluation: RiskEvaluation, state: Dict[str, Any]) -> Dict[str, Any]:
        macros = []
        weather = state.get("weather", {})
        vitals = state.get("vitals", {})
        user_id = state.get("user_id", DEFAULT_USER_ID)

        temperature = weather.get("temperature")
        warnings = weather.get("warnings", [])

        if temperature and temperature >= 33 or "WHOT" in warnings:
            macros.append(self._heat_macro(user_id))

        if vitals.get("sleep") and vitals["sleep"] < 6:
            macros.append(self._sleep_macro(user_id))

        if not macros:
            macros.append(
                {
                    "message": "检测到风险升高，请保持警惕并及时查看提醒任务。",
                    "reminders": [],
                }
            )

        final_message = "\n".join(m["message"] for m in macros)
        reminder_ids = [r.id for m in macros for r in m["reminders"]]
        return {
            "route": "macro",
            "risk_level": evaluation.level,
            "message": final_message,
            "reminder_ids": reminder_ids,
        }

    def _heat_macro(self, user_id: str) -> Dict[str, Any]:
        now = datetime.utcnow()
        reminders = [
            self.reminder_manager.create_reminder(
                "未来 1 小时内补水 500ml，并避免正午外出",
                user_id=user_id,
                severity="high",
                due_time=now + timedelta(minutes=30),
                tags=["heat", "hydration"],
            ),
            self.reminder_manager.create_reminder(
                "联系家属确认状态，如持续不适请求医",
                user_id=user_id,
                severity="high",
                due_time=now + timedelta(hours=1),
                tags=["family", "safety"],
            ),
        ]
        message = (
            "🌡️ 检测到高温高危场景，已生成补水与家属联络提醒，请立即执行，并保持凉爽。"
        )
        return {"message": message, "reminders": reminders}

    def _sleep_macro(self, user_id: str) -> Dict[str, Any]:
        now = datetime.utcnow()
        evening = now.replace(hour=22, minute=0, second=0, microsecond=0)
        if evening <= now:
            evening += timedelta(days=1)
        reminders = [
            self.reminder_manager.create_reminder(
                "今晚 22:00 前完成放松活动（如听音乐/伸展），准备早睡",
                user_id=user_id,
                severity="medium",
                due_time=evening,
                tags=["sleep", "routine"],
            ),
            self.reminder_manager.create_reminder(
                "记录今晚睡眠时长与感受，明早确认",
                user_id=user_id,
                severity="low",
                due_time=now + timedelta(hours=12),
                tags=["sleep", "tracking"],
            ),
        ]
        message = "😴 连续睡眠不足，系统已安排睡眠改善提醒，请按时执行。"
        return {"message": message, "reminders": reminders}


class RiskRouter:
    def __init__(
        self,
        reminder_manager: Optional[ReminderManager] = None,
        system_memory: Optional[SystemMemoryManager] = None,
        llm: Optional[ChatOpenAI] = None,
    ):
        self.reminder_manager = reminder_manager or ReminderManager()
        self.system_memory = system_memory or self.reminder_manager.memory
        self.multi_memory = MultiLayerMemory(system_memory=self.system_memory)
        if llm is not None:
            self.llm = llm
        else:
            use_fake = os.getenv("USE_FAKE_EMBEDDINGS") == "1"
            if use_fake:
                from langchain_community.chat_models.fake import FakeListChatModel

                self.llm = FakeListChatModel(
                    responses=[
                        '{"message": "保持补水与休息，关注近期睡眠", "evidence": {"note": "fake response"}}'
                    ]
                )
            else:
                self.llm = ChatOpenAI(
                    base_url=OPENAI_BASE_URL,
                    api_key=OPENAI_API_KEY,
                    model=CHAT_MODEL,
                    temperature=0,
                )
        self.rag_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是老年人健康关怀助手。基于提供的健康知识、用户档案以及短期记忆，"
                    "给出简短的关怀提示，并说明判断依据。",
                ),
                (
                    "human",
                    "当前状态: {state}\n"
                    "知识片段: {knowledge}\n"
                    "短期记忆: {short_term}\n"
                    "用户档案: {profile}\n"
                    "请输出 JSON，包含 message 与 evidence 两个字段。",
                ),
            ]
        )
        self.care_macro = CareMacroEngine(self.reminder_manager)

    # ------------------------------------------------------------------
    # 风险计算
    # ------------------------------------------------------------------
    def evaluate(self, state: Dict[str, Any]) -> RiskEvaluation:
        score = 0
        reasons: List[str] = []

        weather = state.get("weather", {})
        vitals = state.get("vitals", {})

        temp = weather.get("temperature")
        humidity = weather.get("humidity")
        warnings = weather.get("warnings", [])
        heart_rate = vitals.get("heart_rate")
        sleep = vitals.get("sleep")

        if temp is not None:
            if temp >= 33:
                score += 4
                reasons.append(f"高温 {temp}°C")
            elif temp >= 30:
                score += 2
                reasons.append(f"偏高温度 {temp}°C")
            elif temp <= 10:
                score += 2
                reasons.append(f"低温 {temp}°C")

        if humidity and humidity >= 90:
            score += 1
            reasons.append(f"湿度 {humidity}%")

        if "WHOT" in warnings or "WRAINB" in warnings:
            score += 3
            reasons.append("天文台高危警告")

        if heart_rate and heart_rate >= 110:
            score += 3
            reasons.append(f"心率偏高 {heart_rate}")
        elif heart_rate and heart_rate <= 50:
            score += 2
            reasons.append(f"心率偏低 {heart_rate}")

        if sleep and sleep < 6:
            score += 2
            reasons.append(f"睡眠不足 {sleep}h")

        level = "low"
        if score >= 7:
            level = "high"
        elif score >= 4:
            level = "medium"

        return RiskEvaluation(score=score, level=level, reasons=reasons)

    # ------------------------------------------------------------------
    # 路由逻辑
    # ------------------------------------------------------------------
    def route(self, state: Dict[str, Any]) -> Dict[str, Any]:
        evaluation = self.evaluate(state)
        user_id = state.get("user_id", DEFAULT_USER_ID)
        self.system_memory.add_event(
            user_id=user_id,
            content=f"Routing request level={evaluation.level} reasons={evaluation.reasons}",
            event_type="routing_request",
            importance=1.2,
            extra={"level": evaluation.level},
        )

        if evaluation.level == "high":
            result = self.care_macro.run(evaluation, state)
        elif evaluation.level == "medium":
            result = self._run_rag_path(evaluation, state)
        else:
            result = self._run_template_path(evaluation, state)

        self.system_memory.add_event(
            user_id=user_id,
            content=f"Routing result via {result['route']}: {result['message']}",
            event_type="routing_result",
            importance=1.0,
        )
        return result

    def _run_rag_path(self, evaluation: RiskEvaluation, state: Dict[str, Any]):
        context = self.multi_memory.retrieve(state, user_id=state.get("user_id", DEFAULT_USER_ID))
        payload = {
            "state": json.dumps(state, ensure_ascii=False),
            "knowledge": "\n".join(doc.page_content for doc in context.knowledge_snippets)
            or "无",
            "short_term": "\n".join(doc.page_content for doc in context.short_term_memory)
            or "无",
            "profile": context.user_profile or "无",
        }
        try:
            chain = self.rag_prompt | self.llm
            response = chain.invoke(payload)
            message = response.content if hasattr(response, "content") else str(response)
        except Exception as exc:
            message = f"无法调用模型，改为规则输出。原因: {exc}"

        return {
            "route": "rag",
            "risk_level": evaluation.level,
            "message": message.strip(),
            "evidence": payload,
        }

    def _run_template_path(self, evaluation: RiskEvaluation, state: Dict[str, Any]):
        weather = state.get("weather", {})
        vitals = state.get("vitals", {})

        message = (
            "今日状态平稳，继续保持规律作息和补水。"
            if not weather.get("warnings")
            else "出现轻微天气波动，请留意系统提醒。"
        )

        if vitals.get("steps") and vitals["steps"] < 3000:
            message += " 适量活动可帮助维持心肺功能。"

        return {
            "route": "template",
            "risk_level": evaluation.level,
            "message": message,
            "evidence": {"reasons": evaluation.reasons},
        }
