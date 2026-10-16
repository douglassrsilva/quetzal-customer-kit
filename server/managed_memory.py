"""Adaptador REST para Databricks Managed Agent Memory (Beta).

El alcance se deriva de la identidad autenticada por el proxy de Databricks Apps.
El body de una solicitud y el modelo no pueden seleccionar el alcance de otro usuario.
"""

from __future__ import annotations

import os
from typing import Any

from databricks.sdk import WorkspaceClient


class ManagedAgentMemory:
    def __init__(self) -> None:
        self.store_name = os.getenv("QUETZAL_MANAGED_MEMORY_STORE", "").strip()

    @property
    def enabled(self) -> bool:
        return bool(self.store_name)

    @property
    def entries_path(self) -> str:
        return f"/api/2.1/unity-catalog/memory-stores/{self.store_name}/entries"

    @staticmethod
    def _scope(actor: str) -> str:
        if not actor or actor == "quetzal-operator":
            raise RuntimeError("Managed Memory requiere la identidad verificada del usuario final")
        return f"user:{actor.casefold()}"

    @staticmethod
    def _entry(item: Any) -> dict[str, Any]:
        if not isinstance(item, dict):
            return {}
        entry = item.get("memory_entry", item.get("entry", item))
        return entry if isinstance(entry, dict) else {}

    def recall(self, *, actor: str, query: str, top_k: int = 3) -> list[str]:
        if not self.enabled:
            return []
        result = WorkspaceClient().api_client.do(
            "POST",
            f"{self.entries_path}:search",
            body={
                "scope": self._scope(actor),
                "query": query[:1000],
                "path_prefix": "/memories/research/",
                "top_k": top_k,
            },
        ) or {}
        items = result.get("entries", result.get("results", [])) if isinstance(result, dict) else result
        memories: list[str] = []
        for item in items or []:
            entry = self._entry(item)
            contents = entry.get("contents")
            if isinstance(contents, str) and contents.strip():
                memories.append(contents.strip()[:1800])
        return memories

    def remember_research(
        self,
        *,
        actor: str,
        conversation_id: str,
        trace_id: str,
        question: str,
        answer: str,
        tools: list[dict[str, str]],
    ) -> None:
        if not self.enabled or not any(tool.get("tool") == "web_search" for tool in tools):
            return
        safe_conversation = "".join(char for char in conversation_id if char.isalnum() or char in "-_")[:128]
        safe_trace = "".join(char for char in trace_id if char.isalnum() or char in "-_")[:128]
        WorkspaceClient().api_client.do(
            "POST",
            self.entries_path,
            query={"scope": self._scope(actor)},
            body={
                "path": f"/memories/research/{safe_conversation}/{safe_trace}.md",
                "contents": (
                    "Investigación externa de Quetzal IQ.\n\n"
                    f"Pregunta: {question[:1000]}\n\n"
                    f"Síntesis: {answer[:2400]}"
                ),
                "description": "Contexto externo verificable para continuidad entre conversaciones.",
            },
        )


managed_agent_memory = ManagedAgentMemory()
