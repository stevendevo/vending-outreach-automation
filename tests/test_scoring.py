import pytest

from vending_outreach.config import Config
from vending_outreach.models import Property
from vending_outreach.scoring import score_property


@pytest.fixture
def cfg():
    return Config.load()


def _prop(**kw):
    base = dict(key="k", name="Test", lat=39.93, lng=-75.03)
    base.update(kw)
    return Property(**base)


def test_bigger_community_scores_higher(cfg):
    small, _ = score_property(_prop(unit_count=90), cfg, True)
    big, _ = score_property(_prop(unit_count=450), cfg, True)
    assert big > small


def test_existing_food_truck_history_is_a_strong_signal(cfg):
    plain, _ = score_property(_prop(unit_count=200), cfg, True)
    proven, _ = score_property(_prop(unit_count=200, hosts_food_trucks=True), cfg, True)
    assert proven > plain


def test_large_portfolio_beats_a_one_off(cfg):
    one, _ = score_property(_prop(unit_count=200), cfg, True)
    many, _ = score_property(
        _prop(unit_count=200, portfolio_size=12, management_company="Morgan"), cfg, True)
    assert many > one


def test_unknown_data_does_not_score_worse_than_known_bad(cfg):
    """An un-enriched property must not be ranked below one we know is a poor
    fit -- otherwise good targets get buried before we ever look at them."""
    unknown, _ = score_property(_prop(unit_count=400), cfg, True, enriched=False)
    known_far = _prop(unit_count=400, lat=38.0, lng=-77.5, rating_count=3)
    known, _ = score_property(known_far, cfg, False, enriched=True)
    assert unknown > known


def test_distance_penalises(cfg):
    near, _ = score_property(_prop(unit_count=300), cfg, True)
    far, _ = score_property(_prop(unit_count=300, lat=38.5, lng=-76.8), cfg, True)
    assert near > far


def test_reasons_are_human_readable(cfg):
    _, why = score_property(_prop(unit_count=300, hosts_food_trucks=True), cfg, True)
    assert "300 units" in why
    assert "food trucks" in why
