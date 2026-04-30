from __future__ import annotations

import json
import math
import shutil
import uuid
import csv
from dataclasses import dataclass
from pathlib import Path


PROJECT = "ksz9563_lan7800_switch"
LIB = "eth_switch_generated"
OUT = Path(__file__).resolve().parents[1] / PROJECT
KICAD_SHARE = Path(r"C:\Users\ben.brinks\AppData\Local\Programs\KiCad\10.0\share\kicad")
GRID = 2.54
PIN_LEN = 2.54
TEXT = 1.27
BOARD_W_MM = 175.0
BOARD_H_MM = 105.0


def uid() -> str:
    return str(uuid.uuid4())


def q(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def fnum(v: float) -> str:
    if abs(v - round(v)) < 1e-8:
        return str(int(round(v)))
    return f"{v:.4f}".rstrip("0").rstrip(".")


def effects(size: float = TEXT, justify: str | None = None, hide: bool = False) -> str:
    j = f"\n      (justify {justify})" if justify else ""
    h = "\n    (hide yes)" if hide else ""
    return f"""{h}
    (effects
      (font
        (size {fnum(size)} {fnum(size)})
      ){j}
    )"""


def cached_library_symbol(lib_name: str, symbol_name: str) -> str:
    source = KICAD_SHARE / "symbols" / f"{lib_name}.kicad_sym"
    text = source.read_text(encoding="utf-8")
    marker = f'(symbol "{symbol_name}"'
    start = -1
    for prefix in ("\t", "  ", ""):
        idx = text.find("\n" + prefix + marker)
        if idx >= 0:
            start = idx + 1
            break
    if start < 0:
        raise ValueError(f"Could not find {lib_name}:{symbol_name} in {source}")
    depth = 0
    in_string = False
    escaped = False
    end = None
    for i in range(start, len(text)):
        ch = text[i]
        if escaped:
            escaped = False
            continue
        if ch == "\\" and in_string:
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        raise ValueError(f"Could not parse {lib_name}:{symbol_name} from {source}")
    block = text[start:end].replace(marker, f'(symbol "{lib_name}:{symbol_name}"', 1)
    return "\n".join("  " + line for line in block.splitlines())


@dataclass
class Pin:
    num: str
    name: str
    side: str
    etype: str = "passive"
    net: str | None = None
    nc: bool = False


@dataclass
class SymDef:
    name: str
    ref: str
    value: str
    footprint: str
    datasheet: str
    desc: str
    pins: list[Pin]
    width: float = 45.72
    prefix: str = ""


def pin_xy(pin: Pin, index_by_side: dict[str, int], width: float) -> tuple[float, float, int]:
    i = index_by_side[pin.side]
    index_by_side[pin.side] += 1
    y = i * GRID
    x = -width / 2 - PIN_LEN if pin.side == "L" else width / 2 + PIN_LEN
    rot = 0 if pin.side == "L" else 180
    return x, y, rot


def symbol_definition(sym: SymDef, cache: bool) -> str:
    name = f"{LIB}:{sym.name}" if cache else sym.name
    counts = {"L": sum(p.side == "L" for p in sym.pins), "R": sum(p.side == "R" for p in sym.pins)}
    nrows = max(counts.values(), default=1)
    body_top = -GRID
    body_bot = nrows * GRID
    body_left = -sym.width / 2
    body_right = sym.width / 2
    idx = {"L": 0, "R": 0}
    pins = []
    for p in sym.pins:
        x, y, rot = pin_xy(p, idx, sym.width)
        pins.append(
            f"""      (pin {p.etype} line
        (at {fnum(x)} {fnum(y)} {rot})
        (length {fnum(PIN_LEN)})
        (name {q(p.name)}
          {effects(TEXT * 0.8).strip()}
        )
        (number {q(p.num)}
          {effects(TEXT * 0.8).strip()}
        )
      )"""
        )
    return f"""  (symbol {q(name)}
    (pin_names
      (offset 0.254)
    )
    (exclude_from_sim no)
    (in_bom yes)
    (on_board yes)
    (duplicate_pin_numbers_are_jumpers no)
    (property "Reference" {q(sym.ref)}
      (at {fnum(body_left)} {fnum(body_top - GRID)} 0)
      {effects()}
    )
    (property "Value" {q(sym.value)}
      (at {fnum(body_left + 12.7)} {fnum(body_top - GRID)} 0)
      {effects()}
    )
    (property "Footprint" {q(sym.footprint)}
      (at 0 {fnum(body_bot + GRID)} 0)
      {effects(hide=True)}
    )
    (property "Datasheet" {q(sym.datasheet)}
      (at 0 0 0)
      {effects(hide=True)}
    )
    (property "Description" {q(sym.desc)}
      (at 0 0 0)
      {effects(hide=True)}
    )
    (symbol {q(sym.name + "_0_1")}
      (rectangle
        (start {fnum(body_left)} {fnum(body_top)})
        (end {fnum(body_right)} {fnum(body_bot)})
        (stroke
          (width 0.254)
          (type default)
        )
        (fill
          (type background)
        )
      )
    )
    (symbol {q(sym.name + "_1_1")}
{chr(10).join(pins)}
    )
  )"""


@dataclass
class Instance:
    sym: SymDef
    ref: str
    value: str
    x: float
    y: float
    fields: dict[str, str] | None = None


@dataclass
class LibInstance:
    lib_id: str
    ref: str
    value: str
    footprint: str
    x: float
    y: float
    pin_nets: dict[str, str | None]
    pin_style: str = "vertical"
    datasheet: str = ""
    desc: str = ""
    fields: dict[str, str] | None = None


def pin_positions(sym: SymDef, x: float, y: float) -> dict[str, tuple[float, float, str]]:
    idx = {"L": 0, "R": 0}
    pos = {}
    for p in sym.pins:
        px, py, _ = pin_xy(p, idx, sym.width)
        # KiCad symbol-local Y increases upward; sheet Y increases downward.
        pos[p.num] = (x + px, y - py, p.side)
    return pos


def prop(name: str, value: str, x: float, y: float, hide: bool = False) -> str:
    return f"""    (property {q(name)} {q(value)}
      (at {fnum(x)} {fnum(y)} 0)
      {effects(hide=hide)}
    )"""


def symbol_instance(inst: Instance) -> tuple[str, list[str]]:
    sym = inst.sym
    pin_pos = pin_positions(sym, inst.x, inst.y)
    top_y = inst.y - 5.08
    body_left = inst.x - sym.width / 2
    props = [
        prop("Reference", inst.ref, body_left, top_y),
        prop("Value", inst.value, body_left + 17.78, top_y),
        prop("Footprint", sym.footprint, inst.x, inst.y + 2.54, hide=True),
        prop("Datasheet", sym.datasheet, inst.x, inst.y, hide=True),
        prop("Description", sym.desc, inst.x, inst.y, hide=True),
    ]
    for k, v in (inst.fields or {}).items():
        props.append(prop(k, v, inst.x, inst.y, hide=True))

    pin_refs = "\n".join(
        f"""    (pin {q(p.num)}
      (uuid {q(uid())})
    )"""
        for p in sym.pins
    )
    body = f"""  (symbol
    (lib_id {q(LIB + ":" + sym.name)})
    (at {fnum(inst.x)} {fnum(inst.y)} 0)
    (unit 1)
    (exclude_from_sim no)
    (in_bom yes)
    (on_board yes)
    (dnp no)
    (uuid {q(uid())})
{chr(10).join(props)}
{pin_refs}
    (instances
      (project {q(PROJECT)}
        (path "/"
          (reference {q(inst.ref)})
          (unit 1)
        )
      )
    )
  )"""
    extras: list[str] = []
    for p in sym.pins:
        px, py, side = pin_pos[p.num]
        if p.net:
            out = px - 7.62 if side == "L" else px + 7.62
            rot = 180 if side == "L" else 0
            extras.append(wire(px, py, out, py))
            extras.append(label(p.net, out, py, rot))
        elif p.nc:
            extras.append(no_connect(px, py))
    return body, extras


def lib_pin_positions(inst: LibInstance) -> dict[str, tuple[float, float, str]]:
    if inst.pin_style == "horizontal":
        local = {"1": (-3.81, 0, "L"), "2": (3.81, 0, "R")}
    else:
        local = {"1": (0, 3.81, "L"), "2": (0, -3.81, "R")}
    return {num: (inst.x + dx, inst.y - dy, side) for num, (dx, dy, side) in local.items()}


def library_symbol_instance(inst: LibInstance) -> tuple[str, list[str]]:
    top_y = inst.y - 5.08
    body_left = inst.x - 5.08
    props = [
        prop("Reference", inst.ref, body_left, top_y),
        prop("Value", inst.value, body_left + 7.62, top_y),
        prop("Footprint", inst.footprint, inst.x, inst.y + 2.54, hide=True),
        prop("Datasheet", inst.datasheet, inst.x, inst.y, hide=True),
        prop("Description", inst.desc, inst.x, inst.y, hide=True),
    ]
    for k, v in (inst.fields or {}).items():
        props.append(prop(k, v, inst.x, inst.y, hide=True))
    pin_refs = "\n".join(
        f"""    (pin {q(num)}
      (uuid {q(uid())})
    )"""
        for num in inst.pin_nets
    )
    body = f"""  (symbol
    (lib_id {q(inst.lib_id)})
    (at {fnum(inst.x)} {fnum(inst.y)} 0)
    (unit 1)
    (exclude_from_sim no)
    (in_bom yes)
    (on_board yes)
    (dnp no)
    (uuid {q(uid())})
{chr(10).join(props)}
{pin_refs}
    (instances
      (project {q(PROJECT)}
        (path "/"
          (reference {q(inst.ref)})
          (unit 1)
        )
      )
    )
  )"""
    extras: list[str] = []
    pin_pos = lib_pin_positions(inst)
    for num, net in inst.pin_nets.items():
        px, py, side = pin_pos[num]
        if net:
            out = px - 7.62 if side == "L" else px + 7.62
            rot = 180 if side == "L" else 0
            extras.append(wire(px, py, out, py))
            extras.append(label(net, out, py, rot))
        else:
            extras.append(no_connect(px, py))
    return body, extras


def wire(x1: float, y1: float, x2: float, y2: float) -> str:
    return f"""  (wire
    (pts
      (xy {fnum(x1)} {fnum(y1)}) (xy {fnum(x2)} {fnum(y2)})
    )
    (stroke
      (width 0)
      (type default)
    )
    (uuid {q(uid())})
  )"""


def label(text: str, x: float, y: float, rot: int = 0) -> str:
    return f"""  (label {q(text)}
    (at {fnum(x)} {fnum(y)} {rot})
    {effects(justify="left bottom")}
    (uuid {q(uid())})
  )"""


def no_connect(x: float, y: float) -> str:
    return f"""  (no_connect
    (at {fnum(x)} {fnum(y)})
    (uuid {q(uid())})
  )"""


def text_block(text: str, x: float, y: float, size: float = 1.27) -> str:
    return f"""  (text {q(text)}
    (at {fnum(x)} {fnum(y)} 0)
    {effects(size=size, justify="left")}
    (uuid {q(uid())})
  )"""


def poly_box(x1: float, y1: float, x2: float, y2: float) -> str:
    return f"""  (polyline
    (pts
      (xy {fnum(x1)} {fnum(y1)}) (xy {fnum(x2)} {fnum(y1)}) (xy {fnum(x2)} {fnum(y2)}) (xy {fnum(x1)} {fnum(y2)}) (xy {fnum(x1)} {fnum(y1)})
    )
    (stroke
      (width 0.1524)
      (type dash)
    )
    (fill
      (type none)
    )
    (uuid {q(uid())})
  )"""


def ksz_symbol() -> SymDef:
    p = []
    add = p.append
    for num, name, net in [
        ("62", "TXRX1P_A", "P1_TR_A_P"),
        ("63", "TXRX1M_A", "P1_TR_A_N"),
        ("1", "TXRX1P_B", "P1_TR_B_P"),
        ("2", "TXRX1M_B", "P1_TR_B_N"),
        ("3", "TXRX1P_C", "P1_TR_C_P"),
        ("4", "TXRX1M_C", "P1_TR_C_N"),
        ("6", "TXRX1P_D", "P1_TR_D_P"),
        ("7", "TXRX1M_D", "P1_TR_D_N"),
        ("26", "VDDIO", "+3V3"),
        ("38", "VDDIO", "+3V3"),
        ("54", "VDDIO", "+3V3"),
        ("8", "AVDDH", "+2V5_AVDDH"),
        ("19", "AVDDH", "+2V5_AVDDH"),
        ("61", "AVDDH", "+2V5_AVDDH"),
        ("5", "AVDDL", "+1V2_AVDDL"),
        ("11", "AVDDL", "+1V2_AVDDL"),
        ("16", "AVDDL", "+1V2_AVDDL"),
        ("56", "AVDDL", "+1V2_AVDDL"),
        ("64", "AVDDL", "+1V2_AVDDL"),
        ("20", "DVDDL", "+1V2_DVDDL"),
        ("34", "DVDDL", "+1V2_DVDDL"),
        ("37", "DVDDL", "+1V2_DVDDL"),
        ("41", "DVDDL", "+1V2_DVDDL"),
        ("51", "DVDDL", "+1V2_DVDDL"),
        ("55", "DVDDL", "+1V2_DVDDL"),
        ("59", "GND", "GND"),
        ("65", "EPAD", "GND"),
        ("60", "ISET", "KSZ_ISET"),
        ("58", "XI", "KSZ_XI"),
        ("57", "XO", "KSZ_XO"),
    ]:
        add(Pin(num, name, "L", net=net))
    for num, name, net in [
        ("9", "TXRX2P_A", "P2_KSZ_A_P"),
        ("10", "TXRX2M_A", "P2_KSZ_A_N"),
        ("12", "TXRX2P_B", "P2_KSZ_B_P"),
        ("13", "TXRX2M_B", "P2_KSZ_B_N"),
        ("14", "TXRX2P_C", "P2_KSZ_C_P"),
        ("15", "TXRX2M_C", "P2_KSZ_C_N"),
        ("17", "TXRX2P_D", "P2_KSZ_D_P"),
        ("18", "TXRX2M_D", "P2_KSZ_D_N"),
        ("33", "TX_CLK/REFCLKI", "RGMII_TXC"),
        ("35", "TX_EN/TX_CTL", "RGMII_TX_CTL"),
        ("29", "TXD3", "RGMII_TXD3"),
        ("30", "TXD2", "RGMII_TXD2"),
        ("31", "TXD1", "RGMII_TXD1"),
        ("32", "TXD0", "RGMII_TXD0"),
        ("25", "RX_CLK/REFCLKO", "RGMII_RXC"),
        ("27", "RX_DV/CRS_DV/RX_CTL", "RGMII_RX_CTL"),
        ("21", "RXD3", "RGMII_RXD3"),
        ("22", "RXD2", "RGMII_RXD2"),
        ("23", "RXD1", "RGMII_RXD1"),
        ("24", "RXD0", "RGMII_RXD0"),
        ("49", "SCS_N", "SWITCH_SPI_CS_N"),
        ("50", "SCL/MDC", "SWITCH_MDC_SCL"),
        ("47", "SDO", "SWITCH_SPI_MISO"),
        ("48", "SDI/SDA/MDIO", "SWITCH_MDIO_SDA"),
        ("45", "INTRP_N", "SWITCH_INTP_N"),
        ("46", "RESET_N", "SWITCH_RESET_N"),
        ("44", "PME_N", "SWITCH_PME_N"),
        ("39", "GPIO_1", "SWITCH_GPIO1"),
        ("40", "GPIO_2", "SWITCH_GPIO2"),
    ]:
        add(Pin(num, name, "R", net=net))
    for num, name in [("28", "RX_ER"), ("36", "TX_ER"), ("42", "LED2_0"), ("43", "LED2_1"), ("52", "LED1_0"), ("53", "LED1_1")]:
        add(Pin(num, name, "R", nc=True))
    return SymDef(
        "KSZ9563R",
        "U",
        "KSZ9563R",
        "Package_DFN_QFN:QFN-64-1EP_8x8mm_P0.4mm_EP6.5x6.5mm_ThermalVias",
        "https://ww1.microchip.com/downloads/aemDocuments/documents/OTH/ProductDocuments/DataSheets/KSZ9563R-Data-Sheet-DS00002419D.pdf",
        "Microchip 3-port gigabit Ethernet switch, 2 PHY + RGMII/MII/RMII MAC port",
        p,
        50.8,
    )


def lan_symbol() -> SymDef:
    p = []
    add = p.append
    for num, name, net in [
        ("1", "TR0P", "LAN_TR0_P"),
        ("2", "TR0N", "LAN_TR0_N"),
        ("4", "TR1P", "LAN_TR1_P"),
        ("5", "TR1N", "LAN_TR1_N"),
        ("7", "TR2P", "LAN_TR2_P"),
        ("8", "TR2N", "LAN_TR2_N"),
        ("10", "TR3P", "LAN_TR3_P"),
        ("11", "TR3N", "LAN_TR3_N"),
        ("3", "VDD25A", "LAN_VDD25"),
        ("6", "VDD25A", "LAN_VDD25"),
        ("9", "VDD25A", "LAN_VDD25"),
        ("12", "VDD25A", "LAN_VDD25"),
        ("13", "VDD12_SW_OUT", "LAN_VDD12_SW_OUT"),
        ("14", "VDD_SW_IN", "+3V3"),
        ("15", "VDD12_SW_FB", "LAN_VDD12"),
        ("20", "VDDVARIO", "+3V3"),
        ("21", "VDD12CORE", "LAN_VDD12"),
        ("25", "VDD12A", "LAN_VDD12"),
        ("30", "VDD12A", "LAN_VDD12"),
        ("36", "VDDVARIO", "+3V3"),
        ("38", "VDD33A", "+3V3"),
        ("39", "VDDVARIO", "+3V3"),
        ("42", "VDD12CORE", "LAN_VDD12"),
        ("44", "VDD12A", "LAN_VDD12"),
        ("45", "VDD25_REG_OUT", "LAN_VDD25_LDO"),
        ("46", "VDD33_REG_IN", "+3V3"),
        ("49", "EPAD", "GND"),
    ]:
        add(Pin(num, name, "L", net=net))
    for num, name, net in [
        ("26", "USB2_DP", "USB2_DP"),
        ("27", "USB2_DM", "USB2_DM"),
        ("28", "USB3_TXDP", "USB3_TX_P"),
        ("29", "USB3_TXDM", "USB3_TX_N"),
        ("31", "USB3_RXDP", "USB3_RX_P"),
        ("32", "USB3_RXDM", "USB3_RX_N"),
        ("23", "VBUS_DET", "USB_VBUS"),
        ("35", "RESET_N/PME_CLEAR", "LAN_RESET_N"),
        ("22", "PME_N/GPIO4", "LAN_PME_N"),
        ("24", "SUSPEND_N/LED2/GPIO5", "LAN_SUSPEND_N"),
        ("33", "LED3/GPIO6", "LAN_GPIO6_LED3"),
        ("43", "PME_MODE/GPIO7", "LAN_PME_MODE"),
        ("37", "USBRBIAS", "LAN_USBRBIAS"),
        ("47", "REF_REXT", "LAN_REF_REXT"),
        ("48", "REF_FILT", "LAN_REF_FILT"),
        ("40", "XI", "LAN_XI"),
        ("41", "XO", "LAN_XO"),
        ("34", "TEST", "GND"),
    ]:
        add(Pin(num, name, "R", net=net))
    for num, name in [("16", "EECS/GPIO0"), ("17", "EEDI/GPIO1"), ("18", "EEDO/LED0/GPIO2"), ("19", "EECLK/LED1/GPIO3")]:
        add(Pin(num, name, "R", nc=True))
    return SymDef(
        "LAN7800",
        "U",
        "LAN7800",
        "Package_DFN_QFN:QFN-48-1EP_6x6mm_P0.4mm_EP4.3x4.3mm_ThermalVias",
        "https://ww1.microchip.com/downloads/aemDocuments/documents/UNG/ProductDocuments/DataSheets/LAN7800-Data-Sheet-DS00001992.pdf",
        "Microchip SuperSpeed USB 3.1 Gen 1 to 10/100/1000 Ethernet controller",
        p,
        50.8,
    )


def header_symbol(name: str, count: int) -> SymDef:
    pins = [Pin(str(i), f"Pin_{i}", "L") for i in range(1, count + 1)]
    return SymDef(
        name,
        "J",
        name,
        f"Connector_PinHeader_2.54mm:PinHeader_1x{count:02d}_P2.54mm_Vertical",
        "",
        f"1x{count} 2.54mm male header",
        pins,
        17.78,
    )


def two_pin_symbol(name: str, ref: str, value: str, footprint: str, desc: str) -> SymDef:
    return SymDef(
        name,
        ref,
        value,
        footprint,
        "",
        desc,
        [Pin("1", "1", "L"), Pin("2", "2", "R")],
        12.7,
    )


def regulator_symbol(name: str, value: str, footprint: str, desc: str) -> SymDef:
    pins = [
        Pin("1", "VIN", "L"),
        Pin("2", "EN", "L"),
        Pin("3", "GND", "L"),
        Pin("4", "SW", "R"),
        Pin("5", "FB", "R"),
        Pin("6", "BST", "R"),
    ]
    return SymDef(name, "U", value, footprint, "", desc, pins, 25.4)


def ldo_symbol() -> SymDef:
    pins = [Pin("1", "IN", "L"), Pin("3", "EN", "L"), Pin("2", "GND", "L"), Pin("5", "OUT", "R"), Pin("4", "NC", "R", nc=True)]
    return SymDef(
        "TLV75525PDBV",
        "U",
        "TLV75525PDBV",
        "Package_TO_SOT_SMD:SOT-23-5",
        "https://www.ti.com/lit/ds/symlink/tlv755p.pdf",
        "TI 500mA low-Iq LDO, fixed 2.5V output",
        pins,
        25.4,
    )


def crystal_symbol(name: str) -> SymDef:
    return SymDef(
        name,
        "Y",
        "25MHz",
        "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm",
        "",
        "25MHz crystal, +/-50ppm or better; choose load caps for selected crystal CL",
        [Pin("1", "XI", "L"), Pin("2", "XO", "R")],
        15.24,
    )


def magjack_symbol() -> SymDef:
    left = [
        ("11", "MX1+"),
        ("10", "MX1-"),
        ("12", "MXCT1"),
        ("4", "MX2+"),
        ("5", "MX2-"),
        ("6", "MXCT2"),
        ("3", "MX3+"),
        ("2", "MX3-"),
        ("1", "MXCT3"),
        ("8", "MX4+"),
        ("9", "MX4-"),
        ("7", "MXCT4"),
        ("16", "LED_L_A"),
        ("15", "LED_L_K"),
        ("14", "LED_R_A"),
        ("13", "LED_R_K"),
        ("SH", "SHIELD"),
    ]
    return SymDef(
        "RJ45_Gigabit_MagJack",
        "J",
        "Pulse JK0654219NL",
        "Connector_RJ:RJ45_Pulse_JK0654219NL_Horizontal",
        "https://datasheet4u.com/pdf-down/J/K/0/JK0654219_PulseATechnitrol.pdf",
        "1-port 10/100/1000Base-T RJ45 MagJack with integrated magnetics and LEDs",
        [Pin(num, name, "L") for num, name in left],
        35.56,
    )


def transformer_symbol() -> SymDef:
    pairs: list[tuple[str, str, str]] = []
    for i, pair in enumerate(["A", "B", "C", "D"], start=1):
        pairs += [(str(len(pairs) + 1), f"K_{pair}+", "L"), (str(len(pairs) + 2), f"K_{pair}-", "L"), (str(len(pairs) + 3), f"K_CT_{pair}", "L")]
    for i, pair in enumerate(["A", "B", "C", "D"], start=1):
        pairs += [(str(len(pairs) + 1), f"L_{pair}+", "R"), (str(len(pairs) + 2), f"L_{pair}-", "R"), (str(len(pairs) + 3), f"L_CT_{pair}", "R")]
    pins = [Pin(num, name, side) for num, name, side in pairs]
    return SymDef(
        "GbE_4Pair_Isolation",
        "T",
        "4-pair 1:1 LAN magnetics",
        "Transformer_SMD:Transformer_Ethernet_YDS_30F-51NL_SO-24_7.1x15.1mm",
        "",
        "Placeholder 1000BASE-T isolation/coupling transformer for internal PHY-to-PHY link",
        pins,
        35.56,
    )


def all_symbols() -> dict[str, SymDef]:
    syms = {
        "ksz": ksz_symbol(),
        "lan": lan_symbol(),
        "magjack": magjack_symbol(),
        "xfmr": transformer_symbol(),
        "hdr2": header_symbol("Header_1x02", 2),
        "hdr4": header_symbol("Header_1x04", 4),
        "hdr8": header_symbol("Header_1x08", 8),
        "hdr10": header_symbol("Header_1x10", 10),
        "hdr20": header_symbol("Header_1x20", 20),
        "buck": regulator_symbol("AP62300WU_Buck", "AP62300WU", "Package_TO_SOT_SMD:TSOT-23-6", "3A adjustable buck regulator"),
        "ldo": ldo_symbol(),
    }
    return syms


def inst_with_pin_nets(inst: Instance, nets: dict[str, str | None]) -> Instance:
    for p in inst.sym.pins:
        if p.num in nets:
            p.net = nets[p.num]
            p.nc = nets[p.num] is None
    return inst


def add_manual_component(sym: SymDef, ref: str, value: str, x: float, y: float, nets: dict[str, str | None], fields=None) -> Instance:
    copied = SymDef(sym.name, sym.ref, sym.value, sym.footprint, sym.datasheet, sym.desc, [Pin(p.num, p.name, p.side, p.etype, p.net, p.nc) for p in sym.pins], sym.width)
    return inst_with_pin_nets(Instance(copied, ref, value, x, y, fields=fields or {}), nets)


def add_lib_component(
    lib_id: str,
    ref: str,
    value: str,
    footprint: str,
    x: float,
    y: float,
    nets: dict[str, str | None],
    pin_style: str = "vertical",
    desc: str = "",
    fields=None,
) -> LibInstance:
    return LibInstance(lib_id, ref, value, footprint, x, y, nets, pin_style=pin_style, desc=desc, fields=fields or {})


BOM_EXTRA_FIELDS = ["Manufacturer", "MPN", "Mfr_Region", "Source", "Notes"]


def part_fields(manufacturer: str, mpn: str, region: str, source: str, notes: str = "") -> dict[str, str]:
    return {
        "Manufacturer": manufacturer,
        "MPN": mpn,
        "Mfr_Region": region,
        "Source": source,
        "Notes": notes,
    }


PART_FIELDS_BY_REF: dict[str, dict[str, str]] = {
    "U1": part_fields(
        "Microchip Technology",
        "KSZ9563RNXI",
        "USA-based",
        "https://www.microchip.com/en-us/product/ksz9563",
    ),
    "U2": part_fields(
        "Microchip Technology",
        "LAN7800-I/Y9X",
        "USA-based",
        "https://www.microchip.com/en-us/product/lan7800",
    ),
    "U3": part_fields(
        "Diodes Incorporated",
        "AP62300WU-7",
        "USA-based",
        "https://www.diodes.com/part/view/AP62300",
    ),
    "U4": part_fields(
        "Diodes Incorporated",
        "AP62300WU-7",
        "USA-based",
        "https://www.diodes.com/part/view/AP62300",
    ),
    "U5": part_fields(
        "Texas Instruments",
        "TLV75525PDBVR",
        "USA-based",
        "https://www.ti.com/product/TLV755P",
    ),
    "J1": part_fields(
        "Pulse Electronics",
        "JK0654219NL",
        "USA-based legacy Pulse; verify current supply chain",
        "https://datasheet4u.com/pdf-down/J/K/0/JK0654219_PulseATechnitrol.pdf",
        "10/100/1000Base-T MagJack; LEDs intentionally left NC in this first-pass schematic",
    ),
    "T1": part_fields(
        "YDS Tech",
        "30F-51NL",
        "China-based exception",
        "https://www.lcsc.com/product-detail/C123168.html",
        "Matches KiCad library footprint; replace with a non-China qualified magnetics part before release if required",
    ),
    "J2": part_fields("Samtec", "TSW-110-07-G-S", "USA-based", "https://www.samtec.com/products/tsw-110-07-g-s-010"),
    "J3": part_fields("Samtec", "TSW-120-07-G-S", "USA-based", "https://www.samtec.com/products/tsw-120-07-g-s"),
    "J4": part_fields("Samtec", "TSW-108-07-G-S", "USA-based", "https://www.samtec.com/products/tsw-108-07-g-s"),
    "J5": part_fields("Samtec", "TSW-102-07-G-S", "USA-based", "https://www.samtec.com/products/tsw-102-07-g-s"),
    "J6": part_fields("Samtec", "TSW-104-07-G-S", "USA-based", "https://www.samtec.com/products/tsw-104-07-g-s"),
    "L1": part_fields(
        "Bourns",
        "SRN6045TA-2R2Y",
        "USA-based",
        "https://www.bourns.com/products/magnetic-products/details/power-inductors-smd-semi-shielded/srn6045ta",
    ),
    "L2": part_fields(
        "Bourns",
        "SRN6045TA-2R2Y",
        "USA-based",
        "https://www.bourns.com/products/magnetic-products/details/power-inductors-smd-semi-shielded/srn6045ta",
    ),
    "L3": part_fields(
        "Bourns",
        "SRN4018-3R3M",
        "USA-based",
        "https://www.bourns.com/docs/product-datasheets/srn4018.pdf",
    ),
    "Y1": part_fields(
        "Abracon",
        "ABM8G-25.000MHZ-B4Y-T",
        "USA-based",
        "https://www.digikey.com/en/products/detail/abracon-llc/ABM8G-25-000MHZ-B4Y-T/2218043",
        "Load caps should be tuned against the selected crystal CL and board parasitics",
    ),
    "Y2": part_fields(
        "Abracon",
        "ABM8G-25.000MHZ-B4Y-T",
        "USA-based",
        "https://www.digikey.com/en/products/detail/abracon-llc/ABM8G-25-000MHZ-B4Y-T/2218043",
        "Load caps should be tuned against the selected crystal CL and board parasitics",
    ),
}

for _ref in ("FB1", "FB2", "FB3"):
    PART_FIELDS_BY_REF[_ref] = part_fields(
        "Murata Electronics",
        "BLM15AG121SN1D",
        "Japan-based",
        "https://www.digikey.com/en/products/detail/murata-electronics/BLM15AG121SN1D/584216",
    )

for _ref, _mpn in {
    "R1": "CRCW04026K04FKED",
    "R2": "CRCW04022K00FKED",
    "R3": "CRCW040212K0FKED",
    "R4": "CRCW040210K0FKED",
    "R5": "CRCW040210K0FKED",
    "R6": "CRCW0402316KFKED",
    "R7": "CRCW0402100KFKED",
    "R8": "CRCW040249K9FKED",
    "R9": "CRCW0402100KFKED",
}.items():
    PART_FIELDS_BY_REF[_ref] = part_fields(
        "Vishay Dale",
        _mpn,
        "USA-based",
        "https://www.vishay.com/en/resistors-linear/fixed/surface-mount/chip-resistors/",
    )

for _ref, _mpn, _source in [
    ("C1", "GRM31CR61A476ME15L", "https://www.murata.com/en-us/products/productdetail?partno=GRM31CR61A476ME15%23"),
    ("C2", "GRM188R60J226MEA0D", "https://www.murata.com/en-us/products/productdetail?partno=GRM188R60J226MEA0D"),
    ("C3", "GRM188R60J226MEA0D", "https://www.murata.com/en-us/products/productdetail?partno=GRM188R60J226MEA0D"),
    ("C4", "GRM188R60J226MEA0D", "https://www.murata.com/en-us/products/productdetail?partno=GRM188R60J226MEA0D"),
    ("C5", "GRM155R61A105KE15D", "https://www.digikey.com/en/products/detail/murata-electronics/GRM155R61A105KE15D/965904"),
    ("C6", "GRM155R60J106ME15D", "https://www.murata.com/en-us/products/productdetail?partno=GRM155R60J106ME15D"),
    ("C7", "GRM155R61A105KE15D", "https://www.digikey.com/en/products/detail/murata-electronics/GRM155R61A105KE15D/965904"),
    ("C8", "GRM1555C1H180JA01D", "https://www.digikey.com/en/products/detail/murata-electronics/GRM1555C1H180JA01D/2854383"),
    ("C9", "GRM1555C1H180JA01D", "https://www.digikey.com/en/products/detail/murata-electronics/GRM1555C1H180JA01D/2854383"),
    ("C10", "GRM1555C1H180JA01D", "https://www.digikey.com/en/products/detail/murata-electronics/GRM1555C1H180JA01D/2854383"),
    ("C11", "GRM1555C1H180JA01D", "https://www.digikey.com/en/products/detail/murata-electronics/GRM1555C1H180JA01D/2854383"),
    ("C12", "GRM155R71C104KA88D", "https://www.murata.com/en-us/products/productdetail?partno=GRM155R71C104KA88D"),
    ("C13", "GRM155R71C104KA88D", "https://www.murata.com/en-us/products/productdetail?partno=GRM155R71C104KA88D"),
    ("C14", "GRM155R71C104KA88D", "https://www.murata.com/en-us/products/productdetail?partno=GRM155R71C104KA88D"),
    ("C15", "GRM155R71C104KA88D", "https://www.murata.com/en-us/products/productdetail?partno=GRM155R71C104KA88D"),
    ("C16", "GRM155R71C104KA88D", "https://www.murata.com/en-us/products/productdetail?partno=GRM155R71C104KA88D"),
    ("C17", "GRM155R71C104KA88D", "https://www.murata.com/en-us/products/productdetail?partno=GRM155R71C104KA88D"),
    ("C18", "GRM155R61A105KE15D", "https://www.digikey.com/en/products/detail/murata-electronics/GRM155R61A105KE15D/965904"),
    ("C19", "GRM1555C1H102JA01D", "https://www.digikey.com/en/products/detail/murata-electronics/GRM1555C1H102JA01D/702785"),
]:
    PART_FIELDS_BY_REF[_ref] = part_fields("Murata Electronics", _mpn, "Japan-based", _source)


def apply_part_fields(instances: list[Instance | LibInstance]) -> None:
    missing = []
    for inst in instances:
        ref = instance_ref(inst)
        fields = dict(inst.fields or {})
        if ref in PART_FIELDS_BY_REF:
            fields.update(PART_FIELDS_BY_REF[ref])
        else:
            missing.append(ref)
        inst.fields = fields
    if missing:
        raise ValueError(f"Missing part field selections for: {', '.join(sorted(missing, key=ref_sort_key))}")


def build_instances(syms: dict[str, SymDef]) -> list[Instance | LibInstance]:
    instances: list[Instance | LibInstance] = [
        Instance(syms["ksz"], "U1", "KSZ9563R", 180.34, 228.6),
        Instance(syms["lan"], "U2", "LAN7800", 320.04, 228.6),
        add_manual_component(syms["magjack"], "J1", "RJ45 with GbE magnetics", 370.84, 60.96, {
            "11": "P1_TR_A_P", "10": "P1_TR_A_N", "12": "+2V5_AVDDH",
            "4": "P1_TR_B_P", "5": "P1_TR_B_N", "6": "+2V5_AVDDH",
            "3": "P1_TR_C_P", "2": "P1_TR_C_N", "1": "+2V5_AVDDH",
            "8": "P1_TR_D_P", "9": "P1_TR_D_N", "7": "+2V5_AVDDH",
            "16": None, "15": None, "14": None, "13": None, "SH": "CHASSIS_SHIELD",
        }),
        add_manual_component(syms["xfmr"], "T1", "GbE PHY-to-PHY magnetics", 226.06, 60.96, {
            "1": "P2_KSZ_A_P", "2": "P2_KSZ_A_N", "3": "+2V5_AVDDH",
            "4": "P2_KSZ_B_P", "5": "P2_KSZ_B_N", "6": "+2V5_AVDDH",
            "7": "P2_KSZ_C_P", "8": "P2_KSZ_C_N", "9": "+2V5_AVDDH",
            "10": "P2_KSZ_D_P", "11": "P2_KSZ_D_N", "12": "+2V5_AVDDH",
            "13": "LAN_TR0_P", "14": "LAN_TR0_N", "15": "LAN_VDD25",
            "16": "LAN_TR1_P", "17": "LAN_TR1_N", "18": "LAN_VDD25",
            "19": "LAN_TR2_P", "20": "LAN_TR2_N", "21": "LAN_VDD25",
            "22": "LAN_TR3_P", "23": "LAN_TR3_N", "24": "LAN_VDD25",
        }),
        add_manual_component(syms["hdr10"], "J2", "USB3/USB2 header", 420.37, 134.62, {
            "1": "USB_VBUS", "2": "GND", "3": "USB2_DP", "4": "USB2_DM", "5": "USB3_TX_P",
            "6": "USB3_TX_N", "7": "USB3_RX_P", "8": "USB3_RX_N", "9": "LAN_RESET_N", "10": "LAN_PME_N",
        }),
        add_manual_component(syms["hdr20"], "J3", "RGMII/control header", 420.37, 241.3, {
            "1": "RGMII_TXC", "2": "RGMII_TX_CTL", "3": "RGMII_TXD0", "4": "RGMII_TXD1",
            "5": "RGMII_TXD2", "6": "RGMII_TXD3", "7": "RGMII_RXC", "8": "RGMII_RX_CTL",
            "9": "RGMII_RXD0", "10": "RGMII_RXD1", "11": "RGMII_RXD2", "12": "RGMII_RXD3",
            "13": "SWITCH_MDIO_SDA", "14": "SWITCH_MDC_SCL", "15": "SWITCH_INTP_N",
            "16": "SWITCH_RESET_N", "17": "SWITCH_PME_N", "18": "+3V3", "19": "GND", "20": "GND",
        }),
        add_manual_component(syms["hdr8"], "J4", "Switch management header", 420.37, 269.24, {
            "1": "SWITCH_SPI_CS_N", "2": "SWITCH_SPI_MISO", "3": "SWITCH_MDIO_SDA", "4": "SWITCH_MDC_SCL",
            "5": "SWITCH_GPIO1", "6": "SWITCH_GPIO2", "7": "+3V3", "8": "GND",
        }),
        add_manual_component(syms["hdr4"], "J6", "LAN aux header", 420.37, 177.8, {
            "1": "LAN_PME_MODE", "2": "LAN_GPIO6_LED3", "3": "LAN_SUSPEND_N", "4": "GND",
        }),
        add_manual_component(syms["hdr2"], "J5", "5V input >=1A", 35.56, 30.48, {"1": "+5V_IN", "2": "GND"}),
        add_manual_component(syms["buck"], "U3", "AP62300WU 3.3V/3A buck", 73.66, 25.4, {
            "1": "+5V_IN", "2": "+5V_IN", "3": "GND", "4": "BUCK3V3_SW", "5": "BUCK3V3_FB", "6": "BUCK3V3_BST",
        }),
        add_manual_component(syms["buck"], "U4", "AP62300WU 1.2V/3A buck", 73.66, 63.5, {
            "1": "+5V_IN", "2": "+5V_IN", "3": "GND", "4": "BUCK1V2_SW", "5": "BUCK1V2_FB", "6": "BUCK1V2_BST",
        }),
        add_manual_component(syms["ldo"], "U5", "TLV75525PDBV 2.5V/500mA", 73.66, 104.14, {
            "1": "+3V3", "3": "+3V3", "2": "GND", "5": "+2V5_RAW", "4": None,
        }),
        add_lib_component("Device:FerriteBead", "FB1", "100R@100MHz", "Inductor_SMD:L_0402_1005Metric", 114.3, 101.6, {"1": "+2V5_RAW", "2": "+2V5_AVDDH"}, desc="Ferrite bead"),
        add_lib_component("Device:FerriteBead", "FB2", "100R@100MHz", "Inductor_SMD:L_0402_1005Metric", 114.3, 116.84, {"1": "+1V2_DVDDL", "2": "+1V2_AVDDL"}, desc="Ferrite bead"),
        add_lib_component("Device:FerriteBead", "FB3", "100R@100MHz", "Inductor_SMD:L_0402_1005Metric", 256.54, 170.18, {"1": "LAN_VDD25_LDO", "2": "LAN_VDD25"}, desc="Ferrite bead"),
        add_lib_component("Device:L", "L1", "2.2uH >=3A", "Inductor_SMD:L_Bourns_SRN6045TA", 114.3, 27.94, {"1": "BUCK3V3_SW", "2": "+3V3"}, desc="Inductor"),
        add_lib_component("Device:L", "L2", "2.2uH >=3A", "Inductor_SMD:L_Bourns_SRN6045TA", 114.3, 66.04, {"1": "BUCK1V2_SW", "2": "+1V2_DVDDL"}, desc="Inductor"),
        add_lib_component("Device:L", "L3", "3.3uH LAN7800", "Inductor_SMD:L_Bourns-SRN4018", 266.7, 154.94, {"1": "LAN_VDD12_SW_OUT", "2": "LAN_VDD12"}, desc="Inductor"),
        add_lib_component("Device:Crystal", "Y1", "25MHz KSZ", "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm", 96.52, 154.94, {"1": "KSZ_XI", "2": "KSZ_XO"}, pin_style="horizontal", desc="25MHz crystal"),
        add_lib_component("Device:Crystal", "Y2", "25MHz LAN7800", "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm", 256.54, 190.5, {"1": "LAN_XI", "2": "LAN_XO"}, pin_style="horizontal", desc="25MHz crystal"),
    ]

    # Essential support passives, arranged as clean labeled blocks.
    passives = [
        ("R1", "6.04k 1%", "KSZ_ISET", "GND", 96.52, 134.62),
        ("R2", "2.00k 1%", "LAN_REF_REXT", "GND", 256.54, 175.26),
        ("R3", "12.0k 1%", "LAN_USBRBIAS", "GND", 256.54, 180.34),
        ("R4", "10k", "+3V3", "SWITCH_RESET_N", 35.56, 139.7),
        ("R5", "10k", "+3V3", "SWITCH_INTP_N", 35.56, 144.78),
        ("R6", "316k 1%", "+3V3", "BUCK3V3_FB", 35.56, 50.8),
        ("R7", "100k 1%", "BUCK3V3_FB", "GND", 35.56, 55.88),
        ("R8", "49.9k 1%", "+1V2_DVDDL", "BUCK1V2_FB", 35.56, 81.28),
        ("R9", "100k 1%", "BUCK1V2_FB", "GND", 35.56, 86.36),
    ]
    for ref, value, n1, n2, x, y in passives:
        instances.append(add_lib_component("Device:R", ref, value, "Resistor_SMD:R_0402_1005Metric", x, y, {"1": n1, "2": n2}, desc="Resistor"))

    caps = [
        ("C1", "47uF input bulk", "+5V_IN", "GND", 35.56, 40.64, "Capacitor_SMD:C_1206_3216Metric"),
        ("C2", "22uF 3V3 bulk", "+3V3", "GND", 134.62, 27.94, "Capacitor_SMD:C_0603_1608Metric"),
        ("C3", "22uF 1V2 bulk", "+1V2_DVDDL", "GND", 134.62, 66.04, "Capacitor_SMD:C_0603_1608Metric"),
        ("C4", "22uF 2V5 bulk", "+2V5_AVDDH", "GND", 134.62, 101.6, "Capacitor_SMD:C_0603_1608Metric"),
        ("C5", "1uF LAN REF_FILT", "LAN_REF_FILT", "GND", 284.48, 182.88, "Capacitor_SMD:C_0402_1005Metric"),
        ("C6", "10uF LAN VDD12", "LAN_VDD12", "GND", 284.48, 193.04, "Capacitor_SMD:C_0402_1005Metric"),
        ("C7", "1uF LAN VDD25", "LAN_VDD25", "GND", 284.48, 203.2, "Capacitor_SMD:C_0402_1005Metric"),
        ("C8", "18pF", "KSZ_XI", "GND", 96.52, 162.56, "Capacitor_SMD:C_0402_1005Metric"),
        ("C9", "18pF", "KSZ_XO", "GND", 96.52, 167.64, "Capacitor_SMD:C_0402_1005Metric"),
        ("C10", "18pF", "LAN_XI", "GND", 256.54, 198.12, "Capacitor_SMD:C_0402_1005Metric"),
        ("C11", "18pF", "LAN_XO", "GND", 256.54, 203.2, "Capacitor_SMD:C_0402_1005Metric"),
        ("C12", "0.1uF per KSZ power pin", "+3V3", "GND", 121.92, 180.34, "Capacitor_SMD:C_0402_1005Metric"),
        ("C13", "0.1uF per KSZ AVDDH pin", "+2V5_AVDDH", "GND", 121.92, 190.5, "Capacitor_SMD:C_0402_1005Metric"),
        ("C14", "0.1uF per KSZ 1V2 pin", "+1V2_DVDDL", "GND", 121.92, 200.66, "Capacitor_SMD:C_0402_1005Metric"),
        ("C15", "0.1uF per LAN power pin", "+3V3", "GND", 269.24, 213.36, "Capacitor_SMD:C_0402_1005Metric"),
        ("C16", "0.1uF 3V3 bootstrap", "BUCK3V3_BST", "BUCK3V3_SW", 154.94, 35.56, "Capacitor_SMD:C_0402_1005Metric"),
        ("C17", "0.1uF 1V2 bootstrap", "BUCK1V2_BST", "BUCK1V2_SW", 154.94, 73.66, "Capacitor_SMD:C_0402_1005Metric"),
        ("C18", "1uF LAN VDD25 LDO", "LAN_VDD25_LDO", "GND", 269.24, 172.72, "Capacitor_SMD:C_0402_1005Metric"),
        ("C19", "1nF shield coupling", "CHASSIS_SHIELD", "GND", 370.84, 20.32, "Capacitor_SMD:C_0402_1005Metric"),
    ]
    for ref, value, n1, n2, x, y, fp in caps:
        instances.append(add_lib_component("Device:C", ref, value, fp, x, y, {"1": n1, "2": n2}, desc="Capacitor"))

    apply_part_fields(instances)
    return instances


def schematic() -> str:
    syms = all_symbols()
    instances = build_instances(syms)
    bodies = []
    extras: list[str] = []
    for inst in instances:
        if isinstance(inst, LibInstance):
            body, ext = library_symbol_instance(inst)
        else:
            body, ext = symbol_instance(inst)
        bodies.append(body)
        extras.extend(ext)

    # Functional boxes and notes for readability.
    graphics = [
        poly_box(17.78, 17.78, 149.86, 121.92),
        text_block("Power input and rails", 20.32, 20.32, 1.524),
        poly_box(135.89, 132.08, 230.0, 264.16),
        text_block("KSZ9563R switch core and PHY support", 138.43, 134.62, 1.524),
        poly_box(185.42, 17.78, 429.26, 104.14),
        text_block("Port 1 RJ45 magjack and Port 2 internal Ethernet link", 187.96, 20.32, 1.524),
        poly_box(241.3, 114.3, 429.26, 264.16),
        text_block("LAN7800 USB-to-Ethernet bridge and USB header", 243.84, 116.84, 1.524),
        poly_box(343.0, 190.5, 429.26, 276.86),
        text_block("RGMII, management, and debug headers", 345.44, 193.04, 1.524),
        text_block(
            "Power sizing: KSZ9563R full gigabit typ ~= 0.99 W (2.5V 140mA, 3.3V 35mA, 1.2V 440mA). "
            "LAN7800 SuperSpeed 1000BASE-T typ = 845 mW at 3.3V. "
            "Estimated load ~= 1.84 W before regulator losses; use 5V input rated >=1A, 1.5A preferred. "
            "3V3 and 1V2 bucks are oversized at 3A for margin; 2V5 LDO is 500mA.",
            20.32,
            223.52,
            1.27,
        ),
        text_block(
            "Layout notes: route P1/P2/LAN MDI and USB3 as controlled-impedance differential pairs; keep KSZ/LAN "
            "25MHz crystals close; place one 0.1uF cap at every IC power pin plus shown bulk caps. "
            "T1 is a placeholder for an internal PHY-to-PHY Ethernet coupling method; verify magnetics/biasing before PCB.",
            20.32,
            236.22,
            1.27,
        ),
    ]

    custom_defs = "\n".join(symbol_definition(s, cache=True) for s in syms.values())
    device_defs = "\n".join(cached_library_symbol("Device", name) for name in ["R", "C", "L", "FerriteBead", "Crystal"])
    lib_defs = custom_defs + "\n" + device_defs
    contents = "\n".join(graphics + extras + bodies)
    return f"""(kicad_sch
  (version 20250610)
  (generator "codex_kicad_schematic_generator")
  (generator_version "0.1")
  (uuid {q(uid())})
  (paper "B")
  (title_block
    (title "KSZ9563R + LAN7800 Ethernet Switch Example")
    (date "2026-04-28")
    (rev "A")
    (company "Generated by Codex")
    (comment 1 "Example schematic, not production reviewed")
  )
  (lib_symbols
{lib_defs}
  )
{contents}
  (sheet_instances
    (path "/"
      (page "1")
    )
  )
)"""


def project_file(root_uuid: str) -> str:
    data = {
        "board": {"design_settings": {"defaults": {}, "rule_severities": {}, "rules": {}}, "layer_pairs": []},
        "boards": [f"{PROJECT}.kicad_pcb"],
        "erc": {
            "erc_exclusions": [],
            "meta": {"version": 0},
            "rule_severities": {
                "pin_not_connected": "warning",
                "pin_to_pin": "warning",
                "power_pin_not_driven": "warning",
                "label_dangling": "warning",
                "wire_dangling": "warning",
                "unconnected_wire_endpoint": "warning",
            },
        },
        "libraries": {"pinned_symbol_libs": [LIB], "pinned_footprint_libs": []},
        "meta": {"filename": f"{PROJECT}.kicad_pro", "version": 3},
        "net_settings": {
            "classes": [
                {
                    "name": "Default",
                    "clearance": 0.2,
                    "track_width": 0.2,
                    "via_diameter": 0.6,
                    "via_drill": 0.3,
                    "diff_pair_width": 0.15,
                    "diff_pair_gap": 0.18,
                    "wire_width": 6,
                    "bus_width": 12,
                    "line_style": 0,
                    "priority": 2147483647,
                    "pcb_color": "rgba(0, 0, 0, 0.000)",
                    "schematic_color": "rgba(0, 0, 0, 0.000)",
                },
                {
                    "name": "100ohm_diff",
                    "clearance": 0.15,
                    "track_width": 0.15,
                    "via_diameter": 0.45,
                    "via_drill": 0.25,
                    "diff_pair_width": 0.15,
                    "diff_pair_gap": 0.18,
                    "wire_width": 6,
                    "bus_width": 12,
                    "line_style": 0,
                    "priority": 1,
                    "pcb_color": "rgb(0, 170, 255)",
                    "schematic_color": "rgba(0, 0, 0, 0.000)",
                },
                {
                    "name": "power",
                    "clearance": 0.25,
                    "track_width": 0.5,
                    "via_diameter": 0.8,
                    "via_drill": 0.4,
                    "diff_pair_width": 0.15,
                    "diff_pair_gap": 0.18,
                    "wire_width": 6,
                    "bus_width": 12,
                    "line_style": 0,
                    "priority": 2,
                    "pcb_color": "rgb(255, 128, 0)",
                    "schematic_color": "rgba(0, 0, 0, 0.000)",
                },
            ],
            "meta": {"version": 5},
            "netclass_patterns": [
                {"netclass": "100ohm_diff", "pattern": "P*_TR_*"},
                {"netclass": "100ohm_diff", "pattern": "P2_KSZ_*"},
                {"netclass": "100ohm_diff", "pattern": "LAN_TR*"},
                {"netclass": "100ohm_diff", "pattern": "USB3_*"},
                {"netclass": "power", "pattern": "+*"},
                {"netclass": "power", "pattern": "GND"},
            ],
            "net_colors": {"+3V3": "rgb(200, 77, 176)", "+1V2_DVDDL": "rgb(255, 173, 0)", "+2V5_AVDDH": "rgb(0, 206, 228)", "GND": "rgb(122, 122, 122)"},
        },
        "schematic": {
            "annotate_start_num": 0,
            "drawing": {"default_text_size": 50.0, "label_size_ratio": 0.375},
            "legacy_lib_dir": "",
            "legacy_lib_list": [],
            "meta": {"version": 1},
            "plot_directory": "plots",
        },
        "sheets": [[root_uuid, "Root"]],
        "text_variables": {},
    }
    return json.dumps(data, indent=2)


def ref_sort_key(ref: str) -> tuple[str, int, str]:
    prefix = "".join(ch for ch in ref if not ch.isdigit())
    digits = "".join(ch for ch in ref if ch.isdigit())
    return prefix, int(digits or 0), ref


def instance_ref(inst: Instance | LibInstance) -> str:
    return inst.ref


def instance_value(inst: Instance | LibInstance) -> str:
    return inst.value


def instance_footprint(inst: Instance | LibInstance) -> str:
    return inst.footprint if isinstance(inst, LibInstance) else inst.sym.footprint


def instance_description(inst: Instance | LibInstance) -> str:
    return inst.desc if isinstance(inst, LibInstance) else inst.sym.desc


def instance_datasheet(inst: Instance | LibInstance) -> str:
    return inst.datasheet if isinstance(inst, LibInstance) else inst.sym.datasheet


def instance_fields(inst: Instance | LibInstance) -> dict[str, str]:
    return dict(inst.fields or {})


def instance_pin_nets(inst: Instance | LibInstance) -> dict[str, str | None]:
    if isinstance(inst, LibInstance):
        return dict(inst.pin_nets)
    return {pin.num: (None if pin.nc else pin.net) for pin in inst.sym.pins}


def footprint_parts(fp_id: str) -> tuple[Path, str]:
    if ":" not in fp_id:
        raise ValueError(f"Footprint must be a library-qualified id, got {fp_id!r}")
    lib, name = fp_id.split(":", 1)
    return KICAD_SHARE / "footprints" / f"{lib}.pretty", name


def pcb_pad_nets(inst: Instance | LibInstance) -> dict[str, str | None]:
    nets = instance_pin_nets(inst)
    ref = instance_ref(inst)
    if ref == "J1":
        mapped = {str(pin): nets.get(str(pin)) for pin in range(1, 17)}
        mapped["SH"] = nets.get("SH")
        return mapped
    return nets


def pcb_placements() -> dict[str, tuple[float, float, float]]:
    return {
        "J5": (12, 16, 0),
        "C1": (18, 30, 0),
        "U3": (35, 22, 0),
        "L1": (49, 22, 0),
        "C2": (61, 22, 0),
        "C16": (45, 13, 0),
        "R6": (32, 35, 90),
        "R7": (39, 35, 90),
        "U4": (35, 50, 0),
        "L2": (49, 50, 0),
        "C3": (61, 50, 0),
        "C17": (45, 41, 0),
        "R8": (32, 63, 90),
        "R9": (39, 63, 90),
        "U5": (34, 78, 0),
        "FB1": (50, 76, 0),
        "FB2": (50, 88, 0),
        "C4": (62, 76, 0),
        "R4": (66, 83, 90),
        "R5": (72, 83, 90),
        "U1": (76, 55, 0),
        "C12": (70.5, 50.5, 90),
        "C13": (70.5, 53.5, 90),
        "C14": (70.5, 56.5, 90),
        "Y1": (75, 76, 0),
        "C8": (66, 72, 0),
        "C9": (84, 72, 0),
        "R1": (65, 78, 90),
        "J4": (75, 97, 90),
        "T1": (98, 28, 90),
        "J1": (143, 20, 0),
        "U2": (119, 56, 0),
        "L3": (104, 72, 0),
        "FB3": (108, 82, 0),
        "C5": (124.8, 56, 90),
        "C6": (119, 50.2, 90),
        "C7": (123.2, 50.2, 90),
        "C15": (114.8, 50.2, 90),
        "C18": (124.8, 60.2, 90),
        "Y2": (119, 79, 0),
        "C10": (110, 84, 0),
        "C11": (128, 84, 0),
        "R2": (136, 70, 90),
        "R3": (142, 70, 90),
        "J2": (146, 62, 90),
        "J6": (146, 82, 90),
        "J3": (112, 97, 90),
        "C19": (147, 38, 0),
    }


def write_bom_csv(instances: list[Instance | LibInstance]) -> None:
    groups: dict[tuple[str, ...], list[str]] = {}
    metadata: dict[tuple[str, ...], dict[str, str]] = {}
    for inst in instances:
        fp = instance_footprint(inst)
        fields = instance_fields(inst)
        extras = tuple(fields.get(name, "") for name in BOM_EXTRA_FIELDS)
        key = (instance_value(inst), fp, instance_description(inst), instance_datasheet(inst), *extras)
        groups.setdefault(key, []).append(instance_ref(inst))
        metadata[key] = {
            "Value": instance_value(inst),
            "Footprint": fp,
            "Description": instance_description(inst),
            "Datasheet": instance_datasheet(inst),
            **{name: fields.get(name, "") for name in BOM_EXTRA_FIELDS},
        }

    rows = []
    for idx, key in enumerate(sorted(groups, key=lambda k: ref_sort_key(sorted(groups[k], key=ref_sort_key)[0])), start=1):
        refs = sorted(groups[key], key=ref_sort_key)
        meta = metadata[key]
        rows.append({
            "Item": idx,
            "Qty": len(refs),
            "References": ", ".join(refs),
            "Value": meta["Value"],
            "Footprint": meta["Footprint"],
            "Manufacturer": meta["Manufacturer"],
            "MPN": meta["MPN"],
            "Mfr_Region": meta["Mfr_Region"],
            "Notes": meta["Notes"],
            "Description": meta["Description"],
            "Datasheet": meta["Datasheet"],
            "Source": meta["Source"],
        })

    with (OUT / f"{PROJECT}_BOM.csv").open("w", encoding="utf-8", newline="") as bom:
        writer = csv.DictWriter(
            bom,
            fieldnames=[
                "Item",
                "Qty",
                "References",
                "Value",
                "Footprint",
                "Manufacturer",
                "MPN",
                "Mfr_Region",
                "Notes",
                "Description",
                "Datasheet",
                "Source",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def generate_pcb(instances: list[Instance | LibInstance]) -> None:
    import pcbnew

    board = pcbnew.BOARD()
    board.GetDesignSettings().m_MinThroughDrill = pcbnew.FromMM(0.15)
    net_items: dict[str, object] = {}

    def mm(value: float) -> int:
        return pcbnew.FromMM(value)

    def vec(x: float, y: float):
        return pcbnew.VECTOR2I(mm(x), mm(y))

    def net_item(name: str):
        if not name.startswith("/"):
            name = "/" + name
        if name not in net_items:
            item = pcbnew.NETINFO_ITEM(board, name)
            board.Add(item)
            net_items[name] = item
        return net_items[name]

    def add_edge(x1: float, y1: float, x2: float, y2: float) -> None:
        shape = pcbnew.PCB_SHAPE(board)
        shape.SetShape(pcbnew.SHAPE_T_SEGMENT)
        shape.SetStart(vec(x1, y1))
        shape.SetEnd(vec(x2, y2))
        shape.SetLayer(pcbnew.Edge_Cuts)
        shape.SetWidth(mm(0.1))
        board.Add(shape)

    add_edge(0, 0, BOARD_W_MM, 0)
    add_edge(BOARD_W_MM, 0, BOARD_W_MM, BOARD_H_MM)
    add_edge(BOARD_W_MM, BOARD_H_MM, 0, BOARD_H_MM)
    add_edge(0, BOARD_H_MM, 0, 0)

    placement = pcb_placements()
    for inst in sorted(instances, key=lambda item: ref_sort_key(instance_ref(item))):
        fp_id = instance_footprint(inst)
        if not fp_id:
            raise ValueError(f"{instance_ref(inst)} has no footprint")
        lib_path, footprint_name = footprint_parts(fp_id)
        fp = pcbnew.FootprintLoad(str(lib_path), footprint_name)
        if fp is None:
            raise ValueError(f"Could not load footprint {fp_id}")
        lib_name = lib_path.stem.removesuffix(".pretty")
        fp.SetFPID(pcbnew.LIB_ID(lib_name, footprint_name))
        ref = instance_ref(inst)
        x, y, angle = placement.get(ref, (20, 20, 0))
        fp.SetReference(ref)
        fp.SetValue(instance_value(inst))
        fp.SetField("Datasheet", instance_datasheet(inst))
        fp.SetField("Description", instance_description(inst))
        fp.SetPosition(vec(x, y))
        fp.SetOrientationDegrees(angle)
        fp.SetSheetfile(f"{PROJECT}.kicad_sch")
        fp.SetSheetname("/")

        pad_nets = pcb_pad_nets(inst)
        for pad in fp.Pads():
            pad_name = pad.GetNumber()
            if not pad_name:
                continue
            net_name = pad_nets.get(pad_name)
            if net_name:
                pad.SetNet(net_item(net_name))
        board.Add(fp)

    pcbnew.SaveBoard(str(OUT / f"{PROJECT}.kicad_pcb"), board)


def write_files() -> None:
    OUT.mkdir(exist_ok=True)
    syms = all_symbols()
    instances = build_instances(syms)
    custom_lib = "(kicad_symbol_lib\n  (version 20250610)\n  (generator \"codex_kicad_schematic_generator\")\n" + "\n".join(symbol_definition(s, cache=False) for s in syms.values()) + "\n)\n"
    (OUT / f"{LIB}.kicad_sym").write_text(custom_lib, encoding="utf-8", newline="\n")
    (OUT / "sym-lib-table").write_text(
        f'(sym_lib_table\n  (lib (name "{LIB}")(type "KiCad")(uri "${{KIPRJMOD}}/{LIB}.kicad_sym")(options "")(descr "Generated symbols for KSZ9563R/LAN7800 example"))\n)\n',
        encoding="utf-8",
        newline="\n",
    )
    (OUT / f"{PROJECT}.kicad_sch").write_text(schematic(), encoding="utf-8", newline="\n")
    root_uuid = uid()
    (OUT / f"{PROJECT}.kicad_pro").write_text(project_file(root_uuid), encoding="utf-8", newline="\n")
    write_bom_csv(instances)
    generate_pcb(instances)
    notes = """# KSZ9563R + LAN7800 Example Notes

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
"""
    (OUT / "README_design_notes.md").write_text(notes, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    write_files()
    print(OUT)
