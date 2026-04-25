/*
Power Query M import for HockeyData Sankey -> Power BI Sankey
=============================================================

Create these parameters in Power BI first:

  ApiBaseUrl        text  http://localhost:8000
  SankeyEndpoint    text  /api/sankey/career-paths
  Team              text  K-Kissat
  Season            text  2025
  Level             text  89
  Direction         text  to_current
  TeamId            text  940166431

For one-step endpoints, use one of:
  /api/sankey/to-current
  /api/sankey/from-previous

For career-paths, Direction must be:
  to_current
  from_previous

Then create the queries below. The DAX file expects the table query names:
  SankeyNodesRaw
  SankeyLinksRaw
  SankeyLinkPlayersRaw
  SankeyFlowsRaw
*/


// Query name: SankeyResponse
let
    BaseUrl = Text.TrimEnd(ApiBaseUrl, "/"),
    Endpoint = if Text.StartsWith(SankeyEndpoint, "/") then SankeyEndpoint else "/" & SankeyEndpoint,
    QueryBase = [
        team = Team,
        season = Season,
        level = Level
    ],
    QueryWithDirection =
        if Text.EndsWith(Endpoint, "/career-paths") or Text.Contains(Endpoint, "career-paths")
        then Record.AddField(QueryBase, "direction", Direction)
        else QueryBase,
    QueryWithTeamId =
        if Text.Length(Text.Trim(TeamId)) > 0
        then Record.AddField(QueryWithDirection, "team_id", TeamId)
        else QueryWithDirection,
    Source = Json.Document(
        Web.Contents(
            BaseUrl,
            [
                RelativePath = Text.TrimStart(Endpoint, "/"),
                Query = QueryWithTeamId
            ]
        )
    )
in
    Source


// Query name: SankeyNodesRaw
let
    Response = SankeyResponse,
    Nodes = try Response[nodes] otherwise {},
    NodeX = try Response[node_x] otherwise {},
    NodeY = try Response[node_y] otherwise {},
    NodeIndexes = if List.Count(Nodes) > 0 then {0..List.Count(Nodes)-1} else {},
    NodeRows =
        List.Transform(
            NodeIndexes,
            (i) => [
                NodeIndex = i,
                NodeName = Text.From(Nodes{i}),
                NodeX = if i < List.Count(NodeX) then Number.From(NodeX{i}) else null,
                NodeY = if i < List.Count(NodeY) then Number.From(NodeY{i}) else null
            ]
        ),
    TableOut = Table.FromRecords(
        NodeRows,
        type table [
            NodeIndex = Int64.Type,
            NodeName = text,
            NodeX = nullable number,
            NodeY = nullable number
        ]
    )
in
    TableOut


// Query name: SankeyLinksRaw
let
    Response = SankeyResponse,
    Links = try Response[links] otherwise {},
    LinkIndexes = if List.Count(Links) > 0 then {0..List.Count(Links)-1} else {},
    LinkRows =
        List.Transform(
            LinkIndexes,
            (i) =>
                let
                    L = Links{i}
                in
                    [
                        LinkIndex = i,
                        SourceIndex = Int64.From(L[source]),
                        TargetIndex = Int64.From(L[target]),
                        Weight = Number.From(L[value]),
                        LinkLabel = Text.From(try L[label] otherwise "")
                    ]
        ),
    TableOut = Table.FromRecords(
        LinkRows,
        type table [
            LinkIndex = Int64.Type,
            SourceIndex = Int64.Type,
            TargetIndex = Int64.Type,
            Weight = number,
            LinkLabel = text
        ]
    )
in
    TableOut


// Query name: SankeyLinkPlayersRaw
let
    Response = SankeyResponse,
    Links = try Response[links] otherwise {},
    LinkIndexes = if List.Count(Links) > 0 then {0..List.Count(Links)-1} else {},
    LinkPlayerRows =
        List.Combine(
            List.Transform(
                LinkIndexes,
                (i) =>
                    let
                        L = Links{i},
                        Players = try L[players] otherwise {}
                    in
                        List.Transform(
                            Players,
                            (p) => [
                                LinkIndex = i,
                                PlayerName = Text.From(p)
                            ]
                        )
            )
        ),
    TableOut = Table.FromRecords(
        LinkPlayerRows,
        type table [
            LinkIndex = Int64.Type,
            PlayerName = text
        ]
    )
in
    TableOut


// Query name: SankeyFlowsRaw
// Used only by the optional DAX table SankeyEdgesFromFlows.
// Career-path responses currently return an empty flows array, which is OK.
let
    Response = SankeyResponse,
    Flows = try Response[flows] otherwise {},
    FlowRows =
        List.Transform(
            Flows,
            (f) => [
                person_id = Text.From(try f[person_id] otherwise ""),
                first_name = Text.From(try f[first_name] otherwise ""),
                last_name = Text.From(try f[last_name] otherwise ""),
                source_team = Text.From(try f[source_team] otherwise ""),
                source_season = Text.From(try f[source_season] otherwise ""),
                target_team = Text.From(try f[target_team] otherwise ""),
                target_season = Text.From(try f[target_season] otherwise ""),
                position = Text.From(try f[position] otherwise "")
            ]
        ),
    TableOut = Table.FromRecords(
        FlowRows,
        type table [
            person_id = text,
            first_name = text,
            last_name = text,
            source_team = text,
            source_season = text,
            target_team = text,
            target_season = text,
            position = text
        ]
    )
in
    TableOut

