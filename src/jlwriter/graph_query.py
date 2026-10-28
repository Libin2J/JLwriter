"""
图查询：子图、邻居、最短路径、社区检测
"""
try:
    import networkx as nx
    HAS_NX = True
except ImportError:
    HAS_NX = False


def get_neighbors(G, node, hops=1):
    """N 跳邻居（有向图双向遍历）"""
    if G is None or node not in G:
        return set()
    nodes = {node}
    frontier = {node}
    for _ in range(hops):
        new = set()
        for n in frontier:
            new |= set(G.successors(n))
            new |= set(G.predecessors(n))
        new -= nodes
        if not new:
            break
        nodes |= new
        frontier = new
    return nodes



def get_multi_subgraph(G, seed_nodes, hops=1):
    """多起点子图：对每个起点做 N 跳扩展后合并"""
    if G is None or not seed_nodes:
        return None
    all_nodes = set()
    for n in seed_nodes:
        all_nodes |= get_neighbors(G, n, hops)
    if not all_nodes:
        return None
    return G.subgraph(all_nodes)


def shortest_path(G, a, b):
    """两实体最短路径"""
    if G is None or a not in G or b not in G:
        return None
    try:
        return nx.shortest_path(G, a, b)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None




def format_subgraph(G, max_nodes=40, max_chars=4000):
    """
    把子图转成 prompt 可读文本。
    按节点类型分组，逐条列出节点与边。
    """
    if G is None or G.number_of_nodes() == 0:
        return ""

    nodes = list(G.nodes(data=True))[:max_nodes]
    node_set = {n for n, _ in nodes}

    lines = []
    # 按类型分组
    by_type = {}
    for n, d in nodes:
        by_type.setdefault(d.get("type", "unknown"), []).append(n)

    for t in ("character", "organization", "location", "item"):
        if t not in by_type:
            continue
        label = {
            "character": "角色",
            "organization": "组织",
            "location": "地点",
            "item": "物品",
        }.get(t, t)
        lines.append(f"▸ {label}")
        for ep in by_type[t]:
            _, name = ep.split(":", 1)
            # 关联边
            rels = []
            for _, v, ed in G.out_edges(ep, data=True):
                if v not in node_set:
                    continue
                _, vn = v.split(":", 1)
                typ = ed.get("type", "")
                desc = ed.get("description", "")
                line = f"{name} → {vn}（{typ}）"
                if desc:
                    line += f" {desc[:40]}"
                rels.append(line)
            for u, _, ed in G.in_edges(ep, data=True):
                if u not in node_set:
                    continue
                _, un = u.split(":", 1)
                typ = ed.get("type", "")
                desc = ed.get("description", "")
                line = f"{un} → {name}（{typ}）"
                if desc:
                    line += f" {desc[:40]}"
                rels.append(line)

            if rels:
                lines.append(f"  · {name}")
                for r in rels[:8]:
                    lines.append(f"      {r}")
            else:
                lines.append(f"  · {name}")

    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n……（已截断）"
    return text