from utils.analyzer import analyze_gvg, analyze_gvg_defence, analyze_pvp_equips
from utils.equips import match_equip
from utils.exporter import export_report
from utils.printer import print_report
from utils.helper import get_event
from utils.login_helper import capture_login
from utils.master import ensure_master_db
import base64
import json
import os
import random
import requests
import time

requests.packages.urllib3.disable_warnings()

url = 'https://game-arkre-labs.ecchi.xxx/Router/RouterHandler.ashx'
url_token = 'https://sadpki-portal-v2.ebuajk.com/api/v2/token/access'
headers = {
    'Content-Type': 'application/octet-stream',
    'User-Agent': 'UnityPlayer/2022.3.62f2 (UnityWebRequest/1.0, libcurl/8.10.1-DEV)'
}

def load_config(config_path='data/config.json'):
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_accounts(account_path='data/accounts.json'):
    if not os.path.exists(account_path):
        return []
    with open(account_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_accounts(accounts, account_path='data/accounts.json'):
    os.makedirs(os.path.dirname(account_path), exist_ok=True)
    with open(account_path, 'w', encoding='utf-8') as f:
        json.dump(accounts, f, ensure_ascii=False, indent=2)

def add_account(accounts):
    while True:
        name = input('给账号起个名字：').strip()
        if name:
            break
    try:
        payload = capture_login()
    except Exception as exc:
        print(f'添加账号失败：{exc}')
        return None

    accounts.append({
        'Name': name,
        'Token': payload['jwt']
    })
    save_accounts(accounts)
    print(f'已添加账号：{name}')
    return len(accounts) - 1

def delete_account(accounts):
    if not accounts:
        print('当前没有可删除的账号。')
        return

    idx = input('删除账号：').strip()
    if idx.isdigit() and 0 < int(idx) <= len(accounts):
        removed = accounts.pop(int(idx) - 1)
        save_accounts(accounts)
        print(f'已删除账号：{removed.get("Name")}')
    else:
        print('删除失败，请选择正确的账号编号！')

def choose_account(accounts):
    while True:
        if not accounts:
            print('没有已保存账号，请先添加账号。')
            acc_idx = add_account(accounts)
            if acc_idx is not None:
                return acc_idx
            continue

        print('[选择账号]')
        for i, acc in enumerate(accounts):
            print(f'{i + 1}. {acc.get("Name")}')
        print('+. 添加账号')
        print('-. 删除账号')

        while True:
            idx = input('> ').strip()
            if idx == '+':
                acc_idx = add_account(accounts)
                if acc_idx is not None:
                    return acc_idx
                break
            if idx == '-':
                delete_account(accounts)
                break
            if idx.isdigit() and 0 < int(idx) <= len(accounts):
                return int(idx) - 1

def choose_action():
    actions = [
        '刷NPC',
        '刷活动讨伐',
        '刷日常',
        '刷神秘商店',
        '刷星源商店',
        '刷佣兵团周任务',
        '刷亲密度',
        '查询团战总结',
        '查询团战防守',
        '重新登录'
    ]

    print('[选择功能]')
    for i, a in enumerate(actions):
        print(f'{(i + 1) % 10}. {a}')
    
    while True:
        c = input('> ').strip()
        if c in ('114514', '1919810') \
                or (c.isdigit() and 0 <= int(c) < len(actions)):
            return int(c)

def send(payload):
    time.sleep(random.uniform(1, 2))
    resp = requests.post(url, json=payload, headers=headers, verify=False)
    resp.encoding = 'utf-8'
    return resp.json()

def run_bulletin():
    payload = {
        'data': {},
        'route': 'GameServerDBSettingHandler.QueryBulletinInfoResult'
    }
    return send(payload)

def get_login_version(bulletin):
    return bulletin['Info']['AvailableVersions'][-1]

def run_refresh_token(accounts, acc_idx):
    # device_id = accounts[acc_idx]['DeviceID']
    refresh_token = accounts[acc_idx]['Token']
    local_headers = headers.copy()
    local_headers['Authorization'] = f'Bearer {refresh_token}'
    # local_headers['DeviceId'] = device_id
    time.sleep(random.uniform(1, 2))
    resp = requests.post(url_token, headers=local_headers)
    resp.encoding = 'utf-8'
    data = resp.json()
    accounts[acc_idx]['Token'] = data['data']['refreshToken']
    save_accounts(accounts)
    return data

def run_old_sdk(accounts, acc_idx):
    token = accounts[acc_idx]['Token']
    jwt = token.split('.')[1]
    jwt += '=' * (-len(jwt) % 4)
    token_data = json.loads(base64.urlsafe_b64decode(jwt))
    login_id = token_data['user_id']
    if 'exp' in token_data:
        return True, login_id
    return False, login_id

def run_login(accounts, acc_idx, version):
    # On Android it seems they are using an old SDK
    is_new_sdk, login_id = run_old_sdk(accounts, acc_idx)
    if is_new_sdk:
        token_data = run_refresh_token(accounts, acc_idx)
        login_id = token_data['data']['userId']
        token = token_data['data']['accessToken']
    else:
        token = accounts[acc_idx]['Token']
    payload = {
        'data': {
            'LoginID': login_id,
            'Token': token,
            'Version': version,
            # 'DeviceID': accounts[acc_idx]['DeviceID'],
            'LoginType': 'Erolabs',
            'IsNewSDK': is_new_sdk
        },
        'route': 'AccountHandler.Login'
    }
    return send(payload)

# 1. 刷NPC
def run_npc_ticket(aid, session_id, npc):
    payload = {
        'data':{
            'NPCSceneID': f'HellNPC_{npc}',
            'AID': aid,
            'SessionID': session_id
        },
        'route': 'PVPHandler.PVPCheckTicket'
    }
    # Spend ticket
    send(payload)

def run_npc_battle(aid, session_id, npc, pos_map=None):
    payload = {
        'data': {
            'NPCSceneID': f'HellNPC_{npc}',
            'EndData': {
                'StartBattleInfo': {},
                'Result': 'Win',
            },
            'AID': aid,
            'SessionID': session_id
        },
        'route': 'PVPHandler.NPCPVPBattleEnd'
    }
    if pos_map:
        payload['data']['EndData']['StartBattleInfo']['CampData1'] = {
                'PositionRoleMap': pos_map}
    return send(payload)

def run_npc(aid, session_id, npc_list):
    now = int(time.time() * 1000)
    targets = [npc for npc in npc_list if now > npc_list[npc]]
    print(f'当前可挑战NPC：{targets}')
    try:
        for npc in targets:
            run_npc_ticket(aid, session_id, npc)
            data = run_npc_battle(aid, session_id, npc)
            npc_list[npc] = float('inf')
            print(f'NPC {npc} 挑战{"成功" if data["IsWin"] else "失败"}！')
    except Exception:
        print('挑战结束：没有旗帜！')

# 2. 刷活动讨伐
def run_battle(aid, session_id, pos_map, event):
    payload = {
        'data': {
            'BattleEndData': {
                'StartBattleInfo': {
                    'SceneData': {'StaticID': ''}, 
                    'CampData1': {'PositionRoleMap': pos_map}
                }, 
                'Result': 'Win'
            }, 
            'AID': aid,
            'SessionID': session_id
        },
        'route': 'SceneHandler.FinishScene'
    }
    start_battle_info = payload['data']['BattleEndData']['StartBattleInfo']
    scene = start_battle_info['SceneData']
    camp1 = start_battle_info['CampData1']
    elems = [('火', 'Fire'), ('水', 'Ice'), ('木', 'Earth'), 
             ('光', 'Light'), ('暗', 'Dark')]
    print(' '.join(f'{i + 1}. {name}讨伐' for i, (name, _) in enumerate(elems)))
    print(' '.join(f'{i + 6}. {name}元素' for i, (name, _) in enumerate(elems)))
    print('11. 活动EX 12. 一键活动')
    
    c = input('请选择关卡编号：').strip()
    if not c.isdigit() or not (1 <= (c := int(c)) <= 12):
        print('无效选择！')
        return
    repeat_str = input('请输入挑战次数（默认10次）：').strip()
    repeat = int(repeat_str) if repeat_str.isdigit() else 10
    if c >= 11: # Handle support
        sup = input('请输入助战UID（默认不借人）: ').strip()
        if sup.isdigit():
            start_battle_info['Support'] = {
                'PlayerRoleData': {
                    'PlayerInfo': {'CUID': int(sup)},
                    'RoleData': {'StaticID': 'H001'}
                }
            }
    
    if c <= 10:
        idx = (c - 1) % 5
        prefix = 'Hunt' if c <= 5 else 'Elf'
        suffix = 11 if c <= 5 else 4
        sid = f'{prefix}{elems[idx][1]}_{suffix}'
        runs = [{'static_id': sid, 'pos_map': pos_map}] * repeat
    elif c == 11:
        sid = event['scene_ids'][-2]
        runs = [{'static_id': sid, 'pos_map': pos_map}] * repeat
    else: # c == 12
        runs = [
            {'static_id': sid,
             'pos_map': event['npc_maps'].get(i, pos_map)}
            for i, sid in enumerate(event['scene_ids'][:12])
        ] * repeat

    print('开始刷活动讨伐...')
    try:
        for run in runs:
            scene['StaticID'] = run['static_id']
            camp1['PositionRoleMap'] = run['pos_map']
            data = send(payload)
            energy = data['CostItems'][0]['NowItem']['Count']
            print(f'挑战成功，剩余体力：{energy}')
            # Check for urgent missions
            for m in data.get('UrgentMissionContainer', {}).get('Missions', []):
                if urgent_sid := m['SceneID']:
                    scene['StaticID'] = urgent_sid
                    camp1['PositionRoleMap'] = pos_map
                    data = send(payload)
                    print(f'紧急任务完成：{urgent_sid}')
    except Exception:
        print('挑战失败：体力不足，装备已满，或活动代码错误！')

# 3. 刷日常
def run_dispatched_quests(aid, session_id, d_quests):
    payload_reward = {
        'data': {
            'QuestStaticID': '',
            'AID': aid,
            'SessionID': session_id
        },
        'route': 'ArkHighCommandHandler.RewardQuest'
    }
    payload_dispatch = {
        'data': {
            'Quest': {
                'StaticID': '',
                'DispatchedHeroIDs': []
            },
            'AID': aid,
            'SessionID': session_id
        },
        'route': 'ArkHighCommandHandler.DispatchQuest'
    }
    now = int(time.time() * 1000)
    targets = [quest_id for quest_id in d_quests
               if now > d_quests[quest_id]['FinishTime']['$date']]
    print(f'当前可派遣任务：{targets}')
    for quest_id in targets:
        try:
            payload_reward['data']['QuestStaticID'] = quest_id
            reward_data = send(payload_reward)
            hero_ids = reward_data['FinishedQuest']['DispatchedHeroIDs']
            #hero_ids = d_quests[quest_id]['DispatchedHeroIDs']
            payload_dispatch['data']['Quest']['StaticID'] = quest_id
            payload_dispatch['data']['Quest']['DispatchedHeroIDs'] = hero_ids
            send(payload_dispatch)
            d_quests[quest_id]['FinishTime']['$date'] = float('inf')
            print(f'派遣成功：{quest_id}')
        except Exception:
            # The quest has not been completed
            continue

def run_guild_support(aid, session_id, sups):
    cuid = sups['_cuid']
    payload_guild = {
        'data': {
            'AID': aid,
            'SessionID': session_id
        },
        'route': 'GuildHandler.QueryFullGuildData'
    }
    try:
        print('正在支援佣兵团...')
        data = send(payload_guild)
    except Exception:
        print('查询失败：未加入佣兵团！')
        return
    guild_aid_items = data['GuildData']['GuildAidItemInfoList']
    payload = {
        'data': {
            'GuildAidItemInfoID': '',
            'AID': aid,
            'SessionID': session_id
        },
        'route': 'GuildHandler.SupportGuildAid'
    }
    try:
        for item in guild_aid_items:
            if (item['NowCount'] >= 8
                or sups.get(item['ItemID'], 0) < 2
                or item['Requester']['CUID'] == cuid
                or cuid in item['SupporterList']):
                continue
            payload['data']['GuildAidItemInfoID'] = item['_id']['$oid']
            send(payload)
            sups[item['ItemID']] -= 2
            print(f'支援成功：{item["ItemID"]}')
    except Exception:
        print('支援结束：已达上限！')
    support_items = {
        item_id: count for item_id, count in sups.items()
        if not item_id.startswith('_')
    }
    payload_support = {
        'data': {
            'ItemID': min(support_items, key=support_items.get),
            'AID': aid,
            'SessionID': session_id
        },
        'route': 'GuildHandler.RequestGuildAid'
    }
    # Skip if the player has already requested today
    if any(item['Requester']['CUID'] == cuid for item in guild_aid_items):
        return
    try:
        send(payload_support)
        print(f'请求成功：{payload_support["data"]["ItemID"]}')
    except Exception:
        print('请求失败：今日已请求过！')

def run_daily(aid, session_id, sups, event, d_quests, bp_id):
    run_dispatched_quests(aid, session_id, d_quests)
    run_guild_support(aid, session_id, sups)
    payloads = [
        # Force lab
        {'route': 'ArkReactorHandler.RewardArkReactor'},
        {'route': 'ArkStarForceLabHandler.ChargeTesseract'},
        {'route': 'ArkStarForceLabHandler.RewardPotion'},
        {'route': 'ArkStarForceLabHandler.RewardStarForce'},
        {'route': 'ArkStarForceLabHandler.RewardTesseract'},
        # Guild daily
        {'route': 'GuildHandler.GuildMemberCheckIn'},
        {'route': 'GuildHandler.DonateCourage',
         'data': {'ItemID': '28', 'Count': 3}},
        {'route': 'GuildHandler.DonateGold',
         'data': {'ItemID': '1', 'Count': 10}},
        {'route': 'GuildHandler.GuildMemberDayCheckReward'},
        # Monthly sign-in
        {'route': 'MonthSignInHandler.SignIn'},
        # Abyss
        {'route': 'SceneHandler.PurityScene',
         'data': {'StaticID': 'Abyss_80'}}, 
        # Monthly pack
        {'route': 'ServerStatusHandler.Query'},
        # Store (FriendShip)
        {'route': 'StoreHandler.BuyCommodity', 
         'data': {'Record': {'StaticID': 'FriendShip3'}, 'Count': 1}},
        {'route': 'StoreHandler.BuyCommodity',
         'data': {'Record': {'StaticID': 'FriendShip4'}, 'Count': 1}},
        {'route': 'StoreHandler.BuyCommodity',
         'data': {'Record': {'StaticID': 'FriendShip6'}, 'Count': 1}},
        {'route': 'StoreHandler.BuyCommodity',
         'data': {'Record': {'StaticID': 'FriendShip7'}, 'Count': 1}},
        # Store (VIPGift)
        {'route': 'StoreHandler.BuyCommodity',
         'data': {'Record': {'StaticID': 'VIPGIFT_VIPQuick1'}, 'Count': 1}},
        {'route': 'StoreHandler.BuyCommodity',
         'data': {'Record': {'StaticID': 'VIPGIFT_VIPQuick2'}, 'Count': 1}},
        {'route': 'StoreHandler.BuyCommodity',
         'data': {'Record': {'StaticID': 'VIPGIFT_VIPQuick3'}, 'Count': 1}},
        {'route': 'StoreHandler.BuyCommodity',
         'data': {'Record': {'StaticID': 'VIPGIFT_VIPQuick4'}, 'Count': 1}},
        # Store (MedalHonor)
        {'route': 'StoreHandler.BuyCommodity',
         'data': {'Record': {'StaticID': 'MedalHonor2'}, 'Count': 3}},
        # Support, TimingMeal, and Weekly sign-in
        {'route': 'SupportFriendHandler.GetReward'},
        {'route': 'TimingMealHandler.SentMeal'},
        {'route': 'WeekSignInHandler.SignIn',
         'data': {'ActivityID': f'ActivitySignIn{event["pickup"]}'}},
        # Daily / Weekly / Monthly rewards
        {'route': 'QuestHandler.RewardQuest',
         'data': {'RewardQuestInfos': [
             {'ID': 'DailyScore10', 'Index': 0},
             {'ID': 'DailyScore20', 'Index': 0},
             {'ID': 'DailyScore30', 'Index': 0},
             {'ID': 'DailyScore50', 'Index': 0},
             {'ID': 'DailyScore80', 'Index': 0},
             {'ID': 'DailyScore100', 'Index': 0}]}},
        {'route': 'QuestHandler.RewardQuest',
         'data': {'RewardQuestInfos': [
             {'ID': 'WeekScore20', 'Index': 0},
             {'ID': 'WeekScore40', 'Index': 0},
             {'ID': 'WeekScore60', 'Index': 0},
             {'ID': 'WeekScore80', 'Index': 0},
             {'ID': 'WeekScore100', 'Index': 0},
             {'ID': 'WeekScore120', 'Index': 0}]}},
        {'route': 'BattlePassHandler.GetAllNowRankReward',
         'data': {'ActivityID': bp_id}}
    ]
    for payload in payloads:
        payload_new = {
            'route': payload['route'],
            'data': {
                **payload.get('data', {}),
                'AID': aid,
                'SessionID': session_id,
            }
        }
        try:
            send(payload_new)
            print(f'{payload} 成功！')
        except Exception:
            print(f'{payload} 失败！')

# 4. 刷神秘商店
def run_secret(aid, session_id, secrets):
    print('正在刷神秘商店...')
    buy_list = [
        # Ampleons
        {'Count': 1, 'StaticID': 'EC11'},
        {'Count': 1, 'StaticID': 'EC21'},
        {'Count': 1, 'StaticID': 'EC31'},
        {'Count': 1, 'StaticID': 'EC41'},
        {'Count': 1, 'StaticID': 'EC51'},
        {'Count': 1, 'StaticID': 'EC61'},
        # Recruit contract and mysterious contract
        {'Count': 5, 'StaticID': '5'},
        {'Count': 50, 'StaticID': '6'},
    ]
    payload_refresh = {
        'data': {
            'StoreID': 'SecretShop',
            'IsUseGold': 1,
            'AID': aid,
            'SessionID': session_id
        },
        'route': 'StoreHandler.ResetRandomStore'
    }
    payload_buy = {
        'data': {
            'Record': {'_id': '', 'StaticID': ''},
            'AID': aid,
            'SessionID': session_id
        },
        'route': 'StoreHandler.BuyCommodity'
    }
    while True:
        for record in secrets:
            item = record['DropResult']['Items'][0]
            # Skip if neither in buy_list nor a desired equipment
            if not (('Item' in item and item['Item'] in buy_list) or
                    ('Equipment' in item and match_equip(item['Equipment']))):
                continue
            payload_buy['data']['Record']['_id'] = record['_id']['$oid']
            payload_buy['data']['Record']['StaticID'] = record['StaticID']
            try:
                send(payload_buy)
                print(f'购买成功：{item.get("Item") or item.get("Equipment")}')
            except Exception:
                print(f'购买失败：{item.get("Item") or item.get("Equipment")}')
        try:
            secrets = send(payload_refresh)
            secrets = secrets['Records']
            print('商店刷新成功！')
        except Exception:
            print('商店刷新结束：次数已满！')
            return

# 5. 刷星源商店
def run_rainbow(aid, session_id):
    payload = {
        'data': {
            'CommodityID': 'RainbowStarSourceBox10',
            'AID': aid,
            'SessionID': session_id
        },
        'route': 'CustomEquipHandler.Query'
    }
    print('正在刷新星源商店...')
    while True:
        try:
            data = send(payload)
            payload['route'] = 'CustomEquipHandler.RefreshEquip'
            equips = data['Data']['CustomEquipDropList']
            found = [match_equip(e['Equipment']) for e in equips]
            if found := [e for e in found if e]:
                print(*found, sep='\n')
                choice = input('找到极品装备！是否继续刷新？(y/N)：').strip()
                if choice.upper() != 'Y': return
            else:
                print('刷新成功！')
        except Exception:
            print('刷新结束：次数已满！')
            return

# 6. 刷佣兵团周任务
def run_weekly(aid, session_id, repeat=140):
    payload = {
        'data' : {
            'RewardQuestInfos' : [{'ID' : 'GuildCheckIn', 'Index' : 0}],
            'CommodityID' : '',
            'AID' : aid,
            'SessionID' : session_id
        },
        'route' : 'QuestHandler.RewardQuest'
    }
    for i in range(repeat):
        send(payload)
        print(f'正在刷每周任务...（{i + 1}/{repeat}）')
    print(f'每周任务完成！共{repeat}次')

# 7. 刷亲密度
def run_affection(aid, session_id, npc_list, pos_map):
    now = int(time.time() * 1000)
    targets = [npc for npc in npc_list if now > npc_list[npc]]
    if not targets:
        print('刷亲密度失败：请先保留至少一个可挑战的NPC！')
        return
    print(f'当前可挑战NPC：{targets}')
    repeat = input('请输入刷亲密度次数（默认第一队10次）：').strip()
    repeat = int(repeat) if str(repeat).isdigit() else 10
    try:
        for i in range(repeat):
            run_npc_battle(aid, session_id, targets[i % len(targets)], pos_map)
            print(f'正在刷亲密度...（{i + 1}/{repeat}）')
    except Exception:
        print('刷亲密度失败：可能是未解锁地狱难度NPC！')
    print('亲密度刷完了！')

# 8. 查询团战总结
def run_guild_summary(aid, session_id, guild_data, gid=None, save_csv=True):
    payload = {
        'data': {
            'GuildID': gid,
            'AID': aid,
            'SessionID': session_id
        },
        'route': 'GuildHandler.QueryPartialGuildDataForGuildWar'
    }
    if not gid:
        gid = input('请输入佣兵团 GID（默认查询本团）：').strip()
        payload['data']['GuildID'] = gid
    try:
        print('正在查询团战总结...')
        if gid: guild_data = send(payload)
        return analyze_gvg(guild_data, aid, session_id, save_csv)
    except Exception:
        print('查询失败：未加入佣兵团，未开启团战，或佣兵团 GID 错误！')
        return []

# 9. 查询团战防守
def run_gvg_update(aid, session_id, cuid):
    payload = {
        'data': {
            'AID': aid,
            'SessionID': session_id
        },
        'route': 'GuildWarHandler.QueryNowGuildWarRank'
    }
    try:
        data = send(payload)
    except Exception:
        print('查询失败：未加入佣兵团！')
        return
    guilds = data['GuildWarCampaignInfoList']
    # 0 for not querying
    num_def = input('请输入要查询的前排团战防守（最多前20）：')
    num_def = int(num_def) if str(num_def).strip().isdigit() else 20
    # Query for the top 20 guilds
    for i in range(min(num_def, len(guilds))):
        print(f'正在查询第{i + 1}名佣兵团的防守数据...')
        gid = guilds[i]['GuildSubInfo']['_id']['$oid']
        rows = run_guild_summary(aid, session_id, None, gid=gid, save_csv=False)
        analyze_gvg_defence(aid, session_id, cuid, rows)
    print('防守数据查询完成！')

def run_pvp_update(aid, session_id, cuid, week):
    payload = {
        'data': {
            'Week': week,
            'AID': aid,
            'SessionID': session_id
        },
        'route': 'PVPHandler.GetPVPRankList'
    }
    try:
        print('正在更新装备数据...')
        data = send(payload)
    except Exception:
        print('查询失败：排名可能在结算中！')
        return
    analyze_pvp_equips(data)
    print('装备数据更新完成！')
    # We now update GVG defence data here
    run_gvg_update(aid, session_id, cuid)

# 114514. 查询团战数据
def run_guild_data(aid, session_id):
    payload = {
        'data': {
            'AID': aid,
            'SessionID': session_id
        },
        'route': 'GuildWarHandler.QueryFullGuildWarData'
    }
    try:
        data = send(payload)
    except Exception:
        print('查询失败：未加入佣兵团或未开启团战！')
        return
    print_report(data)
    export_report(data)

# 1919810. 查询JJC数据
def run_pvp_log_data(aid, session_id):
    if input('此功能将导致JJC进场，是否继续：（Y/n）').strip().lower() == 'n':
        return
    # Query PVP data
    try:
        print('正在查询JJC信息...')
        data = send({
            'data': {
                'AID': aid,
                'SessionID': session_id
            },
            'route': 'PVPHandler.QueryPVPData'
        })
        print(data)
    except Exception:
        print('JJC查询失败！')
        return
    print_report(data)
    # Query revenge data
    logs = data['PVPData']['PVPLogList']
    revenge_logs = [log for log in logs if log['CanRevengeBattle']]
    if not revenge_logs:
        print('没有可复仇的对象！')
        return
    for i, log in enumerate(revenge_logs, 1):
        print(f'-----可复仇对象 {i}/{len(revenge_logs)}-----')
        enemy_cuid = log['PlayerInfo']['CUID']
        log_id = log['_id']['$oid']
        try:
            print_report(send({
                'data': {
                    'EnemyCUID': enemy_cuid,
                    'LogID': log_id,
                    'AID': aid,
                    'SessionID': session_id
                },
                'route': 'PVPHandler.QueryRevengeEnemyData'
            }))
        except Exception:
            print(f'复仇查询失败：{enemy_cuid}')

def extract_login_values(data):
    # 1, 2, 3, 4, 5, 6, 7, 8, 9
    aid = data['Info']['_id']['$oid']
    session_id = data['SessionID']
    # 1, 7
    npc_list = {}
    for npc in data['PVPData']['NPCPVPInfoList']:
        npc_list[npc['NPCID']] = max(npc['NextTime']['$date'],
                                   npc_list.get(npc['NPCID'], 0))
    # 2, 3
    event = get_event(data)
    npc_levels = ', '.join(str(i + 1) for i in sorted(event['npc_maps']))
    print(f'当前活动：{event["pickup"]}，NPC关卡：{npc_levels}')
    # 2, 7
    first_team = data['Teams']['Settings'][0]
    pos_map = first_team['TeamSetting']['RolePosMap']
    pos_map = {str(pos): {'_id': role_id} for role_id, pos in pos_map.items()}
    # 3, 9
    cuid = data['Info']['CUID']
    # 3
    d_quests = {
        q['StaticID']: q
        for q in data['ArkHighCommandData'].get('DispatchedQuests', [])
    }
    battle_pass_data = data['BattlePassDataContainer']['BattlePassDataList'][0]
    bp_id = battle_pass_data['ActivityID']
    sups = {'CR14': 0, 'CR24': 0, 'CR34': 0, 'CR44': 0, 'CR54': 0}
    sups.update({
        x['StaticID']: x['Count'] for x in data['ItemContainer']['Items']
        if x.get('StaticID') in sups
    })
    sups['_cuid'] = cuid
    # 4
    secrets = [item for item in data['StoreRecordContainer']['Records'] \
            if item['Store'] == 'SecretShop']
    # 8
    guild_data = {'GuildData': data.get('GuildData', {})}
    # 9
    week = data['PVPData']['PVPRankInfo']['RankWeek']

    return (aid, session_id, npc_list, event, pos_map, cuid, d_quests, bp_id,
            sups, secrets, guild_data, week)

def main():
    print('脚本有风险，使用需谨慎！')
    print('代码开源于https://github.com/jajajag/arkrecode_gvg_sniffer')
    bulletin = run_bulletin()
    ensure_master_db(bulletin)
    accounts = load_accounts()
    acc_idx = choose_account(accounts)
    action = 0
    print(f'当前账号：{accounts[acc_idx].get("Name")}')
    while True:
        if action == 0:
            version = get_login_version(bulletin)
            print('登录中...')
            try:
                data = run_login(accounts, acc_idx, version)
                (aid, session_id, npc_list, event, pos_map,
                 cuid, d_quests, bp_id, sups, secrets,
                 guild_data, week) = extract_login_values(data)
                print('登录成功！')
            except Exception:
                retry = input('登录失败，是否重新登录？（Y/n）').strip().lower()
                if retry == 'n':
                    break
                continue
        if (action := choose_action()) == 0: continue
        actions = {
            # 刷NPC
            1: lambda: run_npc(aid, session_id, npc_list),
            # 刷活动讨伐
            2: lambda: run_battle(aid, session_id, pos_map, event),
            # 刷日常
            3: lambda: run_daily(aid, session_id, sups, event, d_quests, bp_id),
            # 刷神秘商店
            4: lambda: run_secret(aid, session_id, secrets),
            # 刷星源商店
            5: lambda: run_rainbow(aid, session_id),
            # 刷佣兵团周任务
            6: lambda: run_weekly(aid, session_id, repeat=140),
            # 刷亲密度
            7: lambda: run_affection(aid, session_id, npc_list, pos_map),
            # 查询团战总结
            8: lambda: run_guild_summary(aid, session_id, guild_data),
            # 查询团战防守
            9: lambda: run_pvp_update(aid, session_id, cuid, week),
            # 查询团战数据
            114514: lambda: run_guild_data(aid, session_id),
            # 查询JJC数据
            1919810: lambda: run_pvp_log_data(aid, session_id),
        }
        actions.get(action, lambda: None)()

if __name__ == '__main__':
    main()
