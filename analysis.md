# Using Sankey Diagrams To Analyze Junior Player Development

The Sankey diagrams in this project are useful for asking a practical development question:

> How well has a junior team helped its players continue in hockey, and how many moved toward stronger leagues?

This is different from simply asking whether a team won games. A junior team can be valuable if its players keep playing, move to a more competitive age group, reach academy or elite junior levels, or eventually enter adult leagues.

## What The Diagram Shows

Each node is a team in a season. Each link shows players moving from one team-season node to another. Thicker links mean more players followed that path.

For junior development, the most useful views are:

- **Full career out**: Start with a junior team and season, then see where those players went in later seasons.
- **Full career in**: Start with a current team and see which junior teams the players came from.
- **One step forward**: Check the immediate next season after a specific junior roster.
- **One step back**: Understand the feeder teams behind a roster.

When evaluating a junior team, **Full career out** is usually the most important view because it follows that roster forward.

## What Counts As A Good Outcome

Not every good outcome means reaching Liiga or a national team. For most junior players, continuing to play at an appropriate level is already meaningful.

Useful outcome categories:

- **Elite progression**: Players move to higher junior levels such as U16 SM, U18 SM, U20 SM, national team events, or eventually Liiga/Mestis.
- **Competitive continuation**: Players continue in Mestis, Suomi-sarja, II-divisioona, or equivalent competitive junior/adult leagues.
- **Same-club retention**: Players stay inside the same club structure as they age up.
- **Hockey retention**: Players remain active somewhere, even if they move to a lower or recreational level.
- **Drop-off risk**: Players disappear from later seasons or only appear in isolated records.

A strong development team may not produce many elite players, but it should ideally keep a large share of players active and provide a path upward for the best players.

## How To Read A Junior Team's Development Path

Start with a specific team and season, for example a U16, U18, or U20 roster. Use **Full career out**.

Look first at the next season column. This shows immediate retention:

- Did most players continue playing?
- Did they move to the expected next age group?
- Did many stay in the same club?
- Did several players disappear immediately?

Then look two to four seasons forward. This shows longer-term development:

- Which players reached stronger leagues?
- Did the same club keep players through multiple age groups?
- Did players scatter to many teams, or is there a clear pathway?
- Are players still active after junior years?

The best development patterns are usually not one single thick link. They are often a combination of:

- one thick link to the next age group,
- several thinner links to stronger teams,
- and a visible tail of players continuing at lower levels.

## Comparing Junior Teams

When comparing two junior teams, avoid looking only at the highest-level destination. A small club may have a good development record if many players keep playing, even if few reach elite levels.

Better comparison questions:

- What percentage of the roster appears in the next season?
- How many players move to a higher level within two seasons?
- How many are still active three or four seasons later?
- Does the team feed its own older age groups?
- Does the team feed stronger external clubs?
- Are players leaving hockey, or just moving to a suitable lower level?

The Sankey diagram is strongest when used together with player counts. A team with 3 elite outcomes from 15 players is different from 3 elite outcomes from 60 players.

## Same Club Versus Better League

There are two different kinds of success:

1. **Club pathway success**: The club keeps players moving through its own age groups.
2. **Level progression success**: Players move to better leagues, even if they leave the club.

Both matter.

If a team keeps many players but few move upward, it may be good at retention but not elite development. If a team loses many players to stronger clubs, it may still be an important feeder team. If many players vanish, that may suggest a weak continuation pathway or a natural end point for that age group.

## What To Watch Out For

The diagrams depend on Leijonat data, team names, level IDs, and player career records. Some historical teams may have changed names or level labels. For older seasons, use the season-aware level picker and prefer graph traversal when continuing from an existing diagram.

Important limitations:

- A missing player record does not always mean the player stopped playing.
- Team abbreviations can represent several age groups or levels.
- Some players appear on multiple teams or levels in the same season.
- Moving to a lower level is not necessarily failure; it may mean the player found the right level.
- A high-level junior team may receive already-developed players, while a smaller team may have developed them earlier.

Because of this, use the Sankey as an evidence map, not a final ranking by itself.

## Practical Workflow

1. Choose a junior team, season, and exact level.
2. Build **Full career out**.
3. Check the immediate next season for retention.
4. Check later seasons for higher-level progression.
5. Click important nodes to continue following the same player cohort.
6. Compare with another team at the same age group and season.
7. Use counts and player names to verify the story behind each thick link.

## Good Questions To Ask

- Which U16 teams send players to U18 SM or U18 Mestis?
- Which U18 teams keep players active into U20 or adult leagues?
- Which clubs retain players internally through U16, U18, and U20?
- Which teams are strong feeders to elite organizations?
- Which teams keep the most players playing, even outside elite leagues?
- Where do players go after leaving a junior program?

## Summary

The Sankey diagrams are best used to study player pathways, not just team strength. A good junior development program should be judged by both progression and retention:

- Do players reach better leagues?
- Do players continue playing?
- Does the club provide a visible pathway?
- Do players have realistic next steps after the team?

Used this way, the diagrams can show which junior teams are producing elite players, which teams are keeping players in hockey, and which clubs act as important stepping stones in the Finnish hockey system.
