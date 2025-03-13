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
                            QCheckBox, QHBoxLayout)
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
        self.start_pos = start_pos
        self.end_pos = start_pos
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setPen(QPen(Qt.GlobalColor.black, 2))
        self.update_path()
        self.source_component = None
        self.target_component = None
        self.source_point = None
        self.target_point = None
        self.snap_distance = 10.0
        self.dragging = False
        self.drag_point = None
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton)
        logger.debug(f"创建新导线: start_pos={start_pos}")
        
    def mousePressEvent(self, event):
        try:
            if event.button() == Qt.MouseButton.LeftButton:
                pos = event.pos()
                start_dist = (pos - self.start_pos).manhattanLength()
                end_dist = (pos - self.end_pos).manhattanLength()
                
                if start_dist < 10 or end_dist < 10:  # 点击了端点
                    self.dragging = True
                    self.drag_point = 'start' if start_dist < end_dist else 'end'
                    # 断开相应端点的连接
                    self.disconnect_endpoint(self.drag_point == 'start')
                    event.accept()
                    return
            elif event.button() == Qt.MouseButton.RightButton:
                self.show_context_menu(event)
            super().mousePressEvent(event)
        except Exception as e:
            logger.error(f"导线鼠标按下事件出错: {str(e)}", exc_info=True)
            
    def mouseMoveEvent(self, event):
        try:
            if self.dragging and self.drag_point:
                scene_pos = event.scenePos()
                old_pos = self.start_pos if self.drag_point == 'start' else self.end_pos
                
                logger.debug(f"导线拖动: drag_point={self.drag_point}, old_pos={old_pos}, new_pos={scene_pos}")
                
                if self.drag_point == 'start':
                    self.start_pos = scene_pos
                else:
                    self.end_pos = scene_pos
                self.update_path()
                event.accept()
            else:
                super().mouseMoveEvent(event)
        except Exception as e:
            logger.error(f"导线移动事件出错: {str(e)}", exc_info=True)
            
    def mouseReleaseEvent(self, event):
        try:
            if event.button() == Qt.MouseButton.LeftButton and self.dragging:
                logger.debug(f"导线释放: drag_point={self.drag_point}, pos={event.scenePos()}")
                self.dragging = False
                self.drag_point = None
                event.accept()
            else:
                super().mouseReleaseEvent(event)
        except Exception as e:
            logger.error(f"导线释放事件出错: {str(e)}", exc_info=True)
            
    def update_path(self):
        try:
            path = QPainterPath()
            path.moveTo(self.start_pos)
            
            # 计算中间点，实现直角转弯
            dx = self.end_pos.x() - self.start_pos.x()
            dy = self.end_pos.y() - self.start_pos.y()
            
            # 根据起点和终点的相对位置决定路径
            if abs(dx) > abs(dy):
                # 水平方向为主
                mid_x = self.start_pos.x() + dx / 2
                path.lineTo(mid_x, self.start_pos.y())
                path.lineTo(mid_x, self.end_pos.y())
            else:
                # 垂直方向为主
                mid_y = self.start_pos.y() + dy / 2
                path.lineTo(self.start_pos.x(), mid_y)
                path.lineTo(self.end_pos.x(), mid_y)
            
            path.lineTo(self.end_pos)
            
            self.setPath(path)
            logger.debug(f"更新导线路径: start={self.start_pos}, end={self.end_pos}")
        except Exception as e:
            logger.error(f"更新导线路径时出错: {str(e)}", exc_info=True)
        
    def set_end_pos(self, pos):
        self.end_pos = pos
        self.update_path()

    def show_context_menu(self, event):
        menu = QMenu()
        delete_action = menu.addAction("删除导线")
        action = menu.exec(event.screenPos())
        
        if action == delete_action:
            self.delete_wire()

    def delete_wire(self):
        # 断开两端连接
        self.disconnect_endpoint(True)  # 断开起点
        self.disconnect_endpoint(False)  # 断开终点
        
        # 从场景中移除
        if self.scene():
            self.scene().removeItem(self)

    def disconnect_endpoint(self, is_start):
        """断开指定端点的连接"""
        if is_start and self.source_point:
            if self in self.source_point.connected_wires:
                self.source_point.connected_wires.remove(self)
            self.source_point = None
            self.source_component = None
        elif not is_start and self.target_point:
            if self in self.target_point.connected_wires:
                self.target_point.connected_wires.remove(self)
            self.target_point = None
            self.target_component = None

    def connect_endpoint(self, connection_point, is_start):
        """连接到新的连接点"""
        if is_start:
            if self.source_point:  # 如果已经有连接，先断开
                self.disconnect_endpoint(True)
            self.source_point = connection_point
            self.source_component = connection_point.parentItem()
            connection_point.connected_wires.append(self)
        else:
            if self.target_point:  # 如果已经有连接，先断开
                self.disconnect_endpoint(False)
            self.target_point = connection_point
            self.target_component = connection_point.parentItem()
            connection_point.connected_wires.append(self)

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
            input_point.setPos(-25, 0)
            self.connection_points.append(input_point)
            
            # 右侧输出点
            output_point = ConnectionPoint(self, "output")
            output_point.setPos(25, 0)
            self.connection_points.append(output_point)
        elif self.name == "电源":
            # 正极（右侧）
            pos_point = ConnectionPoint(self, "output")
            pos_point.setPos(25, 0)
            pos_point.setBrush(QBrush(Qt.GlobalColor.red))
            self.connection_points.append(pos_point)
            
            # 负极（左侧）
            neg_point = ConnectionPoint(self, "input")
            neg_point.setPos(-25, 0)
            neg_point.setBrush(QBrush(Qt.GlobalColor.black))
            self.connection_points.append(neg_point)
            
        elif self.name in ["电流表", "电压表"]:
            # 上方输入点（正极）
            input_point = ConnectionPoint(self, "input")
            input_point.setPos(0, -20)
            input_point.setBrush(QBrush(Qt.GlobalColor.red))
            self.connection_points.append(input_point)
            
            # 下方输出点（负极）
            output_point = ConnectionPoint(self, "output")
            output_point.setPos(0, 20)
            output_point.setBrush(QBrush(Qt.GlobalColor.black))
            self.connection_points.append(output_point)
            
            # 添加正负极标识
            font = QFont()
            font.setPointSize(8)
            font.setBold(True)
            
            pos_label = QGraphicsSimpleTextItem("+", self)
            pos_label.setFont(font)
            pos_label.setPos(-8, -25)
            
            neg_label = QGraphicsSimpleTextItem("-", self)
            neg_label.setFont(font)
            neg_label.setPos(-6, 15)
        
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
                if point.point_type == "input":
                    wire.end_pos = point.scenePos()
                else:
                    wire.start_pos = point.scenePos()
                wire.update_path()

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
            # 左连接点
            painter.drawEllipse(-25, -3, 6, 6)
            # 右连接点
            painter.drawEllipse(19, -3, 6, 6)
            
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
        # 绘制开关底座
        painter.drawLine(-15, 0, -5, 0)
        painter.drawLine(5, 0, 15, 0)
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
        painter.drawLine(-15, 0, 15, 0)
        
    def _paint_resistor(self, painter):
        # 绘制电阻符号
        painter.drawLine(-15, 0, -10, 0)
        painter.drawLine(10, 0, 15, 0)
        
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
            # 绘制电阻本体
            painter.drawLine(-15, 0, -10, 0)
            painter.drawLine(10, 0, 15, 0)
            
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
        return [QPointF(-22, 0), QPointF(22, 0)]
        
    def get_resistance(self):
        if self.name == "定值电阻":
            return self.properties["电阻值"]
        elif self.name == "滑动变阻器":
            return self.properties["当前电阻值"]
        elif self.name == "导线":
            return 0.001  # 接近0欧姆
        elif self.name == "开关" and self.properties["状态"]:
            return 0.001  # 开关闭合时接近0欧姆
        return float('inf')  # 其他元件（开关断开、电表等）视为开路
        
    def set_property(self, name, value):
        try:
            if name in self.properties:
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
                        
                self.properties[name] = value
                
                # 更新当前电阻值
                if self.name == "滑动变阻器":
                    self._update_current_resistance()
                    
                self.update()  # 更新显示
                
        except (ValueError, TypeError) as e:
            print(f"设置属性时出错: {e}")
            # 保持原值不变

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.name == "开关":
                # 切换开关状态
                self.properties["状态"] = not self.properties["状态"]
                logger.debug(f"开关状态改变: {self.properties['状态']}")
                self.update()  # 重绘开关
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
        
    def build_circuit_matrix(self):
        # 构建节点导纳矩阵
        n = len(self.nodes)  # 节点数
        Y = np.zeros((n, n), dtype=complex)
        I = np.zeros(n, dtype=complex)
        
        # 填充导纳矩阵
        for comp in self.components:
            if comp.name == "导线" or (comp.name == "开关" and comp.properties["状态"]):
                continue
                
            R = comp.get_resistance()
            if R == float('inf'):
                continue
                
            # 获取组件连接的节点
            node1 = comp.node1
            node2 = comp.node2
            
            if node1 is not None and node2 is not None:
                i = self.nodes[node1]
                j = self.nodes[node2]
                Y[i, i] += 1/R
                Y[j, j] += 1/R
                Y[i, j] -= 1/R
                Y[j, i] -= 1/R
                
        return Y, I
        
    def calculate_circuit(self, voltage=12):
        # 使用节点电压法分析电路
        # 1. 识别节点
        self.nodes = {}
        node_count = 0
        
        # 添加参考节点（地）
        self.nodes["GND"] = node_count
        node_count += 1
        
        # 为每个组件分配节点
        for comp in self.components:
            if comp.node1 is None:
                comp.node1 = f"node_{node_count}"
                self.nodes[comp.node1] = node_count
                node_count += 1
            if comp.node2 is None:
                comp.node2 = f"node_{node_count}"
                self.nodes[comp.node2] = node_count
                node_count += 1
                
        # 2. 构建电路矩阵
        Y, I = self.build_circuit_matrix()
        
        # 3. 添加电压源
        # 假设第一个组件是电压源
        if self.components and self.components[0].name == "导线":
            voltage_node = self.components[0].node1
            if voltage_node in self.nodes:
                i = self.nodes[voltage_node]
                I[i] = voltage
                
        # 4. 求解节点电压
        try:
            V = np.linalg.solve(Y, I)
        except np.linalg.LinAlgError:
            print("电路矩阵求解失败，可能是电路结构有问题")
            return
            
        # 5. 计算各组件电压和电流
        for comp in self.components:
            if comp.node1 in self.nodes and comp.node2 in self.nodes:
                i = self.nodes[comp.node1]
                j = self.nodes[comp.node2]
                comp.voltage = abs(V[i] - V[j])
                
                if comp.name in ["定值电阻", "滑动变阻器"]:
                    R = comp.get_resistance()
                    if R != float('inf'):
                        comp.current = comp.voltage / R
                elif comp.name in ["电流表", "电压表"]:
                    comp.current = 0
                    
    def to_dict(self):
        return {
            "components": [comp.to_dict() for comp in self.components],
            "connections": [
                {
                    "from": self.components.index(from_comp),
                    "to": self.components.index(to_comp)
                }
                for from_comp, to_comp in self.connections
            ]
        }
        
    @classmethod
    def from_dict(cls, data):
        circuit = cls()
        # 首先创建所有组件
        components = [Component.from_dict(comp_data) for comp_data in data["components"]]
        circuit.components = components
        
        # 然后创建连接
        for conn in data["connections"]:
            from_comp = components[conn["from"]]
            to_comp = components[conn["to"]]
            circuit.add_connection(from_comp, to_comp)
            
        return circuit 