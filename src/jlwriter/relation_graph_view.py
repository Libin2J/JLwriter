"""
关系图绘制组件：多类型节点（角色/地点/组织/物品）+ 带箭头的边
"""
import math
from PyQt5.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsEllipseItem,
    QGraphicsRectItem, QGraphicsPolygonItem, QGraphicsTextItem,
    QGraphicsPathItem, QGraphicsItem
)
from PyQt5.QtCore import Qt, QPointF
from PyQt5.QtGui import (
    QPen, QBrush, QColor, QFont, QPainterPath, QPainter,
    QPolygonF
)

from .models import parse_endpoint, ENTITY_TYPE_COLORS
from .ui.literary import current_palette, repolish
from .ui.literary.controller import controller


NODE_RADIUS = 36
ARROW_SIZE = 12


# ============================================================
# 节点：按实体类型选择形状与颜色
# ============================================================

class _BaseNode:
    """混入类：提供拖拽、悬停、选中的通用行为"""

    def _init_base(self, endpoint, name, entity_type):
        self.endpoint = endpoint
        self.name = name
        self.entity_type = entity_type
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setCursor(Qt.OpenHandCursor)
        self.setToolTip(f"{name}（{entity_type}）")
        self.setZValue(1)

        display = name if len(name) <= 5 else name[:4] + "…"
        self.text_item = QGraphicsTextItem(display, self)
        self.text_item.setDefaultTextColor(Qt.white)
        font = QFont()
        font.setBold(True)
        font.setPointSize(10 if len(name) <= 4 else 8)
        self.text_item.setFont(font)
        self.text_item.setFlag(QGraphicsItem.ItemIsSelectable, False)
        self.text_item.setAcceptedMouseButtons(Qt.NoButton)

    def _position_text(self):
        br = self.text_item.boundingRect()
        self.text_item.setPos(-br.width() / 2, -br.height() / 2)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            scene = self.scene()
            if scene is not None and hasattr(scene, "update_edges"):
                scene.update_edges()
        elif change == QGraphicsItem.ItemSelectedHasChanged:
            try:
                self._apply_style(hover=False, selected=bool(value))
            except Exception:
                pass
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.setCursor(Qt.OpenHandCursor)
        super().mouseReleaseEvent(event)

    def hoverEnterEvent(self, event):
        try:
            self._apply_style(hover=True, selected=self.isSelected())
        except Exception:
            pass
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        try:
            self._apply_style(hover=False, selected=self.isSelected())
        except Exception:
            pass
        super().hoverLeaveEvent(event)


class CharacterNode(_BaseNode, QGraphicsEllipseItem):
    def __init__(self, endpoint, name):
        r = NODE_RADIUS
        QGraphicsEllipseItem.__init__(self, -r, -r, r * 2, r * 2)
        self._init_base(endpoint, name, "character")
        self._apply_style(hover=False, selected=False)
        self._position_text()

    def _apply_style(self, hover, selected):
        base = QColor(ENTITY_TYPE_COLORS["character"])
        if selected:
            self.setPen(QPen(QColor("#FF8C00"), 3))
            self.setBrush(QBrush(base.lighter(110)))
        elif hover:
            self.setPen(QPen(base.darker(120), 3))
            self.setBrush(QBrush(base.lighter(105)))
        else:
            self.setPen(QPen(base.darker(130), 2))
            self.setBrush(QBrush(base))


class LocationNode(_BaseNode, QGraphicsRectItem):
    def __init__(self, endpoint, name):
        r = NODE_RADIUS - 4
        QGraphicsRectItem.__init__(self, -r, -r * 0.75, r * 2, r * 1.5)
        self._init_base(endpoint, name, "location")
        self._apply_style(hover=False, selected=False)
        self._position_text()

    def _apply_style(self, hover, selected):
        base = QColor(ENTITY_TYPE_COLORS["location"])
        if selected:
            self.setPen(QPen(QColor("#FF8C00"), 3))
            self.setBrush(QBrush(base.lighter(110)))
        elif hover:
            self.setPen(QPen(base.darker(120), 3))
            self.setBrush(QBrush(base.lighter(105)))
        else:
            self.setPen(QPen(base.darker(130), 2))
            self.setBrush(QBrush(base))


