import sys
import os
import json
import math
import logging
from datetime import datetime
from PyQt6.QtWidgets import (QGraphicsItem, QGraphicsEllipseItem, QGraphicsRectItem, 
                            QGraphicsLineItem, QGraphicsPathItem, QGraphicsSimpleTextItem)
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
        self.snap_distance = 10.0  # 自动吸附距离
        self.dragging = False
        self.drag_point = None  # 记录正在拖动的端点
        logger.debug(f"创建新导线: start_pos={start_pos}")
        
    def mousePressEvent(self, event):
        try:
            if event.button() == Qt.MouseButton.LeftButton:
                pos = event.pos()
                # 检查是否点击了起点或终点
                start_dist = (pos - self.start_pos).manhattanLength()
                end_dist = (pos - self.end_pos).manhattanLength()
                
                logger.debug(f"导线鼠标按下: pos={pos}, start_dist={start_dist}, end_dist={end_dist}")
                
                if start_dist < 10:  # 点击了起点
                    self.dragging = True
                    self.drag_point = 'start'
                    logger.debug("开始拖动导线起点")
                elif end_dist < 10:  # 点击了终点
                    self.dragging = True
                    self.drag_point = 'end'
                    logger.debug("开始拖动导线终点")
                event.accept()
            else:
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
            
    def _paint_ammeter(self, painter):
        # 绘制圆形表盘
        painter.drawEllipse(-20, -20, 40, 40)
        
        # 绘制正负极标识
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        painter.setFont(font)
        
        # 正极标识（红色）
        painter.setPen(QPen(Qt.GlobalColor.red, 2))
        painter.drawText(-8, -25, "+")
        
        # 负极标识（黑色）
        painter.setPen(QPen(Qt.GlobalColor.black, 2))
        painter.drawText(-6, 35, "−")
        
        # 绘制 A 符号和数值
        painter.setPen(QPen(Qt.GlobalColor.black, 2))
        font.setPointSize(14)
        painter.setFont(font)
        painter.drawText(-8, 7, "A")
        
        # 显示电流值
        font.setPointSize(10)
        painter.setFont(font)
        if abs(self.current) < 0.01:
            current_str = f"{self.current*1000:.1f}mA"
        else:
            current_str = f"{self.current:.2f}A"
        painter.drawText(-20, -8, current_str)
        
    def _paint_voltmeter(self, painter):
        # 绘制圆形表盘
        painter.drawEllipse(-20, -20, 40, 40)
        
        # 绘制正负极标识
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        painter.setFont(font)
        
        # 正极标识（红色）
        painter.setPen(QPen(Qt.GlobalColor.red, 2))
        painter.drawText(-8, -25, "+")
        
        # 负极标识（黑色）
        painter.setPen(QPen(Qt.GlobalColor.black, 2))
        painter.drawText(-6, 35, "−")
        
        # 绘制 V 符号和数值
        painter.setPen(QPen(Qt.GlobalColor.black, 2))
        font.setPointSize(14)
        painter.setFont(font)
        painter.drawText(-8, 7, "V")
        
        # 显示电压值
        font.setPointSize(10)
        painter.setFont(font)
        if abs(self.voltage) < 0.1:
            voltage_str = f"{self.voltage*1000:.1f}mV"
        else:
            voltage_str = f"{self.voltage:.2f}V"
        painter.drawText(-20, -8, voltage_str)
        
    def _paint_power_source(self, painter):
        # 绘制电源符号
        # 外圆
        painter.drawEllipse(-20, -20, 40, 40)
        # 正负极符号
        painter.setPen(QPen(Qt.GlobalColor.black, 3))
        # 正极
        painter.drawLine(10, 0, 20, 0)
        painter.drawLine(15, -5, 15, 5)
        # 负极
        painter.drawLine(-20, 0, -10, 0)
        
        # 显示电压值
        voltage = self.properties.get("电压值", 12.0)
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(-12, 5, f"{voltage}V")
        
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