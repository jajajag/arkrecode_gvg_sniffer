from collections import Counter
from .helper import calculate_role_stats, calculate_team_stats, equip_parts
from .helper import get_bond, get_role, get_set


def role_sets(equip_map):
    counts = Counter()
    for part in equip_parts():
        equip = (equip_map or {}).get(part)
        if equip:
            counts[equip.get('Set')] += 1
    text = ''
    for set_id, count in counts.most_common():
        name, need = get_set(set_id)
        active = count // need
        if active <= 0:
            continue
        text += f'{active if active > 1 else ""}{name}'
    return text

def role_bond(bond):
    if not bond:
        return ''
    return f'{bond["LV"]}级{get_bond(bond["StaticID"])}'

def role_stats(stats, hp_only=False):
    attack = round(stats.get("Attack", 0))
    if hp_only:
        return f'{round(stats.get("HP", 0))}生'
    return (
        f'{round(stats.get("Speed", 0))}速'
        f'{round(stats.get("HP", 0))}生'
        f'{round(stats.get("Defence", 0))}防'
        f'{round(stats.get("EffectHitRate", 0) * 100)}命'
        f'{round(stats.get("ResistanceRate", 0) * 100)}抗'
        f'{attack}攻'
        f'{round(stats.get("CriticalRate", 0) * 100)}暴'
        f'{round(stats.get("CriticalDamageRate", 0) * 100)}爆'
    )

def print_role(role, stats=None, hp_only=False):
    stats = stats or calculate_role_stats(role)
    desc = role_sets(role.get('EquipmentMap')) \
            + role_bond(role.get('ArtifactData'))
    name = get_role(role["StaticID"])
    print(f'{name}：{desc}({role_stats(stats, hp_only)})')

def print_team(team, hp_only=False):
    roles = [team['PositionRoleMap'][i] \
            for i in sorted(team['PositionRoleMap'].keys())]
    stats = calculate_team_stats(roles)
    for role, role_stats in zip(roles, stats):
        print_role(role, role_stats, hp_only)

def print_player(index, player, hp_only=False):
    if 'PlayerInfo' in player:
        info = player['PlayerInfo']
    else:
        info = player['BattleSupportData']['PlayerInfo']

    avatar = get_role(info['LeaderSID'])
    print(f'{index}. {info.get("Name", "")}（{avatar}-{info["CUID"]}）')

    if 'BattleSupportData' in player:
        gid = info.get('GuildSubInfo', {}).get('_id', {}).get('$oid')
        print(f'IAP: {info["IAP"]}, Score: {player["PVPInfo"]["Score"]}' \
                + (f', GID: {gid}' if gid else ''))

    if 'DefenceTeamData' in player:
        team = player['DefenceTeamData']
        print('[上半]')
        print_team(team['FirstTeam'], hp_only)
        print('[下半]')
        print_team(team['SecondTeam'], hp_only)
    elif 'BattleSupportData' in player:
        print('-----防守队伍-----')
        print_team(player['PVPInfo']['DefenceTeam'], hp_only)
        print('-----辅助团员-----')
        for item in player['BattleSupportData']['RoleDataList']:
            print_role(item['Role'], hp_only=hp_only)
    else:
        print_team(player['TeamData'], hp_only)

def print_report(data):
    if 'GuildWarData' in data:
        if 'EnemyCampData' in data['GuildWarData']:
            plist = data['GuildWarData']['EnemyCampData']['PlayerInfoList']
            hp_only = True
        else:
            plist = data['GuildWarData']['MyCampData']['PlayerInfoList']
            hp_only = False
        for i, player in enumerate(plist, 1):
            print_player(i, player, hp_only)
    elif 'PVPData' in data:
        for i, player in enumerate(data['PVPData']['EnemyList'], 1):
            print_player(i, player)
    else:
        print_player(1, data)

def print_rta_rooms(data):
    for i, room in enumerate(data.get("Rooms", []), 1):
        name = room.get("Name") or "无"
        password = room.get("Password") or "无"
        print(f'{i}. 房间名：{name}，密码：{password}')
        for player in room.get("Players", []):
            guild = player.get("GuildSubInfo", {}).get("Name", "")
            print(
                f'  - {player.get("Name", "")}，'
                f'公会：{guild}，UID：{player.get("CUID", "")}'
            )
