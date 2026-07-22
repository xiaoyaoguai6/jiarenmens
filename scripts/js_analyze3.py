"""Comprehensive analysis of captured JS and HTML data."""
import re, json
from pathlib import Path

# 1. Check capture HTML for data structure
debug = Path("data/debug")
for f in debug.glob("*_html.html"):
    html = f.read_text(encoding="utf-8")
    tables = html.count("<tr") 
    divs_with_data = re.findall(r'data-\w+=', html)
    json_like = re.findall(r'\{[^}]*"(?:code|name|price|profit|ratio|position|stock)"[^}]*\}', html)
    print(f"{f.name}: {len(html)} chars, {tables} <tr>, data-attrs={len(divs_with_data)}, json-like={len(json_like)}")
    if tables > 0:
        tr_section = re.findall(r'<tr[^>]*>.*?</tr>', html, re.DOTALL)
        for tr in tr_section[:3]:
            print(f"  TR: {tr[:200]}")

# 2. Look in main_orig.py for original API approach
orig = Path("main_orig.py")
if orig.exists():
    content = orig.read_text(encoding="utf-16")
    api_lines = [l for i,l in enumerate(content.split('\n')) if ('api' in l.lower() or 'type' in l.lower()) and 'rt_' in l.lower()]
    print("\nmain_orig.py API references:")
    for line in api_lines[:20]:
        print(f"  {line.strip()[:120]}")

# 3. Try the srtV1 endpoint  
print("\n=== Trying srtV1 (signed) endpoint ===")
import requests
s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 EMProjJs-IPhone/EMRead 12.0.0",
    "Referer": "https://groupwap.eastmoney.com",
})
params = {
    "type": "rt_get_rank",
    "rankType": "10005",
    "recIdx": 0,
    "recCnt": 5,
    "rankid": 0,
    "appVer": "9001000",
}
r = s.get("https://emdcspzhapi.dfcfs.cn/srtV1", params=params, timeout=30)
print(f"srtV1 rt_get_rank: result={r.json().get('result')}, msg={r.json().get('message','')[:80]}")
params2 = {
    "type": "rt_zhuhe_yk_new",
    "zjzh": "900113132",
    "appVer": "9001000",
}
r = s.get("https://emdcspzhapi.dfcfs.cn/rtV1", params=params2, timeout=30)
print(f"rtV1 rt_zhuhe_yk_new: result={r.json().get('result')}, msg={r.json().get('message','')[:80]}")
