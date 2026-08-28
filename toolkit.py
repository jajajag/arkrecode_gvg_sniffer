import re
import time
from utils.analyzer import analyze_gvg
from utils.battle_runner import build_realm_scene_ids, duplicate_team_roles
from utils.battle_runner import choose_login_team, login_teams, next_realm_floor
from utils.battle_runner import choose_login_teams, MASTER_DB
from utils.battle_runner import run_auto_battles
from utils.equips import match_equip
from utils.helper import get_event, get_npc_camp, get_role
from utils.login_helper import choose_account, get_login_version, load_accounts
from utils.login_helper import run_bulletin, run_login, send
from utils.master import ensure_master_db
from utils.other_tools import run_other_tools
from utils.battle_support import choose_placeholder_support, choose_support

def choose_action():
    actions = [
        '刷日常',
        '刷NPC派遣',
        '刷活动讨伐',
        '刷神秘商店',
        '刷星源商店',
        '刷佣兵团周任务',
        '刷亲密度',
        '查询团战总结',
        '小众变态工具集',
        '重新登录'
    ]
    print('[选择功能]')
    for i, a in enumerate(actions):
        print(f'{(i + 1) % 10}. {a}')
    while True:
        c = input('> ').strip()
        if c.isdigit() and 0 <= int(c) < len(actions):
            return int(c)

# 1. 清日常
def run_guild_support(aid, session_id, sups):
    cuid = sups['CUID']
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
                or cuid in item.get('SupporterList', [])):
                continue
            payload['data']['GuildAidItemInfoID'] = item['_id']['$oid']
            send(payload)
            sups[item['ItemID']] -= 2
            print(f'支援成功：{item["ItemID"]}')
    except Exception:
        print('支援结束：已达上限！')
    support_items = {
        item_id: count for item_id, count in sups.items()
        if item_id != 'CUID'
    }
    payload_support = {
        'data': {
            'ItemID': min(support_items, key=support_items.get),
            'AID': aid,
            'SessionID': session_id
        },
        'route': 'GuildHandler.RequestGuildAid'
    }
    try:
        send(payload_support)
        print(f'请求成功：{payload_support["data"]["ItemID"]}')
    except Exception:
        print('请求失败：今日已请求过！')

def run_daily(aid, session_id, sups, event, bp_id, progress):
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
        # Abyss
        {'route': 'SceneHandler.PurityScene',
         'data': {'StaticID': progress.get('abyss_scene', 'Abyss_80')}},
        # Support and Weekly sign-in
        {'route': 'SupportFriendHandler.GetReward'},
        {'route': 'WeekSignInHandler.SignIn',
         'data': {'ActivityID': f'ActivitySignIn{event["pickup"]}'}},
        # Daily / Weekly / Monthly rewards
        {'route': 'BattlePassHandler.GetAllNowRankReward',
         'data': {'ActivityID': bp_id}},
        {'route': 'QuestHandler.RewardQuest',
         'data': {'RewardQuestInfos': [
             {'ID': f'DailyScore{i}', 'Index': 0}
             for i in [10, 20, 30, 50, 80, 100]]}},
        {'route': 'QuestHandler.RewardQuest',
         'data': {'RewardQuestInfos': [
             {'ID': f'WeekScore{i}', 'Index': 0}
             for i in [20, 40, 60, 80, 100, 120]]}},
        # Event / Mysterious Realm rewards
        {'route': 'QuestHandler.RewardQuest',
         'data': {'RewardQuestInfos':[
             {'ID': f'Branch{event["pickup"]}', 'Index': 0}] + [
             {'ID': f'Branch{event["pickup"]}_{i+1}', 'Index': 0}
             for i in range(6)]}},
        {'route': 'QuestHandler.RewardQuest',
         'data': {'RewardQuestInfos':[
             {'ID': f'Branch{event["pickup"]}_Achievement_{i+1}', 'Index': 0}
             for i in range(8)]}},
        {'route': 'QuestHandler.RewardQuest',
         'data': {'RewardQuestInfos':[
             {'ID': f'FantasyStar{i+1}', 'Index': 0} for i in range(10)]}}
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

