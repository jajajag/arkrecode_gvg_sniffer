from datetime import datetime, time as dt_time, timedelta, timezone
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from toolkit import (  # noqa: E402
    choose_account,
    get_login_version,
    load_accounts,
    run_bulletin,
    run_login,
    send,
)

BEIJING = timezone(timedelta(hours=8), 'Asia/Shanghai')
RETRY_INTERVAL = 10 * 60


def choose_reward():
    rewards = {
        '1': ('钻石', '2'),
        '2': ('黄票', '6'),
    }

    print('[选择结算奖励]')
    for idx, (name, _) in rewards.items():
        print(f'{idx}. {name}')

    while True:
        choice = input('> ').strip()
        if choice in rewards:
            return rewards[choice]


def next_beijing_monday_at(hour, minute):
    now = datetime.now(BEIJING)
    days = (7 - now.weekday()) % 7
    target = datetime.combine(
        now.date() + timedelta(days=days),
        dt_time(hour, minute),
        tzinfo=BEIJING,
    )
    if target <= now:
        target += timedelta(days=7)
    return target


def wait_until(target):
    while True:
        now = datetime.now(BEIJING)
        remaining = (target - now).total_seconds()
        if remaining <= 0:
            return
        print(f'等待到北京时间 {target:%Y-%m-%d %H:%M:%S}...')
        time.sleep(min(remaining, RETRY_INTERVAL))


def login(accounts, acc_idx):
    bulletin = run_bulletin()
    version = get_login_version(bulletin)
    return run_login(accounts, acc_idx, version)


def claim_reward(accounts, acc_idx, item_static_id):
    data = login(accounts, acc_idx)
    aid = data['Info']['_id']['$oid']
    session_id = data['SessionID']
    base_data = {
        'AID': aid,
        'SessionID': session_id,
    }
    payload_query = {
        'data': base_data,
        'route': 'PVPHandler.QueryPVPData',
    }
    payload_reward = {
        'data': {
            'ItemStaticID': item_static_id,
            **base_data,
        },
        'route': 'PVPHandler.ChoosePVPWeekReward',
    }
    send(payload_query)
    send(payload_reward)


def main():
    accounts = load_accounts()
    acc_idx = choose_account(accounts)
    print(f'当前账号：{accounts[acc_idx].get("Name")}')
    reward_name, item_static_id = choose_reward()
    print(f'已选择：{reward_name}')

    start_at = next_beijing_monday_at(5, 5)
    stop_at = datetime.combine(start_at.date(), dt_time(8, 0), tzinfo=BEIJING)
    wait_until(start_at)

    while datetime.now(BEIJING) < stop_at:
        try:
            claim_reward(accounts, acc_idx, item_static_id)
            print(f'{reward_name}结算奖励领取成功！')
            return
        except Exception as exc:
            now = datetime.now(BEIJING)
            if now >= stop_at:
                break
            print(f'领取失败：{exc}')
            next_try = min(now + timedelta(seconds=RETRY_INTERVAL), stop_at)
            print(f'将在北京时间 {next_try:%Y-%m-%d %H:%M:%S} 重试...')
            time.sleep((next_try - now).total_seconds())

    print('已到北京时间周一 08:00，停止尝试。')


if __name__ == '__main__':
    main()
