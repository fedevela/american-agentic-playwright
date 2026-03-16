<!-- phase:1:start label=phase:keter name=Keter -->
### Phase 1:Daneel-Keter-Intent

Requirement clarified.

# Clarified Requirement
The "Hello Shader World" control, situated in the left-hand interface panel, shall be modified to instantiate a visual simulation of numerous particles executing a random walk. This simulation must leverage WebGL shaders for both computation and rendering to ensure performance scalability, updating or replacing the current behavior associated with this option.

# Constraints and Invariants
-   **UI Integrity:** The entry point remains the specific "Hello Shader World" selection in the left panel; no new UI controls are requested, only the behavior bound to this existing control changes.
-   **Execution Environment:** Rendering and logic must occur within the WebGL context using custom shaders (GLSL), prohibiting CPU-based rendering methods (Canvas 2D) for the particles.
-   **Motion Logic:** Particle movement must adhere to a random walk algorithm (Brownian motion), implying stochastic updates to position on each frame.
-   **Scalability:** The implementation must support a high density of particles without significant frame rate degradation so minimize per particle calculations.
-   **Resource Management:** Activation of this menu item must initialize the necessary shader programs and buffers; deactivation must release these resources to preserve application stability.

# Acceptance Signals
-   **Observable Activation:** Clicking the "Hello Shader World" option transitions the main view to the new particle simulation.
-   **Visual Pattern:** Particles are observed moving in randomized directions over time, rather than following static or pre-determined linear paths.
-   **Shader Utilization:** Code confirms that the GPU is the primary resource used for rendering, and the CPU load remains minimal relative to particle count.
-   **Error-Free Execution:** The browser console remains free of WebGL compilation errors or runtime warnings during the simulation lifecycle.

# Phase 2 Handoff
Generative expansion can proceed.

<!-- phase:1:end label=phase:keter name=Keter -->