# 2. 刷NPC
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
            print(f'派遣失败，可能是体力不足！')
            # The quest has not been completed
            continue

def claim_timing_meal(aid, session_id):
    try:
        send({
            'route': 'TimingMealHandler.SentMeal',
            'data': {
                'AID': aid,
                'SessionID': session_id,
            },
        })
        print('饭点体力领取成功！')
    except Exception:
        print('饭点体力领取失败或当前不可领取。')


def run_npc_ticket(aid, session_id, npc):
    payload = {
        'data':{
            'NPCSceneID': f'HellNPC_{npc}',
            'IsRevenge': 0,
            'AID': aid,
            'SessionID': session_id
        },
        'route': 'PVPHandler.PVPCheckTicket'
    }
    # Spend ticket
    return send(payload)

def npc_battle_end_data(camp, enemy_camp):
    enemy_roles = enemy_camp.get('PositionRoleMap') or {}
    return {
        'StartBattleInfo': {
            'SceneData': {
                'StaticID': 'PVP',
                'Stars': [0, 0, 0],
                'PassCount': 0,
            },
            'CampData1': camp,
            'CampData2': enemy_camp,
            'IsRestart': 0,
            'Round': 0,
            'GM_Wave': 0,
            'IsRepeatAuto': 0,
            'BattleCountDown': -1,
            'IsNPCPVP': 1,
        },
        'Camp2DeadList': [
            role['_id'] for _, role in sorted(enemy_roles.items())
        ],
        'Result': 'Win',
        'TurnRole': 0,
        'FinishWave': 0,
    }


def run_npc_battle(aid, session_id, npc, camp, enemy_log_id, enemy_camp):
    payload = {
        'data': {
            'NPCSceneID': f'HellNPC_{npc}',
            'IsRevenge': 0,
            'EnemyLogID': enemy_log_id,
            'EndData': npc_battle_end_data(camp, enemy_camp),
            'AID': aid,
            'SessionID': session_id
        },
        'route': 'PVPHandler.NPCPVPBattleEnd'
    }
    return send(payload)

def run_npc(aid, session_id, npc_list, first_team, d_quests):
    now = int(time.time() * 1000)
    targets = [npc for npc in npc_list if now > npc_list[npc]]
    print(f'当前可挑战NPC：{targets}')
    if targets:
        specified = input(
            '是否指定刷哪些NPC'
            '（用空格或逗号隔开，不指定则全刷）：'
        ).strip()
        if specified:
            target_map = {str(npc): npc for npc in targets}
            requested = [
                npc for npc in re.split(r'[\s,，]+', specified)
                if npc
            ]
            invalid = [npc for npc in requested if npc not in target_map]
            if invalid:
                print(
                    '以下NPC不存在或当前不可挑战，已取消本次NPC战斗：'
                    + '、'.join(invalid)
                )
                targets = []
            else:
                selected = []
                seen = set()
                for npc in requested:
                    if npc in seen:
                        continue
                    seen.add(npc)
                    selected.append(target_map[npc])
                targets = selected
    try:
        for npc in targets:
            ticket = run_npc_ticket(aid, session_id, npc)
            enemy_log_id = (ticket or {}).get('LogID')
            enemy_camp = get_npc_camp(f'HellNPC_{npc}', MASTER_DB)
            if not enemy_log_id or not enemy_camp:
                print(f'NPC {npc} 挑战失败：无法获取对手战斗数据！')
                continue
            data = run_npc_battle(
                aid,
                session_id,
                npc,
                first_team,
                enemy_log_id,
                enemy_camp,
            )
            npc_list[npc] = float('inf')
            print(f'NPC {npc} 挑战{"成功" if data["IsWin"] else "失败"}！')
    except Exception:
        print('挑战结束：没有旗帜！')
    run_dispatched_quests(aid, session_id, d_quests)
    claim_timing_meal(aid, session_id)

