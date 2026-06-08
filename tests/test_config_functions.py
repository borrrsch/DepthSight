# tests/test_config_functions.py
import pytest
import json
import time
from unittest.mock import MagicMock


# Importing the functions under test and the config module
try:
    from bot_module import config

    # Importing functions for direct testing
    from bot_module.config import load_optimized_params, get_strategy_param
except ImportError:
    pytest.skip("Cannot import bot_module.config.", allow_module_level=True)

# --- Fixtures ---


@pytest.fixture
def setup_config_files(tmp_path, monkeypatch):
    """Sets up temporary files and patches variables in config."""
    opt_file = tmp_path / "test_optimized.json"
    # Patching the file path in the config module
    monkeypatch.setattr(config, "OPTIMIZED_PARAMS_FILE", str(opt_file))
    # Patching (or creating, if it doesn't exist) the in-memory storage
    monkeypatch.setattr(config, "_optimized_params_data", {}, raising=False)
    monkeypatch.setattr(config, "_optimized_params_last_mtime", 0, raising=False)
    # Patching strategy defaults
    monkeypatch.setattr(
        config,
        "STRATEGY_DEFAULTS",
        {
            "StratA": {"param1": 10, "param2": "default_a"},
            "StratB": {"param1": 20, "param3": True},
        },
        raising=False,
    )
    return opt_file


# --- Tests for load_optimized_params ---


def test_load_optimized_params_file_not_found(setup_config_files, monkeypatch):
    """Test of loading when the file does not exist."""
    opt_file = setup_config_files
    # Ensuring the file does not exist
    if opt_file.exists():
        opt_file.unlink()
    # Resetting the state in memory
    monkeypatch.setattr(config, "_optimized_params_data", {"some": "old_data"})
    monkeypatch.setattr(config, "_optimized_params_last_mtime", 12345)

    load_optimized_params()  # Call the function

    # Checking that the data in memory has been cleared
    assert config._optimized_params_data == {}
    assert config._optimized_params_last_mtime == 0


def test_load_optimized_params_empty_file(setup_config_files, monkeypatch):
    """Test of loading an empty file."""
    opt_file = setup_config_files
    opt_file.write_text("")  # Create an empty file
    # Setting the initial state
    initial_data = {"some": "old_data"}
    initial_mtime = 12345
    monkeypatch.setattr(config, "_optimized_params_data", initial_data.copy())
    monkeypatch.setattr(config, "_optimized_params_last_mtime", initial_mtime)

    load_optimized_params()  # Calling the function, expecting an error to be logged

    # Data in memory should NOT change on parsing error
    assert config._optimized_params_data == initial_data
    assert config._optimized_params_last_mtime == initial_mtime


def test_load_optimized_params_invalid_json(setup_config_files, monkeypatch):
    """Test of loading a file with invalid JSON."""
    opt_file = setup_config_files
    opt_file.write_text("{invalid json")
    # Setting the initial state
    initial_data = {"some": "other_data"}
    initial_mtime = 54321
    monkeypatch.setattr(config, "_optimized_params_data", initial_data.copy())
    monkeypatch.setattr(config, "_optimized_params_last_mtime", initial_mtime)

    load_optimized_params()  # Calling the function, expecting an error to be logged

    # Data in memory MUST NOT change
    assert config._optimized_params_data == initial_data
    assert config._optimized_params_last_mtime == initial_mtime


def test_load_optimized_params_invalid_format(setup_config_files, monkeypatch):
    """Test of loading a file with valid JSON but an incorrect structure."""
    opt_file = setup_config_files
    opt_file.write_text(json.dumps({"some_other_key": "value"}))
    monkeypatch.setattr(config, "_optimized_params_data", {"some": "old_data"})
    monkeypatch.setattr(config, "_optimized_params_last_mtime", 12345)

    load_optimized_params()  # There should be no error, but the data will not load either

    # Data in memory MUST NOT change
    assert config._optimized_params_data == {"some": "old_data"}
    # The modification time should NOT change EITHER
    assert config._optimized_params_last_mtime == 12345


def test_load_optimized_params_success_first_time(setup_config_files, monkeypatch):
    """Test of successful loading for the first time."""
    opt_file = setup_config_files
    params_to_load = {"StratA": {"param1": 15, "new_param": "xyz"}}
    data_to_write = {"timestamp": time.time(), "optimized_params": params_to_load}
    opt_file.write_text(json.dumps(data_to_write))

    load_optimized_params()

    assert config._optimized_params_data == params_to_load
    assert config._optimized_params_last_mtime == opt_file.stat().st_mtime


