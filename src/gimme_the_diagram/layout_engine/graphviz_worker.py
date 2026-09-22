from __future__ import annotations

import json
import sys
from typing import Any

import pygraphviz as pgv


def _layout(payload: dict[str, Any]) -> dict[str, Any]:
    graph = pgv.AGraph(directed=True, strict=False)
    graph.graph_attr.update(
        rankdir="LR",
        splines="ortho",
        nodesep="1.0",
        ranksep="1.25",
        pack="36",
        packmode="array",
        margin="0",
        pad="0",
    )
    graph.node_attr.update(shape="box", fixedsize="true", label="")
    graph.edge_attr.update(arrowhead="none")
    for node in payload["nodes"]:
        graph.add_node(
            node["name"], width=str(node["width"]), height=str(node["height"])
        )
    for source, target in payload["edges"]:
        graph.add_edge(source, target)
    graph.layout(prog="dot")
    return {
        "positions": {
            node["name"]: graph.get_node(node["name"]).attr["pos"]
            for node in payload["nodes"]
        }
    }


def _route(payload: dict[str, Any]) -> dict[str, Any]:
    graph = pgv.AGraph(directed=True, strict=False)
    graph.graph_attr.update(
        splines=payload.get("splines", "ortho"),
        notranslate="true",
        pad="0",
        margin="0",
    )
    graph.node_attr.update(shape="box", fixedsize="true", label="", pin="true")
    graph.edge_attr.update(arrowhead="none")
    for node in payload["nodes"]:
        graph.add_node(
            node["name"],
            pos=node["pos"],
            width=str(node["width"]),
            height=str(node["height"]),
        )
    for edge in payload["edges"]:
        graph.add_edge(edge["source"], edge["target"], gtd_index=str(edge["index"]))
    graph.layout(prog="neato", args="-n2")
    return {
        "positions": {
            node["name"]: graph.get_node(node["name"]).attr["pos"]
            for node in payload["nodes"]
        },
        "edges": [
            {"index": int(edge.attr["gtd_index"]), "pos": edge.attr["pos"]}
            for edge in graph.edges()
        ],
    }


def main() -> None:
    payload = json.load(sys.stdin)
    operation = payload.get("operation")
    if operation == "layout":
        result = _layout(payload)
    elif operation == "route":
        result = _route(payload)
    else:
        raise ValueError(f"unknown Graphviz operation: {operation}")
    json.dump(result, sys.stdout)


if __name__ == "__main__":
    main()
