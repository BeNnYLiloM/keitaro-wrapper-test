import pytest
from sqlalchemy import select

from app.models import OperationLog, PinnedOffer, RemovedOffer
from app.schemas import PublishOffers
from app.services import editor
from app.services.errors import ServiceError
from tests.conftest import FakeKeitaro


def offers_stream(fake: FakeKeitaro, *offers: tuple[int, int]) -> dict:
    return fake.add_stream(
        campaign_id=1,
        name="Офферы",
        schema="landings",
        offers=[{"offer_id": oid, "share": share, "state": "active"} for oid, share in offers],
    )


def draft(*offer_ids: int, base: dict | None = None) -> PublishOffers:
    """draft(101, 102) — итоговый список офферов. base — поток, с которого начали редактирование."""
    base_offers = None
    if base is not None:
        base_offers = [{"offer_id": o["offer_id"], "share": o["share"]} for o in base["offers"]]
    return PublishOffers(offers=[{"offer_id": i} for i in offer_ids], base=base_offers)


def shares(view) -> list[tuple[int, int]]:
    return [(o.offer_id, o.share) for o in view.offers]


async def test_publish_added_offers_rebalances_equally(ctx, fake: FakeKeitaro) -> None:
    stream = offers_stream(fake, (101, 100))

    view = await editor.publish_offers(ctx, stream["id"], draft(101, 102, base=stream))
    assert shares(view) == [(101, 50), (102, 50)]

    view = await editor.publish_offers(ctx, stream["id"], draft(101, 102, 103))
    assert shares(view) == [(101, 34), (102, 33), (103, 33)]
    assert view.total_share == 100
    assert [o.name for o in view.offers] == [
        "Miaflow [BEAUTY-RO-BE_0009]",
        "Miaflow [BEAUTY-RO-BE_0008]",
        "Slimfit MX",
    ]
    # в Keitaro ушёл полный состав с правильными долями
    assert [(o["offer_id"], o["share"]) for o in fake.streams[stream["id"]]["offers"]] == shares(view)


async def test_publish_add_and_remove_in_one_go(ctx, fake: FakeKeitaro) -> None:
    stream = offers_stream(fake, (101, 34), (102, 33), (103, 33))

    view = await editor.publish_offers(ctx, stream["id"], draft(102, 103, 3717, base=stream))
    assert shares(view) == [(102, 34), (103, 33), (3717, 33)]

    entry = await ctx.session.scalar(select(OperationLog))
    assert entry.operation == "publish_offers"
    assert entry.payload["added"] == [3717]
    assert entry.payload["removed"] == [101]


async def test_pin_is_saved_immediately_and_freezes_share(ctx, fake: FakeKeitaro) -> None:
    stream = offers_stream(fake, (101, 50), (102, 50))

    view = await editor.pin_offer(ctx, stream["id"], 101)
    assert [(o.offer_id, o.share, o.pinned) for o in view.offers] == [(101, 50, True), (102, 50, False)]
    assert not any(c.request.method == "PUT" for c in fake.router.calls)  # в Keitaro ничего не меняли
    pins = (await ctx.session.scalars(select(PinnedOffer))).all()
    assert [(p.stream_id, p.offer_id) for p in pins] == [(stream["id"], 101)]

    # добавили два оффера — закреплённый 50%, остальные делят оставшиеся 50%
    view = await editor.publish_offers(ctx, stream["id"], draft(101, 102, 103, 3717))
    assert shares(view) == [(101, 50), (102, 17), (103, 17), (3717, 16)]
    assert [o.pinned for o in view.offers] == [True, False, False, False]

    # удалили незакреплённый — закреплённый всё равно 50%
    view = await editor.publish_offers(ctx, stream["id"], draft(101, 102, 103))
    assert shares(view) == [(101, 50), (102, 25), (103, 25)]

    # открепили — при следующей публикации снова поровну
    view = await editor.unpin_offer(ctx, stream["id"], 101)
    assert not any(o.pinned for o in view.offers)
    view = await editor.publish_offers(ctx, stream["id"], draft(101, 102, 103, 3717))
    assert shares(view) == [(101, 25), (102, 25), (103, 25), (3717, 25)]

    ops = (await ctx.session.scalars(select(OperationLog).order_by(OperationLog.id))).all()
    assert [o.operation for o in ops] == [
        "pin_offer",
        "publish_offers",
        "publish_offers",
        "unpin_offer",
        "publish_offers",
    ]


