from vending_outreach.models import property_key


def test_same_community_different_naming_collapses():
    """Places returns the same property under several names; they must dedupe."""
    a = property_key("The Lofts at Haddon Point", "1 Haddon Point Way, Pennsauken NJ")
    b = property_key("Lofts at Haddon Point Apartments", "1 Haddon Point Way, Pennsauken NJ")
    assert a == b


def test_different_street_numbers_stay_distinct():
    a = property_key("Riverloft", "2201 Chestnut St")
    b = property_key("Riverloft", "2301 Chestnut St")
    assert a != b


def test_key_is_stable_across_runs():
    assert property_key("Bexley", "500 Lincoln Dr") == property_key("Bexley", "500 Lincoln Dr")
