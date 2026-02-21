import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.utils.supplements_loader import build_intake_snapshot, format_nutrient_label


def test_build_intake_snapshot_scales_and_aggregates_nutrients():
    items_master = {
        "blend": {
            "name": "Blend",
            "ingredients": {
                "ビタミンC_mg": 1000,
                "プロテイン_g": 10,
            },
        },
        "vitamin_d": {
            "name": "Vitamin D",
            "ingredients": {
                "ビタミンD_IU": 2000,
                "ビタミンC_mg": 200,
            },
        },
    }

    snapshot = build_intake_snapshot(
        items_master,
        {
            "blend": 0.8,
            "vitamin_d": 1.5,
        },
    )

    assert len(snapshot["items"]) == 2
    assert snapshot["total_nutrients"]["ビタミンC_mg"] == 1100
    assert snapshot["total_nutrients"]["プロテイン_g"] == 8
    assert snapshot["total_nutrients"]["ビタミンD_IU"] == 3000


def test_format_nutrient_label():
    assert format_nutrient_label("ビタミンC_mg") == "ビタミンC (mg)"
    assert format_nutrient_label("グリシン") == "グリシン"
