from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Position:
    """持仓信息"""
    zh_id: str                    # 组合ID
    stock_name: str              # 股票名称
    stock_code: str              # 股票代码
    cost_price: float = 0.0      # 成本价
    current_price: float = 0.0   # 当前价
    profit_ratio: float = 0.0    # 盈亏比例%
    position_ratio: float = 0.0   # 仓位比例%
    update_time: str = ""        # 更新时间

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'Position':
        return cls(**data)
