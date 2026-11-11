# Feature Specification: Retro HUD & Interaction Elements Demake

**Feature Branch**: `001-retro-hud-elements`

**Created**: 2026-11-08

**Status**: Draft

**Input**: User description: "Demake of HUD and other interaction elements to a retro style"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Primary Vitals & Quickslots Combat HUD (Priority: P1)

As a player engaging in real-time combat, I want the core heads-up display (health bar, stamina bar, quicksilver bullet counter, blood vial counter, and active weapon/item slots) to reflect an authentic retro console aesthetic with pixelated borders and 15-bit color palette while maintaining instantaneous readability, so that the visual presentation harmonizes with the low-poly world without compromising combat awareness.

**Why this priority**: Core combat survival depends directly on immediate visibility of health and stamina. Without readable, retro-styled vitals, gameplay is disorienting or visually discordant.

**Independent Test**: Can be tested independently in Hunter's Dream or Central Yharnam by receiving damage, sprinting, consuming items, and cycling weapons: verify gauge fill animations and item counter decrements render with crisp retro styling and zero boundary clipping.

**Acceptance Scenarios**:

1. **Given** player takes damage, **When** health bar depletes, **Then** the health gauge animates with chunky retro borders and quantized color fill without clipping or visual tearing.
2. **Given** player expends stamina through attacks or evasion, **When** stamina bar empties and regenerates, **Then** the stamina gauge displays distinct retro stepped texels with clear visibility against dark and light environments.
3. **Given** player equips blood vials and quicksilver bullets, **When** items are consumed, **Then** numerical counters update instantly with clear pixelated digit typography.
4. **Given** player switches active right-hand or left-hand weapons, **When** slot icons refresh, **Then** weapon silhouettes display inside retro framed containers with matching palette depth.

---

### User Story 2 - World Interaction Prompts, Dialogues & Loot Notifications (Priority: P2)

As an exploring hunter, I want environmental interaction prompts ("Talk", "Open", "Traverse nightmare fog", "Inspect"), dialogue selection boxes, and item pickup notification toasts to appear in cohesive retro styling, so that interactive storytelling feels unified with the 32-bit demake aesthetic.

**Why this priority**: World exploration and NPC questlines require continuous interaction with environmental triggers. Clear retro-styled prompts maintain atmospheric immersion without obscuring button instructions.

**Independent Test**: Can be tested independently by approaching interactive doors, initiating dialogue with the Plain Doll, and collecting ground items: verify prompt box styling, choice cursor responsiveness, and pickup toast layout.

**Acceptance Scenarios**:

1. **Given** player approaches an interactive door, lantern, or NPC, **When** the prompt appears, **Then** the interaction frame and action text display in a retro framed box while button guide indicators remain distinctly legible.
2. **Given** player engages in multi-option NPC dialogue, **When** decision choices appear, **Then** the selection highlight and background framing render in quantized retro tones with responsive cursor navigation.
3. **Given** player picks up ground loot, **When** the item popup banner displays, **Then** the item icon and name appear with chunky retro borders before cleanly fading away.

---

### User Story 3 - Boss Encounter Gauges & Milestone Banners (Priority: P3)

As a player confronting boss enemies or achieving major milestones, I want the boss health bar and full-screen announcement banners ("PREY SLAUGHTERED", "YOU DIED", "NIGHTMARE SLAIN") to evoke classic 32-bit gothic horror presentations, so that triumphant and catastrophic moments feel stylistically authentic to the demake theme.

**Why this priority**: Boss battles and death/victory milestones provide the emotional peaks of the game. Demaking these grand banners completes the retro audiovisual experience.

**Independent Test**: Can be tested independently by initiating a boss encounter (e.g. Cleric Beast or Father Gascoigne) and triggering victory/defeat states: verify boss gauge scaling, phase transitions, and announcement banner presentation.

**Acceptance Scenarios**:

1. **Given** player crosses the fog into a boss arena, **When** the boss health bar initializes, **Then** the elongated bottom boss bar renders with ornate retro-styled endcaps and quantized crimson fill.
2. **Given** player defeats a boss or perishes in battle, **When** the banner screen appears, **Then** the iconic typography renders in bold retro presentation with subtle dithered backing.

---

### Edge Cases

- **Aspect Ratio Adaptability**: Vitals gauges and notification banners must maintain correct screen anchoring and 9-slice boundary proportions across standard display formats (16:9, 16:10) without stretching or off-screen clipping.
- **Status Effect Meter Stacking**: Dynamic status buildup gauges (Frenzy, Poison, Beast Blood) must layer distinctly above primary vitals without chromatic clashing or obscuring remaining health levels.
- **Rally Health Visibility**: The transient orange rally health window must remain visually distinguishable from current solid red health under quantized 15-bit color depth.
- **Button Prompt Clarity**: Controller button icons (cross, circle, square, triangle, shoulder triggers) must preserve contrast and edge sharpness at retro resolutions to prevent input confusion.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST render player vitals (health bar, stamina bar, quicksilver bullet counter, blood vial counter) in a quantized 15-bit color retro aesthetic.
- **FR-002**: System MUST render primary and secondary weapon equipment slots, active quick-items, and blood echoes/insight counters using pixelated retro framing.
- **FR-003**: System MUST preserve exact gauge boundary scaling and fill ratios, ensuring health and stamina fill percentages remain mathematically faithful to actual player attributes.
- **FR-004**: System MUST display environmental interaction prompts (e.g., "Talk", "Open", "Traverse") in unified retro framed containers.
- **FR-005**: System MUST ensure all controller input button prompts (cross, circle, square, triangle, triggers) retain high-contrast legibility without illegible blur or missing button indicators.
- **FR-006**: System MUST present boss health bars, lock-on target reticles, and enemy awareness indicators in matching retro styling.
- **FR-007**: System MUST render milestone celebration and death announcement banners ("PREY SLAUGHTERED", "YOU HUNTED", "YOU DIED") with retro typography and dithered backing.
- **FR-008**: System MUST isolate all modified UI assets within the mod distribution structure, maintaining strict immutability of pristine retail game files.

### Key Entities

- **Vitals HUD Display**: Player status container located in the primary screen corner, showing dynamic health, stamina, quick-use ammunition/vials, and currency totals.
- **Interaction Banner Widget**: Context-sensitive screen prompt that appears dynamically upon proximity to actionable world entities (doors, lamps, NPCs, chests).
- **Boss Encounter Bar**: Centered wide-screen combat gauge displaying boss entity name, total hit points, and phase transitions.
- **Milestone Notification Screen**: Modal overlay displayed upon death, victory, or discovery events with distinctive centered lettering and full-width framing.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of visible in-game HUD gauges, item frames, and interaction prompts conform to the 32-bit retro aesthetic with zero modern smooth gradients.
- **SC-002**: Critical combat vitals (current health and stamina values) remain distinguishable and legible within 200 milliseconds of player gaze transition.
- **SC-003**: Controller button prompts maintain 100% glyph legibility across standard viewing distances with zero misidentified inputs in playtesting.
- **SC-004**: Zero visual distortion, clipping, or misaligned slice borders across standard supported aspect ratios (16:9, 16:10).
- **SC-005**: 100% compliance with project baseline immutability: zero modifications to pristine retail directories.

## Assumptions

- Scaleform UI layout definitions and screen coordinate anchors remain standard, with retro styling achieved through texture atlas re-theming, palette quantization, and pixel styling.
- Font glyph contrast will be prioritized over aggressive downscaling for small button prompts to prevent gameplay confusion.
- The retro HUD package is non-destructive and can be toggled via mod directory configuration.
