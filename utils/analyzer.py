from datetime import datetime, timezone
import csv
import json
import random
import requests
import time

requests.packages.urllib3.disable_warnings()

url = 'https://game-arkre-labs.ecchi.xxx/Router/RouterHandler.ashx'
headers = {
    'Content-Type': 'application/octet-stream',
    'User-Agent': 'UnityPlayer/2022.3.62f2 (UnityWebRequest/1.0, libcurl/8.10.1-DEV)'
}

def analyze_hits(data, aid, session_id):
    if 'GuildWarData' in data: # 从自己公会查询
        plist = data['GuildWarData']['MyCampData']['PlayerInfoList']
        guild_name = data['GuildWarData']['MyCampData']['GuildInfo']['Name']
    else: # 从好友/排行榜/公会ID查询
        plist = data['GuildData']['MemberList']
        guild_name = data['GuildData']['Info']['Name']
    rows = []

    for player in plist:
        pinfo = player['PlayerInfo']
        cuid = pinfo['CUID']
        name = pinfo['Name']
        iap = pinfo['IAP'] if 'IAP' in pinfo else None
        # Fetch battle logs for this player
        try:
            logs = analyze_player(aid, session_id, cuid, name, iap)
            rows += parse_battle_logs(logs, cuid, name)
        except Exception as e:
            print(f'{cuid}-{name}获取失败: {e}')
            continue

    # Sort rows by date and cuid
    rows.sort(key=lambda x: (x['date'], x['cuid']))
    fieldnames = ['date', 'cuid', 'name', 'is_attack', 'battle_id', 'win', 
                  'guild', 'enemy_cuid', 'enemy_name', 'enemy_guild']

    # CSV filename
    dt_str = datetime.now().strftime('%Y-%m-%d')
    filename = f'{dt_str} {guild_name}团战总结.csv'
    with open(filename, 'w', newline='', encoding='utf-8-sig') as fp:
        w = csv.DictWriter(fp, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f'Saved: {filename} (rows={len(rows)})')

def analyze_player(aid, session_id, cuid, name, iap):
    payload = {
        'data': {
            'TargetCUID': cuid,
            'AID': aid,
            'SessionID': session_id
        },
        'route': 'GuildWarHandler.QueryGuildWarBattleLogListByAccount'
    }
    print(f'{cuid}-{name}' + (f'-{iap}' if iap else ''))
    time.sleep(random.uniform(1, 2))
    resp = requests.post(url, json=payload, headers=headers, verify=False)
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
