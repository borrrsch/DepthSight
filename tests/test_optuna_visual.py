# tests/test_optuna_visual.py

import os
import sys

# Ensure bot_module is in python path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from bot_module.trainer import (  # noqa: E402
    _scan_strategy_params,
    _inject_params_to_strategy,
    _is_heavy_strategy,
)


def test_scan_strategy_params():
    strategy_json = {
        "filters": {
            "type": "AND",
            "children": [
                {
                    "type": "time_filter",
                    "params": {
                        "start_hour_utc": 10,
                        "end_hour_utc": 18,
                        "mode": "include",
                    },
                }
            ],
        },
        "entryConditions": {
            "type": "AND",
            "children": [
                {"type": "rsi_condition", "params": {"period": 14, "threshold": 30.5}}
            ],
        },
        "initialization": {"params": {"sl_value": 1.5, "tp_value": 3.0}},
    }

    search_space = _scan_strategy_params(strategy_json, search_width_pct=50.0)

    # Assertions
    assert "filters.children.0.params.start_hour_utc" in search_space
    assert "filters.children.0.params.end_hour_utc" in search_space
    assert "entryConditions.children.0.params.period" in search_space
    assert "entryConditions.children.0.params.threshold" in search_space
    assert "initialization.params.sl_value" in search_space
    assert "initialization.params.tp_value" in search_space

    # Type checks
    assert search_space["entryConditions.children.0.params.period"][0] == "int"
    assert search_space["entryConditions.children.0.params.threshold"][0] == "float"
    assert search_space["initialization.params.sl_value"][0] == "float"


def test_inject_params_to_strategy():
    strategy_template = {
        "entryConditions": {
            "type": "AND",
            "children": [
                {"type": "rsi_condition", "params": {"period": 14, "threshold": 30.5}}
            ],
        }
    }

    suggested = {
        "entryConditions.children.0.params.period": 21,
        "entryConditions.children.0.params.threshold": 45.2,
    }

    injected = _inject_params_to_strategy(strategy_template, suggested)

    # Assertions
    assert injected["entryConditions"]["children"][0]["params"]["period"] == 21
    assert injected["entryConditions"]["children"][0]["params"]["threshold"] == 45.2


def test_is_heavy_strategy():
    # Light strategy
    light_strat = {
        "entryConditions": {
            "type": "AND",
            "children": [{"type": "rsi_condition", "params": {"period": 14}}],
        }
    }
    assert _is_heavy_strategy(light_strat) is False

    # Heavy strategy
    heavy_strat = {
        "entryConditions": {
            "type": "AND",
            "children": [{"type": "l2_microstructure", "params": {"period": 14}}],
        }
    }
    assert _is_heavy_strategy(heavy_strat) is True
