# Desktop Pet Skill

This is a standalone fixed-release skill for a Windows desktop pet. It delivers and verifies the existing offline installer bundle.

It is not a pet generator: it does not accept photos, offer cat/dog selection, generate another pet, or include main-project source code.

## Use

Install the `desktop-pet` folder as a Codex skill, then ask:

```text
Use $desktop-pet to deliver the fixed desktop-pet installer.
```

The skill copies the bundled ZIP and verifies its SHA-256 before handoff. See [release.md](desktop-pet/references/release.md) for the release definition.

## Scope

- Fixed offline Windows release
- No runtime API calls or photo uploads
- No pet-generation workflow or source-project dependency

The helper script is released under the [MIT License](LICENSE). Third-party license terms inside the bundled application remain with the application.
