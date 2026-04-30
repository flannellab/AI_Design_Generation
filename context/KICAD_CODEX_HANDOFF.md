# KiCad Codex Handoff

Use this file to resume this KiCad schematic/PCB-generation workflow in a new Codex workspace.

## Local Tooling

- KiCad version target: KiCad 10.
- `kicad-cli` directory: `C:\Users\ben.brinks\AppData\Local\Programs\KiCad\10.0\bin`
- Preferred KiCad Python executable: `C:\Users\ben.brinks\AppData\Local\Programs\KiCad\10.0\bin\python.exe`
- User-provided KiCad Python path, also usable for GUI Python launches: `C:\Users\ben.brinks\AppData\Local\Programs\KiCad\10.0\bin\pythonw.exe`
- Installed KiCad library root: `C:\Users\ben.brinks\AppData\Local\Programs\KiCad\10.0\share\kicad`
- KiCad upstream libraries reference: `https://gitlab.com/kicad/libraries`

When running `kicad-cli`, use bounded process waits because the CLI may write the report and then fail to return promptly. Check report timestamps and contents after a timeout before assuming the command failed.

## Standing Design Instructions

- Generate KiCad 10 projects, schematics, symbols, footprints, PCBs, and BOMs that open correctly in KiCad.
- Default schematic sheet size is 11x17 unless the project clearly needs a different size.
- Schematic symbol placement, pins, wires, and labels should stay on a 2.54 mm / 100 mil grid unless there is a deliberate KiCad-compatible reason not to.
- Prefer existing KiCad library symbols and footprints before generating custom ones.
- If custom symbols are needed, put them in a project-local `.kicad_sym` file and make sure the schematic/project references that library via `sym-lib-table`.
- If custom footprints are needed, put them in a project-local footprint library and wire it into the project.
- Do not present the schematic as complete unless ERC passes or any remaining issue is explicitly explained.
- Create or update the PCB from the schematic and group footprints logically.
- Place decoupling capacitors close to their ICs in both the schematic and PCB.
- Annotate the schematic before declaring it ready for board design.
- Export a BOM in CSV and Excel `.xlsx` format when requested.
- Include manufacturer names and real MPNs for as many BOM items as possible.
- Prefer parts from large, established manufacturers such as Microchip, TI, STMicroelectronics, Analog Devices, Murata, TDK, Vishay, Bourns, Littelfuse, Pulse, Molex, TE, Samtec, Amphenol, etc.
- Prefer USA-based parts where practical. More generally prefer USA, Europe, Japan, Korea, and Taiwan based manufacturers when suitable.
- Avoid China-based manufacturers when practical, but use them when there is no easy alternative and note the exception.

## Formatting And Readability Preferences

- Net labels must sit on real wire segments, not isolated in space.
- All generated local net labels should emit KiCad text effects with both horizontal and vertical justification:

```scheme
(justify left bottom)
```

- This means horizontal justification is `Left` and vertical justification is `Bottom`.
- Use readable local net labels instead of long drawn wires when it keeps the page cleaner.
- Avoid overlapping symbols, labels, text, wires, and pins.
- Do not let wires run through symbols.
- Make sure wire endpoints actually connect to pins or intentional junctions, not just visually touch.
- For passives, use actual KiCad passive schematic symbols that look like real symbols:
  - `Device:R` for resistors
  - `Device:C` for capacitors
  - `Device:L` for inductors
  - `Device:FerriteBead` for ferrite beads
  - `Device:Crystal` for crystals
- Default SMD passives to 0402.
- Use 0201 only when optimizing hard for space.
- Use 0603 or larger where power, voltage, assembly, or availability justifies it.
- Default unknown connectors to standard 0.1 inch male headers.

## Electrical Completion Standard

Generated schematics should include realistic support circuitry, not just the headline ICs:

- power inputs and regulators
- required rails and power sequencing assumptions
- decoupling and bulk capacitance
- ferrites or filtering where appropriate
- pull-ups, pull-downs, straps, reset circuits, and enables
- crystals/oscillators and load capacitors where required
- connector pinouts
- ESD/protection where it is plainly expected
- series termination where interface speed and placement justify it
- test points where useful
- BOM metadata and footprint assignments

