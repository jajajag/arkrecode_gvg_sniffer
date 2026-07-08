import asyncio
import copy
import json
import re
import sqlite3
from pathlib import Path

import requests
import urllib3
import websockets


ROOT = Path(__file__).resolve().parents[1]

ROUTER_URL = 'https://game-arkre-labs.ecchi.xxx/Router/RouterHandler.ashx'
MASTER_DB = ROOT / 'data/master.db'
HTTP_TIMEOUT = 20
WS_TIMEOUT = 60
BATTLE_TIMEOUT = 600
MAX_ACTIONS = 300
TEAM_COUNT = 2
FIRST_FLOOR = 1
LAST_FLOOR = 10
HEADERS = {
    'Content-Type': 'application/octet-stream',
    'User-Agent': (
        'UnityPlayer/2022.3.62f2 '
        '(UnityWebRequest/1.0, libcurl/8.10.1-DEV)'
    ),
}

ROLE_NET_ID = re.compile(r'^[12]-\d+-\d+$')


def compact(obj):
    return json.dumps(obj, separators=(',', ':'), ensure_ascii=False)


def oid(value):
    if isinstance(value, dict):
        return value.get('$oid')
    return value


def oid_str(value):
    value = oid(value)
    return str(value) if value is not None else ''


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def get_nested(value, *keys):
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


class LoginTeamBuilder:
    def __init__(self, login_data, master_db):
        self.login_data = login_data
        self.equipment_parts = self.load_equipment_parts(master_db)
        self.roles = self.collect_roles()
        self.equips, self.artifacts = self.collect_gear()

    def load_equipment_parts(self, master_db):
        db_path = Path(master_db)
        if not db_path.exists():
            return {}
        con = sqlite3.connect(db_path)
        try:
            return {
                row[0]: row[1]
                for row in con.execute('SELECT ID, Part FROM Equipment')
            }
        finally:
            con.close()

    def role_score(self, role):
        score = 0
        for key in (
                'StaticID', 'LV', 'AwakenLV', 'Star', 'Skills',
                'EquipmentMap', 'ArtifactData'):
            if key in role:
                score += 1
        score += len(role)
        return score

    def collect_roles(self):
        roles = {}
        for node in walk(self.login_data):
            role_id = oid_str(node.get('_id'))
            static_id = node.get('StaticID')
            if not role_id or not isinstance(static_id, str):
                continue
            if not static_id.startswith('H'):
                continue
            if 'Skills' not in node and 'LV' not in node and 'AwakenLV' not in node:
                continue
            old = roles.get(role_id)
            if old is None or self.role_score(node) > self.role_score(old):
                roles[role_id] = copy.deepcopy(node)
        return roles

    def collect_gear(self):
        equips = {}
        artifacts = {}
        for node in walk(self.login_data):
            role_id = oid_str(node.get('EquipRole'))
            static_id = node.get('StaticID')
            if not role_id or not isinstance(static_id, str):
                continue
            if 'MainProp' in node or 'SubProps' in node or 'Set' in node:
                part = node.get('Part') or self.equipment_parts.get(static_id)
                if part:
                    equips.setdefault(role_id, {})[part] = copy.deepcopy(node)
            elif 'Enhance' in node:
                artifacts[role_id] = copy.deepcopy(node)
        return equips, artifacts

    def role_for_team(self, role_id):
        role = copy.deepcopy(self.roles.get(role_id) or {})
        if not role:
            raise RuntimeError(f'登录数据里找不到队伍角色: {role_id}')
        role['_id'] = role_id
        if role_id in self.equips:
            role.setdefault('EquipmentMap', {}).update(self.equips[role_id])
        if role_id in self.artifacts:
            role.setdefault('ArtifactData', self.artifacts[role_id])
        return role

    def _build_camp(self, setting):
        role_pos_map = get_nested(setting, 'TeamSetting', 'RolePosMap') or {}
        if not role_pos_map:
            raise RuntimeError('登录数据里队伍为空，无法构造自动战斗队伍')
        pos_map = {}
        for raw_role_id, raw_pos in role_pos_map.items():
            role_id = oid_str(raw_role_id)
            pos_map[str(raw_pos)] = self.role_for_team(role_id)
        return {'PositionRoleMap': pos_map}

    def build_camp(self, settings, index, required=True):
        try:
            return self._build_camp(settings[index])
        except (IndexError, RuntimeError):
            if required:
                raise
            return None

    def build(self, team_count=2):
        settings = get_nested(self.login_data, 'Teams', 'Settings') or []
        if len(settings) < team_count:
            raise RuntimeError(f'登录数据里队伍数量少于 {team_count}')
        return build_battle_template([
            self.build_camp(settings, index)
            for index in range(team_count)
        ])


