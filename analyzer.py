import csv
import json
import requests
import time
from datetime import datetime, timezone
#from mitmproxy.script import concurrent

flag = True

url = 'https://game-arkre-labs.ecchi.xxx/Router/RouterHandler.ashx'

headers = {
    'Content-Type': 'application/octet-stream',
    'User-Agent': 'UnityPlayer/2022.3.62f2 (UnityWebRequest/1.0, libcurl/8.10.1-DEV)'
}

payload = {
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
    if req['route'] != 'GuildWarHandler.QueryFullGuildWarData':
        return

    try:
        data = json.loads(flow.response.content.decode('utf-8'))
    except Exception:
        return

    # Modify global payload
    payload['data'] = req['data']

    analyze(data)

    flag = False

#@concurrent
def response(flow):
    process(flow)

def analyze(data):
    plist = data['GuildWarData']['MyCampData']['PlayerInfoList']
    rows = []

    for player in plist:
        pinfo = player['PlayerInfo']
        cuid = pinfo['CUID']
        name = pinfo['Name']
        # Fetch battle logs for this player
        time.sleep(1)
        logs = analyze_player(cuid)
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

def analyze_player(cuid):
    payload['data']['TargetCUID'] = cuid
    print(payload['data']['TargetCUID'])
    resp = requests.post(url, json=payload, headers=headers)
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
