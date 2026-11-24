import pytest
from pydantic import ValidationError

from app.schemas import CampaignCreate
from app.services.countries import normalize_geo
from app.services.shares import ShareError, ShareSlot, allocate_shares, distribute_equally


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (0, []),
        (1, [100]),
        (2, [50, 50]),
        (3, [34, 33, 33]),
        (4, [25, 25, 25, 25]),
        (6, [17, 17, 17, 17, 16, 16]),
        (7, [15, 15, 14, 14, 14, 14, 14]),
    ],
)
def test_distribute_equally(count: int, expected: list[int]) -> None:
    assert distribute_equally(count) == expected


@pytest.mark.parametrize("count", range(1, 101))
def test_distribute_equally_always_sums_to_100(count: int) -> None:
    shares = distribute_equally(count)
    assert sum(shares) == 100
    assert max(shares) - min(shares) <= 1


def pin(share: int) -> ShareSlot:
    return ShareSlot(pinned=True, share=share)


FREE = ShareSlot()


@pytest.mark.parametrize(
    ("slots", "expected"),
    [
        ([FREE, FREE, FREE], [34, 33, 33]),
        ([pin(50), FREE, FREE], [50, 25, 25]),
        ([FREE, pin(40), FREE], [30, 40, 30]),
        ([pin(10), FREE, FREE, FREE], [10, 30, 30, 30]),
        ([pin(20), pin(20), FREE, FREE, FREE], [20, 20, 20, 20, 20]),
        ([pin(33), FREE, FREE], [33, 34, 33]),
        ([pin(60), pin(40)], [60, 40]),
        ([pin(98), FREE, FREE], [98, 1, 1]),
    ],
)
def test_allocate_shares(slots: list[ShareSlot], expected: list[int]) -> None:
    result = allocate_shares(slots)
    assert result == expected
    assert sum(result) == 100


@pytest.mark.parametrize(
    ("slots", "message"),
    [
        ([], "хотя бы один"),
        ([pin(70), pin(40), FREE], "больше 100"),
        ([pin(50), pin(30)], "Все офферы закреплены"),
        ([pin(99), FREE, FREE], "не хватит"),
        ([pin(100), FREE], "не хватит"),
        ([ShareSlot(pinned=True, share=None), FREE], "от 1 до 100"),
    ],
)
def test_allocate_shares_errors(slots: list[ShareSlot], message: str) -> None:
    with pytest.raises(ShareError, match=message):
        allocate_shares(slots)


def test_normalize_geo_accepts_string_and_list() -> None:
    assert normalize_geo("mx, au ,MX") == ["MX", "AU"]
    assert normalize_geo(["ro", "Ro", "gm"]) == ["RO", "GM"]
    assert normalize_geo("AU;MX RO") == ["AU", "MX", "RO"]


def test_normalize_geo_rejects_unknown_and_empty() -> None:
    with pytest.raises(ValueError, match="ZZ"):
        normalize_geo("AU,ZZ")
    with pytest.raises(ValueError):
        normalize_geo(" , ")


def test_campaign_create_validation() -> None:
    data = CampaignCreate(name="  test  ", geo="au,mx", offer_id=5)
    assert data.name == "test"
    assert data.geo == ["AU", "MX"]
    with pytest.raises(ValidationError):
        CampaignCreate(name="   ", geo="AU", offer_id=5)
    with pytest.raises(ValidationError):
        CampaignCreate(name="x", geo="AUS", offer_id=5)
    with pytest.raises(ValidationError):
        CampaignCreate(name="x", geo="AU", offer_id=0)
