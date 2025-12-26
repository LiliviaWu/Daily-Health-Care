from __future__ import annotations

import os
import warnings
from datetime import datetime
from typing import Dict, List, Optional

from langchain_core.embeddings import Embeddings
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS


from langchain_classic.retrievers import TimeWeightedVectorStoreRetriever

warnings.filterwarnings(
    "ignore",
    message="Relevance scores must be between 0 and 1",
    module="langchain_classic.retrievers.time_weighted_retriever",
)
warnings.filterwarnings(
    "ignore",
    message="No relevant docs were retrieved using the relevance score threshold",
    module="langchain_classic.retrievers.time_weighted_retriever",
)

from config import (
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    EMBEDDING_MODEL,
    SYSTEM_MEMORY_PATH,
)


class SystemMemoryManager:
    """
    负责维护“短期时间线记忆”，并通过 LangChain 的 TimeWeightedVectorStoreRetriever
    提供时间感知的检索能力。可写入来自提醒模块与聊天模块的事件。
    """

    def __init__(
        self,
        persist_path: str = SYSTEM_MEMORY_PATH,
        decay_rate: float = 0.01,
        k: int = 6,
        embeddings: Optional[Embeddings] = None,
    ):
        self.persist_path = persist_path
        self.decay_rate = decay_rate
        self.k = k
        if embeddings is None and os.getenv("USE_FAKE_EMBEDDINGS") == "1":
            from langchain_community.embeddings import FakeEmbeddings

            embeddings = FakeEmbeddings(size=1536)

        self.embeddings = embeddings or OpenAIEmbeddings(
            base_url=OPENAI_BASE_URL, api_key=OPENAI_API_KEY, model=EMBEDDING_MODEL
        )
        self.vectorstore: Optional[FAISS] = None
        self.retriever: Optional[TimeWeightedVectorStoreRetriever] = None
        self._load_or_init_store()

    # ------------------------------------------------------------------
    # 基础能力
    # ------------------------------------------------------------------
    def _load_or_init_store(self) -> None:
        if os.path.isdir(self.persist_path):
            try:
                self.vectorstore = FAISS.load_local(
                    self.persist_path,
                    self.embeddings,
                    allow_dangerous_deserialization=True,
                )
            except Exception:
                # 若加载失败则重新初始化
                self.vectorstore = None

        if self.vectorstore is not None:
            self._refresh_retriever()
            self._sync_memory_stream()

    def _refresh_retriever(self) -> None:
        if self.vectorstore:
            self.retriever = TimeWeightedVectorStoreRetriever(
                vectorstore=self.vectorstore,
                decay_rate=self.decay_rate,
                k=self.k,
            )
            self.retriever.search_kwargs = {"score_threshold": 0, "k": max(self.k, 10)}

    def _persist(self) -> None:
        if self.vectorstore:
            os.makedirs(self.persist_path, exist_ok=True)
            self.vectorstore.save_local(self.persist_path)

    def _add_documents(self, documents: List[Document]) -> None:
        if not documents:
            return

        if self.vectorstore is None:
            self.vectorstore = FAISS.from_documents(documents, self.embeddings)
            self._refresh_retriever()
            self._sync_memory_stream()
        else:
            if self.retriever:
                self.retriever.add_documents(documents)
            else:
                self.vectorstore.add_documents(documents)

        self._persist()

    def _sync_memory_stream(self) -> None:
        """Ensure retriever memory_stream mirrors existing vectorstore docs."""
        if not self.retriever or not self.vectorstore:
            return

        docstore = getattr(self.vectorstore, "docstore", None)
        if docstore is None or not hasattr(docstore, "_dict"):
            return

        docs = list(docstore._dict.values())
        now = datetime.utcnow()
        self.retriever.memory_stream = []
        for idx, doc in enumerate(docs):
            metadata = dict(doc.metadata)
            metadata.setdefault("last_accessed_at", now)
            metadata["buffer_idx"] = idx
            doc.metadata = metadata
            self.retriever.memory_stream.append(doc)
        docstore._dict = {doc.id: doc for doc in docs}

    # ------------------------------------------------------------------
    # 写入接口
    # ------------------------------------------------------------------
    def add_event(
        self,
        user_id: str,
        content: str,
        *,
        event_type: str,
        importance: float = 1.0,
        extra: Optional[Dict] = None,
    ) -> None:
        """
        记录事件到短期记忆。

        调用方式示例::

            mem = SystemMemoryManager()
            mem.add_event(
                user_id="user_001",
                content="午后完成一次补水提醒",
                event_type="reminder_event",
                importance=1.2,
                extra={"reminder_id": 12}
            )

        参数说明:
            user_id: 事件所属用户，后续检索可以按用户过滤。
            content: 存入向量库的文本内容，最好能描述事件事实与结果。
            event_type: 分类标签 (如 reminder_event/chat_message)，便于统计与衰减。
            importance: 附加权重，>1 会让 TimeWeightedRetriever 更倾向保留该记忆。
            extra: 附加的 metadata (如提醒ID、状态)，会随着文档一起写入。
        """
        metadata = {
            "user_id": user_id,
            "event_type": event_type,
            "importance": importance,
            "created_at": datetime.utcnow().isoformat(),
        }
        if extra:
            metadata.update(extra)

        document = Document(page_content=content, metadata=metadata)
        self._add_documents([document])

    def log_reminder_event(
        self,
        user_id: str,
        reminder_id: int,
        status: str,
        note: Optional[str] = None,
    ) -> None:
        content = f"Reminder {reminder_id} status => {status}"
        if note:
            content += f": {note}"

        self.add_event(
            user_id=user_id,
            content=content,
            event_type="reminder_event",
            importance=1.5 if status in {"ignored", "overdue"} else 1.0,
            extra={"reminder_id": reminder_id, "status": status},
        )

    def add_chat_message(
        self,
        user_id: str,
        role: str,
        text: str,
        *,
        importance: float = 1.0,
    ) -> None:
        content = f"[{role}] {text}"
        self.add_event(
            user_id=user_id,
            content=content,
            event_type="chat_message",
            importance=importance,
        )

    def sync_chat_transcript(
        self, user_id: str, transcript: List[Dict[str, str]]
    ) -> None:
        for message in transcript:
            self.add_chat_message(
                user_id=user_id,
                role=message.get("role", "user"),
                text=message.get("content", ""),
            )

    # ------------------------------------------------------------------
    # 查询接口
    # ------------------------------------------------------------------
    def search_recent(
        self, query: str, user_id: Optional[str] = None, top_k: Optional[int] = None
    ) -> List[Document]:
        if self.retriever is None:
            return []

        try:
            docs = self.retriever.invoke(query)
        except AttributeError:
            docs = self.retriever.get_relevant_documents(query)
        if user_id:
            docs = [doc for doc in docs if doc.metadata.get("user_id") == user_id]

        limit = top_k or self.k
        return docs[:limit]

    def dump_all(self) -> List[Document]:
        if self.vectorstore is None:
            return []
        # 使用 similarity_search("", k=n) 少数 trick 以取出所有
        return self.vectorstore.similarity_search("", k=self.k)
