import sys
import os
import json
import logging
import requests
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QHBoxLayout, QPushButton, QLabel, QGraphicsView,
                           QGraphicsScene, QMessageBox, QLineEdit, QSlider,
                           QDialog, QFormLayout, QDoubleSpinBox, QFileDialog,
                           QGroupBox, QComboBox, QCheckBox, QGridLayout, QMenu,
                           QTextEdit, QSplitter)
from PyQt6.QtCore import Qt, QMimeData, QPointF, QTimer, QLineF, pyqtSignal, QPoint, QSettings
from PyQt6.QtGui import QDrag, QPainter, QColor, QPen, QBrush, QTransform
from components import Component, Circuit, Wire, ConnectionPoint, logger

class PropertyDialog(QDialog):
    def __init__(self, component, parent=None):
        super().__init__(parent)
        self.component = component
        self.setWindowTitle(f"{component.name}属性设置")
        self.setModal(True)
        self.setMinimumWidth(300)
        
        layout = QFormLayout(self)
        layout.setSpacing(10)
        
        if component.name == "定值电阻":
            self.resistance_spin = QDoubleSpinBox()
            self.resistance_spin.setRange(0.1, 1000)
            self.resistance_spin.setValue(component.properties["电阻值"])
            self.resistance_spin.setSuffix(" Ω")
            layout.addRow("电阻值:", self.resistance_spin)
            
        elif component.name == "滑动变阻器":
            self.max_resistance_spin = QDoubleSpinBox()
            self.max_resistance_spin.setRange(0.1, 1000)
            self.max_resistance_spin.setValue(component.properties["最大电阻值"])
            self.max_resistance_spin.setSuffix(" Ω")
            layout.addRow("最大电阻值:", self.max_resistance_spin)
            
            self.position_slider = QSlider(Qt.Orientation.Horizontal)
            self.position_slider.setRange(0, 100)
            self.position_slider.setValue(int(component.properties["滑动位置"] * 100))
            layout.addRow("滑动位置:", self.position_slider)
            
        elif component.name == "开关":
            self.state_checkbox = QCheckBox("闭合状态")
            self.state_checkbox.setChecked(component.properties["状态"])
            layout.addRow("开关状态:", self.state_checkbox)
        
        buttons = QHBoxLayout()
        ok_button = QPushButton("确定")
        cancel_button = QPushButton("取消")
        ok_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        buttons.addWidget(ok_button)
        buttons.addWidget(cancel_button)
        layout.addRow(buttons)
        
    def accept(self):
        if self.component.name == "定值电阻":
            self.component.set_property("电阻值", self.resistance_spin.value())
        elif self.component.name == "滑动变阻器":
            self.component.set_property("最大电阻值", self.max_resistance_spin.value())
            self.component.set_property("滑动位置", self.position_slider.value() / 100)
        elif self.component.name == "开关":
            self.component.set_property("状态", self.state_checkbox.isChecked())
        super().accept()

