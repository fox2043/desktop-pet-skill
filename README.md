# Desktop Pet Skill

Create a transparent Windows desktop pet from 1-4 cat or dog photos.

The reference-photo count never controls the number of actions. One photo and four photos both produce the same required action plan: 13 action groups and 65 animation frames. Extra photos only improve identity consistency, side views, and coat/marking accuracy.

## Action set

Idle, sleeping, waiting, greeting, jumping, cute reaction, working companion, review, left/right walking, feeding, playing, and happy response. Passive behavior is deliberately slow, with at least seven seconds between normal state changes.

## Use

Install the `desktop-pet` folder as a Codex skill, then ask:

```text
Use $desktop-pet to turn my pet photos into a multi-action offline desktop pet.
```

The packaged Windows runtime must be offline: reference photos are used during asset creation and the final executable must not upload them or call an API.

See [action-contract.md](desktop-pet/references/action-contract.md) for action, realism, and timing requirements.
