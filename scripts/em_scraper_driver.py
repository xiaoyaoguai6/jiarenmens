"""
em_scraper_driver.py  --  ADB UI automation driver for East Money shipan APP.

Implements scrape_one_player(zh_id, open_player_steps):
    1. Ensure EM APP is alive & at home (cold start if needed).
    2. Open the search page (top-right magnifier button).
    3. Tap the '组合' (combination) sub-tab in search options.
    4. Type the zhid string into the search box.
    5. Tap the first matching result row.
    6. Tap '持仓' sub-tab and wait for it to truly load (mitm will emit a
       CombinationHoldPositionPermitHandler response event).
    7. Tap '调仓' sub-tab and wait for CombinationRelocatePositionHandler.
    8. Press back twice to exit to home for next iteration.

The driver issues ADB input taps at fixed coordinates determined empirically
on a 1080x1920 LDPlayer session. It polls mitm's positions.jsonl to wait for
the right event (matched by zh_id + method) before returning.

Configuration knobs:
    ZHID_LIST: list of player IDs to scrape.
    POLL_SECONDS: how long each scrape-one-player call waits max.

This module is importable as a library; the CLI in scraper_poller.py drives it.
"""
import json
import os
import re
import subprocess
import sys
import time
from datetime import date
from pathlib import Path
from typing import List, Dict, Any, Optional

# import relative paths
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from adb_ui import Adb, tap_text_if_present, dump_to_file, parse_ui_xml, find_node, bounds_to_xy

ADB = Adb()

RECON_DIR = ROOT / "data" / "recon"
EVENTS_PATH = RECON_DIR / "positions.jsonl"

# Hardcoded screen coordinates on LDPlayer @ 1080x1920
# Calibrated via uiautomator dump on newyork APP
TOP_SEARCH_ICON = (990, 140)        # the magnifier icon upper right of home
SEARCH_COMBO_TAB = (913, 266)        # '组合' sub-tab in search options bar
SEARCH_BOX_REGION = (343, 240, 900, 320)  # the OCR/EditText area where to type
FIRST_RESULT_Y = 540                  # approximately the first row Y in result list

HOME_TABS = {
    1: (90, 1880),     # 首页
    2: (270, 1880),    # 资讯
    3: (450, 1880),    # (Self/msg; no name in dump)
    4: (630, 1880),    # 行情
    5: (810, 1880),    # 理财
    6: (990, 1880),    # 交易
}

# Per page tabs in the combination detail view (calibrated on berlin/newyork)
DETAIL_HOLD_TAB = "持仓"
DETAIL_TRADE_TAB = "调仓"


def ensure_app_alive() -> bool:
    """Force open EM newyork home; returns whether current focus landed on HomeActivity."""
    focus = ADB.current_focus()
    if "newyork" in focus or "berlin" in focus:
        return True
    ADB.shell("am force-stop com.eastmoney.android.newyork")
    time.sleep(0.6)
    ADB.shell("monkey -p com.eastmoney.android.newyork -c android.intent.category.LAUNCHER 1")
    time.sleep(5)
    return "newyork" in ADB.current_focus()


def back_to_home(max_back: int = 5) -> bool:
    """Press back until we're on HomeActivity."""
    for _ in range(max_back):
        f = ADB.current_focus()
        if "module.launcher.internal.home.HomeActivity" in f:
            return True
        ADB.press_back()
        time.sleep(0.6)
    # fall-back: force restart app
    return ensure_app_alive()


def open_search():
    """Tap the magnifier icon at top-right of home, return NewSearchActivity focus."""
    ADB.tap(*TOP_SEARCH_ICON)
    time.sleep(1.5)
    # Take a screenshot just to leave a debugging breadcrumb
    ADB.screenshot(str(RECON_DIR / "search_after_tap.png"))
    f = ADB.current_focus()
    return "search.NewSearchActivity" in f