class ComponentButton(QPushButton):
    def __init__(self, name, parent=None):
        super().__init__(name, parent)
        self.setAcceptDrops(True)
        self.component_name = name
        self.setMinimumSize(100, 35)
        self.setMaximumSize(105, 35)
        self.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 4px;
                font-size: 13px;
                margin: 2px;
                text-align: center;
                qproperty-alignment: AlignCenter;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:pressed {
                background-color: #0D47A1;
            }
        """)
        
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            try:
                drag = QDrag(self)
                mime = QMimeData()
                mime.setText(self.component_name)
                
                # 设置拖拽时的预览图像
                pixmap = self.grab()  # 直接使用按钮本身的图像作为预览
                pixmap = pixmap.scaled(100, 40)  # 缩放到合适的大小
                
                # 设置拖拽时的图像
                drag.setPixmap(pixmap)
                drag.setHotSpot(QPoint(pixmap.width() // 2, pixmap.height() // 2))  # 设置热点为图像中心
                
                # 设置拖拽数据
                drag.setMimeData(mime)
                
                # 执行拖拽操作
                result = drag.exec(Qt.DropAction.CopyAction)
                
                # 拖拽结束后恢复默认光标
                self.setCursor(Qt.CursorShape.ArrowCursor)
                
            except Exception as e:
                logger.error(f"拖拽组件时出错: {str(e)}", exc_info=True)

class WorkArea(QGraphicsView):
    # 将信号定义为类变量
    voltage_changed_signal = pyqtSignal(float)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setBackgroundBrush(QBrush(QColor(245, 245, 245)))
        self.voltage = 5.0
        self.current_wire = None
        self.components = []
        self.wires = []
        self.current_component = None
        self.setMinimumSize(500, 400)
        
        # 添加电网背景
        self.grid_size = 20
        self.show_grid = True
        self.snap_to_grid = True
        
        # 添加场景变化信号
        self.scene().changed.connect(self.on_scene_changed)
        
        # 用于视图拖动的变量
        self.is_panning = False
        self.last_pan_point = QPoint()
        self.shift_key_pressed = False  # 使用Shift替代空格键
        
        # 初始化电路
        self.circuit = Circuit()
        self.simulation_running = False
        self.simulation_timer = None
        self.simulation_step = 0
        self.max_simulation_steps = 1000
        
        logger.debug("WorkArea初始化完成")
        
    def draw_grid(self):
        """绘制网格背景（此方法不需要实际实现，因为我们在drawBackground中绘制网格）"""
        pass
        
    def on_scene_changed(self, region):
        """处理场景变化事件"""
        # 更新所有导线的端点位置
        for item in self.scene().items():
            if isinstance(item, Wire) and (item.source_point or item.target_point):
                item.update_endpoints_from_connection_points()
                
        # 更新视图
        self.update()
        
    def drawBackground(self, painter, rect):
        super().drawBackground(painter, rect)
        if self.show_grid:
            # 绘制主网格线
            painter.setPen(QPen(QColor(200, 200, 200)))
            left = int(rect.left()) - (int(rect.left()) % self.grid_size)
            top = int(rect.top()) - (int(rect.top()) % self.grid_size)
            
            lines = []
            x = left
            while x < rect.right():
                lines.append(QLineF(x, rect.top(), x, rect.bottom()))
                x += self.grid_size
                
            y = top
            while y < rect.bottom():
                lines.append(QLineF(rect.left(), y, rect.right(), y))
                y += self.grid_size
                
            painter.drawLines(lines)
            
            # 绘制次网格线（更细的线）
            if self.grid_size >= 20:
                painter.setPen(QPen(QColor(230, 230, 230)))
                x = left
                while x < rect.right():
                    lines.append(QLineF(x, rect.top(), x, rect.bottom()))
                    x += self.grid_size / 2
                    
                y = top
                while y < rect.bottom():
                    lines.append(QLineF(rect.left(), y, rect.right(), y))
                    y += self.grid_size / 2
                    
                painter.drawLines(lines)
            
    def snap_to_grid_point(self, pos):
        """将坐标吸附到最近的网格点"""
        if not self.snap_to_grid:
            return pos
            
        x = round(pos.x() / self.grid_size) * self.grid_size
        y = round(pos.y() / self.grid_size) * self.grid_size
        return QPointF(x, y)
            
    def dragEnterEvent(self, event):
        try:
            if event.mimeData().hasText():
                # 显示可放置的光标
                self.setCursor(Qt.CursorShape.DragCopyCursor)
                event.setAccepted(True)
                event.acceptProposedAction()
            else:
                self.setCursor(Qt.CursorShape.ForbiddenCursor)
                event.ignore()
        except Exception as e:
            logger.error(f"拖拽进入事件出错: {str(e)}", exc_info=True)
            super().dragEnterEvent(event)
            
    def dragMoveEvent(self, event):
        try:
            if event.mimeData().hasText():
                # 显示可放置的光标
                self.setCursor(Qt.CursorShape.DragCopyCursor)
                event.setAccepted(True)
                event.acceptProposedAction()
            else:
                self.setCursor(Qt.CursorShape.ForbiddenCursor)
                event.ignore()
        except Exception as e:
            logger.error(f"拖动组件时出错: {str(e)}", exc_info=True)
            super().dragMoveEvent(event)
            
    def dropEvent(self, event):
        try:
            if not event.mimeData().hasText():
                event.ignore()
                return
                
            pos = self.mapToScene(event.position().toPoint())
            pos = self.snap_to_grid_point(pos)
            
            component_name = event.mimeData().text()
            component = Component(component_name)
            component.setPos(pos)
            self.scene().addItem(component)
            self.circuit.add_component(component)
            
            # 确保视图更新
            self.scene().update()
            self.viewport().update()
            
            # 清除任何可能的拖拽状态
            self.setCursor(Qt.CursorShape.ArrowCursor)
            
            event.setAccepted(True)
            event.acceptProposedAction()
        except Exception as e:
            logger.error(f"放置组件时出错: {str(e)}", exc_info=True)
            event.ignore()
        
    def mousePressEvent(self, event):
        try:
            # 检查是否是拖动视图的条件
            if event.button() == Qt.MouseButton.MiddleButton or \
                (event.button() == Qt.MouseButton.LeftButton and 
                 QApplication.keyboardModifiers() == Qt.KeyboardModifier.ShiftModifier):
                self.is_panning = True
                self.last_pan_point = event.position().toPoint()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                event.accept()
                return
            
            # 继续处理线路创建逻辑
            if event.button() == Qt.MouseButton.LeftButton:
                scene_pos = self.mapToScene(event.position().toPoint())
                
                # 如果正在创建导线
                if self.current_wire:
                    # 检查是否在连接点附近
                    connection_point = self.find_connection_point(scene_pos)
                    if connection_point:
                        # 更新导线终点到连接点位置
                        self.current_wire.set_end_pos(connection_point.scenePos())
                        # 连接导线到连接点
                        self.current_wire.connect_endpoint(connection_point, False)
                        # 完成导线创建
                        self.wires.append(self.current_wire)
                        self.current_wire = None
                        self.setCursor(Qt.CursorShape.ArrowCursor)
                    else:
                        # 如果不是在连接点附近，结束当前导线创建
                        self.scene().removeItem(self.current_wire)
                        self.current_wire = None
                        self.setCursor(Qt.CursorShape.ArrowCursor)
                else:
                    # 检查是否点击了连接点以开始创建导线
                    connection_point = self.find_connection_point(scene_pos)
                    if connection_point:
                        # 开始创建新导线
                        self.current_wire = Wire(connection_point.scenePos())
                        self.scene().addItem(self.current_wire)
                        self.current_wire.connect_endpoint(connection_point, True)
                        self.setCursor(Qt.CursorShape.CrossCursor)
                    
                    # 如果都不是，传递事件给默认处理
                    else:
                        super().mousePressEvent(event)
            else:
                super().mousePressEvent(event)
        except Exception as e:
            logger.error(f"鼠标按下事件出错: {str(e)}", exc_info=True)
            super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        try:
            # 处理视图拖动
            if self.is_panning:
                delta = event.position().toPoint() - self.last_pan_point
                self.last_pan_point = event.position().toPoint()
                self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
                self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
                event.accept()
                return
                
            # 处理导线创建过程中的移动
            if self.current_wire:
                scene_pos = self.mapToScene(event.position().toPoint())
                
                # 检查是否在连接点附近悬停
                connection_point = self.find_connection_point(scene_pos)
                if connection_point:
                    self.current_wire.set_end_pos(connection_point.scenePos())
                    self.setCursor(Qt.CursorShape.CrossCursor)
                else:
                    self.current_wire.set_end_pos(scene_pos)
                    self.setCursor(Qt.CursorShape.CrossCursor)
            else:
                # 检查是否悬停在连接点上
                scene_pos = self.mapToScene(event.position().toPoint())
                connection_point = self.find_connection_point(scene_pos)
                if connection_point:
                    self.setCursor(Qt.CursorShape.CrossCursor)
                else:
                    self.setCursor(Qt.CursorShape.ArrowCursor)
                    
                super().mouseMoveEvent(event)
        except Exception as e:
            logger.error(f"鼠标移动事件出错: {str(e)}", exc_info=True)
            super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        try:
            # 结束视图拖动
            if self.is_panning and event.button() in [Qt.MouseButton.MiddleButton, Qt.MouseButton.LeftButton]:
                self.is_panning = False
                self.setCursor(Qt.CursorShape.ArrowCursor)
                event.accept()
                return
                
            super().mouseReleaseEvent(event)
        except Exception as e:
            logger.error(f"鼠标释放事件出错: {str(e)}", exc_info=True)
            super().mouseReleaseEvent(event)
            
    def contextMenuEvent(self, event):
        try:
            menu = QMenu(self)
            
            # 添加重置视图选项
            reset_view_action = menu.addAction("重置视图")
            reset_view_action.triggered.connect(self.reset_view)
            
            # 检查是否点击在组件或导线上
            scene_pos = self.mapToScene(event.pos())
            item = self.scene().itemAt(scene_pos, QTransform())
            
            # 如果是组件或导线，添加特定操作
            if isinstance(item, Component):
                edit_action = menu.addAction("编辑属性")
                delete_action = menu.addAction("删除组件")
                
                action = menu.exec(event.globalPos())
                
                if action == edit_action:
                    item.edit_properties()
                elif action == delete_action:
                    self.remove_component(item)
            elif isinstance(item, Wire):
                # 调用导线的上下文菜单
                item.show_context_menu(event)
                return
            else:
                menu.exec(event.globalPos())
        except Exception as e:
            logger.error(f"上下文菜单事件出错: {str(e)}", exc_info=True)
            
    def reset_view(self):
        """重置视图到默认位置和缩放"""
        self.resetTransform()
        self.centerOn(0, 0)
        
    def find_connection_point(self, scene_pos):
        """查找最近的连接点"""
        closest_point = None
        min_dist = float('inf')
        
        for item in self.scene().items():
            if isinstance(item, ConnectionPoint):
                point_pos = item.scenePos()
                dist = (point_pos - scene_pos).manhattanLength()
                if dist < min_dist and dist < 10.0:
                    min_dist = dist
                    closest_point = item
            elif isinstance(item, Component):
                point = item.get_closest_connection_point(scene_pos)
                if point:
                    point_pos = point.scenePos()
                    dist = (point_pos - scene_pos).manhattanLength()
                    if dist < min_dist and dist < 10.0:
                        min_dist = dist
                        closest_point = point
                    
        return closest_point
        
    def wheelEvent(self, event):
        zoom_factor = 1.15
        if event.angleDelta().y() > 0:
            self.scale(zoom_factor, zoom_factor)
        else:
            self.scale(1.0 / zoom_factor, 1.0 / zoom_factor)
            
    def clear_circuit(self):
        self.scene().clear()
        self.circuit = Circuit()
        
    def save_circuit(self, filename):
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(self.circuit.to_dict(), f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            QMessageBox.warning(self, "错误", f"保存电路失败：{str(e)}")
            return False
            
    def load_circuit(self, filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.clear_circuit()
            self.circuit = Circuit.from_dict(data)
            
            # 添加组件到场景
            for comp in self.circuit.components:
                # 确保组件位置对齐到网格
                pos = self.snap_to_grid_point(comp.pos())
                comp.setPos(pos)
                self.scene().addItem(comp)
                
            # 添加连接线
            for from_comp, to_comp in self.circuit.connections:
                line = self.scene().addLine(
                    from_comp.pos().x(),
                    from_comp.pos().y(),
                    to_comp.pos().x(),
                    to_comp.pos().y(),
                    QPen(Qt.GlobalColor.black, 2)
                )
            return True
        except Exception as e:
            QMessageBox.warning(self, "错误", f"加载电路失败：{str(e)}")
            return False
            
    def toggle_grid(self, checked):
        """切换网格显示状态"""
        self.show_grid = checked
        self.update()
        
    def toggle_snap(self, checked):
        """切换网格吸附状态"""
        self.snap_to_grid = checked
        self.update()
        
    def set_grid_size(self, size):
        self.grid_size = size
        self.update()

    def start_simulation(self, voltage):
        """开始仿真"""
        if self.simulation_running:
            return
            
        self.simulation_running = True
        self.simulation_step = 0
        self.circuit.calculate_circuit(voltage)
        self.update()  # 更新显示
        
    def stop_simulation(self):
        """停止仿真"""
        self.simulation_running = False
        if self.simulation_timer:
            self.simulation_timer.stop()
            
    def reset_simulation(self):
        """重置仿真"""
        self.stop_simulation()
        self.simulation_step = 0
        # 重置所有组件的状态
        for comp in self.circuit.components:
            comp.voltage = 0
            comp.current = 0
        self.update()
        
    def update_simulation(self):
        """更新仿真状态"""
        if not self.simulation_running:
            return
            
        self.simulation_step += 1
        if self.simulation_step >= self.max_simulation_steps:
            self.stop_simulation()
            return
            
        # 更新电路状态
        self.circuit.calculate_circuit()
        self.update()  # 更新显示

    def remove_component(self, component):
        """从场景和电路中移除组件"""
        try:
            # 断开所有连接的导线
            for point in component.connection_points:
                for wire in point.connected_wires[:]:  # 使用副本进行迭代
                    wire.delete_wire()
                    
            # 从场景中移除组件
            self.scene().removeItem(component)
            
            # 从电路中移除组件
            if component in self.circuit.components:
                self.circuit.components.remove(component)
            
            logger.debug(f"组件已移除: {component.name}")
        except Exception as e:
            logger.error(f"移除组件时出错: {str(e)}", exc_info=True)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("物理电学实验仿真软件")
        self.setMinimumSize(1200, 800)
        
        # 创建主分割器
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(self.main_splitter)
        
        # 左侧面板 - 电路图
        self.circuit_panel = QWidget()
        self.circuit_layout = QVBoxLayout(self.circuit_panel)
        self.circuit_layout.setContentsMargins(5, 5, 5, 5)  # 减小边距
        
        # 创建右侧工作区（提前创建）
        self.work_area = WorkArea()
        
        # 连接电压变化信号
        self.work_area.voltage_changed_signal.connect(self.update_voltage_input)
        
        # 创建菜单栏 - 在work_area创建后
        self.menubar = self.menuBar()
        
        # 文件菜单
        file_menu = self.menubar.addMenu("文件")
        
        save_action = file_menu.addAction("保存电路")
        save_action.triggered.connect(self.save_circuit)
        
        save_json_action = file_menu.addAction("保存为JSON")
        save_json_action.triggered.connect(self.save_circuit_to_json)
        
        load_action = file_menu.addAction("加载电路")
        load_action.triggered.connect(self.load_circuit)
        
        clear_action = file_menu.addAction("清空电路")
        clear_action.triggered.connect(self.clear_circuit)
        
        # 视图菜单
        view_menu = self.menubar.addMenu("视图")
        
        # 添加网格显示控制
        self.toggle_grid_action = view_menu.addAction("显示/隐藏网格")
        self.toggle_grid_action.setCheckable(True)  # 使动作可选中
        self.toggle_grid_action.setChecked(True)    # 默认选中
        self.toggle_grid_action.triggered.connect(self.toggle_grid)
        
        # 添加网格吸附控制
        self.toggle_snap_action = view_menu.addAction("启用/禁用网格吸附")
        self.toggle_snap_action.setCheckable(True)  # 使动作可选中
        self.toggle_snap_action.setChecked(True)    # 默认选中
        self.toggle_snap_action.triggered.connect(self.toggle_snap)
        
        # 创建左侧工具栏
        toolbar = QWidget()
        toolbar.setFixedWidth(220)  # 固定宽度防止过宽
        toolbar_layout = QVBoxLayout(toolbar)
        toolbar_layout.setSpacing(6)  # 减小间距
        toolbar_layout.setContentsMargins(3, 3, 3, 3)  # 减小边距
        
        # 添加组件分组
        components_group = QGroupBox("电路元件")
        components_layout = QGridLayout(components_group)
        components_layout.setSpacing(6)  # 减小组件间距
        components_layout.setContentsMargins(5, 15, 5, 5)  # 调整边距，顶部留更多空间给标题
        
        # 添加组件按钮
        components = ["电源", "开关", "导线", "定值电阻", "滑动变阻器", "电流表", "电压表"]
        for i, component in enumerate(components):
            btn = ComponentButton(component)
            btn.setMinimumSize(100, 35)  # 设置最小大小防止重叠
            btn.setMaximumSize(105, 35)  # 设置最大大小防止过大
            row = i // 2  # 计算行号
            col = i % 2   # 计算列号
            components_layout.addWidget(btn, row, col)
            
        toolbar_layout.addWidget(components_group)
        
        # 添加控制分组
        control_group = QGroupBox("控制面板")
        control_layout = QVBoxLayout(control_group)
        control_layout.setSpacing(8)  # 增加间距
        control_layout.setContentsMargins(8, 20, 8, 8)  # 调整边距，顶部留更多空间给标题
        
        # 添加电压控制
        voltage_layout = QHBoxLayout()
        voltage_layout.setSpacing(5)  # 设置水平间距
        voltage_label = QLabel("电源电压(V):")
        self.voltage_input = QLineEdit("12")
        self.voltage_input.setFixedWidth(70)  # 增加输入框宽度
        voltage_layout.addWidget(voltage_label)
        voltage_layout.addWidget(self.voltage_input)
        voltage_layout.addStretch(1)  # 添加弹性空间
        control_layout.addLayout(voltage_layout)
        
        # 添加网格大小控制
        grid_size_layout = QHBoxLayout()
        grid_size_layout.setSpacing(5)  # 设置水平间距
        grid_size_label = QLabel("网格大小:")
        self.grid_size_combo = QComboBox()
        self.grid_size_combo.addItems(["10", "20", "30", "40", "50"])
        self.grid_size_combo.setCurrentText("20")
        self.grid_size_combo.setFixedWidth(70)  # 增加下拉框宽度
        self.grid_size_combo.currentTextChanged.connect(
            lambda x: self.work_area.set_grid_size(int(x))
        )
        grid_size_layout.addWidget(grid_size_label)
        grid_size_layout.addWidget(self.grid_size_combo)
        grid_size_layout.addStretch(1)  # 添加弹性空间
        control_layout.addLayout(grid_size_layout)
        
        # 添加缩放控制
        zoom_layout = QHBoxLayout()
        zoom_layout.setSpacing(5)  # 设置水平间距
        zoom_out_button = QPushButton("-")
        zoom_in_button = QPushButton("+")
        zoom_out_button.setFixedSize(45, 32)  # 增加按钮大小
        zoom_in_button.setFixedSize(45, 32)   # 增加按钮大小
        zoom_out_button.clicked.connect(lambda: self.work_area.scale(0.8, 0.8))
        zoom_in_button.clicked.connect(lambda: self.work_area.scale(1.2, 1.2))
        zoom_layout.addWidget(zoom_out_button)
        zoom_layout.addWidget(zoom_in_button)
        zoom_layout.addStretch(1)  # 添加弹性空间
        control_layout.addLayout(zoom_layout)
        
        toolbar_layout.addWidget(control_group)
        
        # 添加文件操作分组
        file_group = QGroupBox("文件操作")
        file_layout = QVBoxLayout(file_group)
        file_layout.setSpacing(4)  # 减小间距
        file_layout.setContentsMargins(5, 15, 5, 5)  # 调整边距
        
        save_button = QPushButton("保存电路")
        load_button = QPushButton("加载电路")
        clear_button = QPushButton("清空电路")
        
        # 统一设置按钮大小
        for btn in [save_button, load_button, clear_button]:
            btn.setMinimumHeight(28)
            btn.setMaximumHeight(30)
        
        save_button.clicked.connect(self.save_circuit)
        load_button.clicked.connect(self.load_circuit)
        clear_button.clicked.connect(self.clear_circuit)
        
        file_layout.addWidget(save_button)
        file_layout.addWidget(load_button)
        file_layout.addWidget(clear_button)
        
        toolbar_layout.addWidget(file_group)
        
        # 添加仿真控制分组
        sim_group = QGroupBox("仿真控制")
        sim_layout = QVBoxLayout(sim_group)
        sim_layout.setSpacing(4)  # 减小间距
        sim_layout.setContentsMargins(5, 15, 5, 5)  # 调整边距
        
        self.start_button = QPushButton("开始仿真")
        self.stop_button = QPushButton("停止仿真")
        self.reset_button = QPushButton("重置仿真")
        
        # 统一设置按钮大小
        for btn in [self.start_button, self.stop_button, self.reset_button]:
            btn.setMinimumHeight(28)
            btn.setMaximumHeight(30)
        
        self.start_button.clicked.connect(self.start_simulation)
        self.stop_button.clicked.connect(self.stop_simulation)
        self.reset_button.clicked.connect(self.reset_simulation)
        
        # 初始化按钮状态
        self.stop_button.setEnabled(False)
        self.reset_button.setEnabled(False)
        
        sim_layout.addWidget(self.start_button)
        sim_layout.addWidget(self.stop_button)
        sim_layout.addWidget(self.reset_button)
        
        toolbar_layout.addWidget(sim_group)
        
        # 添加仿真状态显示
        status_group = QGroupBox("仿真状态")
        status_layout = QVBoxLayout(status_group)
        status_layout.setSpacing(4)  # 减小间距
        status_layout.setContentsMargins(5, 15, 5, 5)  # 调整边距
        
        self.simulation_status_label = QLabel("仿真状态: 未开始")
        self.simulation_step_label = QLabel("仿真步数: 0")
        self.measurement_label = QLabel("测量结果: ")
        
        status_layout.addWidget(self.simulation_status_label)
        status_layout.addWidget(self.simulation_step_label)
        status_layout.addWidget(self.measurement_label)
        
        toolbar_layout.addWidget(status_group)
        
        toolbar_layout.addStretch()
        
        # 将工具栏添加到电路面板布局中
        self.circuit_layout.addWidget(toolbar)
        
        # 将面板添加到分割器
        self.main_splitter.addWidget(self.circuit_panel)
        self.main_splitter.addWidget(self.work_area)
        
        # 调整分割器初始比例，左侧工具栏窄一些，中间网格区域宽一些
        self.main_splitter.setSizes([220, self.width() - 520])
        
        # 右侧面板 - AI聊天
        self.chat_panel = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_panel)
        
        # 聊天历史
        self.chat_history = QTextEdit()
        self.chat_history.setReadOnly(True)
        
        # 聊天输入
        self.chat_input = QTextEdit()
        self.chat_input.setMaximumHeight(100)
        self.chat_input.setPlaceholderText("在这里输入你的问题...")
        
        # 发送按钮
        self.send_button = QPushButton("发送")
        self.send_button.clicked.connect(self.send_message)
        
        # 添加所有部件到聊天面板
        self.chat_layout.addWidget(QLabel("AI助手 - 物理实验指导"))
        self.chat_layout.addWidget(self.chat_history)
        self.chat_layout.addWidget(self.chat_input)
        self.chat_layout.addWidget(self.send_button)
        
        # 将面板添加到分割器
        self.main_splitter.addWidget(self.chat_panel)
        
        # 设置样式
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f5;
            }
            QGroupBox {
                border: 1px solid #ccc;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
                color: #333333;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px;
                color: #333333;
            }
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 5px;
                text-align: center;
                qproperty-alignment: AlignCenter;
                min-height: 28px;
                max-height: 30px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
            QLineEdit {
                padding: 3px;
                border: 1px solid #ccc;
                border-radius: 3px;
                color: #333333;
                background-color: #ffffff;
            }
            QLineEdit:focus {
                border-color: #4CAF50;
            }
            QLabel {
                color: #333333;
            }
            QComboBox {
                color: #333333;
                background-color: white;
                border: 1px solid #ccc;
                border-radius: 3px;
                padding: 3px;
                min-height: 24px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #333333;
                width: 0;
                height: 0;
                margin-right: 5px;
            }
        """)
        
        # 创建定时器用于更新仿真状态
        self.simulation_timer = QTimer()
        self.simulation_timer.timeout.connect(self.update_simulation)
        self.simulation_timer.setInterval(100)  # 100ms更新一次
        
    def showEvent(self, event):
        """窗口显示时调整分割器比例"""
        super().showEvent(event)
        # 确保在窗口显示后再次设置分割比例
        QTimer.singleShot(100, self.adjust_splitter_sizes)
    
    def adjust_splitter_sizes(self):
        """调整分割器大小比例"""
        total_width = self.width()
        left_width = 220  # 左侧工具栏宽度
        right_width = 300  # 右侧聊天区域宽度
        center_width = total_width - left_width - right_width  # 中间工作区宽度
        
        self.main_splitter.setSizes([left_width, center_width, right_width])
        
    def save_circuit(self):
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "保存电路",
            "",
            "电路文件 (*.circuit);;所有文件 (*.*)"
        )
        if filename:
            if not filename.endswith('.circuit'):
                filename += '.circuit'
            if self.work_area.save_circuit(filename):
                QMessageBox.information(self, "成功", "电路保存成功！")
                
    def load_circuit(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "加载电路",
            "",
            "电路文件 (*.circuit);;所有文件 (*.*)"
        )
        if filename:
            if self.work_area.load_circuit(filename):
                QMessageBox.information(self, "成功", "电路加载成功！")
                
    def clear_circuit(self):
        reply = QMessageBox.question(
            self,
            "确认",
            "确定要清空当前电路吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.work_area.clear_circuit()
            QMessageBox.information(self, "成功", "电路已清空！")
            
    def start_simulation(self):
        try:
            voltage = float(self.voltage_input.text())
            self.work_area.start_simulation(voltage)
            
            # 更新状态显示
            self.simulation_status_label.setText("仿真状态: 运行中")
            self.simulation_step_label.setText("仿真步数: 0")
            
            # 更新按钮状态
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            self.reset_button.setEnabled(True)
            
            # 开始定时更新
            self.simulation_timer.start()
            
            # 显示初始测量结果
            self.update_measurements()
            
        except ValueError:
            QMessageBox.warning(self, "错误", "请输入有效的电压值")
            
    def stop_simulation(self):
        self.work_area.stop_simulation()
        self.simulation_timer.stop()
        
        # 更新状态显示
        self.simulation_status_label.setText("仿真状态: 已停止")
        
        # 更新按钮状态
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.reset_button.setEnabled(True)
        
        # 显示最终测量结果
        self.update_measurements()
        
    def reset_simulation(self):
        self.work_area.reset_simulation()
        self.simulation_timer.stop()
        
        # 更新状态显示
        self.simulation_status_label.setText("仿真状态: 已重置")
        self.simulation_step_label.setText("仿真步数: 0")
        self.measurement_label.setText("测量结果: ")
        
        # 更新按钮状态
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.reset_button.setEnabled(False)
        
    def update_simulation(self):
        """更新仿真状态"""
        if not self.work_area.simulation_running:
            return
            
        self.work_area.update_simulation()
        
        # 更新状态显示
        self.simulation_step_label.setText(f"仿真步数: {self.work_area.simulation_step}")
        self.update_measurements()
        
    def update_measurements(self):
        """更新测量结果显示"""
        results = []
        for comp in self.work_area.circuit.components:
            if comp.name in ["电流表", "电压表"]:
                if comp.name == "电流表":
                    results.append(f"电流表读数: {comp.current:.2f}A")
                else:
                    results.append(f"电压表读数: {comp.voltage:.2f}V")
                    
        if results:
            self.measurement_label.setText("测量结果: " + "\n".join(results))
        else:
            self.measurement_label.setText("测量结果: 无测量仪器")

    def update_voltage_input(self, value):
        """更新电压输入框的值"""
        self.voltage_input.setText(f"{value:.1f}")
        # 如果正在仿真，重新计算电路
        if self.work_area.simulation_running:
            self.work_area.start_simulation(value)

    def save_circuit_to_json(self):
        """保存电路图到JSON文件"""
        # 获取电路数据
        circuit_data = self.get_circuit_data()
        
        # 打开文件对话框
        file_path, _ = QFileDialog.getSaveFileName(self, "保存电路图", "", "JSON文件 (*.json)")
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(circuit_data, f, ensure_ascii=False, indent=4)
                QMessageBox.information(self, "保存成功", f"电路图已保存到: {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "保存失败", f"保存时出错: {str(e)}")
    
    def get_circuit_data(self):
        """获取电路图的数据结构"""
        circuit_data = {
            "components": [],
            "connections": [],
            "settings": {
                "voltage": self.work_area.voltage
            }
        }
        
        # 收集组件数据
        for component in self.work_area.components:
            component_data = {
                "name": component.name,
                "type": component.type,
                "x": component.x(),
                "y": component.y(),
                "rotation": component.rotation,
                "properties": component.properties
            }
            circuit_data["components"].append(component_data)
        
        # 收集连线数据
        for wire in self.work_area.wires:
            connection_data = {}
            
            # 安全地添加连接点信息
            if hasattr(wire, 'source_point') and wire.source_point:
                if hasattr(wire.source_point, 'parent_component') and wire.source_point.parent_component:
                    connection_data["start_component"] = wire.source_point.parent_component.name
                if hasattr(wire.source_point, 'index'):
                    connection_data["start_point"] = wire.source_point.index
                    
            if hasattr(wire, 'target_point') and wire.target_point:
                if hasattr(wire.target_point, 'parent_component') and wire.target_point.parent_component:
                    connection_data["end_component"] = wire.target_point.parent_component.name
                if hasattr(wire.target_point, 'index'):
                    connection_data["end_point"] = wire.target_point.index
            
            # 安全地添加路径信息
            if hasattr(wire, 'path'):
                try:
                    if isinstance(wire.path, list):
                        connection_data["path"] = [[p.x(), p.y()] for p in wire.path]
                    elif callable(wire.path):
                        # 如果path是一个方法，调用它获取路径点
                        path_points = wire.path()
                        if isinstance(path_points, list):
                            connection_data["path"] = [[p.x(), p.y()] for p in path_points]
                except Exception as e:
                    print(f"获取路径点时出错: {str(e)}")
                    connection_data["path"] = []
            
            circuit_data["connections"].append(connection_data)
        
        return circuit_data

    def send_message(self):
        """发送消息到AI并获取回复"""
        user_message = self.chat_input.toPlainText().strip()
        if not user_message:
            return
        
        # 显示用户消息
        self.chat_history.append(f"<b>你:</b> {user_message}")
        self.chat_input.clear()
        
        try:
            # 导入test_api模块
            from test_api import LLMClient, LLMConfig, load_config
            
            # 加载配置
            config = load_config()
            
            # 创建客户端
            llm_client = LLMClient(config)
            
            # 获取电路数据作为上下文
            circuit_data = self.get_circuit_data()
            
            # 构建提示词
            system_prompt = """你是一位专业的物理电学实验助手。请帮助用户理解和构建电路实验。
            你需要：
            1. 分析当前电路的组成和连接
            2. 提供专业的建议和指导
            3. 回答用户的具体问题
            4. 指出可能存在的问题和改进建议"""
            
            # 构建带有电路上下文的提示词
            prompt = f"""
用户问题: {user_message}

当前电路信息:
"""
            # 添加组件信息
            if circuit_data["components"]:
                prompt += "\n电路组件:\n"
                for comp in circuit_data["components"]:
                    prompt += f"- {comp['name']} (位置: x={comp['x']:.1f}, y={comp['y']:.1f})\n"
                    if "properties" in comp:
                        for prop_name, prop_value in comp["properties"].items():
                            prompt += f"  {prop_name}: {prop_value}\n"
            else:
                prompt += "- 电路中没有组件\n"
            
            # 添加连接信息
            if circuit_data["connections"]:
                prompt += "\n电路连接情况:\n"
                for i, conn in enumerate(circuit_data["connections"]):
                    prompt += f"- 连接{i+1}: 从组件ID {conn['start_component']} 到 {conn['end_component']}\n"
            else:
                prompt += "\n电路中没有连接\n"
            
            # 添加电源设置信息
            prompt += f"\n电源电压设置: {circuit_data['settings']['voltage']}V\n"
            prompt += "\n请根据以上电路信息回答用户问题。如果需要更多信息，请明确指出。"
            
            # 显示正在获取回复的提示
            self.chat_history.append('<font color="blue"><b>系统:</b> 正在获取回复...</font>')
            QApplication.processEvents()
            
            # 调用API获取回复
            response = llm_client.run_llm(
                prompt,
                system_prompt=system_prompt,
                temperature=0.1  # 使用较低的温度以获得更确定的回答
            )
            
            # 显示回复
            self.chat_history.append(f"<b>AI助手:</b> {response}")
            
        except ImportError as e:
            error_msg = "无法导入test_api模块，请确保已安装必要的库"
            self.chat_history.append(f'<font color="red"><b>错误:</b> {error_msg}</font>')
            QMessageBox.critical(self, "模块错误", error_msg)
            
        except Exception as e:
            error_msg = f"API请求失败: {str(e)}"
            self.chat_history.append(f'<font color="red"><b>错误:</b> {error_msg}</font>')
            QMessageBox.critical(self, "API错误", f"调用API时出错:\n{str(e)}")

    def toggle_grid(self, checked):
        """切换网格显示状态"""
        self.work_area.show_grid = checked
        self.work_area.update()
        
    def toggle_snap(self, checked):
        """切换网格吸附状态"""
        self.work_area.snap_to_grid = checked
        self.work_area.update()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec()) 