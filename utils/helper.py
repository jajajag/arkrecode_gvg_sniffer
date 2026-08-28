from functools import lru_cache
import json
import math
from pathlib import Path
import re
import sqlite3
import sys
import uuid


SOURCE_ROOT = Path(__file__).resolve().parents[1]
EXECUTABLE_ROOT = Path(sys.executable).resolve().parent
# mitmdump itself may be a frozen executable while loading this project as an
# external addon. In that case the project's data lives beside this source,
# not beside mitmdump.exe under its installation directory.
APP_ROOT = SOURCE_ROOT if (SOURCE_ROOT / 'data').is_dir() \
    else EXECUTABLE_ROOT if getattr(sys, 'frozen', False) else SOURCE_ROOT
DATA_DIR = APP_ROOT / 'data'


def data_path(*parts):
    return DATA_DIR.joinpath(*parts)


MASTER_JSON = data_path('master.json')

# Map props to stats
BASE = ('HP', 'Attack', 'Defence', 'Speed')
EXTRA = ('CriticalRate', 'CriticalDamageRate', 'EffectHitRate',
         'ResistanceRate', 'PinchRate')
STATS = (*BASE, *EXTRA)
VALUE_PROP = {
    'HPValue': 'HP',
    'AttackValue': 'Attack',
    'DefenceValue': 'Defence',
    'SpeedValue': 'Speed',
}
RATE_PROP = {
    'HPRate': 'HP',
    'AttackRate': 'Attack',
    'DefenceRate': 'Defence',
    'SpeedRate': 'Speed',
    'CriticalRate': 'CriticalRate',
    'CriticalDamageRate': 'CriticalDamageRate',
    'EffectHitRate': 'EffectHitRate',
    'ResistanceRate': 'ResistanceRate',
    'PinchRate': 'PinchRate',
}
# Keys in the master.db
EQUIP_KEYS = {
    'Weapon': 'UI_Equip_Weapon',
    'Head': 'UI_Equip_Helmet',
    'Body': 'UI_Equip_Armor',
    'Necklace': 'UI_Equip_Necklace',
    'Ring': 'UI_Equip_Ring',
    'Shoes': 'UI_Equip_Boots',
}
PROP_KEYS = {
    'AttackRate': 'UI_Equip_Attributes_AttackRate',
    'AttackValue': 'UI_Equip_Attack',
    'CriticalDamageRate': 'UI_PropertyCriticalDamage',
    'CriticalRate': 'UI_Equip_Critical',
    'DefenceRate': 'UI_Guild_Defense',
    'DefenceValue': 'UI_Guild_Defense',
    'EffectHitRate': 'UI_PropertyEffectHit',
    'HPValue': 'UI_Equip_Health',
    'HPRate': 'UI_Equip_Health',
    'ResistanceRate': 'UI_PropertyResistance',
    'SpeedValue': 'UI_PropertySpeed',
}

def num(value, default=0):
    try:
        return default if value in (None, '') else float(value)
    except (TypeError, ValueError):
        return default

def intv(value, default=0):
    try:
        return default if value in (None, '') else int(value)
    except (TypeError, ValueError):
        return default

@lru_cache(maxsize=1)
def master():
    if not MASTER_JSON.exists():
        return {}
    with MASTER_JSON.open('r', encoding='utf-8') as fp:
        return json.load(fp)

# Load chs from master.db with caching
@lru_cache(maxsize=8192)
def chs(key):
    if not key:
        return None
    if not key.startswith(('T_', 'UI_')):
        return key
    return master().get('localization', {}).get(key)

def get_role(role_id):
    return chs(master().get('roles', {}).get(role_id, {}).get('NAME')) or role_id

def master_role_ids():
    return tuple(
        role_id for role_id in master().get('roles', {})
        if role_id.startswith('H')
    )

