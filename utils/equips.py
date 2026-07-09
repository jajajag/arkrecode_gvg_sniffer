import json
from utils.helper import data_path

# Load configuration from config.json
with data_path('config.json').open('r', encoding='utf-8') as fp:
    CONFIG = json.load(fp)

EQUIP_SCORE_MIN_LEFT = CONFIG['equip_score_min_left']
EQUIP_SCORE_MIN_RIGHT = CONFIG['equip_score_min_right']
EQUIP_SETS = CONFIG['equip_sets']
EQUIP_TEMPLATES = CONFIG['equip_templates']

TYPE_MAP = {
    '1': 'Weapon', '2': 'Head', '3': 'Body',
    '4': 'Necklace', '5': 'Ring', '6': 'Shoes'
}
RIGHT_TYPES = {'Necklace', 'Ring', 'Shoes'}
# LV85 equips
VALID_PREFIXES = {'E010', 'E016', 'E022', 'E028', 'E034'}
# Sets that require special handling for speed
SPEED_SETS = {'Speed', 'Revenge'}
PROP_SCORE = {
    'AttackRate': 180,
    'AttackValue': 0.17,
    'CriticalDamageRate': 180,
    'CriticalRate': 200,
    'DefenceRate': 180,
    'DefenceValue': 0.2,
    'EffectHitRate': 125,
    'HPValue': 0.05,
    'HPRate': 150,
    'ResistanceRate': 125,
    'SpeedValue': 3.5,
}

def format_match(eq_type, set_name, main_prop, score, sub_dict):
    score = f'{score:.1f}'.rstrip('0').rstrip('.')
    sub_dict = sorted(sub_dict.items())
    return f'{eq_type} {set_name} {main_prop} {score} -> {sub_dict}'

def match_template(eq_type, set_name, main_prop, score, sub_dict):
    sub_props = set(sub_dict)
    for name in EQUIP_SETS[set_name]:
        template = EQUIP_TEMPLATES[name]
        allowed_subs = set(template['subprops'])
        # 1. Check if all subprops are allowed by the template
        if not sub_props.issubset(allowed_subs):
            continue
        # 2. Check if main prop is allowed for right-side equips
        if eq_type in RIGHT_TYPES and main_prop not in template[eq_type]:
            continue
        return format_match(eq_type, set_name, main_prop, score, sub_dict)
    return None

def match_equip(equip):
    static_id = equip['StaticID']
    eq_type = TYPE_MAP[static_id[-1:]]

    # 1. Check if the equip is legendary
    if equip['ClassLV'] < 4:
        return None
    # 2. Check if the equip is LV85
    if static_id[:4] not in VALID_PREFIXES:
        return None

    set_name = equip['Set']
    main_prop = equip['MainProp']['PropertyType']
    sub_dict = {
        x['PropertyType']: x['Value']
        for x in equip['SubProps']['SourceValues']
    }

    speed = sub_dict.get('SpeedValue', 0)
    # 3. Sets with speed must have a SpeedValue >= 4
    if set_name in SPEED_SETS:
        if eq_type == 'Shoes' and main_prop != 'SpeedValue':
            return None
        elif speed < 4:
            return None

    score = sum(value * PROP_SCORE[prop] for prop, value in sub_dict.items())
    # 4. If it's not shoes, we take the equip without further checks
    if eq_type != 'Shoes' and speed >= 5:
        return format_match(eq_type, set_name, main_prop, score, sub_dict)
    # 5. Check if the score meets the minimum threshold for the equip type
    if eq_type in RIGHT_TYPES and score < EQUIP_SCORE_MIN_RIGHT:
        return None
    if eq_type not in RIGHT_TYPES and score < EQUIP_SCORE_MIN_LEFT:
        return None

    # 6. Check if subprops match a template
    return match_template(eq_type, set_name, main_prop, score, sub_dict)
