from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.login_helper import (  # noqa: E402
    choose_account, load_accounts, login_account, send,
)


VOTE_ACTIVITY_ID = 'Vote02'
DEFAULT_VOTE_ROLE_ID = 'H053'
VOTE_LANGUAGE = 'CHS'


def response_error(data):
    if not isinstance(data, dict):
        return f'响应格式异常：{data!r}'
    if data.get('Success') is False:
        return data.get('Message') or data.get('Error') or repr(data)
    for key in ('Error', 'ErrorMessage', 'Exception'):
        if data.get(key):
            return str(data[key])
    for key in ('ErrorCode', 'Code'):
        if data.get(key) not in (None, 0, '0'):
            return f'{key}={data[key]}，响应={data!r}'
    return None


def vote_role(login_data, role_id=None):
    role_id = role_id or DEFAULT_VOTE_ROLE_ID
    data = send({
        'route': 'VoteHandler.VoteRole',
        'data': {
            'ActivityID': VOTE_ACTIVITY_ID,
            'RoleID': role_id,
            'Language': VOTE_LANGUAGE,
            'Value': 1,
            'AID': login_data['Info']['_id']['$oid'],
            'SessionID': login_data['SessionID'],
        },
    })
    error = response_error(data)
    if error:
        raise RuntimeError(error)
    print(f'投票成功：{role_id}')
    return data


def prompt_and_vote(login_data):
    role_id = input(
        f'投什么？请输入角色ID（默认 {DEFAULT_VOTE_ROLE_ID}）：'
    ).strip() or DEFAULT_VOTE_ROLE_ID
    try:
        vote_role(login_data, role_id)
    except Exception as exc:
        print(f'投票失败：{exc}')
        return 1
    return 0


def main():
    accounts = load_accounts()
    acc_idx = choose_account(accounts)
    print(f'当前账号：{accounts[acc_idx].get("Name")}')
    print('登录中...')
    login_data = login_account(accounts, acc_idx)
    print('登录成功！')
    return prompt_and_vote(login_data)


if __name__ == '__main__':
    raise SystemExit(main())
