from fastapi.testclient import TestClient

from app.api import career_routes
from app.main import app
from app.save.save_manager import SaveManager


def test_new_career_options() -> None:
    client = TestClient(app)

    response = client.get("/career/new/options")

    assert response.status_code == 200
    body = response.json()
    assert len(body["backgrounds"]) == 6
    assert len(body["archetypes"]) == 6
    assert any(team["name"] == "PREMA Racing" for team in body["f2Teams"])
    assert any(academy["id"] == "academy_independent" for academy in body["academies"])


def test_create_career_inserts_player_into_f2_save(tmp_path) -> None:
    career_routes.manager = SaveManager(tmp_path)
    client = TestClient(app)

    response = client.post(
        "/career/new",
        json={
            "name": "Nithin Thumma",
            "nationality": "Indian",
            "age": 18,
            "driverNumber": 27,
            "backgroundId": "karting_prodigy",
            "archetypeId": "one_lap_monster",
            "teamId": "f2_prema",
            "academyId": "academy_ferrari",
            "difficulty": "realistic",
        },
    )

    assert response.status_code == 201
    body = response.json()
    player = next(driver for driver in body["drivers"] if driver["id"] == "player_driver")
    f2_drivers = [driver for driver in body["drivers"] if driver["series"] == "F2"]

    assert body["playerDriverId"] == "player_driver"
    assert len(body["drivers"]) == 44
    assert len(f2_drivers) == 22
    assert player["teamId"] == "f2_prema"
    assert player["academyId"] == "academy_ferrari"
    assert player["attributes"]["pace"] == 81
    assert player["attributes"]["qualifying"] == 80
    assert any(news["id"] == "player_announced" for news in body["news"])
