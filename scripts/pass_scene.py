from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from toolkit import (  # noqa: E402
    choose_account,
    ensure_master_db,
    get_login_version,
    load_accounts,
    run_bulletin,
    run_login,
    send,
)
from utils.battle_runner import LoginTeamBuilder, MASTER_DB, run_auto_battles  # noqa: E402


def scene_is_passed(scene):
    return any(scene.get('Stars') or []) or scene.get('PassCount', 0) > 0


def load_main_scene_ids(db_path=MASTER_DB):
    con = sqlite3.connect(db_path)
    try:
        rows = con.execute(
            """
            SELECT ID, PreScene
            FROM Scene
            WHERE IsStoryMainLine = 'TRUE'
            ORDER BY rowid
            """
        ).fetchall()
    finally:
        con.close()

    if not rows:
        return []

    by_pre_scene = {}
    ids = []
    for scene_id, pre_scene in rows:
        ids.append(scene_id)
        by_pre_scene.setdefault(pre_scene or '', []).append(scene_id)

    chain = []
    scene_id = by_pre_scene.get('', [ids[0]])[0]
    seen = set()
    while scene_id and scene_id not in seen:
        chain.append(scene_id)
        seen.add(scene_id)
        next_ids = by_pre_scene.get(scene_id) or []
        scene_id = next_ids[0] if next_ids else None

    return chain if len(chain) == len(ids) else ids


def passed_scene_ids(login_data):
    scenes = login_data.get('SceneDataContainer', {}).get('Scenes', [])
    return {
        scene.get('StaticID')
        for scene in scenes
        if isinstance(scene, dict) and scene_is_passed(scene)
    }


def next_main_scene(login_data, main_scene_ids):
    passed = passed_scene_ids(login_data)
    for scene_id in main_scene_ids:
        if scene_id not in passed:
            return scene_id
    return None


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
    data = send(finish_scene_payload(aid, session_id, scene_id, first_team))
    if not isinstance(data, dict):
        raise RuntimeError(f'FinishScene 响应格式异常: {data!r}')
    if data.get('Error') or data.get('ErrorCode') or data.get('Code'):
        raise RuntimeError(f'FinishScene 返回错误: {data}')
    if data.get('SceneData') or data.get('GotStars') is not None:
        return data
    if data.get('CostItems') or data.get('Drop') or data.get('AccountSaveData'):
        return data
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


def login(accounts, acc_idx, bulletin):
    version = get_login_version(bulletin)
    return run_login(accounts, acc_idx, version)


def main():
    bulletin = run_bulletin()
    ensure_master_db(bulletin)

    accounts = load_accounts()
    acc_idx = choose_account(accounts)
    print(f'当前账号：{accounts[acc_idx].get("Name")}')
    print('登录中...')
    login_data = login(accounts, acc_idx, bulletin)
    print('登录成功！')

    main_scene_ids = load_main_scene_ids()
    if not main_scene_ids:
        print('master.db 中没有找到主线关卡。')
        return

    aid = login_data['Info']['_id']['$oid']
    session_id = login_data['SessionID']
    settings = login_data['Teams']['Settings']
    first_team = LoginTeamBuilder(login_data, MASTER_DB).build_camp(settings, 0)

    current = next_main_scene(login_data, main_scene_ids)
    if current is None:
        print('主线已全部通关。')
        return

    start_index = main_scene_ids.index(current)
    print(f'当前进度：准备从 {current} 开始推进。')

    for scene_id in main_scene_ids[start_index:]:
        print(f'尝试直发通关：{scene_id}')
        try:
            direct_finish_scene(aid, session_id, scene_id, first_team)
            print(f'{scene_id} 直发通关成功。')
            continue
        except Exception as exc:
            print(f'{scene_id} 直发失败：{exc}')

        print(f'开始实时战斗：{scene_id}')
        try:
            auto_battle_scene(aid, session_id, scene_id, first_team)
            print(f'{scene_id} 实时战斗胜利。')
        except Exception as exc:
            print(f'{scene_id} 实时战斗失败：{exc}')
            print('停止推进。')
            return

    print('主线已推进到 master.db 记录的最后一关。')


if __name__ == '__main__':
    main()
