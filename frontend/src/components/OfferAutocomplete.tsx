import { useEffect, useRef, useState } from "react";
import { api, type Offer } from "../api";

type Props = {
  value: Offer | null;
  onChange: (offer: Offer | null) => void;
  excludeIds?: number[];
  placeholder?: string;
  disabled?: boolean;
};

/** Поиск оффера по названию или id с подсказками (debounce + отмена устаревших запросов). */
export default function OfferAutocomplete({ value, onChange, excludeIds = [], placeholder, disabled }: Props) {
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<Offer[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState(0);
  const boxRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setLoading(true);
      setError(null);
      try {
        const found = await api.searchOffers(query, controller.signal);
        setItems(found);
        setActive(0);
      } catch (e) {
        if ((e as Error).name !== "AbortError") setError((e as Error).message);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }, 250);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query, open]);

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  const visible = items.filter((o) => !excludeIds.includes(o.id));

  const select = (offer: Offer) => {
    onChange(offer);
    setQuery("");
    setOpen(false);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActive((i) => Math.min(i + 1, visible.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      if (open && visible[active]) {
        e.preventDefault();
        select(visible[active]);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  if (value) {
    return (
      <div className="selected-offer">
        <span className="offer-id">#{value.id}</span>
        <span className="offer-name">{value.name}</span>
        {!disabled && (
          <button
            type="button"
            className="icon-btn"
            title="Выбрать другой оффер"
            onClick={() => {
              onChange(null);
              setTimeout(() => inputRef.current?.focus());
            }}
          >
            ×
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="autocomplete" ref={boxRef}>
      <input
        ref={inputRef}
        value={query}
        disabled={disabled}
        placeholder={placeholder ?? "Начните вводить название или id оффера"}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
      />
      {open && (
        <div className="dropdown">
          {loading && <div className="dropdown-hint">Поиск…</div>}
          {error && <div className="dropdown-hint error-text">{error}</div>}
          {!loading && !error && visible.length === 0 && <div className="dropdown-hint">Ничего не найдено</div>}
          {visible.map((offer, i) => (
            <div
              key={offer.id}
              className={`dropdown-item ${i === active ? "active" : ""}`}
              onMouseEnter={() => setActive(i)}
              onMouseDown={(e) => {
                e.preventDefault();
                select(offer);
              }}
            >
              <span className="offer-id">#{offer.id}</span>
              <span className="offer-name">{offer.name}</span>
              {offer.country && offer.country.length > 0 && (
                <span className="offer-geo">{offer.country.slice(0, 4).join(", ")}</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
