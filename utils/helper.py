from __future__ import annotations

import json
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Any


MASTER_JSON = Path("data/master.json")

BASE = ("HP", "Attack", "Defence", "Speed")
EXTRA = ("CriticalRate", "CriticalDamageRate", "EffectHitRate", "ResistanceRate", "PinchRate")
STATS = (*BASE, *EXTRA)

VALUE_PROP = {
    "HPValue": "HP",
    "AttackValue": "Attack",
    "DefenceValue": "Defence",
    "SpeedValue": "Speed",
}
RATE_PROP = {
    "HPRate": "HP",
    "AttackRate": "Attack",
    "DefenceRate": "Defence",
    "SpeedRate": "Speed",
    "CriticalRate": "CriticalRate",
    "CriticalDamageRate": "CriticalDamageRate",
    "EffectHitRate": "EffectHitRate",
    "ResistanceRate": "ResistanceRate",
    "PinchRate": "PinchRate",
}

PROP_SCORE = {
    "AttackRate": 180,
    "AttackValue": 0.17,
    "CriticalDamageRate": 180,
    "CriticalRate": 200,
    "DefenceRate": 180,
    "DefenceValue": 0.2,
    "EffectHitRate": 125,
    "HPValue": 0.05,
    "HPRate": 150,
    "ResistanceRate": 125,
    "SpeedValue": 3.5,
}

EQUIP_KEYS = {
    "Weapon": "UI_Equip_Weapon",
    "Head": "UI_Equip_Helmet",
    "Body": "UI_Equip_Armor",
    "Necklace": "UI_Equip_Necklace",
    "Ring": "UI_Equip_Ring",
    "Shoes": "UI_Equip_Boots",
}
PROP_KEYS = {
    "AttackRate": "UI_Equip_Attributes_AttackRate",
    "AttackValue": "UI_Equip_Attack",
    "CriticalDamageRate": "UI_PropertyCriticalDamage",
    "CriticalRate": "UI_Equip_Critical",
    "DefenceRate": "UI_Guild_Defense",
    "DefenceValue": "UI_Guild_Defense",
    "EffectHitRate": "UI_PropertyEffectHit",
    "HPValue": "UI_Equip_Health",
    "HPRate": "UI_Equip_Health",
    "ResistanceRate": "UI_PropertyResistance",
    "SpeedValue": "UI_PropertySpeed",
}


def num(value: Any, default: float = 0) -> float:
    try:
        return default if value in (None, "") else float(value)
    except (TypeError, ValueError):
        return default


def intv(value: Any, default: int = 0) -> int:
    try:
        return default if value in (None, "") else int(value)
    except (TypeError, ValueError):
        return default


@lru_cache(maxsize=1)
def master() -> dict[str, Any]:
    if not MASTER_JSON.exists():
        return {}
    with MASTER_JSON.open("r", encoding="utf-8") as fp:
        return json.load(fp)


@lru_cache(maxsize=8192)
def chs(key: str | None) -> str | None:
    if not key:
        return None
    if not key.startswith(("T_", "UI_")):
        return key
    return master().get("localization", {}).get(key)


def get_role(role_id: str) -> str:
    row = master().get("roles", {}).get(role_id, {})
    return chs(row.get("NAME")) or role_id


def get_bond(bond_id: str) -> str:
    row = master().get("items", {}).get(bond_id, {})
    return chs(row.get("Name")) or bond_id


def equip_name(part: str) -> str:
    return chs(EQUIP_KEYS.get(part)) or part


def equip_parts() -> tuple[str, ...]:
    return tuple(EQUIP_KEYS)


def prop_short(prop: str) -> str:
    if prop == "CriticalDamageRate":
        return "爆"
    if prop == "CriticalRate":
        return "暴"
    if prop == "EffectHitRate":
        return "命"
    if prop == "ResistanceRate":
        return "抗"
    if prop == "SpeedValue":
        return "速"

    name = (chs(PROP_KEYS.get(prop)) or prop).replace("(%)", "").replace("（%）", "").replace(" ", "")
    if "攻击" in name:
        return "攻"
    if "防御" in name:
        return "防"
    if "生命" in name:
        return "生"
    return name[:1] if name else prop