def build_battle_template(teams, payload_mode='wave'):
    info = {
        'SceneData': {
            'StaticID': 'MysteriousRealm_1',
            'Stars': [0, 0, 0],
            'PassCount': 0,
        },
        'CampData1': {},
        'CampData2': {},
        'IsRestart': 0,
        'Round': 0,
        'GM_Wave': 0,
        'IsRepeatAuto': 0,
        'BattleCountDown': -1,
        'IsNPCPVP': 0,
    }
    if payload_mode == 'scene':
        info['CampData1'] = teams[0]
    else:
        info['WaveCampDatas'] = teams
    return {
        'StartBattleInfo': {
            **info,
        },
        'Index': '0',
        'OID': '0_S1',
    }


def validate_teams(start_payload, team_count=2, payload_mode='wave'):
    if payload_mode == 'scene':
        camps = [get_nested(start_payload, 'StartBattleInfo', 'CampData1')]
    else:
        camps = get_nested(
            start_payload, 'StartBattleInfo', 'WaveCampDatas') or []
    if len(camps) < team_count:
        raise RuntimeError(f'模板里队伍数量少于 {team_count}')

    seen_object_ids = {}
    seen_static_ids = {}
    for team_idx, camp in enumerate(camps[:team_count], start=1):
        pos_map = (camp or {}).get('PositionRoleMap') or {}
        if not pos_map:
            raise RuntimeError(f'第 {team_idx} 队为空')
        for pos, role in pos_map.items():
            object_id = oid(role.get('_id'))
            static_id = role.get('StaticID')
            label = f'第{team_idx}队位置{pos}'
            if object_id:
                if object_id in seen_object_ids:
                    raise RuntimeError(
                        f'重复角色实例: {object_id} '
                        f'({seen_object_ids[object_id]} / {label})'
                    )
                seen_object_ids[object_id] = label
            if static_id:
                if static_id in seen_static_ids:
                    raise RuntimeError(
                        f'重复角色 StaticID: {static_id} '
                        f'({seen_static_ids[static_id]} / {label})'
                    )
                seen_static_ids[static_id] = label


def scene_payload(template, scene_id, oid_value=None, index='0', team_count=2,
                  payload_mode='wave'):
    payload = copy.deepcopy(template)
    info = payload['StartBattleInfo']
    info.setdefault('SceneData', {})['StaticID'] = scene_id
    if payload_mode == 'scene':
        info.pop('WaveCampDatas', None)
    else:
        info['WaveCampDatas'] = (info.get('WaveCampDatas') or [])[:team_count]
    info['IsRestart'] = 0
    info['Round'] = 0
    info['GM_Wave'] = 0
    info.setdefault('BattleCountDown', -1)
    if oid_value is not None:
        payload['OID'] = oid_value
    payload['Index'] = str(index)
    return payload