# 3. 刷活动讨伐
def scene_is_passed(scene):
    # If the scene has already been passed
    return any(scene.get('Stars') or []) or scene.get('PassCount', 0) > 0

def highest_passed_scene(data, pattern):
    best = (0, None)
    scenes = data.get('SceneDataContainer', {}).get('Scenes', [])
    for scene in scenes:
        static_id = scene.get('StaticID')
        if not isinstance(static_id, str) or not scene_is_passed(scene):
            continue
        match = re.fullmatch(pattern, static_id)
        if not match: continue
        idx = int(match.group(1))
        if idx > best[0]: best = (idx, static_id)
    return best

def set_activity_progress(progress, event, idx):
    if idx <= progress.get('activity_idx', 0): return
    scene_ids = event.get('scene_ids') or []
    progress['activity_idx'] = idx
    progress['activity_scene'] = scene_ids[idx - 1] if len(scene_ids) >= idx \
        else f'B{event["pickup"]}_1_{idx}'

def run_battle(aid, session_id, event, progress, teams):
    default_team = teams[0]['camp'] if teams else None
    if default_team is None:
        print('登录数据里没有可用的非空队伍。')
        return
    payload = {
        'data': {
            'BattleEndData': {
                'StartBattleInfo': {
                    'SceneData': {'StaticID': ''}, 
                    'CampData1': default_team
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
    elems = [('火', 'Fire'), ('水', 'Ice'), ('木', 'Earth'), 
             ('光', 'Light'), ('暗', 'Dark')]
    print(' '.join(f'{i + 1}. {name}讨伐' for i, (name, _) in enumerate(elems)))
    print(' '.join(f'{i + 6}. {name}元素' for i, (name, _) in enumerate(elems)))
    print('11. 活动EX 12. 一键活动 13. 自动精英 14. 自动深渊')
    
    c = input('请选择关卡编号：').strip()
    if not c.isdigit() or not (1 <= (c := int(c)) <= 14):
        print('无效选择！')
        return
    support = None
    if c in (11, 12):
        support = choose_placeholder_support()
    elif c == 13:
        support = choose_support(aid, session_id)
    if c == 13:
        battle_team = choose_login_team(teams, '请选择自动精英队伍：')
        if battle_team is None:
            return
        pickup = event['pickup']
        scene_id = f'B{pickup}_1_13'
        try:
            result = run_auto_battles(
                aid, session_id, [battle_team], [scene_id],
                payload_mode='scene', support=support)
        except Exception as exc:
            print(f'自动精英失败：{exc}')
            return
        if result == 0:
            set_activity_progress(progress, event, 13)
        return
    if c == 14:
        battle_teams = choose_login_teams(teams, 2, '请选择自动深渊队伍')
        if battle_teams is None:
            return
        duplicates = duplicate_team_roles(battle_teams)
        if duplicates:
            names = ', '.join(get_role(role_id) for role_id, _, _ in duplicates)
            print(f'自动深渊队伍存在重复角色：{names}')
            return
        try:
            run_auto_battles(
                aid, session_id, battle_teams,
                build_realm_scene_ids(progress['realm_first_floor']),
                complete_message='深渊已完成，无需继续挑战！')
        except Exception as exc:
            print(f'自动深渊失败：{exc}')
        return
    repeat_str = input('请输入挑战次数（默认10次）：').strip()
    repeat = int(repeat_str) if repeat_str.isdigit() else 10
    if support:
        start_battle_info['Support'] = support
    
    if c <= 10:
        idx = (c - 1) % 5
        elem = elems[idx][1]
        scene_map = progress['hunt_scenes'] if c <= 5 \
                else progress['elf_scenes']
        sid = scene_map.get(elem)
        if not sid:
            prefix = 'Hunt' if c <= 5 else 'Elf'
            # 没找到最高已通关关卡，就用第11关和第4关
            fallback = 11 if c <= 5 else 4
            sid = f'{prefix}{elem}_{fallback}'
        print(f'即将挑战：{sid}')
        runs = [{'static_id': sid, 'camp': default_team}] * repeat
    elif c == 11:
        sid = progress.get('activity_scene')
        if not sid: sid = event['scene_ids'][-2]
        print(f'即将挑战：{sid}')
        runs = [{'static_id': sid, 'camp': default_team}] * repeat
    else: # c == 12
        runs = [
            {'static_id': sid,
             'camp': {'PositionRoleMap': event['npc_maps'][i]}
             if i in event['npc_maps'] else default_team}
            for i, sid in enumerate(event['scene_ids'][:12])
        ] * repeat

    print('开始刷活动讨伐...')
    try:
        for run in runs:
            scene['StaticID'] = run['static_id']
            start_battle_info['CampData1'] = run['camp']
            data = send(payload)
            energy = data['CostItems'][0]['NowItem']['Count']
            print(f'挑战成功，剩余体力：{energy}')
            # Check for urgent missions
            for m in data.get('UrgentMissionContainer', {}).get('Missions', []):
                if urgent_sid := m['SceneID']:
                    scene['StaticID'] = urgent_sid
                    start_battle_info['CampData1'] = default_team
                    data = send(payload)
                    print(f'紧急任务完成：{urgent_sid}')
        if c == 12:
            set_activity_progress(progress, event, 12)
    except Exception:
        print('挑战失败：体力不足，装备已满，或活动代码错误！')

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
        try:
            for record in secrets:
                item = record['DropResult']['Items'][0]
                # Skip if neither in buy_list nor a desired equipment
                if not (('Item' in item and item['Item'] in buy_list) or
                        ('Equipment' in item and match_equip(item['Equipment']))):
                    continue
                payload_buy['data']['Record']['_id'] = record['_id']['$oid']
                payload_buy['data']['Record']['StaticID'] = record['StaticID']
                send(payload_buy)
                print(f'购买成功：{item.get("Item") or item.get("Equipment")}')
            secrets = send(payload_refresh)
            secrets = secrets['Records']
            print('商店刷新成功！')
        except Exception:
            print('商店刷新结束：金币不足或刷新次数已满！')
            return

# 5. 刷星源商店
def run_rainbow(aid, session_id, login_data):
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
            found = []
            for item_index, equip in enumerate(equips):
                if description := match_equip(equip['Equipment']):
                    found.append({
                        'description': description,
                        'item_index': item_index,
                        #'record_id': equip['Equipment']['_id']['$oid']
                    })
            if found:
                print(*(item['description'] for item in found), sep='\n')
                choice = input('找到极品装备！是否继续刷新？(y/N)：').strip()
                if choice.upper() == 'Y':
                    continue
                choice = input('是否直接购买装备？(y/N)：').strip()
                if choice.upper() != 'Y':
                    return
                selected = found[0]
                if len(found) > 1:
                    print('[选择购买装备]')
                    for menu_idx, item in enumerate(found, start=1):
                        print(f'{menu_idx}. {item["description"]}')
                    choice = input('请选择要购买的装备：').strip()
                    if (not choice.isdigit()
                            or not 1 <= int(choice) <= len(found)):
                        print('无效选择，已取消购买！')
                        return
                    selected = found[int(choice) - 1]
                payload_buy = {
                    'data': {
                        'Record': {
                            #'_id': selected['record_id'],
                            'StaticID': 'RainbowStarSourceBox10',
                        },
                        'Count': 1,
                        'ItemIndex': selected['item_index'],
                        'AID': aid,
                        'SessionID': session_id,
                    },
                    'route': 'StoreHandler.BuyCommodity',
                }
                send(payload_buy)
                print(f'购买成功：{selected["description"]}')
                return
            else:
                print('刷新成功！')
        except Exception:
            print('刷新次数已满，或星源不足购买失败！')
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
def run_affection(aid, session_id, npc_list, teams):
    now = int(time.time() * 1000)
    targets = [npc for npc in npc_list if now > npc_list[npc]]
    if not targets:
        print('刷亲密度失败：请先保留至少一个可挑战的NPC！')
        return
    print(f'当前可挑战NPC：{targets}')
    battle_team = choose_login_team(teams, '请选择刷亲密度队伍：')
    if battle_team is None:
        return
    repeat = input('请输入刷亲密度次数（默认10次）：').strip()
    repeat = int(repeat) if str(repeat).isdigit() else 10
    for i in range(repeat):
        run_npc_battle(aid, session_id, targets[i % len(targets)], battle_team)
        print(f'正在刷亲密度...（{i + 1}/{repeat}）')
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

# 提取活动和进度信息
def get_progress(data, event):
    pickup = event['pickup']
    activity_idx, activity_scene = highest_passed_scene(
        data, rf'B{re.escape(pickup)}_1_(\d+)')
    abyss_idx, abyss_scene = highest_passed_scene(data, r'Abyss_(\d+)')
    elems = ('Fire', 'Ice', 'Earth', 'Light', 'Dark')
    hunt_scenes = {
        elem: highest_passed_scene(data, rf'Hunt{elem}_(\d+)')[1]
        for elem in elems
    }
    elf_scenes = {
        elem: highest_passed_scene(data, rf'Elf{elem}_(\d+)')[1]
        for elem in elems
    }
    return {
        'activity_idx': activity_idx,
        'activity_scene': activity_scene,
        'abyss_idx': abyss_idx,
        'abyss_scene': abyss_scene,
        'hunt_scenes': hunt_scenes,
        'elf_scenes': elf_scenes,
    }

def extract_login_values(data):
    # 1, 2, 3, 4, 5, 6, 7, 8, 9
    aid = data['Info']['_id']['$oid']
    session_id = data['SessionID']
    # 1, 3
    event = get_event(data)
    progress = get_progress(data, event)
    teams = login_teams(data, MASTER_DB)
    first_team = teams[0]['camp'] if teams else None
    progress['realm_first_floor'] = next_realm_floor(data)
    npc_levels = ', '.join(str(i + 1) for i in sorted(event['npc_maps']))
    print(f'当前活动：{event["pickup"]}，NPC关卡：{npc_levels}')
    # 1
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
    sups['CUID'] = data['Info']['CUID']
    # 2, 7
    npc_list = {}
    for npc in data['PVPData']['NPCPVPInfoList']:
        npc_list[npc['NPCID']] = max(npc['NextTime']['$date'],
                                   npc_list.get(npc['NPCID'], 0))
    # 4
    secrets = [item for item in data['StoreRecordContainer']['Records'] \
            if item['Store'] == 'SecretShop']
    # 8
    guild_data = {'GuildData': data.get('GuildData', {})}
    return (aid, session_id, npc_list, event, progress, first_team, teams,
            d_quests, bp_id, sups, secrets, guild_data)

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
                (aid, session_id, npc_list, event, progress, first_team,
                 teams, d_quests, bp_id, sups, secrets, guild_data) = \
                    extract_login_values(data)
                print('登录成功！')
            except Exception:
                retry = input('登录失败，是否重新登录？（Y/n）').strip().lower()
                if retry == 'n':
                    break
                continue
        if (action := choose_action()) == 0: continue
        actions = {
            # 刷日常
            1: lambda: run_daily(aid, session_id, sups, event, bp_id, progress),
            # 刷NPC派遣
            2: lambda: run_npc(aid, session_id, npc_list, first_team, d_quests),
            # 刷活动讨伐
            3: lambda: run_battle(aid, session_id, event, progress, teams),
            # 刷神秘商店
            4: lambda: run_secret(aid, session_id, secrets),
            # 刷星源商店
            5: lambda: run_rainbow(aid, session_id, data),
            # 刷佣兵团周任务
            6: lambda: run_weekly(aid, session_id, repeat=140),
            # 刷亲密度
            7: lambda: run_affection(aid, session_id, npc_list, teams),
            # 查询团战总结
            8: lambda: run_guild_summary(aid, session_id, guild_data),
            # 小众变态工具集
            9: lambda: run_other_tools(data, accounts, acc_idx),
        }
        actions.get(action, lambda: None)()

if __name__ == '__main__':
    main()
