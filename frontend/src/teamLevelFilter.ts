import type { Level } from "./api";

const GIRLS_MARK = /\b(N10|N12|N15|N16|N20)\b|tytöt/i;

function norm(s: string): string {
  return s.toLowerCase();
}

/** All U-age tokens in the name (e.g. U18, U20). */
function uAgesIn(name: string): string[] {
  return name.match(/\bU(9|10|11|12|13|14|15|16|17|18|20)\b/gi) ?? [];
}

/** True when the name has no U-age, or only the given band (e.g. only U18). */
function ageBandOrGeneric(name: string, band: string): boolean {
  const tags = uAgesIn(name);
  if (tags.length === 0) return true;
  const b = band.toLowerCase();
  return tags.every((t) => t.toLowerCase() === b);
}

/** Youth league row must carry the age band in the name (excludes adult / harraste lines). */
function youthStrictBand(name: string, band: string): boolean {
  const tags = uAgesIn(name);
  if (tags.length === 0) return false;
  const b = band.toLowerCase();
  return tags.every((t) => t.toLowerCase() === b);
}

function nationalLoose(name: string): boolean {
  const n = norm(name);
  return /national|maajoukkue|team finland|leijonat|suomi\s*u\d+/i.test(n);
}

/** Liiga–V-divisioona: men's senior rep only, no junior / women's lines. */
function menUpperLeague(name: string): boolean {
  const n = norm(name);
  if (uAgesIn(name).length > 0) return false;
  if (GIRLS_MARK.test(name)) return false;
  if (/juniori|jg akatemia|gimmat/i.test(n)) return false;
  if ((/naiset|naisten/i.test(n) || /\bn\d{2}\b/i.test(n)) && !/miehet/i.test(n)) return false;
  if (/\btytöt\b/i.test(n) && !/miehet/i.test(n)) return false;
  if (/miehet/i.test(n) && /edustus/i.test(n)) return true;
  if (/miehet/i.test(n) && !/naiset|naisten|tytöt/i.test(n)) return true;
  if (/edustus/i.test(n) && !/naiset|naisten|tytöt|\bn1[0-9]\b/i.test(n)) return true;
  return false;
}

function menHarraste(name: string): boolean {
  if (uAgesIn(name).length > 0) return false;
  const n = norm(name);
  return /harraste|hobby|recreational/i.test(n) || /senior/i.test(n);
}

function menSeniorisarja(name: string): boolean {
  if (uAgesIn(name).length > 0) return false;
  return /senior/i.test(name);
}

/** Auroraliiga (stored under Men): women's pro naming. */
function auroraliiga(name: string): boolean {
  const n = norm(name);
  if (/\bmiehet\b/i.test(name) && !/naiset|naisten|tytöt/i.test(n)) return false;
  if (uAgesIn(name).length > 0 && !/naiset|naisten|tytöt|\bn\d/i.test(n)) return false;
  return /naiset|naisten|aurora|tytöt|\bn20\b|\bn16\b|\bn15\b|\bn12\b|\bn10\b|women/i.test(name);
}

function womenLeague(name: string): boolean {
  const n = norm(name);
  if (/\bmiehet\b/i.test(name) && !/naiset|naisten/i.test(n)) return false;
  if (/rf\s+u\d+/i.test(n)) return false;
  if (uAgesIn(name).length > 0 && !/naiset|naisten|tytöt|\bn\d|women/i.test(n)) return false;
  return /naiset|naisten|tytöt|\bn20\b|\bn16\b|\bn15\b|\bn12\b|\bn10\b|women|aurora/i.test(name);
}

function nBand(name: string, token: string): boolean {
  const t = token.toLowerCase();
  return norm(name).includes(t) || new RegExp(`\\b${token}\\b`, "i").test(name);
}

function u15ForLevelId(name: string, id: string): boolean {
  if (!ageBandOrGeneric(name, "U15")) return false;
  const tags = uAgesIn(name);
  const n = norm(name);
  if (tags.length === 0) return true;
  if (id === "93") return n.includes("sininen") || /\bu15\b.*\ba\b/i.test(n);
  if (id === "94") return n.includes("valkoinen") || /\bu15\b.*\bb\b/i.test(n);
  if (id === "95") return n.includes("keltainen") || /\bu15\b.*\bc\b/i.test(n);
  return true;
}

function u14ForLevelId(name: string, id: string): boolean {
  if (!ageBandOrGeneric(name, "U14")) return false;
  const tags = uAgesIn(name);
  const n = norm(name);
  if (tags.length === 0) return true;
  if (id === "97") return n.includes("sininen") || /\bu14\b.*\ba\b/i.test(n);
  if (id === "98") return n.includes("valkoinen") || /\bu14\b.*\bb\b/i.test(n);
  if (id === "99") return /\bu14\b.*\bc\b/i.test(n) || n.includes(" u14 c");
  return true;
}

function u13ForLevelId(name: string, id: string): boolean {
  if (!ageBandOrGeneric(name, "U13")) return false;
  const tags = uAgesIn(name);
  const n = norm(name);
  if (tags.length === 0) return true;
  if (id === "101") return n.includes("sininen");
  if (id === "102") return n.includes("valkoinen");
  return true;
}

/**
 * Whether a team search row fits the league level selected in the UI.
 * When level is missing or "all levels", every team is shown.
 */
export function teamMatchesSelectedLevel(teamName: string, level: Level | null | undefined): boolean {
  if (!level || level.id === "0") return true;

  const name = teamName;
  const g = level.group;
  const id = level.id;

  if (g === "Men") {
    if (["64", "65", "66", "67", "68", "69", "70"].includes(id)) return menUpperLeague(name);
    if (id === "71") return menHarraste(name);
    if (id === "72") return menSeniorisarja(name);
    if (id === "73") return auroraliiga(name);
    return true;
  }

  if (g === "Women") {
    if (["74", "75"].includes(id)) return womenLeague(name);
    if (id === "113") return nBand(name, "N20");
    if (id === "117") return nBand(name, "N16");
    if (id === "119") return /\bN15\b|n15|tytöt/i.test(name);
    if (id === "120") return /\bN12\b|n12|tytöt/i.test(name);
    if (id === "121") return /\bN10\b|n10|tytöt/i.test(name);
    if (id === "133") return /national|maajoukkue|team finland|naisten.*team|leijonat/i.test(name) || womenLeague(name);
    if (id === "134") return /u18|n18|national|maajoukkue/i.test(name) || womenLeague(name);
    return womenLeague(name);
  }

  if (g === "U20") {
    if (id === "128") return youthStrictBand(name, "U20") || nationalLoose(name);
    return youthStrictBand(name, "U20");
  }
  if (g === "U18") {
    if (id === "130") return youthStrictBand(name, "U18") || nationalLoose(name);
    return youthStrictBand(name, "U18");
  }
  if (g === "U16") {
    if (id === "131") return youthStrictBand(name, "U17") || youthStrictBand(name, "U16") || nationalLoose(name);
    if (id === "132") return youthStrictBand(name, "U16") || nationalLoose(name);
    return youthStrictBand(name, "U16");
  }

  if (g === "U15") return u15ForLevelId(name, id);
  if (g === "U14") return u14ForLevelId(name, id);
  if (g === "U13") return u13ForLevelId(name, id);

  if (g === "U12–U11") {
    if (id === "145") return ageBandOrGeneric(name, "U12");
    if (id === "146") return ageBandOrGeneric(name, "U11");
    return true;
  }

  if (g === "National" || g === "Other") return true;

  return true;
}