class MasterData:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.skills = {}
        self.load()

    def load(self):
        if not self.db_path.exists():
            return
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        try:
            for row in con.execute(
                    'SELECT ID, CoolDown, TargetCamp, TargetType, NoSelf, '
                    'SkillType, IsInitCoolDown, SkillSoulCost, SoulSkillFunc '
                    'FROM Skill'):
                self.skills[row['ID']] = {
                    'cooldown': int(float(row['CoolDown'] or 0)),
                    'target_camp': row['TargetCamp'] or '',
                    'target_type': row['TargetType'] or '',
                    'no_self': row['NoSelf'] == 'TRUE',
                    'skill_type': row['SkillType'] or '',
                    'init_cooldown': row['IsInitCoolDown'] == '1',
                    'soul_cost': int(float(row['SkillSoulCost'] or 0)),
                    'soul_func': row['SoulSkillFunc'] or '',
                }
        finally:
            con.close()

    def target_camp(self, skill_id):
        return self.skills.get(skill_id, {}).get('target_camp', '')

    def target_type(self, skill_id):
        return self.skills.get(skill_id, {}).get('target_type', '')

    def no_self(self, skill_id):
        return self.skills.get(skill_id, {}).get('no_self', False)

    def is_passive(self, skill_id):
        return self.skills.get(skill_id, {}).get('skill_type') == 'Passive'

    def has_init_cooldown(self, skill_id):
        return self.skills.get(skill_id, {}).get('init_cooldown', False)

    def skill_soul_cost(self, skill_id):
        return self.skills.get(skill_id, {}).get('soul_cost', 0)

    def has_soul_skill(self, skill_id):
        return bool(self.skills.get(skill_id, {}).get('soul_func'))


