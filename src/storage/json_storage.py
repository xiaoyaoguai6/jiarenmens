import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from src.config import DATA_BY_DATE, PLAYERS_DIR, POSITIONS_DIR, TRADES_DIR, LATEST_DIR, DATA_DIR
from src.utils.logger import setup_logger

logger = setup_logger()

# 兼容旧数据目录
OLD_DATA_DIR = DATA_DIR


def ensure_dirs():
    """确保目录存在"""
    PLAYERS_DIR.mkdir(parents=True, exist_ok=True)
    POSITIONS_DIR.mkdir(parents=True, exist_ok=True)
    TRADES_DIR.mkdir(parents=True, exist_ok=True)


def update_latest_symlink():
    """更新latest软链接指向最新数据"""
    try:
        if LATEST_DIR.exists() or LATEST_DIR.is_symlink():
            LATEST_DIR.unlink()
        os.symlink(DATA_BY_DATE, LATEST_DIR)
        logger.info(f"更新latest链接到 {DATA_BY_DATE}")
    except Exception as e:
        logger.warning(f"更新latest链接失败: {e}")


class JsonStorage:
    """JSON文件存储"""

    @staticmethod
    def save_players(players: List[Dict[str, Any]], filename: str = "players.json"):
        """保存选手列表"""
        ensure_dirs()
        path = PLAYERS_DIR / filename
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(players, f, ensure_ascii=False, indent=2)
        logger.info(f"保存选手列表到 {path}")

    @staticmethod
    def _find_file(filename: str, subdir: str = "players") -> Optional[Path]:
        """查找文件，支持多目录搜索"""
        search_paths = []
        if LATEST_DIR.exists():
            search_paths.append(LATEST_DIR / subdir / filename)
        if PLAYERS_DIR.exists():
            search_paths.append(PLAYERS_DIR / filename)
        # 兼容旧数据目录
        if (OLD_DATA_DIR / subdir).exists():
            search_paths.append(OLD_DATA_DIR / subdir / filename)

        for p in search_paths:
            if p.exists():
                return p
        return None

    @staticmethod
    def load_players(filename: str = "players.json", use_latest: bool = True) -> List[Dict[str, Any]]:
        """加载选手列表"""
        path = JsonStorage._find_file(filename, "players")
        if not path:
            return []
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    @staticmethod
    def save_player_detail(zh_id: str, data: Dict[str, Any]):
        """保存单个选手详情"""
        ensure_dirs()
        path = PLAYERS_DIR / f"{zh_id}.json"
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def load_player_detail(zh_id: str, use_latest: bool = True) -> Dict[str, Any]:
        """加载单个选手详情"""
        path = JsonStorage._find_file(f"{zh_id}.json", "players")
        if not path:
            return {}
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    @staticmethod
    def save_positions(zh_id: str, positions: List[Dict[str, Any]]):
        """保存持仓数据"""
        ensure_dirs()
        path = POSITIONS_DIR / f"{zh_id}.json"
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(positions, f, ensure_ascii=False, indent=2)

    @staticmethod
    def load_positions(zh_id: str, use_latest: bool = True) -> List[Dict[str, Any]]:
        """加载持仓数据"""
        path = JsonStorage._find_file(f"{zh_id}.json", "positions")
        if not path:
            return []
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    @staticmethod
    def save_trades(zh_id: str, trades: List[Dict[str, Any]]):
        """保存调仓记录"""
        ensure_dirs()
        path = TRADES_DIR / f"{zh_id}.json"
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(trades, f, ensure_ascii=False, indent=2)

    @staticmethod
    def load_trades(zh_id: str, use_latest: bool = True) -> List[Dict[str, Any]]:
        """加载调仓记录"""
        path = JsonStorage._find_file(f"{zh_id}.json", "trades")
        if not path:
            return []
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    @staticmethod
    def get_all_player_ids() -> set:
        """获取所有选手ID"""
        player_ids = set()
        # 搜索多个目录
        search_dirs = []
        if LATEST_DIR.exists():
            search_dirs.append(LATEST_DIR / "players")
        if PLAYERS_DIR.exists():
            search_dirs.append(PLAYERS_DIR)
        # 兼容旧数据目录
        if OLD_DATA_DIR.exists() and (OLD_DATA_DIR / "players").exists():
            search_dirs.append(OLD_DATA_DIR / "players")

        for d in search_dirs:
            if not d.exists():
                continue
            for f in d.glob("*.json"):
                if f.name not in ["players.json", "年榜.json", "月榜.json", "周榜.json", "日榜.json", "总榜.json"]:
                    player_ids.add(f.stem)
        return player_ids
