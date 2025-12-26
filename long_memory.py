from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS

from config import (
    DEFAULT_USER_ID,
    EMBEDDING_MODEL,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    PERSON_KB_PATH,
    USER_PROFILE_PATH,
)
from system_memory import SystemMemoryManager


@dataclass
class RetrievedContext:
    knowledge_snippets: List[Document]
    short_term_memory: List[Document]
    user_profile: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "knowledge": [doc.page_content for doc in self.knowledge_snippets],
            "short_term": [doc.page_content for doc in self.short_term_memory],
            "user_profile": self.user_profile,
        }


class MultiLayerMemory:
    """
    负责统一管理“外部健康知识 + 用户档案 + 短期记忆”。
    """

    def __init__(
        self,
        faiss_path: str = PERSON_KB_PATH,
        user_profile_path: str = USER_PROFILE_PATH,
        system_memory: Optional[SystemMemoryManager] = None,
    ):
        self.faiss_path = faiss_path
        if os.getenv("USE_FAKE_EMBEDDINGS") == "1":
            from langchain_community.embeddings import FakeEmbeddings

            self.embeddings = FakeEmbeddings(size=1536)
        else:
            self.embeddings = OpenAIEmbeddings(
                base_url=OPENAI_BASE_URL, api_key=OPENAI_API_KEY, model=EMBEDDING_MODEL
            )
        self.health_kb: Optional[FAISS] = None
        self.system_memory = system_memory or SystemMemoryManager()
        self.user_profile_text = self._load_user_profile(user_profile_path)
        self._load_health_kb()

    def _load_health_kb(self) -> None:
        if os.path.isdir(self.faiss_path):
            try:
                self.health_kb = FAISS.load_local(
                    self.faiss_path,
                    self.embeddings,
                    allow_dangerous_deserialization=True,
                )
            except Exception:
                self.health_kb = None

    def _load_user_profile(self, path: str) -> Optional[str]:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        return None

    # ------------------------------------------------------------------
    # 检索
    # ------------------------------------------------------------------
    def _state_to_query(self, state: Dict[str, Any]) -> str:
        parts = []
        weather = state.get("weather")
        if weather:
            parts.append(
                f"Weather temp {weather.get('temperature')} humidity {weather.get('humidity')}"
            )
            warnings = weather.get("warnings")
            if warnings:
                parts.append(f"warnings: {' '.join(warnings)}")

        vitals = state.get("vitals")
        if vitals:
            hr = vitals.get("heart_rate")
            steps = vitals.get("steps")
            sleep = vitals.get("sleep")
            parts.append(f"heart rate {hr}, steps {steps}, sleep {sleep}")

        extra = state.get("notes")
        if extra:
            parts.append(extra)

        return " | ".join(filter(None, parts)) or "health advice"

    def retrieve(
        self,
        state: Dict[str, Any],
        *,
        query: Optional[str] = None,
        user_id: str = DEFAULT_USER_ID,
        k: int = 3,
    ) -> RetrievedContext:
        query = query or self._state_to_query(state)

        knowledge_docs: List[Document] = []
        if self.health_kb:
            knowledge_docs = self.health_kb.similarity_search(query, k=k)

        short_term = self.system_memory.search_recent(query=query, user_id=user_id)

        return RetrievedContext(
            knowledge_snippets=knowledge_docs,
            short_term_memory=short_term,
            user_profile=self.user_profile_text,
        )

    # ------------------------------------------------------------------
    # 便捷写入
    # ------------------------------------------------------------------
    def add_short_term_event(
        self, user_id: str, event: str, metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        self.system_memory.add_event(
            user_id=user_id,
            content=event,
            event_type="short_term_event",
            extra=metadata,
        )

    def context_json(self, state: Dict[str, Any]) -> str:
        return json.dumps(self.retrieve(state).to_dict(), ensure_ascii=False, indent=2)
