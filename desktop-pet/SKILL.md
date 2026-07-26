---
name: desktop-pet
description: Create, repair, validate, and package a transparent Windows desktop pet from 1-4 uploaded cat or dog photos. Use when a user wants their pet photos turned into a desktop companion with many realistic, slow, interactive actions. Always generate the complete fixed action set independent of the number of uploaded photos; photos determine appearance only, never the number of actions.
---

# Desktop Pet

Create an offline Windows desktop-pet package from 1-4 reference photos. Treat the photos as one identity set: select a canonical appearance and reuse it for every action. Never map photo 1 to action 1, photo 2 to action 2, or otherwise make action count depend on photo count.

## Required action contract

Create all 13 action groups, each with 5 distinct transparent PNG frames (65 frames total):

1. `idle` — sitting or lying quietly; blink, breathe, tiny head turn.
2. `sleeping` — slow settling, eyes closing, sleeping, brief head lift, resettling.
3. `waiting` — alert but calm, looking toward the cursor.
4. `greeting` — approach, look up, soft paw or head greeting.
5. `jumping` — a short playful hop with a settle frame.
6. `cute` — gentle roll, stretch, or affectionate head tilt.
7. `working` — quiet companion pose while the user works.
8. `review` — attentive listening/looking pose.
9. `walking-right` — a real alternating rightward gait.
10. `walking-left` — a real alternating leftward gait.
11. `feeding` — approach bowl, lower head, chew, look up contentedly.
12. `playing` — curious paw tap or small play bow.
13. `happy` — relaxed, content response after interaction.

Keep cat and dog body language different. Cats should prefer sleep, loafing, lying, grooming-like pauses, slow stretching, and occasional play. Dogs should prefer sit/lie, ear and head attention, short tail/body responses, food interest, and a gentler walking cadence.

## Generation workflow

1. Run `scripts/prepare_action_manifest.py` with every uploaded photo. It must produce exactly 65 requested frames before any image work begins.
2. Use the reference photos to establish one consistent realistic pet identity. Preserve face markings, coat blocks, eye color, proportions, and fur texture. Do not make a cartoon pet unless the user asks.
3. Generate or edit each action group as its own five-frame sequence. Ground every group in the canonical pet appearance and the original photos. Do not reuse a frame across different action groups.
4. Remove the background and export all frames as transparent PNG. Validate that every required group has five nonblank frames with visible pose variation.
5. Package the generated action folder with the desktop-pet runtime. The runtime must run locally and must not upload photos or call an API.
6. Set passive states to long dwell times: at least 7 seconds before an ordinary state change. Only interaction events may temporarily interrupt the passive sequence.

## Interaction mapping

- Mouse hover: `waiting`, `greeting`, `cute`, or `playing`.
- Right-click greeting: `greeting`.
- Tease/jump: `jumping` then `happy`.
- Feed: `feeding` then `happy`.
- Work/document activity: `working` or `review`.
- Idle desktop: favor `idle` and `sleeping`; do not cycle actions quickly.
- After 23:00: prefer `sleeping` with a short bedtime acknowledgement.

## Acceptance checks

- Exactly 13 action folders and 65 frames, regardless of whether the user uploads 1, 2, 3, or 4 photos.
- No action group is composed of five identical frames.
- `feeding`, `walking-*`, `jumping`, `greeting`, and `playing` have clearly different silhouettes from `idle`.
- Background is transparent; no background rectangle, fading ghost, or cross-fade overlap between actions.
- Provide a contact sheet and a short preview for visual QA before packaging.

Read `references/action-contract.md` for detailed pose and timing requirements.
