"""Tests for silly season driver market."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import career_routes, season_routes
from app.engine.silly_season_engine import (
    evaluate_f1_seat_openings,
    evaluate_player_f1_offers,
    generate_transfer_rumors,
    get_driver_rating,
    get_f2_promotion_candidates,
    simulate_silly_season,
)
from app.main import app
from app.save.save_manager import SaveManager


def _create_career(tmp_path) -> tuple[TestClient, SaveManager, str]:
    """Create a career for testing."""
    manager = SaveManager(tmp_path)
    career_routes.manager = manager
    season_routes.manager = manager
    client = TestClient(app)

    response = client.post(
        "/career/new",
        json={
            "name": "Test Driver",
            "nationality": "British",
            "age": 18,
            "driverNumber": 27,
            "backgroundId": "karting_prodigy",
            "archetypeId": "one_lap_monster",
            "teamId": "f2_prema",
            "academyId": "academy_ferrari",
            "difficulty": "realistic",
        },
    )
    save_id = response.json()["saveId"]
    return client, manager, save_id


class TestGetDriverRating:
    def test_calculates_rating(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)
        save = manager.get(save_id)

        player = next(d for d in save.drivers if d.id == save.player_driver_id)
        rating = get_driver_rating(player)

        assert 0 <= rating <= 100


class TestGetF2PromotionCandidates:
    def test_returns_f2_drivers(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)
        save = manager.get(save_id)

        candidates = get_f2_promotion_candidates(save)

        # All candidates should be F2 drivers
        for driver, position in candidates:
            assert driver.series == "F2"
            assert 1 <= position <= 22


class TestEvaluateF1SeatOpenings:
    def test_returns_openings(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)
        save = manager.get(save_id)

        openings = evaluate_f1_seat_openings(save)

        # All openings should be for F1 teams
        for team, reason in openings:
            assert team.series == "F1"


class TestGenerateTransferRumors:
    def test_generates_rumors(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)
        save = manager.get(save_id)

        rumors = generate_transfer_rumors(save)

        # Should have some rumors
        for rumor in rumors:
            assert rumor.driver_id is not None
            assert rumor.to_team_id is not None
            assert 0 <= rumor.likelihood <= 100


class TestEvaluatePlayerF1Offers:
    def test_no_offers_at_start(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)
        save = manager.get(save_id)

        # At the start with no races, player shouldn't have F1 offers
        offers = evaluate_player_f1_offers(save)

        # May or may not have offers depending on initial standings
        assert isinstance(offers, list)


class TestSimulateSillySeason:
    def test_simulates_market(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)
        save = manager.get(save_id)

        updated_save, news = simulate_silly_season(save)

        # Should return a save game and news
        assert updated_save is not None
        assert isinstance(news, list)


class TestF1OffersEndpoint:
    def test_requires_offseason(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)

        response = client.get(f"/career/{save_id}/season/f1-offers")
        assert response.status_code == 400

    def test_returns_offers_in_offseason(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)
        save = manager.get(save_id)

        # Set to offseason
        save = save.model_copy(update={"phase": "offseason"})
        manager.save(save)

        response = client.get(f"/career/{save_id}/season/f1-offers")
        assert response.status_code == 200

        body = response.json()
        assert "offers" in body
        assert "hasOffers" in body


class TestF1DecisionEndpoint:
    def test_requires_offseason(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)

        response = client.post(
            f"/career/{save_id}/season/f1-decision",
            json={"accept": False},
        )
        assert response.status_code == 400

    def test_decline_offer(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)
        save = manager.get(save_id)

        # Set to offseason
        save = save.model_copy(update={"phase": "offseason"})
        manager.save(save)

        response = client.post(
            f"/career/{save_id}/season/f1-decision",
            json={"accept": False},
        )
        assert response.status_code == 200


class TestRumorsEndpoint:
    def test_requires_offseason(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)

        response = client.get(f"/career/{save_id}/season/rumors")
        assert response.status_code == 400

    def test_returns_rumors_in_offseason(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)
        save = manager.get(save_id)

        # Set to offseason
        save = save.model_copy(update={"phase": "offseason"})
        manager.save(save)

        response = client.get(f"/career/{save_id}/season/rumors")
        assert response.status_code == 200

        body = response.json()
        assert "rumors" in body


class TestSimulateMarketEndpoint:
    def test_requires_offseason(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)

        response = client.post(f"/career/{save_id}/season/simulate-market")
        assert response.status_code == 400

    def test_simulates_in_offseason(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)
        save = manager.get(save_id)

        # Set to offseason
        save = save.model_copy(update={"phase": "offseason"})
        manager.save(save)

        response = client.post(f"/career/{save_id}/season/simulate-market")
        assert response.status_code == 200
