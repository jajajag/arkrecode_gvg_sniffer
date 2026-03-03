from collections import Counter
from datetime import datetime, timezone
from translator import *
import csv
import json

DATA_PATH = 'data.json'

def load_data(path=DATA_PATH):
    with open(path, 'r', encoding='utf-8') as fp:
        return json.load(fp)

def export_prop(row, equip_map):
    if not equip_map: return

    prop_set = {i: 0 for i in PROP}
    for equip in equip_map:
        if not equip_map[equip]['SubProps']:
            continue
        for prop in equip_map[equip]['SubProps']['SourceValues']:
            prop_type = prop['PropertyType']
            if 'Rate' in prop_type:
                value = int(float(prop['Value']) * 100)
            else:
                value = int(float(prop['Value']))
            prop_set[prop_type] += value
    ret = []
    for prop in prop_set:
        if not prop_set[prop]: 
            continue
        if 'Rate' in prop:
            ret.append(f'{prop_set[prop]}%{get_prop_short(prop)}')
        else:
            ret.append(f'{prop_set[prop]}{get_prop_short(prop)}')
    row['副属性'] = ''.join(reversed(ret))

def export_equip(row, equip_map):
    if not equip_map: return

    sets = []
    for equip in EQUIP:
        if equip not in equip_map:
            continue
        prop_type = equip_map[equip]['MainProp']['PropertyType']
        prop = equip_map[equip]['MainProp']['SValue']
        if 'Rate' in prop_type:
            prop = f'{int(float(prop) * 100)}%'
        else:
            prop = f'{int(float(prop))}'
        # We only care about main prop for shoes, ring, necklace
        if equip in ['Shoes', 'Ring', 'Necklace']:
            row[EQUIP[equip]] = f'{prop}{get_prop_short(prop_type)}'
        sets.append(equip_map[equip]['Set'])

    sets = Counter(sets)
    set_str = ''
    for set_name, count in sets.most_common():
        cur_set = get_set(set_name)
        cur_count = count // cur_set[1]
        set_str += cur_set[0] * cur_count
    row['套装'] = set_str

def export_bond(row, bond):
    if not bond: return
    static_id = bond['StaticID']
    lv = bond['LV']
    row['羁绊'] = f'{lv}级{get_bond(static_id)}'

def export_skill(row, skills):
    skills = [skill['Level'] - 1 for skill in skills]
    skills = [str(skill) for skill in skills][:3]
    row['技能'] = ''.join(skills)

def export_role(role):
    row = {'角色': f'{get_role(role["StaticID"])}'}
    bond = role['ArtifactData'] if 'ArtifactData' in role else None
    equip_map = role['EquipmentMap'] if 'EquipmentMap' in role else None
    skills = role['Skills']['Skills']

    export_bond(row, bond)
    export_equip(row, equip_map)
    export_prop(row, equip_map)
    export_skill(row, skills)
    row['星级'] = f'{role["Star"]}星觉醒{role["AwakenLV"]}'
    ip = role['ImprintLV']
    if ip: row['潜能'] = f'{ip}潜{"自阵" if role["IsSelfImprint"] else "群阵"}'

    return row

def export_team(team):
    team = team['PositionRoleMap']
    rows = []
    for i in sorted(team.keys()):
        role = team[i]
        rows.append(export_role(role))
    return rows

def export_player(player):
    # Player info
    info = player['PlayerInfo']
    player_cuid = info['CUID']
    player_name = info['Name']
    leader_name = get_role(info['LeaderSID'])

    # Team data
    team = player['DefenceTeamData']
    first_rows = export_team(team['FirstTeam'])
    second_rows = export_team(team['SecondTeam'])
    first_rows[0]['UID'] = player_cuid
    first_rows[0]['昵称'] = player_name
    first_rows[0]['头像'] = leader_name
    first_rows[0]['队伍'] = '上半'
    second_rows[0]['队伍'] = '下半'

    return first_rows + second_rows

def export_all():
    data, rows = load_data(), []

    # GVG (只保存团战)
    if 'GuildWarData' in data and 'EnemyCampData' in data['GuildWarData']:
        plist = data['GuildWarData']['EnemyCampData']['PlayerInfoList']
        for player in plist:
            rows += export_player(player)
        fieldnames = [
            '昵称', '头像', '队伍', '角色', '羁绊', '套装', 
            '鞋子', '戒指', '项链', '副属性',
            '技能', '星级', '潜能', 'UID'
        ]

        # CSV filename
        ts = int(data['Utc'])
        dt_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
        dt_str = dt_utc.strftime('%Y-%m-%d')
        guild_name = data['GuildWarData']['EnemyCampData']['GuildInfo']['Name']

        # Write CSV
        with open(f'{dt_str} {guild_name}.csv', 'w', newline='', 
                  encoding='utf-8-sig') as fp:
            w = csv.DictWriter(fp, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows)

if __name__ == '__main__':
    export_all()