def test_load_optimized_params_success_reload_if_changed(
    setup_config_files, monkeypatch
):
    """Test of reloading only if the file has changed."""
    opt_file = setup_config_files
    # 1. First load
    params1 = {"StratA": {"param1": 15}}
    data1 = {"timestamp": time.time(), "optimized_params": params1}
    opt_file.write_text(json.dumps(data1))
    mtime1 = opt_file.stat().st_mtime
    load_optimized_params()
    assert config._optimized_params_data == params1
    assert config._optimized_params_last_mtime == mtime1

    # 2. Call without file changes
    load_optimized_params()
    assert config._optimized_params_data == params1  # Data is the same
    assert config._optimized_params_last_mtime == mtime1  # Time is the same

    # 3. File modification and reload
    time.sleep(0.01)  # Ensuring a different modification time
    params2 = {"StratA": {"param1": 18}, "StratB": {"param3": False}}
    data2 = {"timestamp": time.time(), "optimized_params": params2}
    opt_file.write_text(json.dumps(data2))
    mtime2 = opt_file.stat().st_mtime
    assert mtime2 > mtime1
    load_optimized_params()
    assert config._optimized_params_data == params2  # Data updated
    assert config._optimized_params_last_mtime == mtime2  # Time updated


# --- Tests for get_strategy_param ---


def test_get_strategy_param_from_optimized(setup_config_files, monkeypatch):
    """Test of getting a parameter from optimized data."""
    # Loading parameters into config "memory"
    opt_params = {"StratA": {"param1": 15, "param2": "optimized_val"}}
    monkeypatch.setattr(config, "_optimized_params_data", opt_params)
    monkeypatch.setattr(config, "_optimized_params_last_mtime", 1)  # Marking as loaded

    # Requesting a parameter that exists in optimized
    assert get_strategy_param("StratA", "param1", default=99) == 15
    assert get_strategy_param("StratA", "param2", default="fallback") == "optimized_val"
    # Requesting a parameter that is not in optimized but is in default
    assert (
        get_strategy_param("StratB", "param1", default=99) == 20
    )  # Taking from STRATEGY_DEFAULTS
    assert (
        get_strategy_param("StratB", "param3", default=False) is True
    )  # Taking from STRATEGY_DEFAULTS


def test_get_strategy_param_from_defaults(setup_config_files, monkeypatch):
    """Test of getting a parameter from defaults."""
    # Clearing "optimized" data
    monkeypatch.setattr(config, "_optimized_params_data", {})
    monkeypatch.setattr(config, "_optimized_params_last_mtime", 1)

    assert (
        get_strategy_param("StratA", "param1", default=99) == 10
    )  # From STRATEGY_DEFAULTS
    assert (
        get_strategy_param("StratA", "param2", default="fallback") == "default_a"
    )  # From STRATEGY_DEFAULTS
    assert (
        get_strategy_param("StratB", "param3", default=False) is True
    )  # From STRATEGY_DEFAULTS


def test_get_strategy_param_fallback_to_default_arg(setup_config_files, monkeypatch):
    """Test of getting a parameter when it is nowhere to be found (the default argument is used)."""
    monkeypatch.setattr(config, "_optimized_params_data", {})
    monkeypatch.setattr(config, "_optimized_params_last_mtime", 1)

    assert (
        get_strategy_param("StratA", "non_existent_param", default="my_default")
        == "my_default"
    )
    assert get_strategy_param("StratA", "non_existent_param", default=None) is None
    assert get_strategy_param("NonExistentStrat", "param1", default=123) == 123


def test_get_strategy_param_calls_load_params(setup_config_files, monkeypatch):
    """Test: Ensure that get_strategy_param calls load_optimized_params (although it does not in the current implementation)."""
    # IN THE CURRENT IMPLEMENTATION, get_strategy_param DOES NOT CALL load_optimized_params.
    # load_optimized_params should be called periodically from outside (e.g., by a controller).
    # This test will show that there is NO call. If the logic is changed, the test will need to be updated.
    mock_load = MagicMock()
    monkeypatch.setattr(config, "load_optimized_params", mock_load)

    get_strategy_param("StratA", "param1")

    mock_load.assert_not_called()  # Expecting that it will NOT be called
