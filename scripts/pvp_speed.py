from __future__ import annotations

import itertools
import sqlite3
import sys
import unicodedata
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "data.db"
PARTS = ("Weapon", "Head", "Body", "Necklace", "Ring")
BASE_SPEED = 189
SET_NAME_CN = {
    "Attack": "攻击",
    "Counter": "反击",
    "Critical": "暴击",
    "Defense": "防御",
    "Destruction": "爆伤",
    "Health": "生命",
    "Hit": "命中",
    "Immunity": "免疫",
    "Injury": "伤口",
    "Lifesteal": "吸血",
    "Penetration": "贯穿",
    "Pinch": "夹攻",
    "Rage": "愤怒",
    "Resist": "抗性",
    "Revenge": "复仇",
    "Speed": "速度",
}


def display_width(value: object) -> int:
    text = str(value)
    return sum(2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1 for ch in text)


def pad(value: object, width: int) -> str:
    text = str(value)
    return text + " " * max(width - display_width(text), 0)


def print_table(headers: list[str], rows: list[list[object]]) -> None:
    widths = [
        max(display_width(row[idx]) for row in [headers, *rows])
        for idx in range(len(headers))
    ]
    print(" ".join(pad(value, widths[idx]) for idx, value in enumerate(headers)))
    print(" ".join("-" * width for width in widths))
    for row in rows:
        print(" ".join(pad(value, widths[idx]) for idx, value in enumerate(row)))


def speed_value(row: sqlite3.Row) -> float:
    for idx in range(1, 5):
        if row[f"sub{idx}_prop"] == "SpeedValue":
            return float(row[f"sub{idx}_value"] or 0)
    return 0.0


def load_player_equips(conn: sqlite3.Connection, name: str) -> dict[tuple[int, str], list[dict[str, Any]]]:
    rows = conn.execute(
        """
        SELECT *
        FROM pvp_equips
        WHERE player_name LIKE ?
          AND equip_type IN ('Weapon', 'Head', 'Body', 'Necklace', 'Ring')
        ORDER BY player_name, cuid, equip_type
        """,
        (f"%{name}%",),
    ).fetchall()

    players: dict[tuple[int, str], list[dict[str, Any]]] = {}
    for row in rows:
        equip = dict(row)
        equip["speed"] = speed_value(row)
        players.setdefault((int(row["cuid"]), row["player_name"]), []).append(equip)
    return players


def best_speed_set(equips: list[dict[str, Any]], used: set[str] | None = None) -> tuple[float, list[dict[str, Any]]] | None:
    used = used or set()
    by_part: dict[str, list[dict[str, Any]]] = {part: [] for part in PARTS}
    for equip in equips:
        if equip["equip_id"] in used:
            continue
        part = equip["equip_type"]
        if part in by_part:
            by_part[part].append(equip)

    if any(not by_part[part] for part in PARTS):
        return None

    best_total = -1.0
    best_combo: list[dict[str, Any]] = []
    for combo in itertools.product(*(by_part[part] for part in PARTS)):
        speed_set_count = sum(1 for equip in combo if equip["set_name"] == "Speed")
        if speed_set_count < 3:
            continue
        total = sum(float(equip["speed"]) for equip in combo)
        if total > best_total:
            best_total = total
            best_combo = list(combo)

    if best_total < 0:
        return None
    return BASE_SPEED + best_total, best_combo


def fmt_speed(value: float | None) -> str:
    if value is None:
        return "-"
    return str(round(value, 2)).rstrip("0").rstrip(".")


def fmt_combo(combo: list[dict[str, Any]]) -> str:
    pieces = []
    for equip in sorted(combo, key=lambda item: PARTS.index(item["equip_type"])):
        set_name = SET_NAME_CN.get(equip["set_name"], equip["set_name"])
        pieces.append(f'{set_name}{fmt_speed(equip["speed"])}')
    return " ".join(pieces)


def main() -> int:
    player_name = " ".join(sys.argv[1:]).strip()
    if not player_name:
        print("用法: python3 scripts/pvp_speed.py <玩家名称>")
        print('示例: python3 scripts/pvp_speed.py 杂鱼')
        return 1
    if not DB_PATH.exists():
        print(f"找不到数据库: {DB_PATH}")
        return 1

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        players = load_player_equips(conn, player_name)
    finally:
        conn.close()

    if not players:
        print(f"没有找到包含「{player_name}」的玩家装备")
        return 0

    rows = []
    for (cuid, name), equips in sorted(players.items(), key=lambda item: (item[0][1], item[0][0])):
        first = best_speed_set(equips)
        used = {equip["equip_id"] for equip in first[1]} if first else set()
        second = best_speed_set(equips, used)
        rows.append(
            [
                name,
                cuid,
                f"{fmt_speed(first[0] if first else None)}(一速)",
                fmt_combo(first[1]) if first else "-",
            ]
        )
        rows.append(
            [
                name,
                cuid,
                f"{fmt_speed(second[0] if second else None)}(二速)",
                fmt_combo(second[1]) if second else "-",
            ]
        )
    print_table(["玩家名", "cuid", "速度", "装备"], rows)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
