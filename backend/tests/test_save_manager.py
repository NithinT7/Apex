from app.models.save_game import CreateSaveRequest
from app.save.save_manager import SaveManager


def test_create_list_get_and_delete_save(tmp_path) -> None:
    manager = SaveManager(tmp_path)

    save = manager.create(CreateSaveRequest(name="Road to F1"))

    assert save.name == "Road to F1"
    assert save.phase == "preseason"
    assert save.player_driver_id is None
    assert len(save.drivers) == 44
    assert len(save.calendar) == 14
    assert save.standings.driver_standings
    assert (tmp_path / f"{save.save_id}.json").exists()

    summaries = manager.list()
    assert len(summaries) == 1
    assert summaries[0].save_id == save.save_id

    loaded = manager.get(save.save_id)
    assert loaded is not None
    assert loaded.random_seed == save.random_seed

    assert manager.delete(save.save_id) is True
    assert manager.get(save.save_id) is None
    assert manager.delete(save.save_id) is False
