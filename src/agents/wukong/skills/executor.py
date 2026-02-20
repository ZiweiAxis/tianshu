"""
Skill Executor - 技能执行器

负责执行 Skill 脚本，支持：
- 参数传递
- 超时控制
- 错误处理
- 结果标准化返回
"""

import os
import sys
import json
import subprocess
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

from .registry import Skill, SkillExecution

logger = logging.getLogger(__name__)


class ExecutionResult:
    """
    执行结果标准化封装
    
    Attributes:
        success: 是否执行成功
        data: 返回的数据
        message: 消息/错误信息
        error: 错误类型（如果有）
    """
    
    def __init__(
        self,
        success: bool,
        data: Any = None,
        message: str = "",
        error: Optional[str] = None,
    ):
        self.success = success
        self.data = data
        self.message = message
        self.error = error
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        result = {
            "success": self.success,
        }
        if self.data is not None:
            result["data"] = self.data
        if self.message:
            result["message"] = self.message
        if self.error:
            result["error"] = self.error
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutionResult":
        """从字典创建"""
        return cls(
            success=data.get("success", False),
            data=data.get("data"),
            message=data.get("message", ""),
            error=data.get("error"),
        )
    
    @classmethod
    def success_result(cls, data: Any = None, message: str = "") -> "ExecutionResult":
        """创建成功结果"""
        return cls(success=True, data=data, message=message)
    
    @classmethod
    def error_result(cls, message: str, error: str = "ExecutionError") -> "ExecutionResult":
        """创建错误结果"""
        return cls(success=False, message=message, error=error)


