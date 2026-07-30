import math
from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsObject, QGraphicsItem, QWidget, QVBoxLayout
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtProperty, QPropertyAnimation, pyqtSignal, QTimer, QVariantAnimation, QLineF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPainterPath

class DataPacketItem(QGraphicsObject):
    """A visual representation of data flowing along an edge."""
    def __init__(self, source_node, dest_node, message="", parent=None):
        super().__init__(parent)
        self.source_node = source_node
        self.dest_node = dest_node
        self.message = message
        self._progress = 0.0
        
        # Calculate precise bounding rect to avoid paint artifacts
        self._cached_rect = QRectF(-5, -5, 10, 10)
        if self.message:
            from PyQt6.QtGui import QFontMetrics
            font = QFont("Segoe UI", 7)
            fm = QFontMetrics(font)
            text_rect = fm.boundingRect(self.message)
            bg_rect = QRectF(-text_rect.width()/2 - 4, -18 - text_rect.height(), text_rect.width() + 8, text_rect.height() + 4)
            self._cached_rect = bg_rect.united(QRectF(-5, -5, 10, 10)).adjusted(-5, -5, 5, 5)
            
        self.setPos(self.source_node.pos())
        self.setZValue(3)  # Above nodes and edges

    @pyqtProperty(float)
    def progress(self):
        return self._progress

    @progress.setter
    def progress(self, val):
        self._progress = val
        path = self._get_path()
        new_pos = path.pointAtPercent(self._progress)
        self.setPos(new_pos)
        self.update()

    def _get_path(self):
        p1 = self.source_node.pos()
        p2 = self.dest_node.pos()
        path = QPainterPath()
        path.moveTo(p1)
        path.lineTo(p2)
        return path

    def boundingRect(self):
        return self._cached_rect

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        if self.message:
            font = QFont("Segoe UI", 7)
            painter.setFont(font)
            fm = painter.fontMetrics()
            text_rect = fm.boundingRect(self.message)
            # Center text above the dot
            bg_rect = QRectF(-text_rect.width()/2 - 4, -18 - text_rect.height(), text_rect.width() + 8, text_rect.height() + 4)
            
            painter.setBrush(QBrush(QColor(30, 30, 30, 200)))
            painter.setPen(QPen(QColor(100, 100, 100, 150)))
            painter.drawRoundedRect(bg_rect, 3, 3)
            
            painter.setPen(QPen(QColor(220, 220, 220)))
            painter.drawText(bg_rect, Qt.AlignmentFlag.AlignCenter, self.message)

        painter.setBrush(QBrush(QColor(0, 255, 255, 200))) # Cyan glowing packet
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(-4, -4, 8, 8)

class ActionBadgeItem(QGraphicsObject):
    """Temporary badge shown when an agent uses a tool."""
    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.text = text
        self._opacity = 1.0
        self.setZValue(4)
        
        from PyQt6.QtGui import QFontMetrics, QFont
        font = QFont("Segoe UI", 8, QFont.Weight.Bold)
        fm = QFontMetrics(font)
        text_rect = fm.boundingRect(self.text)
        self._cached_rect = QRectF(-text_rect.width()/2 - 10, -15, text_rect.width() + 20, text_rect.height() + 15)
        
        # Fade out animation
        self.fade_anim = QVariantAnimation(self)
        self.fade_anim.setStartValue(1.0)
        self.fade_anim.setEndValue(0.0)
        self.fade_anim.setDuration(3000)
        self.fade_anim.valueChanged.connect(self._update_opacity)
        self.fade_anim.finished.connect(self._on_finished)
        self.fade_anim.start()
        
    def _update_opacity(self, value):
        self._opacity = value
        self.update()
        
    def _on_finished(self):
        if self.scene():
            self.scene().removeItem(self)

    def boundingRect(self):
        return self._cached_rect

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(self._opacity)
        
        font = QFont("Segoe UI", 8, QFont.Weight.Bold)
        painter.setFont(font)
        fm = painter.fontMetrics()
        text_rect = fm.boundingRect(self.text)
        
        bg_rect = QRectF(-text_rect.width()/2 - 6, -10, text_rect.width() + 12, text_rect.height() + 6)
        
        painter.setBrush(QBrush(QColor(60, 40, 100, 220))) # Purple badge
        painter.setPen(QPen(QColor(150, 100, 255, 255)))
        painter.drawRoundedRect(bg_rect, 4, 4)
        
        painter.setPen(QPen(QColor(255, 255, 255)))
        painter.drawText(bg_rect, Qt.AlignmentFlag.AlignCenter, self.text)


