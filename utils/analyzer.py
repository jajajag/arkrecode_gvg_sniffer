from datetime import datetime, timezone
from .helper import *
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

def analyze_guild(data, aid, session_id, save_csv=True):
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
    if save_csv:
        with open(filename, 'w', newline='', encoding='utf-8-sig') as fp:
            w = csv.DictWriter(fp, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows)
        print(f'Saved: {filename} (rows={len(rows)})')

    return rows

def analyze_player(aid, session_id, cuid, name, iap=None):
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
    return resp.json()

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

def analyze_hit(aid, session_id, cuid, battle_id):
    payload = {
        'data': {
            'TargetCUID': cuid,
            'TargetID': battle_id,
            'AID': aid,
            'SessionID': session_id
        },
        'route': 'GuildWarHandler.QueryGuildWarBattleLogByID'
    }
    time.sleep(random.uniform(1, 2))
    resp = requests.post(url, json=payload, headers=headers, verify=False)
    resp.encoding = 'utf-8'
    return resp.json()

def analyze_defence(aid, session_id, cuid, rows):
    filename, seen, new_rows = '团战防守.csv', set(), []

    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8-sig') as f:
            for r in csv.DictReader(f):
                seen.add(r['battle_id'])

    for row in rows:
        if row['is_attack']: continue
        if row['battle_id'] in seen: continue
        try:
            logs = analyze_hit(aid, session_id, cuid, row['battle_id'])
            new_rows += parse_def_logs(logs)
            seen.add(row['battle_id'])
        except Exception as e:
            print(f"battle {row['battle_id']} 获取失败: {e}")

    # Sort rows by date
    new_rows.sort(key=lambda x: (x['date'], x['battle_id']))
    fieldnames = ['date', 'def_1', 'def_2', 'def_3', 'atk_1', 'atk_2', 'atk_3',
                  'win', 'dead', 'def_cuid', 'def_name', 'def_guild',
                  'atk_cuid', 'atk_name', 'atk_guild', 'battle_id']

    # CSV filename
    with open(filename, 'a', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if not f.tell():
            w.writeheader()
        w.writerows(new_rows)
        print(f'Saved: {filename} (rows={len(new_rows)})')

    return new_rows

def parse_def_logs(logs):
    logs, rows = logs['Logs'][0], []

    ts = logs['StartTime']['$date']
    dt_utc = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
    dt_str = dt_utc.strftime('%Y-%m-%d')

    atker = logs['AttackerPlayerInfo']
    defer = logs['DefenderPlayerInfo']
    atk_cuid = atker['CUID']
    atk_name = atker['Name']
    atk_guild = atker['GuildSubInfo']['Name'] if 'GuildSubInfo' in atker else ''
    def_cuid = defer['CUID']
    def_name = defer['Name']
    def_guild = defer['GuildSubInfo']['Name'] if 'GuildSubInfo' in defer else ''

    for item in logs['EndDatas']:
        camp1 = item['StartBattleInfo']['CampData1']['PositionRoleMap']
        camp2 = item['StartBattleInfo']['CampData2']['PositionRoleMap']
        atk_roles = sorted(camp1.values(), key=lambda x: x['StaticID'])
        def_roles = sorted(camp2.values(), key=lambda x: x['StaticID'])
        # Pad with empty roles if less than 3
        padding = {'StaticID': '', '_id': {'$oid': ''}}
        atk_roles = atk_roles + [padding] * (3 - len(atk_roles))
        def_roles = def_roles + [padding] * (3 - len(def_roles))

        dead_ids, dead = set(), []
        if 'Camp1DeadList' in item:
            dead_ids.update(item['Camp1DeadList'])
        if 'Camp2DeadList' in item:
            dead_ids.update(item['Camp2DeadList'])
        for i, role in enumerate(def_roles, start=1):
            if role['_id']['$oid'] in dead_ids:
                dead.append(str(i))
        for i, role in enumerate(atk_roles, start=4):
            if role['_id']['$oid'] in dead_ids:
                dead.append(str(i))

        win = True if item['Result'] == 'Win' else False
        battle_id = logs['_id']['$oid']

        rows.append({
            'date': dt_str,
            'def_1': get_role(def_roles[0]['StaticID']),
            'def_2': get_role(def_roles[1]['StaticID']),
            'def_3': get_role(def_roles[2]['StaticID']),
            'atk_1': get_role(atk_roles[0]['StaticID']),
            'atk_2': get_role(atk_roles[1]['StaticID']),
            'atk_3': get_role(atk_roles[2]['StaticID']),
            'win': win,
            'dead': ''.join(dead),
            'def_cuid': def_cuid,
            'def_name': def_name,
            'def_guild': def_guild,
            'atk_cuid': atk_cuid,
            'atk_name': atk_name,
            'atk_guild': atk_guild,
            'battle_id': battle_id,
        })

    return rows