class BattleDriver:
    def __init__(self, start_payload, master):
        self.start_payload = start_payload
        self.master = master
        self.server_cooldowns = {}
        self.camp_soul = [0, 0]
        self.dead = set()
        self.known_roles = set()
        self.role_by_net_id = self.build_role_map()
        self.skill_levels = self.build_skill_levels()
        self.initial_cooldowns = self.build_initial_cooldowns()
        self.acted_prompts = set()

    def build_role_map(self):
        result = {}
        info = get_nested(self.start_payload, 'StartBattleInfo') or {}
        camps = info.get('WaveCampDatas') or []
        if not camps:
            camps = [info.get('CampData1') or {}]
        for wave_idx, camp in enumerate(camps):
            for pos, role in (camp.get('PositionRoleMap') or {}).items():
                result[f'1-{wave_idx}-{pos}'] = role
        return result

    def build_skill_levels(self):
        result = {}
        for net_id, role in self.role_by_net_id.items():
            for skill in (role.get('Skills') or {}).get('Skills') or []:
                static_id = skill.get('StaticID')
                if static_id:
                    result[(net_id, static_id)] = int(skill.get('Level') or 1)
        return result

    def build_initial_cooldowns(self):
        result = {}
        for source_id in self.role_by_net_id:
            for skill_no in (2, 3):
                skill_id = self.role_skill_id(source_id, skill_no)
                if skill_id and self.master.has_init_cooldown(skill_id):
                    result[(source_id, skill_id)] = 1
        return result

    def observe(self, msg):
        round_result = msg.get('RoundResult') or {}
        camp_soul = round_result.get('CampSoulList')
        if isinstance(camp_soul, list) and len(camp_soul) >= 2:
            self.camp_soul = camp_soul[:2]
        for node in walk(msg):
            target_role_id = node.get('TargetRoleID')
            if isinstance(target_role_id, str) and ROLE_NET_ID.fullmatch(
                    target_role_id):
                self.known_roles.add(target_role_id)
                cooldown_map = node.get('NowSkillCooldownMap')
                if isinstance(cooldown_map, dict):
                    self.server_cooldowns[target_role_id] = {
                        skill_id: int(float(value or 0))
                        for skill_id, value in cooldown_map.items()
                    }
                if node.get('NowIsDieOut') == 1 or node.get('NowHP') == 0:
                    self.dead.add(target_role_id)
            for key, value in node.items():
                if isinstance(key, str) and ROLE_NET_ID.fullmatch(key):
                    self.known_roles.add(key)
                if isinstance(value, str) and ROLE_NET_ID.fullmatch(value):
                    self.known_roles.add(value)
                elif key in ('DeadList', 'Camp1DeadList', 'Camp2DeadList'):
                    if isinstance(value, list):
                        self.dead.update(
                            item for item in value
                            if isinstance(item, str)
                            and ROLE_NET_ID.fullmatch(item)
                        )

    def is_finished(self, msg):
        for node in walk(msg):
            result = node.get('Result')
            if result in ('Win', 'Lose', 'Draw'):
                return result
            if node.get('BattleResult') in ('Win', 'Lose', 'Draw'):
                return node.get('BattleResult')
        return None

    def now_role(self, msg):
        for node in walk(msg):
            role_id = node.get('NowRoundRoleID') or node.get('NowRoleID')
            if isinstance(role_id, str) and ROLE_NET_ID.fullmatch(role_id):
                return role_id
        return None

    def is_action_prompt(self, msg):
        step = msg.get('Step')
        return step in ('NowRoleBeforeRound', 'NowRoleRound') and (
            self.now_role(msg) is not None)

    def prompt_key(self, msg):
        round_result = msg.get('RoundResult') or {}
        return (
            round_result.get('NowTurn'),
            round_result.get('NowWaveTurn'),
            round_result.get('NowWaveIndex'),
            round_result.get('NowRoundRoleID'),
        )

    def mark_prompt(self, msg):
        key = self.prompt_key(msg)
        if key in self.acted_prompts:
            return False
        self.acted_prompts.add(key)
        return True

    def skill_cooldown(self, source_id, skill_id):
        if source_id in self.server_cooldowns:
            return self.server_cooldowns[source_id].get(skill_id, 0)
        return self.initial_cooldowns.get((source_id, skill_id), 0)

    def role_skill_id(self, source_id, skill_no):
        role = self.role_by_net_id.get(source_id) or {}
        static_id = role.get('StaticID')
        if not static_id:
            return None
        skill_id = f'{static_id}S{skill_no}'
        if (source_id, skill_id) in self.skill_levels:
            return skill_id
        return None

    def choose_target(self, source_id, skill_id):
        target_camp = self.master.target_camp(skill_id)
        target_type = self.master.target_type(skill_id)
        no_self = self.master.no_self(skill_id)
        source_parts = source_id.split('-')
        wave_id = source_parts[1] if len(source_parts) > 1 else '0'
        if target_type == 'Self':
            if no_self:
                return None
            return source_id
        if 'Own' in target_camp or 'My' in target_camp:
            if not no_self:
                return source_id
            allies = sorted((
                role_id for role_id in self.role_by_net_id
                if role_id.startswith(f'1-{wave_id}-')
                and role_id != source_id
                and role_id not in self.dead
            ), reverse=True)
            return allies[0] if allies else None

        enemies = sorted(
            role_id for role_id in self.known_roles
            if role_id.startswith(f'2-{wave_id}-') and role_id not in self.dead
        )
        if enemies:
            return enemies[0]
        return f'2-{wave_id}-0'

    def choose_skill_and_target(self, source_id):
        for skill_no in (3, 2, 1):
            skill_id = self.role_skill_id(source_id, skill_no)
            if not skill_id or self.master.is_passive(skill_id):
                continue
            if self.skill_cooldown(source_id, skill_id) > 0:
                continue
            target_id = self.choose_target(source_id, skill_id)
            if target_id:
                return skill_id, target_id
        return None, None

    def should_use_soul(self, skill_id):
        cost = self.master.skill_soul_cost(skill_id)
        if cost <= 0 or not self.master.has_soul_skill(skill_id):
            return 0
        if self.camp_soul[0] >= cost:
            return 1
        return 0

    def action(self, source_id, oid_value, index):
        if source_id not in self.role_by_net_id:
            return None
        skill_id, target_id = self.choose_skill_and_target(source_id)
        if not skill_id:
            return None
        level = self.skill_levels.get((source_id, skill_id), 1)
        return {
            'SourceID': source_id,
            'TargetID': target_id,
            'SkillData': {'Level': level, 'StaticID': skill_id},
            'IsUseSoul': self.should_use_soul(skill_id),
            'Priority': 1,
            'ActionType': 'Main',
            'ActionInfo': 'None',
            'Index': str(index),
            'OID': oid_value,
        }

    def role_label(self, net_id):
        role = self.role_by_net_id.get(net_id) or {}
        static_id = role.get('StaticID')
        return f'{net_id}({static_id})' if static_id else net_id