from PyQt6.QtGui import QPainterPathStroker
import os

class EdgeItem(QGraphicsObject):
    hover_entered = pyqtSignal(object, object)
    hover_left = pyqtSignal(object)
    
    def __init__(self, source_node, dest_node, parent=None):
        super().__init__(parent)
        self.source_node = source_node
        self.dest_node = dest_node
        self.source_node.add_edge(self)
        self.dest_node.add_edge(self)
        self.setZValue(1)
        self.setAcceptHoverEvents(True)
        self.messages = []

    def add_message(self, message):
        self.messages.append(message)

    def boundingRect(self):
        if not self.source_node or not self.dest_node:
            return QRectF()
        extra = 15
        p1 = self.source_node.pos()
        p2 = self.dest_node.pos()
        rect = QRectF(p1, p2).normalized()
        return rect.adjusted(-extra, -extra, extra, extra)

    def _get_path(self):
        p1 = self.source_node.pos()
        p2 = self.dest_node.pos()
        path = QPainterPath()
        path.moveTo(p1)
        path.lineTo(p2)
        return path

    def shape(self):
        path = QPainterPath()
        if not self.source_node or not self.dest_node:
            return path
        
        edge_path = self._get_path()
        stroker = QPainterPathStroker()
        stroker.setWidth(15)
        return stroker.createStroke(edge_path)

    def paint(self, painter, option, widget):
        if not self.source_node or not self.dest_node:
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        edge_path = self._get_path()
        
        is_hovered = self.isUnderMouse()
        color = QColor(150, 150, 200, 200) if is_hovered else QColor(100, 100, 100, 150)
        
        pen = QPen(color)
        pen.setWidth(4 if is_hovered else 2)
        painter.setPen(pen)
        painter.drawPath(edge_path)

    def hoverEnterEvent(self, event):
        self.hover_entered.emit(self, event)
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.hover_left.emit(self)
        self.update()
        super().hoverLeaveEvent(event)

    def adjust(self):
        self.prepareGeometryChange()
        self.update()

