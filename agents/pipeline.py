"""Deep Agents Pipeline Framework and Factory.

Task 4.4:
- create_deep_agent implementation conforming to Deep Agents architecture
- Subagent configuration (Router Subagent, Answer Subagent, Retrieval Tools)
- Multi-step execution pipeline with state propagation
"""

import os
import time
import logging
from typing import Optional, List, Dict, Any, Callable, Union, Awaitable
from pydantic import BaseModel, Field

from llm.gigachat_client import GigaChatClient, GigaChatConfig
from agents.router_agent import RouterAgent, RouterOutput
from agents.answer_agent import AnswerAgent, AnswerOutput, DocumentContext

logger = logging.getLogger(__name__)


class AgentState(BaseModel):
    """Shared state passed between subagents in the pipeline."""
    query: str
    router_output: Optional[RouterOutput] = None
    retrieved_docs: List[DocumentContext] = Field(default_factory=list)
    answer_output: Optional[AnswerOutput] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    logs: List[str] = Field(default_factory=list)
    duration_sec: float = 0.0


class DeepAgent:
    """Agent representation in the Deep Agents framework."""

    def __init__(
        self,
        name: str,
        role: str,
        system_prompt: str = "",
        model: Optional[str] = None,
        tools: Optional[List[Callable[..., Any]]] = None,
        subagents: Optional[List["DeepAgent"]] = None,
        llm_client: Optional[GigaChatClient] = None,
    ):
        self.name = name
        self.role = role
        self.system_prompt = system_prompt
        self.model = model
        self.tools = tools or []
        self.subagents = subagents or []
        self.llm_client = llm_client or GigaChatClient()

    def add_tool(self, tool: Callable[..., Any]) -> None:
        """Register a tool to the agent."""
        self.tools.append(tool)

    def add_subagent(self, subagent: "DeepAgent") -> None:
        """Register a subagent."""
        self.subagents.append(subagent)

    def run(self, state: AgentState) -> AgentState:
        """Execute agent step."""
        state.logs.append(f"Executing agent: {self.name} ({self.role})")
        return state

    async def arun(self, state: AgentState) -> AgentState:
        """Execute agent step asynchronously."""
        state.logs.append(f"Executing async agent: {self.name} ({self.role})")
        return state


def create_deep_agent(
    name: str,
    role: str,
    system_prompt: str = "",
    model: Optional[str] = None,
    tools: Optional[List[Callable[..., Any]]] = None,
    subagents: Optional[List[DeepAgent]] = None,
    llm_client: Optional[GigaChatClient] = None,
) -> DeepAgent:
    """Factory function for creating Deep Agents according to architecture spec."""
    return DeepAgent(
        name=name,
        role=role,
        system_prompt=system_prompt,
        model=model,
        tools=tools,
        subagents=subagents,
        llm_client=llm_client,
    )


class DeepAgentsPipeline:
    """High-level pipeline executing the 2-LLM-call architecture:

    User Question
        |
    [Router Agent (GigaChat Lite)] -> Extracts SQL filters + query rewrite
        |
    [RAG Search (Local Vector + BM25 + Cross-Encoder)] -> Top-5 docs
        |
    [Attachment Enricher] -> Attachment text injection
        |
    [Answer Agent (GigaChat Max)] -> Strictly grounded answer with [slug] citations
    """

    def __init__(
        self,
        llm_client: Optional[GigaChatClient] = None,
        router_agent: Optional[RouterAgent] = None,
        answer_agent: Optional[AnswerAgent] = None,
        search_fn: Optional[Callable[[RouterOutput], List[DocumentContext]]] = None,
    ):
        self.llm_client = llm_client or GigaChatClient()
        self.router_agent = router_agent or RouterAgent(llm_client=self.llm_client)
        self.answer_agent = answer_agent or AnswerAgent(llm_client=self.llm_client)
        self.search_fn = search_fn

        
        self.router_subagent = create_deep_agent(
            name="RouterAgent",
            role="Query Classifier & Metadata Extractor",
            system_prompt=self.router_agent.system_prompt,
            model=self.llm_client.config.model_lite,
            llm_client=self.llm_client,
        )

        self.answer_subagent = create_deep_agent(
            name="AnswerAgent",
            role="Grounded QA Generator with Citations",
            system_prompt=self.answer_agent.system_prompt,
            model=self.llm_client.config.model_max,
            llm_client=self.llm_client,
        )

    def execute(self, query: str) -> AgentState:
        """Execute end-to-end pipeline synchronously."""
        start_time = time.time()
        state = AgentState(query=query)
        state.logs.append(f"Starting pipeline for query: {query}")

        
        state.router_output = self.router_agent.route(query)
        state.logs.append(
            f"Router extracted: product_code={state.router_output.product_code}, "
            f"slug={state.router_output.slug}, "
            f"need_attachment={state.router_output.need_attachment}"
        )

        
        if self.search_fn:
            try:
                state.retrieved_docs = self.search_fn(state.router_output)
            except Exception as e:
                logger.error("Error executing search_fn: %s", e)
                state.logs.append(f"Search error: {e}")
        else:
            state.logs.append("No search_fn configured. Using fallback retrieval.")

        
        state.answer_output = self.answer_agent.generate_answer(
            query=query,
            documents=state.retrieved_docs,
        )
        state.logs.append(
            f"Answer generated with {len(state.answer_output.citations)} citations."
        )

        state.duration_sec = time.time() - start_time
        return state

    async def aexecute(self, query: str) -> AgentState:
        """Execute end-to-end pipeline asynchronously."""
        start_time = time.time()
        state = AgentState(query=query)
        state.logs.append(f"Starting async pipeline for query: {query}")

        
        state.router_output = await self.router_agent.aroute(query)
        state.logs.append(
            f"Router extracted: product_code={state.router_output.product_code}, "
            f"slug={state.router_output.slug}, "
            f"need_attachment={state.router_output.need_attachment}"
        )

        
        if self.search_fn:
            try:
                state.retrieved_docs = self.search_fn(state.router_output)
            except Exception as e:
                logger.error("Error executing search_fn: %s", e)
                state.logs.append(f"Search error: {e}")

        
        state.answer_output = await self.answer_agent.agenerate_answer(
            query=query,
            documents=state.retrieved_docs,
        )
        state.logs.append(
            f"Answer generated with {len(state.answer_output.citations)} citations."
        )

        state.duration_sec = time.time() - start_time
        return state
