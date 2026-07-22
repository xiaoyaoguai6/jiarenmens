
import requests, json, time

ZH_ID = '900013608'
UID = '2012094520785316'
UA_APP = 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 EMProjJs-IPhone/EMRead 12.0.0 (em_appid/200)'
UA_PC = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

s_app = requests.Session()
s_app.headers.update({'User-Agent': UA_APP, 'Referer': 'https://groupwap.eastmoney.com'})
s_pc = requests.Session()
s_pc.headers.update({'User-Agent': UA_PC, 'Referer': 'https://www.eastmoney.com/'})

print('='*70)
print('ALL-IN-ONE POSITION DATA TEST')
print('='*70)

# TEST 1: rtV1 new type names
print()
print('>> TEST 1: rtV1 - many new type names')
print('-'*60)
types = [
    'rt_get_zuhe_detail','rt_get_zuhe_info','rt_get_zuhe_position',
    'rt_get_zuhe_change','rt_get_zuhe_trade','rt_get_zuhe_stock',
    'rt_get_zuhe_list','rt_get_zuhe_hold','rt_get_zuhe_stocklist',
    'rt_get_real_position','rt_get_real_stock','rt_get_real_hold',
    'rt_get_real_detail','rt_get_real_info','rt_get_real_trade',
    'rt_get_cb_position','rt_get_cb_stock','rt_get_cb_trade',
    'rt_get_cb_change','rt_get_cb_detail','rt_get_cb_hold',
    'rt_position','rt_info','rt_detail','rt_stock','rt_trade',
    'rt_hold','rt_change','rt_stocklist',
    'rt_player_position','rt_player_stock','rt_player_detail',
    'rt_player_info','rt_player_trade','rt_player_change',
    'rt_player_hold','rt_player_asset',
    'rt_group_position','rt_group_stock','rt_group_detail',
    'rt_group_trade','rt_group_change','rt_group_hold',
    'rt_combo_position','rt_combo_stock','rt_combo_detail',
    'rt_combo_trade','rt_combo_change',
    'rt_get_holdings','rt_get_hold_detail','rt_get_hold_stocklist',
    'rt_get_position_list','rt_get_stock_list',
    'rt_get_concern_detail','rt_get_concern_position',
    'rt_get_user_position','rt_get_user_stock',
    'rt_get_zjzh_position','rt_get_zjzh_stock','rt_get_zjzh_detail',
]
found1 = []
for t in types:
    try:
        resp = s_app.get('https://emdcspzhapi.dfcfs.cn/rtV1', params={'type': t, 'zh': ZH_ID, 'appVer': '9001000'}, timeout=5)
        d = resp.json()
        r = d.get('result', '')
        if r != '-10000':
            found1.append((t, r, json.dumps(d, ensure_ascii=False)[:300]))
            print('  [HIT!] type=%s result=%s' % (t, r))
            print('  data=%s' % json.dumps(d, ensure_ascii=False)[:300])
    except:
        pass
if found1:
    print('FOUND %d working types!' % len(found1))
else:
    print('No working types found.')

# TEST 2: rtV1 param combos
print()
print('>> TEST 2: rtV1 - param combos')
print('-'*60)
param_combos = [
    {'zjzh': ZH_ID},
    {'zh': ZH_ID, 'uid': UID},
    {'zjzh': ZH_ID, 'uid': UID},
    {'zjzh': ZH_ID, 'deviceid': 'test123', 'plat': '1'},
    {'zh': ZH_ID, 'deviceid': 'test123'},
    {'zh': ZH_ID, 'userid': UID},
    {'zjzh': ZH_ID, 'userid': UID},
]
for t in ['rt_get_position','rt_get_info','rt_get_detail','rt_get_stock','rt_get_trade','rt_get_change','rt_get_hold']:
    for p in param_combos:
        try:
            resp = s_app.get('https://emdcspzhapi.dfcfs.cn/rtV1', params={'type': t, 'appVer': '9001000', **p}, timeout=5)
            d = resp.json()
            if d.get('result', '') != '-10000':
                print('  [HIT!] type=%s params=%s => %s' % (t, p, json.dumps(d, ensure_ascii=False)[:200]))
        except:
            pass

# TEST 3: srtV1
print()
print('>> TEST 3: srtV1')
print('-'*60)
for t in ['srt_get_position','srt_get_detail','srt_get_stock','srt_get_info','srt_get_trade','rt_get_position','rt_get_info','rt_get_detail']:
    try:
        resp = s_app.get('https://emdcspzhapi.dfcfs.cn/srtV1', params={'type': t, 'zh': ZH_ID, 'appVer': '9001000'}, timeout=5)
        d = resp.json()
        if d.get('result', '') != '-10000':
            print('  [HIT!] srtV1 type=%s => %s' % (t, json.dumps(d, ensure_ascii=False)[:200]))
    except:
        pass

