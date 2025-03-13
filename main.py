import sys
import os
import json
import logging
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QHBoxLayout, QPushButton, QLabel, QGraphicsView,
                           QGraphicsScene, QMessageBox, QLineEdit, QSlider,
                           QDialog, QFormLayout, QDoubleSpinBox, QFileDialog,
                           QGroupBox, QComboBox, QCheckBox)
from PyQt6.QtCore import Qt, QMimeData, QPointF, QTimer, QLineF
from PyQt6.QtGui import QDrag, QPainter, QColor, QPen
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
        self.setMinimumSize(100, 40)
        self.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px;
                font-size: 14px;
                margin: 3px;
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
            drag = QDrag(self)
            mime = QMimeData()
            mime.setText(self.component_name)
            drag.setMimeData(mime)
            drag.exec()

class WorkArea(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setAcceptDrops(True)
        
        self.setStyleSheet("""
            QGraphicsView {
                background-color: white;
                border: 1px solid #ccc;
                border-radius: 5px;
            }
        """)
        
        self.circuit = Circuit()
        self.current_wire = None
        self.drawing_wire = False
        self.source_point = None
        self.grid_size = 20
        self.show_grid = True
        self.snap_to_grid = True
        self.simulation_running = False
        self.simulation_timer = None
        self.simulation_step = 0
        self.max_simulation_steps = 1000
        self.dragging_wire = None
        logger.debug("WorkArea 初始化完成")
        
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
        if event.mimeData().hasText():
            event.acceptProposedAction()
        
    def dragMoveEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()
            
    def dropEvent(self, event):
        pos = self.mapToScene(event.position().toPoint())
        pos = self.snap_to_grid_point(pos)
        
        component_name = event.mimeData().text()
        component = Component(component_name)
        component.setPos(pos)
        self.scene.addItem(component)
        self.circuit.add_component(component)
        event.acceptProposedAction()
        
    def mousePressEvent(self, event):
        try:
            scene_pos = self.mapToScene(event.position().toPoint())
            logger.debug(f"鼠标按下事件: pos={scene_pos}")
            
            if event.button() == Qt.MouseButton.LeftButton:
                item = self.scene.itemAt(scene_pos, self.transform())
                logger.debug(f"点击项类型: {type(item)}")
                
                if isinstance(item, ConnectionPoint):
                    # 开始绘制导线
                    self.drawing_wire = True
                    self.source_point = item
                    start_pos = item.scenePos()
                    self.current_wire = Wire(start_pos)
                    self.scene.addItem(self.current_wire)
                    self.current_wire.source_component = item.parentItem()
                    logger.debug(f"开始绘制导线: start_pos={start_pos}")
                elif isinstance(item, Wire):
                    # 处理导线的拖动
                    self.dragging_wire = item
                    logger.debug("开始拖动已有导线")
                elif isinstance(item, Component):
                    logger.debug("点击组件")
                    super().mousePressEvent(event)
                    
            elif event.button() == Qt.MouseButton.RightButton:
                item = self.scene.itemAt(scene_pos, self.transform())
                if isinstance(item, Component):
                    dialog = PropertyDialog(item, self)
                    dialog.exec()
        except Exception as e:
            logger.error(f"鼠标按下事件处理出错: {str(e)}", exc_info=True)
                
    def mouseMoveEvent(self, event):
        try:
            scene_pos = self.mapToScene(event.position().toPoint())
            
            if self.drawing_wire and self.current_wire:
                # 处理新导线的绘制
                closest_point = self.find_closest_connection_point(scene_pos)
                if closest_point and closest_point != self.source_point:
                    self.current_wire.set_end_pos(closest_point.scenePos())
                    logger.debug(f"导线绘制吸附到连接点: pos={closest_point.scenePos()}")
                else:
                    self.current_wire.set_end_pos(scene_pos)
                    logger.debug(f"导线绘制跟随鼠标: pos={scene_pos}")
            elif self.dragging_wire:
                # 处理导线的拖动
                logger.debug(f"拖动导线: pos={scene_pos}")
                self.dragging_wire.mouseMoveEvent(event)
            else:
                super().mouseMoveEvent(event)
        except Exception as e:
            logger.error(f"鼠标移动事件处理出错: {str(e)}", exc_info=True)
            
    def mouseReleaseEvent(self, event):
        try:
            if event.button() == Qt.MouseButton.LeftButton:
                if self.drawing_wire:
                    scene_pos = self.mapToScene(event.position().toPoint())
                    target_point = self.find_closest_connection_point(scene_pos)
                    logger.debug(f"释放导线: pos={scene_pos}, 找到目标点={target_point is not None}")
                    
                    if target_point and target_point != self.source_point:
                        # 完成导线连接
                        self.current_wire.end_pos = target_point.scenePos()
                        self.current_wire.update_path()
                        self.current_wire.target_component = target_point.parentItem()
                        
                        # 更新连接点的导线列表
                        self.source_point.connected_wires.append(self.current_wire)
                        target_point.connected_wires.append(self.current_wire)
                        
                        # 更新电路连接
                        self.circuit.add_connection(self.current_wire.source_component,
                                                 self.current_wire.target_component)
                        logger.debug("导线连接完成")
                    else:
                        # 如果没有找到目标连接点，删除导线
                        self.scene.removeItem(self.current_wire)
                        logger.debug("未找到目标连接点，删除导线")
                        
                    self.drawing_wire = False
                    self.current_wire = None
                    self.source_point = None
                elif self.dragging_wire:
                    logger.debug("结束导线拖动")
                    self.dragging_wire.mouseReleaseEvent(event)
                    self.dragging_wire = None
            
            super().mouseReleaseEvent(event)
        except Exception as e:
            logger.error(f"鼠标释放事件处理出错: {str(e)}", exc_info=True)
        
    def find_closest_connection_point(self, scene_pos):
        """查找最近的连接点"""
        closest_point = None
        min_dist = float('inf')
        
        for item in self.scene.items():
            if isinstance(item, Component):
                point = item.get_closest_connection_point(scene_pos)
                if point and point != self.source_point:
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
        self.scene.clear()
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
                self.scene.addItem(comp)
                
            # 添加连接线
            for from_comp, to_comp in self.circuit.connections:
                line = self.scene.addLine(
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
            
    def toggle_grid(self):
        self.show_grid = not self.show_grid
        self.update()
        
    def toggle_snap(self):
        self.snap_to_grid = not self.snap_to_grid
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

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("物理电学实验仿真软件")
        self.setMinimumSize(1200, 800)
        
        # 创建主窗口部件
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        # 创建主布局
        layout = QHBoxLayout(main_widget)
        layout.setSpacing(10)
        
        # 创建右侧工作区（提前创建）
        self.work_area = WorkArea()
        
        # 创建左侧工具栏
        toolbar = QWidget()
        toolbar.setMaximumWidth(250)
        toolbar_layout = QVBoxLayout(toolbar)
        toolbar_layout.setSpacing(10)
        
        # 添加组件分组
        components_group = QGroupBox("电路元件")
        components_layout = QVBoxLayout(components_group)
        components_layout.setSpacing(5)
        
        # 添加组件按钮
        components = ["电源", "开关", "导线", "定值电阻", "滑动变阻器", "电流表", "电压表"]
        for component in components:
            btn = ComponentButton(component)
            components_layout.addWidget(btn)
            
        toolbar_layout.addWidget(components_group)
        
        # 添加控制分组
        control_group = QGroupBox("控制面板")
        control_layout = QVBoxLayout(control_group)
        control_layout.setSpacing(5)
        
        # 添加电压控制
        voltage_layout = QHBoxLayout()
        voltage_label = QLabel("电源电压(V):")
        self.voltage_input = QLineEdit("12")
        self.voltage_input.setMaximumWidth(80)
        voltage_layout.addWidget(voltage_label)
        voltage_layout.addWidget(self.voltage_input)
        control_layout.addLayout(voltage_layout)
        
        # 添加网格控制
        grid_layout = QVBoxLayout()
        
        # 网格显示控制
        grid_button = QPushButton("显示/隐藏网格")
        grid_button.clicked.connect(self.work_area.toggle_grid)
        grid_layout.addWidget(grid_button)
        
        # 网格吸附控制
        snap_button = QPushButton("启用/禁用网格吸附")
        snap_button.clicked.connect(self.work_area.toggle_snap)
        grid_layout.addWidget(snap_button)
        
        # 网格大小控制
        grid_size_layout = QHBoxLayout()
        grid_size_label = QLabel("网格大小:")
        self.grid_size_combo = QComboBox()
        self.grid_size_combo.addItems(["10", "20", "30", "40", "50"])
        self.grid_size_combo.setCurrentText("20")
        self.grid_size_combo.currentTextChanged.connect(
            lambda x: self.work_area.set_grid_size(int(x))
        )
        grid_size_layout.addWidget(grid_size_label)
        grid_size_layout.addWidget(self.grid_size_combo)
        grid_layout.addLayout(grid_size_layout)
        
        control_layout.addLayout(grid_layout)
        
        # 添加缩放控制
        zoom_layout = QHBoxLayout()
        zoom_out_button = QPushButton("-")
        zoom_in_button = QPushButton("+")
        zoom_out_button.clicked.connect(lambda: self.work_area.scale(0.8, 0.8))
        zoom_in_button.clicked.connect(lambda: self.work_area.scale(1.2, 1.2))
        zoom_layout.addWidget(zoom_out_button)
        zoom_layout.addWidget(zoom_in_button)
        control_layout.addLayout(zoom_layout)
        
        toolbar_layout.addWidget(control_group)
        
        # 添加文件操作分组
        file_group = QGroupBox("文件操作")
        file_layout = QVBoxLayout(file_group)
        file_layout.setSpacing(5)
        
        save_button = QPushButton("保存电路")
        load_button = QPushButton("加载电路")
        clear_button = QPushButton("清空电路")
        
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
        sim_layout.setSpacing(5)
        
        self.start_button = QPushButton("开始仿真")
        self.stop_button = QPushButton("停止仿真")
        self.reset_button = QPushButton("重置仿真")
        
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
        status_layout.setSpacing(5)
        
        self.simulation_status_label = QLabel("仿真状态: 未开始")
        self.simulation_step_label = QLabel("仿真步数: 0")
        self.measurement_label = QLabel("测量结果: ")
        
        status_layout.addWidget(self.simulation_status_label)
        status_layout.addWidget(self.simulation_step_label)
        status_layout.addWidget(self.measurement_label)
        
        toolbar_layout.addWidget(status_group)
        
        toolbar_layout.addStretch()
        
        # 创建主布局
        main_layout = QVBoxLayout()
        content_layout = QHBoxLayout()
        content_layout.addWidget(toolbar)
        content_layout.addWidget(self.work_area)
        main_layout.addLayout(content_layout)
        layout.addLayout(main_layout)
        
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
                padding: 5px;
                border: 1px solid #ccc;
                border-radius: 3px;
                color: #333333;
            }
            QLabel {
                color: #333333;
            }
            QComboBox {
                color: #333333;
                background-color: white;
                border: 1px solid #ccc;
                border-radius: 3px;
                padding: 5px;
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

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec()) 