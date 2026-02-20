"""
Skill Registry - 技能注册表

负责扫描、加载和管理 Skill 元数据
支持文档式 SKILL.md (YAML frontmatter + Markdown)
"""

import os
import re
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


@dataclass
class SkillParameter:
    """Skill 参数定义"""
    name: str
    type: str
    required: bool = True
    description: str = ""
    default: Any = None


@dataclass
class SkillTrigger:
    """Skill 触发器定义"""
    keywords: List[str] = field(default_factory=list)
    pattern: str = ""


@dataclass
class SkillExecution:
    """Skill 执行配置"""
    type: str = "script"  # script, function, api
    entry: str = ""  # 入口文件或函数名
    timeout: int = 30


@dataclass
class Skill:
    """Skill 元数据"""
    name: str
    description: str
    version: str = "1.0.0"
    triggers: List[SkillTrigger] = field(default_factory=list)
    parameters: List[SkillParameter] = field(default_factory=list)
    execution: Optional[SkillExecution] = None
    path: str = ""  # Skill 目录路径
    content: str = ""  # SKILL.md 完整内容
    
    @classmethod
    def from_dict(cls, data: Dict, path: str = "", content: str = "") -> "Skill":
        """从字典创建 Skill 对象"""
        # 解析 triggers
        triggers = []
        for t in data.get("triggers", []):
            triggers.append(SkillTrigger(
                keywords=t.get("keywords", []),
                pattern=t.get("pattern", "")
            ))
        
        # 解析 parameters
        parameters = []
        for p in data.get("parameters", []):
            parameters.append(SkillParameter(
                name=p["name"],
                type=p.get("type", "string"),
                required=p.get("required", True),
                description=p.get("description", ""),
                default=p.get("default")
            ))
        
        # 解析 execution
        execution = None
        if "execution" in data:
            exec_data = data["execution"]
            execution = SkillExecution(
                type=exec_data.get("type", "script"),
                entry=exec_data.get("entry", ""),
                timeout=exec_data.get("timeout", 30)
            )
        
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            triggers=triggers,
            parameters=parameters,
            execution=execution,
            path=path,
            content=content
        )


