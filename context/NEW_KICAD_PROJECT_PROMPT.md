# Starter Prompt For A New Codex KiCad Project

Paste this into a new Codex instance after copying `KICAD_CODEX_HANDOFF.md`, `agent.md`, and `preferences.txt` into the new workspace.

```text
I want to generate a new KiCad 10 schematic/PCB project from scratch in this folder.

Please read these local files first:
- KICAD_CODEX_HANDOFF.md
- agent.md
- preferences.txt

Use the KiCad tooling paths from the handoff file. Follow the schematic-generation, symbol-library, annotation, PCB-placement, BOM, ERC/DRC, and net-label rules in those files.

For every generated local net label, emit KiCad text effects with `(justify left bottom)`.

Use existing KiCad library symbols and footprints where possible. Put generated symbols in a project-local `.kicad_sym` file and make sure the project references it. Use real schematic symbols for passives, not generic boxes.

Create the schematic, annotate it, assign footprints, create/update the PCB from the schematic, place components in logical groups with decoupling caps close to their ICs, export CSV and Excel BOMs with manufacturer and MPN fields, then run/inspect ERC and DRC before reporting completion.

Here is the new design brief:

[PASTE THE DESIGN BRIEF HERE]
```

