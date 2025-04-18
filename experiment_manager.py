import os
import json
import logging
from typing import List, Dict, Any, Optional

# 获取当前已经配置的logger
logger = logging.getLogger('CircuitSimulator')

def load_experiments(filepath: str) -> List[Dict[str, Any]]:
    """
    从JSON文件加载实验列表
    
    Args:
        filepath: 实验配置文件的路径
        
    Returns:
        实验配置列表，每个实验是一个字典
        
    Raises:
        FileNotFoundError: 如果文件不存在
        json.JSONDecodeError: 如果JSON格式无效
    """
    try:
        # 确保文件存在
        if not os.path.exists(filepath):
            logger.error(f"实验配置文件不存在: {filepath}")
            return []
        
        # 读取并解析JSON文件
        with open(filepath, 'r', encoding='utf-8') as f:
            experiments = json.load(f)
            
        # 验证实验配置的有效性
        valid_experiments = []
        for exp in experiments:
            if validate_experiment(exp):
                valid_experiments.append(exp)
            else:
                logger.warning(f"实验配置无效: {exp.get('name', '未命名')}")
                
        logger.info(f"成功加载了 {len(valid_experiments)} 个实验")
        return valid_experiments
    
    except json.JSONDecodeError as e:
        logger.error(f"解析实验配置文件时出错: {str(e)}")
        return []
    except Exception as e:
        logger.error(f"加载实验配置时发生错误: {str(e)}")
        return []

def validate_experiment(experiment: Dict[str, Any]) -> bool:
    """
    验证实验配置的有效性
    
    Args:
        experiment: 实验配置字典
        
    Returns:
        bool: 配置是否有效
    """
    # 检查必要字段
    required_fields = ["name", "description", "goal"]
    for field in required_fields:
        if field not in experiment:
            logger.warning(f"实验缺少必要字段: {field}")
            return False
            
    # 验证组件配置
    if "components" in experiment:
        for comp in experiment["components"]:
            if "type" not in comp or "x" not in comp or "y" not in comp:
                logger.warning(f"实验 '{experiment['name']}' 中的组件配置无效")
                return False
    
    return True

def get_experiment_by_name(experiments: List[Dict[str, Any]], name: str) -> Optional[Dict[str, Any]]:
    """
    通过名称查找实验
    
    Args:
        experiments: 实验列表
        name: 实验名称
        
    Returns:
        找到的实验配置，如果未找到则返回None
    """
    for experiment in experiments:
        if experiment.get("name") == name:
            return experiment
    return None

def get_component_mapping(component_type: str) -> str:
    """
    将配置文件中的组件类型映射到程序中的组件类名
    
    Args:
        component_type: 配置中的组件类型
        
    Returns:
        程序中对应的组件类名
    """
    # 组件类型映射表
    mapping = {
        "DCVoltageSource": "电源",
        "Lamp": "灯泡",
        "Switch": "开关",
        "Resistor": "定值电阻",
        "Potentiometer": "滑动变阻器",
        "Ammeter": "电流表",
        "Voltmeter": "电压表",
        "Wire": "导线"
    }
    
    return mapping.get(component_type, component_type)

def get_experiments_by_difficulty(experiments: List[Dict[str, Any]], difficulty: str) -> List[Dict[str, Any]]:
    """
    按难度级别筛选实验
    
    Args:
        experiments: 实验列表
        difficulty: 难度级别 ('初级', '中级', '高级')
        
    Returns:
        符合指定难度的实验列表
    """
    return [exp for exp in experiments if exp.get('difficulty') == difficulty]

