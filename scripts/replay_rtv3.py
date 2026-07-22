"""Replay captured rtV3 request against the same zhid (900296556) to verify
token-based auth (stateless re-use without needing to re-sign).

If it returns the same stock list, we've verified:
1. The endpoint is replicated with captured tokens verbatim,
2. There's no per-request HMAC/signature on rtV3 (only `sign` header on
   certain endpoints — let's verify by sending with/without sign).
"""
import json
import random
import string
import time

import requests

# Stash of values captured by mitmproxy from user's session.
CT_TOKEN = ("B2Ap3vErhpdGrGYg5NYMdBeZptzkEAxIWa78HkFfGbtaTwdGqCZfqFbT68i6g5Yji"
            "Pm40ztnmCs7jhl-EH1pGtMW64hIspTmuqkDFIS58yl9lT1MsmWhn486KQx2doTalRb"
            "azyxKCqs-D_L_lny5dPz-az4ndgd55dCaNiKXOok")
UT_TOKEN = ("FobyicMgeV41pekRygl4kcB4zNQ_e4LuRS8h1Mcj_vG430C-yVSZHT6ZD7ECNUXqA"
            "ocFSR9WJhyjrPmhI7O4dTBFzJZ-O6MKr1_n3Cq07vZ_aiVg1M1hYGTwAHXswED8h0IJ"
            "ZFUenhhq-oOtOyjZH-HHXcr-nzNXHDL_d_-Zkqr36Cv2zjqNmVxbQIXGGPUQ4vhZ-GZ"
            "yI4rakK7INbwwyn_HGZ7R9SoMJwFigidGUyKROn-PJz8mwNgbeu6QBDsKJfxxGYxWl"
            "_w3pbqQOFADijSYZ7slPRh5zjEgwmk6_nYMc5Qw9vPMwZf_kXKVc1F5FtefzlRM1PY"
            "wNCz3zpADZTPUkLrfoRmYhB2NojqdxPbsoYEw6WtgsjJN6lRoMafT")
USER_ID = "8953027422282872"
DEVICE_ID = "9e15d94609c60d80e1cf717c079b402c||iemi_tluafed_me"

ENDPOINT = "https://spzhapi.dfcfs.cn/rtV3"


def make_random_code():
    ts = time.strftime("%H%M%S", time.localtime())
    rnd = "".join(random.choices(string.ascii_letters + string.digits, k=25))
    return f"{ts}{rnd}"


def call(zhid: str, method: str, extra_args: dict | None = None):
    args = {
        "ctToken": CT_TOKEN,
        "utToken": UT_TOKEN,
        "userId": USER_ID,
        "combinationId": zhid,
    }
    if extra_args:
        args.update(extra_args)
    body = {
        "args": args,
        "method": method,
        "client": "android",
        "randomCode": make_random_code(),
        "timestamp": int(time.time() * 1000),
        "deviceId": DEVICE_ID,
        "clientType": "cfw",
        "clientVersion": "11.1.5",
    }
    headers = {
        "accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "User-Agent": "okhttp/3.12.13",
        "Host": "spzhapi.dfcfs.cn",
        "Connection": "Keep-Alive",
        "Accept-Encoding": "gzip",
        "appversion": "11.1.5",
        "rnversion": "2.2.0.260626112525513",
    }
    r = requests.post(ENDPOINT, headers=headers, json=body, timeout=15)
    print(f"-> method={method} zhid={zhid} status={r.status_code} bytes={len(r.content)}")
    try:
        j = r.json()
        print(json.dumps(j, ensure_ascii=False, indent=2)[:1500])
        return j
    except Exception as e:
        print("non-JSON:", r.text[:500], "err:", e)
        return None


if __name__ == "__main__":
    # Step 1: replay against the same zhid we already saw succeed in the capture.
    print("\n=== Replay 900296556 CombinationHoldPositionPermitHandler ===")
    call("900296556", "CombinationHoldPositionPermitHandler")

    # Step 2: now WITHOUT captured sign header — verify no signature required
    #         (the response already implies sign is server-side optional/lax).
    print("\n=== Try a DIFFERENT zhid (900013608, from older DB) ===")
    call("900013608", "CombinationHoldPositionPermitHandler")
    print("\n=== Try CombinationInfoHandler for the same zhid ===")
    call("900296556", "CombinationInfoHandler")
    print("\n=== Try CombinationRelocatePositionHandler for the same zhid ===")
    call("900296556", "CombinationRelocatePositionHandler",
         extra_args={"pageNum": 1, "pageSize": 50, "isLastDay": True})