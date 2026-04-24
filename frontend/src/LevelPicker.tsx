import { useState, useEffect, useRef, useMemo } from "react";
import type { Level } from "./api";

interface Props {
  levels: Level[];
  value: string;          // selected level id, "0" = all
  onChange: (id: string) => void;
  disabled?: boolean;
}

/** Preferred display order for groups */
const GROUP_ORDER = [
  "Men", "Women", "U20", "U18", "U16", "U15", "U14", "U13",
  "U12–U11", "National", "Other",
];

export default function LevelPicker({ levels, value, onChange, disabled }: Props) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    const h = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node))
        setOpen(false);
    };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  const selectedLevel = levels.find((l) => l.id === value);
  const displayLabel = value === "0" ? "All levels" : (selectedLevel?.name ?? value);

  // Filter + group levels by query
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? levels.filter((l) =>
      l.name.toLowerCase().includes(q) || l.group.toLowerCase().includes(q)
    ) : levels;
  }, [levels, query]);

  const groups: Record<string, Level[]> = {};
  for (const l of filtered) {
    (groups[l.group] ||= []).push(l);
  }
  const orderedGroups = GROUP_ORDER.filter((g) => groups[g]);

  const select = (id: string) => {
    onChange(id);
    setOpen(false);
    setQuery("");
  };

  return (
    <div className="level-picker" ref={containerRef}>
      <button
        type="button"
        className={`level-picker-trigger ${open ? "open" : ""}`}
        onClick={() => !disabled && setOpen((v) => !v)}
        disabled={disabled}
      >
        <span className="level-picker-value">{displayLabel}</span>
        <span className="level-picker-chevron">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="level-picker-dropdown">
          <div className="level-picker-search-wrap">
            <input
              autoFocus
              type="text"
              placeholder="Filter levels…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="level-picker-search"
            />
          </div>

          <ul className="level-picker-list">
            {/* All levels option */}
            {!query && (
              <li
                className={`level-picker-item ${value === "0" ? "selected" : ""}`}
                onMouseDown={() => select("0")}
              >
                All levels
              </li>
            )}

            {orderedGroups.map((group) => (
              <li key={group} className="level-picker-group">
                <div className="level-picker-group-label">{group}</div>
                <ul>
                  {groups[group].map((l) => (
                    <li
                      key={l.id}
                      className={`level-picker-item ${l.id === value ? "selected" : ""}`}
                      onMouseDown={() => select(l.id)}
                    >
                      {l.name}
                    </li>
                  ))}
                </ul>
              </li>
            ))}

            {orderedGroups.length === 0 && (
              <li className="level-picker-empty">No matching levels</li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