# TEST 4: web2 zuhe
print()
print('>> TEST 4: web2.eastmoney.com zuhe')
print('-'*60)
for url in [
    'https://web2.eastmoney.com/zuhe/API/ZuheInfo.aspx?ZH=%s' % ZH_ID,
    'https://web2.eastmoney.com/zuhe/API/ZuhePosition.aspx?ZH=%s' % ZH_ID,
    'https://web2.eastmoney.com/zuhe/API/ZuheStock.aspx?ZH=%s' % ZH_ID,
    'https://web2.eastmoney.com/zuhe/JS.aspx?type=9&ZH=%s' % ZH_ID,
    'https://web2.eastmoney.com/zuhe/JS.aspx?type=1&ZH=%s' % ZH_ID,
    'https://web2.eastmoney.com/zuhe/JS.aspx?type=2&ZH=%s' % ZH_ID,
    'https://web2.eastmoney.com/zuhe/JS.aspx?type=3&ZH=%s' % ZH_ID,
    'https://web2.eastmoney.com/zuhe/JS.aspx?type=4&ZH=%s' % ZH_ID,
]:
    try:
        resp = s_pc.get(url, timeout=10)
        short = url.split('.cn')[1][:70] if '.cn' in url else url[-70:]
        print('  %s => Status=%d Len=%d' % (short, resp.status_code, len(resp.text)))
        if len(resp.text) > 30:
            gbk = resp.content.decode('gbk', errors='replace')[:200]
            print('    GBK: %s' % gbk)
    except Exception as e:
        print('    Error: %s' % e)

# TEST 5: POST
print()
print('>> TEST 5: POST to rtV1')
print('-'*60)
try:
    resp = s_app.post('https://emdcspzhapi.dfcfs.cn/rtV1', json={'type': 'rt_get_position', 'zh': ZH_ID, 'appVer': '9001000'}, timeout=10)
    print('  POST JSON: Status=%d Len=%d' % (resp.status_code, len(resp.text)))
    print('  Body: %s' % resp.text[:300])
except Exception as e:
    print('  Error: %s' % e)

# TEST 6: push2
print()
print('>> TEST 6: push2.eastmoney.com')
print('-'*60)
for url in [
    'https://push2.eastmoney.com/api/qt/stock/get?secid=90.%s&fields=f57,f58,f43,f169,f170' % ZH_ID,
    'https://push2.eastmoney.com/api/qt/slist/get?spt=90&ids=%s&fields=f12,f14' % ZH_ID,
]:
    try:
        resp = s_pc.get(url, timeout=10)
        print('  Status=%d Len=%d' % (resp.status_code, len(resp.text)))
        if resp.status_code == 200:
            try:
                d = resp.json()
                print('  %s' % json.dumps(d, ensure_ascii=False)[:300])
            except:
                print('  %s' % resp.text[:200])
    except Exception as e:
        print('  Error: %s' % e)

# TEST 7: datacenter
print()
print('>> TEST 7: datacenter-web')
print('-'*60)
for rn in ['RPT_REAL_COMBOSTOCK','RPT_REAL_PLAYER','RPT_ZH_COMBOSTOCK','RPT_PORTFOLIO_STOCK','RPT_SHIPAN_STOCK','RPT_ZUHE_DETAIL','RPT_COMBOSTOCK']:
    try:
        url = 'https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=%s&columns=ALL&filter=(ZH_ID=%%22%s%%22)&pageSize=5' % (rn, ZH_ID)
        resp = s_pc.get(url, timeout=10)
        d = resp.json()
        print('  %s: success=%s code=%s' % (rn, d.get('success'), d.get('code')))
        if d.get('result'):
            print('    RESULT: %s' % json.dumps(d['result'], ensure_ascii=False)[:300])
    except Exception as e:
        print('  Error: %s' % e)

# TEST 8: groupwap API paths
print()
print('>> TEST 8: groupwap API paths')
print('-'*60)
s_gw = requests.Session()
s_gw.headers.update({'User-Agent': UA_APP, 'Referer': 'https://groupwap.eastmoney.com/group/reality/info.html'})
for url in [
    'https://groupwap.eastmoney.com/group/api/getPosition?zh=%s' % ZH_ID,
    'https://groupwap.eastmoney.com/group/api/getInfo?zh=%s' % ZH_ID,
    'https://groupwap.eastmoney.com/group/invest/api/getPosition?zh=%s' % ZH_ID,
    'https://groupwap.eastmoney.com/group/reality/api/getPosition?zh=%s' % ZH_ID,
    'https://groupwap.eastmoney.com/group/reality/api/getInfo?zh=%s' % ZH_ID,
    'https://groupwap.eastmoney.com/group/invest/api/detail?zh=%s' % ZH_ID,
]:
    try:
        resp = s_gw.get(url, timeout=10)
        short = url.split('.com')[1][:60]
        print('  %s => Status=%d Len=%d' % (short, resp.status_code, len(resp.text)))
        if resp.status_code == 200 and len(resp.text) > 10:
            print('    %s' % resp.text[:200])
    except Exception as e:
        print('  Error: %s' % e)

# TEST 9: rank record structure
print()
print('>> TEST 9: Full rank record structure')
print('-'*60)
resp = s_app.get('https://emdcspzhapi.dfcfs.cn/rtV1', params={
    'type': 'rt_get_rank', 'rankType': '10004', 'recIdx': 0, 'recCnt': 1, 'rankid': 0, 'appVer': '9001000'
}, timeout=10)
d = resp.json()
if d.get('data'):
    p = d['data'][0]
    print('  Keys: %s' % list(p.keys()))
    print('  Full: %s' % json.dumps(p, ensure_ascii=False))

print()
print('='*70)
print('DONE')
print('='*70)
