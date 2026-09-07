# Script

Each episode has one `script.md` containing its front matter, acts, scenes, and all
beats. The manuscript is the publication source. Scenes and beats are dramatic
units within it; do not create separate scene manuscripts or beat folders/documents.

Start from [the neutral season scaffold](season_template/Season_N/README.md), its
[episode outline](season_template/Season_N/Episode_N/README.md), and its
[blank manuscript](season_template/Season_N/Episode_N/script.md). Replace `N`,
`scene-id`, and all bracketed placeholders with established values when preparing
a real episode outside `season_template`. Every `season_template` directory is
excluded from runtime handoff discovery, including explicit selection.

## Manuscript and preparation

A real scene is prepared under `Season_01/Episode_01/scene_materials/<scene_id>/`
with `AGENTS.md`, `dramatic_action_brief.md`, `scene_skeleton.md`,
`scene_template.md`, and version-2 `performance_context.json`. These are runtime
inputs. The attributed phase-6 skeleton stays unchanged. The immutable scene
template holds the public Markdown heading, established opening directions,
canonical beat markers, and neutral dialogue placeholders. It has no front matter,
act heading, or scene boundary lines. Initially copy it exactly into its bounded
region in the episode’s `script.md`; actual performance replaces that region.
Never append a duplicate scene ID or automatically overwrite a differing region.

Use a unique scene ID containing only letters, digits, `_` or `-`. Its complete
boundary lines are `<!-- SCENE scene-id BEGIN -->` and
`<!-- SCENE scene-id END -->`. Boundaries are balanced and non-nested; fenced
examples do not define destinations. Keep each assigned canonical
`<!-- RESOLVES [BEAT …] -->` once in established order. The illustrative `BEAT ID`
below must be replaced with the real assigned ID. Preserve each full canonical
beat definition in its source and preparation references; shortening a marker
does not redefine the beat. Repeat beat blocks inside the same scene region.

## Markdown and export layout

| Element | Markdown | Export layout |
| --- | --- | --- |
| Title and playwright | Title heading and credited name | Center on title page |
| Contact | Contact name, email, additional information | Bottom corner of title page |
| Cast | Bold uppercase names, age, gender, traits | Separate introductory page |
| Setting and time | Separate place and time fields | Before dramatic text |
| Acts and scenes | Uppercase headings | Center; optionally underline |
| Speaker cue | Bold uppercase display name followed by two trailing spaces | Center or indent roughly four inches |
| Dialogue | Speech directly below the cue, without wrapper quotes | Left-align at standard margin |
| Stage direction | Blockquoted italic parenthetical | Indent on both sides |
| Inline direction | Italic parenthetical within speech | Keep inside the speech paragraph |

Markdown carries text structure. The export stylesheet controls page breaks,
centering, margins and precise placement. Preserve deliberately quoted words
within speech. Silence is an explicit stage direction with no invented dialogue.
Public performance excludes inner monologues, private direction and internal tags.

## Reusable blank manuscript

```markdown
# [PLAY TITLE]

[Playwright name]

[Contact name]  
[Email address]  
[Additional contact information]

---

# DRAMATIS PERSONAE

**[CHARACTER NAME]** — [Age description], [gender, as established], [relevant traits].

---

# SETTING & TIME

**Place:** [Where the play takes place.]

**Time:** [When the play takes place.]

---

## ACT [NUMBER]

<!-- SCENE scene-id BEGIN -->
### SCENE N — [SCENE TITLE]

> *([Setting at the opening of the scene.])*

<!-- RESOLVES [BEAT ID] -->

> *([Stage direction: action or movement.])*

**[CHARACTER NAME]**  
[Dialogue in normal sentence case.]

**[CHARACTER NAME]**  
[Dialogue before an inline direction.] *([Brief action or emotional cue.])* [Dialogue continues.]

> *([Stage direction between speeches.])*
<!-- SCENE scene-id END -->

<!-- Repeat beat blocks within each scene and bounded scene regions within the episode. -->
```
