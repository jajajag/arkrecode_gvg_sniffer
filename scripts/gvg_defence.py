from __future__ import annotations

import itertools
import sqlite3
import sys
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "data.db"
sys.path.append(str(ROOT))

from utils.helper import get_role  # noqa: E402


@dataclass(frozen=True)
class Round:
    battle_id: str
    round_idx: int
    win: int
    atk: tuple[str, ...]
    defense: tuple[str, ...]
    atk_dead: bool


def display_width(value: object) -> int:
    text = str(value)
    return sum(2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1 for ch in text)


def pad(value: object, width: int) -> str:
    text = str(value)
    return text + " " * max(width - display_width(text), 0)


def print_table(headers: list[str], rows: list[list[object]]) -> None:
    if not rows:
        return
    widths = [
        max(display_width(row[idx]) for row in [headers, *rows])
        for idx in range(len(headers))
    ]
    print("  ".join(pad(value, widths[idx]) for idx, value in enumerate(headers)))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(pad(value, widths[idx]) for idx, value in enumerate(row)))


def pct(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "-"
    return f"{numerator / denominator * 100:.1f}%"


def names(ids: Iterable[str]) -> str:
    return " / ".join(get_role(role_id) for role_id in ids)


def sorted_team(ids: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(ids))


def defense_success(rows: list[Round]) -> int:
    return sum(1 for row in rows if not row.win)


def attack_wins(rows: list[Round]) -> int:
    return sum(1 for row in rows if row.win)


def load_rounds(conn: sqlite3.Connection) -> list[Round]:
    units: dict[tuple[str, int, str], list[sqlite3.Row]] = defaultdict(list)
    for row in conn.execute("SELECT * FROM gvg_units ORDER BY battle_id, round_idx, side, pos"):
        units[(row["battle_id"], int(row["round_idx"]), row["side"])].append(row)

    rounds: list[Round] = []
    for row in conn.execute("SELECT * FROM gvg_rounds ORDER BY start_ts, battle_id, round_idx"):
        key = (row["battle_id"], int(row["round_idx"]))
        atk_units = units.get((*key, "atk"), [])
        def_units = units.get((*key, "def"), [])
        if len(atk_units) != 3 or len(def_units) != 3:
            continue
        rounds.append(
            Round(
                battle_id=row["battle_id"],
                round_idx=int(row["round_idx"]),
                win=int(row["win"] or 0),
                atk=sorted_team(unit["role_id"] for unit in atk_units),
                defense=sorted_team(unit["role_id"] for unit in def_units),
                atk_dead=any(bool(unit["dead"]) for unit in atk_units),
            )
        )
    return rounds


def role_candidates(query: str, known_role_ids: set[str]) -> list[tuple[str, str]]:
    folded_query = query.casefold()
    result = []
    for role_id in known_role_ids:
        name = get_role(role_id)
        if folded_query in name.casefold():
            result.append((role_id, name))
    return sorted(result, key=lambda item: (len(item[1]), item[1], item[0]))


def resolve_roles(queries: list[str], known_role_ids: set[str]) -> tuple[str, ...] | None:
    resolved = []
    for query in queries:
        matches = role_candidates(query, known_role_ids)
        if len(matches) != 1:
            print(f"「{query}」匹配到 {len(matches)} 个角色，无法唯一确定:")
            for role_id, name in matches[:30]:
                print(f"  {role_id}\t{name}")
            if len(matches) > 30:
                print(f"  ... 还有 {len(matches) - 30} 个")
            return None
        resolved.append(matches[0][0])
    if len(set(resolved)) != len(resolved):
        print("三个输入解析到了重复角色，请重新输入。")
        return None
    return sorted_team(resolved)


def group_rows(rows: list[Round], key_func) -> dict[tuple[str, ...], list[Round]]:
    grouped: dict[tuple[str, ...], list[Round]] = defaultdict(list)
    for row in rows:
        for key in key_func(row):
            grouped[key].append(row)
    return grouped


def top_group_line(
    grouped: dict[tuple[str, ...], list[Round]],
    *,
    rate_kind: str,
    exclude: set[str] | None = None,
) -> str:
    exclude = exclude or set()
    candidates = []
    for key, rows in grouped.items():
        if exclude.intersection(key):
            continue
        total = len(rows)
        wins = defense_success(rows) if rate_kind == "def" else attack_wins(rows)
        candidates.append((total, wins / total if total else 0, key, wins))
    if not candidates:
        return "-"
    total, _, key, wins = max(candidates, key=lambda item: (item[0], item[1], names(item[2])))
    label = "防守成功率" if rate_kind == "def" else "进攻胜率"
    return f"{names(key)} | 场次 {total} | {label} {pct(wins, total)}"


def print_meta(rounds: list[Round], target: tuple[str, ...]) -> None:
    exact_rows = [row for row in rounds if row.defense == target]

    print("=== 阵容概览 ===")
    print(f"防守阵容: {names(target)}")
    print(f"完全相同阵容场次: {len(exact_rows)} | 防守成功率 {pct(defense_success(exact_rows), len(exact_rows))}")

    print("\n=== 两人组合 ===")
    for pair in itertools.combinations(target, 2):
        pair_set = set(pair)
        rows = [row for row in rounds if pair_set.issubset(row.defense)]
        partner_groups = group_rows(
            rows,
            lambda row, pair_set=pair_set: [tuple(role for role in row.defense if role not in pair_set)],
        )
        counter_groups = group_rows(rows, lambda row: itertools.combinations(row.atk, 2))
        print(f"{names(pair)} | 场次 {len(rows)} | 防守成功率 {pct(defense_success(rows), len(rows))}")
        print(f"  最搭第三人: {top_group_line(partner_groups, rate_kind='def')}")
        print(f"  最常见两人counter: {top_group_line(counter_groups, rate_kind='atk')}")

    print("\n=== 单人 ===")
    for role_id in target:
        rows = [row for row in rounds if role_id in row.defense]
        partner_groups = group_rows(
            rows,
            lambda row, role_id=role_id: [tuple(role for role in row.defense if role != role_id)],
        )
        counter_single = group_rows(rows, lambda row: ((role,) for role in row.atk))
        print(f"{get_role(role_id)} | 场次 {len(rows)} | 防守成功率 {pct(defense_success(rows), len(rows))}")
        print(f"  最搭双人组: {top_group_line(partner_groups, rate_kind='def')}")
        print(f"  最常见单人counter: {top_group_line(counter_single, rate_kind='atk')}")

    print("\n=== 前十进攻解 ===")
    attack_groups: dict[tuple[str, ...], list[Round]] = defaultdict(list)
    for row in exact_rows:
        attack_groups[row.atk].append(row)
    ranked = sorted(
        attack_groups.items(),
        key=lambda item: (len(item[1]), attack_wins(item[1]) / len(item[1]), names(item[0])),
        reverse=True,
    )
    if not ranked:
        print("没有找到完全相同三人防守的记录。")
        return
    attack_rows = []
    for idx, (atk, group) in enumerate(ranked[:10], start=1):
        dead = sum(1 for row in group if row.atk_dead)
        attack_rows.append([idx, names(atk), len(group), pct(attack_wins(group), len(group)), pct(dead, len(group))])
    print_table(["排名", "进攻阵容", "场次", "进攻胜率", "掉人概率"], attack_rows)


def main() -> int:
    if not DB_PATH.exists():
        print(f"找不到数据库: {DB_PATH}")
        return 1

    queries = sys.argv[1:]
    if len(queries) != 3:
        print("用法: python3 scripts/gvg_defense_meta.py <角色1> <角色2> <角色3>")
        print('示例: python3 scripts/gvg_defense_meta.py 彼岸花 空 "时界巡者Aoi"')
        print('角色名里有空格时请加引号，例如: "Aoi Hinamori"')
        return 1

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rounds = load_rounds(conn)
    finally:
        conn.close()

    known_role_ids = {role_id for row in rounds for role_id in (*row.atk, *row.defense)}
    target = resolve_roles(queries, known_role_ids)
    if target is None:
        return 1
    print_meta(rounds, target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
