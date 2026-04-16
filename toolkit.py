from equips.equip_matcher import match_equip
# 装备模板文件来源于蜜娜（请大家支持蜜娜）
# 装备模板来源于太上天魔
from utils.analyzer import analyze_guild, analyze_defence
from utils.printer import print_report
from utils.exporter import export_report
import base64
import json
import os
import random
import requests
import time

PICKUP = 'H179'

requests.packages.urllib3.disable_warnings()

url = 'https://game-arkre-labs.ecchi.xxx/Router/RouterHandler.ashx'
url_token = 'https://sadpki-portal-v2.ebuajk.com/api/v2/token/access'
headers = {
    'Content-Type': 'application/octet-stream',
    'User-Agent': 'UnityPlayer/2022.3.62f2 (UnityWebRequest/1.0, libcurl/8.10.1-DEV)'
}

def load_accounts():
    if not os.path.exists('accounts.json'):
        print('请参考utils/accounts_example.json创建accounts.json！')
        exit()
    with open('accounts.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def save_accounts(accounts):
    with open('accounts.json', 'w', encoding='utf-8') as f:
        json.dump(accounts, f, ensure_ascii=False, indent=2)

def choose_account(accounts):
    if len(accounts) == 1:
        return 0

    print('[选择账号]')
    for i, acc in enumerate(accounts):
        print(f'{i + 1}. {acc.get("name")}')

    while True:
        idx = input('> ')
        if idx.isdigit() and 0 < int(idx) <= len(accounts):
            return int(idx) - 1

def choose_action():
    actions = [
        '刷日常（神秘商店）',
        '刷星源商店',
        '刷NPC（不进场）',
        '刷活动讨伐',
        '刷佣兵团周任务（2800）',
        '刷亲密度',
        '查询团战数据',
        '查询团战总结',
        '查询团战防守',
        '退出'
    ]

    print('[选择功能]')
    for i, a in enumerate(actions):
        print(f'{(i + 1) % 10}. {a}')
    
    while True:
        c = input('> ')
        if c.isdigit() and 0 <= int(c) < len(actions):
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
    return send(payload)['Info']['AvailableVersions'][-1]

def run_refresh_token(accounts, acc_idx):
    device_id = accounts[acc_idx]['DeviceID']
    refresh_token = accounts[acc_idx]['refreshToken']
    local_headers = headers.copy()
    local_headers['Authorization'] = f'Bearer {refresh_token}'
    local_headers['DeviceId'] = device_id
    time.sleep(random.uniform(1, 2))
    resp = requests.post(url_token, headers=local_headers)
    resp.encoding = 'utf-8'
    data = resp.json()
    accounts[acc_idx]['refreshToken'] = data['data']['refreshToken']
    save_accounts(accounts)
    return data

def run_old_sdk(accounts, acc_idx, token):
    jwt = token.split('.')[1]
    jwt += '=' * (-len(jwt) % 4)
    token_data = json.loads(base64.urlsafe_b64decode(jwt))
    login_id = token_data['user_id']
    if 'exp' in token_data:
        return 1, login_id
    return 0, login_id

def run_login(accounts, acc_idx, version):
    # On Android it seems they are using an old SDK
    is_new_sdk, login_id = run_old_sdk(accounts, acc_idx, 
                                       accounts[acc_idx]['refreshToken'])
    if is_new_sdk:
        token_data = run_refresh_token(accounts, acc_idx)
        login_id = token_data['data']['userId']
        token = token_data['data']['accessToken']
    else:
        token = accounts[acc_idx]['refreshToken']
    payload = {
        'data': {
            'LoginID': login_id,
            'Token': token,
            'Version': version,
            'DeviceID': accounts[acc_idx]['DeviceID'],
            'LoginType': 'Erolabs',
            'IsNewSDK': is_new_sdk
        },
        'route': 'AccountHandler.Login'
    }
    return send(payload)

def run_secret(aid, session_id, secret_data):
    buy_list = [
        {'Count': 1, 'StaticID': 'EC11'}, # 芯片
        {'Count': 1, 'StaticID': 'EC21'},
        {'Count': 1, 'StaticID': 'EC31'},
        {'Count': 1, 'StaticID': 'EC41'},
        {'Count': 1, 'StaticID': 'EC51'},
        {'Count': 1, 'StaticID': 'EC61'},
        {'Count': 5, 'StaticID': '5'}, # 绿票
        {'Count': 50, 'StaticID': '6'}, # 黄票
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
    while True:
        for record in secret_data:
            payload_buy = {
                'data': {
                    'Record': {'DropResult': {}},
                    'Count': 1,
                    'AID': aid,
                    'SessionID': session_id
                },
                'route': 'StoreHandler.BuyCommodity'
            }
            item = record['DropResult']['Items'][0]
            drop = payload_buy['data']['Record']['DropResult']
            if 'Item' in item and item['Item'] in buy_list:
                drop['Items'] = [{'Item': item['Item']}]
                payload_buy['data']['Record']['StaticID'] = record['StaticID']
            elif 'Equipment' in item and item['Equipment']['ClassLV'] >= 4:
                found = match_equip(item['Equipment'], is_gold=True)
                if not found: continue
                drop['Items'] = [{'Equipment': item['Equipment']}]
                payload_buy['data']['Record']['StaticID'] = record['StaticID']
            else:
                continue
            try:
                send(payload_buy)
                print(f'{item} 成功！')
            except Exception:
                print(f'{item} 失败！')
        try:
            secret_data = send(payload_refresh)
            secret_data = secret_data['Records']
            print('刷新成功！')
        except Exception:
            print('刷新次数已满！')
            return

def run_daily(aid, session_id, secret_data):
    payloads = [
        {'route': 'ArkReactorHandler.RewardArkReactor'}, # Force lab
        {'route': 'ArkStarForceLabHandler.ChargeTesseract'},
        {'route': 'ArkStarForceLabHandler.RewardPotion'},
        {'route': 'ArkStarForceLabHandler.RewardStarForce'},
        {'route': 'ArkStarForceLabHandler.RewardTesseract'},
        {'route': 'GuildHandler.GuildMemberCheckIn'}, # Guild daily
        {'route': 'GuildHandler.DonateCourage',
         'data': {'ItemID': '28', 'Count': 3}},
        {'route': 'GuildHandler.DonateGold',
         'data': {'ItemID': '1', 'Count': 10}},
        {'route': 'GuildHandler.GuildMemberDayCheckReward'},
        #{'route': 'MailHandler.QueryNewestMails'}, # 月卡
        #{'route': 'TimingMealHandler.SentMeal'},
        #{'route': 'MailHandler.QueryNewestMails'},
        {'route': 'MonthSignInHandler.SignIn'}, # Monthly sign-in
        {'route': 'WeekSignInHandler.SignIn', # Weekly sign-in
         'data': {'ActivityID': f'ActivitySignIn{PICKUP}'}},
        {'route': 'SceneHandler.PurityScene', # Abyss
         'data': {'StaticID': 'Abyss_80'}}, 
        {'route': 'StoreHandler.BuyCommodity', # 'Store': 'FriendShip'
         'data': {'Record': {'StaticID': 'FriendShip3'}, 'Count': 1}},
        {'route': 'StoreHandler.BuyCommodity',
         'data': {'Record': {'StaticID': 'FriendShip4'}, 'Count': 1}},
        {'route': 'StoreHandler.BuyCommodity',
         'data': {'Record': {'StaticID': 'FriendShip6'}, 'Count': 1}},
        {'route': 'StoreHandler.BuyCommodity',
         'data': {'Record': {'StaticID': 'FriendShip7'}, 'Count': 1}},
        {'route': 'StoreHandler.BuyCommodity', # 'Store': 'VIPGift'
         'data': {'Record': {'StaticID': 'VIPGIFT_VIPQuick1'}, 'Count': 1}},
        {'route': 'StoreHandler.BuyCommodity',
         'data': {'Record': {'StaticID': 'VIPGIFT_VIPQuick2'}, 'Count': 1}},
        {'route': 'StoreHandler.BuyCommodity',
         'data': {'Record': {'StaticID': 'VIPGIFT_VIPQuick3'}, 'Count': 1}},
        {'route': 'StoreHandler.BuyCommodity', # 'Store': 'MedalHonor'
         'data': {'Record': {'StaticID': 'MedalHonor2'}, 'Count': 3}},
        #{'route': 'SupportFriendHandler.QuerySupFriendContainer'},
        {'route': 'SupportFriendHandler.GetReward'},
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
    # 刷神秘商店
    print('正在刷神秘商店...')
    run_secret(aid, session_id, secret_data)

def run_rainbow(aid, session_id):
    payload = {
        'data': {
            'CommodityID': 'RainbowStarSourceBox10',
            'AID': aid,
            'SessionID': session_id
        },
        'route': 'CustomEquipHandler.Query'
    }
    while True:
        try:
            data = send(payload)
            payload['route'] = 'CustomEquipHandler.RefreshEquip'
            equips = data['Data']['CustomEquipDropList']
            equips = [e['Equipment'] for e in equips]
            found = [match_equip(e, is_gold=False) for e in equips]
            found = [e for e in found if e]
            if found:
                choice = input('找到极品装备，是否继续刷新？（y/N）').strip()
                if choice.upper() != 'Y': return
            else:
                print('刷新成功！')
        except Exception:
            print('刷新次数已满！')
            return

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
            print(f'NPC {npc} 挑战结果：{data["IsWin"]}')
    except Exception:
        print('没有旗帜了，等会儿再试吧！')

def run_battle(aid, session_id, pos_map):
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
    
    c = input('选择: ').strip()
    if not c.isdigit() or not (1 <= (c := int(c)) <= 12):
        print('无效选择！')
        return
    repeat_str = input('次数（默认刷10次）：').strip()
    repeat = int(repeat_str) if repeat_str.isdigit() else 10
    if c >= 11: # Handle support
        sup = input('助战UID（默认不借人）: ').strip()
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
        sid = f'B{PICKUP}_1_13'
        runs = [{'static_id': sid, 'pos_map': pos_map}] * repeat
    else: # c == 12
        npc_map = {'0': {'StaticID': f'AcStory{PICKUP}', 'LV': 60}}
        runs = [
            {'static_id': f'B{PICKUP}_1_{i + 1}',
             'pos_map': npc_map if i == 0 else pos_map}
            for i in range(12)
        ] * repeat

    try:
        for run in runs:
            scene['StaticID'] = run['static_id']
            camp1['PositionRoleMap'] = run['pos_map']
            data = send(payload)
            energy = data['CostItems'][0]['NowItem']['Count']
            print(f'挑战成功，剩余体力：{energy}')
    except Exception:
        print('体力不足，装备已满，或者活动代码出错！')

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
    print(f'刷完{repeat}次了！')

def run_affection(aid, session_id, npc_list, pos_map):
    repeat = input('请输入刷亲密度次数（默认第一队刷10次）：').strip()
    repeat = int(repeat) if str(repeat).isdigit() else 10
    now = int(time.time() * 1000)
    targets = [npc for npc in npc_list if now > npc_list[npc]]
    if not targets:
        print('刷亲密度需要保留几个可以挑战的NPC！')
        return
    print(f'当前可挑战NPC：{targets}')
    for i in range(repeat):
        run_npc_battle(aid, session_id, targets[i % len(targets)], pos_map)
        print(f'正在刷亲密度...（{i + 1}/{repeat}）')

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
        print('没有开团战！')
        return
    print_report(data)
    export_report(data)

def run_guild_summary(aid, session_id, guild_data, gid=None, save_csv=True):
    if not gid:
        gid = input('请输入公会ID（默认查询本公会）：').strip()
    payload = {
        'data': {
            'GuildID': gid,
            'AID': aid,
            'SessionID': session_id
        },
        'route': 'GuildHandler.QueryPartialGuildDataForGuildWar'
    }
    try:
        if gid: guild_data = send(payload)
    except Exception:
        print('查询失败，请输入正确的公会ID！')
        return
    return analyze_guild(guild_data, aid, session_id, save_csv)

def run_guild_defence(aid, session_id, cuid):
    num_def = input('请输入要查询的前排团战防守（最多前20）：').strip()
    num_def = int(num_def) if str(num_def).isdigit() else 20
    payload = {
        'data': {
            'AID': aid,
            'SessionID': session_id
        },
        'route': 'GuildWarHandler.QueryNowGuildWarRank'
    }
    data = send(payload)
    guilds = data['GuildWarCampaignInfoList']
    def_rows = []
    for i in range(min(num_def, len(guilds))):
        print(f'正在查询第{i + 1}名公会的防守数据...')
        gid = guilds[i]['GuildSubInfo']['_id']['$oid']
        rows = run_guild_summary(aid, session_id, None, gid=gid, save_csv=False)
        analyze_defence(aid, session_id, cuid, rows)

def main():
    accounts = load_accounts()
    acc_idx = choose_account(accounts)
    print(f'当前账号：{accounts[acc_idx].get("name")}')

    version = run_bulletin()
    print('登录中...')
    data = run_login(accounts, acc_idx, version)

    # Preprocess data
    aid = data['Info']['_id']['$oid']
    session_id = data['SessionID']
    cuid = data['Info']['CUID']
    guild_data = {'GuildData': data['GuildData']}
    npc_list = {}
    for npc in data['PVPData']['NPCPVPInfoList']:
        npc_list[npc['NPCID']] = max(npc['NextTime']['$date'], 
                                   npc_list.get(npc['NPCID'], 0))
    first_team = data['Teams']['Settings'][0]
    pos_map = first_team['TeamSetting']['RolePosMap']
    pos_map = {str(pos): {'_id': role_id} for role_id, pos in pos_map.items()}
    secret_data = [item for item in data['StoreRecordContainer']['Records'] \
            if item['Store'] == 'SecretShop']

    while (action := choose_action()) != 0:
        actions = {
            # 刷日常（神秘商店）
            1: lambda: run_daily(aid, session_id, secret_data),
            # 刷星源商店
            2: lambda: run_rainbow(aid, session_id),
            # 刷NPC（不进场）
            3: lambda: run_npc(aid, session_id, npc_list),
            # 刷活动讨伐
            4: lambda: run_battle(aid, session_id, pos_map),
            # 刷佣兵团周任务（2800）
            5: lambda: run_weekly(aid, session_id, repeat=140),
            # 刷亲密度
            6: lambda: run_affection(aid, session_id, npc_list, pos_map),
            # 查询团战数据
            7: lambda: run_guild_data(aid, session_id),
            # 查询团战总结
            8: lambda: run_guild_summary(aid, session_id, guild_data),
            # 查询团战防守
            9: lambda: run_guild_defence(aid, session_id, cuid),
        }
        actions.get(action, lambda: None)()

if __name__ == '__main__':
    main()