class NodeItem(QGraphicsObject):
    def __init__(self, node_id, label, graph_widget, parent=None):
        super().__init__(parent)
        self.node_id = node_id
        self.label = label
        self.graph_widget = graph_widget
        self.edges = []
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)
        self.setZValue(2)
        
        self.width = 240
        self.height = 160
        self.setAcceptHoverEvents(True)
        
        # State: idle, thinking, waiting_user, error, success
        self.state = "idle"
        self._glow_intensity = 0.0

        # Information for synthetic display
        self.exchanged_files = []
        self.reports = []
        self.used_tools = {}

        # Animation for active states
        self.glow_anim = QVariantAnimation(self)
        self.glow_anim.setStartValue(0.0)
        self.glow_anim.setEndValue(1.0)
        self.glow_anim.setDuration(800)
        self.glow_anim.setLoopCount(-1)  # Infinite
        self.glow_anim.valueChanged.connect(self._update_glow)
        
    def _recalc_size(self):
        h = 90
        if self.exchanged_files:
            h += 20 + len(self.exchanged_files) * 22
        if self.reports:
            h += 26 + len(self.reports) * 22
        if self.used_tools:
            h += 26 + min(len(self.used_tools), 3) * 22
        self.prepareGeometryChange()
        self.height = max(160, h)
        self.update()

    def add_tool(self, tool_name):
        self.used_tools[tool_name] = self.used_tools.get(tool_name, 0) + 1
        self._recalc_size()

    def add_edge(self, edge):
        self.edges.append(edge)

    def add_file(self, filename, action_type="read"):
        existing = next((item for item in self.exchanged_files if isinstance(item, dict) and item.get("name") == filename), None)
        if existing:
            existing["action"] = action_type
        else:
            self.exchanged_files.append({"name": filename, "action": action_type})
            if len(self.exchanged_files) > 3:
                self.exchanged_files.pop(0)
            self._recalc_size()
            
    def add_report(self, report_name):
        if report_name not in self.reports:
            self.reports.append(report_name)
            if len(self.reports) > 2:
                self.reports.pop(0)
            self._recalc_size()

    def set_state(self, state):
        self.state = state
        if state in ["thinking", "waiting_user", "error", "success"]:
            if self.glow_anim.state() != QPropertyAnimation.State.Running:
                self.glow_anim.start()
        else:
            self.glow_anim.stop()
            self._glow_intensity = 0.0
            
        self.update()

    def _update_glow(self, value):
        if self.state == "waiting_user":
            # Blink faster
            self._glow_intensity = 0.1 + (math.sin(value * math.pi * 4) + 1) * 0.45
        else:
            # Pulse normally
            self._glow_intensity = 0.2 + (math.sin(value * math.pi * 2) + 1) * 0.4
        self.update()

    def boundingRect(self):
        return QRectF(-self.width/2 - 15, -self.height/2 - 15, self.width + 30, self.height + 30)

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        glow_color = None
        border_color = QColor(60, 70, 90)
        
        if self.state == "thinking":
            glow_color = QColor(0, 150, 255, int(100 * self._glow_intensity))
            border_color = QColor(0, 200, 255)
        elif self.state == "waiting_user":
            glow_color = QColor(255, 200, 0, int(120 * self._glow_intensity))
            border_color = QColor(255, 200, 0)
        elif self.state == "error":
            glow_color = QColor(255, 50, 50, int(100 * self._glow_intensity))
            border_color = QColor(255, 100, 100)
        elif self.state == "success":
            glow_color = QColor(50, 255, 50, int(100 * self._glow_intensity))
            border_color = QColor(100, 255, 100)
            
        rect = QRectF(-self.width/2, -self.height/2, self.width, self.height)
            
        # Draw Glow
        if glow_color:
            painter.setBrush(QBrush(glow_color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect.adjusted(-6, -6, 6, 6), 12, 12)
            
        # Draw Node body (Dark blueish background like in reference image)
        base_color = QColor(30, 34, 48) 
        painter.setBrush(QBrush(base_color))
        pen = QPen(border_color)
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawRoundedRect(rect, 8, 8)
        
        # Header (Label)
        painter.setPen(QPen(QColor(255, 255, 255)))
        font_header = QFont("Segoe UI", 11, QFont.Weight.Bold)
        painter.setFont(font_header)
        title = self.label
        if self.node_id == "orchestrator":
            title = "⭐ " + title
        painter.drawText(QRectF(-self.width/2 + 15, -self.height/2 + 10, self.width-30, 25), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, title)
        
        # Separator line
        painter.setPen(QPen(QColor(60, 70, 90)))
        painter.drawLine(int(-self.width/2 + 15), int(-self.height/2 + 35), int(self.width/2 - 15), int(-self.height/2 + 35))
        
        # Info text (synthetic info)
        font_body = QFont("Segoe UI", 9)
        painter.setFont(font_body)
        
        y_offset = -self.height/2 + 45
        
        if not self.exchanged_files and not self.reports:
            painter.setPen(QPen(QColor(120, 130, 150)))
            if self.state == "success":
                status_text = "Mission accomplie" if self.node_id == "orchestrator" else "Terminé"
                painter.drawText(QRectF(-self.width/2 + 15, y_offset, self.width-30, 20), Qt.AlignmentFlag.AlignLeft, status_text)
            else:
                painter.drawText(QRectF(-self.width/2 + 15, y_offset, self.width-30, 20), Qt.AlignmentFlag.AlignLeft, "En attente d'activité...")
        
        if self.exchanged_files:
            painter.setPen(QPen(QColor(180, 190, 210)))
            painter.drawText(QRectF(-self.width/2 + 15, y_offset, self.width-30, 15), Qt.AlignmentFlag.AlignLeft, "📄 Fichiers & Écrans :")
            y_offset += 20
            for f_info in self.exchanged_files:
                if isinstance(f_info, str):
                    f_name = f_info
                    action = "read"
                else:
                    f_name = f_info.get("name", "")
                    action = f_info.get("action", "read")

                display_name = f_name if len(f_name) < 28 else "..." + f_name[-25:]
                
                if action == "read":
                    display_name = f"👁️ {display_name}"
                elif action == "read_image":
                    display_name = f"🖼️ {display_name}"
                elif action == "write":
                    display_name = f"✏️ {display_name}"
                elif action == "delete":
                    display_name = f"🗑️ {display_name}"
                elif action == "scan":
                    display_name = f"🔎 {display_name}"
                elif action == "cmd":
                    display_name = f"⚙️ {display_name}"

                fm = painter.fontMetrics()
                tw = fm.horizontalAdvance(display_name)
                pill_rect = QRectF(-self.width/2 + 25, y_offset, tw + 10, 18)
                painter.setBrush(QBrush(QColor(45, 55, 75)))
                painter.setPen(QPen(QColor(80, 90, 110)))
                painter.drawRoundedRect(pill_rect, 4, 4)
                
                painter.setPen(QPen(QColor(200, 220, 255)))
                painter.drawText(pill_rect, Qt.AlignmentFlag.AlignCenter, display_name)
                y_offset += 22
                
        if self.reports:
            if self.exchanged_files:
                y_offset += 6
            painter.setPen(QPen(QColor(180, 190, 210)))
            painter.drawText(QRectF(-self.width/2 + 15, y_offset, self.width-30, 15), Qt.AlignmentFlag.AlignLeft, "📊 Rapports:")
            y_offset += 20
            for r in self.reports:
                r_name = r if len(r) < 28 else "..." + r[-25:]
                
                fm = painter.fontMetrics()
                tw = fm.horizontalAdvance(r_name)
                pill_rect = QRectF(-self.width/2 + 25, y_offset, tw + 10, 18)
                painter.setBrush(QBrush(QColor(35, 65, 45)))
                painter.setPen(QPen(QColor(60, 110, 70)))
                painter.drawRoundedRect(pill_rect, 4, 4)
                
                painter.setPen(QPen(QColor(150, 255, 180)))
                painter.drawText(pill_rect, Qt.AlignmentFlag.AlignCenter, r_name)
                y_offset += 22

        if self.used_tools:
            if self.exchanged_files or self.reports:
                y_offset += 6
            painter.setPen(QPen(QColor(180, 190, 210)))
            painter.drawText(QRectF(-self.width/2 + 15, y_offset, self.width-30, 15), Qt.AlignmentFlag.AlignLeft, "🛠️ Outils utilisés:")
            y_offset += 20
            
            sorted_tools = sorted(self.used_tools.items(), key=lambda x: x[1], reverse=True)
            for t_name, count in sorted_tools[:3]:
                display_str = f"{t_name} x{count}"
                fm = painter.fontMetrics()
                tw = fm.horizontalAdvance(display_str)
                pill_rect = QRectF(-self.width/2 + 25, y_offset, tw + 10, 18)
                painter.setBrush(QBrush(QColor(60, 50, 70)))
                painter.setPen(QPen(QColor(100, 80, 120)))
                painter.drawRoundedRect(pill_rect, 4, 4)
                
                painter.setPen(QPen(QColor(220, 200, 255)))
                painter.drawText(pill_rect, Qt.AlignmentFlag.AlignCenter, display_str)
                y_offset += 22

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for edge in self.edges:
                edge.adjust()
        return super().itemChange(change, value)
        
    def mousePressEvent(self, event):
        self._drag_start_pos = event.scenePos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if hasattr(self, '_drag_start_pos'):
            diff = event.scenePos() - self._drag_start_pos
            if abs(diff.x()) < 5 and abs(diff.y()) < 5:
                self.graph_widget.node_clicked.emit(self.node_id)


class NodeGraphWidget(QGraphicsView):
    node_clicked = pyqtSignal(str)
    edge_hovered = pyqtSignal(object, object)
    edge_hover_left = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.scene.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)
        self.scene.setSceneRect(-2000, -2000, 4000, 4000)
        self.setScene(self.scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setStyleSheet("background-color: #1a1e24; border: none;") # Darker background
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        
        self.nodes = {}
        self.edges = []
        
        self.physics_timer = QTimer(self)
        self.physics_timer.timeout.connect(self._apply_forces)
        self.physics_timer.start(30)
        
        # Initialize default orchestrator node
        self.add_node("orchestrator", "Orchestrateur")
        
    def _apply_forces(self):
        if not self.nodes:
            return
            
        k = 0.05
        c = 60000.0
        ideal_len = 350.0
        
        forces = {node_id: QPointF(0, 0) for node_id in self.nodes}
        
        node_ids = list(self.nodes.keys())
        for i in range(len(node_ids)):
            n1 = self.nodes[node_ids[i]]
            for j in range(i + 1, len(node_ids)):
                n2 = self.nodes[node_ids[j]]
                dx = n2.x() - n1.x()
                dy = n2.y() - n1.y()
                dist_sq = dx*dx + dy*dy
                if dist_sq < 1:
                    dist_sq = 1
                    dx, dy = 1, 0
                
                f = c / dist_sq
                dist = math.sqrt(dist_sq)
                fx = f * dx / dist
                fy = f * dy / dist
                
                # Anti-chevauchement (Anti-overlap) fort pour que les fenêtres ne se touchent pas
                min_dx = (n1.width + n2.width) / 2.0 + 40.0
                min_dy = (n1.height + n2.height) / 2.0 + 40.0
                
                if abs(dx) < min_dx and abs(dy) < min_dy:
                    overlap_x = min_dx - abs(dx)
                    overlap_y = min_dy - abs(dy)
                    
                    push_factor = 150.0
                    
                    if overlap_y < overlap_x:
                        push_y = push_factor * (overlap_y / min_dy)
                        fy += push_y if dy >= 0 else -push_y
                        # Jitter seulement si empilement parfait
                        if abs(dx) < 2:
                            fx += (push_factor * 0.15) if dx >= 0 else -(push_factor * 0.15)
                    else:
                        push_x = push_factor * (overlap_x / min_dx)
                        fx += push_x if dx >= 0 else -push_x
                        if abs(dy) < 2:
                            fy += (push_factor * 0.15) if dy >= 0 else -(push_factor * 0.15)
                
                forces[node_ids[i]] -= QPointF(fx, fy)
                forces[node_ids[j]] += QPointF(fx, fy)
                
        for edge in self.edges:
            n1 = edge.source_node
            n2 = edge.dest_node
            dx = n2.x() - n1.x()
            dy = n2.y() - n1.y()
            dist = math.sqrt(dx*dx + dy*dy)
            if dist > 0:
                f = k * (dist - ideal_len)
                fx = f * dx / dist
                fy = f * dy / dist
                forces[n1.node_id] += QPointF(fx, fy)
                forces[n2.node_id] -= QPointF(fx, fy)
                
        for node_id, node in self.nodes.items():
            target_x = 0
            # Répartir naturellement les cibles Y selon le nom du nœud pour éviter les amas au centre
            target_y = (hash(node_id) % 600) - 300
            
            if node_id in ("orchestrator", "assistant_general"):
                target_x = -400
                target_y = 0
            elif str(node_id).startswith("folder_"):
                target_x = 400
            else:
                target_x = 0
            
            # Application d'une force pour tirer les nœuds vers leur colonne (X) et position (Y)
            forces[node_id].setX(forces[node_id].x() - (node.x() - target_x) * 0.05)
            forces[node_id].setY(forces[node_id].y() - (node.y() - target_y) * 0.02)
                
        damping = 0.8
        for node_id, node in self.nodes.items():
            if node.scene() and node.scene().mouseGrabberItem() == node:
                continue
                
            fx, fy = forces[node_id].x(), forces[node_id].y()
            
            v = math.sqrt(fx*fx + fy*fy)
            if v > 40:
                fx = fx / v * 40
                fy = fy / v * 40
                
            fx *= damping
            fy *= damping
            
            # Augmentation du seuil d'arrêt pour éviter les micro-tremblements continus
            if abs(fx) > 0.8 or abs(fy) > 0.8:
                node.setPos(node.x() + fx, node.y() + fy)

    def _recalc_layout(self):
        pass

    def add_node(self, node_id, label):
        if node_id in self.nodes:
            return self.nodes[node_id]
        
        node = NodeItem(node_id, label, self)
        self.scene.addItem(node)
        self.nodes[node_id] = node
        
        import random
        rx, ry = random.randint(-50, 50), random.randint(-50, 50)
        
        if node_id in ("orchestrator", "assistant_general"):
            node.setPos(-200 + rx, ry)
        elif str(node_id).startswith("folder_"):
            node.setPos(550 + rx, ry)
            self._recalc_layout()
        else:
            if "orchestrator" in self.nodes:
                self.add_edge("orchestrator", node_id)
            elif "assistant_general" in self.nodes:
                self.add_edge("assistant_general", node_id)
            node.setPos(200 + rx, ry)
            self._recalc_layout()
            
        return node

    def add_edge(self, source_id, dest_id):
        if source_id not in self.nodes or dest_id not in self.nodes:
            return None
        for e in self.edges:
            if (e.source_node.node_id == source_id and e.dest_node.node_id == dest_id) or \
               (e.source_node.node_id == dest_id and e.dest_node.node_id == source_id):
                return e
        edge = EdgeItem(self.nodes[source_id], self.nodes[dest_id])
        edge.hover_entered.connect(self._on_edge_hover_enter)
        edge.hover_left.connect(self._on_edge_hover_leave)
        self.scene.addItem(edge)
        self.edges.append(edge)
        return edge

    def _on_edge_hover_enter(self, edge, event):
        view_pos = self.mapFromScene(event.scenePos())
        self.edge_hovered.emit(edge, view_pos)

    def _on_edge_hover_leave(self, edge):
        self.edge_hover_left.emit(edge)

    def set_agent_active(self, agent_id):
        if agent_id and agent_id not in self.nodes:
            try:
                from core.utils import AGENTS_CONFIG
                label = AGENTS_CONFIG.get(agent_id, {}).get("name", agent_id)
            except Exception:
                label = agent_id
            self.add_node(agent_id, label)
        for nid, node in self.nodes.items():
            if nid == "orchestrator" or nid == agent_id:
                node.set_state("thinking")
            else:
                node.set_state("idle")

    def update_agent_state(self, agent_id, state):
        if agent_id in self.nodes:
            self.nodes[agent_id].set_state(state)

    def show_agent_action(self, agent_id, action_name, target):
        if agent_id in self.nodes:
            node = self.nodes[agent_id]
            node.add_tool(action_name)
            
            # Update synthetic information dynamically
            if action_name in ("write_file", "edit_file", "multi_replace_file_content", "replace_file_content", "delete_file", "rename_file", "read_file", "list_dir", "read_image"):
                if target:
                    filename = os.path.basename(target)
                    if not filename:
                        filename = os.path.basename(os.path.dirname(target))
                    
                    if action_name in ("write_file", "edit_file", "multi_replace_file_content", "replace_file_content", "rename_file"):
                        action_type = "write"
                    elif action_name == "delete_file":
                        action_type = "delete"
                    elif action_name == "read_file":
                        action_type = "read"
                    elif action_name == "read_image":
                        action_type = "read_image"
                    elif action_name == "list_dir":
                        action_type = "scan"
                    else:
                        action_type = "read"
                    
                    if action_name != "list_dir":
                        node.add_file(filename, action_type=action_type)
                        
                    # Logic for directory windows and data flow
                    folder_path = os.path.dirname(target) if action_name != "list_dir" else target
                    folder_name = os.path.basename(folder_path) or "racine"
                    folder_id = f"folder_{folder_name}"
                    folder_label = f"📁 {folder_name}"
                    
                    # Ensure folder node exists
                    if folder_id not in self.nodes:
                        self.add_node(folder_id, folder_label)
                        folder_node = self.nodes[folder_id]
                        # Position randomly around top right initially, _recalc_layout will arrange them
                        import random
                        folder_node.setPos(550, -300 + random.randint(-50, 50))
                    
                    folder_node = self.nodes[folder_id]
                    if action_name != "list_dir":
                        folder_node.add_file(filename, action_type=action_type)
                    else:
                        folder_node.add_file("Recherche/Scan", action_type="scan")
                        
                    if action_name == "read_file":
                        msg = f"Lecture {filename}"
                    elif action_name == "read_image":
                        msg = f"Lecture image {filename}"
                    elif action_name == "list_dir":
                        msg = f"Scan {folder_name}"
                    else:
                        msg = f"Écriture {filename}"
                    
                    if action_name in ("write_file", "edit_file", "multi_replace_file_content", "replace_file_content", "delete_file", "rename_file"):
                        self.trigger_data_flow(agent_id, folder_id, msg)
                    else:
                        self.trigger_data_flow(folder_id, agent_id, msg)

            elif action_name == "publish_report":
                if target:
                    node.add_report(os.path.basename(target))
            elif action_name == "run_command" or action_name == "run_named_command":
                cmd_name = target.split()[0] if target else 'cmd'
                node.add_file(f"> {cmd_name}", action_type="cmd")
            
            # Transient badge for action
            text = f"🛠️ {action_name}"
            if target:
                target_short = target if len(target) < 20 else target[:17] + "..."
                text += f" ({target_short})"
                
            badge = ActionBadgeItem(text)
            self.scene.addItem(badge)
            badge.setPos(node.pos() + QPointF(0, -node.height/2 - 20))

    def trigger_data_flow(self, source_id, target_id, message=""):
        def _ensure_node(node_id):
            if node_id not in self.nodes:
                try:
                    from core.utils import AGENTS_CONFIG
                    label = AGENTS_CONFIG.get(node_id, {}).get("name", node_id)
                except Exception:
                    label = node_id
                self.add_node(node_id, label)
                
        _ensure_node(source_id)
        _ensure_node(target_id)
            
        source_node = self.nodes[source_id]
        target_node = self.nodes[target_id]
        
        edge = self.add_edge(source_id, target_id)
        if edge and message:
            edge.add_message(message)
        
        packet = DataPacketItem(source_node, target_node, message)
        self.scene.addItem(packet)
        
        anim = QPropertyAnimation(packet, b"progress")
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        
        dist = QLineF(source_node.pos(), target_node.pos()).length()
        speed = 350.0  # pixels per second
        duration = int((dist / max(1.0, speed)) * 1000)
        duration = max(600, min(3000, duration))
        anim.setDuration(duration)
        
        def on_finished():
            self.scene.removeItem(packet)
            
        anim.finished.connect(on_finished)
        anim.start()
        packet._anim = anim
        
    def reset_graph(self):
        self.scene.clear()
        self.nodes.clear()
        self.edges.clear()
        
        try:
            from core.utils import AGENTS_CONFIG
            # N'ajouter que l'orchestrateur au démarrage. Les autres s'ajouteront dynamiquement s'ils sont utilisés.
            if "orchestrator" in AGENTS_CONFIG:
                self.add_node("orchestrator", AGENTS_CONFIG["orchestrator"].get("name", "Orchestrateur"))
            elif "assistant_general" in AGENTS_CONFIG:
                self.add_node("assistant_general", AGENTS_CONFIG["assistant_general"].get("name", "Assistant Général"))
            else:
                self.add_node("orchestrator", "Orchestrateur")
        except Exception:
            self.add_node("orchestrator", "Orchestrateur")
    def wheelEvent(self, event):
        zoom_in_factor = 1.15
        zoom_out_factor = 1 / zoom_in_factor
        if event.angleDelta().y() > 0:
            zoom_factor = zoom_in_factor
        else:
            zoom_factor = zoom_out_factor
        self.scale(zoom_factor, zoom_factor)

