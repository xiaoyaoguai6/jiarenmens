from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Player:
    """实盘选手信息"""
    zh_id: str                    # 组合ID (900304915)
    name: str                     # 选手名称
    followers: int = 0           # 关注人数
    total_return: float = 0.0    # 总收益率%
    daily_return: float = 0.0    # 日收益率%
    net_value: float = 0.0       # 净值
    max_drawdown: float = 0.0    # 最大回撤%
    win_rate: float = 0.0        # 胜率%
    days: int = 0                # 运行天数
    concept: str = ""            # 概念标签
    intro: str = ""              # 简介

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'Player':
        return cls(**data)