def role_candidates(query, role_ids=None):
    role_ids = master_role_ids() if role_ids is None else tuple(role_ids)
    folded_query = query.casefold()
    # 1. First try exact match on role ID
    if query in role_ids:
        return [(query, get_role(query))]
    # 2. Then try exact match on role name
    exact = [
        (role_id, get_role(role_id))
        for role_id in role_ids
        if get_role(role_id).casefold() == folded_query
    ]
    if exact:
        return exact
    # 3. Finally try substring match on role name
    result = [
        (role_id, get_role(role_id))
        for role_id in role_ids
        if folded_query in get_role(role_id).casefold()
    ]
    return sorted(result, key=lambda item: (len(item[1]), item[1], item[0]))

def resolve_role_ids(queries, role_ids=None):
    role_ids = master_role_ids() if role_ids is None else tuple(role_ids)
    resolved = []
    for query in queries:
        matches = role_candidates(query, role_ids)
        if len(matches) != 1:
            print(f'「{query}」匹配到 {len(matches)} 个角色，无法唯一确定：')
            for role_id, name in matches[:30]:
                print(f'  {role_id}\t{name}')
            if len(matches) > 30:
                print(f'  ... 还有 {len(matches) - 30} 个')
            return None
        resolved.append(matches[0][0])
    if len(set(resolved)) != len(resolved):
        print('输入解析到了重复角色，请重新输入。')
        return None
    return resolved

def get_bond(bond_id):
    return chs(master().get('items', {}).get(bond_id, {}).get('Name')) or bond_id

def equip_name(part):
    return chs(EQUIP_KEYS.get(part)) or part

def equip_parts():
    return tuple(EQUIP_KEYS)

def prop_short(prop):
    if prop == 'CriticalDamageRate':
        return '爆'
    if prop == 'CriticalRate':
        return '暴'
    if prop == 'EffectHitRate':
        return '命'
    if prop == 'ResistanceRate':
        return '抗'
    if prop == 'SpeedValue':
        return '速'
    name = (chs(PROP_KEYS.get(prop)) or prop).replace('(%)', '').replace(
            '（%）', '').replace(' ', '')
    if '攻击' in name:
        return '攻'
    if '防御' in name:
        return '防'
    if '生命' in name:
        return '生'
    return name[:1] if name else prop

def get_set(set_id):
    row = master().get('equipment_sets', {}).get(set_id)
    if not row:
        return set_id, 1
    name = (chs(row.get('Name')) or set_id).removesuffix('套装')
    return name, max(intv(row.get('Count'), 1), 1)

def bucket():
    return {stat: 0.0 for stat in STATS}

def add_prop(flat, rate, prop, value):
    if not prop:
        return
    if prop in VALUE_PROP:
        flat[VALUE_PROP[prop]] += num(value)
    elif prop in RATE_PROP:
        rate[RATE_PROP[prop]] += num(value)

def role_row(role_id):
    return master().get('roles', {}).get(role_id)

def role_prop(prop_id, level):
    rows = master().get('role_properties', {}).get(prop_id, [])
    exact = next((row for row in rows if row.get('LV') == str(level)), None)
    return exact or max(rows, key=lambda row: intv(row.get('LV')), default=None)

def base_stats(role):
    row = role_row(role.get('StaticID', ''))
    if not row:
        return bucket(), None
    prop_id = row.get('RolePropertyID') or 'HERO'
    level = intv(role.get('LV') or role.get('Level'), 60)
    prop = role_prop(prop_id, level)
    return {
        stat: num(prop.get(stat) if prop else 0) * num(row.get(stat), 1)
        for stat in STATS
    }, row

def add_awaken(role_id, awaken_lv, flat, rate):
    for row in master().get('role_awaken', {}).get(role_id, []):
        if intv(row.get('LV')) > awaken_lv:
            continue
        for prop, stat in VALUE_PROP.items():
            flat[stat] += num(row.get(prop))
        for prop, stat in RATE_PROP.items():
            rate[stat] += num(row.get(prop))

