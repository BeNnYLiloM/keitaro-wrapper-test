import { useEffect, useMemo, useState } from "react";
import { ApiError, api, type Offer, type Stream } from "../api";
import { allocateShares, formatDate } from "../utils";
import OfferAutocomplete from "./OfferAutocomplete";
import { useToast } from "./Toasts";

/**
 * Оффер в черновике потока:
 * - existing  — опубликован и остаётся;
 * - new       — добавлен в черновике;
 * - removed   — опубликован, в черновике помечен на удаление;
 * - archived  — удалён раньше (лежит в корзине), можно восстановить;
 * - restoring — из корзины, в черновике помечен на восстановление.
 */
type DraftStatus = "existing" | "new" | "removed" | "archived" | "restoring";

type DraftItem = {
  offer_id: number;
  name: string;
  state: string;
  status: DraftStatus;
  published: number | null; // доля, которая сейчас в Keitaro (null — оффера в потоке нет)
  archivedShare?: number; // доля на момент удаления (для офферов из корзины)
  removedAt?: string;
};

/** Офферы, которые после публикации будут в потоке. */
const IN_STREAM: DraftStatus[] = ["existing", "new", "restoring"];

function initDraft(stream: Stream): DraftItem[] {
  return [
    ...stream.offers.map((o): DraftItem => ({
      offer_id: o.offer_id,
      name: o.name,
      state: o.state,
      status: "existing",
      published: o.share,
    })),
    ...stream.removed_offers.map((o): DraftItem => ({
      offer_id: o.offer_id,
      name: o.name,
      state: o.state,
      status: "archived",
      published: null,
      archivedShare: o.share,
      removedAt: o.removed_at,
    })),
  ];
}

function pinsOf(stream: Stream): Set<number> {
  return new Set(stream.offers.filter((o) => o.pinned).map((o) => o.offer_id));
}

type Props = {
  stream: Stream;
  onPublished: (stream: Stream) => void;
  onDirtyChange: (dirty: boolean) => void;
  onActivity: () => void; // что-то сохранено (например, пин) — обновить историю
};

/**
 * Редактор офферов потока.
 * - «Добавить», «Удалить», «Восстановить» копятся в черновике и уходят в Keitaro по «Опубликовать».
 * - Пин сохраняется сразу: закрепляет текущую опубликованную долю, черновик не затрагивает.
 */