async def test_pins_are_returned_by_get_stream(ctx, fake: FakeKeitaro) -> None:
    stream = offers_stream(fake, (101, 50), (102, 50))
    await editor.pin_offer(ctx, stream["id"], 102)
    view = await editor.get_stream(ctx, stream["id"])
    assert [(o.offer_id, o.pinned) for o in view.offers] == [(101, False), (102, True)]


async def test_removing_pinned_offer_drops_its_pin(ctx, fake: FakeKeitaro) -> None:
    stream = offers_stream(fake, (101, 50), (102, 50))
    await editor.pin_offer(ctx, stream["id"], 101)
    view = await editor.publish_offers(ctx, stream["id"], draft(102, 103))
    assert shares(view) == [(102, 50), (103, 50)]
    assert (await ctx.session.scalars(select(PinnedOffer))).all() == []


async def test_cannot_pin_unpublished_offer(ctx, fake: FakeKeitaro) -> None:
    stream = offers_stream(fake, (101, 100))
    with pytest.raises(ServiceError) as exc_info:
        await editor.pin_offer(ctx, stream["id"], 102)
    assert exc_info.value.status_code == 404


async def test_pin_twice_is_idempotent(ctx, fake: FakeKeitaro) -> None:
    stream = offers_stream(fake, (101, 100))
    await editor.pin_offer(ctx, stream["id"], 101)
    await editor.pin_offer(ctx, stream["id"], 101)
    assert len((await ctx.session.scalars(select(PinnedOffer))).all()) == 1
    await editor.unpin_offer(ctx, stream["id"], 101)
    await editor.unpin_offer(ctx, stream["id"], 101)
    assert (await ctx.session.scalars(select(PinnedOffer))).all() == []


async def test_unchanged_draft_does_not_touch_keitaro(ctx, fake: FakeKeitaro) -> None:
    stream = offers_stream(fake, (101, 50), (102, 50))
    view = await editor.publish_offers(ctx, stream["id"], draft(101, 102))
    assert shares(view) == [(101, 50), (102, 50)]
    assert not any(c.request.method == "PUT" for c in fake.router.calls)


async def test_stale_base_is_rejected(ctx, fake: FakeKeitaro) -> None:
    stream = offers_stream(fake, (101, 100))
    stale = {"offers": [{"offer_id": 101, "share": 50}, {"offer_id": 999, "share": 50}]}
    with pytest.raises(ServiceError) as exc_info:
        await editor.publish_offers(ctx, stream["id"], draft(101, 102, base=stale))
    assert exc_info.value.status_code == 409
    assert fake.streams[stream["id"]]["offers"] == [{"offer_id": 101, "share": 100, "state": "active"}]


async def test_all_pinned_but_not_100_is_rejected(ctx, fake: FakeKeitaro) -> None:
    stream = offers_stream(fake, (101, 60), (102, 30), (103, 10))
    await editor.pin_offer(ctx, stream["id"], 101)
    await editor.pin_offer(ctx, stream["id"], 102)
    with pytest.raises(ServiceError) as exc_info:
        await editor.publish_offers(ctx, stream["id"], draft(101, 102))  # удалили единственный свободный
    assert exc_info.value.status_code == 422
    assert "Все офферы закреплены" in exc_info.value.detail


async def test_no_room_for_unpinned_is_rejected(ctx, fake: FakeKeitaro) -> None:
    stream = offers_stream(fake, (101, 60), (102, 40))
    await editor.pin_offer(ctx, stream["id"], 101)
    await editor.pin_offer(ctx, stream["id"], 102)
    with pytest.raises(ServiceError) as exc_info:
        await editor.publish_offers(ctx, stream["id"], draft(101, 102, 103))
    assert exc_info.value.status_code == 422
    assert "не хватит" in exc_info.value.detail
    assert [o["offer_id"] for o in fake.streams[stream["id"]]["offers"]] == [101, 102]


async def test_unknown_offer_is_rejected(ctx, fake: FakeKeitaro) -> None:
    stream = offers_stream(fake, (101, 100))
    with pytest.raises(ServiceError) as exc_info:
        await editor.publish_offers(ctx, stream["id"], draft(101, 999999))
    assert exc_info.value.status_code == 422
    assert fake.streams[stream["id"]]["offers"] == [{"offer_id": 101, "share": 100, "state": "active"}]


