# KSZ9563R + LAN7800 Example Notes

This is a first-pass KiCad 10 schematic package generated from the project brief.

Major assumptions:
- 5 V board input, external supply rated at least 1 A; 1.5 A preferred.
- KSZ9563R VDDIO is 3.3 V, AVDDH is 2.5 V, AVDDL/DVDDL are 1.2 V.
- LAN7800 runs from 3.3 V and uses its internal 2.5 V LDO and 1.2 V switcher.
- LAN7800 USB SuperSpeed/Hi-Speed pins are brought to a 0.1 inch header for now.
- KSZ9563R port 2 to LAN7800 is shown through a placeholder 4-pair isolation/coupling transformer. This should be reviewed against the intended internal PHY-to-PHY implementation before layout.

Power budget basis:
- KSZ9563R full 1000 Mbps operation: 2.5 V AVDDH 140 mA, 3.3 V VDDIO 35 mA, 1.2 V AVDDL 190 mA, 1.2 V DVDDL 250 mA, about 0.99 W.
- LAN7800 SuperSpeed 1000BASE-T operation: 3.3 V at 256 mA, about 0.845 W.
- Total IC load is about 1.84 W before regulator losses and support circuitry.

Generated board status:
- The PCB file is populated from the same annotated component set as the schematic.
- Parts are placed by function: input/regulators at left, KSZ9563R in the center-left, LAN7800 center-right, RJ45/magnetics near the top/right edge, and headers along the lower/right edges.
- Nets are assigned to footprint pads where pad naming matches the schematic symbol. T1 uses a SO-24 Ethernet transformer footprint as a review placeholder.
- Manufacturer/MPN fields are populated in the schematic and BOM. The preference is USA-based suppliers where practical, but this is based on manufacturer/brand region, not a guaranteed factory country of origin.
- T1 currently uses YDS 30F-51NL because that is the KiCad library footprint that matches this first-pass internal PHY-to-PHY transformer. Treat it as the known China-based exception and replace before release if the sourcing rule is strict.
- The KSZ9563R and LAN7800 decoupling symbols are placed visibly beside their IC blocks in the schematic, and the PCB footprints are pulled close to their IC packages; final routing still needs power-integrity/layout review.
