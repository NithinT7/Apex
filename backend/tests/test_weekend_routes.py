from fastapi.testclient import TestClient

from app.api import career_routes, weekend_routes
from app.main import app
from app.save.save_manager import SaveManager


def test_simulate_opening_weekend_updates_save(tmp_path) -> None:
    manager = SaveManager(tmp_path)
    career_routes.manager = manager
    weekend_routes.manager = manager
    client = TestClient(app)

    create_response = client.post(
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
    save_id = create_response.json()["saveId"]

    response = client.post(f"/career/{save_id}/weekend/f2_2026_round_01/simulate")

    assert response.status_code == 200
    body = response.json()
    weekend = body["weekendResults"][0]

    assert body["phase"] == "between_races"
    assert body["currentDate"] == "2026-03-08"
    assert body["calendar"][0]["completed"] is True
    assert weekend["completed"] is True
    assert len(weekend["qualifying"]["classification"]) == 22
    assert len(weekend["sprint"]["lapLog"]) == 12
    assert len(weekend["feature"]["lapLog"]) == 24
    assert len(weekend["feature"]["classification"]) == 22
    assert 1 <= len(weekend["sprint"]["decisionPrompts"]) <= 6
    assert 3 <= len(weekend["feature"]["decisionPrompts"]) <= 8
    assert any(
        lap["decisionPrompt"] is not None
        for lap in weekend["feature"]["lapLog"]
    )
    assert weekend["feature"]["decisionPrompts"][0]["choices"]
    assert any(news["id"] == "f2_2026_round_01_feature_headline" for news in body["news"])
    assert sum(entry["points"] for entry in body["standings"]["driverStandings"]) > 0


def test_completed_weekend_can_be_fetched_and_not_resimulated(tmp_path) -> None:
    manager = SaveManager(tmp_path)
    career_routes.manager = manager
    weekend_routes.manager = manager
    client = TestClient(app)

    save = client.post(
        "/career/new",
        json={
            "name": "Test Driver",
            "nationality": "British",
            "age": 19,
            "driverNumber": 42,
            "backgroundId": "technical_driver",
            "archetypeId": "smooth_operator",
            "teamId": "f2_art",
            "academyId": "academy_independent",
            "difficulty": "realistic",
        },
    ).json()

    first = client.post(f"/career/{save['saveId']}/weekend/f2_2026_round_01/simulate")
    assert first.status_code == 200

    fetched = client.get(f"/career/{save['saveId']}/weekend/f2_2026_round_01")
    assert fetched.status_code == 200
    assert fetched.json()["roundId"] == "f2_2026_round_01"

    second = client.post(f"/career/{save['saveId']}/weekend/f2_2026_round_01/simulate")
    assert second.status_code == 409
