from analyzer import analyze_hits
from printer import print_report
from exporter import export_report
import json
import os
import random
import requests
import time

requests.packages.urllib3.disable_warnings()

url = 'https://game-arkre-labs.ecchi.xxx/Router/RouterHandler.ashx'
headers = {
    'Content-Type': 'application/octet-stream',
    'User-Agent': 'UnityPlayer/2022.3.62f2 (UnityWebRequest/1.0, libcurl/8.10.1-DEV)'
}

def load_accounts():
    if not os.path.exists('accounts.json'):
        print('请抓取AccountHandler.Login信息并在accounts.json里配置！')
        exit()
    return json.load(open('accounts.json', 'r', encoding='utf-8'))

def choose_account(accounts):
    if len(accounts) == 1:
        return accounts[0]

    print('[选择账号]')
    for i, acc in enumerate(accounts):
        print(f'{i + 1}. {acc.get("name")}（{acc.get("cuid")}）')

    while True:
        idx = input('> ')
        if idx.isdigit() and 0 < int(idx) <= len(accounts):
            return accounts[int(idx) - 1]

def choose_action():
    actions = [
        '查团战数据',
        '查团战总结',
        '刷每周任务',
        '刷NPC',
        '查团战防守',
        '查团战总结（按公会ID）',
        '退出'
    ]

    print('[选择功能]')
    for i, a in enumerate(actions):
        print(f'{i + 1}. {a}')
    
    while True:
        c = input('> ')
        if c.isdigit() and 0 < int(c) <= len(actions):
            return int(c) - 1

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

def run_login(account):
    data = send(account)
    aid = data['Info']['_id']['$oid']
    session_id = data['SessionID']
    cuid = data['Info']['CUID']
    guild_data = {'GuildData': data['GuildData']}
    npc_list = {}
    for npc in data['PVPData']['NPCPVPInfoList']:
        npc_list[npc['NPCID']] = max(npc['NextTime']['$date'], 
                                   npc_list.get(npc['NPCID'], 0))
    return aid, session_id, cuid, guild_data, npc_list

def run_clan_data(aid, session_id):
    payload = {
        'data': {
            'AID': aid,
            'SessionID': session_id},
        'route': 'GuildWarHandler.QueryFullGuildWarData'
    }
    data = send(payload)
    print_report(data)
    export_report(data)

def run_clan_summary(aid, session_id, guild_data):
    analyze_hits(guild_data, aid, session_id)

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
        print(send(payload))
    print(f'刷完{repeat}次了！')

def run_npc_helper(aid, session_id, npc):
    payload = {
        'data':{
            'NPCSceneID': f'HellNPC_{npc}',
            #'IsRevenge': 0,
            'AID': aid,
            'SessionID': session_id
        },
        'route': 'PVPHandler.PVPCheckTicket'
    }
    # Spend ticket
    send(payload)
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
    return send(payload)

def run_npc(aid, session_id, npc_list):
    now = int(time.time() * 1000)
    targets = [npc for npc in npc_list if now > npc_list[npc]]
    print(f'当前可挑战NPC：{targets}')
    for npc in targets:
        try:
            data = run_npc_helper(aid, session_id, npc)
            npc_list[npc] = float('inf')
            print(f'NPC {npc} 挑战结果：{data["IsWin"]}')
        except Exception as e:
            print('没有旗帜了，等会儿再试吧！')

def run_clan_summary_by_id(aid, session_id, gid):
    payload = {
        'data': {
            'GuildID': gid,
            'AID': aid,
            'SessionID': session_id
        },
        'route': 'GuildHandler.QueryPartialGuildDataForGuildWar'
    }
    try:
        data = send(payload)
    except Exception as e:
        print('查询失败，请输入正确的公会ID！')
        return
    analyze_hits(data, aid, session_id)

def main():
    accounts = load_accounts()
    account = choose_account(accounts)
    print(f'当前账号：{account.get("name")}（{account.get("cuid")}）')

    version = run_bulletin()
    account = {'data': account['data'], 'route': account['route']}
    account['data']['Version'] = version
    print('登录中...')
    aid, session_id, cuid, guild_data, npc_list = run_login(account)

    while (action := choose_action()) != 6:
        if action == 0: # 输出团战数据
            run_clan_data(aid, session_id)
        elif action == 1: # 输出团战总结
            run_clan_summary(aid, session_id, guild_data)
        elif action == 2: # 刷佣兵团周任务2800
            run_weekly(aid, session_id, repeat=140)
        elif action == 3: # 刷NPC
            run_npc(aid, session_id, npc_list)
        elif action == 4: # 查团战防守
            pass
        elif action == 5: # 按公会ID查询团战总结
            gid = input('请输入公会ID（可以在main.py通过好友查询）：')
            run_clan_summary_by_id(aid, session_id, gid)

if __name__ == '__main__':
    main()
