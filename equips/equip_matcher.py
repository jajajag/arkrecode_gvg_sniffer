from collections import defaultdict
import json

RULE_PATH = 'equips/equipments.json'
TYPE_MAP = {
    '1': 'Weapon',
    '2': 'Head',
    '3': 'Body',
    '4': 'Necklace',
    '5': 'Ring',
    '6': 'Shoes',
}

def _load_rule_index(path=RULE_PATH):
    with open(path, 'r', encoding='utf-8') as f:
        rules = json.load(f)

    index = defaultdict(list)
    for rule in rules:
        key = (rule['type'], rule['set_name'],
               rule['main_prop'], rule['status'])
        index[key].append(rule)
    return index

RULE_INDEX = _load_rule_index()

def get_type(equip):
    return TYPE_MAP.get(equip['StaticID'][-1])

def match_equip(equip, is_gold):
    status = 'gold' if is_gold else 'star'
    eq_type = get_type(equip)

    sub_props = {
        x['PropertyType']: x['Value'] for x in equip['SubProps']['SourceValues']
    }

    main_prop = equip['MainProp']['PropertyType']
    set_name = equip['Set']

    key = (eq_type, set_name, main_prop, status)
    key_both = (eq_type, set_name, main_prop, 'both')

    for rule in RULE_INDEX.get(key, []) + RULE_INDEX.get(key_both, []):
        if all(sub_props.get(p, -1) >= v for p, v in rule['sub_props'].items()):
            print(f'{eq_type} {set_name} {main_prop} -> {sub_props}')
            return equip

    return None
