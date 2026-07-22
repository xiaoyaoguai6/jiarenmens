"""ADB UI driver primitives for driving the East Money Android APP on LDPlayer.

Strategy: use Android's built-in `uiautomator dump` XML + `adb shell input tap`
to navigate the APP. This works on stock Android 9 LDPlayer without needing
Appium. We don't rely on accessibility IDs; we tap by visible text.

Why uiautomator dump (not input keyevent / monkey): the EM APP's combination
detail Activity is React-Native-rendered, with mostly text nodes that we can
match against zh_id / names / "持仓" / "调仓" labels.
"""
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ADB_PATH = r"C:\leidian\LDPlayer9\adb.exe"
DEVICE = "emulator-5554"

# LDPlayer screen geometry defaults (BKQ-ANO0 414x896 from earlier dumpsys)
DEFAULT_W, DEFAULT_H = 1080, 1920


class Adb:
    def __init__(self, adb_path: str = ADB_PATH, device: str = DEVICE):
        self.adb_path = adb_path
        self.device = device

    # ---- low-level adb shell ----
    def shell(self, cmd: str, timeout: int = 30) -> str:
        full = f'"{self.adb_path}" -s {self.device} shell "{cmd}"'
        try:
            out = subprocess.check_output(full, stderr=subprocess.STDOUT, shell=True, timeout=timeout)
            return out.decode("utf-8", errors="replace")
        except subprocess.CalledProcessError as e:
            return e.output.decode("utf-8", errors="replace")

    def shell_async(self, cmd: str):
        full = f'"{self.adb_path}" -s {self.device} shell "{cmd}"'
        return subprocess.Popen(full, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)

    # ---- screen / navigation ----
    def screenshot(self, dst: str):
        """Take a screenshot, pull it to dst (host path)."""
        remote = "/sdcard/_ui_dump.png"
        self.shell(f"screencap -p {remote}")
        full = f'"{self.adb_path}" -s {self.device} pull {remote} "{dst}"'
        out = subprocess.check_output(full, shell=True, stderr=subprocess.STDOUT)
        return out.decode("utf-8", errors="replace")

    def dump_ui(self) -> str:
        """Run uiautomator dump and read the XML content."""
        remote = "/sdcard/window_dump.xml"
        # uiautomator may fail intermittently if window is busy
        for _ in range(3):
            out = self.shell(f"uiautomator dump {remote}")
            if "UI hierchary dumped to" in out or "success" in out.lower():
                break
            time.sleep(0.5)
        # Pull via cat instead of file pull (faster)
        xml = self.shell(f"cat {remote}")
        # uiautomator dump XML is utf-8
        if not xml.startswith("<?xml") and "<hierarchy" not in xml:
            return ""
        return xml

    def tap(self, x: int, y: int):
        self.shell(f"input tap {x} {y}")

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300):
        self.shell(f"input swipe {x1} {y1} {x2} {y2} {duration_ms}")

    def press_back(self):
        self.shell("input keyevent 4")

    def press_home(self):
        self.shell("input keyevent 3")

    def current_focus(self) -> str:
        out = self.shell("dumpsys window | grep mCurrentFocus")
        m = re.search(r"mCurrentFocus=Window\{[^\s]+ \S+ (\S+)/(\S+)", out)
        if m:
            return f"{m.group(1)}/{m.group(2)}"
        return out.strip().splitlines()[-1] if out.strip() else ""


def parse_ui_xml(xml: str) -> list:
    """Return [(text, bounds, resource_id, class, content_desc), ...]."""
    nodes = []
    try:
        root = ET.fromstring(xml)
    except Exception:
        return nodes
    for el in root.iter("node"):
        text = (el.attrib.get("text") or "").strip()
        cd = (el.attrib.get("content-desc") or "").strip()
        rid = el.attrib.get("resource-id") or ""
        cls = el.attrib.get("class") or ""
        bounds = el.attrib.get("bounds") or ""
        if text or cd or rid:
            nodes.append({
                "text": text,
                "content_desc": cd,
                "resource_id": rid,
                "class": cls,
                "bounds": bounds,
            })
    return nodes


def bounds_to_xy(bounds: str):
    """Convert '[x1,y1][x2,y2]' to center (x, y)."""
    m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds)
    if not m:
        return None
    x1, y1, x2, y2 = map(int, m.groups())
    return ((x1 + x2) // 2, (y1 + y2) // 2)


def find_node(nodes: list, *, text: str = None, contains: str = None,
              resource_id: str = None, content_desc: str = None):
    """Find first node matching given criteria."""
    for n in nodes:
        if text is not None and n["text"] == text:
            return n
        if contains is not None and contains in n["text"]:
            return n
        if resource_id is not None and n["resource_id"].endswith(resource_id):
            return n
        if content_desc is not None and n["content_desc"] == content_desc:
            return n
    return None


def wait_for_text(adb: Adb, contains: str, timeout: int = 30, poll: float = 1.0) -> bool:
    """Poll until text shows up in UI dump, returns True if found."""
    end = time.time() + timeout
    while time.time() < end:
        xml = adb.dump_ui()
        if not xml:
            time.sleep(poll)
            continue
        if contains in xml:
            return True
        time.sleep(poll)
    return False


def tap_text(adb: Adb, contains: str, exact: bool = False, timeout: int = 15) -> bool:
    """Find node whose text matches, then tap its center. Returns success."""
    end = time.time() + timeout
    while time.time() < end:
        xml = adb.dump_ui()
        if not xml:
            time.sleep(0.6)
            continue
        nodes = parse_ui_xml(xml)
        if exact:
            n = find_node(nodes, text=contains)
        else:
            n = find_node(nodes, contains=contains)
        if not n:
            time.sleep(0.6)
            continue
        xy = bounds_to_xy(n["bounds"])
        if not xy:
            return False
        adb.tap(*xy)
        return True
    return False


def tap_text_if_present(adb: Adb, contains: str) -> bool:
    """One-shot tap if the text is currently on screen. No wait."""
    xml = adb.dump_ui()
    nodes = parse_ui_xml(xml) if xml else []
    n = find_node(nodes, contains=contains)
    if not n:
        return False
    xy = bounds_to_xy(n["bounds"])
    if not xy:
        return False
    adb.tap(*xy)
    return True


def dump_to_file(adb: Adb, dst: str):
    xml = adb.dump_ui()
    Path(dst).write_text(xml, encoding="utf-8")
    return xml


# --- quick self-test ---
if __name__ == "__main__":
    adb = Adb()
    print("current focus:", adb.current_focus())
    xml = dump_to_file(adb, r"D:\project\jiarenmens\data\recon\ui_state_initial.xml")
    nodes = parse_ui_xml(xml)
    print(f"nodes: {len(nodes)}")
    for n in nodes[:20]:
        print(f"  text={n['text'][:40]!r} bounds={n['bounds']}")