from datetime import datetime, timezone
from .helper import *
import csv
import json
import os
import random
import requests
import time

requests.packages.urllib3.disable_warnings()

url = 'https://game-arkre-labs.ecchi.xxx/Router/RouterHandler.ashx'
headers = {
    'Content-Type': 'application/octet-stream',
    'User-Agent': 'UnityPlayer/2022.3.62f2 (UnityWebRequest/1.0, libcurl/8.10.1-DEV)'
}

# 1. 团战总结
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
            guild = item['AttackerPlayerInfo'].get(
                    'GuildSubInfo', {}).get('Name', '')
            enemy_name = item['DefenderPlayerInfo']['Name']
            enemy_cuid = item['DefenderPlayerInfo']['CUID']
            enemy_guild = item['DefenderPlayerInfo'].get(
                    'GuildSubInfo', {}).get('Name', '')
        else:
            is_attack = False
            win = item['DefenderResult']['Result']
            guild = item['DefenderPlayerInfo'].get(
                    'GuildSubInfo', {}).get('Name', '')
            enemy_name = item['AttackerPlayerInfo']['Name']
            enemy_cuid = item['AttackerPlayerInfo']['CUID']
            enemy_guild = item['AttackerPlayerInfo'].get(
                    'GuildSubInfo', {}).get('Name', '')

        rows.append({
            'date': dt_str,
            'cuid': cuid,
            'name': name,
            'is_attack': is_attack,
            'battle_id': battle_id,
            'win': {'Lose': 0, 'Draw': 1, 'Win': 2}[win],
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

# 2. 团战防守（csv）
def analyze_defence_csv(aid, session_id, cuid, rows, filename='团战防守.csv'):
    seen, new_rows = set(), []

    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8-sig') as f:
            for r in csv.DictReader(f):
                seen.add(r['battle_id'])

    for row in rows:
        #if row['is_attack']: continue
        if row['battle_id'] in seen: continue
        try:
            logs = analyze_hit(aid, session_id, cuid, row['battle_id'])
            # Parse logs to extract team compositions and battle results
            for r in parse_def_logs(logs):
                # Pad teams to ensure they have 3 members
                atk_team = (r['atk_team'] + [{}] * 3)[:3]
                def_team = (r['def_team'] + [{}] * 3)[:3]
                new_rows.append({
                    'date': datetime.fromtimestamp(r['start_ts'] / 1000,
                        tz=timezone.utc).strftime('%Y-%m-%d'),
                    'atk_1': get_role(atk_team[0].get('role_id', '')),
                    'atk_2': get_role(atk_team[1].get('role_id', '')),
                    'atk_3': get_role(atk_team[2].get('role_id', '')),
                    'def_1': get_role(def_team[0].get('role_id', '')),
                    'def_2': get_role(def_team[1].get('role_id', '')),
                    'def_3': get_role(def_team[2].get('role_id', '')),
                    'win': r['win'],
                    'dead': ''.join(str(i) for i, u in enumerate(
                        def_team[:3] + atk_team[:3], start=1) if u.get('dead')),
                    'atk_cuid': r['atk_cuid'],
                    'atk_name': r['atk_name'],
                    'atk_guild': r['atk_guild'],
                    'def_cuid': r['def_cuid'],
                    'def_name': r['def_name'],
                    'def_guild': r['def_guild'],
                    'battle_id': r['battle_id'],
                })
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

# 3. 团战防守（db）
def analyze_defence_db(aid, session_id, cuid, rows, db_path='data.db'):
    import sqlite3
    conn = sqlite3.connect(db_path)
    # Create table for single battle
    conn.execute('''
        CREATE TABLE IF NOT EXISTS gvg_rounds (
            battle_id TEXT, round_idx INTEGER, start_ts INTEGER,
            atk_cuid INTEGER, atk_name TEXT, atk_guild TEXT,
            def_cuid INTEGER, def_name TEXT, def_guild TEXT,
            win INTEGER, PRIMARY KEY (battle_id, round_idx)
        )
    ''')
    # Create table for units in each battle
    conn.execute('''
        CREATE TABLE IF NOT EXISTS gvg_units (
            battle_id TEXT, round_idx INTEGER, side TEXT, pos INTEGER,
            role_id TEXT, star INTEGER, awaken INTEGER, imprint INTEGER,
            dead INTEGER, PRIMARY KEY (battle_id, round_idx, side, pos)
        )
    ''')

    for row in rows:
        #if row['is_attack']: continue
        battle_id = row['battle_id']
        # Check if battle_id already exists in DB
        exists = conn.execute(
                'SELECT 1 FROM gvg_rounds WHERE battle_id = ? LIMIT 1',
                (battle_id,)).fetchone()
        if exists: continue
        try:
            logs = analyze_hit(aid, session_id, cuid, battle_id)
            parsed_rows = parse_def_logs(logs)
            for r in parsed_rows:
                # Insert battle info
                conn.execute('''
                    INSERT OR IGNORE INTO gvg_rounds (
                        battle_id, round_idx, start_ts, atk_cuid, atk_name,
                        atk_guild, def_cuid, def_name, def_guild, win
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    r['battle_id'], r['round_idx'], r['start_ts'],
                    r['atk_cuid'], r['atk_name'], r['atk_guild'],
                    r['def_cuid'], r['def_name'], r['def_guild'], int(r['win'])
                ))
                for side, team in [('atk', r['atk_team']),
                                   ('def', r['def_team'])]:
                    for unit in team:
                        # Insert unit info
                        conn.execute('''
                            INSERT OR IGNORE INTO gvg_units (
                                battle_id, round_idx, side, pos,
                                role_id, star, awaken, imprint, dead
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            r['battle_id'], r['round_idx'], side, unit['pos'],
                            unit['role_id'], unit['star'], unit['awaken'],
                            unit['imprint'], int(unit['dead'])
                        ))
            conn.commit()
        except Exception as e:
            print(f"battle {battle_id} 获取失败: {e}")
    conn.close()
    print(f'Saved to DB: {db_path}')

def parse_def_logs(logs):
    logs, rows = logs['Logs'][0], []

    battle_id = logs['_id']['$oid']
    start_ts = logs['StartTime']['$date']

    atker = logs['AttackerPlayerInfo']
    atk_cuid = atker['CUID']
    atk_name = atker['Name']
    atk_guild = atker.get('GuildSubInfo', {}).get('Name', '')
    defer = logs['DefenderPlayerInfo']
    def_cuid = defer['CUID']
    def_name = defer['Name']
    def_guild = defer.get('GuildSubInfo', {}).get('Name', '')

    for round_idx, item in enumerate(logs['EndDatas'], start=1):
        battle_info = item['StartBattleInfo']
        camp1 = battle_info['CampData1']['PositionRoleMap']
        camp2 = battle_info['CampData2']['PositionRoleMap']

        dead_ids = set(item.get('Camp1DeadList', []))
        dead_ids.update(item.get('Camp2DeadList', []))

        atk_team, def_team = [
            sorted([{
                    'pos': int(pos),
                    'role_id': role['StaticID'],
                    'star': role['Star'],
                    'awaken': role['AwakenLV'],
                    'imprint': role['ImprintLV'],
                    'dead': role['_id']['$oid'] in dead_ids,
                } for pos, role in camp.items()
            ], key=lambda x: x['pos']) for camp in (camp1, camp2)
        ]

        rows.append({
            'battle_id': battle_id,
            'round_idx': round_idx,
            'start_ts': start_ts,
            'atk_cuid': atk_cuid,
            'atk_name': atk_name,
            'atk_guild': atk_guild,
            'atk_team': atk_team,
            'def_cuid': def_cuid,
            'def_name': def_name,
            'def_guild': def_guild,
            'def_team': def_team,
            'win': item['Result'] == 'Win',
        })

    return rows