def add_equips(equips, flat, rate):
    for equip in (equips or {}).values():
        main = equip.get('MainProp') or {}
        add_prop(flat, rate, main.get('PropertyType'),
                 main.get('Value', main.get('SValue')))
        for prop in (equip.get('SubProps') or {}).get('SourceValues') or []:
            add_prop(flat, rate, prop.get('PropertyType'),
                     prop.get('Value', prop.get('SValue')))

def add_sets(equips, rate):
    counts = {}
    for equip in (equips or {}).values():
        set_id = equip.get('Set')
        if set_id:
            counts[set_id] = counts.get(set_id, 0) + 1
    for set_id, owned in counts.items():
        row = master().get('equipment_sets', {}).get(set_id)
        if not row:
            continue
        active = owned // max(intv(row.get('Count'), 1), 1)
        if active <= 0:
            continue
        for prop, stat in RATE_PROP.items():
            rate[stat] += num(row.get(prop)) * active

# Compute bond base value
def bond_value(base, max_value, level, floor=False):
    if level <= 1:
        value = base
    else:
        value = base + (max_value - base) * min(max(level - 1, 0), 29) / 29
    return math.floor(value + 1e-6) if floor else round(value)

def add_bond(bond, flat):
    if not bond:
        return
    row = master().get('artifacts', {}).get(bond.get('StaticID'))
    if not row:
        return
    level = intv(bond.get('LV'), 1)
    flat['Attack'] += bond_value(
        num(row.get('Base.AttackValue')),
        num(row.get('Max.AttackValue')),
        level,
        floor=True,
    )
    flat['HP'] += bond_value(
        num(row.get('Base.HPValue')),
        num(row.get('Max.HPValue')),
        level,
        floor=True,
    )

def add_passive(raw, flat, rate):
    if not raw or '#' not in raw or raw.startswith('Fun#'):
        return
    prop, value = raw.split('#', 1)
    add_prop(flat, rate, prop, value)

def add_skills(role, flat, rate):
    skills = master().get('skills', {})
    levels = master().get('skill_levels', {})
    for skill in (role.get('Skills') or {}).get('Skills') or []:
        skill_id = skill.get('StaticID')
        if not skill_id:
            continue
        for i in range(1, 4):
            add_passive((skills.get(skill_id) or {}).get(
                f'PassiveProp.DynamicField{i}'), flat, rate)
        for row in levels.get(skill_id, []):
            if intv(row.get('LV')) > intv(skill.get('Level'), 1):
                continue
            for i in range(1, 4):
                add_passive(row.get(f'PassiveProp.DynamicField{i}'), flat, rate)

def imprint(imprint_id, level):
    row = master().get('role_imprints', {}).get(imprint_id or '')
    if not row or level <= 0:
        return []
    props = []
    fields = (
        (row.get('Base.DynamicField1'), 1),
        (row.get('LevelAdd.DynamicField1'), max(level - 1, 0)),
    )
    for raw, times in fields:
        if raw and '#' in raw:
            prop, value = raw.split('#', 1)
            props.append((prop, num(value) * times))
    return props

# Team imprint
def team_bonuses(roles):
    bonuses = {i: {'flat': bucket(), 'rate': bucket()} 
               for i in range(len(roles))}
    for source_i, role in enumerate(roles):
        if role.get('IsSelfImprint'):
            continue
        _, row = base_stats(role)
        if not row:
            continue
        for prop, value in imprint(row.get('TeamImprint'),
                                   intv(role.get('ImprintLV'))):
            for target_i in bonuses:
                if target_i != source_i:
                    add_prop(bonuses[target_i]['flat'],
                             bonuses[target_i]['rate'], prop, value)
    return bonuses