def get_prop_score(prop: str) -> float:
    return PROP_SCORE.get(prop, 0)


@lru_cache(maxsize=128)
def get_set(set_id: str) -> tuple[str, int]:
    row = master().get("equipment_sets", {}).get(set_id)
    if not row:
        return set_id, 1
    name = (chs(row.get("Name")) or set_id).removesuffix("套装")
    return name, max(intv(row.get("Count"), 1), 1)


def bucket() -> dict[str, float]:
    return {stat: 0.0 for stat in STATS}


def add_prop(flat: dict[str, float], rate: dict[str, float], prop: str | None, value: Any) -> None:
    if not prop:
        return
    if prop in VALUE_PROP:
        flat[VALUE_PROP[prop]] += num(value)
    elif prop in RATE_PROP:
        rate[RATE_PROP[prop]] += num(value)


def role_row(role_id: str) -> dict[str, Any] | None:
    return master().get("roles", {}).get(role_id)


def role_prop(prop_id: str, level: int) -> dict[str, Any] | None:
    rows = master().get("role_properties", {}).get(prop_id, [])
    exact = next((row for row in rows if row.get("LV") == str(level)), None)
    return exact or max(rows, key=lambda row: intv(row.get("LV")), default=None)


def base_stats(role: dict[str, Any]) -> tuple[dict[str, float], dict[str, Any] | None]:
    row = role_row(role.get("StaticID", ""))
    if not row:
        return bucket(), None

    prop = role_prop(row.get("RolePropertyID") or "HERO", intv(role.get("LV") or role.get("Level"), 60))
    return {stat: num(prop.get(stat) if prop else 0) * num(row.get(stat), 1) for stat in STATS}, row


def add_awaken(role_id: str, awaken_lv: int, flat: dict[str, float], rate: dict[str, float]) -> None:
    for row in master().get("role_awaken", {}).get(role_id, []):
        if intv(row.get("LV")) > awaken_lv:
            continue
        for prop, stat in VALUE_PROP.items():
            flat[stat] += num(row.get(prop))
        for prop, stat in RATE_PROP.items():
            rate[stat] += num(row.get(prop))


def add_equips(equips: dict[str, Any] | None, flat: dict[str, float], rate: dict[str, float]) -> None:
    for equip in (equips or {}).values():
        main = equip.get("MainProp") or {}
        add_prop(flat, rate, main.get("PropertyType"), main.get("Value", main.get("SValue")))
        for prop in (equip.get("SubProps") or {}).get("SourceValues") or []:
            add_prop(flat, rate, prop.get("PropertyType"), prop.get("Value", prop.get("SValue")))


def add_sets(equips: dict[str, Any] | None, rate: dict[str, float]) -> None:
    counts: dict[str, int] = {}
    for equip in (equips or {}).values():
        set_id = equip.get("Set")
        if set_id:
            counts[set_id] = counts.get(set_id, 0) + 1

    sets = master().get("equipment_sets", {})
    for set_id, owned in counts.items():
        row = sets.get(set_id)
        if not row:
            continue
        active = owned // max(intv(row.get("Count"), 1), 1)
        if active <= 0:
            continue
        for prop, stat in RATE_PROP.items():
            rate[stat] += num(row.get(prop)) * active


def bond_value(base: float, max_value: float, level: int, *, floor: bool = False) -> float:
    value = base if level <= 1 else base + (max_value - base) * min(max(level - 1, 0), 29) / 29
    return math.floor(value + 1e-6) if floor else round(value)


def add_bond(bond: dict[str, Any] | None, flat: dict[str, float]) -> None:
    if not bond:
        return
    row = master().get("artifacts", {}).get(bond.get("StaticID"))
    if not row:
        return
    level = intv(bond.get("LV"), 1)
    flat["Attack"] += bond_value(num(row.get("Base.AttackValue")), num(row.get("Max.AttackValue")), level, floor=True)
    flat["HP"] += bond_value(num(row.get("Base.HPValue")), num(row.get("Max.HPValue")), level, floor=True)


