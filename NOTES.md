using gh and github REST api :
- post comment to issue ##
- create four new sub issues
- make them children to 43 (both by appending comments and in the gtihub api graph)
- make them each block its subsequent sister (the first one will be unblocked) 


# A script to create and link sub-issues on GitHub using the 'gh' CLI and 'jq'.

# --- Configuration ---
# The parent issue number.
PARENT_ISSUE=43
# The owner/repo path.
REPO="fedevela/particle-life-3d"

# The JSON payload containing the comment and sub-issue definitions.
# Note: In a real script, this would be loaded from a file or variable.
JSON_PAYLOAD='{
  "comment": "The 12 canonical requirements from the Gevurah phase have been analyzed and decomposed into four sequential, testable child issues for implementation. The decomposition strategy groups requirements by functional area to create clear, actionable units of work with a logical dependency chain.\n\nThis decomposition maps all 12 canonical requirements to the 4 child issues, ensuring complete coverage. No requirements were deferred or rejected at this stage.\n\n- **Child Issue 1: Core Simulation Shaders** covers the fundamental GPU logic for particle computation and rendering (`HSW-103`, `HSW-104`). This is the foundational piece upon which everything else is built.\n- **Child Issue 2: Deterministic Contract Test** is dedicated to verifying the correctness and deterministic nature of the core shaders (`HSW-105`). It directly depends on the completion of the first issue.\n- **Child Issue 3: Application Integration & Configuration** handles wiring the simulation into the application, including navigation, autostart, and all URL-based configuration parameters (`HSW-101`, `HSW-102`, `HSW-106`, `HSW-107`, `HSW-108`, `HSW-112`). This issue consolidates all user-facing setup and control mechanisms.\n- **Child Issue 4: UI/UX Polish & Performance** addresses the final visual and performance aspects, such as responsive behavior, frame rate, and particle coloring (`HSW-109`, `HSW-110`, `HSW-111`). This ensures the user experience is robust and aesthetically complete.",
  "sub_issues": [
    { "title": "[AUTO/TIFERET] Implement Core Simulation Shaders (Vertex/Fragment)", "body": "Requirement IDs: HSW-103, HSW-104\n\nCanonical Requirements:\n- `GUID: HSW-103` [RED] A vertex shader must be used to calculate the next position for each particle based on a random walk algorithm.\n- `GUID: HSW-104` [RED] A fragment shader must be used to render each particle as a visible point on the canvas.\n\n---\n\nGiven a data texture containing particle positions and velocities\nWhen the simulation advances one frame\nThen a vertex shader must be executed that updates each particle''s position based on a random walk algorithm.\n\nGiven a set of particle positions\nWhen the render pipeline executes\nThen a fragment shader must be executed that renders each particle as a visible point on the target canvas." },
    { "title": "[AUTO/TIFERET] Create Deterministic Contract Test for Simulation", "body": "Requirement IDs: HSW-105\n\nCanonical Requirements:\n- `GUID: HSW-105` [RED] Given a specific initial seed, the simulation must be deterministic, with particle positions matching a known contract file after a fixed number of frames.\n\n---\n\nGiven the simulation is initialized with a known seed (e.g., ''test-seed'')\nAnd the particle count is set to a fixed number (e.g., 100)\nWhen the simulation runs for a specific number of frames (e.g., 60 frames)\nThen the final state of all particles (positions) must be read from the GPU\nAnd the resulting data must exactly match the contents of a pre-approved contract file for that seed and frame count." },
    { "title": "[AUTO/TIFERET] Integrate Simulation and Add URL-Based Configuration", "body": "Requirement IDs: HSW-101, HSW-102, HSW-106, HSW-107, HSW-108, HSW-112\n\nCanonical Requirements:\n- `GUID: HSW-101` [RED] When the user clicks the \"Hello Shader World\" navigation link, the application must navigate to the shader simulation page.\n- `GUID: HSW-102` [RED] When the simulation page loads, the particle simulation must start automatically without user interaction.\n- `GUID: HSW-106` [ORANGE] If no seed is provided in the URL, a random seed must be generated for the simulation and its value added as a query parameter to the URL.\n- `GUID: HSW-107` [ORANGE] The number of particles in the simulation must be configurable via a URL query parameter.\n- `GUID: HSW-108` [ORANGE] If no particle count is specified in the URL, the simulation must default to at least 10,000 particles.\n- `GUID: HSW-112` [GREEN] If a `debug` flag is present in the URL, a frame rate counter must be displayed as an overlay on the simulation.\n\n---\n\nGiven the user is on the main dashboard\nWhen the user clicks the \"Hello Shader World\" navigation item\nThen the application URL must change to the corresponding route (e.g., ''/hello-shader-world'')\nAnd the simulation component must be rendered.\n\nGiven the user navigates to the simulation URL without any query parameters\nWhen the page and component finish loading\nThen the simulation must begin running automatically\nAnd the simulation must use a default particle count of at least 10,000\nAnd a new query parameter (e.g., `?seed=...`) with the generated seed value must be appended to the URL.\n\nGiven the user navigates to the simulation URL with a `particleCount` parameter (e.g., ``/hello-shader-world`?particleCount=50000`)\nWhen the simulation initializes\nThen the number of particles used must be 50,000.\n\nGiven the user navigates to the simulation URL with a `debug=true` parameter\nWhen the simulation is running\nThen a visible frame rate counter must be rendered as an overlay on the canvas." },
    { "title": "[AUTO/TIFERET] Implement Responsive Canvas, Performance, and Particle Color", "body": "Requirement IDs: HSW-109, HSW-110, HSW-111\n\nCanonical Requirements:\n- `GUID: HSW-109` [ORANGE] The simulation canvas must be responsive, adjusting to the dimensions of its container element and constraining particles within those boundaries.\n- `GUID: HSW-110` [ORANGE] The simulation must maintain a frame rate at or above 30 FPS on typical hardware with the default particle count.\n- `GUID: HSW-111` [GREEN] The color of each rendered particle can be selected from a palette based on a deterministic property such as its position.\n\n---\n\nGiven the simulation is running within a container element\nWhen the size of the browser window is changed, causing the container''s dimensions to update\nThen the simulation canvas must resize to match the new dimensions of its container\nAnd the particles must remain visible and constrained within the new canvas boundaries.\n\nGiven the simulation is running with the default particle count of 10,000\nWhen performance is monitored over a 1-minute interval on a target device\nThen the average frame rate must remain at or above 30 frames per second.\n\nGiven a particle has a specific position on the canvas\nWhen the fragment shader renders the particle\nThen its color must be determined by a function of its position, using a predefined color palette." }
  ]
}'

