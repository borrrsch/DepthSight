# tests/test_tasks_model_lab.py

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import pandas as pd

from tasks import _async_generate_dataset_logic, _async_train_model_logic
from api import crud, schemas


@pytest.mark.anyio
async def test_generate_dataset_task_success(db_session, test_user):
    """Test for successful execution of the dataset generation task."""
    run_create = schemas.DatasetRunCreate(
        name="Task Test DS",
        symbols=["BTCUSDT"],
        start_date="2024-01-01T00:00:00Z",
        end_date="2024-02-01T00:00:00Z",
        feature_data_types=["kline_1m"],
        target_variable="Test",
    )
    db_run = await crud.create_dataset_run(
        db_session, test_user.id, run_create, "celery-id-1"
    )
    await db_session.commit()
    await db_session.refresh(db_run)

    mock_df = pd.DataFrame(
        {"feature1": [1, 2], "y_true": [0, 1], "raw_features_json": [{}, {}]}
    )

    # Adding a patch for pandas.DataFrame.to_parquet to avoid ImportError
    with (
        patch("tasks.DatasetGenerator", new_callable=MagicMock) as MockGeneratorClass,
        patch("pandas.DataFrame.to_parquet") as mock_to_parquet,
    ):
        # Setting up the mock for DatasetGenerator
        mock_generator_instance = MagicMock()
        mock_generator_instance.generate = AsyncMock(
            return_value=(mock_df, ["feature1"])
        )
        MockGeneratorClass.return_value = mock_generator_instance

        await _async_generate_dataset_logic(
            celery_task=MagicMock(),
            run_id=db_run.id,
            user_id=test_user.id,
            session=db_session,
        )

        # Checking that our mock for saving the file was called
        mock_to_parquet.assert_called_once()

    await db_session.refresh(db_run)
    assert db_run.status == "COMPLETED"
    assert db_run.file_path is not None
    assert db_run.dataset_shape["rows"] == 2
    assert "feature1" in db_run.feature_list


@pytest.mark.anyio
async def test_train_model_task_success(db_session, test_user):
    """Test for successful execution of the training task."""
    ds_create = schemas.DatasetRunCreate(
        name="Dataset for Training Task",
        symbols=["ETHUSDT"],
        start_date="2024-01-01T00:00:00Z",
        end_date="2024-02-01T00:00:00Z",
        feature_data_types=["kline_1m"],
        target_variable="Test",
    )
    db_dataset = await crud.create_dataset_run(
        db_session, test_user.id, ds_create, "ds-task-2"
    )
    db_dataset.status = "COMPLETED"
    db_dataset.file_path = "/fake/path/to/dataset.parquet"
    await db_session.commit()

    # Passing an empty dictionary for hyperparameters to make the test more accurate
    train_create = schemas.TrainingRunCreate(
        dataset_id=db_dataset.id, model_type="River TestModel", hyperparameters={}
    )
    db_run = await crud.create_training_run(
        db_session, test_user.id, train_create, "celery-id-2"
    )
    await db_session.commit()
    await db_session.refresh(db_run)

    with (
        patch("tasks.run_river_training_from_config") as mock_run_training,
        patch("tasks.run_sklearn_training_from_config"),
        patch("pathlib.Path.exists", return_value=True),
    ):
        mock_run_training.return_value = ("/fake/model.joblib", "/fake/report.json")

        await _async_train_model_logic(
            celery_task=MagicMock(),
            run_id=db_run.id,
            user_id=test_user.id,
            session=db_session,
        )

    mock_run_training.assert_called_once()
    call_config = mock_run_training.call_args[0][0]
    assert call_config["data_file"] == db_dataset.file_path

    await db_session.refresh(db_run)
    assert db_run.status == "COMPLETED"
    assert db_run.model_path == "/fake/model.joblib"
