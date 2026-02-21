from pathlib import Path
from typing import Any, Dict, List

import yaml

_SUPPLEMENTS_PATH = Path("config/supplements.yaml")


def load_supplements(path: Path = _SUPPLEMENTS_PATH) -> Dict[str, Any]:
    """Load supplements master YAML. Returns safe defaults if not found."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
            if not isinstance(loaded, dict):
                return {"items": {}, "presets": {}}
            return {
                "items": loaded.get("items", {}) or {},
                "presets": loaded.get("presets", {}) or {},
            }
    except FileNotFoundError:
        return {"items": {}, "presets": {}}


def get_scene_preset(scene: str, supplements: Dict[str, Any]) -> Dict[str, Any]:
    presets = supplements.get("presets", {}) if isinstance(supplements, dict) else {}
    preset = presets.get(scene, {}) if isinstance(presets, dict) else {}
    if not isinstance(preset, dict):
        preset = {}
    return {
        "default_items": preset.get("default_items", []) or [],
        "default_scale": float(preset.get("default_scale", 1.0) or 1.0),
    }


def format_nutrient_label(nutrient_key: str) -> str:
    if "_" not in nutrient_key:
        return nutrient_key
    name, unit = nutrient_key.rsplit("_", 1)
    return f"{name} ({unit})"


def _round_amount(value: float) -> float:
    rounded = round(value, 4)
    if float(rounded).is_integer():
        return int(rounded)
    return rounded


def build_intake_snapshot(
    items_master: Dict[str, Any],
    selected_item_scales: Dict[str, float],
) -> Dict[str, Any]:
    """Build immutable snapshot payload from selected item scales."""
    snapshot_items: List[Dict[str, Any]] = []
    total_nutrients: Dict[str, float] = {}

    for item_id, scale in selected_item_scales.items():
        item = items_master.get(item_id, {}) if isinstance(items_master, dict) else {}
        if not isinstance(item, dict):
            continue

        base_ingredients = item.get("ingredients", {})
        if not isinstance(base_ingredients, dict):
            continue

        ratio = max(0.5, min(1.5, float(scale)))
        scaled_ingredients: Dict[str, float] = {}

        for nutrient_key, amount in base_ingredients.items():
            if not isinstance(amount, (int, float)):
                continue
            scaled_amount = _round_amount(float(amount) * ratio)
            scaled_ingredients[nutrient_key] = scaled_amount
            total_nutrients[nutrient_key] = _round_amount(
                float(total_nutrients.get(nutrient_key, 0)) + float(scaled_amount)
            )

        snapshot_items.append(
            {
                "item_id": item_id,
                "name": item.get("name", item_id),
                "scale": ratio,
                "ingredients": scaled_ingredients,
            }
        )

    return {
        "items": snapshot_items,
        "total_nutrients": total_nutrients,
    }
