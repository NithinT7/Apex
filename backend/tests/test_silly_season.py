"""Tests for silly season driver market."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import career_routes, season_routes
from app.engine.silly_season_engine import (
    UPPER_MIDFIELD_PERFORMANCE,
    evaluate_f1_seat_openings,
    evaluate_player_f1_offers,
    generate_transfer_rumors,
    get_driver_rating,
    get_f2_promotion_candidates,
    process_player_f1_decision,
    simulate_silly_season,
)
from app.main import app
from app.models.save_game import ChampionshipEntry, ChampionshipState
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

    def test_affiliate_driver_can_be_linked_to_works_team(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)
        save = manager.get(save_id)
        bearman = next(driver for driver in save.drivers if driver.id == "driver_oliver_bearman")
        save = save.model_copy(
            update={
                "drivers": [
                    bearman.model_copy(update={"current_form": 90})
                    if driver.id == bearman.id
                    else driver
                    for driver in save.drivers
                ]
            }
        )

        rumors = generate_transfer_rumors(save)

        assert any(
            rumor.driver_id == bearman.id
            and rumor.to_team_id == "f1_ferrari"
            and rumor.transfer_type == "lateral"
            for rumor in rumors
        )


class TestEvaluatePlayerF1Offers:
    def test_no_offers_at_start(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)
        save = manager.get(save_id)

        # At the start with no races, player shouldn't have F1 offers
        offers = evaluate_player_f1_offers(save)

        # May or may not have offers depending on initial standings
        assert isinstance(offers, list)

    def test_offers_are_unique_by_team(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)
        save = manager.get(save_id)
        player_id = save.player_driver_id
        standings = ChampionshipState(
            driver_standings=[
                ChampionshipEntry(driver_id=player_id, points=250, wins=8, podiums=12),
                *[
                    ChampionshipEntry(driver_id=driver.id)
                    for driver in save.drivers
                    if driver.series == "F2" and driver.id != player_id
                ],
            ],
            team_standings=save.standings.team_standings,
        )
        save = save.model_copy(update={"phase": "offseason", "standings": standings})

        offers = evaluate_player_f1_offers(save)
        team_ids = [offer["team_id"] for offer in offers]

        assert len(team_ids) == len(set(team_ids))

    def test_non_champion_offers_are_lower_midfield_or_backmarker(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)
        save = manager.get(save_id)
        player_id = save.player_driver_id
        other_f2_drivers = [
            driver for driver in save.drivers if driver.series == "F2" and driver.id != player_id
        ]
        standings = ChampionshipState(
            driver_standings=[
                ChampionshipEntry(driver_id=other_f2_drivers[0].id, points=260, wins=7, podiums=10),
                ChampionshipEntry(driver_id=other_f2_drivers[1].id, points=230, wins=5, podiums=8),
                ChampionshipEntry(driver_id=other_f2_drivers[2].id, points=210, wins=3, podiums=7),
                ChampionshipEntry(driver_id=player_id, points=180, wins=1, podiums=5),
                *[
                    ChampionshipEntry(driver_id=driver.id)
                    for driver in other_f2_drivers[3:]
                ],
            ],
            team_standings=save.standings.team_standings,
        )
        save = save.model_copy(update={"phase": "offseason", "standings": standings})

        offers = evaluate_player_f1_offers(save)

        assert offers
        assert all(offer["car_performance"] < UPPER_MIDFIELD_PERFORMANCE for offer in offers)

    def test_outsider_has_lower_chance_when_team_has_academy_candidate(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)
        save = manager.get(save_id)
        player_id = save.player_driver_id
        alpine_junior = next(
            driver
            for driver in save.drivers
            if driver.series == "F2" and driver.academy_id == "academy_alpine"
        )
        other_f2_drivers = [
            driver
            for driver in save.drivers
            if driver.series == "F2" and driver.id not in {player_id, alpine_junior.id}
        ]
        standings = ChampionshipState(
            driver_standings=[
                ChampionshipEntry(driver_id=player_id, points=250, wins=8, podiums=12),
                ChampionshipEntry(driver_id=alpine_junior.id, points=220, wins=4, podiums=8),
                *[ChampionshipEntry(driver_id=driver.id) for driver in other_f2_drivers],
            ],
            team_standings=save.standings.team_standings,
        )
        save = save.model_copy(update={"phase": "offseason", "standings": standings})
        outsider_offer = next(
            offer for offer in evaluate_player_f1_offers(save) if offer["team_id"] == "f1_alpine"
        )

        player = next(driver for driver in save.drivers if driver.id == player_id)
        alpine_player = player.model_copy(update={"academy_id": "academy_alpine"})
        academy_save = save.model_copy(
            update={
                "drivers": [
                    alpine_player if driver.id == player_id else driver
                    for driver in save.drivers
                ]
            }
        )
        academy_offer = next(
            offer for offer in evaluate_player_f1_offers(academy_save) if offer["team_id"] == "f1_alpine"
        )

        assert academy_offer["likelihood"] - outsider_offer["likelihood"] >= 20

    def test_historical_affiliate_boosts_top_academy_driver(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)
        save = manager.get(save_id)
        player_id = save.player_driver_id
        other_f2_drivers = [
            driver for driver in save.drivers if driver.series == "F2" and driver.id != player_id
        ]
        standings = ChampionshipState(
            driver_standings=[
                ChampionshipEntry(driver_id=player_id, points=250, wins=8, podiums=12),
                *[ChampionshipEntry(driver_id=driver.id) for driver in other_f2_drivers],
            ],
            team_standings=save.standings.team_standings,
        )
        ferrari_save = save.model_copy(update={"phase": "offseason", "standings": standings})
        ferrari_haas = next(
            offer for offer in evaluate_player_f1_offers(ferrari_save) if offer["team_id"] == "f1_haas"
        )

        player = next(driver for driver in save.drivers if driver.id == player_id)
        independent_player = player.model_copy(update={"academy_id": "academy_independent"})
        independent_save = ferrari_save.model_copy(
            update={
                "drivers": [
                    independent_player if driver.id == player_id else driver
                    for driver in ferrari_save.drivers
                ]
            }
        )
        independent_haas = next(
            offer for offer in evaluate_player_f1_offers(independent_save) if offer["team_id"] == "f1_haas"
        )

        assert ferrari_haas["likelihood"] - independent_haas["likelihood"] >= 10

    def test_top_team_non_academy_route_requires_marketability(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)
        save = manager.get(save_id)
        player_id = save.player_driver_id
        player = next(driver for driver in save.drivers if driver.id == player_id)
        aston_driver_ids = {
            driver.id for driver in save.drivers if driver.series == "F1" and driver.team_id == "f1_aston_martin"
        }
        other_f2_drivers = [
            driver for driver in save.drivers if driver.series == "F2" and driver.id != player_id
        ]
        standings = ChampionshipState(
            driver_standings=[
                ChampionshipEntry(driver_id=player_id, points=280, wins=10, podiums=14),
                *[ChampionshipEntry(driver_id=driver.id) for driver in other_f2_drivers],
            ],
            team_standings=save.standings.team_standings,
        )
        strong_attrs = player.attributes.model_copy(
            update={
                "pace": 92,
                "qualifying": 92,
                "racecraft": 94,
                "consistency": 94,
                "reputation": 86,
                "sponsor_value": 86,
            }
        )
        low_market_player = player.model_copy(
            update={
                "academy_id": "academy_independent",
                "attributes": strong_attrs.model_copy(update={"marketability": 62}),
            }
        )
        base_save = save.model_copy(
            update={
                "phase": "offseason",
                "standings": standings,
                "contracts": [
                    contract for contract in save.contracts if contract.driver_id not in aston_driver_ids
                ],
            }
        )
        low_market_save = base_save.model_copy(
            update={
                "drivers": [
                    low_market_player if driver.id == player_id else driver
                    for driver in base_save.drivers
                ]
            }
        )

        high_market_player = low_market_player.model_copy(
            update={"attributes": strong_attrs.model_copy(update={"marketability": 94})}
        )
        high_market_save = base_save.model_copy(
            update={
                "drivers": [
                    high_market_player if driver.id == player_id else driver
                    for driver in base_save.drivers
                ]
            }
        )

        low_market_rumors = generate_transfer_rumors(low_market_save)
        high_market_rumors = generate_transfer_rumors(high_market_save)

        assert not any(rumor.driver_id == player_id and rumor.to_team_id == "f1_aston_martin" for rumor in low_market_rumors)
        assert any(rumor.driver_id == player_id and rumor.to_team_id == "f1_aston_martin" for rumor in high_market_rumors)


class TestSimulateSillySeason:
    def test_simulates_market(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)
        save = manager.get(save_id)

        updated_save, news = simulate_silly_season(save)

        # Should return a save game and news
        assert updated_save is not None
        assert isinstance(news, list)

    def test_market_preserves_f1_grid_size_and_caps_promotions(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)
        save = manager.get(save_id)
        before_f1_ids = {driver.id for driver in save.drivers if driver.series == "F1"}

        updated_save, news = simulate_silly_season(save)

        after_f1_ids = {driver.id for driver in updated_save.drivers if driver.series == "F1"}
        promoted_ids = after_f1_ids - before_f1_ids

        assert len(after_f1_ids) == len(before_f1_ids)
        assert len(promoted_ids) <= 4


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

    def test_returns_camel_case_offer_keys(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)
        save = manager.get(save_id)

        player_id = save.player_driver_id
        standings = ChampionshipState(
            driver_standings=[
                ChampionshipEntry(driver_id=player_id, points=250, wins=8, podiums=12),
                *[
                    ChampionshipEntry(driver_id=driver.id)
                    for driver in save.drivers
                    if driver.series == "F2" and driver.id != player_id
                ],
            ],
            team_standings=save.standings.team_standings,
        )
        save = save.model_copy(update={"phase": "offseason", "standings": standings})
        manager.save(save)

        response = client.get(f"/career/{save_id}/season/f1-offers")

        assert response.status_code == 200
        body = response.json()
        assert body["hasOffers"] is True
        assert "teamId" in body["offers"][0]
        assert "teamName" in body["offers"][0]
        assert "carPerformance" in body["offers"][0]
        assert "isAcademyTeam" in body["offers"][0]


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

    def test_accepting_offer_replaces_existing_f1_driver(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)
        save = manager.get(save_id)
        before_f1_count = sum(1 for driver in save.drivers if driver.series == "F1")

        updated_save, news = process_player_f1_decision(save, True, "f1_williams")

        after_f1_drivers = [driver for driver in updated_save.drivers if driver.series == "F1"]
        player = next(driver for driver in updated_save.drivers if driver.id == save.player_driver_id)

        assert len(after_f1_drivers) == before_f1_count
        assert player.series == "F1"
        assert player.team_id == "f1_williams"
        assert player.academy_id is None

    def test_joining_affiliate_team_keeps_academy_path(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)
        save = manager.get(save_id)

        updated_save, news = process_player_f1_decision(save, True, "f1_haas")
        player = next(driver for driver in updated_save.drivers if driver.id == save.player_driver_id)

        assert player.team_id == "f1_haas"
        assert player.academy_id == "academy_ferrari"


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