def evaluate_experiment_progress(experiment: Dict[str, Any], circuit_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    评估实验完成进度
    
    Args:
        experiment: 实验配置
        circuit_data: 当前电路状态数据
        
    Returns:
        评估结果，包含完成度、缺少的元件等信息
    """
    result = {
        "completion_percentage": 0,  # 完成百分比
        "missing_components": [],    # 缺少的组件
        "incorrect_connections": [], # 错误的连接
        "feedback": ""               # 反馈信息
    }
    
    # 检查必要组件是否存在
    required_components = []
    if "components" in experiment:
        required_components = [comp["type"] for comp in experiment["components"]]
    
    if "missing_elements" in experiment:
        required_components.extend(experiment["missing_elements"])
    
    # 检查当前电路中的组件
    current_components = []
    if "components" in circuit_data:
        current_components = [comp.get("type") for comp in circuit_data["components"]]
    
    # 找出缺少的组件
    for comp_type in required_components:
        # 将组件类型映射为显示名称
        display_name = get_component_mapping(comp_type)
        if comp_type not in current_components and display_name not in current_components:
            result["missing_components"].append(display_name)
    
    # 计算完成度
    total_required = len(required_components)
    missing_count = len(result["missing_components"])
    
    if total_required > 0:
        completion = (total_required - missing_count) / total_required
        result["completion_percentage"] = int(completion * 100)
    
    # 生成反馈信息
    if result["completion_percentage"] == 100:
        result["feedback"] = "实验电路已完全搭建，请进行仿真测试验证结果。"
    elif result["completion_percentage"] >= 80:
        result["feedback"] = f"实验即将完成，还缺少: {', '.join(result['missing_components'])}。"
    elif result["completion_percentage"] >= 50:
        result["feedback"] = f"实验已完成一半，继续加油！缺少: {', '.join(result['missing_components'])}。"
    else:
        result["feedback"] = "实验刚开始，请按照实验目标继续搭建电路。"
    
    return result

def create_experiment_template(name: str, difficulty: str = "中级") -> Dict[str, Any]:
    """
    创建新的实验模板
    
    Args:
        name: 实验名称
        difficulty: 难度级别
        
    Returns:
        新的实验配置模板
    """
    return {
        "name": name,
        "description": "请在此处添加实验描述",
        "components": [],
        "missing_elements": [],
        "goal": "请在此处设置实验目标",
        "hints": ["提示1", "提示2", "提示3"],
        "evaluation_criteria": ["标准1", "标准2", "标准3"],
        "difficulty": difficulty
    }

def save_experiment(experiment: Dict[str, Any], filepath: str) -> bool:
    """
    保存单个实验到配置文件
    
    Args:
        experiment: 实验配置
        filepath: 文件路径
        
    Returns:
        bool: 保存是否成功
    """
    try:
        # 验证实验配置有效性
        if not validate_experiment(experiment):
            logger.error("实验配置无效，无法保存")
            return False
        
        # 如果文件已存在，则读取现有实验
        experiments = []
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                experiments = json.load(f)
        
        # 检查是否已存在同名实验
        for i, exp in enumerate(experiments):
            if exp.get("name") == experiment["name"]:
                # 更新现有实验
                experiments[i] = experiment
                break
        else:
            # 添加新实验
            experiments.append(experiment)
        
        # 保存到文件
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(experiments, f, ensure_ascii=False, indent=2)
        
        logger.info(f"实验 '{experiment['name']}' 已保存")
        return True
        
    except Exception as e:
        logger.error(f"保存实验时出错: {str(e)}")
        return False

def export_experiment_report(experiment: Dict[str, Any], circuit_data: Dict[str, Any], results: Dict[str, Any]) -> str:
    """
    生成实验报告
    
    Args:
        experiment: 实验配置
        circuit_data: 电路数据
        results: 实验结果数据
        
    Returns:
        str: 实验报告文本
    """
    report = f"# {experiment['name']} 实验报告\n\n"
    report += f"## 实验目标\n{experiment['goal']}\n\n"
    report += f"## 实验难度\n{experiment.get('difficulty', '未指定')}\n\n"
    
    report += "## 实验步骤\n"
    if "steps" in experiment:
        for i, step in enumerate(experiment["steps"]):
            report += f"{i+1}. {step}\n"
    else:
        report += "无详细步骤记录\n"
    
    report += "\n## 实验结果\n"
    if results:
        report += f"完成度: {results.get('completion_percentage', 0)}%\n"
        report += f"反馈: {results.get('feedback', '')}\n"
        
        if "measurements" in results:
            report += "\n### 测量结果\n"
            for key, value in results["measurements"].items():
                report += f"- {key}: {value}\n"
    
    report += "\n## 实验总结\n"
    report += "请在此处添加实验总结...\n"
    
    return report 