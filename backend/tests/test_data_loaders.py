from app.data.loaders import get_bootstrap, validate_data_references


def test_bootstrap_loads_real_world_data() -> None:
    bootstrap = get_bootstrap()

    assert len(bootstrap.f1_teams) == 11
    assert len(bootstrap.f1_drivers) == 22
    assert len(bootstrap.f2_teams) == 11
    assert len(bootstrap.f2_drivers) == 22
    assert len(bootstrap.academies) >= 8
    assert len(bootstrap.f2_calendar) == 14
    assert len(bootstrap.tracks) >= 39


def test_data_references_are_valid() -> None:
    assert validate_data_references() == []


def test_tracks_cover_full_2026_f1_calendar() -> None:
    track_ids = {track.id for track in get_bootstrap().tracks}

    expected_2026_f1_tracks = {
        "melbourne",
        "shanghai",
        "suzuka",
        "miami",
        "montreal",
        "monaco",
        "barcelona",
        "spielberg",
        "silverstone",
        "spa",
        "budapest",
        "zandvoort",
        "monza",
        "madrid",
        "baku",
        "singapore",
        "cota",
        "mexico_city",
        "interlagos",
        "las_vegas",
        "lusail",
        "yas_marina",
    }

    assert expected_2026_f1_tracks <= track_ids