class BattleRunner:
    def __init__(self, aid, session_id, first_floor=FIRST_FLOOR,
                 last_floor=LAST_FLOOR):
        self.aid = aid
        self.session_id = session_id
        self.first_floor = first_floor
        self.last_floor = last_floor
        self.master = MasterData(MASTER_DB)
        self.session = requests.Session()
        self.session.verify = False
        self.scene_id = None
        urllib3.disable_warnings()

    def post_router(self, payload):
        resp = self.session.post(
            ROUTER_URL,
            json=payload,
            headers=HEADERS,
            timeout=HTTP_TIMEOUT,
        )
        resp.encoding = 'utf-8'
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        resp.raise_for_status()
        return body

    def create_room(self, scene_id):
        data = self.post_router({
            'data': {
                'SceneID': scene_id,
                'AID': self.aid,
                'SessionID': self.session_id,
            },
            'route': 'RoomHandler.CreateRoomByScene',
        })
        room_id = oid(data.get('_id'))
        if not room_id:
            raise RuntimeError(f'创建房间响应缺少 _id: {data}')
        return {
            'room_id': room_id,
            'server_id': data['ServerID'],
            'domain': data['Domain'],
        }

    async def send_json(self, ws, payload, label):
        await ws.send(compact(payload))

    async def recv_json(self, ws):
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=WS_TIMEOUT)
        except asyncio.TimeoutError as exc:
            raise RuntimeError(
                f'服务器连续 {WS_TIMEOUT} 秒没有返回战斗或结算消息，停止等待'
            ) from exc
        try:
            payload = json.loads(raw)
        except Exception:
            raise
        return payload

    async def recv_json_for(self, ws, timeout):
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
        try:
            payload = json.loads(raw)
        except Exception:
            raise
        return payload

    async def heartbeat(self, ws):
        while True:
            await asyncio.sleep(15)
            await self.send_json(ws, {'HB': 1}, 'HB')

    async def recv_until(self, ws, pred, label):
        while True:
            msg = await self.recv_json(ws)
            if pred(msg):
                return msg

    async def fight_room(self, room, start_payload):
        async with websockets.connect(
                room['domain'], ping_interval=None) as ws:
            hb_task = asyncio.create_task(self.heartbeat(ws))
            try:
                print('连接房间中...', flush=True)
                await self.send_json(
                    ws, {'ServerID': room['server_id']}, 'ServerID')
                await self.recv_until(ws, lambda m: 'NetID' in m, 'NetID')

                await self.send_json(
                    ws,
                    {'RoomDBInfo': room['room_id'], 'AID': self.aid},
                    'RoomDBInfo/AID',
                )
                await self.recv_until(
                    ws, lambda m: m.get('RoomReady') == 1, 'RoomReady')
                spawn = await self.recv_until(
                    ws, lambda m: 'Spawn' in m and 'OID' in m, 'Spawn/OID')
                print('房间已就绪，准备开战。', flush=True)

                oid_value = spawn['OID']
                index = spawn.get('Spawn', '0')
                start_payload['OID'] = oid_value
                start_payload['Index'] = str(index)

                # Some rooms send SetMaster/CType before StartBattleInfo, while
                # others expect StartBattleInfo immediately after Spawn.
                while True:
                    try:
                        msg = await self.recv_json_for(ws, 2)
                    except asyncio.TimeoutError:
                        break
                    if msg.get('CType') == 'FantasyBattleNetControl':
                        break
                    if msg.get('SetMaster') is True:
                        continue
                    break

                await self.send_json(ws, start_payload, 'StartBattleInfo')
                print('战斗开始。', flush=True)

                driver = BattleDriver(start_payload, self.master)
                actions = 0
                while actions < MAX_ACTIONS:
                    msg = await self.recv_json(ws)
                    driver.observe(msg)
                    result = driver.is_finished(msg)
                    if result:
                        print(f'战斗结束：{result}', flush=True)
                        return result
                    if not driver.is_action_prompt(msg):
                        continue
                    source_id = driver.now_role(msg)
                    if not source_id or not source_id.startswith('1-'):
                        continue
                    if not driver.mark_prompt(msg):
                        continue
                    action = driver.action(source_id, oid_value, index)
                    if action is None:
                        continue
                    await self.send_json(ws, action, f'Action {source_id}')
                    actions += 1
                    skill = action['SkillData']['StaticID']
                    target_id = action['TargetID']
                    print(
                        f'行动 {actions}: '
                        f'{driver.role_label(source_id)} '
                        f'{skill} -> {target_id}',
                        flush=True,
                    )

                raise RuntimeError(
                    f'超过最大行动数 {MAX_ACTIONS}，停止测试')
            finally:
                hb_task.cancel()

    async def run_scenes(self, template, scene_ids, team_count=TEAM_COUNT,
                         payload_mode='wave',
                         complete_message='自动战斗已完成，无需继续挑战。'):
        validate_teams(template, team_count, payload_mode=payload_mode)
        if not scene_ids:
            print(complete_message, flush=True)
            return 0
        for scene_id in scene_ids:
            self.scene_id = scene_id
            print(f'开始 {scene_id}', flush=True)
            start_payload = scene_payload(
                template, scene_id, team_count=team_count,
                payload_mode=payload_mode)
            room = self.create_room(scene_id)
            print(
                f'房间 {room["room_id"]} | '
                f'ServerID {room["server_id"]} | {room["domain"]}',
                flush=True,
            )
            try:
                result = await asyncio.wait_for(
                    self.fight_room(room, start_payload),
                    timeout=BATTLE_TIMEOUT,
                )
            except asyncio.TimeoutError as exc:
                raise RuntimeError(
                    f'{scene_id} 战斗或结算超过 '
                    f'{BATTLE_TIMEOUT} 秒，停止等待'
                ) from exc
            print(f'{scene_id}: {result}', flush=True)
            if result != 'Win':
                print(f'{scene_id} 未胜利，停止后续关卡。', flush=True)
                return 1
        return 0

