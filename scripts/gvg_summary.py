import argparse
import csv
import math
import sqlite3
import time
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
from utils.helper import get_role

DEFAULT_RECENT_DAYS = 14
DEFAULT_LINEUP_LIMIT = 5
MIN_DEFENSE_MATCHES = 2
MILLIS_PER_DAY = 24 * 60 * 60 * 1000
ROOT = Path(__file__).resolve().parents[1]
INVALID_FILENAME_CHARS = '<>:"/\\|?*'


@dataclass(frozen=True)
class Round:
    battle_id: str
    round_idx: int
    win: int
    atk_guild: str
    atk_name: str
    atk_cuid: int
    atk: tuple[str, ...]
    defense: tuple[str, ...]


def pct(numerator, denominator):
    if denominator <= 0:
        return '-'
    return f'{numerator / denominator * 100:.1f}%'


def role_name(role_id):
    return get_role(role_id)


def sorted_team(ids):
    return tuple(sorted(ids))


def attack_wins(rows):
    return sum(1 for row in rows if row.win)


def log_rate_score(successes, total):
    if total <= 0:
        return 0.0
    return successes / total * math.log(total + 1)


def member_label(row):
    if row.atk_name:
        return row.atk_name
    return str(row.atk_cuid)


def group_rows(rows, key_func):
    grouped = defaultdict(list)
    for row in rows:
        grouped[key_func(row)].append(row)
    return grouped


def load_rounds(conn, since_ts):
    units = defaultdict(list)
    for row in conn.execute(
            '''
            SELECT u.*
            FROM gvg_units AS u
            JOIN gvg_rounds AS r
              ON r.battle_id = u.battle_id
             AND r.round_idx = u.round_idx
            WHERE r.start_ts >= ?
            ORDER BY u.battle_id, u.round_idx, u.side, u.pos
            ''',
            (since_ts,)):
        units[(row['battle_id'], int(row['round_idx']),
               row['side'])].append(row)

    rounds = []
    for row in conn.execute(
            '''
            SELECT *
            FROM gvg_rounds
            WHERE start_ts >= ?
            ORDER BY start_ts, battle_id, round_idx
            ''',
            (since_ts,)):
        key = (row['battle_id'], int(row['round_idx']))
        atk_units = units.get((*key, 'atk'), [])
        def_units = units.get((*key, 'def'), [])
        if len(atk_units) != 3 or len(def_units) != 3:
            continue
        rounds.append(
            Round(
                battle_id=row['battle_id'],
                round_idx=int(row['round_idx']),
                win=int(row['win'] or 0),
                atk_guild=row['atk_guild'] or '',
                atk_name=row['atk_name'] or '',
                atk_cuid=int(row['atk_cuid'] or 0),
                atk=sorted_team(unit['role_id'] for unit in atk_units),
                defense=sorted_team(unit['role_id'] for unit in def_units),
            )
        )
    return rounds


def guild_candidates(query, guilds):
    folded_query = query.casefold()
    exact = [guild for guild in guilds if guild.casefold() == folded_query]
    if exact:
        return sorted(exact)
    return sorted(guild for guild in guilds
                  if folded_query in guild.casefold())


def resolve_guild(query, guilds):
    matches = guild_candidates(query, guilds)
    if len(matches) == 1:
        return matches[0]
    print(f'「{query}」匹配到 {len(matches)} 个公会，无法唯一确定:',
          file=sys.stderr)
    for guild in matches[:30]:
        print(f'  {guild}', file=sys.stderr)
    if len(matches) > 30:
        print(f'  ... 还有 {len(matches) - 30} 个', file=sys.stderr)
    return None


def positive_int(value):
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError('必须是正整数') from exc
    if number <= 0:
        raise argparse.ArgumentTypeError('必须是正整数')
    return number


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description='导出指定公会最近团战进攻失败错题本。'
    )
    parser.add_argument('guild', nargs='+', help='公会名称，支持空格分隔')
    parser.add_argument(
        '-d', '--days',
        type=positive_int,
        default=DEFAULT_RECENT_DAYS,
        help=f'统计最近多少天，默认 {DEFAULT_RECENT_DAYS} 天',
    )
    parser.add_argument(
        '-n', '--lineups',
        type=positive_int,
        default=DEFAULT_LINEUP_LIMIT,
        help=f'输出防守阵容数量，默认 {DEFAULT_LINEUP_LIMIT}',
    )
    return parser.parse_args(argv)