export default function OffersEditor({ stream, onPublished, onDirtyChange, onActivity }: Props) {
  const toast = useToast();
  const [items, setItems] = useState<DraftItem[]>(() => initDraft(stream));
  const [pins, setPins] = useState<Set<number>>(() => pinsOf(stream));
  const [newOffer, setNewOffer] = useState<Offer | null>(null);
  const [publishing, setPublishing] = useState(false);
  const [pinning, setPinning] = useState<number | null>(null);

  // пришло новое состояние потока (после публикации или «Обновить») — начинаем черновик заново
  useEffect(() => {
    setItems(initDraft(stream));
    setPins(pinsOf(stream));
    setNewOffer(null);
  }, [stream]);

  const isPinned = (item: DraftItem) => item.status === "existing" && pins.has(item.offer_id);

  const active = items.filter((i) => IN_STREAM.includes(i.status));
  const allocation = useMemo(
    () =>
      allocateShares(
        items
          .filter((i) => IN_STREAM.includes(i.status))
          .map((i) => ({
            pinned: i.status === "existing" && pins.has(i.offer_id),
            share: i.published,
          })),
      ),
    [items, pins],
  );
  const nextShare = new Map<number, number>();
  if (allocation.shares) active.forEach((item, idx) => nextShare.set(item.offer_id, allocation.shares![idx]));

  const added = items.filter((i) => i.status === "new").length;
  const removed = items.filter((i) => i.status === "removed").length;
  const restoring = items.filter((i) => i.status === "restoring").length;
  const dirty = added + removed + restoring > 0;

  useEffect(() => onDirtyChange(dirty), [dirty, onDirtyChange]);

  // --- действия черновика ------------------------------------------------

  const setStatus = (offerId: number, status: DraftItem["status"]) =>
    setItems((list) => list.map((i) => (i.offer_id === offerId ? { ...i, status } : i)));

  const add = () => {
    if (!newOffer) return;
    const existing = items.find((i) => i.offer_id === newOffer.id);
    if (existing?.status === "removed") {
      setStatus(newOffer.id, "existing"); // добавили помеченный на удаление — просто снимаем пометку
    } else if (existing?.status === "archived") {
      setStatus(newOffer.id, "restoring"); // добавили оффер из корзины — восстанавливаем его
    } else if (!existing) {
      setItems((list) => [
        ...list,
        { offer_id: newOffer.id, name: newOffer.name, state: "active", status: "new", published: null },
      ]);
    }
    setNewOffer(null);
  };

  const remove = (item: DraftItem) => {
    if (item.status === "new") {
      // ещё не опубликованный оффер просто убираем из черновика
      setItems((list) => list.filter((i) => i.offer_id !== item.offer_id));
    } else if (item.status === "restoring") {
      setStatus(item.offer_id, "archived"); // передумали восстанавливать — обратно в корзину
    } else {
      setStatus(item.offer_id, "removed");
    }
  };

  const restore = (item: DraftItem) =>
    setStatus(item.offer_id, item.status === "archived" ? "restoring" : "existing");

  const cancel = () => {
    setItems(initDraft(stream));
    setNewOffer(null);
  };

  const publish = async () => {
    if (!allocation.shares) return;
    setPublishing(true);
    try {
      const fresh = await api.publishOffers(stream.id, {
        offers: active.map((i) => ({ offer_id: i.offer_id })),
        base: stream.offers.map((o) => ({ offer_id: o.offer_id, share: o.share })),
      });
      toast.success(`Опубликовано. Доли: ${fresh.offers.map((o) => `${o.share}%`).join(" / ")}`);
      onPublished(fresh);
    } catch (e) {
      const message = (e as Error).message;
      // 409 — поток изменили в Keitaro, текст уже говорит, что делать
      toast.error(e instanceof ApiError && e.status === 409 ? message : `Не опубликовано: ${message}`);
    } finally {
      setPublishing(false);
    }
  };

  // --- пин: сохраняется сразу --------------------------------------------

  const togglePin = async (item: DraftItem) => {
    const pin = !pins.has(item.offer_id);
    setPinning(item.offer_id);
    try {
      const fresh = pin
        ? await api.pinOffer(stream.id, item.offer_id)
        : await api.unpinOffer(stream.id, item.offer_id);
      // берём только закрепления — черновик (добавленные/удалённые) не трогаем
      setPins(pinsOf(fresh));
      toast.success(
        pin ? `Доля оффера #${item.offer_id} закреплена: ${item.published}%` : `Доля оффера #${item.offer_id} откреплена`,
      );
      onActivity();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setPinning(null);
    }
  };

  // --- отображение -------------------------------------------------------

  const summary = [
    added && `добавлено: ${added}`,
    restoring && `к восстановлению: ${restoring}`,
    removed && `к удалению: ${removed}`,
  ]
    .filter(Boolean)
    .join(" · ");
  const archivedItems = items.filter((i) => i.status === "archived");

  return (
    <div className="offers-editor">
      {dirty && (
        <div className={`draft-bar ${allocation.error ? "has-error" : ""}`}>
          <div>
            <b>Есть неопубликованные изменения</b>
            <span className="draft-summary">{summary}</span>
            {allocation.error && <div className="draft-error">{allocation.error}</div>}
          </div>
          <div className="toolbar">
            <button className="btn" onClick={cancel} disabled={publishing}>
              Отменить
            </button>
            <button className="btn btn-primary" onClick={publish} disabled={publishing || !allocation.shares}>
              {publishing ? "Публикуем…" : "Опубликовать"}
            </button>
          </div>
        </div>
      )}

      <table className="table offers-table">
        <thead>
          <tr>
            <th style={{ width: 80 }}>ID</th>
            <th>Оффер</th>
            <th style={{ width: 330 }}>Доля</th>
            <th style={{ width: 90 }}>Статус</th>
            <th style={{ width: 130 }} />
          </tr>
        </thead>
        <tbody>
          {items.filter((i) => i.status !== "archived").map((item) => {
            const isRemoved = item.status === "removed";
            const pinned = isPinned(item);
            const next = isRemoved ? 0 : nextShare.get(item.offer_id);
            const shown = next ?? item.published ?? 0;
            const changed = next !== undefined && next !== item.published;
            const pinDisabledReason =
              item.status === "new" || item.status === "restoring"
                ? "Сначала опубликуйте оффер"
                : isRemoved
                  ? "Оффер помечен на удаление"
                  : null;
            return (
              <tr key={item.offer_id} className={`offer-row offer-${item.status}`}>
                <td className="mono">{item.offer_id}</td>
                <td>
                  <span className="offer-title">{item.name}</span>
                  {item.status === "new" && <span className="badge badge-new">новый</span>}
                  {item.status === "restoring" && <span className="badge badge-new">будет восстановлен</span>}
                  {isRemoved && <span className="badge badge-removed">будет удалён</span>}
                </td>
                <td>
                  <div className="share">
                    <div className="share-bar">
                      <div className={`share-fill ${pinned ? "share-fill-pinned" : ""}`} style={{ width: `${shown}%` }} />
                    </div>
                    {item.published !== null && (
                      <span className={`mono share-num ${changed ? "share-old" : ""}`}>{item.published}%</span>
                    )}
                    {changed && <span className="mono share-next">→ {next}%</span>}
                    <button
                      type="button"
                      className={`pin-btn ${pinned ? "pinned" : ""}`}
                      disabled={pinDisabledReason !== null || pinning !== null || publishing}
                      onClick={() => togglePin(item)}
                      title={pinDisabledReason ?? (pinned ? `Открепить долю (${item.published}%)` : `Закрепить долю ${item.published}%`)}
                      aria-label={pinned ? "Открепить долю" : "Закрепить долю"}
                      aria-pressed={pinned}
                    >
                      <PinIcon filled={pinned} />
                    </button>
                  </div>
                </td>
                <td>
                  <span className={`badge ${item.state === "active" ? "badge-green" : ""}`}>{item.state}</span>
                </td>
                <td className="actions">
                  {isRemoved ? (
                    <button className="btn btn-sm" onClick={() => restore(item)} disabled={publishing}>
                      Восстановить
                    </button>
                  ) : (
                    <button className="btn btn-sm btn-danger" onClick={() => remove(item)} disabled={publishing}>
                      Удалить
                    </button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
        <tfoot>
          <tr>
            <td />
            <td className="muted">Итого: {active.length} офф.</td>
            <td className="mono">
              {allocation.shares ? `${allocation.shares.reduce((a, b) => a + b, 0)}%` : <span className="error-text">—</span>}
            </td>
            <td colSpan={2} />
          </tr>
        </tfoot>
      </table>

      <div className="add-offer">
        <div className="grow">
          <OfferAutocomplete
            value={newOffer}
            onChange={setNewOffer}
            excludeIds={active.map((i) => i.offer_id)}
            placeholder="Добавить оффер: название или id"
            disabled={publishing}
          />
        </div>
        <button className="btn" disabled={!newOffer || publishing} onClick={add}>
          Добавить
        </button>
      </div>

      {archivedItems.length > 0 && (
        <div className="archive">
          <div className="archive-head">Удалённые офферы — можно восстановить ({archivedItems.length})</div>
          <table className="table offers-table">
            <tbody>
              {archivedItems.map((item) => (
                <tr key={item.offer_id} className="offer-row offer-archived">
                  <td className="mono" style={{ width: 80 }}>
                    {item.offer_id}
                  </td>
                  <td>
                    <span className="offer-title">{item.name}</span>
                  </td>
                  <td className="muted small" style={{ width: 330 }}>
                    была доля {item.archivedShare}%{item.removedAt ? ` · ${formatDate(item.removedAt)}` : ""}
                  </td>
                  <td style={{ width: 90 }}>
                    <span className="badge badge-removed-state" title={`Статус до удаления: ${item.state}`}>
                      удалён
                    </span>
                  </td>
                  <td className="actions" style={{ width: 130 }}>
                    <button className="btn btn-sm" onClick={() => restore(item)} disabled={publishing}>
                      Восстановить
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="muted small">
        Добавление, удаление и восстановление применяются в Keitaro после «Опубликовать». Удалённые офферы остаются в списке ниже — их можно вернуть в любой момент. Доли делятся поровну; закреплённые
        (<PinIcon filled small />) сохраняют свой процент, остальные делят остаток. Пин сохраняется сразу.
      </p>
    </div>
  );
}

function PinIcon({ filled, small }: { filled?: boolean; small?: boolean }) {
  const size = small ? 12 : 16;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={filled ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      style={small ? { verticalAlign: "-1px" } : undefined}
    >
      <path d="M12 17v5" />
      <path d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z" />
    </svg>
  );
}
