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
            
        logger.info(f"成功加载了 {len(experiments)} 个实验")
        return experiments
    
    except json.JSONDecodeError as e:
        logger.error(f"解析实验配置文件时出错: {str(e)}")
        return []
    except Exception as e:
        logger.error(f"加载实验配置时发生错误: {str(e)}")
        return []

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