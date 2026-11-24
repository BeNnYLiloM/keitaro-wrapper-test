let regionNames: Intl.DisplayNames | null = null;
try {
  regionNames = new Intl.DisplayNames(["ru"], { type: "region" });
} catch {
  regionNames = null;
}

export function countryName(code: string): string {
  try {
    return regionNames?.of(code) ?? code;
  } catch {
    return code;
  }
}

/** Та же формула, что на бэкенде: целые доли с суммой 100, остаток — по +1 первым. */
export function distributeEqually(count: number, total = 100): number[] {
  if (count <= 0) return [];
  const base = Math.floor(total / count);
  const remainder = total % count;
  return Array.from({ length: count }, (_, i) => (i < remainder ? base + 1 : base));
}

export type ShareSlot = { pinned: boolean; share: number | null };
export type Allocation = { shares: number[]; error: null } | { shares: null; error: string };

/**
 * Зеркало allocate_shares с бэкенда — для предпросмотра в черновике.
 * Закреплённые сохраняют долю, остальные поровну делят остаток. Окончательно считает сервер.
 */
export function allocateShares(slots: ShareSlot[], total = 100): Allocation {
  if (slots.length === 0) return { shares: null, error: "В потоке должен остаться хотя бы один оффер" };
  const pinnedTotal = slots.reduce((sum, s) => sum + (s.pinned ? (s.share ?? 0) : 0), 0);
  const freeCount = slots.filter((s) => !s.pinned).length;
  const freeTotal = total - pinnedTotal;
  if (pinnedTotal > total) {
    return { shares: null, error: `Закреплённые доли в сумме дают ${pinnedTotal}% — больше ${total}%. Открепите часть офферов` };
  }
  if (freeCount === 0 && pinnedTotal !== total) {
    return {
      shares: null,
      error: `Все офферы закреплены, а их доли в сумме ${pinnedTotal}%, не ${total}%. Открепите хотя бы один оффер, чтобы он забрал остаток`,
    };
  }
  if (freeCount > freeTotal) {
    return {
      shares: null,
      error: `Незакреплённым офферам (${freeCount} шт.) остаётся ${freeTotal}% — этого не хватит даже по 1%. Открепите часть офферов`,
    };
  }
  const free = distributeEqually(freeCount, freeTotal);
  let i = 0;
  return { shares: slots.map((s) => (s.pinned ? (s.share as number) : free[i++])), error: null };
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function refLabel(ref: { id: number; name: string | null } | null | undefined): string {
  if (!ref) return "—";
  return ref.name ? `${ref.name} (#${ref.id})` : `#${ref.id}`;
}
