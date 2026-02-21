# Channel 注册表
# 管理所有可用渠道

from typing import Dict, Optional, Type

from channel.base import Channel


class ChannelRegistry:
    """Channel 注册表。"""

    _channels: Dict[str, Type[Channel]] = {}
    _instances: Dict[str, Channel] = {}

    @classmethod
    def register(cls, name: str, channel_class: Type[Channel]) -> None:
        """注册渠道类。"""
        cls._channels[name] = channel_class

    @classmethod
    def get(cls, name: str) -> Optional[Channel]:
        """获取渠道实例。"""
        return cls._instances.get(name)

    @classmethod
    def set_instance(cls, name: str, instance: Channel) -> None:
        """设置渠道实例。"""
        cls._instances[name] = instance

    @classmethod
    def list_channels(cls) -> Dict[str, Channel]:
        """列出所有已实例化的渠道。"""
        return cls._instances.copy()

    @classmethod
    def has_channel(cls, name: str) -> bool:
        """检查渠道是否存在。"""
        return name in cls._instances


# 便捷函数
def register_channel(name: str) -> Type[Channel]:
    """装饰器：注册渠道。"""
    def decorator(cls: Type[Channel]) -> Type[Channel]:
        ChannelRegistry.register(name, cls)
        return cls
    return decorator


def get_channel(name: str) -> Optional[Channel]:
    """获取渠道实例。"""
    return ChannelRegistry.get(name)