class OrganizationNode(_BaseNode, QGraphicsPolygonItem):
    def __init__(self, endpoint, name):
        r = NODE_RADIUS + 2
        poly = QPolygonF([
            QPointF(0, -r),
            QPointF(r * 0.87, -r * 0.5),
            QPointF(r * 0.87, r * 0.5),
            QPointF(0, r),
            QPointF(-r * 0.87, r * 0.5),
            QPointF(-r * 0.87, -r * 0.5),
        ])
        QGraphicsPolygonItem.__init__(self, poly)
        self._init_base(endpoint, name, "organization")
        self._apply_style(hover=False, selected=False)
        self._position_text()

    def _apply_style(self, hover, selected):
        base = QColor(ENTITY_TYPE_COLORS["organization"])
        if selected:
            self.setPen(QPen(QColor("#FF8C00"), 3))
            self.setBrush(QBrush(base.lighter(110)))
        elif hover:
            self.setPen(QPen(base.darker(120), 3))
            self.setBrush(QBrush(base.lighter(105)))
        else:
            self.setPen(QPen(base.darker(130), 2))
            self.setBrush(QBrush(base))


class ItemNode(_BaseNode, QGraphicsPolygonItem):
    def __init__(self, endpoint, name):
        r = NODE_RADIUS - 4
        poly = QPolygonF([
            QPointF(0, -r),
            QPointF(r, 0),
            QPointF(0, r),
            QPointF(-r, 0),
        ])
        QGraphicsPolygonItem.__init__(self, poly)
        self._init_base(endpoint, name, "item")
        self._apply_style(hover=False, selected=False)
        self._position_text()

    def _apply_style(self, hover, selected):
        base = QColor(ENTITY_TYPE_COLORS["item"])
        if selected:
            self.setPen(QPen(QColor("#FF8C00"), 3))
            self.setBrush(QBrush(base.lighter(110)))
        elif hover:
            self.setPen(QPen(base.darker(120), 3))
            self.setBrush(QBrush(base.lighter(105)))
        else:
            self.setPen(QPen(base.darker(130), 2))
            self.setBrush(QBrush(base))

# ============================================================
# 怪物档案
# ============================================================

class MonsterNode(_BaseNode, QGraphicsPolygonItem):
    """三角形节点，代表怪物"""

    def __init__(self, endpoint, name):
        r = NODE_RADIUS + 2
        poly = QPolygonF([
            QPointF(0, -r),
            QPointF(r * 0.87, r * 0.5),
            QPointF(-r * 0.87, r * 0.5),
        ])
        QGraphicsPolygonItem.__init__(self, poly)
        self._init_base(endpoint, name, "monster")
        self._apply_style(hover=False, selected=False)
        self._position_text()

    def _apply_style(self, hover, selected):
        base = QColor(ENTITY_TYPE_COLORS["monster"])
        if selected:
            self.setPen(QPen(QColor("#FF8C00"), 3))
            self.setBrush(QBrush(base.lighter(110)))
        elif hover:
            self.setPen(QPen(base.darker(120), 3))
            self.setBrush(QBrush(base.lighter(105)))
        else:
            self.setPen(QPen(base.darker(130), 2))
            self.setBrush(QBrush(base))

def create_node(endpoint, name=None):
    """工厂：按端点类型返回合适的节点对象"""
    entity_type, parsed_name = parse_endpoint(endpoint)
    name = name or parsed_name
    if entity_type == "location":
        return LocationNode(endpoint, name)
    if entity_type == "organization":
        return OrganizationNode(endpoint, name)
    if entity_type == "item":
        return ItemNode(endpoint, name)
    if entity_type == "monster":
        return MonsterNode(endpoint, name)
    return CharacterNode(endpoint, name)


# ============================================================
# 边
# ============================================================