Do not fabricate precision values where the design depends on unknown system constraints. Choose defensible defaults only when reasonable, and document assumptions.

## Verification Checklist

Before handing off generated KiCad files:

1. Regenerate the schematic/project files.
2. Confirm the custom symbol library is referenced by `sym-lib-table`.
3. Confirm all schematic net labels use `(justify left bottom)`.
4. Run ERC and inspect the report.
5. Generate/export a netlist as a parser/connectivity sanity check.
6. Create or update the PCB from the schematic.
7. Place related parts in logical groups on the PCB.
8. Put decoupling caps close to their IC packages on the PCB.
9. Run DRC and inspect the report.
10. Export and verify the BOM CSV/XLSX.

Expected status before routing: DRC may show many unconnected pads because the PCB is placed but not routed. DRC should still show zero rule violations unless a remaining issue is explicitly documented.

## Useful PowerShell Command Patterns

Run the generator:

```powershell
& 'C:\Users\ben.brinks\AppData\Local\Programs\KiCad\10.0\bin\python.exe' .\tools\generate_eth_switch_example.py
```

Run ERC with a bounded wait:

```powershell
$exe='C:\Users\ben.brinks\AppData\Local\Programs\KiCad\10.0\bin\kicad-cli.exe'
$proj='C:\path\to\project'
$args=@('sch','erc','--output',(Join-Path $proj 'erc.rpt'),(Join-Path $proj 'project_name.kicad_sch'))
$p=Start-Process -FilePath $exe -ArgumentList $args -WorkingDirectory $proj -WindowStyle Hidden -PassThru
if (-not $p.WaitForExit(60000)) { Stop-Process -Id $p.Id -Force; 'ERC timed out; inspect report timestamp/content' } else { "ERC exit $($p.ExitCode)" }
```

Check all local net labels have left/bottom justification:

```powershell
$path='.\project_name\project_name.kicad_sch'
$labels=(Select-String -Path $path -Pattern '^\s*\(label ' | Measure-Object).Count
$leftBottom=(Select-String -Path $path -Pattern '\(justify left bottom\)' | Measure-Object).Count
"labels=$labels left_bottom=$leftBottom"
```

## Current Example Project

The current example project is:

`C:\Projects\09_chatgpt_schematic_creation\codex\ksz9563_lan7800_switch`

It contains:

- `ksz9563_lan7800_switch.kicad_pro`
- `ksz9563_lan7800_switch.kicad_sch`
- `ksz9563_lan7800_switch.kicad_pcb`
- `eth_switch_generated.kicad_sym`
- `sym-lib-table`
- `ksz9563_lan7800_switch.net`
- `ksz9563_lan7800_switch_BOM.csv`
- `ksz9563_lan7800_switch_BOM.xlsx`
- `erc.rpt`
- `drc.rpt`
- `README_design_notes.md`

Example design contents:

- KSZ9563R unmanaged Ethernet switch IC.
- One switch Ethernet port to an RJ45 connector with integrated magnetics.
- One switch Ethernet port to LAN7800 Ethernet-to-USB IC, with USB signals brought to a standard header for now.
- One switch Ethernet port exposed as RGMII to a standard header.
- Local generated symbols in `eth_switch_generated.kicad_sym`.
- Annotated schematic, PCB generated from schematic, footprints placed logically, decoupling caps near ICs, and BOM exported to Excel.

## Reusable Script Starting Points

The `tools` folder contains script patterns worth reusing:

- `tools\generate_eth_switch_example.py`: KiCad 10 project/schematic/PCB generator pattern.
- `tools\build_bom_xlsx.mjs`: converts the generated CSV BOM to formatted `.xlsx`.
- `tools\verify_bom_xlsx.mjs`: verifies the generated workbook.

For a new project, copy only the patterns you need and rename the project-specific generator. Do not assume the Ethernet part choices are reusable unless the new design is also Ethernet-related.

