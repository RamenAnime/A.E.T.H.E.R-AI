from __future__ import annotations

from collections import defaultdict, deque
from typing import Dict, List, Set, Tuple

from aether.workflow.types import WorkflowEdge, WorkflowNode


class WorkflowGraph:
    def __init__(self, name: str = "") -> None:
        self.name = name
        self._nodes: Dict[str, WorkflowNode] = {}
        self._edges: List[WorkflowEdge] = []
        self._adjacency: Dict[str, List[str]] = defaultdict(list)
        self._reverse: Dict[str, List[str]] = defaultdict(list)

    def add_node(self, node: WorkflowNode) -> None:
        if node.id in self._nodes:
            raise ValueError(f"Duplicate node id: {node.id}")
        self._nodes[node.id] = node

    def add_edge(self, edge: WorkflowEdge) -> None:
        if edge.source not in self._nodes or edge.target not in self._nodes:
            raise ValueError("Edge references unknown node")
        self._edges.append(edge)
        self._adjacency[edge.source].append(edge.target)
        self._reverse[edge.target].append(edge.source)

    @property
    def nodes(self) -> List[WorkflowNode]:
        return list(self._nodes.values())

    @property
    def edges(self) -> List[WorkflowEdge]:
        return list(self._edges)

    def validate(self) -> Tuple[bool, str]:
        visited: Set[str] = set()
        in_stack: Set[str] = set()

        def dfs(node_id: str) -> bool:
            visited.add(node_id)
            in_stack.add(node_id)
            for neighbor in self._adjacency.get(node_id, []):
                if neighbor in in_stack:
                    return True
                if neighbor not in visited and dfs(neighbor):
                    return True
            in_stack.discard(node_id)
            return False

        for node_id in self._nodes:
            if node_id not in visited and dfs(node_id):
                return False, f"Cycle detected at {node_id}"
        return True, ""

    def execution_stages(self) -> List[List[str]]:
        in_degree = {nid: 0 for nid in self._nodes}
        for edge in self._edges:
            in_degree[edge.target] += 1
        stages: List[List[str]] = []
        ready = [nid for nid, deg in in_degree.items() if deg == 0]
        while ready:
            stages.append(sorted(ready))
            next_ready: List[str] = []
            for node_id in ready:
                for neighbor in self._adjacency.get(node_id, []):
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        next_ready.append(neighbor)
            ready = next_ready
        return stages
