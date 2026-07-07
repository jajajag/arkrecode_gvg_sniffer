import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from toolkit import (choose_account, get_login_version, load_accounts,
                     run_bulletin, run_login)
from utils.master import ensure_master_db
from utils.battle_runner import (
    LoginTeamBuilder, MASTER_DB, build_realm_scene_ids, next_realm_floor,
    run_auto_battles)


def main():
    print('读取账号并登录...')
    bulletin = run_bulletin()
    ensure_master_db(bulletin)
    accounts = load_accounts()
    acc_idx = choose_account(accounts)
    print(f'当前账号：{accounts[acc_idx].get("Name")}')
    data = run_login(accounts, acc_idx, get_login_version(bulletin))
    aid = data['Info']['_id']['$oid']
    session_id = data['SessionID']
    builder = LoginTeamBuilder(data, MASTER_DB)
    settings = data['Teams']['Settings']
    first_team = builder.build_camp(settings, 0)
    second_team = builder.build_camp(settings, 1)
    first_floor = next_realm_floor(data)
    print('登录成功！')
    return run_auto_battles(
        aid, session_id, [first_team, second_team],
        build_realm_scene_ids(first_floor),
        complete_message='深渊已完成，无需继续挑战。')


if __name__ == '__main__':
    raise SystemExit(main())