class RelationEdge(QGraphicsPathItem):
    def __init__(self, source, target, relation_type, description=""):
        super().__init__()
        self.source = source
        self.target = target
        self.relation_type = relation_type
        self.description = description
        self.setZValue(0)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setCursor(Qt.PointingHandCursor)

        self.base_color = self._color_for_type(relation_type)
        self.setPen(QPen(self.base_color, 2))
        tip = relation_type
        if description:
            tip += f"：{description}"
        self.setToolTip(tip)
        self.update_path()

    @staticmethod
    def _color_for_type(t):
        mapping = {
            "敌对": "#E74C3C", "仇敌": "#E74C3C",
            "师徒": "#27AE60",
            "父子": "#8E44AD", "母子": "#8E44AD",
            "母女": "#8E44AD", "父女": "#8E44AD",
            "恋人": "#E91E63", "夫妻": "#E91E63",
            "盟友": "#3498DB", "朋友": "#3498DB",
            "兄弟": "#16A085", "姐妹": "#16A085",
            "同门": "#16A085", "同僚": "#16A085",
            "上下级": "#7F8C8D", "主仆": "#7F8C8D",
            "所属": "#9B59B6",
            "领导": "#9B59B6",
            "位于": "#2ECC71",
            "拥有": "#F39C12",
            "使用": "#F39C12",
        }
        for k, v in mapping.items():
            if k in (t or ""):
                return QColor(v)
        return QColor("#7F8C8D")

    def update_path(self):
        src = self.source.pos()
        tgt = self.target.pos()
        dx = tgt.x() - src.x()
        dy = tgt.y() - src.y()
        length = math.hypot(dx, dy)
        if length < 1:
            self.setPath(QPainterPath())
            return

        ux, uy = dx / length, dy / length
        start = QPointF(src.x() + ux * NODE_RADIUS,
                        src.y() + uy * NODE_RADIUS)
        end = QPointF(tgt.x() - ux * NODE_RADIUS,
                      tgt.y() - uy * NODE_RADIUS)
        line_end = QPointF(end.x() - ux * ARROW_SIZE,
                           end.y() - uy * ARROW_SIZE)

        path = QPainterPath()
        path.moveTo(start)
        path.lineTo(line_end)

        w = ARROW_SIZE
        p1 = QPointF(end.x() - ux * w - uy * w * 0.5,
                     end.y() - uy * w + ux * w * 0.5)
        p2 = QPointF(end.x() - ux * w + uy * w * 0.5,
                     end.y() - uy * w - ux * w * 0.5)
        path.moveTo(p1)
        path.lineTo(end)
        path.lineTo(p2)
        self.setPath(path)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemSelectedHasChanged:
            if value:
                self.setPen(QPen(QColor("#FF8C00"), 3))
            else:
                self.setPen(QPen(self.base_color, 2))
        return super().itemChange(change, value)


# ============================================================
# 场景与视图
# ============================================================

class RelationGraphScene(QGraphicsScene):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.nodes = {}     # endpoint -> node
        self.edges = []

    def clear_graph(self):
        self.nodes.clear()
        self.edges.clear()
        self.clear()

    def set_relations(self, relations, extra_character_names=None):
        """
        重建图。
        - 节点从 relations 的两端自动提取
        - extra_character_names：额外显示的孤立角色名
        """
        self.clear_graph()

        endpoints = {}
        for rel in relations:
            a = rel.get("from", "")
            b = rel.get("to", "")
            if a and a not in endpoints:
                _, name = parse_endpoint(a)
                endpoints[a] = name
            if b and b not in endpoints:
                _, name = parse_endpoint(b)
                endpoints[b] = name

        if extra_character_names:
            for name in extra_character_names:
                ep = f"character:{name}"
                if ep not in endpoints:
                    endpoints[ep] = name

        for ep, name in endpoints.items():
            node = create_node(ep, name)
            self.addItem(node)
            self.nodes[ep] = node

        for rel in relations:
            a = rel.get("from", "")
            b = rel.get("to", "")
            if a not in self.nodes or b not in self.nodes:
                continue
            edge = RelationEdge(
                self.nodes[a], self.nodes[b],
                rel.get("type", ""), rel.get("description", ""),
            )
            self.addItem(edge)
            self.edges.append(edge)

        self.relayout()

    def relayout(self):
        n = len(self.nodes)
        if n == 0:
            self.setSceneRect(0, 0, 400, 400)
            return
        if n == 1:
            list(self.nodes.values())[0].setPos(0, 0)
        else:
            radius = max(180, n * 34)
            for i, node in enumerate(self.nodes.values()):
                angle = 2 * math.pi * i / n - math.pi / 2
                node.setPos(radius * math.cos(angle),
                            radius * math.sin(angle))
        self.update_edges()
        rect = self.itemsBoundingRect()
        self.setSceneRect(rect.adjusted(-100, -100, 100, 100))

    def update_edges(self):
        for edge in self.edges:
            edge.update_path()

    def find_edge(self, a_endpoint, b_endpoint, rel_type):
        for edge in self.edges:
            if (edge.source.endpoint == a_endpoint
                    and edge.target.endpoint == b_endpoint
                    and edge.relation_type == rel_type):
                return edge
        return None


class RelationGraphView(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setProperty("role", "graph")
        self._apply_graph_theme()
        controller().theme_changed.connect(self._apply_graph_theme)

    def _apply_graph_theme(self, _key=None):
        self.setBackgroundBrush(QBrush(QColor(current_palette().surface)))
        repolish(self)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(factor, factor)
        else:
            super().wheelEvent(event)