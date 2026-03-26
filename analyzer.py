import csv
import json
import requests
import threading
import time
from datetime import datetime, timezone

flag = True

url = 'https://game-arkre-labs.ecchi.xxx/Router/RouterHandler.ashx'

headers = {
    'Content-Type': 'application/octet-stream',
    'User-Agent': 'UnityPlayer/2022.3.62f2 (UnityWebRequest/1.0, libcurl/8.10.1-DEV)'
}

payload_player = {
    'data': {
        'TargetCUID': 0,
        'TargetID': '',
        'AID': '',
        'SessionID': ''
    },
    # Full guild war data
    'route': 'GuildWarHandler.QueryGuildWarBattleLogListByAccount'
    # Battle log details
    #'route': 'GuildWarHandler.QueryGuildWarBattleLogByID'
}

payload_guild = {
    'data': {
        'GuildID': '',
        'AID': '',
        'SessionID': ''
    },
    'route': 'GuildHandler.QueryPartialGuildDataForGuildWar'
}

routes = [
    'GuildWarHandler.QueryFullGuildWarData',
    'GuildHandler.QueryPartialGuildDataForGuildWar',
    'AccountHandler.QueryPlayerCardData',
]

def process(flow):
    global flag, payload
    if not flag:
        return
    if not flow.response:
        return
    if 'RouterHandler.ashx' not in flow.request.url:
        return

    try:
        req = json.loads(flow.request.content.decode('utf-8'))
    except Exception:
        return
    if req['route'] not in routes:
        return

    try:
        data = json.loads(flow.response.content.decode('utf-8'))
    except Exception:
        return

    flag = False

    # Modify global payload
    #payload_player['data'] = payload_guild['data'] = req['data']
    payload_player['data']['AID'] = req['data']['AID']
    payload_guild['data']['AID'] = req['data']['AID']
    payload_player['data']['SessionID'] = req['data']['SessionID']
    payload_guild['data']['SessionID'] = req['data']['SessionID']

    threading.Thread(target=analyze, args=(data,), daemon=True).start()

def response(flow):
    process(flow)

def analyze(data):
    if 'GuildWarData' in data:
        # Query from self guild
        plist = data['GuildWarData']['MyCampData']['PlayerInfoList']
    elif 'GuidData' in data:
        # Query from ranking list
        plist = data['GuildData']['MemberList']
    else:
        # Query from player card
        ginfo = data['BattleSupportData']['PlayerInfo']['GuildSubInfo']
        gid = ginfo['_id']['$oid']
        data = analyze_guid(gid)
        print(data)
        plist = data['GuildData']['MemberList']
    rows = []

    for player in plist:
        pinfo = player['PlayerInfo']
        cuid = pinfo['CUID']
        name = pinfo['Name']
        iap = pinfo['IAP'] if 'IAP' in pinfo else None
        # Fetch battle logs for this player
        time.sleep(1)
        logs = analyze_player(cuid, name, iap)
        rows += parse_battle_logs(logs, cuid, name)

    # Sort rows by date and cuid
    rows.sort(key=lambda x: (x['date'], x['cuid']))
    fieldnames = ['date', 'cuid', 'name', 'is_attack', 'battle_id', 'win', 
                  'guild', 'enemy_cuid', 'enemy_name', 'enemy_guild']

    with open('summary.csv', 'w', newline='', encoding='utf-8-sig') as fp:
        w = csv.DictWriter(fp, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f'Saved: summary.csv (rows={len(rows)})')

def analyze_guid(gid):
    payload_guild['data']['GuildID'] = gid
    # Disable warnings
    requests.packages.urllib3.disable_warnings()
    resp = requests.post(url, json=payload_guild, headers=headers, verify=False)
    resp.encoding = 'utf-8'
    data = resp.json()
    return data

def analyze_player(cuid, name, iap):
    payload_player['data']['TargetCUID'] = cuid
    print(f'{cuid}-{name}' + (f'-{iap}' if iap else ''))
    # Disable warnings
    requests.packages.urllib3.disable_warnings()
    resp = requests.post(url, json=payload_player, headers=headers, 
                         verify=False)
    resp.encoding = 'utf-8'
    data = resp.json()
    return data

def parse_battle_logs(logs, cuid, name):
    log_list, rows = logs['SubLogs'], []
    for item in log_list:
        battle_id = item['_id']

        ts = item['StartTime']['$date']
        dt_utc = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        dt_str = dt_utc.strftime('%Y-%m-%d')

        # The player is attacker
        if item['AttackerPlayerInfo']['CUID'] == cuid:
            is_attack = True
            win = item['AttackerResult']['Result']
            # Check self guild
            if 'GuildSubInfo' in item['AttackerPlayerInfo']:
                guild = item['AttackerPlayerInfo']['GuildSubInfo']['Name']
            else:
                guild = ''
            enemy_name = item['DefenderPlayerInfo']['Name']
            enemy_cuid = item['DefenderPlayerInfo']['CUID']
            # Check enemy guild
            if 'GuildSubInfo' in item['DefenderPlayerInfo']:
                enemy_guild = item['DefenderPlayerInfo']['GuildSubInfo']['Name']
            else:
                enemy_guild = ''
        else:
            is_attack = False
            win = item['DefenderResult']['Result']
            if 'GuildSubInfo' in item['DefenderPlayerInfo']:
                guild = item['DefenderPlayerInfo']['GuildSubInfo']['Name']
            else:
                guild = ''
            enemy_name = item['AttackerPlayerInfo']['Name']
            enemy_cuid = item['AttackerPlayerInfo']['CUID']
            if 'GuildSubInfo' in item['AttackerPlayerInfo']:
                enemy_guild = item['AttackerPlayerInfo']['GuildSubInfo']['Name']
            else:
                enemy_guild = ''

        if win == 'Win':
            win = 2
        elif win == 'Lose':
            win = 0
        else:
            win = 1

        rows.append({
            'date': dt_str,
            'cuid': cuid,
            'name': name,
            'is_attack': is_attack,
            'battle_id': battle_id,
            'win': win,
            'guild': guild,
            'enemy_cuid': enemy_cuid,
            'enemy_name': enemy_name,
            'enemy_guild': enemy_guild
        })

    return rows