def calculate_role_stats(role, team_bonus=None):
    base, row = base_stats(role)
    flat, rate = bucket(), bucket()
    if team_bonus:
        for stat, value in team_bonus.get('flat', {}).items():
            flat[stat] += value
        for stat, value in team_bonus.get('rate', {}).items():
            rate[stat] += value
    add_awaken(role.get('StaticID', ''), intv(role.get('AwakenLV')), flat, rate)
    add_equips(role.get('EquipmentMap'), flat, rate)
    add_sets(role.get('EquipmentMap'), rate)
    add_bond(role.get('ArtifactData'), flat)
    add_skills(role, flat, rate)
    if row and role.get('IsSelfImprint'):
        for prop, value in imprint(row.get('SelfImprint'),
                                   intv(role.get('ImprintLV'))):
            add_prop(flat, rate, prop, value)
    stats = {
        stat: base[stat] * (1 + rate[stat]) + flat[stat]
        for stat in BASE
    }
    stats.update({
        stat: base[stat] + rate[stat] + flat[stat]
        for stat in EXTRA
    })
    stats['CriticalRate'] = min(stats.get('CriticalRate', 0), 1)
    stats['CriticalDamageRate'] = min(stats.get('CriticalDamageRate', 0), 3.5)
    return stats

def calculate_team_stats(roles):
    bonuses = team_bonuses(roles)
    return [calculate_role_stats(role, bonuses.get(i))
            for i, role in enumerate(roles)]

def format_role_stats(stats):
    return (
        f'生命{round(stats.get("HP", 0))} '
        f'攻击{round(stats.get("Attack", 0))} '
        f'防御{round(stats.get("Defence", 0))} '
        f'速度{round(stats.get("Speed", 0))} '
        f'暴击{round(stats.get("CriticalRate", 0) * 100)}% '
        f'暴伤{round(stats.get("CriticalDamageRate", 0) * 100)}% '
        f'命中{round(stats.get("EffectHitRate", 0) * 100)}% '
        f'抗性{round(stats.get("ResistanceRate", 0) * 100)}%'
    )

def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)

# Load event id from login data
def pickup_from_login(login_data):
    now = login_data.get('Info', {}).get('LoginTime', {}).get('$date')
    candidates = []
    for node in walk(login_data):
        activity_id = node.get('ActivityID')
        match = re.search(r'H\d+', activity_id or '') if isinstance(
                activity_id, str) else None
        if not match:
            continue
        start = node.get('StartTime', {}).get('$date', 0)
        end = node.get('EndTime', {}).get('$date', 0)
        if now and start and end and not (start <= now <= end):
            continue
        suffix = match.group(0)
        priority = 0
        # Search for the event id
        if activity_id == f'Branch{suffix}':
            priority = 3
        elif activity_id == f'ActivitySignIn{suffix}':
            priority = 2
        elif activity_id.startswith(('AcyivitySummon', 'ActivitySummon')):
            priority = 1
        if priority:
            candidates.append((priority, int(start or 0), suffix))
    return max(candidates)[2] if candidates else None

def get_pickup(login_data=None):
    if login_data:
        pickup = pickup_from_login(login_data)
        if pickup:
            return pickup
    branches = (
        activity_id
        for activity_id, row in master().get('activities', {}).items()
        if row.get('Type') == 'SideStory'
        and re.fullmatch(r'BranchH\d+', activity_id or '')
    )
    pickup = max(branches, key=lambda value: intv(value.replace('BranchH', '')),
                 default=None)
    return pickup.replace('Branch', '')

def get_activity_scene_ids(pickup):
    prefix = f'B{pickup}_1_'
    scene_ids = [
        row.get('ID')
        for row in master().get('scenes', {}).get(f'Branch{pickup}', [])
        if re.fullmatch(rf'{re.escape(prefix)}\d+', row.get('ID') or '')
    ]
    scene_ids.sort(key=lambda scene_id: intv(scene_id.removeprefix(prefix)))
    return scene_ids or [f'B{pickup}_1_{i + 1}' for i in range(14)]

