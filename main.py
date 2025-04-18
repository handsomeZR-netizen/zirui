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
                           QTextEdit, QSplitter, QScrollArea, QListWidget, QListWidgetItem)
from PyQt6.QtCore import Qt, QMimeData, QPointF, QTimer, QLineF, pyqtSignal, QPoint, QSettings
from PyQt6.QtGui import QDrag, QPainter, QColor, QPen, QBrush, QTransform, QPixmap
from components import Component, Circuit, Wire, ConnectionPoint, logger
import experiment_manager

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
        self.setMinimumSize(120, 38)  # 更新默认最小大小
        self.setMaximumSize(130, 38)  # 更新默认最大大小
        self.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 6px;
                font-size: 14px;
                margin: 3px;
                text-align: center;
                qproperty-alignment: AlignCenter;
                font-family: 'SimSun', 'simsun', serif;
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
        self.simulation_status = "未开始"  # 新增：仿真状态
        
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
        """清空电路画布"""
        self.scene().clear()
        self.circuit = Circuit()
        self.components = []
        self.wires = []
        self.current_wire = None
        # 重置电气参数
        self.voltage = 5.0
        self.simulation_running = False
        self.simulation_status = "未开始"
    
    def save_circuit(self, filename):
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(self.circuit.to_dict(self.scene()), f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            QMessageBox.warning(self, "错误", f"保存电路失败：{str(e)}")
            return False
            
    def load_circuit(self, filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.clear_circuit()
            # 传入场景参数给from_dict
            self.circuit = Circuit.from_dict(data, self.scene())
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
        """执行静态直流分析"""
        # 设置状态
        self.simulation_running = True
        
        # 执行一次电路计算
        result = self.circuit.calculate_circuit(voltage)
        
        if result:
            # 更新状态
            self.simulation_status = "已计算"
        else:
            # 计算失败
            self.simulation_status = "计算失败"
            QMessageBox.warning(None, "计算错误", "电路分析失败，请检查电路连接是否正确")
        
        # 更新显示
        self.update()
        
        # 返回计算结果状态，用于通知主窗口
        return result
    
    def stop_simulation(self):
        """停止仿真（保留计算结果）"""
        self.simulation_running = False
        self.simulation_status = "已停止"
        # 不清除计算结果，只更新状态
        self.update()
    
    def reset_simulation(self):
        """重置仿真（清除所有计算结果）"""
        self.simulation_running = False
        self.simulation_status = "未开始"
        
        # 重置所有组件的电气参数
        for comp in self.circuit.components:
            comp.voltage = 0
            comp.current = 0
        
        # 更新显示
        self.update()
    
    def update_simulation(self):
        """此方法保留用于属性变化后的手动更新"""
        if not self.simulation_running:
            return
            
        # 获取当前电压
        voltage = 5.0  # 默认值
        
        # 查找电源组件获取电压值
        for comp in self.circuit.components:
            if comp.name == "电源":
                voltage = comp.properties.get("电压值", 5.0)
                break
        
        # 重新计算电路
        self.circuit.calculate_circuit(voltage)
        
        # 更新显示
        self.update()

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
        
        # 设置实验配置文件路径
        self.experiment_file = os.path.join("experiments", "electrical_experiments.json")
        
        # 加载实验列表
        self.experiments = experiment_manager.load_experiments(self.experiment_file)
        self.current_experiment = None
        
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
        
        # 添加实验菜单
        experiments_menu = self.menubar.addMenu("实验")
        refresh_experiments_action = experiments_menu.addAction("刷新实验列表")
        refresh_experiments_action.triggered.connect(self.refresh_experiments)
        
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
        toolbar.setFixedWidth(280)  # 进一步增加工具栏宽度从250到280
        toolbar_layout = QVBoxLayout(toolbar)
        toolbar_layout.setSpacing(10)  # 进一步增加组件之间的垂直间距
        toolbar_layout.setContentsMargins(5, 5, 5, 5)  # 调整边距
        
        # 添加实验目录分组
        experiments_group = QGroupBox("物理电学实验目录")
        experiments_layout = QVBoxLayout(experiments_group)
        experiments_layout.setSpacing(10)  # 进一步增加内部组件间距
        experiments_layout.setContentsMargins(10, 25, 10, 10)  # 增加内边距
        
        # 添加实验选择提示标签
        experiment_label = QLabel("请从下方选择一个实验开始探究：")
        experiment_label.setStyleSheet("font-weight: bold; color: #333; font-size: 14px;")
        experiment_label.setWordWrap(True)  # 允许文本换行
        experiment_label.setMinimumHeight(30)  # 设置最小高度
        experiments_layout.addWidget(experiment_label)
        
        # 添加实验列表
        self.experiment_list = QListWidget()
        self.experiment_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #ccc;
                border-radius: 4px;
                background-color: white;
                font-size: 14px;
                font-family: 'SimSun', 'simsun', serif;
                padding: 5px;
            }
            QListWidget::item {
                height: 35px;  /* 进一步增加项目高度 */
                padding: 6px;
                border-bottom: 1px solid #eee;
            }
            QListWidget::item:selected {
                background-color: #3498db;
                color: white;
            }
            QListWidget::item:hover {
                background-color: #e0f0ff;
            }
        """)
        self.experiment_list.setMinimumHeight(200)  # 进一步增加列表最小高度
        self.populate_experiment_list()
        self.experiment_list.currentItemChanged.connect(self.handle_experiment_selected)
        experiments_layout.addWidget(self.experiment_list)
        
        # 添加状态显示区域
        self.experiment_status = QLabel("当前未选择实验")
        self.experiment_status.setStyleSheet("""
            font-weight: bold;
            color: #2c3e50;
            background-color: #ecf0f1;
            padding: 10px;  /* 增加内边距 */
            margin-top: 8px;  /* 增加上边距 */
            border-radius: 5px;
            font-size: 14px;  /* 增加字体大小 */
            font-family: 'SimSun', 'simsun', serif;
        """)
        self.experiment_status.setWordWrap(True)  # 允许文本换行
        self.experiment_status.setMinimumHeight(35)  # 设置最小高度
        experiments_layout.addWidget(self.experiment_status)
        
        # 添加任务目标区域
        goal_layout = QVBoxLayout()
        goal_layout.setSpacing(8)  # 增加间距
        goal_label = QLabel("实验目标：")
        goal_label.setStyleSheet("font-weight: bold; color: #333; margin-top: 10px; font-size: 14px;")
        self.goal_text = QTextEdit()
        self.goal_text.setReadOnly(True)
        self.goal_text.setMinimumHeight(90)  # 增加最小高度
        self.goal_text.setMaximumHeight(120)  # 增加最大高度
        self.goal_text.setStyleSheet("""
            QTextEdit {
                background-color: #f8f8f8;
                border: 1px solid #ddd;
                border-radius: 5px;
                font-size: 14px;
                font-family: 'SimSun', 'simsun', serif;
                padding: 10px;
                line-height: 1.5;
            }
        """)
        goal_layout.addWidget(goal_label)
        goal_layout.addWidget(self.goal_text)
        experiments_layout.addLayout(goal_layout)
        
        # 添加交互按钮 - 优化布局
        buttons_layout = QVBoxLayout()  # 改为垂直布局
        buttons_layout.setSpacing(10)  # 增加按钮之间的间距
        buttons_layout.setContentsMargins(0, 8, 0, 0)  # 增加上边距
        
        # 上排按钮（报告进度和请求提示）
        top_buttons = QHBoxLayout()
        top_buttons.setSpacing(10)  # 增加按钮间的水平间距
        
        self.report_progress_button = QPushButton("报告进度")
        self.report_progress_button.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 10px;
                font-weight: bold;
                font-family: 'SimSun', 'simsun', serif;
                font-size: 14px;
                min-height: 36px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.report_progress_button.clicked.connect(self.report_progress)
        self.report_progress_button.setEnabled(False)
        
        self.request_hint_button = QPushButton("请求提示")
        self.request_hint_button.setStyleSheet("""
            QPushButton {
                background-color: #9b59b6;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 10px;
                font-weight: bold;
                font-family: 'SimSun', 'simsun', serif;
                font-size: 14px;
                min-height: 36px;
            }
            QPushButton:hover {
                background-color: #8e44ad;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.request_hint_button.clicked.connect(self.request_hint)
        self.request_hint_button.setEnabled(False)
        
        top_buttons.addWidget(self.report_progress_button)
        top_buttons.addWidget(self.request_hint_button)
        buttons_layout.addLayout(top_buttons)
        
        # 下排按钮（重置实验）- 增加间距
        bottom_buttons = QHBoxLayout()
        bottom_buttons.setContentsMargins(0, 5, 0, 0)  # 增加上边距
        
        self.reset_experiment_button = QPushButton("重置实验")
        self.reset_experiment_button.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 10px;
                font-weight: bold;
                font-family: 'SimSun', 'simsun', serif;
                font-size: 14px;
                min-height: 36px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        self.reset_experiment_button.clicked.connect(self.reset_current_experiment)
        self.reset_experiment_button.setEnabled(False)
        
        bottom_buttons.addWidget(self.reset_experiment_button)
        buttons_layout.addLayout(bottom_buttons)
        
        experiments_layout.addLayout(buttons_layout)
        
        toolbar_layout.addWidget(experiments_group)
        
        # 添加组件分组
        components_group = QGroupBox("电路元件")
        components_layout = QGridLayout(components_group)
        components_layout.setSpacing(12)  # 进一步增加组件间距
        components_layout.setContentsMargins(10, 25, 10, 10)  # 调整边距，顶部留更多空间给标题
        
        # 添加组件按钮
        components = ["电源", "开关", "导线", "定值电阻", "滑动变阻器", "电流表", "电压表"]
        for i, component in enumerate(components):
            btn = ComponentButton(component)
            btn.setMinimumSize(120, 38)  # 进一步增加最小大小
            btn.setMaximumSize(130, 38)  # 增加最大大小
            # 更新ComponentButton样式
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #2196F3;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 6px;
                    font-size: 14px;
                    margin: 3px;
                    text-align: center;
                    qproperty-alignment: AlignCenter;
                    font-family: 'SimSun', 'simsun', serif;
                }
                QPushButton:hover {
                    background-color: #1976D2;
                }
                QPushButton:pressed {
                    background-color: #0D47A1;
                }
            """)
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
        
        # 调整分割器初始比例，左侧工具栏宽一些
        self.main_splitter.setSizes([280, self.width() - 580])
        
        # 右侧面板 - AI聊天
        self.chat_panel = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_panel)
        self.chat_layout.setContentsMargins(5, 5, 5, 5)  # 减小边距，让内容区域更大
        self.chat_layout.setSpacing(5)  # 减小间距
        
        # 添加Logo区域
        self.logo_area = QWidget()
        self.logo_layout = QHBoxLayout(self.logo_area)
        self.logo_layout.setContentsMargins(10, 10, 10, 5)  # 减小底部边距
        
        # 添加logo图片
        self.logo_image = QLabel()
        logo_pixmap = QPixmap("logo.png")
        logo_pixmap = logo_pixmap.scaledToHeight(48, Qt.TransformationMode.SmoothTransformation)  # 放大logo
        self.logo_image.setPixmap(logo_pixmap)
        self.logo_image.setFixedSize(48, 48)  # 放大logo区域
        
        self.logo_label = QLabel("AI 物理助手")
        self.logo_label.setStyleSheet("""
            font-size: 22px;  # 放大字体
            font-weight: bold;
            color: #333333;
            font-family: 'SimSun', 'simsun', serif;
        """)
        self.logo_layout.addWidget(self.logo_image)
        self.logo_layout.addWidget(self.logo_label)
        self.logo_layout.addStretch()
        
        # 聊天历史区域
        self.chat_history_container = QWidget()
        self.chat_history_layout = QVBoxLayout(self.chat_history_container)
        self.chat_history_layout.setContentsMargins(0, 0, 0, 0)
        self.chat_history_layout.setSpacing(8)  # 减小消息之间的间距
        # 为聊天历史容器添加样式
        self.chat_history_container.setStyleSheet("""
            QWidget {
                background-color: transparent;
                margin-top: 0px;
            }
        """)
        
        # 使用滚动区域包装聊天历史
        self.chat_scroll_area = QScrollArea()
        self.chat_scroll_area.setWidgetResizable(True)
        self.chat_scroll_area.setWidget(self.chat_history_container)
        self.chat_scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #f9f9f9;
                padding-top: 0px;
                margin-top: 0px;
            }
            QScrollArea > QWidget > QWidget {
                margin-top: 0px;
                padding-top: 0px;
            }
        """)
        
        # 底部输入区域 - 设置为相对较小
        self.input_area = QWidget()
        self.input_area.setMaximumHeight(80)  # 限制最大高度
        
        # 创建相对位置布局
        self.input_area.setLayout(QHBoxLayout())
        self.input_area.layout().setContentsMargins(10, 5, 10, 5)
        self.input_area.layout().setSpacing(0)
        
        # 创建输入框容器
        self.input_container = QWidget()
        self.input_container.setStyleSheet("""
            background-color: #e8e8e8;
            border-radius: 8px;
        """)
        
        # 使用相对布局来放置输入框和按钮
        self.input_layout = QGridLayout(self.input_container)
        self.input_layout.setContentsMargins(2, 2, 2, 2)
        self.input_layout.setSpacing(0)
        
        # 聊天输入
        self.chat_input = QTextEdit()
        self.chat_input.setMinimumHeight(36)
        self.chat_input.setMaximumHeight(70)
        self.chat_input.setPlaceholderText("在这里输入你的问题...")
        self.chat_input.setStyleSheet("""
            QTextEdit {
                border: none;
                border-radius: 6px;
                padding: 8px;
                background-color: #f0f0f0;
                font-family: 'SimSun', 'simsun', serif;
                font-size: 14px;
            }
        """)
        # 设置回车键发送消息
        self.chat_input.installEventFilter(self)
        # 文本变化时更新发送按钮状态
        self.chat_input.textChanged.connect(self.update_send_button_state)
        
        # 发送按钮 - 使用向上箭头
        self.send_button = QPushButton()
        self.send_button.setFixedSize(32, 32)
        self.send_button.clicked.connect(self.send_message)
        self.send_button.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # 初始设置为禁用状态
        self.send_button.setStyleSheet("""
            QPushButton {
                background-color: #CCCCCC;
                color: white;
                border: none;
                border-radius: 16px;
                font-size: 16px;
                font-weight: bold;
                qproperty-text: "↑";
            }
        """)
        self.send_button.setEnabled(False)
        
        # 在网格布局中放置输入框和按钮，按钮在右下角
        self.input_layout.addWidget(self.chat_input, 0, 0, 1, 1)
        self.input_layout.addWidget(self.send_button, 0, 0, 1, 1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        
        # 添加输入容器到输入区域
        self.input_area.layout().addWidget(self.input_container)
        
        # 添加所有部件到聊天面板，使用较小的输入区域
        self.chat_layout.addWidget(self.logo_area, 0)  # 固定大小
        self.chat_layout.addWidget(self.chat_scroll_area, 1)  # 占据剩余空间
        self.chat_layout.addWidget(self.input_area, 0)  # 固定大小
        
        # 将面板添加到分割器
        self.main_splitter.addWidget(self.chat_panel)
        
        # 添加一条欢迎消息 - 修改为直接调用而不是使用计时器延迟
        self.add_message_to_chat("assistant", "你好！我是物理电学实验AI助手，有关于电路实验的问题都可以问我。")
        
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
                font-family: 'SimSun', 'simsun', serif;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px;
                color: #333333;
                font-family: 'SimSun', 'simsun', serif;
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
                font-family: 'SimSun', 'simsun', serif;
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
                font-family: 'SimSun', 'simsun', serif;
            }
            QLineEdit:focus {
                border-color: #4CAF50;
            }
            QLabel {
                color: #333333;
                font-family: 'SimSun', 'simsun', serif;
            }
            QComboBox {
                color: #333333;
                background-color: white;
                border: 1px solid #ccc;
                border-radius: 3px;
                padding: 3px;
                min-height: 24px;
                font-family: 'SimSun', 'simsun', serif;
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
            QTextEdit {
                font-family: 'SimSun', 'simsun', serif;
            }
            QScrollArea {
                font-family: 'SimSun', 'simsun', serif;
            }
        """)
        
    def showEvent(self, event):
        """窗口显示时调整分割器比例"""
        super().showEvent(event)
        # 确保在窗口显示后再次设置分割比例
        QTimer.singleShot(100, self.adjust_splitter_sizes)
    
    def adjust_splitter_sizes(self):
        """调整分割器大小比例"""
        total_width = self.width()
        left_width = 280  # 左侧工具栏宽度增加
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
        """清空当前电路（带确认对话框）"""
        reply = QMessageBox.question(
            self,
            "确认",
            "确定要清空当前电路吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.clear_circuit_silent()
            QMessageBox.information(self, "成功", "电路已清空！")
    
    def clear_circuit_silent(self):
        """无需确认直接清空电路"""
        # 清空工作区
        self.work_area.clear_circuit()
        
        # 如果有选择的实验，重新启用实验列表
        if self.current_experiment:
            self.experiment_list.setEnabled(True)
            self.current_experiment = None
            self.experiment_status.setText("当前未选择实验")
            self.goal_text.clear()
            self.report_progress_button.setEnabled(False)
            self.request_hint_button.setEnabled(False)
            self.reset_experiment_button.setEnabled(False)
            
        # 更新状态栏
        self.statusBar().showMessage("电路已清空")
    
    def start_simulation(self):
        try:
            # 重置所有组件的电气参数
            for comp in self.work_area.circuit.components:
                comp.voltage = 0
                comp.current = 0
            
            # 更新显示
            self.work_area.update()
            
            # 调用WorkArea的start_simulation方法
            voltage = 5.0  # 默认电压值
            # 查找电源组件获取电压值
            for comp in self.work_area.circuit.components:
                if comp.name == "电源":
                    voltage = comp.properties.get("电压值", 5.0)
                    break
                    
            # 执行电路计算
            result = self.work_area.start_simulation(voltage)
            
            # 更新测量结果
            if result:
                self.update_measurements()
            
        except Exception as e:
            # 添加异常处理
            print(f"仿真启动错误: {str(e)}")
            logger.error(f"仿真启动错误: {str(e)}", exc_info=True)
            QMessageBox.warning(self, "仿真错误", f"启动仿真时出现错误：{str(e)}")
    
    def update_simulation(self):
        """手动触发电路重新计算"""
        if not self.work_area.simulation_running:
            return
            
        self.work_area.update_simulation()
        
        # 更新测量结果
        self.update_measurements()
        
    def update_measurements(self):
        """更新测量结果显示"""
        results = []
        for comp in self.work_area.circuit.components:
            if comp.name in ["电流表", "电压表"]:
                if comp.name == "电流表":
                    results.append(f"电流表读数: {comp.current:.4f}A")
                else:
                    results.append(f"电压表读数: {comp.voltage:.4f}V")
                    
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
            # 更新测量结果
            self.update_measurements()

    def stop_simulation(self):
        """停止仿真"""
        try:
            # 调用WorkArea的stop_simulation方法
            self.work_area.stop_simulation()
            
            # 更新按钮状态
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.reset_button.setEnabled(True)
            
            # 更新状态显示
            self.simulation_status_label.setText(f"仿真状态: {self.work_area.simulation_status}")
            
        except Exception as e:
            logger.error(f"停止仿真出错: {str(e)}", exc_info=True)
            QMessageBox.warning(self, "仿真错误", f"停止仿真时出现错误：{str(e)}")
    
    def reset_simulation(self):
        """重置仿真"""
        try:
            # 调用WorkArea的reset_simulation方法
            self.work_area.reset_simulation()
            
            # 更新按钮状态
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.reset_button.setEnabled(False)
            
            # 更新状态显示
            self.simulation_status_label.setText(f"仿真状态: {self.work_area.simulation_status}")
            self.measurement_label.setText("测量结果: ")
            
        except Exception as e:
            logger.error(f"重置仿真出错: {str(e)}", exc_info=True)
            QMessageBox.warning(self, "仿真错误", f"重置仿真时出现错误：{str(e)}")

    def save_circuit_to_json(self):
        try:
            options = QFileDialog.Option(0)
            file_name, _ = QFileDialog.getSaveFileName(
                self, "保存电路", "", "JSON Files (*.json)", options=options
            )
            if file_name:
                if not file_name.endswith('.json'):
                    file_name += '.json'
                
                # 使用 work_area 的 circuit 对象来获取电路数据，传入场景
                circuit_data = self.work_area.circuit.to_dict(self.work_area.scene())
                
                with open(file_name, 'w') as f:
                    json.dump(circuit_data, f, indent=4)
                
                self.statusBar().showMessage(f"电路已保存到 {file_name}", 5000)
                
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"保存电路失败: {str(e)}")
    
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
        
        # 添加用户消息到聊天界面
        self.add_message_to_chat("user", user_message)
        self.chat_input.clear()
        # 清空输入框后更新按钮状态
        self.update_send_button_state()
        
        try:
            # 导入test_api模块
            from test_api import LLMClient, LLMConfig, load_config
            
            # 加载配置
            config = load_config()
            
            # 创建客户端
            llm_client = LLMClient(config)
            
            # 使用完善后的circuit.to_dict()方法获取电路数据，传入场景参数
            circuit_data = self.work_area.circuit.to_dict(self.work_area.scene())
            circuit_json = json.dumps(circuit_data, ensure_ascii=False, indent=2)
            
            # 构建提示词
            system_prompt = """你是一位专业的物理电学实验助手。请帮助用户理解和构建电路实验。
            你需要：
            1. 分析当前电路的组成和连接
            2. 提供专业的建议和指导
            3. 回答用户的具体问题
            4. 指出可能存在的问题和改进建议"""
            
            # 构建带有完整电路上下文的提示词
            prompt = f"""
用户问题: {user_message}

当前电路信息:
{circuit_json}

请根据以上电路信息回答用户问题。如果需要更多信息，请明确指出。
"""
            
            # 显示正在获取回复的提示
            self.add_thinking_message()
            QApplication.processEvents()
            
            # 准备流式响应处理
            def handle_stream_chunk(chunk):
                # 更新AI消息内容
                if hasattr(self, 'ai_message_label') and self.ai_message_label:
                    # 如果是第一次收到内容，更改气泡样式为正式回复样式
                    if not hasattr(self, '_response_started') or not self._response_started:
                        self._response_started = True
                        # 更新气泡样式为回复样式
                        self.ai_message_bubble.setStyleSheet(f"""
                            background-color: {self.get_bubble_color("assistant")};
                            border-radius: 8px;
                            padding: 2px;
                        """)
                        # 更新文本样式
                        self.ai_message_label.setStyleSheet(f"""
                            font-family: 'SimSun', 'simsun', serif;
                            font-size: 14px;
                            color: {self.get_text_color("assistant")};
                            background: transparent;
                            line-height: 1.5;
                        """)
                    
                    # 更新AI消息内容
                    html_content = chunk.replace("\n", "<br>")
                    self.ai_message_label.setText(html_content)
                    # 滚动到底部
                    self.chat_scroll_area.verticalScrollBar().setValue(
                        self.chat_scroll_area.verticalScrollBar().maximum())
                QApplication.processEvents()  # 刷新UI
            
            # 使用流式API调用
            try:
                # 执行流式调用
                self.stream_llm_request(
                    llm_client, 
                    prompt, 
                    system_prompt, 
                    handle_stream_chunk
                )
                # 清理临时标记
                if hasattr(self, '_response_started'):
                    delattr(self, '_response_started')
            except Exception as e:
                # 移除"正在思考"消息
                self.remove_thinking_message()
                # 清理临时标记
                if hasattr(self, '_response_started'):
                    delattr(self, '_response_started')
                # 显示错误信息
                error_msg = f"流式API请求失败: {str(e)}"
                self.add_system_message("错误", error_msg, "red")
            
        except ImportError as e:
            # 移除"正在思考"消息
            self.remove_thinking_message()
            error_msg = "无法导入test_api模块，请确保已安装必要的库"
            self.add_system_message("错误", error_msg, "red")
            QMessageBox.critical(self, "模块错误", error_msg)
            
        except Exception as e:
            # 移除"正在思考"消息
            self.remove_thinking_message()
            error_msg = f"API请求失败: {str(e)}"
            self.add_system_message("错误", error_msg, "red")
            QMessageBox.critical(self, "API错误", f"调用API时出错:\n{str(e)}")
    
    def stream_llm_request(self, llm_client, prompt, system_prompt, callback_fn):
        """执行流式LLM请求"""
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ]
            
            # 流式响应
            full_response = ""
            
            # 直接使用OpenAI客户端进行流式请求
            stream = llm_client.client.chat.completions.create(
                model=llm_client.config.default_model,
                messages=messages,
                temperature=llm_client.config.default_temperature,
                stream=True  # 启用流式输出
            )
            
            # 处理流式响应
            for chunk in stream:
                if hasattr(chunk, 'choices') and chunk.choices:
                    delta = chunk.choices[0].delta
                    if hasattr(delta, 'content') and delta.content:
                        content = delta.content
                        full_response += content
                        callback_fn(full_response)
            
            # 确保最后一次更新
            if full_response:
                callback_fn(full_response)
                
            return full_response
            
        except Exception as e:
            logger.error(f"流式请求出错: {str(e)}")
            raise
    
    def create_empty_ai_message(self):
        """[已废弃] 创建空的AI消息气泡，准备流式填充内容"""
        # 此方法已废弃，我们现在改用directly modifying the thinking message
        # 保留此方法仅为了避免潜在的引用错误
        return None
    
    def update_ai_message_content(self, message_widget, content):
        """[已废弃] 更新AI消息内容"""
        # 此方法已废弃，我们现在直接更新ai_message_label
        # 保留此方法仅为了避免潜在的引用错误
        pass

    def get_avatar_color(self, role):
        """根据角色获取头像背景颜色"""
        if role == "user":
            return "#5E5EE9"  # 用户头像颜色 - 蓝色
        else:
            return "#8E44AD"  # AI助手头像颜色 - 紫色
            
    def get_avatar_text(self, role):
        """根据角色获取头像文本"""
        if role == "user":
            return "用"
        else:
            return "AI"
            
    def get_bubble_color(self, role):
        """根据角色获取气泡背景颜色"""
        if role == "user":
            return "#ECF0F1"  # 用户气泡 - 浅灰色
        else:
            return "#F4EEFF"  # AI助手气泡 - 浅紫色
            
    def get_text_color(self, role):
        """根据角色获取文本颜色"""
        if role == "user":
            return "#2C3E50"  # 用户文本 - 深灰色
        else:
            return "#2C3E50"  # AI助手文本 - 深灰色

    def eventFilter(self, obj, event):
        """事件过滤器，处理输入框的按键事件"""
        if obj is self.chat_input and event.type() == event.Type.KeyPress:
            if event.key() == Qt.Key.Key_Return and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                # 回车键发送消息，Shift+回车是换行
                self.send_message()
                return True
        return super().eventFilter(obj, event)

    def toggle_grid(self, checked):
        """切换网格显示状态"""
        self.work_area.show_grid = checked
        self.work_area.update()
        
    def toggle_snap(self, checked):
        """切换网格吸附状态"""
        self.work_area.snap_to_grid = checked
        self.work_area.update()

    def update_send_button_state(self):
        """根据输入框内容更新发送按钮状态"""
        has_text = len(self.chat_input.toPlainText().strip()) > 0
        
        if has_text:
            # 有文本时启用按钮，设置为紫色
            self.send_button.setEnabled(True)
            self.send_button.setStyleSheet("""
                QPushButton {
                    background-color: #5E35B1;
                    color: white;
                    border: none;
                    border-radius: 16px;
                    font-size: 16px;
                    font-weight: bold;
                    qproperty-text: "↑";
                }
                QPushButton:hover {
                    background-color: #4527A0;
                }
                QPushButton:pressed {
                    background-color: #311B92;
                }
            """)
        else:
            # 无文本时禁用按钮，设置为灰色
            self.send_button.setEnabled(False)
            self.send_button.setStyleSheet("""
                QPushButton {
                    background-color: #CCCCCC;
                    color: white;
                    border: none;
                    border-radius: 16px;
                    font-size: 16px;
                    font-weight: bold;
                    qproperty-text: "↑";
                }
            """)

    def add_message_to_chat(self, role, message):
        """添加消息到聊天界面"""
        # 创建消息容器
        msg_container = QWidget()
        msg_layout = QHBoxLayout(msg_container)
        msg_layout.setContentsMargins(5, 3, 5, 3)  # 减小上下边距
        
        # 设置头像和样式
        avatar_label = QLabel()
        avatar_label.setFixedSize(36, 36)
        avatar_label.setStyleSheet(f"""
            background-color: {self.get_avatar_color(role)};
            border-radius: 18px;
            color: white;
            font-weight: bold;
            qproperty-alignment: AlignCenter;
            font-family: 'SimSun', 'simsun', serif;
        """)
        avatar_label.setText(self.get_avatar_text(role))
        
        # 消息气泡
        message_bubble = QWidget()
        bubble_layout = QVBoxLayout(message_bubble)
        bubble_layout.setContentsMargins(12, 8, 12, 8)  # 减小上下边距
        
        message_label = QLabel(message)
        message_label.setWordWrap(True)
        message_label.setTextFormat(Qt.TextFormat.RichText)
        message_label.setOpenExternalLinks(True)
        message_label.setStyleSheet(f"""
            font-family: 'SimSun', 'simsun', serif;
            font-size: 14px;
            color: {self.get_text_color(role)};
            background: transparent;
            line-height: 1.5;
        """)
        
        bubble_layout.addWidget(message_label)
        
        # 设置消息气泡样式
        message_bubble.setStyleSheet(f"""
            background-color: {self.get_bubble_color(role)};
            border-radius: 8px;
            padding: 2px;
        """)
        
        # 根据角色调整布局
        if role == "user":
            msg_layout.addStretch()
            msg_layout.addWidget(message_bubble)
            msg_layout.addWidget(avatar_label)
        else:
            msg_layout.addWidget(avatar_label)
            msg_layout.addWidget(message_bubble)
            msg_layout.addStretch()
        
        # 添加到聊天历史
        self.chat_history_layout.addWidget(msg_container)
        
        # 滚动到底部
        QTimer.singleShot(100, lambda: self.chat_scroll_area.verticalScrollBar().setValue(
            self.chat_scroll_area.verticalScrollBar().maximum()))

    def add_thinking_message(self):
        """添加正在思考的消息提示（这个组件后续会被直接用于显示回复）"""
        self.ai_message_container = QWidget()
        thinking_layout = QHBoxLayout(self.ai_message_container)
        thinking_layout.setContentsMargins(5, 5, 5, 5)
        
        # 设置头像
        avatar_label = QLabel()
        avatar_label.setFixedSize(36, 36)
        avatar_label.setStyleSheet("""
            background-color: #8E44AD;
            border-radius: 18px;
            color: white;
            font-weight: bold;
            qproperty-alignment: AlignCenter;
            font-family: 'SimSun', 'simsun', serif;
        """)
        avatar_label.setText("AI")
        
        # 消息气泡
        self.ai_message_bubble = QWidget()
        bubble_layout = QVBoxLayout(self.ai_message_bubble)
        bubble_layout.setContentsMargins(12, 10, 12, 10)
        
        # 创建标签用于显示内容
        self.ai_message_label = QLabel("正在思考...")
        self.ai_message_label.setWordWrap(True)
        self.ai_message_label.setTextFormat(Qt.TextFormat.RichText)
        self.ai_message_label.setOpenExternalLinks(True)
        self.ai_message_label.setStyleSheet("""
            font-family: 'SimSun', 'simsun', serif;
            font-size: 14px;
            color: #666666;
            background: transparent;
            line-height: 1.5;
        """)
        
        bubble_layout.addWidget(self.ai_message_label)
        
        # 设置气泡样式
        self.ai_message_bubble.setStyleSheet("""
            background-color: #f1f0f0;
            border-radius: 8px;
            padding: 2px;
        """)
        
        thinking_layout.addWidget(avatar_label)
        thinking_layout.addWidget(self.ai_message_bubble)
        thinking_layout.addStretch()
        
        # 添加到聊天历史
        self.chat_history_layout.addWidget(self.ai_message_container)
        
        # 滚动到底部
        QTimer.singleShot(100, lambda: self.chat_scroll_area.verticalScrollBar().setValue(
            self.chat_scroll_area.verticalScrollBar().maximum()))
    
    def remove_thinking_message(self):
        """移除思考中的消息"""
        if hasattr(self, 'ai_message_container') and self.ai_message_container:
            self.ai_message_container.deleteLater()
            self.ai_message_container = None
            self.ai_message_bubble = None
            self.ai_message_label = None
    
    def add_system_message(self, title, message, color="blue"):
        """添加系统消息"""
        system_container = QWidget()
        system_layout = QVBoxLayout(system_container)
        system_layout.setContentsMargins(5, 5, 5, 5)
        
        system_label = QLabel(f"<b>{title}:</b> {message}")
        system_label.setWordWrap(True)
        system_label.setStyleSheet(f"""
            font-family: 'SimSun', 'simsun', serif;
            font-size: 13px;
            color: {color};
            background-color: #f9f9f9;
            border-radius: 6px;
            padding: 8px;
            border: 1px solid #eeeeee;
        """)
        
        system_layout.addWidget(system_label)
        
        # 添加到聊天历史
        self.chat_history_layout.addWidget(system_container)
        
        # 滚动到底部
        QTimer.singleShot(100, lambda: self.chat_scroll_area.verticalScrollBar().setValue(
            self.chat_scroll_area.verticalScrollBar().maximum()))

    def handle_experiment_selected(self, item):
        if not item:
            return
            
        # 获取当前选择的实验
        experiment_index = self.experiment_list.currentIndex().row()
        self.current_experiment = self.experiments[experiment_index]
        
        # 更新实验目标显示
        self.goal_text.setText(self.current_experiment['goal'])
        
        # 更新状态显示
        self.experiment_status.setText(f"当前实验：{self.current_experiment['name']}")
        
        # 清空当前画布
        self.work_area.clear_circuit()
        
        # 放置实验中定义的组件
        if 'components' in self.current_experiment:
            for comp_data in self.current_experiment['components']:
                # 获取组件类型和映射到程序内部名称
                comp_type = experiment_manager.get_component_mapping(comp_data['type'])
                x = comp_data['x']
                y = comp_data['y']
                properties = comp_data.get('properties', {})
                
                # 创建组件并添加到工作区
                component = Component(comp_type)
                
                # 设置组件属性
                for prop_name, prop_value in properties.items():
                    component.set_property(prop_name, prop_value)
                
                # 添加到场景中
                component.setPos(x, y)
                self.work_area.scene().addItem(component)
                self.work_area.components.append(component)
                
                # 通知用户
                logger.debug(f"已放置组件: {comp_type} 在位置 ({x}, {y})")
        
        # 显示实验描述和提示
        description = self.current_experiment.get('description', '')
        missing_elements = self.current_experiment.get('missing_elements', [])
        
        # 将未知类型映射为中文名称
        missing_elements_cn = [experiment_manager.get_component_mapping(elem) for elem in missing_elements]
        
        # 构建提示信息
        message = f"<b>{self.current_experiment['name']}</b><br><br>"
        message += f"{description}<br><br>"
        message += f"<b>需要添加的元件:</b> {', '.join(missing_elements_cn)}<br><br>"
        message += "请完成电路搭建，点击「报告进度」查看分析，或点击「请求提示」获取帮助。"
        
        # 显示消息框
        QMessageBox.information(self, "实验已加载", message)
        
        # 启用交互按钮
        self.report_progress_button.setEnabled(True)
        self.request_hint_button.setEnabled(True)
        self.reset_experiment_button.setEnabled(True)
        
        # 禁用实验列表，直到重置实验
        self.experiment_list.setEnabled(False)
        
        # 在状态栏显示当前实验
        self.statusBar().showMessage(f"正在进行实验：{self.current_experiment['name']}")

    def reset_current_experiment(self):
        """重置当前实验到初始状态"""
        if not self.current_experiment:
            return
            
        reply = QMessageBox.question(
            self,
            "确认重置",
            "确定要重置当前实验吗？这将清除您所做的所有更改。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # 保存当前实验的索引
            current_index = self.experiment_list.currentIndex().row()
            
            # 清空画布
            self.work_area.clear_circuit()
            
            # 重新启用实验列表（它会在handle_experiment_selected中被再次禁用）
            self.experiment_list.setEnabled(True)
            
            # 重新加载相同的实验
            self.experiment_list.setCurrentRow(current_index)
            
            # 提示用户
            QMessageBox.information(self, "实验已重置", "实验已恢复到初始状态。")
            
    def refresh_experiments(self):
        """刷新实验列表"""
        # 启用实验列表
        self.experiment_list.setEnabled(True)
        
        # 清空当前实验
        self.current_experiment = None
        
        # 更新状态显示
        self.experiment_status.setText("当前未选择实验")
        self.goal_text.clear()
        
        # 禁用交互按钮
        self.report_progress_button.setEnabled(False)
        self.request_hint_button.setEnabled(False)
        self.reset_experiment_button.setEnabled(False)
        
        # 重新加载实验列表
        self.experiments = experiment_manager.load_experiments(self.experiment_file)
        self.populate_experiment_list()
        
        # 清空画布
        self.clear_circuit()
        
        # 更新状态栏
        self.statusBar().showMessage("实验列表已刷新")
        
    def serialize_circuit(self):
        """
        序列化当前画布上的电路状态为文本描述
        
        Returns:
            str: 电路状态的文本描述
        """
        result = {}
        
        # 获取所有组件
        components = []
        for component in self.work_area.components:
            comp_dict = {
                "type": component.name,
                "position": (component.pos().x(), component.pos().y()),
                "properties": component.properties
            }
            components.append(comp_dict)
        
        # 获取所有导线
        wires = []
        for item in self.work_area.scene().items():
            if isinstance(item, Wire):
                wire_dict = {
                    "start": (item.start_pos.x(), item.start_pos.y()),
                    "end": (item.end_pos.x(), item.end_pos.y()),
                    "source_component": item.source_component.name if item.source_component else None,
                    "target_component": item.target_component.name if item.target_component else None
                }
                wires.append(wire_dict)
        
        result["components"] = components
        result["wires"] = wires
        
        # 转换为文本描述
        text_description = "当前电路状态:\n\n"
        
        # 描述组件
        text_description += "组件列表:\n"
        for i, comp in enumerate(components):
            text_description += f"{i+1}. {comp['type']} - 位置: ({comp['position'][0]:.1f}, {comp['position'][1]:.1f})"
            
            # 添加属性描述
            if comp['properties']:
                text_description += ", 属性: "
                props = []
                for k, v in comp['properties'].items():
                    props.append(f"{k}={v}")
                text_description += ", ".join(props)
            
            text_description += "\n"
        
        # 描述连接
        text_description += "\n连接情况:\n"
        for i, wire in enumerate(wires):
            source = wire['source_component'] or "未连接"
            target = wire['target_component'] or "未连接"
            text_description += f"{i+1}. {source} -> {target}\n"
        
        return text_description
    
    def report_progress(self):
        """提交当前电路进度，获取大模型反馈"""
        if not self.current_experiment:
            QMessageBox.warning(self, "警告", "请先选择一个实验!")
            return
        
        # 获取当前电路状态
        circuit_description = self.serialize_circuit()
        
        # 构建提交给大模型的提示信息
        experiment_name = self.current_experiment['name']
        experiment_goal = self.current_experiment['goal']
        
        prompt = f"""
        这是一个中小学物理电学实验中的 '{experiment_name}' 实验。

        实验目标: {experiment_goal}

        学生当前搭建的电路情况:
        {circuit_description}

        请分析学生当前的电路状态，评估完成度，提供以下反馈:
        1. 实验进展: 电路已经完成了哪些部分，还缺少哪些部分?
        2. 评估: 当前电路是否可以实现实验目标? 如果不能，原因是什么?
        3. 鼓励性建议: 针对学生当前的进度，提供具体、鼓励性的下一步指导。
        4. 物理知识点: 简要介绍实验中涉及的1-2个物理知识点，帮助学生理解。

        请用中文回答，语言要友好，适合中小学生理解。
        """
        
        # 调用现有的LLM请求函数
        thinking_message = self.add_thinking_message()
        
        try:
            # 添加加载中的消息
            self.add_system_message("进度分析中", "正在分析您的电路...", "blue")
            
            # 使用现有的API调用函数发送请求
            self.stream_llm_request(
                None,  # LLM客户端在原方法中创建
                prompt,
                "你是一位资深的中小学物理老师，擅长电学实验教学。你的任务是分析学生的电路实验状态，给予鼓励性的反馈和指导。",
                lambda message: self.update_ai_message_content(thinking_message, message)
            )
        except Exception as e:
            self.remove_thinking_message()
            self.add_system_message("错误", f"分析失败: {str(e)}", "red")
            logger.error(f"调用大模型API时出错: {str(e)}", exc_info=True)
    
    def request_hint(self):
        """请求大模型提供针对当前实验的提示"""
        if not self.current_experiment:
            QMessageBox.warning(self, "警告", "请先选择一个实验!")
            return
        
        # 获取当前电路状态
        circuit_description = self.serialize_circuit()
        
        # 构建提交给大模型的提示信息
        experiment_name = self.current_experiment['name']
        experiment_goal = self.current_experiment['goal']
        missing_elements = self.current_experiment.get('missing_elements', [])
        missing_elements_cn = [experiment_manager.get_component_mapping(elem) for elem in missing_elements]
        hints = self.current_experiment.get('hints', [])
        
        prompt = f"""
        这是一个中小学物理电学实验中的 '{experiment_name}' 实验。

        实验目标: {experiment_goal}

        学生当前搭建的电路情况:
        {circuit_description}

        实验提示信息:
        - 这个实验可能缺少以下元件: {', '.join(missing_elements_cn)}
        - 可用的实验提示: {' '.join(hints) if hints else '无'}

        请根据以上信息，提供一个针对性的提示，帮助学生继续完成实验。提示应当:
        1. 明确指出下一步应当添加什么元件或如何连接
        2. 解释为什么需要这样做
        3. 不要直接给出完整解决方案，而是引导学生思考
        4. 如果发现电路有问题，指出问题所在并提供修正建议

        请用中文回答，语言要简洁清晰，适合中小学生理解。
        """
        
        # 调用现有的LLM请求函数
        thinking_message = self.add_thinking_message()
        
        try:
            # 添加加载中的消息
            self.add_system_message("提示生成中", "正在为您生成提示...", "purple")
            
            # 使用现有的API调用函数发送请求
            self.stream_llm_request(
                None,  # LLM客户端在原方法中创建
                prompt,
                "你是一位资深的中小学物理老师，擅长电学实验教学。你的任务是为学生提供有帮助的提示，引导他们完成电路实验。",
                lambda message: self.update_ai_message_content(thinking_message, message)
            )
        except Exception as e:
            self.remove_thinking_message()
            self.add_system_message("错误", f"获取提示失败: {str(e)}", "red")
            logger.error(f"调用大模型API时出错: {str(e)}", exc_info=True)

    def populate_experiment_list(self):
        """填充实验列表"""
        self.experiment_list.clear()
        for experiment in self.experiments:
            self.experiment_list.addItem(experiment['name'])

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec()) 