def add_passive(raw: str | None, flat: dict[str, float], rate: dict[str, float]) -> None:
    if not raw or "#" not in raw or raw.startswith("Fun#"):
        return
    prop, value = raw.split("#", 1)
    add_prop(flat, rate, prop, value)


def add_skills(role: dict[str, Any], flat: dict[str, float], rate: dict[str, float]) -> None:
    skills = master().get("skills", {})
    levels = master().get("skill_levels", {})
    for skill in (role.get("Skills") or {}).get("Skills") or []:
        skill_id = skill.get("StaticID")
        if not skill_id:
            continue
        for i in range(1, 4):
            add_passive((skills.get(skill_id) or {}).get(f"PassiveProp.DynamicField{i}"), flat, rate)
        for row in levels.get(skill_id, []):
            if intv(row.get("LV")) > intv(skill.get("Level"), 1):
                continue
            for i in range(1, 4):
                add_passive(row.get(f"PassiveProp.DynamicField{i}"), flat, rate)


def imprint(imprint_id: str | None, level: int) -> list[tuple[str, float]]:
    row = master().get("role_imprints", {}).get(imprint_id or "")
    if not row or level <= 0:
        return []

    props: list[tuple[str, float]] = []
    for raw, times in ((row.get("Base.DynamicField1"), 1), (row.get("LevelAdd.DynamicField1"), max(level - 1, 0))):
        if raw and "#" in raw:
            prop, value = raw.split("#", 1)
            props.append((prop, num(value) * times))
    return props


def team_bonuses(roles: list[dict[str, Any]]) -> dict[int, dict[str, dict[str, float]]]:
    bonuses = {i: {"flat": bucket(), "rate": bucket()} for i in range(len(roles))}
    for source_i, role in enumerate(roles):
        if role.get("IsSelfImprint"):
            continue
        _, row = base_stats(role)
        if not row:
            continue
        for prop, value in imprint(row.get("TeamImprint"), intv(role.get("ImprintLV"))):
            for target_i in bonuses:
                if target_i != source_i:
                    add_prop(bonuses[target_i]["flat"], bonuses[target_i]["rate"], prop, value)
    return bonuses


def calculate_role_stats(role: dict[str, Any], team_bonus: dict[str, dict[str, float]] | None = None) -> dict[str, float]:
    base, row = base_stats(role)
    flat, rate = bucket(), bucket()

    if team_bonus:
        for stat, value in team_bonus.get("flat", {}).items():
            flat[stat] += value
        for stat, value in team_bonus.get("rate", {}).items():
            rate[stat] += value

    add_awaken(role.get("StaticID", ""), intv(role.get("AwakenLV")), flat, rate)
    add_equips(role.get("EquipmentMap"), flat, rate)
    add_sets(role.get("EquipmentMap"), rate)
    add_bond(role.get("ArtifactData"), flat)
    add_skills(role, flat, rate)

    if row and role.get("IsSelfImprint"):
        for prop, value in imprint(row.get("SelfImprint"), intv(role.get("ImprintLV"))):
            add_prop(flat, rate, prop, value)

    stats = {stat: base[stat] * (1 + rate[stat]) + flat[stat] for stat in BASE}
    stats.update({stat: base[stat] + rate[stat] + flat[stat] for stat in EXTRA})
    stats["CriticalRate"] = min(stats.get("CriticalRate", 0), 1)
    stats["CriticalDamageRate"] = min(stats.get("CriticalDamageRate", 0), 3.5)
    return stats


def calculate_team_stats(roles: list[dict[str, Any]]) -> list[dict[str, float]]:
    bonuses = team_bonuses(roles)
    return [calculate_role_stats(role, bonuses.get(i)) for i, role in enumerate(roles)]


def stat_int(value: float) -> int:
    return round(value)


def hp_int(value: float) -> int:
    return round(value)


