import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from toolkit import (choose_account, get_login_version, load_accounts,
                     run_bulletin, run_login)
from utils.master import ensure_master_db
from utils.realm_runner import run_mysterious_realm


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
    print('登录成功！')
    return run_mysterious_realm(aid, session_id, data)


if __name__ == '__main__':
    raise SystemExit(main())
