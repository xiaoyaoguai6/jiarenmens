import requests, json

s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0"})

zh = "900113132"

# Try push2em for zuhe (combination portfolio) data
print("=== push2em zuhe APIs ===")
urls = [
    "https://push2em.eastmoney.com/em/zuheV64/JS.aspx?type=get&zh=" + zh,
    "https://push2em.eastmoney.com/em/zuheV64/JS.aspx?type=getPosition&zh=" + zh,
    "https://push2em.eastmoney.com/em/zuheV64/JS.aspx?type=getTrade&zh=" + zh,
    "https://push2.eastmoney.com/api/qt/zsxj/get?fs=m:1+t:2",
]
for url in urls:
    try:
        r = s.get(url, timeout=30)
        preview = r.text[:300]
        print(f"  {url[:100]}: status={r.status_code}, len={len(r.text)}, preview={preview}")
    except Exception as e:
        print(f"  {url[:100]}: ERROR: {e}")

# Try with post to push2em
print()
print("=== push2em POST ===")
r = s.post("https://push2em.eastmoney.com/em/zuheV64/JS.aspx", data={
    "type": "get",
    "zh": zh,
}, timeout=30)
print(f"  POST: status={r.status_code}, text[0:300]={r.text[:300]}")

# Try jsonp format
print()
print("=== JSONP format ===")
r = s.get("https://push2em.eastmoney.com/em/zuheV64/JS.aspx", params={
    "type": "get",
    "zh": zh,
    "callback": "jQuery",
}, timeout=30)
print(f"  callback: status={r.status_code}, text[0:300]={r.text[:300]}")

# Try data.eastmoney.com for shipan data
print()
print("=== data.eastmoney.com ===")
r = s.get("https://data.eastmoney.com/stockdata/" + zh + ".html", timeout=30)
print(f"  stockdata: status={r.status_code}, len={len(r.text)}")

# Try guba.eastmoney.com/list/zuhe
print()
print("=== guba.eastmoney.com zuhe ===")
r = s.get("https://guba.eastmoney.com/list/zuhe," + zh + ".html", timeout=30)
print(f"  guba zuhe: status={r.status_code}, len={len(r.text)}")
