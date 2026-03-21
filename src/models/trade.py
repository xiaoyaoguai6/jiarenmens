from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Trade:
    """调仓记录"""
    zh_id: str                    # 组合ID
    stock_name: str              # 股票名称
    stock_code: str              # 股票代码
    trades: int = 1              # 笔数
    position_ratio: str = ""     # 交易仓位 (如"9成以上")
    price: float = 0.0           # 成交价格
    trade_date: str = ""         # 交易日期

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'Trade':
        return cls(**data)
