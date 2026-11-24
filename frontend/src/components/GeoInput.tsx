import { useMemo, useRef, useState } from "react";
import { countryName } from "../utils";

type Props = {
  value: string[];
  onChange: (codes: string[]) => void;
  countries: string[];
  disabled?: boolean;
};

/** Ввод стран чипами: можно выбирать из подсказок или вставить строку вида "MX,AU,RO". */
export default function GeoInput({ value, onChange, countries, disabled }: Props) {
  const [text, setText] = useState("");
  const [focused, setFocused] = useState(false);
  const [invalid, setInvalid] = useState<string[]>([]);
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const known = useMemo(() => new Set(countries), [countries]);

  const suggestions = useMemo(() => {
    const q = text.trim().toLowerCase();
    if (!q) return [];
    return countries
      .filter((c) => !value.includes(c))
      .filter((c) => c.toLowerCase().startsWith(q) || countryName(c).toLowerCase().includes(q))
      .sort((a, b) => Number(!a.toLowerCase().startsWith(q)) - Number(!b.toLowerCase().startsWith(q)))
      .slice(0, 8);
  }, [text, countries, value]);

  /** Разбирает введённый текст на коды; неизвестные оставляет в поле и подсвечивает. */
  const commit = (raw: string) => {
    const tokens = raw
      .split(/[\s,;]+/)
      .map((t) => t.trim().toUpperCase())
      .filter(Boolean);
    if (tokens.length === 0) return;
    const good = tokens.filter((t) => known.has(t));
    const bad = tokens.filter((t) => !known.has(t));
    const next = [...value];
    for (const code of good) if (!next.includes(code)) next.push(code);
    onChange(next);
    setInvalid(bad);
    setText(bad.join(","));
  };

  const add = (code: string) => {
    if (!value.includes(code)) onChange([...value, code]);
    setText("");
    setInvalid([]);
    inputRef.current?.focus();
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown" && suggestions.length) {
      e.preventDefault();
      setActive((i) => Math.min(i + 1, suggestions.length - 1));
    } else if (e.key === "ArrowUp" && suggestions.length) {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" || e.key === "," || e.key === " " || e.key === "Tab") {
      if (!text.trim()) return;
      const exact = text.trim().toUpperCase();
      if (e.key === "Enter" && suggestions[active] && !known.has(exact)) {
        e.preventDefault();
        add(suggestions[active]);
        return;
      }
      if (e.key !== "Tab") e.preventDefault();
      commit(text);
    } else if (e.key === "Backspace" && !text && value.length) {
      onChange(value.slice(0, -1));
    }
  };

  return (
    <div className="geo-wrap">
      <div
        className={`chips-input ${focused ? "focused" : ""} ${invalid.length ? "has-error" : ""}`}
        onClick={() => inputRef.current?.focus()}
      >
        {value.map((code) => (
          <span key={code} className="chip" title={countryName(code)}>
            {code}
            {!disabled && (
              <button
                type="button"
                className="chip-x"
                onClick={(e) => {
                  e.stopPropagation();
                  onChange(value.filter((c) => c !== code));
                }}
              >
                ×
              </button>
            )}
          </span>
        ))}
        <input
          ref={inputRef}
          value={text}
          disabled={disabled}
          placeholder={value.length ? "" : "MX, AU, RO…"}
          onChange={(e) => {
            const v = e.target.value;
            if (/[,;\s]/.test(v)) {
              commit(v);
            } else {
              setText(v);
              setInvalid([]);
              setActive(0);
            }
          }}
          onPaste={(e) => {
            e.preventDefault();
            commit(text + e.clipboardData.getData("text"));
          }}
          onKeyDown={onKeyDown}
          onFocus={() => setFocused(true)}
          onBlur={() => {
            setFocused(false);
            if (text.trim()) commit(text);
          }}
        />
      </div>
      {focused && suggestions.length > 0 && (
        <div className="dropdown">
          {suggestions.map((code, i) => (
            <div
              key={code}
              className={`dropdown-item ${i === active ? "active" : ""}`}
              onMouseEnter={() => setActive(i)}
              onMouseDown={(e) => {
                e.preventDefault();
                add(code);
              }}
            >
              <span className="offer-id">{code}</span>
              <span className="offer-name">{countryName(code)}</span>
            </div>
          ))}
        </div>
      )}
      {invalid.length > 0 && <div className="field-error">Неизвестные коды стран: {invalid.join(", ")}</div>}
      {value.length > 0 && (
        <div className="field-hint">{value.map((c) => countryName(c)).join(", ")}</div>
      )}
    </div>
  );
}
