"""
从 StoryProject 构建 NetworkX 图
"""
try:
    import networkx as nx
    HAS_NX = True
except ImportError:
    HAS_NX = False

from .models import normalize_endpoint, parse_endpoint


def is_available():
    return HAS_NX


def build_graph(project):
    """构建多向图。节点属性：type / name；边属性：type / description / chapter"""
    if not HAS_NX:
        return None

    G = nx.MultiDiGraph()

    # 节点
    for c in project.characters:
        if c.name:
            G.add_node(f"character:{c.name}",
                       type="character", name=c.name)
    for l in project.locations:
        if l.name:
            G.add_node(f"location:{l.name}",
                       type="location", name=l.name)
    for o in project.organizations:
        if o.name:
            G.add_node(f"organization:{o.name}",
                       type="organization", name=o.name)
    for i in project.items:
        if i.name:
            G.add_node(f"item:{i.name}",
                       type="item", name=i.name)

    # 边
    for rel in project.relations or []:
        a = normalize_endpoint(rel.get("from", ""))
        b = normalize_endpoint(rel.get("to", ""))
        if not a or not b:
            continue

        # 端点可能指向未建档的实体：动态补节点
        if a not in G:
            _, name = parse_endpoint(a)
            t = a.split(":", 1)[0]
            G.add_node(a, type=t, name=name)
        if b not in G:
            _, name = parse_endpoint(b)
            t = b.split(":", 1)[0]
            G.add_node(b, type=t, name=name)

        G.add_edge(
            a, b,
            key=rel.get("type", "") or "",
            type=rel.get("type", ""),
            description=rel.get("description", ""),
            chapter=rel.get("chapter"),
        )
    return G


