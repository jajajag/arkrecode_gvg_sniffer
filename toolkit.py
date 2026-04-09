from utils.analyzer import analyze_guild, analyze_defence
from utils.printer import print_report
from utils.exporter import export_report
import base64
import json
import os
import random
import requests
import time

requests.packages.urllib3.disable_warnings()

url = 'https://game-arkre-labs.ecchi.xxx/Router/RouterHandler.ashx'
url_token = "https://sadpki-portal-v2.ebuajk.com/api/v2/token/access"
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
        '刷日常',
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
    local_headers['Authorization'] = f"Bearer {refresh_token}"
    local_headers['DeviceId'] = device_id
    time.sleep(random.uniform(1, 2))
    resp = requests.post(url_token, headers=local_headers)
    resp.encoding = 'utf-8'
    data = resp.json()
    accounts[acc_idx]['refreshToken'] = data['data']['refreshToken']
    save_accounts(accounts)
    return data

def run_old_sdk(accounts, acc_idx, token):
    jwt = token.split(".")[1]
    jwt += "=" * (-len(jwt) % 4)
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
    for npc in targets:
        try:
            run_npc_ticket(aid, session_id, npc)
            data = run_npc_battle(aid, session_id, npc)
            npc_list[npc] = float('inf')
            print(f'NPC {npc} 挑战结果：{data["IsWin"]}')
        except Exception as e:
            print('没有旗帜了，等会儿再试吧！')

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
    repeat = input('请输入刷亲密度次数（默认第一队刷10次）：')
    repeat = int(repeat) if str(repeat).strip().isdigit() else 10
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
    except Exception as e:
        print('没有开团战！')
        return
    print_report(data)
    export_report(data)

def run_guild_summary(aid, session_id, guild_data):
    gid = input('请输入公会ID（默认查询本公会）：')
    payload = {
        'data': {
            'GuildID': gid,
            'AID': aid,
            'SessionID': session_id
        },
        'route': 'GuildHandler.QueryPartialGuildDataForGuildWar'
    }
    try:
        if gid.strip(): guild_data = send(payload)
    except Exception as e:
        print('查询失败，请输入正确的公会ID！')
        return
    return analyze_guild(guild_data, aid, session_id)

def run_guild_defence(aid, session_id, cuid):
    num_def = input('请输入要查询的前排团战防守（最多前20）：')
    num_def = int(num_def) if str(num_def).strip().isdigit() else 20
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
        rows = run_guild_summary_by_id(aid, session_id, gid, save_csv=False)
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
    pos_map = {str(pos): {"_id": role_id} for role_id, pos in pos_map.items()}

    while (action := choose_action()) != 0:
        actions = {
            # 刷日常
            1: lambda: None,
            # 刷星源商店
            2: lambda: None,
            # 刷NPC（不进场）
            3: lambda: run_npc(aid, session_id, npc_list),
            # 刷活动讨伐
            4: lambda: None,
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
