from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.login_helper import (  # noqa: E402
    choose_account, load_accounts, login_account, run_bulletin, send,
)
from utils.battle_runner import (  # noqa: E402
    MASTER_DB, choose_login_team, login_teams, run_auto_battles,
)
from utils.master import ensure_master_db  # noqa: E402
from utils.battle_support import choose_support  # noqa: E402


# 一键通关层数上限，后续版本开放新层数时只需修改这里。
ABYSS_MAX_FLOOR = 80
HUNT_MAX_FLOOR = 11

MODE_LABELS = {
    '1': '主线',
    '2': '主线困难',
    '3': '支线',
    '4': '虚拟幻境',
    '5': '元素',
    '6': '讨伐',
}
ELEMENTS = ('Fire', 'Ice', 'Earth', 'Light', 'Dark')


def is_story_scene_id(scene_id):
    parts = scene_id.split('_')
    return len(parts) == 3 and all(part.isdigit() for part in parts)


def scene_floor(scene_id):
    try:
        return int(scene_id.rsplit('_', 1)[1])
    except (IndexError, ValueError):
        return None


def scene_is_complete(scene, mode):
    stars = scene.get('Stars') or []
    if mode in ('4', '5', '6'):
        return any(stars)
    return len(stars) >= 3 and all(stars[:3])


def login_scene_map(login_data):
    scenes = login_data.get('SceneDataContainer', {}).get('Scenes', [])
    return {
        scene.get('StaticID'): scene
        for scene in scenes
        if isinstance(scene, dict) and scene.get('StaticID')
    }


def load_scene_lines(mode, db_path=MASTER_DB):
    con = sqlite3.connect(db_path)
    try:
        rows = con.execute(
            'SELECT ID, Chapter, IsStoryMainLine FROM Scene ORDER BY rowid'
        ).fetchall()
    finally:
        con.close()

    if mode == '1':
        return [('主线', [
            scene_id for scene_id, _, is_main in rows
            if is_main == 'TRUE'
        ])]
    if mode == '2':
        return [('主线困难', [scene_id for scene_id, _, _ in rows
                              if scene_id.startswith('1Ext_')])]
    if mode == '3':
        return [('支线', [
            scene_id for scene_id, _, is_main in rows
            if is_story_scene_id(scene_id) and is_main != 'TRUE'
        ])]
    if mode == '4':
        return [('虚拟幻境', [scene_id for scene_id, _, _ in rows
                              if scene_id.startswith('Abyss_')
                              and scene_floor(scene_id) is not None
                              and scene_floor(scene_id) <= ABYSS_MAX_FLOOR])]
    if mode == '5':
        return [
            (f'元素 {element}', [
                scene_id for scene_id, _, _ in rows
                if scene_id.startswith(f'Elf{element}_')
            ])
            for element in ELEMENTS
        ]
    if mode == '6':
        return [
            (f'讨伐 {element}', [
                scene_id for scene_id, _, _ in rows
                if scene_id.startswith(f'Hunt{element}_')
                and scene_floor(scene_id) is not None
                and scene_floor(scene_id) <= HUNT_MAX_FLOOR
            ])
            for element in ELEMENTS
        ]
    raise ValueError(f'未知模式: {mode}')


def unfinished_scene_ids(scene_ids, scene_map, mode):
    return [
        scene_id for scene_id in scene_ids
        if not scene_is_complete(scene_map.get(scene_id, {}), mode)
    ]


def finish_scene_payload(aid, session_id, scene_id, first_team, support=None):
    start_battle_info = {
        'SceneData': {
            'StaticID': scene_id,
            'Stars': [0, 0, 0],
            'PassCount': 0,
        },
        'CampData1': first_team,
    }
    if support:
        start_battle_info['Support'] = support
    return {
        'route': 'SceneHandler.FinishScene',
        'data': {
            'BattleEndData': {
                'StartBattleInfo': start_battle_info,
                'Result': 'Win',
            },
            'IsQuickBattle': 0,
            'AID': aid,
            'SessionID': session_id,
        },
    }


