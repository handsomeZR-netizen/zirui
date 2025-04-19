import sys
import os
import json
import math
import logging
from datetime import datetime
from PyQt6.QtWidgets import (QGraphicsItem, QGraphicsEllipseItem, QGraphicsRectItem, 
                            QGraphicsLineItem, QGraphicsPathItem, QGraphicsSimpleTextItem,
                            QMenu, QInputDialog, QDialog, QVBoxLayout, QFormLayout,
                            QLineEdit, QPushButton, QLabel, QDoubleSpinBox, QMessageBox,
                            QCheckBox, QHBoxLayout, QFileDialog)
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QPainter, QPen, QColor, QBrush, QPainterPath, QFont
import numpy as np

# 创建logs目录
if not os.path.exists('logs'):
    os.makedirs('logs')

# 设置日志记录
log_filename = os.path.join('logs', f'circuit_debug_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filename, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('CircuitSimulator')

class Wire(QGraphicsPathItem):
    def __init__(self, start_pos, parent=None):
        super().__init__(parent)
        self.setZValue(0)
        self.start_pos = start_pos
        self.end_pos = start_pos
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setPen(QPen(Qt.GlobalColor.black, 2))
        self.update_path()
        self.source_component = None
        self.target_component = None
        self.source_point = None
        self.target_point = None
        self.snap_distance = 10.0
        self.joint_clickable_radius = 8.0  # 关节点可点击半径
        self.path_points = []  # 保存路径上的点
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton)
        logger.debug(f"创建新导线: start_pos={start_pos}")
        
    def paint(self, painter, option, widget):
        """重写paint方法，根据选中状态改变外观"""
        # 根据选中状态设置不同的画笔
        if self.isSelected():
            pen = QPen(QColor(30, 144, 255), 2, Qt.PenStyle.SolidLine)  # 选中时为蓝色
        else:
            pen = QPen(Qt.GlobalColor.black, 2)
        self.setPen(pen)
        
        # 调用父类的paint方法
        super().paint(painter, option, widget)
        
        # 如果被选中，绘制导线上的关节点
        if self.isSelected():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(255, 0, 0, 180)))
            
            # 绘制端点
            painter.drawEllipse(self.start_pos, 4, 4)
            painter.drawEllipse(self.end_pos, 4, 4)
            
            # 绘制中间关节点
            painter.setBrush(QBrush(QColor(0, 120, 215, 180)))
            for i, point in enumerate(self.path_points):
                if i > 0 and i < len(self.path_points) - 1:  # 跳过起点和终点
                    painter.drawEllipse(point, 4, 4)
            
    def update_path(self):
        try:
            path = QPainterPath()
            path.moveTo(self.start_pos)
            
            # 计算中间点，实现直角转弯
            dx = self.end_pos.x() - self.start_pos.x()
            dy = self.end_pos.y() - self.start_pos.y()
            
            self.path_points = [self.start_pos]
            # 根据起点和终点的相对位置决定路径
            if abs(dx) > abs(dy):
                # 水平方向为主
                mid_x = self.start_pos.x() + dx / 2
                mid_point1 = QPointF(mid_x, self.start_pos.y())
                mid_point2 = QPointF(mid_x, self.end_pos.y())
                path.lineTo(mid_point1)
                path.lineTo(mid_point2)
                self.path_points.extend([mid_point1, mid_point2])
            else:
                # 垂直方向为主
                mid_y = self.start_pos.y() + dy / 2
                mid_point1 = QPointF(self.start_pos.x(), mid_y)
                mid_point2 = QPointF(self.end_pos.x(), mid_y)
                path.lineTo(mid_point1)
                path.lineTo(mid_point2)
                self.path_points.extend([mid_point1, mid_point2])
            
            path.lineTo(self.end_pos)
            self.path_points.append(self.end_pos)
            
            self.setPath(path)
            logger.debug(f"更新导线路径: start={self.start_pos}, end={self.end_pos}, points={len(self.path_points)}")
        except Exception as e:
            logger.error(f"更新导线路径时出错: {str(e)}", exc_info=True)
    
    def show_context_menu(self, event):
        menu = QMenu()
        delete_action = menu.addAction("删除导线")
        add_joint_action = menu.addAction("添加关节点")
        action = menu.exec(event.screenPos())
        
        if action == delete_action:
            self.delete_wire()
        elif action == add_joint_action:
            self.add_joint_at_position(event.scenePos())

    def add_joint_at_position(self, pos):
        """在指定位置添加一个关节点"""
        if len(self.path_points) < 2:
            return
            
        # 找到最接近的线段
        min_dist = float('inf')
        insert_index = -1
        
        for i in range(len(self.path_points) - 1):
            p1 = self.path_points[i]
            p2 = self.path_points[i + 1]
            
            # 计算点到线段的距离
            line_length = math.sqrt((p2.x() - p1.x())**2 + (p2.y() - p1.y())**2)
            if line_length == 0:
                continue
                
            # 计算投影点
            t = ((pos.x() - p1.x()) * (p2.x() - p1.x()) + 
                 (pos.y() - p1.y()) * (p2.y() - p1.y())) / (line_length * line_length)
            
            t = max(0, min(1, t))  # 确保t在[0,1]范围内
            
            proj_x = p1.x() + t * (p2.x() - p1.x())
            proj_y = p1.y() + t * (p2.y() - p1.y())
            
            dist = math.sqrt((proj_x - pos.x())**2 + (proj_y - pos.y())**2)
            
            if dist < min_dist:
                min_dist = dist
                insert_index = i + 1
                
        # 在找到的位置插入新的关节点
        if insert_index > 0:
            self.path_points.insert(insert_index, QPointF(pos))
            self.update_path_from_points()

    def delete_wire(self):
        # 断开两端连接
        self.disconnect_endpoint(True)  # 断开起点
        self.disconnect_endpoint(False)  # 断开终点
        
        # 从场景中移除
        if self.scene():
            self.scene().removeItem(self)

    def disconnect_endpoint(self, is_start):
        """断开指定端点的连接"""
        try:
            if is_start and self.source_point:
                if self in self.source_point.connected_wires:
                    self.source_point.connected_wires.remove(self)
                self.source_point = None
                self.source_component = None
                logger.debug(f"断开导线起点")
            elif not is_start and self.target_point:
                if self in self.target_point.connected_wires:
                    self.target_point.connected_wires.remove(self)
                self.target_point = None
                self.target_component = None
                logger.debug(f"断开导线终点")
        except Exception as e:
            logger.error(f"断开导线连接出错: {str(e)}", exc_info=True)

    def connect_endpoint(self, connection_point, is_start):
        """连接到新的连接点"""
        try:
            if is_start:
                if self.source_point:  # 如果已经有连接，先断开
                    self.disconnect_endpoint(True)
                self.source_point = connection_point
                self.source_component = connection_point.parentItem()
                connection_point.connected_wires.append(self)
                logger.debug(f"导线起点连接到: {connection_point.parentItem().name if connection_point.parentItem() else 'None'}")
            else:
                if self.target_point:  # 如果已经有连接，先断开
                    self.disconnect_endpoint(False)
                self.target_point = connection_point
                self.target_component = connection_point.parentItem()
                connection_point.connected_wires.append(self)
                logger.debug(f"导线终点连接到: {connection_point.parentItem().name if connection_point.parentItem() else 'None'}")
        except Exception as e:
            logger.error(f"连接导线端点出错: {str(e)}", exc_info=True)
    
    def update_path_from_points(self):
        """根据路径点更新路径"""
        if len(self.path_points) < 2:
            return
            
        try:
            path = QPainterPath()
            path.moveTo(self.path_points[0])
            
            for i in range(1, len(self.path_points)):
                path.lineTo(self.path_points[i])
                
            self.setPath(path)
        except Exception as e:
            logger.error(f"从路径点更新导线路径时出错: {str(e)}", exc_info=True)
        
    def set_end_pos(self, pos):
        self.end_pos = pos
        self.update_path()

    def update_endpoints_from_connection_points(self):
        """根据连接点更新导线的端点"""
        try:
            if self.source_point:
                self.start_pos = self.source_point.scenePos()
                if len(self.path_points) > 0:
                    self.path_points[0] = self.start_pos
            if self.target_point:
                self.end_pos = self.target_point.scenePos()
                if len(self.path_points) > 1:
                    self.path_points[-1] = self.end_pos
            self.update_path_from_points()
        except Exception as e:
            logger.error(f"更新导线端点出错: {str(e)}", exc_info=True)