def parse_team(raw):
    members = []
    for item in re.findall(r'\{[^{}]*M:"[^"]+"[^{}]*\}', raw or ''):
        match = re.search(
            r'M:"(?P<sid>[^"]+)"[^}]*?Pos:(?P<pos>\d+)'
            r'[^}]*?LV:(?P<lv>\d+)',
            item,
        )
        if not match:
            continue
        artifact = re.search(r'ArtifactID:"(?P<id>[^"]+)"', item)
        artifact_lv = re.search(r'ArtifactLV:(?P<lv>\d+)', item)
        members.append({
            'sid': match.group('sid'),
            'pos': int(match.group('pos')),
            'lv': int(match.group('lv')),
            'artifact_id': artifact.group('id') if artifact else '',
            'artifact_lv': int(
                artifact_lv.group('lv') if artifact_lv else 1),
        })
    return members


def _npc_role(static_id, lv=60, artifact_id='', artifact_lv=1,
              skill_ids=None):
    role = {
        '_id': str(uuid.uuid4()),
        'StaticID': str(static_id or ''),
        'Exp': 0,
        'LV': intv(lv, 60),
        'AwakenLV': 0,
        'AwakenValue': 0,
        'Star': 6,
        'ImprintLV': 0,
        'Locks': [],
        'IsLock': 0,
        'IsFavorite': 0,
        'IsSelfImprintOpen': 0,
        'IsDispatched': 0,
        'IsSelfImprint': 0,
        'Skills': {'Skills': [
            {'Level': 1, 'StaticID': skill_id}
            for skill_id in (skill_ids or [])
        ]},
    }
    if artifact_id:
        role['ArtifactData'] = {
            '_id': '',
            'StaticID': artifact_id,
            'Exp': 0,
            'LV': intv(artifact_lv, 1),
            'Enhance': 0,
            'IsLock': 0,
            'IsNew': 1,
        }
    return role


def get_npc_camp(scene_id, db_path=None):
    db_path = Path(db_path) if db_path else data_path('master.db')
    if not db_path.is_file():
        return None
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute(
                'SELECT WaveInfoJsonString FROM Scene WHERE ID=?',
                (scene_id,),
            ).fetchone()
            members = parse_team(row[0]) if row else []
            if not members:
                return None
            role_map = {}
            for member in members:
                role_sid = member['sid'].removeprefix('PVP')
                skill_ids = [
                    str(skill[0]) for skill in conn.execute(
                        'SELECT ID FROM Skill WHERE ID LIKE ? ORDER BY ID',
                        (f'{role_sid}S%',),
                    )
                ]
                role_map[str(member['pos'])] = _npc_role(
                    member['sid'],
                    member['lv'],
                    member['artifact_id'],
                    member['artifact_lv'],
                    skill_ids,
                )
        finally:
            conn.close()
    except sqlite3.Error:
        return None
    return {
        'Name': '方舟α维安小队',
        'PositionRoleMap': role_map,
    }

def get_activity_npc_pos_maps(pickup):
    prefix = f'B{pickup}_1_'
    rows = [
        row for row in master().get('scenes', {}).get(f'Branch{pickup}', [])
        if row.get('MyCampTeam')
    ]
    rows.sort(key=lambda row: intv((row.get('ID') or '').removeprefix(prefix)))
    npc_maps = {}
    for row in rows:
        members = parse_team(row.get('MyCampTeam') or '')
        if not members:
            continue
        preferred = [m for m in members if m['sid'] == f'AcStory{pickup}']
        source = preferred or members[:1]
        index = int((row.get('ID') or '0_2').rsplit('_', 1)[-1]) - 1
        npc_maps[index] = {
            str(i): {'StaticID': m['sid'], 'LV': m['lv']}
            for i, m in enumerate(source)
        }
    return npc_maps or {1: {'0': {'StaticID': f'AcStory{pickup}', 'LV': 60}}}

def get_event(login_data):
    pickup = get_pickup(login_data)
    scene_ids = get_activity_scene_ids(pickup)
    npc_maps = get_activity_npc_pos_maps(pickup)
    return {'pickup': pickup, 'scene_ids': scene_ids, 'npc_maps': npc_maps}