def direct_finish_scene(aid, session_id, scene_id, first_team, support=None):
    data = send(finish_scene_payload(
        aid, session_id, scene_id, first_team, support=support))
    if not isinstance(data, dict):
        raise RuntimeError(f'FinishScene 响应格式异常: {data!r}')
    if data.get('Error') or data.get('ErrorCode') or data.get('Code'):
        raise RuntimeError(f'FinishScene 返回错误: {data}')
    if data.get('SceneData') or data.get('GotStars') is not None:
        return
    if data.get('CostItems') or data.get('Drop') or data.get('AccountSaveData'):
        return
    raise RuntimeError(f'FinishScene 未返回通关结果字段: {data}')


def auto_battle_scene(aid, session_id, scene_id, first_team, support=None):
    result = run_auto_battles(
        aid,
        session_id,
        [first_team],
        [scene_id],
        payload_mode='scene',
        support=support,
    )
    if result != 0:
        raise RuntimeError(f'实时战斗失败，返回码: {result}')


def choose_mode():
    print('请选择要推进的玩法：')
    for key, label in MODE_LABELS.items():
        print(f'{key}. {label}')
    mode = input('请输入编号：').strip()
    if mode in MODE_LABELS:
        return mode
    print('无效选择！')
    return None


def run_line(label, scene_ids, aid, session_id, direct_team, battle_team,
             support=None):
    if not scene_ids:
        print(f'{label}：所有关卡均已满星。')
        return True

    print(f'{label}：从 {scene_ids[0]} 开始，共 {len(scene_ids)} 关未满星。')
    for scene_id in scene_ids:
        print(f'尝试直发通关：{scene_id}')
        try:
            direct_finish_scene(
                aid, session_id, scene_id, direct_team, support=support)
            print(f'{scene_id} 直发通关成功。')
            continue
        except Exception as exc:
            print(f'{scene_id} 直发失败：{exc}')

        print(f'开始实时战斗：{scene_id}')
        try:
            auto_battle_scene(
                aid, session_id, scene_id, battle_team, support=support)
            print(f'{scene_id} 实时战斗胜利。')
        except Exception as exc:
            print(f'{scene_id} 实时战斗失败：{exc}')
            print(f'{label} 停止推进。')
            return False
    print(f'{label} 已推进完毕。')
    return True


def main(login_data=None):
    if login_data is None:
        bulletin = run_bulletin()
        ensure_master_db(bulletin)
        accounts = load_accounts()
        acc_idx = choose_account(accounts)
        print(f'当前账号：{accounts[acc_idx].get("Name")}')
        print('登录中...')
        login_data = login_account(accounts, acc_idx, bulletin)
        print('登录成功！')

    mode = choose_mode()
    if mode is None:
        return
    lines = load_scene_lines(mode)
    scene_map = login_scene_map(login_data)
    if not any(scene_ids for _, scene_ids in lines):
        print(f'master.db 中没有找到{MODE_LABELS[mode]}关卡。')
        return
    pending_lines = [
        (label, unfinished_scene_ids(scene_ids, scene_map, mode))
        for label, scene_ids in lines
    ]
    if not any(scene_ids for _, scene_ids in pending_lines):
        for label, _ in pending_lines:
            print(f'{label}：所有关卡均已满星。')
        print(f'{MODE_LABELS[mode]}处理完成。')
        return

    aid = login_data['Info']['_id']['$oid']
    session_id = login_data['SessionID']
    teams = login_teams(login_data, MASTER_DB)
    if not teams:
        print('登录数据里没有可用的非空队伍。')
        return
    direct_team = teams[0]['camp']
    battle_team = choose_login_team(teams, '请选择实时战斗队伍：')
    if battle_team is None:
        return
    support = choose_support(aid, session_id) if mode in ('1', '2', '3') \
        else None

    continue_after_failure = mode in ('5', '6')
    for label, pending in pending_lines:
        succeeded = run_line(
            label, pending, aid, session_id, direct_team, battle_team,
            support=support)
        if not succeeded and not continue_after_failure:
            return

    print(f'{MODE_LABELS[mode]}处理完成。')


if __name__ == '__main__':
    main()
