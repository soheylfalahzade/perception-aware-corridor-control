"""Junction graph, greedy t-spanner backbone and backbone routes."""
from __future__ import annotations

import heapq
from collections.abc import Iterable

Edge = tuple[str, str]


def dijkstra(adj: dict[str, dict[str, float]], src: str, dst: str) -> tuple[float, list[str]]:
    """Shortest path ``(length, nodes)``; ``(inf, [])`` when ``dst`` is unreachable."""
    dist = {src: 0.0}
    prev: dict[str, str] = {}
    heap = [(0.0, src)]
    while heap:
        d, u = heapq.heappop(heap)
        if u == dst:
            break
        if d > dist.get(u, float("inf")):
            continue
        for v, w in adj.get(u, {}).items():
            nd = d + w
            if nd < dist.get(v, float("inf")):
                dist[v], prev[v] = nd, u
                heapq.heappush(heap, (nd, v))
    if dst not in dist:
        return float("inf"), []
    path = [dst]
    while path[-1] != src:
        path.append(prev[path[-1]])
    return dist[dst], path[::-1]


def adjacency(weights: dict[Edge, float]) -> dict[str, dict[str, float]]:
    """Undirected adjacency from ``{(u, v): weight}``."""
    adj: dict[str, dict[str, float]] = {}
    for (u, v), w in weights.items():
        adj.setdefault(u, {})[v] = w
        adj.setdefault(v, {})[u] = w
    return adj


def greedy_spanner(weights: dict[Edge, float], t: float) -> set[Edge]:
    """Greedy t-spanner: scan edges by weight and keep one that the kept subgraph does not
    already connect within ``t`` times its weight."""
    kept: dict[Edge, float] = {}
    adj: dict[str, dict[str, float]] = {}
    for (u, v), w in sorted(weights.items(), key=lambda kv: kv[1]):
        d, _ = dijkstra(adj, u, v) if u in adj and v in adj else (float("inf"), [])
        if d > t * w:
            kept[(u, v)] = w
            adj.setdefault(u, {})[v] = w
            adj.setdefault(v, {})[u] = w
    return set(kept)


def route(weights: dict[Edge, float], src: str, dst: str) -> tuple[float, list[str]]:
    """Shortest route over the given undirected edge set."""
    return dijkstra(adjacency(weights), src, dst)


def load_grid(net_path: str) -> tuple[dict[Edge, float], dict[Edge, str]]:
    """Undirected travel-time weights and directed edge ids ``{(from, to): edge_id}``."""
    import sumolib

    net = sumolib.net.readNet(net_path, withPrograms=True)
    weights: dict[Edge, float] = {}
    directed: dict[Edge, str] = {}
    for e in net.getEdges():
        u, v = e.getFromNode().getID(), e.getToNode().getID()
        directed[(u, v)] = e.getID()
        key = (u, v) if u < v else (v, u)
        w = e.getLength() / e.getSpeed()
        weights[key] = min(w, weights.get(key, w))
    return weights, directed


def edge_ids(path: Iterable[str], directed: dict[Edge, str]) -> list[str]:
    """Directed edge ids along a node path."""
    nodes = list(path)
    return [directed[(a, b)] for a, b in zip(nodes, nodes[1:], strict=False)]


def backbone_report(weights: dict[Edge, float], src: str, dst: str, t: float) -> dict[str, float]:
    """Edges kept, stretch of the backbone route and number of junctions on it."""
    keep = greedy_spanner(weights, t)
    full, _ = route(weights, src, dst)
    sub, path = route({e: weights[e] for e in keep}, src, dst)
    return {"edges_full": float(len(weights)), "edges_backbone": float(len(keep)),
            "route_stretch": sub / full, "route_junctions": float(len(path))}


def route_comparison(weights: dict[Edge, float], src: str, dst: str, t: float) -> dict[str, object]:
    """Backbone route against the shortest route of the whole graph.

    Reports both free-flow times, the stretch and the junctions that only one route controls.
    """
    keep = greedy_spanner(weights, t)
    full, full_path = route(weights, src, dst)
    sub, sub_path = route({e: weights[e] for e in keep}, src, dst)
    inner_full, inner_sub = set(full_path[1:-1]), set(sub_path[1:-1])
    return {"t": t, "edges_backbone": len(keep), "edges_full": len(weights),
            "full_time_s": full, "backbone_time_s": sub, "route_stretch": sub / full,
            "full_path": full_path, "backbone_path": sub_path,
            "junctions_full": len(inner_full), "junctions_backbone": len(inner_sub),
            "only_full": sorted(inner_full - inner_sub),
            "only_backbone": sorted(inner_sub - inner_full)}
