from fastapi.testclient import TestClient

from app.api import save_routes
from app.main import app
from app.save.save_manager import SaveManager


def test_save_routes_create_list_get_and_delete(tmp_path) -> None:
    save_routes.manager = SaveManager(tmp_path)
    client = TestClient(app)

    create_response = client.post("/saves", json={"name": "Phase 2 Save"})

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["name"] == "Phase 2 Save"
    assert created["phase"] == "preseason"
    assert created["playerDriverId"] is None
    assert len(created["drivers"]) == 44

    list_response = client.get("/saves")
    assert list_response.status_code == 200
    assert list_response.json()[0]["saveId"] == created["saveId"]

    get_response = client.get(f"/saves/{created['saveId']}")
    assert get_response.status_code == 200
    assert get_response.json()["randomSeed"] == created["randomSeed"]

    delete_response = client.delete(f"/saves/{created['saveId']}")
    assert delete_response.status_code == 204

    missing_response = client.get(f"/saves/{created['saveId']}")
    assert missing_response.status_code == 404