class ConnectionPoint(QGraphicsEllipseItem):
    def __init__(self, parent=None, point_type="input"):
        super().__init__(-4, -4, 8, 8, parent)
        self.point_type = point_type  # "input" 或 "output"
        self.setBrush(QBrush(Qt.GlobalColor.yellow))
        self.setPen(QPen(Qt.GlobalColor.black, 1))
        self.setAcceptHoverEvents(True)
        self.connected_wires = []
        
    def hoverEnterEvent(self, event):
        self.setBrush(QBrush(Qt.GlobalColor.red))
        super().hoverEnterEvent(event)
        
    def hoverLeaveEvent(self, event):
        self.setBrush(QBrush(Qt.GlobalColor.yellow))
        super().hoverLeaveEvent(event)

class Component(QGraphicsItem):
    def __init__(self, name, parent=None):
        super().__init__(parent)
        self.setZValue(1)
        self.name = name
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton)
        
        # 初始化连接点
        self.connection_points = []
        self.setup_connection_points()
        
        self.voltage = 0
        self.current = 0
        self.node1 = None
        self.node2 = None
        
        # 添加属性设置
        self.properties = {}
        if self.name == "定值电阻":
            self.properties["电阻值"] = 100.0  # 默认100欧姆
            self.properties["可调范围"] = "0.1-1000"  # 可调范围提示
        elif self.name == "滑动变阻器":
            self.properties["最大电阻值"] = 20.0
            self.properties["滑动位置"] = 0.5
            self._update_current_resistance()
        elif self.name == "开关":
            self.properties["状态"] = False
        elif self.name == "电源":
            self.properties["电压值"] = 12.0  # 默认12V
            self.properties["可调范围"] = "0-24"  # 可调范围提示
            
    def setup_connection_points(self):
        """设置组件的连接点"""
        if self.name in ["定值电阻", "滑动变阻器", "导线", "开关"]:
            # 左侧输入点
            input_point = ConnectionPoint(self, "input")
            input_point.setPos(-self.boundingRect().width() / 2 - 3, 0)
            self.connection_points.append(input_point)
            
            # 右侧输出点
            output_point = ConnectionPoint(self, "output")
            output_point.setPos(self.boundingRect().width() / 2 + 3, 0)
            self.connection_points.append(output_point)
        elif self.name == "电源":
            # 正极（右侧）
            pos_point = ConnectionPoint(self, "output")
            pos_point.setPos(self.boundingRect().width() / 2 + 3, 0)
            pos_point.setBrush(QBrush(Qt.GlobalColor.red))
            self.connection_points.append(pos_point)
            
            # 负极（左侧）
            neg_point = ConnectionPoint(self, "input")
            neg_point.setPos(-self.boundingRect().width() / 2 - 3, 0)
            neg_point.setBrush(QBrush(Qt.GlobalColor.black))
            self.connection_points.append(neg_point)
            
        elif self.name in ["电流表", "电压表"]:
            # 左侧输入点（正极）
            input_point = ConnectionPoint(self, "input")
            input_point.setPos(-self.boundingRect().width() / 2 - 3, 0)
            input_point.setBrush(QBrush(Qt.GlobalColor.red))
            self.connection_points.append(input_point)
            
            # 右侧输出点（负极）
            output_point = ConnectionPoint(self, "output")
            output_point.setPos(self.boundingRect().width() / 2 + 3, 0)
            output_point.setBrush(QBrush(Qt.GlobalColor.black))
            self.connection_points.append(output_point)
            
            # 添加正负极标识
            font = QFont()
            font.setPointSize(8)
            font.setBold(True)
            
            pos_label = QGraphicsSimpleTextItem("+", self)
            pos_label.setFont(font)
            pos_label.setPos(-32, -5)
            
            neg_label = QGraphicsSimpleTextItem("-", self)
            neg_label.setFont(font)
            neg_label.setPos(27, -5)
        
    def get_closest_connection_point(self, scene_pos):
        """获取最近的连接点"""
        min_dist = float('inf')
        closest_point = None
        
        for point in self.connection_points:
            point_pos = point.scenePos()
            dist = math.sqrt((point_pos.x() - scene_pos.x())**2 + 
                           (point_pos.y() - scene_pos.y())**2)
            if dist < min_dist:
                min_dist = dist
                closest_point = point
                
        return closest_point if min_dist <= 10.0 else None

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        # 更新所有连接的导线
        for point in self.connection_points:
            for wire in point.connected_wires:
                wire.update_endpoints_from_connection_points()

    def _update_current_resistance(self):
        """更新滑动变阻器的当前电阻值"""
        try:
            if self.name == "滑动变阻器":
                max_resistance = float(self.properties.get("最大电阻值", 20.0))
                position = float(self.properties.get("滑动位置", 0.5))
                # 确保位置在0-1之间
                position = max(0.0, min(1.0, position))
                self.properties["当前电阻值"] = max_resistance * position
        except (ValueError, TypeError) as e:
            print(f"更新电阻值时出错: {e}")
            # 设置默认值
            self.properties["当前电阻值"] = 10.0
            
    def to_dict(self):
        return {
            "name": self.name,
            "pos": {"x": self.pos().x(), "y": self.pos().y()},
            "properties": self.properties
        }
        
    @classmethod
    def from_dict(cls, data):
        component = cls(data["name"])
        component.setPos(data["pos"]["x"], data["pos"]["y"])
        component.properties = data["properties"]
        return component
        
    def boundingRect(self):
        # 增大边界矩形以适应更大的组件
        return QRectF(-25, -25, 50, 50)
    
    def paint(self, painter, option, widget):
        try:
            # 设置基本画笔和画刷
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            # 绘制选中状态
            if self.isSelected():
                painter.setPen(QPen(QColor(0, 120, 215), 2, Qt.PenStyle.DashLine))
                painter.drawRect(self.boundingRect())
            
            # 绘制连接点
            painter.setPen(QPen(Qt.GlobalColor.black, 2))
            painter.setBrush(QBrush(Qt.GlobalColor.yellow))
            # 左连接点 - 修改为与setup_connection_points方法中相同的计算方式
            left_x = -self.boundingRect().width() / 2 - 3
            painter.drawEllipse(left_x, -3, 6, 6)
            # 右连接点 - 修改为与setup_connection_points方法中相同的计算方式
            right_x = self.boundingRect().width() / 2 + 3
            painter.drawEllipse(right_x, -3, 6, 6)
            
            # 设置默认画笔和画刷
            painter.setPen(QPen(Qt.GlobalColor.black, 2))
            painter.setBrush(QBrush(Qt.GlobalColor.white))
            
            if self.name == "开关":
                self._paint_switch(painter)
            elif self.name == "导线":
                self._paint_wire(painter)
            elif self.name == "定值电阻":
                self._paint_resistor(painter)
            elif self.name == "滑动变阻器":
                self._paint_potentiometer(painter)
            elif self.name == "电流表":
                self._paint_ammeter(painter)
            elif self.name == "电压表":
                self._paint_voltmeter(painter)
            elif self.name == "电源":
                self._paint_power_source(painter)
            
            # 显示属性值
            if self.name in ["定值电阻", "滑动变阻器", "电源"]:
                painter.setPen(QPen(Qt.GlobalColor.blue))
                if self.name == "定值电阻":
                    resistance = self.properties.get("电阻值", 100.0)
                    painter.drawText(-15, -25, f"{resistance:.1f}Ω")
                elif self.name == "电源":
                    voltage = self.properties.get("电压值", 12.0)
                    painter.drawText(-15, -25, f"{voltage:.1f}V")
                else:
                    self._update_current_resistance()
                    current_resistance = self.properties.get("当前电阻值", 10.0)
                    painter.drawText(-15, -25, f"{current_resistance:.1f}Ω")
                
            # 显示电流方向
            if self.current != 0:
                painter.setPen(QPen(Qt.GlobalColor.red, 2))
                direction = 1 if self.current > 0 else -1
                painter.drawLine(0, 0, 10 * direction, 0)
                painter.drawLine(10 * direction, -5, 10 * direction, 5)
            
        except Exception as e:
            print(f"绘制组件时出错: {e}")
            # 绘制错误提示
            painter.setPen(QPen(Qt.GlobalColor.red))
            painter.drawText(-20, 0, "错误")
            
    def _paint_switch(self, painter):
        # 获取连接点位置
        left_x = -15
        right_x = 15
        
        # 绘制开关底座
        painter.drawLine(left_x, 0, -5, 0)
        painter.drawLine(5, 0, right_x, 0)
        # 绘制开关触点
        if self.properties["状态"]:
            # 闭合状态
            painter.drawLine(-5, 0, 5, 0)
        else:
            # 断开状态
            painter.drawLine(-5, 0, 5, -10)
        # 绘制铰接点
        painter.setBrush(QBrush(Qt.GlobalColor.black))
        painter.drawEllipse(-7, -2, 4, 4)
        
    def _paint_wire(self, painter):
        # 获取连接点位置
        left_x = -15
        right_x = 15
        
        painter.drawLine(left_x, 0, right_x, 0)
        
    def _paint_resistor(self, painter):
        # 获取连接点位置
        left_x = -15
        right_x = 15
        
        # 绘制电阻符号
        painter.drawLine(left_x, 0, -10, 0)
        painter.drawLine(10, 0, right_x, 0)
        
        # 绘制锯齿形电阻
        path = QPainterPath()
        path.moveTo(-10, 0)
        path.lineTo(-8, -8)
        path.lineTo(-4, 8)
        path.lineTo(0, -8)
        path.lineTo(4, 8)
        path.lineTo(8, -8)
        path.lineTo(10, 0)
        painter.drawPath(path)
        
    def _paint_potentiometer(self, painter):
        try:
            # 获取连接点位置
            left_x = -15
            right_x = 15
            
            # 绘制电阻本体
            painter.drawLine(left_x, 0, -10, 0)
            painter.drawLine(10, 0, right_x, 0)
            
            # 绘制矩形电阻体
            painter.drawRect(-10, -8, 20, 16)
            
            # 绘制滑动触点
            pos = float(self.properties.get("滑动位置", 0.5))
            pos = max(0.0, min(1.0, pos))  # 确保位置在0-1之间
            x = -10 + 20 * pos
            
            painter.setBrush(QBrush(Qt.GlobalColor.black))
            painter.drawRect(int(x)-2, -12, 4, 4)  # 滑块
            painter.drawLine(int(x), -8, int(x), 8)     # 触点
            
        except Exception as e:
            print(f"绘制滑动变阻器时出错: {e}")
            # 绘制错误提示
            painter.setPen(QPen(Qt.GlobalColor.red))
            painter.drawText(-20, 0, "错误")
            
    def _paint_power_source(self, painter):
        # 绘制电源符号
        painter.setPen(QPen(Qt.GlobalColor.black, 2))
        painter.setBrush(QBrush(Qt.GlobalColor.white))
        
        # 绘制外框
        painter.drawRect(-20, -15, 40, 30)
        
        # 绘制正负极符号
        painter.setPen(QPen(Qt.GlobalColor.black, 2))
        # 正极
        painter.drawLine(5, -5, 15, -5)
        painter.drawLine(10, -10, 10, 0)
        # 负极
        painter.drawLine(-15, -5, -5, -5)
        
        # 显示电压值
        voltage = self.properties.get("电压值", 12.0)
        font = QFont()
        font.setPointSize(9)
        painter.setFont(font)
        painter.drawText(-15, 12, f"{voltage:.1f}V")
        
    def _paint_ammeter(self, painter):
        # 绘制圆形表盘
        painter.setPen(QPen(Qt.GlobalColor.black, 2))
        painter.setBrush(QBrush(Qt.GlobalColor.white))
        painter.drawEllipse(-20, -20, 40, 40)
        
        # 绘制连接线 - 修改位置以匹配新的连接点
        left_x = -self.boundingRect().width() / 2 - 3
        right_x = self.boundingRect().width() / 2 + 3
        painter.drawLine(left_x, 0, -20, 0)  # 左侧连接线
        painter.drawLine(20, 0, right_x, 0)   # 右侧连接线
        
        # 绘制内部装饰
        painter.drawArc(-15, -15, 30, 30, 30 * 16, 120 * 16)
        
        # 绘制刻度线
        for i in range(7):
            angle = 30 + i * 20
            rad = angle * 3.14159 / 180
            x1 = 15 * math.cos(rad)
            y1 = 15 * math.sin(rad)
            x2 = 12 * math.cos(rad)
            y2 = 12 * math.sin(rad)
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))
        
        # 绘制 A 符号
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(-6, 5, "A")
        
        # 显示电流值（移到上方）
        font.setPointSize(9)
        painter.setFont(font)
        if abs(self.current) < 0.01:
            current_str = f"{self.current*1000:.1f}mA"
        else:
            current_str = f"{self.current:.2f}A"
        # 创建一个白色背景的矩形
        text_rect = painter.boundingRect(-30, -45, 60, 20, Qt.AlignmentFlag.AlignCenter, current_str)
        painter.fillRect(text_rect, QBrush(Qt.GlobalColor.white))
        painter.drawText(-30, -45, 60, 20, Qt.AlignmentFlag.AlignCenter, current_str)
        
    def _paint_voltmeter(self, painter):
        # 绘制圆形表盘
        painter.setPen(QPen(Qt.GlobalColor.black, 2))
        painter.setBrush(QBrush(Qt.GlobalColor.white))
        painter.drawEllipse(-20, -20, 40, 40)
        
        # 绘制连接线 - 修改位置以匹配新的连接点
        left_x = -self.boundingRect().width() / 2 - 3
        right_x = self.boundingRect().width() / 2 + 3
        painter.drawLine(left_x, 0, -20, 0)  # 左侧连接线
        painter.drawLine(20, 0, right_x, 0)   # 右侧连接线
        
        # 绘制内部装饰
        painter.drawArc(-15, -15, 30, 30, 30 * 16, 120 * 16)
        
        # 绘制刻度线
        for i in range(7):
            angle = 30 + i * 20
            rad = angle * 3.14159 / 180
            x1 = 15 * math.cos(rad)
            y1 = 15 * math.sin(rad)
            x2 = 12 * math.cos(rad)
            y2 = 12 * math.sin(rad)
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))
        
        # 绘制 V 符号
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(-6, 5, "V")
        
        # 显示电压值（移到上方）
        font.setPointSize(9)
        painter.setFont(font)
        if abs(self.voltage) < 0.1:
            voltage_str = f"{self.voltage*1000:.1f}mV"
        else:
            voltage_str = f"{self.voltage:.2f}V"
        # 创建一个白色背景的矩形
        text_rect = painter.boundingRect(-30, -45, 60, 20, Qt.AlignmentFlag.AlignCenter, voltage_str)
        painter.fillRect(text_rect, QBrush(Qt.GlobalColor.white))
        painter.drawText(-30, -45, 60, 20, Qt.AlignmentFlag.AlignCenter, voltage_str)
        
    def get_connection_points(self):
        # 返回左右两个连接点的坐标
        left_x = -self.boundingRect().width() / 2 - 3
        right_x = self.boundingRect().width() / 2 + 3
        return [QPointF(left_x, 0), QPointF(right_x, 0)]
        
    def get_resistance(self):
        if self.name == "定值电阻":
            return self.properties["电阻值"]
        elif self.name == "滑动变阻器":
            return self.properties["当前电阻值"]
        elif self.name == "导线":
            return 0.001  # 接近0欧姆
        elif self.name == "开关":
            if self.properties["状态"]:
                return 0.001  # 开关闭合时接近0欧姆
            else:
                return float('inf')  # 开关断开时无穷大
        elif self.name == "电流表":
            return 0.001  # 理想电流表接近0欧姆
        elif self.name == "电压表":
            return 1000000.0  # 理想电压表有很大的电阻（接近无穷大）
        elif self.name == "电源":
            return 0.001  # 理想电源内阻接近0欧姆
        return float('inf')  # 其他元件默认视为开路
        
    def set_property(self, name, value):
        try:
            if name in self.properties:
                # 检查值是否实际改变
                old_value = self.properties[name]
                
                # 对滑动变阻器的特殊处理
                if self.name == "滑动变阻器":
                    if name == "滑动位置":
                        # 确保位置在0-1之间
                        value = float(value)
                        value = max(0.0, min(1.0, value))
                    elif name == "最大电阻值":
                        # 确保最大电阻值为正数
                        value = float(value)
                        value = max(0.1, value)
                        
                # 更新属性值
                self.properties[name] = value
                
                # 更新当前电阻值
                if self.name == "滑动变阻器":
                    self._update_current_resistance()
                    
                # 更新显示
                self.update()
                
                # 如果属性值实际发生变化，触发电路重新计算
                if old_value != value and self.scene():
                    # 查找WorkArea视图，触发电路重新计算
                    for view in self.scene().views():
                        if hasattr(view, 'update_simulation'):
                            # 确保仿真已开始
                            if hasattr(view, 'simulation_running') and view.simulation_running:
                                view.update_simulation()
                                break
                
        except (ValueError, TypeError) as e:
            print(f"设置属性时出错: {e}")
            # 保持原值不变

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.name == "开关":
                # 切换开关状态
                old_state = self.properties["状态"]
                self.properties["状态"] = not old_state
                logger.debug(f"开关状态改变: {self.properties['状态']}")
                self.update()  # 重绘开关
                
                # 如果状态改变且电路仿真正在进行，触发电路重新计算
                if self.scene():
                    # 查找WorkArea视图，触发电路重新计算
                    for view in self.scene().views():
                        if hasattr(view, 'update_simulation'):
                            # 确保仿真已开始
                            if hasattr(view, 'simulation_running') and view.simulation_running:
                                view.update_simulation()
                                break
                
                event.accept()
                return
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu()
        
        # 添加编辑名称选项
        rename_action = menu.addAction("编辑名称")
        
        # 添加编辑属性选项
        edit_properties_action = menu.addAction("编辑属性")
        
        # 添加删除选项
        delete_action = menu.addAction("删除")
        
        # 显示菜单并获取选择的动作
        action = menu.exec(event.screenPos())
        
        if action == rename_action:
            self.rename_component()
        elif action == edit_properties_action:
            self.edit_properties()
        elif action == delete_action:
            self.delete_component()

    def rename_component(self):
        new_name, ok = QInputDialog.getText(None, "编辑名称", 
                                          "输入新名称:", 
                                          text=self.name)
        if ok and new_name:
            self.name = new_name
            self.update()

    def edit_properties(self):
        dialog = QDialog()
        dialog.setWindowTitle(f"{self.name}属性设置")
        layout = QFormLayout()
        
        # 创建属性编辑控件
        property_widgets = {}
        for prop_name, prop_value in self.properties.items():
            if prop_name != "可调范围":  # 不显示范围提示
                if isinstance(prop_value, bool):
                    widget = QCheckBox()
                    widget.setChecked(prop_value)
                elif isinstance(prop_value, (int, float)):
                    widget = QDoubleSpinBox()
                    if self.name == "电源":
                        widget.setRange(0, 24)  # 电源的电压范围
                    else:
                        widget.setRange(0.1, 1000)  # 其他组件的范围
                    widget.setValue(prop_value)
                    if "电阻" in prop_name:
                        widget.setSuffix(" Ω")
                    elif "电压" in prop_name:
                        widget.setSuffix(" V")
                    property_widgets[prop_name] = widget
                    layout.addRow(f"{prop_name}:", widget)
        
        # 添加确定和取消按钮
        button_box = QHBoxLayout()
        ok_button = QPushButton("确定")
        cancel_button = QPushButton("取消")
        button_box.addWidget(ok_button)
        button_box.addWidget(cancel_button)
        
        ok_button.clicked.connect(dialog.accept)
        cancel_button.clicked.connect(dialog.reject)
        
        layout.addRow(button_box)
        dialog.setLayout(layout)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # 更新属性值
            for prop_name, widget in property_widgets.items():
                if isinstance(widget, QCheckBox):
                    self.set_property(prop_name, widget.isChecked())
                else:
                    value = widget.value()
                    self.set_property(prop_name, value)
                    # 如果是电源，同步更新主界面的电压输入框
                    if self.name == "电源" and prop_name == "电压值":
                        # 发送自定义事件通知主窗口更新电压值
                        if self.scene():
                            view = self.scene().views()[0]
                            if hasattr(view, 'voltage_changed_signal'):
                                view.voltage_changed_signal.emit(value)
            self.update()  # 更新显示

    def delete_component(self):
        reply = QMessageBox.question(None, "确认删除", 
                                   f"确定要删除 {self.name} 吗？",
                                   QMessageBox.StandardButton.Yes | 
                                   QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            # 删除所有连接的导线
            for point in self.connection_points:
                for wire in point.connected_wires[:]:  # 使用副本进行迭代
                    wire.delete_wire()  # 使用wire的删除方法
            
            # 从场景中移除组件
            if self.scene():
                self.scene().removeItem(self)

class Circuit:
    def __init__(self):
        self.components = []
        self.connections = []
        self.nodes = {}  # 存储节点信息
        self.voltage_sources = []  # 存储电压源
        
    def add_component(self, component):
        self.components.append(component)
        
    def add_connection(self, from_comp, to_comp):
        self.connections.append((from_comp, to_comp))
        
    def calculate_circuit(self, voltage=12):
        """
        使用改进节点分析法(MNA)对电路进行分析
        """
        # 第1步：识别电路中的节点
        nodes = self.identify_nodes()
        if not nodes:
            logging.error("电路节点识别失败，可能是电路不完整")
            return False
        
        # 第2步：分配节点ID给组件
        self.assign_node_ids(nodes)
        
        # 第3步：构建MNA方程组 Ax = z
        A, z, var_index_map = self.build_mna_matrices()
        if A is None:
            logging.error("构建方程组失败")
            return False
        
        # 第4步：求解方程组
        try:
            x = np.linalg.solve(A, z)
            # 更新组件的电压和电流
            self.update_component_values(x, var_index_map)
            return True
        except np.linalg.LinAlgError as e:
            logging.error(f"电路方程组求解失败: {e}")
            return False
        
    def identify_nodes(self):
        """
        使用BFS算法识别电路中的节点
        节点定义为一组相互连接的连接点
        返回: 字典 {节点ID: 连接点列表}
        """
        # 获取所有连接点
        all_connection_points = []
        for component in self.components:
            all_connection_points.extend(component.connection_points)
        
        # 使用BFS查找连接的节点
        nodes = {}  # {node_id: [connection_points]}
        node_id = 0
        visited = set()
        
        for start_point in all_connection_points:
            if start_point in visited:
                continue
            
            # 开始BFS
            node_points = []
            queue = [start_point]
            while queue:
                current_point = queue.pop(0)
                if current_point in visited:
                    continue
                
                visited.add(current_point)
                node_points.append(current_point)
                
                # 查找所有连接的导线
                for wire in current_point.connected_wires:
                    # 获取导线另一端的连接点
                    next_point = None
                    if wire.source_point == current_point and wire.target_point:
                        next_point = wire.target_point
                    elif wire.target_point == current_point and wire.source_point:
                        next_point = wire.source_point
                    
                    if next_point and next_point not in visited:
                        queue.append(next_point)
        
            # 创建新节点
            if node_points:
                nodes[node_id] = node_points
                node_id += 1
        
        # 默认第0个节点为参考节点(地)
        logging.debug(f"识别到 {len(nodes)} 个节点")
        return nodes

    def assign_node_ids(self, nodes):
        """为每个组件分配节点ID"""
        # 清除先前的节点分配
        for component in self.components:
            component.node1 = None
            component.node2 = None
        
        # 创建连接点到节点ID的映射
        point_to_node = {}
        for node_id, points in nodes.items():
            for point in points:
                point_to_node[point] = node_id
        
        # 为每个组件分配节点
        for component in self.components:
            if len(component.connection_points) >= 2:
                component.node1 = point_to_node.get(component.connection_points[0])
                component.node2 = point_to_node.get(component.connection_points[1])
                logging.debug(f"组件 {component.name} 分配节点: {component.node1}, {component.node2}")
        
        return True

    def build_mna_matrices(self):
        """
        构建改进节点分析(MNA)的矩阵
        返回: A矩阵, z向量, 变量索引映射
        """
        # 计算节点数和电压源数量
        nodes = set()
        voltage_sources = []
        
        for component in self.components:
            if component.node1 is not None:
                nodes.add(component.node1)
            if component.node2 is not None:
                nodes.add(component.node2)
            
            # 识别电压源
            if component.name == "电源":
                voltage_sources.append(component)
        
        num_nodes = len(nodes)
        num_voltage_sources = len(voltage_sources)
        
        # MNA矩阵大小: [节点数-1 + 电压源数]
        # 节点0作为参考节点(地)，不包含在方程中
        n = num_nodes - 1 + num_voltage_sources
        if n <= 0:
            return None, None, None
        
        # 创建MNA矩阵
        A = np.zeros((n, n), dtype=float)
        z = np.zeros(n, dtype=float)
        
        # 创建变量索引映射
        var_index_map = {
            'node_voltages': {}, # 节点电压索引
            'branch_currents': {} # 支路电流索引
        }
        
        # 为非参考节点分配索引
        node_index = 0
        for node in sorted(nodes):
            if node != 0:  # 跳过参考节点
                var_index_map['node_voltages'][node] = node_index
                node_index += 1
        
        # 为电压源分配索引
        for i, vsource in enumerate(voltage_sources):
            var_index_map['branch_currents'][id(vsource)] = num_nodes - 1 + i
        
        # 填充导纳矩阵(G子矩阵)
        for component in self.components:
            if component.node1 is None or component.node2 is None:
                continue
            
            # 跳过电压源
            if component.name == "电源":
                continue
            
            # 获取组件的电阻
            r = component.get_resistance()
            if r <= 0 or r == float('inf'):
                continue
            
            g = 1.0 / r  # 导纳 = 1/电阻
            
            # 获取组件连接的节点索引
            node1 = component.node1
            node2 = component.node2
            
            # 如果节点是参考节点(0)，则忽略
            if node1 != 0 and node2 != 0:
                idx1 = var_index_map['node_voltages'][node1]
                idx2 = var_index_map['node_voltages'][node2]
                
                # 填充导纳矩阵
                A[idx1, idx1] += g
                A[idx2, idx2] += g
                A[idx1, idx2] -= g
                A[idx2, idx1] -= g
            elif node1 != 0:
                idx1 = var_index_map['node_voltages'][node1]
                A[idx1, idx1] += g
            elif node2 != 0:
                idx2 = var_index_map['node_voltages'][node2]
                A[idx2, idx2] += g
        
        # 处理电压源
        for i, vsource in enumerate(voltage_sources):
            # 电压源电流变量索引
            idx_i = var_index_map['branch_currents'][id(vsource)]
            
            # 电压源节点
            node1 = vsource.node1
            node2 = vsource.node2
            
            # 电压源方程: v1 - v2 = V
            if node1 != 0:
                idx1 = var_index_map['node_voltages'][node1]
                A[idx_i, idx1] = 1
                A[idx1, idx_i] = 1
            
            if node2 != 0:
                idx2 = var_index_map['node_voltages'][node2]
                A[idx_i, idx2] = -1
                A[idx2, idx_i] = -1
            
            # 电压值
            z[idx_i] = vsource.properties.get("电压值", 12.0)
        
        return A, z, var_index_map

    def update_component_values(self, x, var_index_map):
        """根据求解结果更新组件的电压和电流值"""
        # 更新节点电压
        node_voltages = {}
        node_voltages[0] = 0.0  # 参考节点电压为0
        
        for node, idx in var_index_map['node_voltages'].items():
            node_voltages[node] = x[idx]
        
        # 更新组件电压和电流
        for component in self.components:
            if component.node1 is None or component.node2 is None:
                continue
            
            # 计算端点电压
            v1 = node_voltages.get(component.node1, 0.0)
            v2 = node_voltages.get(component.node2, 0.0)
            
            # 组件电压
            component.voltage = abs(v1 - v2)
            
            # 计算电流
            if component.name == "电源":
                # 电源电流从支路电流变量获取
                if id(component) in var_index_map['branch_currents']:
                    idx = var_index_map['branch_currents'][id(component)]
                    component.current = x[idx]
            else:
                # 其他元件的电流通过电压和电阻计算
                r = component.get_resistance()
                if r != float('inf') and r > 0:
                    component.current = component.voltage / r
                    # 确定电流方向
                    if v1 > v2:
                        component.current *= -1  # 从高电位流向低电位

    def to_dict(self, scene=None):
        # 组件字典
        components_dict = []
        for comp in self.components:
            comp_dict = comp.to_dict()
            components_dict.append(comp_dict)
        
        # 导线字典
        wires_dict = []
        if scene:  # 如果提供了场景参数
            for scene_item in scene.items():
                if isinstance(scene_item, Wire):
                    wire = scene_item
                    wire_dict = {
                        "path_points": [{"x": p.x(), "y": p.y()} for p in wire.path_points],
                        "source": None,
                        "target": None
                    }
                    
                    # 保存源连接点信息
                    if wire.source_point and wire.source_component:
                        source_comp_idx = self.components.index(wire.source_component) if wire.source_component in self.components else -1
                        if source_comp_idx >= 0:
                            source_point_idx = wire.source_component.connection_points.index(wire.source_point) if wire.source_point in wire.source_component.connection_points else -1
                            if source_point_idx >= 0:
                                wire_dict["source"] = {
                                    "component_index": source_comp_idx,
                                    "point_index": source_point_idx
                                }
                    
                    # 保存目标连接点信息
                    if wire.target_point and wire.target_component:
                        target_comp_idx = self.components.index(wire.target_component) if wire.target_component in self.components else -1
                        if target_comp_idx >= 0:
                            target_point_idx = wire.target_component.connection_points.index(wire.target_point) if wire.target_point in wire.target_component.connection_points else -1
                            if target_point_idx >= 0:
                                wire_dict["target"] = {
                                    "component_index": target_comp_idx,
                                    "point_index": target_point_idx
                                }
                    
                    wires_dict.append(wire_dict)
        
        return {
            "components": components_dict,
            "wires": wires_dict
        }
        
    @classmethod
    def from_dict(cls, data, scene=None):
        circuit = cls()
        
        # 首先创建所有组件
        components = []
        for comp_data in data["components"]:
            component = Component(comp_data["name"])
            # 如果有位置信息，设置位置
            if "pos" in comp_data:
                component.setPos(comp_data["pos"]["x"], comp_data["pos"]["y"])
            # 如果有属性信息，设置属性
            if "properties" in comp_data:
                component.properties = comp_data["properties"]
            components.append(component)
            if scene:  # 如果提供了场景，则将组件添加到场景
                scene.addItem(component)
        
        circuit.components = components
        
        # 如果存在导线信息，创建导线
        if "wires" in data and scene:
            for wire_data in data["wires"]:
                # 创建新导线
                if "path_points" in wire_data and wire_data["path_points"]:
                    start_point = QPointF(wire_data["path_points"][0]["x"], wire_data["path_points"][0]["y"])
                    wire = Wire(start_point)
                    scene.addItem(wire)
                    
                    # 恢复路径点
                    wire.path_points = [QPointF(p["x"], p["y"]) for p in wire_data["path_points"]]
                    wire.start_pos = wire.path_points[0]
                    wire.end_pos = wire.path_points[-1]
                    wire.update_path_from_points()
                    
                    # 恢复连接
                    if "source" in wire_data and wire_data["source"]:
                        source_comp_idx = wire_data["source"]["component_index"]
                        source_point_idx = wire_data["source"]["point_index"]
                        if 0 <= source_comp_idx < len(components) and 0 <= source_point_idx < len(components[source_comp_idx].connection_points):
                            source_comp = components[source_comp_idx]
                            source_point = source_comp.connection_points[source_point_idx]
                            wire.connect_endpoint(source_point, True)
                    
                    if "target" in wire_data and wire_data["target"]:
                        target_comp_idx = wire_data["target"]["component_index"]
                        target_point_idx = wire_data["target"]["point_index"]
                        if 0 <= target_comp_idx < len(components) and 0 <= target_point_idx < len(components[target_comp_idx].connection_points):
                            target_comp = components[target_comp_idx]
                            target_point = target_comp.connection_points[target_point_idx]
                            wire.connect_endpoint(target_point, False)
                    
                    # 在连接完端点后，强制更新导线路径以匹配连接点位置
                    wire.update_endpoints_from_connection_points()
        
        return circuit 

def save_circuit_to_json(self):
    try:
        options = QFileDialog.Option(0)
        file_name, _ = QFileDialog.getSaveFileName(
            self, "保存电路", "", "JSON Files (*.json)", options=options
        )
        if file_name:
            if not file_name.endswith('.json'):
                file_name += '.json'
            
            # 使用 work_area 的 circuit 对象来获取电路数据
            circuit_data = self.work_area.circuit.to_dict()
            
            with open(file_name, 'w') as f:
                json.dump(circuit_data, f, indent=4)
            
            self.statusBar().showMessage(f"电路已保存到 {file_name}", 5000)
            
    except Exception as e:
        QMessageBox.critical(self, "保存失败", f"保存电路失败: {str(e)}") 