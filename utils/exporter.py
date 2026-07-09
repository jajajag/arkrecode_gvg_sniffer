from collections import Counter
from datetime import datetime, timezone
from .helper import calculate_role_stats, calculate_team_stats, data_path
from .helper import equip_name, equip_parts, get_bond, get_role, get_set
from .helper import prop_short
import csv


def export_prop(row, stats, hp_only=False):
    row['生命'] = round(stats.get('HP', 0))
    if hp_only:
        return
    row['速度'] = round(stats.get('Speed', 0))
    row['防御'] = round(stats.get('Defence', 0))
    row['命中'] = round(stats.get('EffectHitRate', 0) * 100)
    row['抵抗'] = round(stats.get('ResistanceRate', 0) * 100)
    row['攻击'] = round(stats.get('Attack', 0))
    row['暴击'] = round(stats.get('CriticalRate', 0) * 100)
    row['爆伤'] = round(stats.get('CriticalDamageRate', 0) * 100)

def export_equip(row, equip_map):
    if not equip_map: return

    sets = []
    for equip in equip_parts():
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
            row[equip_name(equip)] = f'{prop}{prop_short(prop_type)}'
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

def export_role(role, stats=None, hp_only=False):
    stats = stats or calculate_role_stats(role)
    row = {'角色': f'{get_role(role["StaticID"])}'}
    bond = role['ArtifactData'] if 'ArtifactData' in role else None
    equip_map = role['EquipmentMap'] if 'EquipmentMap' in role else None
    skills = role['Skills']['Skills']

    export_bond(row, bond)
    export_equip(row, equip_map)
    export_prop(row, stats, hp_only)
    export_skill(row, skills)
    row['星级'] = f'{role["Star"]}星觉醒{role["AwakenLV"]}'
    ip = role['ImprintLV']
    if ip: row['潜能'] = f'{ip}潜{"自阵" if role["IsSelfImprint"] else "群阵"}'

    return row

def export_team(team, hp_only=False):
    team = team['PositionRoleMap']
    roles = [team[i] for i in sorted(team.keys())]
    stats = calculate_team_stats(roles)
    rows = []
    for role, role_stats in zip(roles, stats):
        rows.append(export_role(role, role_stats, hp_only))
    return rows

def export_player(player, hp_only=False):
    # Player info
    info = player['PlayerInfo']
    player_cuid = info['CUID']
    player_name = info['Name']
    leader_name = get_role(info['LeaderSID'])

    # Team data
    team = player['DefenceTeamData']
    first_rows = export_team(team['FirstTeam'], hp_only)
    second_rows = export_team(team['SecondTeam'], hp_only)
    first_rows[0]['UID'] = player_cuid
    first_rows[0]['昵称'] = player_name
    first_rows[0]['头像'] = leader_name
    first_rows[0]['队伍'] = '上半'
    second_rows[0]['队伍'] = '下半'

    return first_rows + second_rows

def export_report(data):
    rows = []

    # GVG (只保存团战)
    if 'GuildWarData' in data:
        guild_war = data['GuildWarData']
        if 'EnemyCampData' in data['GuildWarData']:
            plist = guild_war['EnemyCampData']['PlayerInfoList']
            guild_name = guild_war['EnemyCampData']['GuildInfo']['Name']
            hp_only = True
        else:
            plist = guild_war['MyCampData']['PlayerInfoList']
            guild_name = guild_war['MyCampData']['GuildInfo']['Name']
            hp_only = False
        for player in plist:
            rows += export_player(player, hp_only)
        prop_fieldnames = ['生命'] if hp_only else [
            '速度', '生命', '防御', '命中', '抵抗', '攻击', '暴击', '爆伤'
        ]
        fieldnames = [
            '昵称', '头像', '队伍', '角色', '羁绊', '套装', 
            '鞋子', '戒指', '项链', *prop_fieldnames,
            '技能', '星级', '潜能', 'UID'
        ]

        # CSV filename
        ts = int(data['Utc'])
        dt_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
        dt_str = dt_utc.strftime('%Y-%m-%d')

        # Write CSV
        filename = data_path(f'{dt_str} {guild_name}.csv')
        filename.parent.mkdir(parents=True, exist_ok=True)
        with open(filename, 'w', newline='', encoding='utf-8-sig') as fp:
            w = csv.DictWriter(fp, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows)
