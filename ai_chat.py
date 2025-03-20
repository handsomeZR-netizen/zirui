# ai_chat.py
import os
import json
import time
import requests
from typing import Optional, Dict, List


class AIAssistant:
    MODEL_CONFIG = {
        "gpt-4": {
            "api_base": "https://api.openai.com/v1/",
            "auth_header": "Bearer"
        },
        "llama-2": {
            "api_base": "https://api.planetzero.live/v1/",
            "auth_header": "Token"
        }
    }

    def __init__(
            self,
            model: str = "gpt-4",
            api_key: Optional[str] = None,
            system_prompt: str = "你是一位物理实验助手，帮助用户理解和构建电路实验。"
    ):
        self.model = model
        self.system_prompt = system_prompt
        self.api_key = api_key or os.getenv("AI_API_KEY")
        self._validate_config()

    def _validate_config(self):
        """验证模型配置合法性"""
        if self.model not in self.MODEL_CONFIG:
            raise ValueError(f"不支持的模型：{self.model}")
        if not self.api_key:
            raise ValueError("必须提供API密钥或设置AI_API_KEY环境变量")

    def _build_request_data(
            self,
            message: str,
            context: Optional[Dict] = None,
            temperature: float = 0.7,
            max_retries: int = 3
    ) -> Dict:
        """构造API请求数据"""
        user_content = f"电路信息：{json.dumps(context)}\n\n用户问题：{message}" if context else message

        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_content}
            ],
            "temperature": temperature
        }

    def get_response(
            self,
            message: str,
            context: Optional[Dict] = None,
            temperature: float = 0.7,
            timeout: int = 15
    ) -> str:
        """获取AI回复（带自动重试机制）

        Args:
            message: 用户输入消息
            context: 电路图上下文信息（JSON格式）
            temperature: 生成随机性（0.0-2.0）
            timeout: 请求超时时间（秒）

        Returns:
            AI生成的回复文本

        Raises:
            APIError: API请求失败时抛出
        """
        config = self.MODEL_CONFIG[self.model]
        headers = {
            "Authorization": f"{config['auth_header']} {self.api_key}",
            "Content-Type": "application/json"
        }
        data = self._build_request_data(message, context, temperature)

        for attempt in range(3):
            try:
                response = requests.post(
                    url=f"{config['api_base']}chat/completions",
                    headers=headers,
                    json=data,
                    timeout=timeout
                )
                response.raise_for_status()
                return response.json()["choices"][0]["message"]["content"]

            except requests.exceptions.RequestException as e:
                if attempt == 2:
                    error_msg = f"API请求失败: {str(e)}"
                    if hasattr(e.response, "status_code"):
                        error_msg += f" | 状态码: {e.response.status_code}"
                    if e.response.text:
                        try:
                            error_details = e.response.json()
                            error_msg += f" | 错误详情: {error_details}"
                        except:
                            error_msg += f" | 原始响应: {e.response.text[:200]}"
                    raise APIError(error_msg)
                time.sleep(2 ** attempt)  # 指数退避

        raise APIError("未知错误")


class APIError(Exception):
    """自定义API异常"""
    pass