def parse_skill_md(file_path: Path) -> tuple[Optional[Dict], str]:
    """
    解析 SKILL.md 文件，提取 YAML frontmatter 和 Markdown 内容
    
    Args:
        file_path: SKILL.md 文件路径
        
    Returns:
        (元数据字典, Markdown 内容)
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 使用正则匹配 YAML frontmatter
        # 格式: --- ... ---
        pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
        match = re.match(pattern, content, re.DOTALL)
        
        if match:
            yaml_str = match.group(1)
            markdown_content = match.group(2).strip()
            
            # 解析 YAML
            metadata = yaml.safe_load(yaml_str)
            return metadata, markdown_content
        
        return None, content
        
    except Exception as e:
        print(f"Failed to parse SKILL.md {file_path}: {e}")
        return None, ""


class SkillRegistry:
    """
    Skill 注册表
    
    功能:
    - 扫描目录发现 Skill
    - 解析 SKILL.md 获取元数据（YAML frontmatter）
    - 提供 Skill 查询接口
    """
    
    SKILL_FILE = "SKILL.md"  # 改为扫描 .md 文件
    
    def __init__(self, skills_path: Optional[str] = None):
        """
        初始化注册表
        
        Args:
            skills_path: Skill 目录路径，默认使用模块目录
        """
        if skills_path is None:
            # 使用当前模块所在目录
            self.skills_path = Path(__file__).parent
        else:
            self.skills_path = Path(skills_path)
        
        self._skills: Dict[str, Skill] = {}
        self._loaded = False
    
    def scan(self) -> List[Skill]:
        """
        扫描 skills 目录，发现所有 Skill
        
        Returns:
            Skill 列表
        """
        skills = []
        
        if not self.skills_path.exists():
            return skills
        
        for entry in self.skills_path.iterdir():
            if not entry.is_dir():
                continue
            
            # 跳过隐藏目录和示例目录
            if entry.name.startswith('.') or entry.name == 'examples':
                continue
            
            skill_file = entry / self.SKILL_FILE
            if skill_file.exists():
                skill = self._load_skill(entry)
                if skill:
                    skills.append(skill)
                    self._skills[skill.name] = skill
        
        # 扫描 examples 目录
        examples_path = self.skills_path / "examples"
        if examples_path.exists():
            for entry in examples_path.iterdir():
                if not entry.is_dir():
                    continue
                
                skill_file = entry / self.SKILL_FILE
                if skill_file.exists():
                    skill = self._load_skill(entry)
                    if skill:
                        skills.append(skill)
                        self._skills[skill.name] = skill
        
        self._loaded = True
        return skills
    
    def _load_skill(self, skill_path: Path) -> Optional[Skill]:
        """加载单个 Skill"""
        skill_file = skill_path / self.SKILL_FILE
        
        try:
            metadata, markdown_content = parse_skill_md(skill_file)
            
            if not metadata:
                # 如果没有 frontmatter，尝试使用文件名作为名称
                metadata = {
                    "name": skill_path.name,
                    "description": f"Skill: {skill_path.name}"
                }
            
            return Skill.from_dict(metadata, str(skill_path), markdown_content)
        except Exception as e:
            print(f"Failed to load skill from {skill_path}: {e}")
            return None
    
    def list_skills(self) -> List[Skill]:
        """
        列出所有已注册的 Skill
        
        Returns:
            Skill 列表
        """
        if not self._loaded:
            self.scan()
        return list(self._skills.values())
    
    def get_skill(self, name: str) -> Optional[Skill]:
        """
        获取指定名称的 Skill
        
        Args:
            name: Skill 名称
            
        Returns:
            Skill 对象，不存在则返回 None
        """
        if not self._loaded:
            self.scan()
        return self._skills.get(name)
    
    def get_skill_content(self, name: str) -> Optional[str]:
        """
        获取指定名称的 Skill 完整文档内容
        
        Args:
            name: Skill 名称
            
        Returns:
            SKILL.md 完整内容
        """
        skill = self.get_skill(name)
        if skill:
            # 如果 content 为空，尝试重新读取
            if not skill.content:
                skill_file = Path(skill.path) / self.SKILL_FILE
                if skill_file.exists():
                    _, skill.content = parse_skill_md(skill_file)
            return skill.content
        return None
    
    def find_by_keyword(self, keyword: str) -> List[Skill]:
        """
        根据关键词查找 Skill
        
        Args:
            keyword: 关键词
            
        Returns:
            匹配的 Skill 列表
        """
        if not self._loaded:
            self.scan()
        
        keyword = keyword.lower()
        results = []
        
        for skill in self._skills.values():
            for trigger in skill.triggers:
                if any(keyword in kw.lower() for kw in trigger.keywords):
                    results.append(skill)
                    break
        
        return results
    
    def find_by_description(self, query: str) -> List[Skill]:
        """
        根据描述/意图查找 Skill
        
        Args:
            query: 查询字符串
            
        Returns:
            匹配的 Skill 列表（按描述匹配度排序）
        """
        if not self._loaded:
            self.scan()
        
        query = query.lower()
        results = []
        
        for skill in self._skills.values():
            # 匹配 name, description
            score = 0
            if query in skill.name.lower():
                score += 10
            if query in skill.description.lower():
                score += 5
            
            if score > 0:
                results.append((score, skill))
        
        # 按分数排序
        results.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in results]
    
    def reload(self):
        """重新加载所有 Skill"""
        self._skills.clear()
        self._loaded = False
        return self.scan()


# 全局注册表实例
_default_registry: Optional[SkillRegistry] = None


def get_registry() -> SkillRegistry:
    """获取全局注册表实例"""
    global _default_registry
    if _default_registry is None:
        _default_registry = SkillRegistry()
    return _default_registry
