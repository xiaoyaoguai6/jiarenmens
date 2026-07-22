import sys, re
print('--- encoding hint: ---')
with open(r'D:\project\jiarenmens\data\recon\ui_ny_now.xml', 'r', encoding='utf-8') as f:
    xml = f.read()
print('len:', len(xml), '地方含实盘榜单:', '实盘榜单' in xml)
# Find clickable=true nodes and their text attribute (anywhere in the attrs block)
clickable_blocks = re.findall(r'<node[^>]*clickable="true"[^>]*>', xml)
print('found clickable blocks:', len(clickable_blocks))
# Walk each block, extract text=, bounds=, content-desc=
shown = 0
for blk in clickable_blocks:
    txt = re.search(r'text="([^"]*)"', blk)
    bnd = re.search(r'bounds="([^"]*)"', blk)
    cd = re.search(r'content-desc="([^"]*)"', blk)
    rid = re.search(r'resource-id="([^"]*)"', blk)
    text = txt.group(1) if txt else ''
    bounds = bnd.group(1) if bnd else ''
    desc = cd.group(1) if cd else ''
    rid_s = rid.group(1) if rid else ''
    if text or desc or rid_s:
        print(f'  text={text[:30]:32s} desc={desc[:30]:32s} rid={rid_s[-40:]:42s} bounds={bounds}')
        shown += 1
        if shown >= 30: break
