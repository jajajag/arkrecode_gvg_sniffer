from collections import Counter, defaultdict
from translator import *
import json
import sys

DATA_PATH = 'data.json'

def load_data(path=DATA_PATH):
    with open(path, 'r', encoding='utf-8') as fp:
        return json.load(fp)

def print_prop(equip_map):
    if not equip_map: 
        return
    #prop_set = defaultdict(int)
    prop_set = get_prop_set()
    for equip in equip_map:
        if not equip_map[equip]['SubProps']: 
            continue
        for prop in equip_map[equip]['SubProps']['SourceValues']:
            prop_type = prop['PropertyType']
            if 'Rate' in prop_type:
                value = int(prop['Value'] * 100)
            elif prop_type == 'SpeedValue':
                value = int(prop['Value'])
            else:
                continue
            # Currently, we pass all values in subprops to simplify the output
            #prop_set[get_prop_full(prop_type)] += value
            prop_set[get_prop_short(prop_type)] += value
    if not prop_set: 
        return
    # We do not print the 0 values
    ret = [str(prop_set[prop]) + prop for prop in prop_set if prop_set[prop]]
    print(f'（{"".join(ret)}）', end='')

def print_equipment(equip_map):
    if not equip_map: 
        return
    sets = []
    for equip in ['Shoes', 'Ring', 'Necklace']:
        if equip not in equip_map:
            print('X', end='')
            continue
        prop = equip_map[equip]["MainProp"]["PropertyType"]
        print(f'{get_prop_short(prop)}', end='')
        sets.append(equip_map[equip]['Set'])
    for equip in ['Body', 'Head', 'Weapon']:
        if equip not in equip_map:
            continue
        sets.append(equip_map[equip]['Set'])
    print('，', end='')
    sets = Counter(sets)
    # Check if not a single set is matched
    flag_set = False
    for set_name, count in sets.most_common():
        cur_set = get_set(set_name)
        cur_count = count // cur_set[1]
        if cur_count > 1:
            print(f'{cur_count}', end='')
        if cur_count >= 1:
            flag_set = True
            print(f'{cur_set[0]}', end='')
    if not flag_set:
        print('散件', end='')

def print_bond(artifact):
    if not artifact: 
        return
    static_id = artifact['StaticID']
    lv = artifact['LV']
    print(f'，{lv}级{get_bond(static_id)}', end='')

def print_role(role):
    print(f'{get_role(role["StaticID"])}：', end='')
    bond = role['ArtifactData'] if 'ArtifactData' in role else None
    equip = role['EquipmentMap'] if 'EquipmentMap' in role else None
    print_equipment(equip)
    print_bond(bond)
    print_prop(equip)
    print()

def print_team(team):
    team = team['PositionRoleMap']
    for i in sorted(team.keys()):
        role = team[i]
        print_role(role)

def print_player(index, player):
    info = player['PlayerInfo']
    print(f'{index}. {info["Name"]}（{get_role(info["LeaderSID"])}）')
    # GVG
    if 'DefenceTeamData' in player:
        team = player['DefenceTeamData']
        print('[上半]')
        print_team(team['FirstTeam'])
        print('[下半]')
        print_team(team['SecondTeam'])
    # PVP
    else:
        print_team(player['TeamData'])

def print_all():
    data = load_data()
    # GVG (团战)
    if 'GuildWarData' in data and 'EnemyCampData' in data['GuildWarData']:
        plist = data['GuildWarData']['EnemyCampData']['PlayerInfoList']
        for i, player in enumerate(plist, 1):
            print_player(i, player)
    # PVP (竞技场)
    elif 'PVPData' in data:
        plist = data['PVPData']['EnemyList']
        for i, player in enumerate(plist, 1):
            print_player(i, player)
    # Support (好友支援)
    elif 'BattleSupportData' in data:
        info = data['BattleSupportData']['PlayerInfo']
        print(f'1. {info["Name"]}（{get_role(info["LeaderSID"])}）')
        plist = data['BattleSupportData']['RoleDataList']
        for i, player in enumerate(plist, 1):
            print_role(player['Role'])
    # Revenge (复仇)
    else:
        print_player(1, data)

if __name__ == '__main__':
    print_all()
