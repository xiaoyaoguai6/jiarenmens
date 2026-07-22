# -*- coding: utf-8 -*-
"""Implement TripleDES cipher and test emstockdiag gateway for combo/position/trade data."""
import sys, io, requests, json, time, binascii
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from pyDes import triple_des, ECB, PAD_PKCS5

# Key from JS: b154054573c72ecd66ab57b1e35c0671 (32 hex = 16 bytes)
KEY_HEX = "b154054573c72ecd66ab57b1e35c0671"
KEY_BYTES = binascii.unhexlify(KEY_HEX)  # 16 bytes

def triple_des_encrypt(plaintext, key_bytes):
    """Encrypt using 3DES ECB with PKCS5 padding, return hex string."""
    # 3DES needs 16 or 24 byte key
    # 16-byte key = 2-key 3DES: K1|K2|K1
    if len(key_bytes) == 16:
        key_bytes = key_bytes + key_bytes[:8]
    cipher = triple_des(key_bytes, ECB, pad=None, padmode=PAD_PKCS5)
    encrypted = cipher.encrypt(plaintext.encode("utf-8"))
    return binascii.hexlify(encrypted).decode("utf-8")

# Test with captured CID
UID = "2012094520785316"
CAPTURED_CID = "9f69c1bcff839a3202625794b00c75e3"
computed_cid = triple_des_encrypt(UID, KEY_BYTES)
print("UID: %s" % UID)
print("Captured CID: %s" % CAPTURED_CID)
print("Computed CID: %s" % computed_cid)
print("Match: %s" % (computed_cid == CAPTURED_CID))

# If no match, try without padding expansion
if computed_cid != CAPTURED_CID:
    print("\nTrying alternative key formats...")
    # Try raw 16-byte key without expansion
    cipher2 = triple_des(KEY_BYTES, ECB, pad=None, padmode=PAD_PKCS5)
    encrypted2 = cipher2.encrypt(UID.encode("utf-8"))
    alt_cid = binascii.hexlify(encrypted2).decode("utf-8")
    print("Alt CID (no expansion): %s" % alt_cid)
    print("Match: %s" % (alt_cid == CAPTURED_CID))

    # Try with the key as-is (16 bytes, 2-key DES)
    cipher3 = triple_des(KEY_BYTES, ECB)
    encrypted3 = cipher3.encrypt(UID.encode("utf-8"))
    alt_cid2 = binascii.hexlify(encrypted3).decode("utf-8")
    print("Alt CID (auto pad): %s" % alt_cid2)
    print("Match: %s" % (alt_cid2 == CAPTURED_CID))

# Now test emstockdiag gateway with all combo-related paths
CID = computed_cid if computed_cid == CAPTURED_CID else CAPTURED_CID
print("\nUsing CID: %s" % CID)

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://emcreative.eastmoney.com/",
    "Content-Type": "application/json",
})

APPKEY = "a8157f5ef970edda2c103e192b6dc3e5"
PAGE_URL = "https://emcreative.eastmoney.com/app_fortune/person/index.html?uid=%s&anchor=3" % UID

paths_to_try = [
    # Combo/zuhe related
    "v4/mobileadapter/getUserZuHeList",
    "v4/mobileadapter/getUserZuheList",
    "v4/mobileadapter/zuheList",
    "v4/mobileadapter/getZuheList",
    "v4/mobileadapter/getComboList",
    "v4/mobileadapter/comboList",
    # Position related
    "v4/mobileadapter/getZuhePositionList",
    "v4/mobileadapter/getPositionList",
    "v4/mobileadapter/positionList",
    "v4/mobileadapter/zuhePosition",
    "v4/mobileadapter/position",
    # Trade related
    "v4/mobileadapter/getZuheTradeList",
    "v4/mobileadapter/getTradeList",
    "v4/mobileadapter/tradeList",
    "v4/mobileadapter/zuheTrade",
    "v4/mobileadapter/trade",
    "v4/mobileadapter/change",
    # Detail related
    "v4/mobileadapter/getZuheDetail",
    "v4/mobileadapter/getDetail",
    "v4/mobileadapter/detail",
    "v4/mobileadapter/zuheDetail",
    # Stock related
    "v4/mobileadapter/getZuheStockList",
    "v4/mobileadapter/getStockList",
    "v4/mobileadapter/stockList",
    "v4/mobileadapter/zuheStock",
    "v4/mobileadapter/stock",
    # Hold related
    "v4/mobileadapter/getZuheHold",
    "v4/mobileadapter/getHold",
    "v4/mobileadapter/hold",
    "v4/mobileadapter/holding",
    # Info related
    "v4/mobileadapter/getZuheInfo",
    "v4/mobileadapter/getInfo",
    "v4/mobileadapter/info",
    "v4/mobileadapter/zuheInfo",
    # User info
    "v4/mobileadapter/getUserInfo",
    "v4/mobileadapter/userInfo",
    "v4/mobileadapter/user",
    # With cid in parm
    "v4/mobileadapter/gszcount",
    # Query privacy
    "v4/mobile/query-privacy-config",
    "v4/mobile_anonym/query-privacy-config",
]

print("\n=== Testing emstockdiag paths ===")
found = []
for path in paths_to_try:
    try:
        body = {
            "path": path,
            "parm": json.dumps({"cid": CID}),
            "header": {
                "appkey": APPKEY,
                "Referer": "http://www.eastmoney.com",
                "ut": "", "ct": "", "MyFavorVer": "",
            },
            "track": "sys_%d" % int(time.time() * 1000),
            "pageUrl": PAGE_URL,
        }
        r = s.post("https://emstockdiag.eastmoney.com/apistock/Tran/GetData",
                    json=body, timeout=10)
        d = r.json()
        rdata = d.get("RData", "")
        rcode = d.get("RCode", 0)
        if rcode == 200 and rdata:
            inner = json.loads(rdata)
            state = inner.get("state", -1)
            msg = inner.get("message", "")
            data = inner.get("data")
            if state == 0 and data:
                print("  ** %s => state=0, data=%s" % (path, json.dumps(data, ensure_ascii=False)[:300]))
                found.append(path)
            elif state != -1 and state != 0:
                print("     %s => state=%s, msg=%s" % (path, state, msg[:80]))
    except Exception as e:
        pass

if not found:
    print("  No paths returned data")

print("\n=== Found working paths ===")
for f in found:
    print("  %s" % f)

print("\nDone!")
