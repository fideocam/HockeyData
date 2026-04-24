import { useState, useEffect, useRef, useCallback } from "react";
import { api } from "./api";
import type { Level, TeamResult } from "./api";
import { teamMatchesSelectedLevel } from "./teamLevelFilter";

/** Abbreviation plus optional joukkuekortti TeamID when the user picks a search row (enables full roster). */
export type TeamSearchPick = { abbr: string; joukkueTeamId?: string };

interface Props {
  value: string;
  /** Highlights the dropdown row for this joukkuekortti id (same abbr can appear on several lines). */
  selectedTeamId?: string;
  onChange: (pick: TeamSearchPick) => void;
  disabled?: boolean;
  /** When set (and not "all levels"), search results are restricted to teams that fit this level. */
  level: Level | null;
}

function useDebounce<T>(value: T, delay: number): T {
  const [d, setD] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setD(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return d;
}

/**
 * Returns a score for sorting (lower = shown first) and a group key for dedup.
 * We keep one entry per (org, age-group) combination so the user can see and
 * pick youth teams separately from the adult team of the same organisation.
 */
function categorise(t: TeamResult): { score: number; groupKey: string } {
  const name = t.TeamName.toLowerCase();
  const abbr = t.AssociationAbbrv;

  // Age-group buckets — ordered from most to least competitive
  if (name.includes("miehet edustus") || name.includes("men"))
    return { score: 0, groupKey: `${abbr}-men` };
  if ((name.includes("edustus") && !name.includes("nainen") && !name.includes("nais")))
    return { score: 1, groupKey: `${abbr}-edustus` };
  // Same club often has several U18/U16 lines (e.g. II-div vs III-div). TeamID keeps each row.
  if (name.includes("u20")) return { score: 2, groupKey: `${abbr}-u20-${t.TeamID}` };
  if (name.includes("u18")) return { score: 3, groupKey: `${abbr}-u18-${t.TeamID}` };
  if (name.includes("u16")) return { score: 4, groupKey: `${abbr}-u16-${t.TeamID}` };
  if (name.includes("u15")) return { score: 5, groupKey: `${abbr}-u15-${t.TeamID}` };
  if (name.includes("u14")) return { score: 6, groupKey: `${abbr}-u14-${t.TeamID}` };
  if (name.includes("u13")) return { score: 7, groupKey: `${abbr}-u13-${t.TeamID}` };
  if (name.includes("u12") || name.includes("u11") || name.includes("u10"))
    return { score: 8, groupKey: `${abbr}-youth-${t.TeamID}` };
  if (name.includes("naiset edustus") || name.includes("naiset") || name.includes("nainen"))
    return { score: 9, groupKey: `${abbr}-women` };
  if (name.includes("harraste") || name.includes("senior"))
    return { score: 10, groupKey: `${abbr}-rec` };
  // Unclassified: keep as unique entry
  return { score: 5, groupKey: `${abbr}-${t.TeamID}` };
}

export default function TeamSearch({ value, selectedTeamId, onChange, disabled, level }: Props) {
  const [query, setQuery] = useState(value);
  const [results, setResults] = useState<TeamResult[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const debouncedQuery = useDebounce(query, 280);

  useEffect(() => { setQuery(value); }, [value]);

  useEffect(() => {
    if (debouncedQuery.length < 2) { setResults([]); return; }
    let cancelled = false;
    setLoading(true);
    api.searchTeams(debouncedQuery)
      .then((res) => {
        if (cancelled) return;
        const levelFiltered = res.filter((t) => teamMatchesSelectedLevel(t.TeamName, level));
        // Sort by score, then deduplicate by (org, age-group) — keeps one entry
        // per age group per organisation so youth teams stay visible.
        const tagged = levelFiltered
          .filter((t) => t.AssociationAbbrv)
          .map((t) => ({ t, ...categorise(t) }))
          .sort((a, b) => a.score - b.score);

        const seen = new Set<string>();
        const unique: TeamResult[] = [];
        for (const { t, groupKey } of tagged) {
          if (!seen.has(groupKey)) {
            seen.add(groupKey);
            unique.push(t);
          }
        }
        setResults(unique.slice(0, 28));
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [debouncedQuery, level]);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node))
        setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const select = useCallback((t: TeamResult) => {
    setQuery(t.AssociationAbbrv);
    onChange({ abbr: t.AssociationAbbrv, joukkueTeamId: t.TeamID });
    setOpen(false);
    setResults([]);
  }, [onChange]);

  const handleInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = e.target.value;
    setQuery(v);
    onChange({ abbr: v });
    setOpen(true);
  };

  return (
    <div className="team-search" ref={containerRef}>
      <div className="team-search-input-wrap">
        <input
          type="search"
          name="hd-club-team-lookup"
          enterKeyHint="search"
          placeholder={
            level && level.id !== "0"
              ? "Team name or abbreviation (matches selected level)…"
              : "Type team name or abbreviation…"
          }
          value={query}
          onChange={handleInput}
          onFocus={() => results.length > 0 && setOpen(true)}
          disabled={disabled}
          autoComplete="off"
          autoCorrect="off"
          autoCapitalize="none"
          spellCheck={false}
          data-1p-ignore
          data-lpignore="true"
          data-form-type="other"
        />
        {loading && <span className="team-search-spinner" />}
      </div>
      {open && results.length > 0 && (
        <ul className="team-search-dropdown">
          {results.map((t) => (
            <li
              key={t.TeamID}
              className={`team-search-item ${
                t.AssociationAbbrv === value && (!selectedTeamId || selectedTeamId === t.TeamID)
                  ? "selected"
                  : ""
              }`}
              onMouseDown={() => select(t)}
            >
              <span className="abbr">{t.AssociationAbbrv}</span>
              <span className="full-name">{t.TeamName}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
