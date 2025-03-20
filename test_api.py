import json
import time
from typing import List, Dict, Optional
from openai import OpenAI, AuthenticationError, APIError, RateLimitError, APIConnectionError
from dataclasses import dataclass
import logging
from pathlib import Path

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    api_key: str
    api_base: str
    max_retries: int = 3
    retry_delay: int = 2
    default_temperature: float = 0.1
    default_model: str = "gpt-3.5-turbo"


class LLMClient:
    def __init__(self, config: LLMConfig):
        self.config = config
        self.client = None
        self._initialize_client()

    def _initialize_client(self):
        """初始化OpenAI客户端"""
        try:
            self.client = OpenAI(
                api_key=self.config.api_key,
                base_url=self.config.api_base,
                timeout=10
            )
            logger.info("OpenAI客户端初始化成功")
        except AuthenticationError as e:
            logger.error("认证失败，请检查API密钥")
            raise
        except Exception as e:
            logger.error(f"客户端初始化失败: {str(e)}")
            raise

    def test_connection(self) -> (bool, str):
        """专用API连接测试方法"""
        test_messages = [{"role": "user", "content": "请回复'Test successful'"}]

        for attempt in range(self.config.max_retries):
            try:
                response = self.client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=test_messages,
                    max_tokens=10
                )
                content = response.choices[0].message.content.strip().lower()
                if "test successful" in content:
                    return True, "API 正常工作，响应正常"
                return True, f"API 可访问，但响应内容异常: {content}"

            except AuthenticationError:
                return False, "认证失败：无效的API密钥"
            except APIConnectionError:
                if attempt < self.config.max_retries - 1:
                    time.sleep(self.config.retry_delay)
                    continue
                return False, "网络连接失败，请检查网络或代理"
            except RateLimitError:
                return False, "请求被限流，请检查配额"
            except APIError as e:
                return False, f"API服务器错误: {str(e)}"
            except Exception as e:
                return False, f"未知错误: {str(e)}"

    # 新增缺失的run_llm方法
    def run_llm(
            self,
            prompt: str,
            temperature: Optional[float] = None,
            model: Optional[str] = None,
            system_prompt: str = "你是一个专业的物理教育助手"
    ) -> str:
        """运行LLM模型获取响应"""
        temperature = temperature or self.config.default_temperature
        model = model or self.config.default_model

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]

        for attempt in range(self.config.max_retries):
            try:
                completion = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                )
                return completion.choices[0].message.content
            except Exception as e:
                logger.warning(f"第{attempt + 1}次尝试失败: {str(e)}")
                if attempt < self.config.max_retries - 1:
                    time.sleep(self.config.retry_delay)
                else:
                    logger.error(f"达到最大重试次数，请求失败: {str(e)}")
                    raise


def load_config(config_path: str = "config.json") -> LLMConfig:
    """加载配置文件"""
    default_config = {
        "api_key": "sk-your-api-key-here",
        "api_base": "https://api.openai.com/v1",
        "max_retries": 3,
        "retry_delay": 2
    }

    try:
        config_file = Path(config_path)
        if not config_file.exists():
            logger.warning("配置文件不存在，使用默认配置")
            return LLMConfig(**default_config)

        with open(config_file, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
            return LLMConfig(**{**default_config, **config_data})
    except Exception as e:
        logger.error(f"配置加载失败: {str(e)}")
        return LLMConfig(**default_config)


def main():
    # 加载配置
    config = load_config()

    try:
        llm_client = LLMClient(config)

        # 执行连接测试
        logger.info("正在测试API连接...")
        success, message = llm_client.test_connection()

        if success:
            logger.info("\033[32m✓ 连接测试成功\033[0m")
            logger.info(message)

            # 示例请求
            response = llm_client.run_llm("你的参数量有多大")
            logger.info("示例响应内容：" + response[:10000] + "...")
        else:
            logger.error("\033[31m✗ 连接测试失败\033[0m")
            logger.error(message)

    except Exception as e:
        logger.error(f"初始化失败: {str(e)}")


if __name__ == '__main__':
    main()