# 1. Post the main comment to the parent issue.
echo "$JSON_PAYLOAD" | jq -r .comment | gh issue comment "$PARENT_ISSUE" -R "$REPO" --body-file -

# 2. Create the child issues sequentially and link them.
CHILD_ISSUE_NUMBERS=()
PREVIOUS_ISSUE_NUMBER=""
SUB_ISSUE_COUNT=$(echo "$JSON_PAYLOAD" | jq '.sub_issues | length')

for i in $(seq 0 $(($SUB_ISSUE_COUNT - 1))); do
  TITLE=$(echo "$JSON_PAYLOAD" | jq -r ".sub_issues[$i].title")
  BODY=$(echo "$JSON_PAYLOAD" | jq -r ".sub_issues[$i].body")

  # For subsequent issues, add the "Blocked by" reference to the previous one.
  if [ -n "$PREVIOUS_ISSUE_NUMBER" ]; then
    BODY+="\n\nBlocked by: #$PREVIOUS_ISSUE_NUMBER"
  fi
  
  # Create the issue and capture its URL. The output of 'gh issue create' is the URL.
  NEW_ISSUE_URL=$(echo -e "$BODY" | gh issue create -R "$REPO" --title "$TITLE" --body-file -)
  
  # Extract the issue number from the URL for later steps.
  NEW_ISSUE_NUMBER=$(basename "$NEW_ISSUE_URL")
  CHILD_ISSUE_NUMBERS+=($NEW_ISSUE_NUMBER)
  PREVIOUS_ISSUE_NUMBER=$NEW_ISSUE_NUMBER
  echo "Created issue #$NEW_ISSUE_NUMBER"
done

# 3. Add the child issue task list to the parent issue's body.
PARENT_BODY=$(gh issue view "$PARENT_ISSUE" -R "$REPO" --json body --jq .body)
TASK_LIST="\n\n### Child Issues\n"
for NUM in "${CHILD_ISSUE_NUMBERS[@]}"; do
  TASK_LIST+="- [ ] #$NUM\n"
done

echo -e "$PARENT_BODY$TASK_LIST" | gh issue edit "$PARENT_ISSUE" -R "$REPO" --body-file -

echo "Successfully created and linked all child issues to parent #$PARENT_ISSUE."
