# 物理电学实验仿真软件

这是一个专为物理教学和学习设计的电学实验仿真平台，基于Windows系统开发。该软件通过直观的图形界面，让用户能够轻松构建各种电路并进行实时仿真，帮助理解电学原理和实验现象。

## 版权声明
- 版权和api仅供本大创小组成员所有，请务必做好隐私守护工作

## 核心功能

- **丰富的元器件库**：
  - 基础元件：电源（直流、交流）、开关、导线、接地
  - 电阻元件：定值电阻、滑动变阻器、热敏电阻、光敏电阻
  - 测量仪表：电流表、电压表、万用表、示波器
  - 半导体元件：二极管、三极管、电容、电感
  - 特殊元件：灯泡、蜂鸣器、继电器等

- **交互式电路设计**：
  - 拖拽式界面，直观构建电路
  - 元件旋转、调整尺寸等便捷操作
  - 快速连线和节点识别功能
  - 电路存储与加载功能

- **高精度仿真引擎**：
  - 实时计算电流、电压分布
  - 动态显示电路工作状态
  - 支持瞬态分析和稳态分析
  - 准确模拟各种物理现象（如短路保护）

- **数据分析工具**：
  - 实时数据曲线绘制
  - 测量结果记录与导出
  - 电路参数分析报告

## 系统要求

- Windows 10/11 操作系统
- Python 3.8 或更高版本
- 4GB 以上内存
- 500MB 可用磁盘空间

## 安装步骤

1. **下载与准备**：
   - 克隆或下载本仓库到本地
   - 确保已安装Python 3.8+和pip

2. **安装依赖**：
   ```
   pip install -r requirements.txt
   ```

3. **启动程序**：
   ```
   python main.py
   ```

## 使用指南

### 基础操作

1. **创建新电路**：
   - 启动软件后，点击"文件" > "新建"创建空白电路
   - 或选择"模板"菜单加载预设电路

2. **添加元件**：
   - 从左侧元件库中选择所需元件
   - 将元件拖拽到工作区的适当位置
   - 双击元件可修改其参数（如电阻值、电压值等）

3. **连接电路**：
   - 点击元件上的连接点，然后拖动到目标连接点完成导线连接
   - 也可使用"自动连线"功能，选择两个连接点后右键选择"连接"

4. **运行仿真**：
   - 点击工具栏中的"开始仿真"按钮
   - 使用开关元件控制电路状态
   - 通过测量仪表观察电路工作参数

### 高级功能

1. **参数调节**：
   - 对于可调元件（如滑动变阻器），可通过滑块实时调节参数
   - 支持键盘精确输入数值

2. **故障分析**：
   - "电路诊断"功能可自动检测常见问题
   - 短路、开路检测与提示

3. **数据导出**：
   - 点击"导出数据"保存测量结果到CSV文件
   - "截图"功能可保存当前电路图像

4. **电路保存与加载**：
   - "保存"电路到项目文件(.pec格式)
   - "加载"已保存的电路继续实验

## 常见问题解答

1. **Q: 电路无法正常工作？**
   A: 检查是否存在元件连接不当或参数设置不合理，使用"电路诊断"功能查找问题。

2. **Q: 如何创建复杂电路？**
   A: 推荐先绘制简图，从电源开始逐步构建，使用"分组"功能管理复杂部分。

3. **Q: 如何设计定制实验？**
   A: 使用"实验模式"，可以预设参数变化和测量点，创建完整实验流程。

## 技术支持

如有任何问题或建议，请通过以下方式联系我们：
- 提交GitHub Issue
- 发送邮件至：1516924835@qq.com
- 联系微信：zr15156555878

## 开发技术

- 前端界面：PyQt6
- 仿真引擎：NumPy, SciPy
- 图形渲染：Matplotlib

## 贡献指南

欢迎参与项目开发！请查看`CONTRIBUTING.md`了解如何提交代码和报告问题。

## 许可证

本项目采用MIT许可证，详情请参阅`LICENSE`文件。 