"""Operator interface generator for B-RAX 3300"""
__version__ = 'v0.0.1 2026-11-04'
# pylint: disable=invalid-name,broad-exception-caught

import argparse
from pathlib import Path

import phoebusgen.screen
import phoebusgen.widget

DEVICE = "B-RAX_3300"
INSTANCE = "0"
TITLE = DEVICE+INSTANCE
PREFIX = f'pva://vac:brax:{INSTANCE}:'

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        epilog=__version__,
    )
    parser.add_argument("-t", "--title", default=TITLE, help="Screen title")
    parser.add_argument("--diagnostics", action="store_true",
        help="Include diagnostic PVs enabled by the server's --diagnostics option")
    parser.add_argument("prefix", nargs="?", default=PREFIX,
        help=(
            "PV prefix used for all widget PV names. "
        ),
    )
    return parser.parse_args()

def _add_items(widget, values: str) -> None:
    for item in values.split(", "):
        widget.item(item)

def main() -> None:
    pargs = _parse_args()
    prefix = pargs.prefix

    screen = phoebusgen.screen.Screen(pargs.title, f"{TITLE}.bob")
    screen.width(1080)
    screen.height(760 if pargs.diagnostics else 660)

    w = phoebusgen.widget
    widgets = {
        "title": w.Label("title", pargs.title, 20, 10, 360, 30),
        "Firmware_lbl": w.Label("Firmware_lbl", "Firmware:", 400, 14, 80, 20),
        "Firmware": w.TextUpdate("Firmware", f"{prefix}Firmware", 480, 14, 280, 20),
        "dateTime": w.TextUpdate("dateTime", f"{prefix}dateTime", 800, 14, 260, 20),
    }
    y = 45
    widgets.update({
        "srvStatus_lbl": w.Label("srvStatus_lbl", "Server:", 20, y, 60, 20),
        "srvStatus": w.TextUpdate("srvStatus", f"{prefix}status", 80, y, 980, 20),
    })
    y += 40
    widgets.update({
        "state_lbl": w.Label("state_lbl", "Run/Stop:", 20, y, 65, 20),
        "server": w.ComboBox("server", f"{prefix}server", 90, y, 110, 20),
        "sleep_lbl": w.Label("sleep_lbl", "Sleep:", 410, y, 40, 20),
        "sleep": w.TextEntry("sleep", f"{prefix}sleep", 450, y, 50, 20),
        "cycleTime_lbl": w.Label("cycleTime_lbl", "Period:", 510, y, 50, 20),
        "cycleTime": w.TextUpdate("cycleTime", f"{prefix}cycleTime", 560, y, 60, 20),
        "hb_lbl": w.Label("hb_lbl", "HB:", 640, y, 30, 20),
        "HEARTBEAT": w.TextUpdate("HEARTBEAT", f"{prefix}HEARTBEAT", 670, y, 70, 20),
    })

    y = 125
    widgets.update({
        "host_lbl": w.Label("host_lbl", "Gateway:", 20, y, 80, 20),
        "host": w.TextUpdate("host", f"{prefix}host", 100, y, 180, 20),
        "port_lbl": w.Label("port_lbl", "Port:", 300, y, 40, 20),
        "port": w.TextUpdate("port", f"{prefix}port", 340, y, 70, 20),
        "Connected_lbl": w.Label("Connected_lbl", "Connected:", 440, y, 90, 20),
        "Connected": w.TextUpdate("Connected", f"{prefix}Connected", 530, y, 50, 20),
        "PressureUnits_lbl": w.Label("PressureUnits_lbl", "Units:", 620, y, 50, 20),
        "PressureUnits": w.TextUpdate("PressureUnits", f"{prefix}PressureUnits", 670, y, 90, 20),
        "CommStatus_lbl": w.Label("CommStatus_lbl", "Communication:", 20, 155, 120, 20),
        "CommStatus": w.TextUpdate("CommStatus", f"{prefix}CommStatus", 140, 155, 920, 20),
    })

    for name, label, xpos, width in (
            ("channel", "Gauge", 20, 90),
            ("pressure", "Pressure", 120, 180),
            ("raw", "Raw response", 330, 200),
            ("validity", "Measurement status", 560, 500)):
        widgets[f"{name}_heading"] = w.Label(f"{name}_heading", label, xpos, 195, width, 20)
    for index, channel in enumerate(("IG", "CG1", "CG2", "AI")):
        y = 225 + index * 30
        widgets[f"{channel}_lbl"] = w.Label(f"{channel}_lbl", channel, 20, y, 90, 20)
        for suffix, xpos, width in (
                ("Pressure", 120, 180), ("PressureRaw", 330, 200), ("Status", 560, 500)):
            name = f"{channel}{suffix}"
            widgets[name] = w.TextUpdate(name, f"{prefix}{name}", xpos, y, width, 20)
        widgets[f"{channel}Pressure"].format("Exponential")
        widgets[f"{channel}Pressure"].precision(3)

    widgets["controls_heading"] = w.Label("controls_heading", "Ion gauge", 20, 365, 180, 20)
    widgets["request_heading"] = w.Label("request_heading", "Requested", 230, 365, 130, 20)
    widgets["readback_heading"] = w.Label("readback_heading", "Readback", 400, 365, 180, 20)
    for index, (name, label, choices, readback) in enumerate((
            ("IGEnable", "Ion gauge enable:", "Off, On", "IGEnabled"),
            ("Degas", "Degas:", "Off, On", "DegasActive"),
            ("Emission", "Emission current:", "100 uA, 4 mA, 10 mA", "EmissionReadback"),
            ("Filament", "Filament:", "1, 2", "FilamentReadback"))):
        y = 395 + index * 30
        widgets[f"{name}_lbl"] = w.Label(f"{name}_lbl", label, 20, y, 190, 20)
        widgets[name] = w.ComboBox(name, f"{prefix}{name}", 230, y, 130, 20)
        _add_items(widgets[name], choices)
        widgets[readback] = w.TextUpdate(readback, f"{prefix}{readback}", 400, y, 300, 20)
    widgets.update({
        "IGDeviceStatus_lbl": w.Label("IGDeviceStatus_lbl", "Ion gauge status:", 20, 525, 190, 20),
        "IGDeviceStatus": w.TextUpdate("IGDeviceStatus", f"{prefix}IGDeviceStatus", 230, 525, 830, 20),
        "RelayMask_lbl": w.Label("RelayMask_lbl", "Relay mask:", 20, 565, 100, 20),
        "RelayMask": w.TextUpdate("RelayMask", f"{prefix}RelayMask", 120, 565, 80, 20),
    })
    for relay in range(1, 7):
        name = f"Relay{relay}"
        xpos = 20 + (relay - 1) * 170
        widgets[f"{name}_lbl"] = w.Label(f"{name}_lbl", f"Relay {relay}:", xpos, 605, 80, 20)
        widgets[name] = w.TextUpdate(name, f"{prefix}{name}", xpos + 85, 605, 60, 20)

    if pargs.diagnostics:
        widgets["diagnostics_heading"] = w.Label(
            "diagnostics_heading", "Diagnostics", 20, 650, 200, 20)
        for index, (name, label) in enumerate((
                ("EmissionCurrent", "Emission current (A):"),
                ("FilamentVoltage", "Filament voltage (V):"),
                ("FilamentCurrent", "Filament current (A):"),
                ("IonCurrent", "Ion current (A):"))):
            xpos = 20 + (index % 2) * 540
            y = 680 + (index // 2) * 30
            widgets[f"{name}_lbl"] = w.Label(f"{name}_lbl", label, xpos, y, 210, 20)
            widgets[name] = w.TextUpdate(name, f"{prefix}{name}", xpos + 220, y, 230, 20)
            widgets[name].format("Exponential")
            widgets[name].precision(3)

    _add_items(widgets["server"], "Start, Stop, Clear, Exit, Started, Stopped, Exited")
    for name in ("sleep", "cycleTime"):
        widgets[name].precision(3)
    for name in ("port", "Connected", "IGEnabled", "DegasActive", "FilamentReadback",
                 "RelayMask", "HEARTBEAT", *(f"Relay{relay}" for relay in range(1, 7))):
        widgets[name].format("Decimal")
        widgets[name].precision(0)

    screen.add_widget(list(widgets.values()))

    out = Path(__file__).with_name(f"{TITLE}.bob")
    screen.write_screen(str(out))

if __name__ == "__main__":
    main()
