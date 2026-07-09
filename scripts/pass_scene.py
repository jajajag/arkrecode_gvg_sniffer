from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.login_helper import (  # noqa: E402
    choose_account, load_accounts, login_account, run_bulletin, send,
)
from utils.battle_runner import LoginTeamBuilder, MASTER_DB, run_auto_battles  # noqa: E402
from utils.master import ensure_master_db  # noqa: E402


# 一键通关层数上限，后续版本开放新层数时只需修改这里。
ABYSS_MAX_FLOOR = 80
HUNT_MAX_FLOOR = 11

MODE_LABELS = {
    '1': '主线',
    '2': '主线困难',
    '3': '虚拟幻境',
    '4': '元素',
    '5': '讨伐',
}
ELEMENTS = ('Fire', 'Ice', 'Earth', 'Light', 'Dark')


def scene_floor(scene_id):
    try:
        return int(scene_id.rsplit('_', 1)[1])
    except (IndexError, ValueError):
        return None


def scene_is_complete(scene, mode):
    stars = scene.get('Stars') or []
    if mode in ('3', '4', '5'):
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
        return [('虚拟幻境', [scene_id for scene_id, _, _ in rows
                              if scene_id.startswith('Abyss_')
                              and scene_floor(scene_id) is not None
                              and scene_floor(scene_id) <= ABYSS_MAX_FLOOR])]
    if mode == '4':
        return [
            (f'元素 {element}', [
                scene_id for scene_id, _, _ in rows
                if scene_id.startswith(f'Elf{element}_')
            ])
            for element in ELEMENTS
        ]
    if mode == '5':
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


def finish_scene_payload(aid, session_id, scene_id, first_team):
    return {
        'route': 'SceneHandler.FinishScene',
        'data': {
            'BattleEndData': {
                'StartBattleInfo': {
                    'SceneData': {
                        'StaticID': scene_id,
                        'Stars': [0, 0, 0],
                        'PassCount': 0,
                    },
                    'CampData1': first_team,
                },
                'Result': 'Win',
            },
            'IsQuickBattle': 0,
            'AID': aid,
            'SessionID': session_id,
        },
    }


def direct_finish_scene(aid, session_id, scene_id, first_team):
    data = send(finish_scene_payload(
        aid, session_id, scene_id, first_team))
    if not isinstance(data, dict):
        raise RuntimeError(f'FinishScene 响应格式异常: {data!r}')
    if data.get('Error') or data.get('ErrorCode') or data.get('Code'):
        raise RuntimeError(f'FinishScene 返回错误: {data}')
    if data.get('SceneData') or data.get('GotStars') is not None:
        return
    if data.get('CostItems') or data.get('Drop') or data.get('AccountSaveData'):
        return
    raise RuntimeError(f'FinishScene 未返回通关结果字段: {data}')


def auto_battle_scene(aid, session_id, scene_id, first_team):
    result = run_auto_battles(
        aid,
        session_id,
        [first_team],
        [scene_id],
        payload_mode='scene',
    )
    if result != 0:
        raise RuntimeError(f'实时战斗失败，返回码: {result}')


def choose_mode():
    print('请选择要推进的玩法：')
    for key, label in MODE_LABELS.items():
        print(f'{key}. {label}')
    while True:
        mode = input('请输入编号：').strip()
        if mode in MODE_LABELS:
            return mode
        print('请输入 1 到 5。')


def run_line(label, scene_ids, aid, session_id, first_team):
    if not scene_ids:
        print(f'{label}：所有关卡均已满星。')
        return True

    print(f'{label}：从 {scene_ids[0]} 开始，共 {len(scene_ids)} 关未满星。')
    for scene_id in scene_ids:
        print(f'尝试直发通关：{scene_id}')
        try:
            direct_finish_scene(
                aid, session_id, scene_id, first_team)
            print(f'{scene_id} 直发通关成功。')
            continue
        except Exception as exc:
            print(f'{scene_id} 直发失败：{exc}')

        print(f'开始实时战斗：{scene_id}')
        try:
            auto_battle_scene(
                aid, session_id, scene_id, first_team)
            print(f'{scene_id} 实时战斗胜利。')
        except Exception as exc:
            print(f'{scene_id} 实时战斗失败：{exc}')
            print(f'{label} 停止推进。')
            return False
    print(f'{label} 已推进完毕。')
    return True


def main(login_data=None):
    bulletin = run_bulletin()
    ensure_master_db(bulletin)

    if login_data is None:
        accounts = load_accounts()
        acc_idx = choose_account(accounts)
        print(f'当前账号：{accounts[acc_idx].get("Name")}')
        print('登录中...')
        login_data = login_account(accounts, acc_idx, bulletin)
        print('登录成功！')

    mode = choose_mode()
    lines = load_scene_lines(mode)
    scene_map = login_scene_map(login_data)
    if not any(scene_ids for _, scene_ids in lines):
        print(f'master.db 中没有找到{MODE_LABELS[mode]}关卡。')
        return

    aid = login_data['Info']['_id']['$oid']
    session_id = login_data['SessionID']
    settings = login_data['Teams']['Settings']
    first_team = LoginTeamBuilder(
        login_data, MASTER_DB).build_camp(settings, 0)

    continue_after_failure = mode in ('4', '5')
    for label, all_scene_ids in lines:
        pending = unfinished_scene_ids(all_scene_ids, scene_map, mode)
        succeeded = run_line(
            label, pending, aid, session_id, first_team)
        if not succeeded and not continue_after_failure:
            return

    print(f'{MODE_LABELS[mode]}处理完成。')


if __name__ == '__main__':
    main()
