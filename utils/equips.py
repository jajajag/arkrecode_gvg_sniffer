from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from utils.helper import get_prop_score, num


MIN_CLASS_LV = 4
CONFIG_JSON = Path("data/config.json")
EQUIP_TYPE_MAP = {
    "1": "Weapon",
    "2": "Head",
    "3": "Body",
    "4": "Necklace",
    "5": "Ring",
    "6": "Shoes",
}
EQUIP_CONFIG_KEYS = {
    "Necklace": "necklace",
    "Ring": "ring",
    "Shoes": "shoes",
}
LEFT_EQUIP_TYPES = frozenset(("Weapon", "Head", "Body"))
RIGHT_EQUIP_TYPES = frozenset(("Necklace", "Ring", "Shoes"))
VALID_EQUIP_PREFIXES = frozenset(("E010", "E016", "E022", "E028", "E034"))
SPEED_REQUIRED_SETS = frozenset(("Speed", "Revenge"))


@lru_cache(maxsize=1)
def config() -> dict[str, Any]:
    with CONFIG_JSON.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def update_equip_templates(*_args: Any, **_kwargs: Any) -> None:
    print("装备模板已改为读取 data/config.json，无需从竞技场装备生成。")


def equip_score(sub_props: dict[str, float]) -> float:
    return sum(value * get_prop_score(prop) for prop, value in sub_props.items())


def _equip_type(equip: dict[str, Any]) -> str | None:
    static_id = str(equip.get("StaticID") or "")
    return EQUIP_TYPE_MAP.get(static_id[-1:]) if static_id else None


def _main_prop(equip: dict[str, Any]) -> str:
    return (equip.get("MainProp") or {}).get("PropertyType") or ""


def _sub_values(equip: dict[str, Any]) -> dict[str, float]:
    values: dict[str, float] = {}
    for prop in (equip.get("SubProps") or {}).get("SourceValues") or []:
        prop_type = prop.get("PropertyType")
        if prop_type:
            values[prop_type] = num(prop.get("Value", prop.get("SValue")))
    return values


def _min_score() -> float:
    return num(config()["equip_score_threshold"])


def _template_names_for_set(set_name: str) -> list[str]:
    names = config().get("equip_sets", {}).get(set_name)
    return names if isinstance(names, list) else []


def _template(template_name: str) -> dict[str, Any]:
    template = config().get("equip_templates", {}).get(template_name)
    return template if isinstance(template, dict) else {}


def _matches_template(eq_type: str, set_name: str, main_prop: str, sub_props: set[str]) -> str | None:
    for template_name in _template_names_for_set(set_name):
        template = _template(template_name)
        allowed_subs = set(template.get("subprops") or ())
        if not allowed_subs or not sub_props.issubset(allowed_subs):
            continue

        if eq_type in RIGHT_EQUIP_TYPES:
            part_key = EQUIP_CONFIG_KEYS.get(eq_type)
            if main_prop not in set(template.get(part_key) or ()):
                continue
        elif eq_type not in LEFT_EQUIP_TYPES:
            continue

        return template_name
    return None


def _format_match(
    eq_type: str,
    set_name: str,
    main_prop: str,
    score: float,
    sub_props: set[str],
    reason: str,
) -> str:
    score_text = f"{score:.1f}".rstrip("0").rstrip(".")
    return f"{eq_type} {set_name} {main_prop} {score_text} [{reason}] -> {sorted(sub_props)}"


def match_equip(equip: dict[str, Any]) -> str | None:
    eq_type = _equip_type(equip)
    if not eq_type:
        return None

    # 1. 传说装备
    if int(equip.get("ClassLV") or 0) < MIN_CLASS_LV:
        return None

    # 2. 85级装备
    static_id = str(equip.get("StaticID") or "")
    if static_id[:4] not in VALID_EQUIP_PREFIXES:
        return None

    set_name = equip.get("Set") or ""
    main_prop = _main_prop(equip)
    sub_dict = _sub_values(equip)
    sub_props = set(sub_dict)
    speed = sub_dict.get("SpeedValue", 0)

    # 3. 速度套/复仇套速度要求
    if set_name in SPEED_REQUIRED_SETS:
        if eq_type == "Shoes":
            if main_prop != "SpeedValue":
                return None
        elif speed < 4:
            return None

    score = equip_score(sub_dict)

    # 4. 非鞋5速直接要
    if eq_type != "Shoes" and speed >= 5:
        return _format_match(eq_type, set_name, main_prop, score, sub_props, "5速")

    # 5. 副属性分数门槛
    if score < _min_score():
        return None

    # 6. 套装 -> 模板 -> 主属性/副属性检查
    template_name = _matches_template(eq_type, set_name, main_prop, sub_props)
    if template_name:
        return _format_match(eq_type, set_name, main_prop, score, sub_props, template_name)

    return None
