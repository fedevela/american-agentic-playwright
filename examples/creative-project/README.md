# Creative Project Reference

An empty, copyable structure for a creative-writing project. The bible establishes
canon; the Script hierarchy holds the story developed from it. This reference has
no characters, plot, or performance-ready scene materials yet.

```text
creative-project/
├── AGENTS.md
├── bible/
│   ├── README.md, project.md, characters.md, dramatic_arcs.md
│   ├── world_rules.md, theme.md, relationships.drawio
│   └── characters/character_id/
│       ├── objective.md
│       ├── hidden_objective.md
│       ├── conflict_with_others.md
│       ├── conflict_with_self.md
│       ├── conflict_with_environment.md
│       ├── line_of_thought.md
│       └── line_of_images.md
└── Script/
    ├── README.md
    └── season_template/Season_N/
        ├── README.md
        └── Episode_N/
            ├── README.md
            └── script.md
```

Copy this directory's contents into a story repository. Read the
[agent instructions](AGENTS.md) and populate the [story bible](bible/README.md)
with the human partner's established material before starting generation.
Rename `character_id` to a stable character ID and repeat its seven-file profile
for each character. Introduce those IDs in the cast overview.

Instantiate the neutral `season_template` outside that directory with real season
and episode numbers. Each episode has one Markdown `script.md` containing all acts,
scenes and beats. Follow the [manuscript format](Script/README.md).

Treatments and performance preparation belong outside the bible. Real scene inputs
live under `Episode_N/scene_materials/<scene_id>/`: `AGENTS.md`,
`dramatic_action_brief.md`, `performance_context.json`, `scene_skeleton.md`, and
`scene_template.md`. The preserved skeleton and public scene template are immutable
preparation, not additional manuscripts. No ready-to-run handoff is supplied here.

File presence alone does not make an empty bible sufficient for writing. The
human partner must supply its canon, and scene preparation must complete before
performance can begin.

## Blank Writing Templates

The Markdown templates provide empty sections for project identity, audience,
format, world, themes and aesthetics, cast profiles, and dramatic arcs. The
[season outline](Script/season_template/Season_N/README.md) holds the season synopsis and episode
index; the [episode outline](Script/season_template/Season_N/Episode_N/README.md) holds its synopsis,
character progression, and narrative turns. Its scene index links directly to headings in the episode manuscript.

The section coverage draws on `prompt_biblia_cicatriz_perfecta.txt`, a user-provided
season-bible prompt. Only its organizational requirements were used; no story facts
or inferred canon were imported. That source file is not required to use this
reference. Its suggested synopsis lengths are editorial guidance, not runtime gates.

Project presentation sections and outline READMEs support authoring; they add no
runtime prerequisites. Populate source references and distinguish unapproved
inferences from established canon. See the [bible index](bible/README.md) for ownership
of each part of the story material.
