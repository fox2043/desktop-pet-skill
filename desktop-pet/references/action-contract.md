# Action contract

Reference-photo count controls identity coverage only. One clear photo is sufficient to request all 13 action groups. Additional photos provide better markings, side views, and pose grounding; they never add or remove action groups.

## Timing

- Hold passive `idle`, `sleeping`, and `working` states for at least 7 seconds.
- Use 0.8-1.6 seconds for an interaction sequence, followed by 7+ seconds of rest.
- Do not use cross-fade or overlapping sprite frames between actions. Finish the current frame, pause briefly, then switch to the next action's first frame.

## Sequence requirements

- `sleeping`: settle -> eyes close -> sleep -> raise head -> resettle.
- `feeding`: notice -> approach -> lower head to bowl -> chew -> contented look.
- `walking-*`: alternating paw placement and a stable baseline, not a translated still image.
- `jumping`: crouch -> lift -> apex -> land -> settle.
- `greeting`: notice -> look up -> small welcoming motion -> pause -> return calm.

## Realism

Keep body movement modest and physically plausible. Prefer ear turns, slow head turns, breath, paw shifts, stretch, loafing, lying down, and short interest responses. Avoid cartoon arcs, rapid looping, large unexplained rotations, and action frames that merely duplicate a reference photo.
