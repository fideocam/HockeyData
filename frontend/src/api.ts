const BASE = import.meta.env.VITE_API_URL ?? "";

export interface Level {
  id: string;
  name: string;
  group: string;
}

export interface TeamResult {
  TeamID: string;
  TeamName: string;
  AssociationAbbrv: string;
}

/** Response from /api/team-from-id (joukkuekortti ?teamid=…) */
export interface TeamFromIdResponse {
  teamid: string;
  teamName: string | null;
  teamAbbrv: string | null;
  levelId: string | null;
  associationId: string | null;
  associationName: string | null;
  statGroupName: string | null;
}

export interface SankeyLink {
  source: number;
  target: number;
  value: number;
  label: string;
  players: string[];
}

export interface PlayerFlow {
  person_id: string;
  first_name: string;
  last_name: string;
  source_team: string;
  source_season: string;
  target_team: string;
  target_season: string;
  position: string;
}

export interface SankeyResponse {
  nodes: string[];
  links: SankeyLink[];
  focal_team: string;
  /** Official team name when cohort was loaded via joukkuekortti team id */
  focal_team_display?: string;
  resolved_team_id?: string;
  resolved_level_id?: string;
  mode: string;
  player_count: number;
  searched_count: number;
  node_x: number[];
  node_y: number[];
  node_meta?: SankeyNodeMeta[];
  flows: PlayerFlow[];
}

export interface SankeyNodeMeta {
  season?: string;
  season_label?: string;
  team?: string;
  level_id?: string;
  level_name?: string;
  team_id?: string;
  players?: SankeyNodePlayer[];
}

export interface SankeyNodePlayer {
  id: string;
  name: string;
}

export interface RetentionOrg {
  org: string;
  total: number;
  professional: number;
  competitive: number;
  active: number;
  recreational: number;
  no_record: number;
  continued_rate: number;
  high_level_rate: number;
  professional_rate: number;
  competitive_rate: number;
  active_rate: number;
  recreational_rate: number;
  no_record_rate: number;
  professional_names: string[];
  competitive_names: string[];
  active_names: string[];
  recreational_names: string[];
  no_record_names: string[];
}

export interface RetentionResponse {
  level: string;
  season_from: string;
  season_to: string;
  total_players_fetched: number;
  total_orgs: number;
  capped: boolean;
  orgs: RetentionOrg[];
}

export interface PlayerNetworkGame {
  date: string;
  game_id: string;
  home: string;
  away: string;
  relation: string;
}

export interface PlayerNetworkRow {
  person_id: string;
  link_id: string;
  name: string;
  score: number;
  level_id: string;
  level_name: string;
  ranking_reasons: string[];
  best_season: string;
  best_teams: string[];
  encounter_games: number;
  encounter_teams: string[];
  encounter_seasons: string[];
  sample_games: PlayerNetworkGame[];
}

export interface PlayerNetworkResponse {
  player: {
    name: string;
    person_id: string;
    link_id: string;
    association: string;
  };
  candidates: Array<{
    PersonID: string;
    LinkID: string;
    LastName: string;
    FirstName: string;
    Association: string;
  }>;
  summary: {
    seasons: string[];
    scanned_games: number;
    scanned_team_seasons: number;
    missing_game_rosters: number;
    method: string;
  };
  best_with: PlayerNetworkRow[];
  best_against: PlayerNetworkRow[];
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? res.statusText);
  }
  return res.json();
}

export const api = {
  levels: (season?: string) =>
    get<Level[]>(`/api/levels${season ? `?season=${encodeURIComponent(season)}` : ""}`),

  searchTeams: (q: string) =>
    get<TeamResult[]>(`/api/search-teams?q=${encodeURIComponent(q)}`),

  playerNetwork: (q: string, seasonsBack = 20, maxGames = 250) =>
    get<PlayerNetworkResponse>(
      `/api/player-network?q=${encodeURIComponent(q)}&seasons_back=${seasonsBack}&max_games=${maxGames}`
    ),

  teamFromId: (teamid: string) =>
    get<TeamFromIdResponse>(`/api/team-from-id?teamid=${encodeURIComponent(teamid.trim())}`),

  sankeyToCurrent: (
    team: string,
    season: string,
    level: string,
    weight: "players" | "games" = "players",
    teamId?: string,
    cohort?: SankeyNodePlayer[],
  ) => {
    const q = new URLSearchParams({ team, season, level, weight });
    if (teamId?.trim()) q.set("team_id", teamId.trim());
    if (cohort?.length) q.set("cohort", JSON.stringify(cohort));
    return get<SankeyResponse>(`/api/sankey/to-current?${q}`);
  },

  sankeyFromPrevious: (
    team: string,
    season: string,
    level: string,
    weight: "players" | "games" = "players",
    teamId?: string,
    cohort?: SankeyNodePlayer[],
  ) => {
    const q = new URLSearchParams({ team, season, level, weight });
    if (teamId?.trim()) q.set("team_id", teamId.trim());
    if (cohort?.length) q.set("cohort", JSON.stringify(cohort));
    return get<SankeyResponse>(`/api/sankey/from-previous?${q}`);
  },

  retention: (level: string, seasonFrom: string, seasonTo: string, minDataPoints: number) =>
    get<RetentionResponse>(
      `/api/retention?level=${level}&season_from=${seasonFrom}&season_to=${seasonTo}&min_data_points=${minDataPoints}`
    ),

  sankeyCareerPaths: (
    team: string,
    season: string,
    level: string,
    direction: "to_current" | "from_previous",
    maxSeasonsBack = 10,
    teamId?: string,
    cohort?: SankeyNodePlayer[],
  ) => {
    const q = new URLSearchParams({
      team,
      season,
      level,
      direction,
      max_seasons_back: String(maxSeasonsBack),
    });
    if (teamId?.trim()) q.set("team_id", teamId.trim());
    if (cohort?.length) q.set("cohort", JSON.stringify(cohort));
    return get<SankeyResponse>(`/api/sankey/career-paths?${q}`);
  },
};