def format_role_stats(stats: dict[str, float]) -> str:
    return (
        f'生命{hp_int(stats.get("HP", 0))} '
        f'攻击{stat_int(stats.get("Attack", 0))} '
        f'防御{stat_int(stats.get("Defence", 0))} '
        f'速度{stat_int(stats.get("Speed", 0))} '
        f'暴击{round(stats.get("CriticalRate", 0) * 100)}% '
        f'暴伤{round(stats.get("CriticalDamageRate", 0) * 100)}% '
        f'命中{round(stats.get("EffectHitRate", 0) * 100)}% '
        f'抗性{round(stats.get("ResistanceRate", 0) * 100)}%'
    )


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def pickup_from_login(login_data: dict[str, Any]) -> str | None:
    now = login_data.get("Info", {}).get("LoginTime", {}).get("$date")
    candidates: list[tuple[int, int, str]] = []
    for node in _walk(login_data):
        activity_id = node.get("ActivityID")
        match = re.search(r"H\d+", activity_id or "") if isinstance(activity_id, str) else None
        if not match:
            continue
        start = node.get("StartTime", {}).get("$date", 0)
        end = node.get("EndTime", {}).get("$date", 0)
        if now and start and end and not (start <= now <= end):
            continue
        suffix = match.group(0)
        priority = 0
        if activity_id == f"Branch{suffix}":
            priority = 3
        elif activity_id == f"ActivitySignIn{suffix}":
            priority = 2
        elif activity_id.startswith(("AcyivitySummon", "ActivitySummon")):
            priority = 1
        if not priority:
            continue
        candidates.append((priority, int(start or 0), suffix))
    return max(candidates)[2] if candidates else None


def get_pickup(login_data: dict[str, Any] | None = None) -> str:
    if login_data:
        pickup = pickup_from_login(login_data)
        if pickup:
            return pickup
    branches = (
        activity_id for activity_id, row in master().get("activities", {}).items()
        if row.get("Type") == "SideStory" and re.fullmatch(r"BranchH\d+", activity_id or "")
    )
    pickup = max(branches, key=lambda value: intv(value.replace("BranchH", "")), default=None)
    return pickup.replace("Branch", "") if pickup else "H602"


def get_activity_scene_ids(pickup: str) -> list[str]:
    prefix = f"B{pickup}_1_"
    scene_ids = [
        row.get("ID") for row in master().get("scenes", {}).get(f"Branch{pickup}", [])
        if re.fullmatch(rf"{re.escape(prefix)}\d+", row.get("ID") or "")
    ]
    scene_ids.sort(key=lambda scene_id: intv(scene_id.removeprefix(prefix)))
    return scene_ids or [f"B{pickup}_1_{i + 1}" for i in range(12)]


def _parse_team(raw: str) -> list[dict[str, Any]]:
    members = []
    for match in re.finditer(r'M:"(?P<sid>[^"]+)"[^}]*?Pos:(?P<pos>\d+)[^}]*?LV:(?P<lv>\d+)', raw or ""):
        members.append({"sid": match.group("sid"), "pos": int(match.group("pos")), "lv": int(match.group("lv"))})
    return members


def get_activity_npc_pos_map(pickup: str) -> tuple[int, dict[str, dict[str, Any]]]:
    prefix = f"B{pickup}_1_"
    rows = [
        row for row in master().get("scenes", {}).get(f"Branch{pickup}", [])
        if row.get("MyCampTeam")
    ]
    rows.sort(key=lambda row: intv((row.get("ID") or "").removeprefix(prefix)))

    for row in rows:
        members = _parse_team(row.get("MyCampTeam") or "")
        if not members:
            continue
        preferred = [m for m in members if m["sid"] == f"AcStory{pickup}"]
        source = preferred or members[:1]
        index = int((row.get("ID") or "0_2").rsplit("_", 1)[-1]) - 1
        return index, {str(i): {"StaticID": m["sid"], "LV": m["lv"]} for i, m in enumerate(source)}

    return 1, {"0": {"StaticID": f"AcStory{pickup}", "LV": 60}}
