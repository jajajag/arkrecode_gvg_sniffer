from collections import Counter

from .helper import (
    calculate_role_stats,
    calculate_team_stats,
    equip_parts,
    get_bond,
    get_role,
    get_set,
    hp_int,
    stat_int,
)


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


def role_stats(stats):
    attack = stat_int(stats.get("Attack", 0))
    attack_text = f'{(attack + 500) // 1000}k' if attack >= 1000 else str(attack)
    return (
        f'{stat_int(stats.get("Speed", 0))}速'
        f'{hp_int(stats.get("HP", 0))}生'
        f'{stat_int(stats.get("Defence", 0))}防'
        f'{round(stats.get("EffectHitRate", 0) * 100)}命'
        f'{round(stats.get("ResistanceRate", 0) * 100)}抗'
        f'{attack_text}攻'
        f'{round(stats.get("CriticalRate", 0) * 100)}暴'
        f'{round(stats.get("CriticalDamageRate", 0) * 100)}爆'
    )


def print_role(role, stats=None):
    stats = stats or calculate_role_stats(role)
    desc = role_sets(role.get('EquipmentMap')) + role_bond(role.get('ArtifactData'))
    name = get_role(role["StaticID"])
    print(f'{name}：{desc}({role_stats(stats)})' if desc else f'{name}({role_stats(stats)})')


def print_team(team):
    roles = [team['PositionRoleMap'][i] for i in sorted(team['PositionRoleMap'].keys())]
    stats = calculate_team_stats(roles)
    for role, role_stats in zip(roles, stats):
        print_role(role, role_stats)


def print_player(index, player):
    if 'PlayerInfo' in player:
        info = player['PlayerInfo']
    else:
        info = player['BattleSupportData']['PlayerInfo']

    avatar = get_role(info['LeaderSID'])
    print(f'{index}. {info["Name"]}（{avatar}-{info["CUID"]}）')

    if 'BattleSupportData' in player:
        gid = info.get('GuildSubInfo', {}).get('_id', {}).get('$oid')
        print(f'IAP: {info["IAP"]}, Score: {player["PVPInfo"]["Score"]}' + (f', GID: {gid}' if gid else ''))

    if 'DefenceTeamData' in player:
        team = player['DefenceTeamData']
        print('[上半]')
        print_team(team['FirstTeam'])
        print('[下半]')
        print_team(team['SecondTeam'])
    elif 'BattleSupportData' in player:
        print('-----防守队伍-----')
        print_team(player['PVPInfo']['DefenceTeam'])
        print('-----辅助团员-----')
        for item in player['BattleSupportData']['RoleDataList']:
            print_role(item['Role'])
    else:
        print_team(player['TeamData'])


def print_report(data):
    if 'GuildWarData' in data:
        if 'EnemyCampData' in data['GuildWarData']:
            plist = data['GuildWarData']['EnemyCampData']['PlayerInfoList']
        else:
            plist = data['GuildWarData']['MyCampData']['PlayerInfoList']
        for i, player in enumerate(plist, 1):
            print_player(i, player)
    elif 'PVPData' in data:
        for i, player in enumerate(data['PVPData']['EnemyList'], 1):
            print_player(i, player)
    else:
        print_player(1, data)
