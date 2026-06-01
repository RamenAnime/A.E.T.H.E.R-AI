from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from aether.workflow.graph import WorkflowGraph
from aether.workflow.types import WorkflowEdge, WorkflowNode

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]


def load_workflow_toml(path: str | Path) -> WorkflowGraph:
    path = Path(path)
    with open(path, "rb") as fh:
        data = tomllib.load(fh)
    wf = data.get("workflow", {})
    graph = WorkflowGraph(name=wf.get("name", path.stem))
    for node_data in wf.get("nodes", []):
        graph.add_node(
            WorkflowNode(
                id=node_data["id"],
                role=node_data["role"],
                description=node_data.get("description", ""),
                config=node_data.get("config", {}),
            )
        )
    for edge_data in wf.get("edges", []):
        graph.add_edge(WorkflowEdge(source=edge_data["source"], target=edge_data["target"]))
    valid, msg = graph.validate()
    if not valid:
        raise ValueError(f"Invalid workflow: {msg}")
    return graph
