# Action contract

Reference-photo count controls identity coverage only. One clear photo is sufficient to request all 13 action groups. Additional photos provide better markings, side views, and pose grounding; they never add or remove action groups.

## Timing

- Hold passive `idle`, `sleeping`, and `working` states for at least 7 seconds.
- Use 0.8-1.6 seconds for an interaction sequence, followed by 7+ seconds of rest.
- Do not use cross-fade or overlapping sprite frames between actions. Finish the current frame, pause briefly, then switch to the next action's first frame.
- Every exported PNG must be RGBA. Its outer two-pixel border must have alpha <= 8, so a photo background cannot remain visible around the pet.
- Remove RGB residue wherever alpha is near zero; do not leave white, gray, or photo-background halos in transparent pixels.
- Do not leave a black outline around the silhouette. For light fur, replace only near-transparent black matte pixels with the nearest interior fur color; preserve naturally dark fur by sampling its interior color rather than globally brightening it.

## Display size

Provide exactly three user-selectable size presets in the right-click menu: Small (55%), Medium (72%), and Large (90%). Default to Medium and migrate the old 90% default to Medium once so the pet does not cover too much of a typical desktop.

## Autonomous companion behavior

The pet must move without waiting for a click. Use a slow, non-repetitive passive loop: mostly `idle` and `sleeping`, with occasional `waiting`, `review`, a short stretch-like `failed`, one brief walk, or a quiet `working` companion pose. Choose a new passive sequence only after the current state has held for its minimum duration. Do not use a rapid random action timer.

Mouse and menu events interrupt the passive loop temporarily, then return to it: hover triggers `waiting` then `waving`/`happy`; feeding triggers `feeding` then `happy`; cursor activity near the pet triggers a short look or walk; work activity triggers `working`/`review`; late night favors `sleeping`.

## Sequence requirements

- `sleeping`: settle -> eyes close -> sleep -> raise head -> resettle.
- `feeding`: notice -> approach -> lower head to bowl -> chew -> contented look.
- `walking-*`: alternating paw placement and a stable baseline, not a translated still image.
- `jumping`: crouch -> lift -> apex -> land -> settle.
- `greeting`: notice -> look up -> small welcoming motion -> pause -> return calm.

## Realism

Keep body movement modest and physically plausible. Prefer ear turns, slow head turns, breath, paw shifts, stretch, loafing, lying down, and short interest responses. Avoid cartoon arcs, rapid looping, large unexplained rotations, and action frames that merely duplicate a reference photo.
