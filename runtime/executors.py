"""层执行器：顺序执行 / LangGraph 扇出。

RuntimeEngine 负责路由、切片、审批、存储；执行器只负责"把一层切片跑完"。
默认优先 LangGraph（环境里可用时），不可用则回退到顺序执行。
"""
from __future__ import annotations

from typing import Annotated, Callable, Protocol, TypedDict

from .agent_runners import AgentResult
from .contracts import Slice

RunSlice = Callable[[Slice], AgentResult]


def _merge_results(
    current: dict[int, AgentResult] | None,
    update: dict[int, AgentResult] | None,
) -> dict[int, AgentResult]:
    merged = dict(current or {})
    merged.update(update or {})
    return merged


class LayerState(TypedDict, total=False):
    results: Annotated[dict[int, AgentResult], _merge_results]


class LayerExecutor(Protocol):
    name: str

    def run(self, slices: list[Slice], run_slice: RunSlice) -> dict[int, AgentResult]: ...


class SequentialLayerExecutor:
    """最简单的执行器：按顺序跑同层切片。"""

    name = "sequential"

    def run(self, slices: list[Slice], run_slice: RunSlice) -> dict[int, AgentResult]:
        return {slice_.no: run_slice(slice_) for slice_ in slices}


class LangGraphLayerExecutor:
    """用 LangGraph StateGraph 把同层切片作为并行节点扇出。"""

    name = "langgraph"

    def __init__(self) -> None:
        try:
            from langgraph.graph import END, START, StateGraph  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("langgraph 未安装；请使用 SequentialLayerExecutor") from exc
        self._END = END
        self._START = START
        self._StateGraph = StateGraph

    def run(self, slices: list[Slice], run_slice: RunSlice) -> dict[int, AgentResult]:
        if not slices:
            return {}

        graph = self._StateGraph(LayerState)
        for slice_ in slices:
            node_name = f"slice_{slice_.no}"

            def node(state: LayerState, slice_: Slice = slice_) -> dict:
                try:
                    result = run_slice(slice_)
                except Exception as exc:  # 执行器不让异常穿透图
                    result = AgentResult(
                        agent=slice_.agent,
                        status="failed",
                        error=f"{type(exc).__name__}: {exc}",
                    )
                return {"results": {slice_.no: result}}

            graph.add_node(node_name, node)
            graph.add_edge(self._START, node_name)
            graph.add_edge(node_name, self._END)

        compiled = graph.compile()
        final = compiled.invoke({"results": {}})
        return dict(final.get("results") or {})


def langgraph_available() -> bool:
    try:
        import langgraph  # noqa: F401
        return True
    except ImportError:
        return False


def make_default_executor() -> LayerExecutor:
    if langgraph_available():
        try:
            return LangGraphLayerExecutor()
        except Exception:
            pass
    return SequentialLayerExecutor()


def make_executor(name: str = "auto") -> LayerExecutor:
    if name == "sequential":
        return SequentialLayerExecutor()
    if name == "langgraph":
        return LangGraphLayerExecutor()
    return make_default_executor()
