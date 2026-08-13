from datetime import datetime, timezone
import csv
import random
import requests
import time

from utils.helper import data_path

requests.packages.urllib3.disable_warnings()

url = 'https://game-arkre-labs.ecchi.xxx/Router/RouterHandler.ashx'
headers = {
    'Content-Type': 'application/octet-stream',
    'User-Agent': 'UnityPlayer/2022.3.62f2 (UnityWebRequest/1.0, libcurl/8.10.1-DEV)'
}

# 1. 团战总结
def analyze_gvg(data, aid, session_id, save_csv=True):
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
    filename = data_path(f'{dt_str} {guild_name}团战总结.csv')
    if save_csv:
        filename.parent.mkdir(parents=True, exist_ok=True)
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
    time.sleep(random.uniform(0.08, 0.12))
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

# 2. 团战防守
def analyze_gvg_defence(aid, session_id, cuid, rows, db_path=None):
    db_path = data_path('data.db') if db_path is None else db_path
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

# 3. 竞技场装备总结
def analyze_pvp_equips(data, db_path=None):
    db_path = data_path('data.db') if db_path is None else db_path
    import sqlite3
    conn = sqlite3.connect(db_path)

    conn.execute('''
        CREATE TABLE IF NOT EXISTS pvp_equips (
            equip_id TEXT PRIMARY KEY, cuid INTEGER, player_name TEXT,
            equip_type TEXT, static_id TEXT, set_name TEXT,
            class_lv INTEGER, lv INTEGER, main_prop TEXT, main_value REAL,
            sub1_prop TEXT, sub1_value REAL, sub2_prop TEXT, sub2_value REAL,
            sub3_prop TEXT, sub3_value REAL, sub4_prop TEXT, sub4_value REAL
        )
    ''')
    # 1. Go through players' defence teams
    for item in data['PVPRankInfoList']:
        player_info = item['PlayerInfo']
        cuid = player_info['CUID']
        player_name = player_info['Name']

        role_map = item['PVPInfo']['DefenceTeam']['PositionRoleMap']

        # 2. Go through roles
        for role in role_map.values():
            equip_map = role.get('EquipmentMap', {})

            # 3. Go through equipments
            for equip_type, equip in equip_map.items():
                equip_id = equip['_id']['$oid']

                new_lv = equip['LV']
                old_lv = conn.execute(
                    'SELECT lv FROM pvp_equips WHERE equip_id = ?',
                    (equip_id,)
                ).fetchone()
                # Skip if existing record has same or higher level
                if old_lv and new_lv <= old_lv[0]:
                    continue

                main_prop = equip['MainProp']
                # Pad subprops to ensure we have 4 entries
                subprops = (equip.get('SubProps') or {}).get('SourceValues') or []
                subprops = (subprops + [{}] * 4)[:4]

                conn.execute('''
                    INSERT OR REPLACE INTO pvp_equips (
                        equip_id, cuid, player_name, equip_type, static_id,
                        set_name, class_lv, lv, main_prop, main_value,
                        sub1_prop, sub1_value, sub2_prop, sub2_value,
                        sub3_prop, sub3_value, sub4_prop, sub4_value
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ''', (
                    equip_id, cuid, player_name, equip_type,
                    equip['StaticID'], equip['Set'], equip['ClassLV'], new_lv,
                    main_prop['PropertyType'], main_prop['Value'],
                    subprops[0].get('PropertyType', ''),
                    subprops[0].get('Value', 0),
                    subprops[1].get('PropertyType', ''),
                    subprops[1].get('Value', 0),
                    subprops[2].get('PropertyType', ''),
                    subprops[2].get('Value', 0),
                    subprops[3].get('PropertyType', ''),
                    subprops[3].get('Value', 0),
                ))

    conn.commit()
    conn.close()

    print(f'Saved PVP equips to DB: {db_path}')
