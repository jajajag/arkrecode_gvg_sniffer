from utils.helper import get_role
from utils.login_helper import send


def normalize_oids(value):
    if isinstance(value, dict):
        if set(value) == {'$oid'}:
            return value['$oid']
        return {key: normalize_oids(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_oids(item) for item in value]
    return value


def support_label(item):
    role = item.get('Role') or {}
    job = item.get('SupportJob') or 'Unknown'
    name = get_role(role.get('StaticID'))
    level = role.get('LV')
    star = role.get('Star')
    parts = [job, name]
    if level:
        parts.append(f'Lv{level}')
    if star:
        parts.append(f'{star}星')
    return ' '.join(parts)


def query_player_supports(aid, session_id, cuid):
    data = send({
        'route': 'AccountHandler.QueryPlayerCardData',
        'data': {
            'CUID': cuid,
            'AID': aid,
            'SessionID': session_id,
        },
    })
    support_data = data.get('BattleSupportData') if isinstance(data, dict) else None
    if not isinstance(support_data, dict):
        return []

    player_info = support_data.get('PlayerInfo') or {}
    is_friend = bool(support_data.get('IsFriend'))
    supports = []
    for item in support_data.get('RoleDataList') or []:
        role = item.get('Role')
        if not isinstance(role, dict) or not role.get('StaticID'):
            continue
        supports.append({
            'label': support_label(item),
            'support': {
                'PlayerRoleData': {
                    'PlayerInfo': normalize_oids(player_info),
                    'RoleData': normalize_oids(role),
                },
                'IsFriend': 1 if is_friend else 0,
                'Job': item.get('SupportJob') or '',
                'IsNPC': 0,
            },
        })
    return supports


def prompt_support_cuid():
    cuid_text = input('请输入助战UID（默认不借人）: ').strip()
    return int(cuid_text) if cuid_text.isdigit() else None


def placeholder_support(cuid):
    return {
        'PlayerRoleData': {
            'PlayerInfo': {'CUID': cuid},
            'RoleData': {'StaticID': 'H001'},
        },
    }


def choose_placeholder_support():
    cuid = prompt_support_cuid()
    return placeholder_support(cuid) if cuid is not None else None


def choose_support(aid, session_id):
    cuid = prompt_support_cuid()
    if cuid is None:
        return None

    try:
        supports = query_player_supports(aid, session_id, cuid)
    except Exception as exc:
        print(f'查询助战失败，跳过借人：{exc}')
        return None
    if not supports:
        print('没有找到可借助战，跳过借人。')
        return None

    print('[选择助战]')
    for index, support in enumerate(supports, start=1):
        print(f'{index}. {support["label"]}')
    choice = input('请选择助战编号：').strip()
    if not choice.isdigit() or not (1 <= int(choice) <= len(supports)):
        print('无效选择，跳过借人。')
        return None
    return supports[int(choice) - 1]['support']
