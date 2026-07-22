import requests, json
base = 'https://spzhapi.eastmoney.com/rtV1'
headers = {
    'Accept-Encoding': 'gzip',
    'EM-CHL': 'taobao45',
    'EM-CT': '',
    'EM-GT': 'cean-cce6b56eac83e024ef690e55d3bf23ce',
    'EM-GV': 'c82971043',
    'EM-MD': 'YjUyMTZhY2UzZGE4MGYxY2MzYzQ4ODVmNTQwYzdkN2F8fDM0NTgxODQyMDMyNTg1Mw==',
    'EM-OS': 'Android',
    'EM-PA': '1',
    'EM-PKG': 'com.eastmoney.android.newyork',
    'EM-SL': '0',
    'EM-UT': '',
    'EM-VER': '10.13.5',
    'Host': 'spzhapi.eastmoney.com',
    'User-Agent': 'okhttp/3.12.13',
}

# test 1: same zhid (sanity replay)
r = requests.get(base, params={'appVer':'10013005','type':'rt_hold_detail86','zh':'900235873'}, headers=headers, timeout=15)
print('--- rt_hold_detail86 zh=900235873 ---')
print('status', r.status_code, 'len', len(r.text))
try:
    j = r.json()
    print('result:', j.get('result'), 'msg:', j.get('message'), 'listSize:', j.get('listSize'))
    if j.get('data'):
        for sec in j['data'][:3]:
            print(f'  sector {sec["BlockName"]} ({sec["blkRatio"]}%) n_data={len(sec["data"])}')
            for s in sec['data'][:2]:
                print(f'     -> {s["__code"]} {s["__name"]} cbj={s["cbj"]} zxjg={s["__zxjg"]} yk={s["webYkRate"]}% pos={s["holdPos"]}%')
except Exception as e:
    print('err', e, 'text:', r.text[:500])

# test 2: try DIFFERENT zhid (900083077 -- 晒网打大)
print('--- rt_hold_detail86 zh=900083077 ---')
r2 = requests.get(base, params={'appVer':'10013005','type':'rt_hold_detail86','zh':'900083077'}, headers=headers, timeout=15)
print('status', r2.status_code, 'len', len(r2.text))
try:
    j2 = r2.json()
    print('result:', j2.get('result'), 'listSize:', j2.get('listSize'))
    if j2.get('data'):
        for sec in j2['data'][:3]:
            print(f'  {sec["BlockName"]} ({sec["blkRatio"]}%) n={len(sec["data"])}')
except Exception as e:
    print('err', e, r2.text[:300])

# test 3: try with EMPTY/BAD EM-MD to see if they check identity
print('--- EM-MD empty ---')
h3 = dict(headers); h3['EM-MD'] = ''
r3 = requests.get(base, params={'appVer':'10013005','type':'rt_hold_detail86','zh':'900083077'}, headers=h3, timeout=15)
print('status', r3.status_code, 'len', len(r3.text))
try:
    j3 = r3.json()
    print('result:', j3.get('result'), 'listSize:', j3.get('listSize'), 'msg:', j3.get('message'))
except:
    print(r3.text[:300])

# test 4: try stripped headers (minimal) to see what's mandatory
print('--- minimal headers only User-Agent ---')
h4 = {'User-Agent': 'okhttp/3.12.13'}
r4 = requests.get(base, params={'appVer':'10013005','type':'rt_hold_detail86','zh':'900083077'}, headers=h4, timeout=15)
print('status', r4.status_code, 'len', len(r4.text))
try:
    j4 = r4.json()
    print('result:', j4.get('result'), 'listSize:', j4.get('listSize'), 'msg:', j4.get('message'))
except:
    print(r4.text[:300])