def top_failed_defenses(guild_rows, limit):
    defense_groups = group_rows(guild_rows, lambda row: row.defense)
    candidates = []
    for defense, rows in defense_groups.items():
        if len(rows) < MIN_DEFENSE_MATCHES:
            continue
        fails = sum(1 for row in rows if not row.win)
        if fails:
            score = log_rate_score(fails, len(rows))
            candidates.append((score, fails / len(rows), fails, len(rows),
                               defense, rows))
    return sorted(
        candidates,
        key=lambda item: (item[0], item[1], item[2], item[3],
                          tuple(role_name(role) for role in item[4])),
        reverse=True,
    )[:limit]


def failed_attacks(rows):
    attack_groups = group_rows(rows, lambda row: row.atk)
    candidates = []
    for atk, group in attack_groups.items():
        fails = [row for row in group if not row.win]
        if fails:
            score = log_rate_score(len(fails), len(group))
            candidates.append((score, len(fails) / len(group), len(fails),
                               len(group), atk, group, fails))
    return sorted(
        candidates,
        key=lambda item: (item[0], item[1], item[2], item[3],
                          tuple(role_name(role) for role in item[4])),
        reverse=True,
    )[:5]


def potential_solutions(all_rows, defense):
    rows = [row for row in all_rows if row.defense == defense]
    attack_groups = group_rows(rows, lambda row: row.atk)
    candidates = []
    for atk, group in attack_groups.items():
        wins = attack_wins(group)
        if wins:
            candidates.append((log_rate_score(wins, len(group)),
                               wins / len(group), wins, len(group),
                               atk, group))
    return sorted(
        candidates,
        key=lambda item: (item[0], item[1], item[2], item[3],
                          tuple(role_name(role) for role in item[4])),
        reverse=True,
    )[:5]


def team_columns(team):
    return [role_name(role_id) for role_id in team]


def safe_filename_part(value):
    return ''.join(
        '_' if ch in INVALID_FILENAME_CHARS else ch
        for ch in value
    ).strip()


def write_summary(rounds, guild, output, lineup_limit):
    guild_rows = [row for row in rounds if row.atk_guild == guild]
    writer = csv.writer(output, lineterminator='\n')
    writer.writerow([
        '排序', '角色1', '角色2', '角色3',
        '总场次', '成功场次', '成功率', '失败团员',
    ])

    for idx, (_, _, _, _, defense, defense_rows) in enumerate(
            top_failed_defenses(guild_rows, lineup_limit),
            start=1):
        wins = attack_wins(defense_rows)
        writer.writerow([
            f'防守阵容{idx}',
            *team_columns(defense),
            len(defense_rows),
            wins,
            pct(wins, len(defense_rows)),
            '',
        ])

        for attack_idx, (_, _, _, _, atk, attack_rows, fails) in enumerate(
                failed_attacks(defense_rows),
                start=1):
            attack_wins_count = attack_wins(attack_rows)
            failed_members = sorted({member_label(row) for row in fails})
            writer.writerow([
                f'失败进攻' if attack_idx == 1 else '',
                *team_columns(atk),
                len(attack_rows),
                attack_wins_count,
                pct(attack_wins_count, len(attack_rows)),
                '，'.join(failed_members),
            ])

        for solution_idx, (_, _, _, _, atk, solution_rows) in enumerate(
                potential_solutions(rounds, defense),
                start=1):
            solution_wins = attack_wins(solution_rows)
            writer.writerow([
                f'潜在解法' if solution_idx == 1 else '',
                *team_columns(atk),
                len(solution_rows),
                solution_wins,
                pct(solution_wins, len(solution_rows)),
                '',
            ])


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    guild_query = ' '.join(args.guild).strip()

    try:
        conn = sqlite3.connect('data/data.db')
        conn.row_factory = sqlite3.Row
        since_ts = int(time.time() * 1000) - args.days * MILLIS_PER_DAY
        rounds = load_rounds(conn, since_ts)
    except Exception:
        print('找不到data/data.db，请先运行9！')
        return 1
    finally:
        if 'conn' in locals():
            conn.close()

    guilds = {row.atk_guild for row in rounds if row.atk_guild}
    guild = resolve_guild(guild_query, guilds)
    if guild is None:
        return 1

    guild_rows = [row for row in rounds if row.atk_guild == guild]
    if not any(not row.win for row in guild_rows):
        print(f'最近{args.days}天没有找到「{guild}」的进攻失败记录',
              file=sys.stderr)
        return 0

    filename = f'{time.strftime("%Y-%m-%d")} {safe_filename_part(guild)}错题本.csv'
    output_path = ROOT / 'data' / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open('w', newline='', encoding='utf-8-sig') as output:
        write_summary(rounds, guild, output, args.lineups)
    print(f'已输出: {output_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