def test_draft_validation() -> None:
    with pytest.raises(ValueError, match="повторяются"):
        PublishOffers(offers=[{"offer_id": 1}, {"offer_id": 1}])
    with pytest.raises(ValueError):
        PublishOffers(offers=[])


async def test_redirect_stream_is_not_editable(ctx, fake: FakeKeitaro) -> None:
    stream = fake.add_stream(campaign_id=1, schema="redirect", action_payload="https://google.com")
    with pytest.raises(ServiceError) as exc_info:
        await editor.publish_offers(ctx, stream["id"], draft(101))
    assert exc_info.value.status_code == 400


async def test_disabled_offer_keeps_state(ctx, fake: FakeKeitaro) -> None:
    stream = fake.add_stream(
        campaign_id=1,
        schema="landings",
        offers=[{"offer_id": 101, "share": 100, "state": "disabled"}],
    )
    view = await editor.publish_offers(ctx, stream["id"], draft(101, 102))
    assert [(o.offer_id, o.share, o.state) for o in view.offers] == [(101, 50, "disabled"), (102, 50, "active")]


async def test_removed_offer_goes_to_archive_and_can_be_restored(ctx, fake: FakeKeitaro) -> None:
    stream = offers_stream(fake, (101, 34), (102, 33), (103, 33))

    view = await editor.publish_offers(ctx, stream["id"], draft(102, 103))
    assert shares(view) == [(102, 50), (103, 50)]
    # удалённый оффер виден в корзине потока с долей на момент удаления
    assert [(r.offer_id, r.name, r.share) for r in view.removed_offers] == [(101, "Miaflow [BEAUTY-RO-BE_0009]", 34)]
    rows = (await ctx.session.scalars(select(RemovedOffer))).all()
    assert [(r.stream_id, r.offer_id, r.share) for r in rows] == [(stream["id"], 101, 34)]

    # корзина переживает другие публикации
    view = await editor.publish_offers(ctx, stream["id"], draft(102, 103, 3717))
    assert [r.offer_id for r in view.removed_offers] == [101]

    # восстановили — снова в потоке, доли поровну, корзина пуста
    view = await editor.publish_offers(ctx, stream["id"], draft(102, 103, 3717, 101))
    assert shares(view) == [(102, 25), (103, 25), (3717, 25), (101, 25)]
    assert view.removed_offers == []
    assert (await ctx.session.scalars(select(RemovedOffer))).all() == []

    entry = (await ctx.session.scalars(select(OperationLog).order_by(OperationLog.id.desc()))).first()
    assert entry.payload["restored"] == [101]
    assert entry.payload["added"] == []


async def test_restored_offer_keeps_its_state(ctx, fake: FakeKeitaro) -> None:
    stream = fake.add_stream(
        campaign_id=1,
        schema="landings",
        offers=[
            {"offer_id": 101, "share": 50, "state": "active"},
            {"offer_id": 102, "share": 50, "state": "disabled"},
        ],
    )
    await editor.publish_offers(ctx, stream["id"], draft(101))
    view = await editor.publish_offers(ctx, stream["id"], draft(101, 102))
    assert [(o.offer_id, o.state) for o in view.offers] == [(101, "active"), (102, "disabled")]


async def test_removing_again_updates_archive_entry(ctx, fake: FakeKeitaro) -> None:
    stream = offers_stream(fake, (101, 50), (102, 50))
    await editor.publish_offers(ctx, stream["id"], draft(102))
    await editor.publish_offers(ctx, stream["id"], draft(102, 101, 103))
    view = await editor.publish_offers(ctx, stream["id"], draft(102, 103))
    assert [(r.offer_id, r.share) for r in view.removed_offers] == [(101, 33)]
    assert len((await ctx.session.scalars(select(RemovedOffer))).all()) == 1


async def test_archive_hides_offers_returned_outside_wrapper(ctx, fake: FakeKeitaro) -> None:
    stream = offers_stream(fake, (101, 50), (102, 50))
    await editor.publish_offers(ctx, stream["id"], draft(102))
    # кто-то вернул оффер прямо в Keitaro
    fake.streams[stream["id"]]["offers"].append({"offer_id": 101, "share": 50, "state": "active"})
    view = await editor.get_stream(ctx, stream["id"])
    assert view.removed_offers == []