def next_realm_floor(login_data, last_floor=LAST_FLOOR):
    scenes = get_nested(login_data, 'SceneDataContainer', 'Scenes') or []
    passed = []
    for scene in scenes:
        static_id = scene.get('StaticID')
        if not isinstance(static_id, str):
            continue
        match = re.fullmatch(r'MysteriousRealm_(\d+)', static_id)
        if not match:
            continue
        stars = scene.get('Stars') or []
        if any(stars):
            passed.append(int(match.group(1)))
    floor = max(passed, default=0) + 1
    return floor


def build_realm_scene_ids(first_floor, last_floor=LAST_FLOOR):
    return [
        f'MysteriousRealm_{floor}'
        for floor in range(first_floor, last_floor + 1)
    ]


async def run_auto_battles_async(
        aid, session_id, teams, scene_ids,
        payload_mode='wave',
        complete_message='自动战斗已完成，无需继续挑战。'):
    runner = BattleRunner(aid, session_id)
    return await runner.run_scenes(
        build_battle_template(teams, payload_mode=payload_mode), scene_ids,
        team_count=len(teams), payload_mode=payload_mode,
        complete_message=complete_message)


def run_auto_battles(
        aid, session_id, teams, scene_ids,
        payload_mode='wave',
        complete_message='自动战斗已完成，无需继续挑战。'):
    return asyncio.run(run_auto_battles_async(
        aid, session_id, teams, scene_ids, payload_mode, complete_message))
