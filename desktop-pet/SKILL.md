---
name: desktop-pet
description: Deliver, verify, or prepare the fixed Windows desktop-pet installer. Use when the user asks for this desktop pet's install package, portable release, integrity verification, or release handoff. This skill is exclusively for the existing fixed pet and must not accept pet photos, create another pet, offer cat/dog selection, or modify the main desktop-pet project.
---

# Desktop Pet

Use this skill only to release the verified installer bundle. The bundle is a fixed, offline Windows package containing the existing transparent desktop-pet application and installation notes.

## Delivery workflow

1. Keep this skill independent. Do not read from, write to, or copy the main desktop-pet project.
2. Run the delivery script with an explicit output directory:

```powershell
python "<skill-dir>\scripts\deliver_desktop_pet.py" --output "C:\Users\<user>\Desktop\desktop-pet-installer-v1.0.0"
```

3. Give the user the copied ZIP. It contains the installer, SHA-256 record, and install instructions.
4. Report the checksum produced by the script. Do not claim that the installer has been installed or run unless that was separately tested.

## Boundaries

- Never ask for, ingest, or upload pet photos.
- Never call an API or generate a replacement appearance/action pack.
- Never use this skill to make a dog, another cat, or a customized pet.
- If the user wants a new pet or changes to the application, work in a separately scoped main project; do not alter this fixed release skill.

## Resources

- `scripts/deliver_desktop_pet.py` copies and integrity-checks the bundled release.
- `references/release.md` states the fixed release contents and verification criteria.
- `assets/release/desktop-pet-installer-v1.0.0.zip` is the only bundled application artifact.
