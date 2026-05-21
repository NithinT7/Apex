from fastapi.testclient import TestClient

from app.main import app


def test_data_bootstrap_endpoint() -> None:
    client = TestClient(app)

    response = client.get("/data/bootstrap")

    assert response.status_code == 200
    body = response.json()
    assert body["f1Drivers"][0]["series"] == "F1"
    assert body["f2Calendar"][0]["trackId"] == "melbourne"


def test_f2_team_endpoint() -> None:
    client = TestClient(app)

    response = client.get("/data/teams/f2")

    assert response.status_code == 200
    assert any(team["name"] == "PREMA Racing" for team in response.json())