def search_for_zhid(zhid: str):
    """Open search page, switch to '组合' tab, type zhid, press enter."""
    if not open_search():
        return False
    ADB.tap(*SEARCH_COMBO_TAB)
    time.sleep(0.8)
    # Use ADB input text (only safe for ASCII digits; that is fine for zhids)
    ADB.shell(f"input text {zhid}")
    time.sleep(0.5)
    ADB.shell("input keyevent 66")  # ENTER (sometimes 84=SEARCH)
    time.sleep(2)
    # tap first result row to open the combination page
    ADB.tap(540, FIRST_RESULT_Y)
    time.sleep(3)
    f = ADB.current_focus()
    return "EMHybridActivity" in f or "WebH5Activity" in f or "StockActivity" in f


def tap_dashboard_tab(label: str, timeout: int = 8) -> bool:
    """Tap a text label like '持仓' or '调仓' on the current RN dashboard."""
    end = time.time() + timeout
    while time.time() < end:
        if tap_text_if_present(ADB, label):
            return True
        time.sleep(0.6)
    return False


def wait_for_event(zh_id: str, method: str, timeout: float = 12.0) -> Optional[dict]:
    """Poll positions.jsonl backward for a fresh event matching zh_id+method.

    An event is 'fresh' if its `ts` is within (now - timeout) seconds of now.
    """
    if not EVENTS_PATH.exists():
        return None
    deadline = time.time() + timeout
    target_ts_min = time.time() - timeout - 5  # generous
    while time.time() < deadline:
        try:
            with EVENTS_PATH.open("r", encoding="utf-8") as f:
                lines = f.readlines()[-30:]
            for line in reversed(lines):
                try:
                    ev = json.loads(line)
                except Exception:
                    continue
                if ev.get("zh_id") != str(zh_id):
                    continue
                if ev.get("method") != method:
                    continue
                if ev.get("ts", 0) < target_ts_min:
                    continue
                if ev.get("code") != 0:
                    continue
                return ev
        except Exception:
            pass
        time.sleep(0.4)
    return None


def scrape_one_player(zh_id: str, hold: bool = True, trade: bool = True) -> Dict[str, Any]:
    """Open the combination detail page for this zh_id, switch to 持仓 then 调仓 tab;
    waits up to ~15s for mitm to capture each response.

    Returns a dict with the latest captured events (or {error: ...} on failure).
    """
    if not ensure_app_alive():
        return {"error": "app_alive_failed"}

    if not back_to_home():
        return {"error": "back_to_home_failed"}

    if not search_for_zhid(str(zh_id)):
        return {"error": "search_for_zhid_failed"}

    out = {"zh_id": zh_id}
    if hold:
        if not tap_dashboard_tab(DETAIL_HOLD_TAB, timeout=4):
            # sometimes default tab is already '持仓' so this is a soft warning
            out["hold_tab_tapped"] = False
        ev = wait_for_event(zh_id, "CombinationHoldPositionPermitHandler", timeout=15)
        if ev is None:
            # try alternate handler if it's the "showPermit-only" lemma
            ev = wait_for_event(zh_id, "CombinationHoldBlockPermitHandler", timeout=2)
        out["hold_event"] = ev
        if ev is None:
            out["error_hold"] = "no event"
    if trade:
        if not tap_dashboard_tab(DETAIL_TRADE_TAB, timeout=4):
            out["trade_tab_tapped"] = False
        ev = wait_for_event(zh_id, "CombinationRelocatePositionHandler", timeout=15)
        out["trade_event"] = ev
        if ev is None:
            out["error_trade"] = "no event"

    # Press back twice to go to home
    ADB.press_back()
    time.sleep(0.3)
    ADB.press_back()
    time.sleep(0.6)
    return out


if __name__ == "__main__":
    # ad-hoc CLI for inspection: python scripts/em_scraper_driver.py 900296556
    zhid = sys.argv[1] if len(sys.argv) > 1 else "900296556"
    print(scrape_one_player(zhid))