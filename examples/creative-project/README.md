# Creative Project Reference

An empty, copyable structure for a creative-writing project. The bible establishes
canon; the Script hierarchy holds the story developed from it. This reference has
no characters, plot, or performance-ready scene materials yet.

```text
creative-project/
├── AGENTS.md
├── bible/
│   ├── README.md
│   ├── project.md
│   ├── characters.md
│   ├── dramatic_arcs.md
│   ├── world_rules.md
│   ├── theme.md
│   ├── relationships.drawio
│   └── characters/
│       └── character_id/
│           ├── appearance.md
│           ├── personality.md
│           ├── interiorvoice.md
│           ├── wants.md
│           ├── fears.md
│           ├── secrets.md
│           └── lexicon.md
└── Script/
    └── Season_01/
        ├── README.md
        └── Episode_01/
            ├── README.md
            └── Scene_01/
                └── Beat_01/
                    └── .gitkeep
```

Copy this directory's contents into a story repository. Read the
[agent instructions](AGENTS.md) and populate the [story bible](bible/README.md)
with the human partner's established material before starting generation.
Rename `character_id` to a stable character ID and repeat its seven-file profile
for each character. Introduce those IDs in the cast overview.

The numbered Script branch demonstrates the hierarchy. Add seasons, episodes,
scenes, and beats as needed, retaining the same naming convention. The empty
`.gitkeep` preserves the leaf and its ancestor directories in Git; it carries no
story content and may be removed once the beat contains real material.

Treatments, skeletons, and performed scripts belong outside the bible. During
preparation, each scene receives its own `AGENTS.md`, `dramatic_action_brief.md`,
`performance_context.json`, `scene_skeleton.md`, and initial `script.md`. These are
generated when real scene material is available. Beat folders organize material;
they do not replace canonical beat IDs or runtime handoff files. The runtime
locates scenes by their handoff files, not by this directory naming convention.

File presence alone does not make an empty bible sufficient for writing. The
human partner must supply its canon, and scene preparation must complete before
performance can begin.

## Blank Writing Templates

The Markdown templates provide empty sections for project identity, audience,
format, world, themes and aesthetics, cast profiles, and dramatic arcs. The
[season outline](Script/Season_01/README.md) holds the season synopsis and episode
index; the [episode outline](Script/Season_01/Episode_01/README.md) holds its synopsis,
character progression, and narrative turns. Scene and beat folders remain empty
until actual dramatic material is available.

The section coverage draws on `prompt_biblia_cicatriz_perfecta.txt`, a user-provided
season-bible prompt. Only its organizational requirements were used; no story facts
or inferred canon were imported. That source file is not required to use this
reference. Its suggested synopsis lengths are editorial guidance, not runtime gates.

Project presentation sections and outline READMEs support authoring; they add no
runtime prerequisites. Populate source references and distinguish unapproved
inferences from established canon. See the [bible index](bible/README.md) for ownership
of each part of the story material.
