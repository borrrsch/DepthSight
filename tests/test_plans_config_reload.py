from pathlib import Path
from uuid import uuid4

from api.plans import PlansConfig


def test_plans_config_reloads_block_restrictions_when_file_changes():
    config_path = Path.cwd() / f".plans_config_test_{uuid4().hex}.yml"
    try:
        config_path.write_text(
            """
block_restrictions:
  pro_only:
    - btc_state_filter
  kline_only:
    - tape_condition
plans:
  free:
    permissions: []
    quotas: {}
registration_trial:
  enabled: true
  plan: standard
  days: 7
""".strip(),
            encoding="utf-8",
        )

        plans_config = PlansConfig(config_path)
        assert plans_config.get_block_restrictions()["kline_only"] == ["tape_condition"]
        assert plans_config.get_registration_trial_config() == {
            "enabled": True,
            "plan": "standard",
            "days": 7,
        }

        config_path.write_text(
            """
block_restrictions:
  pro_only:
    - btc_state_filter
    - open_interest
  kline_only:
    - tape_condition
    - senior_tf_confluence
plans:
  free:
    permissions: []
    quotas: {}
registration_trial:
  enabled: false
  plan: pro
  days: 14
""".strip(),
            encoding="utf-8",
        )

        assert plans_config.get_block_restrictions()["pro_only"] == [
            "btc_state_filter",
            "open_interest",
        ]
        assert plans_config.get_block_restrictions()["kline_only"] == [
            "tape_condition",
            "senior_tf_confluence",
        ]
        assert plans_config.get_registration_trial_config() == {
            "enabled": False,
            "plan": "pro",
            "days": 14,
        }
    finally:
        config_path.unlink(missing_ok=True)
