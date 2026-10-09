"""已停用的 NPC 刷亲密度逻辑，仅作归档保留。"""

import time

from toolkit import run_npc_battle
from utils.battle_runner import MASTER_DB, choose_login_team
from utils.helper import get_npc_camp


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
        npc = targets[i % len(targets)]
        run_npc_battle(aid, session_id, npc, battle_team, '',
                       get_npc_camp(f'HellNPC_{npc}', MASTER_DB))
        print(f'正在刷亲密度...（{i + 1}/{repeat}）')
    print('亲密度刷完了！')

