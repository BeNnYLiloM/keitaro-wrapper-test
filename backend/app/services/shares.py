from collections.abc import Sequence
from dataclasses import dataclass

TOTAL_SHARE = 100


class ShareError(ValueError):
    """Доли невозможно распределить (например, закреплённые офферы заняли всё)."""


def distribute_equally(count: int, total: int = TOTAL_SHARE) -> list[int]:
    """Делит `total` на `count` целых долей, которые в сумме дают ровно `total`.

    Остаток от деления раздаётся по +1 первым офферам:
    1 → [100], 2 → [50, 50], 3 → [34, 33, 33], 6 → [17, 17, 17, 17, 16, 16].
    """
    if count <= 0:
        return []
    base, remainder = divmod(total, count)
    return [base + 1 if i < remainder else base for i in range(count)]


@dataclass(frozen=True)
class ShareSlot:
    pinned: bool = False
    share: int | None = None  # для закреплённого оффера — его замороженная доля


def allocate_shares(slots: Sequence[ShareSlot], total: int = TOTAL_SHARE) -> list[int]:
    """Доли с учётом закреплённых офферов.

    Закреплённые офферы сохраняют свою долю, остальные поровну делят остаток
    (`total` минус сумма закреплённых) по правилу `distribute_equally`.
    Пример: [пин 50, -, -] → [50, 25, 25]; [пин 40, -, -] → [40, 30, 30].
    """
    if not slots:
        raise ShareError("В потоке должен остаться хотя бы один оффер")
    for slot in slots:
        if slot.pinned and (slot.share is None or not 1 <= slot.share <= total):
            raise ShareError(f"У закреплённого оффера доля должна быть от 1 до {total}%")

    pinned_total = sum(s.share or 0 for s in slots if s.pinned)
    free_count = sum(1 for s in slots if not s.pinned)
    free_total = total - pinned_total

    if pinned_total > total:
        raise ShareError(f"Закреплённые доли в сумме дают {pinned_total}% — больше {total}%. Открепите часть офферов")
    if free_count == 0 and pinned_total != total:
        raise ShareError(
            f"Все офферы закреплены, а их доли в сумме {pinned_total}%, не {total}%. "
            "Открепите хотя бы один оффер, чтобы он забрал остаток"
        )
    if free_count > free_total:
        raise ShareError(
            f"Незакреплённым офферам ({free_count} шт.) остаётся {free_total}% — "
            "этого не хватит даже по 1%. Открепите часть офферов"
        )

    free_shares = iter(distribute_equally(free_count, free_total))
    return [slot.share if slot.pinned else next(free_shares) for slot in slots]  # type: ignore[misc]
