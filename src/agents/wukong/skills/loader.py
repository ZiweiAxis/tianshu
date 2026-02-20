"""
Skill Loader - 技能加载器

负责从 Registry 加载 Skill 并提供文档内容
支持热重载和文件变化监听
"""

import os
import re
import logging
import subprocess
import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass

from .registry import SkillRegistry, Skill, get_registry, parse_skill_md
from .executor import SkillExecutor, ExecutionResult, execute_skill

logger = logging.getLogger(__name__)

# 尝试导入 watchdog 用于文件监听
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileModifiedEvent
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    logger.warning("watchdog not installed, hot reload will use polling mode")


@dataclass
class SkillContext:
    """
    Skill 上下文信息
    
    包含 Skill 元数据和完整文档内容
    用于提供给 LLM 作为执行指引
    """
    skill: Skill
    content: str  # SKILL.md 完整内容
    markdown_content: str  # Markdown 部分（不含 frontmatter）


class SkillLoader:
    """
    Skill 加载器（文档式）
    
    功能:
    - 从 Registry 加载 Skill
    - 返回 SkillContext 供 LLM 使用
    - Skill 热重载支持
    - 文件变化监听
    
    执行流程:
    1. 接收用户消息
    2. LLM 意图识别 → 找到匹配 Skill
    3. 读取 SKILL.md 内容
    4. 将 SKILL.md 内容作为上下文发送给 LLM
    5. LLM 按照文档指引执行操作
    6. 返回结果
    """
    
    def __init__(
        self,
        registry: Optional[SkillRegistry] = None,
        skills_path: Optional[str] = None,
        enable_hot_reload: bool = True,
    ):
        """
        初始化 SkillLoader
        
        Args:
            registry: SkillRegistry 实例，默认使用全局注册表
            skills_path: Skill 目录路径
            enable_hot_reload: 是否启用热重载
        """
        self._registry = registry or get_registry()
        self._skills_path = skills_path
        self._skills: Dict[str, SkillContext] = {}  # name -> SkillContext
        self._enable_hot_reload = enable_hot_reload
        self._observer = None
        self._reload_callbacks: List[Callable[[], None]] = []
        
        # 初始化执行器
        self._executor = SkillExecutor()
        
        # 初始加载
        self.load()
        
        # 启动文件监听
        if enable_hot_reload:
            self._start_watchdog()
    
    def load(self) -> List[SkillContext]:
        """
        加载所有 Skill
        
        Returns:
            SkillContext 列表
        """
        skills = self._registry.scan()
        
        self._skills = {}
        
        for skill in skills:
            # 获取完整文档内容
            content = skill.content
            if not content:
                skill_file = Path(skill.path) / "SKILL.md"
                if skill_file.exists():
                    _, content = parse_skill_md(skill_file)
            
            context = SkillContext(
                skill=skill,
                content=content,
                markdown_content=content  # 这里 content 已经是 markdown
            )
            self._skills[skill.name] = context
        
        logger.info(f"Loaded {len(self._skills)} skills")
        return list(self._skills.values())
    
    def get_context(self, name: str) -> Optional[SkillContext]:
        """
        获取指定名称的 Skill 上下文
        
        Args:
            name: Skill 名称
            
        Returns:
            SkillContext 对象
        """
        return self._skills.get(name)
    
    def get_skill(self, name: str) -> Optional[Skill]:
        """
        获取指定名称的 Skill
        
        Args:
            name: Skill 名称
            
        Returns:
            Skill 对象
        """
        context = self._skills.get(name)
        return context.skill if context else None
    
    def get_all_contexts(self) -> List[SkillContext]:
        """
        获取所有 Skill 上下文
        
        Returns:
            SkillContext 列表
        """
        return list(self._skills.values())
    
    def find_by_keyword(self, keyword: str) -> List[SkillContext]:
        """
        根据关键词查找匹配的 Skill
        
        Args:
            keyword: 关键词
            
        Returns:
            匹配的 SkillContext 列表
        """
        results = []
        keyword = keyword.lower()
        
        for ctx in self._skills.values():
            skill = ctx.skill
            for trigger in skill.triggers:
                if any(keyword in kw.lower() for kw in trigger.keywords):
                    results.append(ctx)
                    break
        
        return results
    
    def find_by_intent(self, intent: str) -> List[SkillContext]:
        """
        根据意图描述查找匹配的 Skill
        
        Args:
            intent: 意图描述（如"查询天气"、"发送文件"）
            
        Returns:
            匹配的 SkillContext 列表（按相关度排序）
        """
        results = []
        intent_lower = intent.lower()
        
        # 中文关键词映射
        cn_keywords = {
            '天气': 'weather',
            '气温': 'weather',
            '预报': 'weather',
            '晴': 'weather',
            '雨': 'weather',
            '雪': 'weather',
            '查询': 'search',
            '发送': 'send',
            '文件': 'file',
        }
        
        for ctx in self._skills.values():
            skill = ctx.skill
            score = 0
            content = (ctx.content or "").lower()
            
            # 1. 检查中文关键词匹配
            for cn_kw, skill_name in cn_keywords.items():
                if cn_kw in intent_lower and skill_name == skill.name:
                    score += 15
            
            # 2. 检查名称匹配
            if skill.name.lower() in intent_lower:
                score += 10
            
            # 3. 检查描述匹配
            if skill.description and skill.description.lower() in intent_lower:
                score += 5
            
            # 4. 检查文档内容中的关键词
            chinese_trigger_words = ['天气', '气温', '预报', '查询', '发送', '文件']
            for kw in chinese_trigger_words:
                if kw in intent_lower and kw in content:
                    score += 8
            
            # 5. 检查触发关键词（如果有）
            for trigger in skill.triggers:
                for kw in trigger.keywords:
                    kw_lower = kw.lower()
                    if kw_lower in intent_lower:
                        score += 5
                    elif intent_lower in kw_lower:
                        score += 3
            
            if score > 0:
                results.append((score, ctx))
        
        # 按分数排序
        results.sort(key=lambda x: x[0], reverse=True)
        return [ctx for _, ctx in results]
    
    def get_skill_document(self, name: str) -> Optional[str]:
        """
        获取 Skill 的完整文档内容
        
        Args:
            name: Skill 名称
            
        Returns:
            SKILL.md 完整内容
        """
        ctx = self._skills.get(name)
        return ctx.content if ctx else None
    
    def format_for_llm(self, name: str, include_frontmatter: bool = False) -> Optional[str]:
        """
        格式化 Skill 文档供 LLM 使用
        
        Args:
            name: Skill 名称
            include_frontmatter: 是否包含 YAML frontmatter
            
        Returns:
            格式化后的文档内容
        """
        ctx = self._skills.get(name)
        if not ctx:
            return None
        
        content = ctx.content
        
        if not include_frontmatter:
            # 移除 YAML frontmatter
            pattern = r'^---\s*\n.*?\n---\s*\n'
            content = re.sub(pattern, '', content, flags=re.DOTALL)
        
        return content.strip()
    
    def execute_skill(self, skill_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行 Skill
        
        Args:
            skill_name: Skill 名称
            parameters: 执行参数
            
        Returns:
            执行结果
        """
        skill = self.get_skill(skill_name)
        if not skill:
            return {
                "success": False,
                "message": f"Skill '{skill_name}' not found"
            }
        
        # 使用执行器执行
        result = self._executor.execute(skill, parameters)
        return result.to_dict()
    
    def reload(self) -> List[SkillContext]:
        """
        重新加载所有 Skill
        
        Returns:
            重新加载后的 SkillContext 列表
        """
        logger.info("Reloading skills...")
        self._registry.reload()
        contexts = self.load()
        
        # 触发回调
        for callback in self._reload_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Error in reload callback: {e}")
        
        return contexts
    
    def on_reload(self, callback: Callable[[], None]) -> None:
        """
        注册重载回调
        
        Args:
            callback: 重载时调用的回调函数
        """
        self._reload_callbacks.append(callback)
    
    def _start_watchdog(self) -> None:
        """启动文件变化监听"""
        if not WATCHDOG_AVAILABLE:
            logger.warning("Watchdog not available, using polling mode for hot reload")
            return
        
        skills_path = self._skills_path or str(self._registry.skills_path)
        
        if not os.path.exists(skills_path):
            logger.warning(f"Skills path does not exist: {skills_path}")
            return
        
        class SkillFileHandler(FileSystemEventHandler):
            def __init__(self, loader_instance):
                super().__init__()
                self._loader = loader_instance
                self._reload_timer = None
            
            def on_modified(self, event):
                if event.is_directory:
                    return
                if event.src_path.endswith("SKILL.md"):
                    logger.info(f"Skill file modified: {event.src_path}")
                    # 防抖：延迟重载
                    import threading
                    if self._reload_timer:
                        self._reload_timer.cancel()
                    self._reload_timer = threading.Timer(1.0, self._loader.reload)
                    self._reload_timer.start()
        
        self._observer = Observer()
        self._observer.schedule(
            SkillFileHandler(),
            skills_path,
            recursive=True
        )
        self._observer.start()
        logger.info(f"Started file watcher on {skills_path}")
    
    def stop(self) -> None:
        """停止文件监听"""
        if self._observer:
            self._observer.stop()
            self._observer.join()
            self._observer = None
            logger.info("Stopped file watcher")
    
    def __del__(self):
        """析构时停止监听"""
        self.stop()


# 全局加载器实例
_default_loader: Optional[SkillLoader] = None


def get_loader(
    registry: Optional[SkillRegistry] = None,
    skills_path: Optional[str] = None,
    enable_hot_reload: bool = True,
) -> SkillLoader:
    """
    获取全局 SkillLoader 实例
    
    Args:
        registry: SkillRegistry 实例
        skills_path: Skill 目录路径
        enable_hot_reload: 是否启用热重载
        
    Returns:
        SkillLoader 实例
    """
    global _default_loader
    if _default_loader is None:
        _default_loader = SkillLoader(
            registry=registry,
            skills_path=skills_path,
            enable_hot_reload=enable_hot_reload,
        )
    return _default_loader
