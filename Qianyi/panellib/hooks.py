"""The optional hook a component can use when it changes its own topology."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass(frozen=True)
class EdgeRef:
    """One edge as the hook sees it: plain data, no Blender objects."""

    panel: str
    index: int
    uuid: int
    name: str
    points: Any = None          # sampled points of the edge, (N, 2) or None


@dataclass
class RebuildContext:
    """What the core knows about a rebuild, handed to the component's hook."""

    old_edges: list[EdgeRef] = field(default_factory=list)
    new_edges: list[EdgeRef] = field(default_factory=list)
    topology_changed: bool = False

    def old_edge(self, panel: str, name: str = "", index: int = -1) -> EdgeRef | None:
        return _find(self.old_edges, panel, name, index)

    def new_edges_of(self, panel: str, name: str = "") -> list[EdgeRef]:
        return [edge for edge in self.new_edges
                if edge.panel == panel and (not name or edge.name == name)]


class EdgeMap:
    """Previous edges to new edges, filled in by a hook."""

    def __init__(self) -> None:
        self.pairs: dict[int, int | None] = {}

    def map_to(self, old_uuid: int, new_uuid: int | None) -> None:
        self.pairs[old_uuid] = new_uuid

    def map_run(self, old: EdgeRef, new_edges: list[EdgeRef]) -> None:
        """A previous edge that is now the given run of new edges."""
        self.map_to(old.uuid, new_edges[0].uuid if new_edges else None)


HANDLED = "handled"          # the hook adjusted the sewings itself


def _find(edges: list[EdgeRef], panel: str, name: str, index: int) -> EdgeRef | None:
    for edge in edges:
        if edge.panel != panel:
            continue
        if name and edge.name == name:
            return edge
        if index >= 0 and edge.index == index:
            return edge
    return None


def points_or_none(points) -> np.ndarray | None:
    return None if points is None else np.asarray(points, dtype=np.float32)
