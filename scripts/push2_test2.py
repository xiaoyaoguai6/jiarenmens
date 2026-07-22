import requests
import sys
import io

# Fix encoding for Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0"})

zh = "900113132"

# Get all 3 page types from push2em
for ptype in ["get", "getPosition", "getTrade"]:
    url = f"https://push2em.eastmoney.com/em/zuheV64/JS.aspx?type={ptype}&zh={zh}"
    try:
        r = s.get(url, timeout=30)
        # Set encoding properly
        r.encoding = r.apparent_encoding or 'gb2312'
        text = r.text
        
        print(f"\n=== type={ptype} | status={r.status_code} | len={len(text)} ===")
        # Look for key data patterns
        if "table" in text.lower():
            print("  Contains TABLE elements")
        if "持仓" in text:
            print("  Contains 持仓")
        if "调仓" in text:
            print("  Contains 调仓")
        if "stock" in text.lower():
            print("  Contains stock")
        # Print first 500 chars
        print(f"  Preview:{text[:500]}")
        
        # Save to file
        with open(f"D:\\project\\jiarenmens\\data\\debug\\push2em_{ptype}.html", "w", encoding="utf-8") as f:
            f.write(text)
    except Exception as e:
        print(f"\n=== type={ptype} | ERROR: {e} ===")

# Also try detail and change pages
print("\n=== detail page ===")
for ptype in ["getDetail", "detail", "get"]:
    url = f"https://push2em.eastmoney.com/em/zuheV64/JS.aspx?type={ptype}&zh={zh}"
    try:
        r = s.get(url, timeout=30)
        r.encoding = r.apparent_encoding or 'gb2312'
        print(f"  type={ptype}: status={r.status_code}, len={len(r.text)}, preview={r.text[:200]}")
    except Exception as e:
        print(f"  type={ptype}: ERROR: {e}")