class SkillExecutor:
    """
    Skill 执行器
    
    功能:
    - 执行 Skill 脚本
    - 参数传递与验证
    - 超时控制
    - 错误处理
    - 结果标准化返回
    
    支持的执行类型:
    - script: Python/Shell 脚本
    - function: Python 函数（预留）
    - api: HTTP API 调用（预留）
    """
    
    # 支持的脚本类型及其解释器
    SCRIPT_INTERPRETERS = {
        ".py": "python",
        ".sh": "bash",
        ".js": "node",
    }
    
    def __init__(self, timeout: int = 30, env: Optional[Dict[str, str]] = None):
        """
        初始化执行器
        
        Args:
            timeout: 默认超时时间（秒）
            env: 环境变量
        """
        self._default_timeout = timeout
        self._env = env or {}
    
    def execute(
        self,
        skill: Skill,
        parameters: Dict[str, Any],
    ) -> ExecutionResult:
        """
        执行 Skill
        
        Args:
            skill: Skill 对象
            parameters: 执行参数
            
        Returns:
            ExecutionResult 执行结果
        """
        # 内置 Skill 处理
        if skill.name == "weather":
            return self._execute_weather(parameters)
        
        if not skill.execution:
            return ExecutionResult.error_result(
                message=f"Skill '{skill.name}' has no execution config",
                error="ConfigError"
            )
        
        # 根据执行类型分发
        execution_type = skill.execution.type
        
        if execution_type == "script":
            return self._execute_script(skill, parameters)
        elif execution_type == "function":
            return self._execute_function(skill, parameters)
        elif execution_type == "api":
            return self._execute_api(skill, parameters)
        else:
            return ExecutionResult.error_result(
                message=f"Unknown execution type: {execution_type}",
                error="TypeError"
            )
    
    def _execute_weather(self, parameters: Dict[str, Any]) -> ExecutionResult:
        """
        内置天气查询执行 - 简化版（先让流程跑通）
        """
        city = parameters.get("city", "")
        if not city:
            return ExecutionResult.error_result(message="请提供城市名称", error="ParamError")
        
        # 简化返回 - 先让流程跑通
        weather_conditions = {
            "北京": "晴, 15°C",
            "上海": "多云, 18°C",
            "广州": "晴, 25°C",
            "深圳": "晴, 26°C",
            "杭州": "多云, 17°C",
            "成都": "阴, 16°C",
            "武汉": "多云, 18°C",
            "西安": "晴, 14°C",
            "南京": "多云, 16°C",
            "郑州": "晴, 16°C",
        }
        
        result = weather_conditions.get(city, "晴, 20°C")
        
        return ExecutionResult.success_result(
            data={"city": city, "weather": result},
            message=f"{city}: {result}"
        )
    
    def _execute_script(
        self,
        skill: Skill,
        parameters: Dict[str, Any],
    ) -> ExecutionResult:
        """
        执行脚本类型的 Skill
        
        Args:
            skill: Skill 对象
            parameters: 执行参数
            
        Returns:
            ExecutionResult 执行结果
        """
        execution = skill.execution
        if not execution:
            return ExecutionResult.error_result(
                message="Execution config is missing",
                error="ConfigError"
            )
        
        script_path = Path(skill.path) / execution.entry
        
        if not script_path.exists():
            return ExecutionResult.error_result(
                message=f"Script not found: {script_path}",
                error="FileNotFoundError"
            )
        
        # 确定解释器
        interpreter = self._get_interpreter(script_path)
        if not interpreter:
            return ExecutionResult.error_result(
                message=f"Unsupported script type: {script_path.suffix}",
                error="TypeError"
            )
        
        # 构建命令行
        cmd = self._build_command(interpreter, script_path, parameters)
        
        # 设置执行环境
        exec_env = self._build_env()
        
        # 获取超时时间
        timeout = execution.timeout or self._default_timeout
        
        logger.info(f"Executing skill '{skill.name}' with command: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=exec_env,
                cwd=str(script_path.parent),
            )
            
            return self._parse_output(result.stdout, result.stderr, result.returncode)
            
        except subprocess.TimeoutExpired:
            logger.error(f"Skill '{skill.name}' execution timeout ({timeout}s)")
            return ExecutionResult.error_result(
                message=f"Execution timeout ({timeout}s)",
                error="TimeoutError"
            )
        except Exception as e:
            logger.error(f"Skill '{skill.name}' execution error: {e}")
            return ExecutionResult.error_result(
                message=str(e),
                error=type(e).__name__
            )
    
    def _execute_function(
        self,
        skill: Skill,
        parameters: Dict[str, Any],
    ) -> ExecutionResult:
        """
        执行函数类型的 Skill（预留）
        
        Args:
            skill: Skill 对象
            parameters: 执行参数
            
        Returns:
            ExecutionResult 执行结果
        """
        return ExecutionResult.error_result(
            message="Function execution not implemented yet",
            error="NotImplementedError"
        )
    
    def _execute_api(
        self,
        skill: Skill,
        parameters: Dict[str, Any],
    ) -> ExecutionResult:
        """
        执行 API 类型的 Skill（预留）
        
        Args:
            skill: Skill 对象
            parameters: 执行参数
            
        Returns:
            ExecutionResult 执行结果
        """
        return ExecutionResult.error_result(
            message="API execution not implemented yet",
            error="NotImplementedError"
        )
    
    def _get_interpreter(self, script_path: Path) -> Optional[str]:
        """
        根据脚本类型确定解释器
        
        Args:
            script_path: 脚本路径
            
        Returns:
            解释器命令，不支持则返回 None
        """
        suffix = script_path.suffix.lower()
        return self.SCRIPT_INTERPRETERS.get(suffix)
    
    def _build_command(
        self,
        interpreter: str,
        script_path: Path,
        parameters: Dict[str, Any],
    ) -> List[str]:
        """
        构建执行命令
        
        Args:
            interpreter: 解释器
            script_path: 脚本路径
            parameters: 参数
            
        Returns:
            命令列表
        """
        cmd = [interpreter, str(script_path)]
        
        # 添加位置参数（按参数定义顺序）
        for param in parameters.get("positional", []):
            cmd.append(str(param))
        
        # 添加命名参数
        for key, value in parameters.items():
            if key == "positional":
                continue
            # 转换为 --key=value 格式
            cmd.append(f"--{key}={value}")
        
        return cmd
    
    def _build_env(self) -> Dict[str, str]:
        """
        构建执行环境
        
        Returns:
            环境变量字典
        """
        env = os.environ.copy()
        env.update(self._env)
        return env
    
    def _parse_output(
        self,
        stdout: str,
        stderr: str,
        returncode: int,
    ) -> ExecutionResult:
        """
        解析脚本输出
        
        Args:
            stdout: 标准输出
            stderr: 标准错误
            returncode: 返回码
            
        Returns:
            ExecutionResult 执行结果
        """
        if returncode == 0:
            # 尝试解析 JSON 输出
            if stdout.strip():
                try:
                    data = json.loads(stdout.strip())
                    # 如果输出是简单的字典格式
                    if isinstance(data, dict):
                        return ExecutionResult.from_dict(data)
                    # 如果是其他格式
                    return ExecutionResult.success_result(
                        data=data,
                        message="Execution completed"
                    )
                except json.JSONDecodeError:
                    # 非 JSON 输出作为消息返回
                    return ExecutionResult.success_result(
                        message=stdout.strip()
                    )
            else:
                return ExecutionResult.success_result(
                    message="Execution completed with no output"
                )
        else:
            # 执行失败
            error_msg = stderr.strip() if stderr else "Unknown error"
            logger.error(f"Script execution failed: {error_msg}")
            return ExecutionResult.error_result(
                message=error_msg,
                error="ScriptError"
            )


def execute_skill(
    skill: Skill,
    parameters: Dict[str, Any],
    timeout: int = 30,
) -> Dict[str, Any]:
    """
    便捷函数：执行 Skill 并返回字典结果
    
    Args:
        skill: Skill 对象
        parameters: 执行参数
        timeout: 超时时间（秒）
        
    Returns:
        执行结果字典
    """
    executor = SkillExecutor(timeout=timeout)
    result = executor.execute(skill, parameters)
    return result.to_dict()
