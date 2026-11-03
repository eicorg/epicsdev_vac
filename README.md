# EPICS PVAccess server for various vacuum gauge controller
Currently it is being developed and tested with B-RAX 3300

EPICS PVAccess support using the native InstruTech RS232/RS485 protocol in
section 8 of `misc/programming_manual.pdf`. Communication uses PyVISA's
pure-Python backend and a TCP socket to a transparent serial gateway.

## Running

From this directory:

```sh
uv sync
uv run epicsdev_vac
```

Defaults: `TCPIP0::192.168.27.10::1::SOCKET`, native RS232, Torr pressure
units, two-second timeout, and PV prefix `vac:brax:0:`.

Set the controller COMM TYPE to native `RS232`, not a GP compatibility mode.
Configure the serial gateway to match the controller's serial settings
(factory default: 19200 baud, 8 data bits, no parity, 1 stop bit). Commands
and replies end with CR, not LF. The gateway must provide a raw, transparent
socket stream, not a Telnet negotiation or login session.

For native RS485 at node 01:

```sh
uv run epicsdev-vac-brax --address 01 --units mbar --baud 19200
```

`--baud` controls command pacing using the repetition intervals in section 8.1;
it does not configure the gateway. `--units` must match the controller display:
the native protocol returns readings in display units but does not provide a
unit query. No unit conversion or hardware unit change is performed.
Use `--host`, `--port`, `--timeout`, and `--instance` to override the defaults.
`--diagnostics` enables research measurements added after January 2017.

Autosave follows epicsdev defaults. Select a writable directory with
`--autosave /path/to/cache`, or pass bare `--autosave` to disable it.
Restoring cached control PVs never writes hardware; control PVs show the last
requested value, while separate readbacks show the measured device state.

## Device PVs

Names below follow the configured prefix. Standard epicsdev server controls,
heartbeat, timing, and status PVs are also available.

| PV | Meaning |
| --- | --- |
| `IGPressure`, `CG1Pressure`, `CG2Pressure`, `AIPressure` | Double-precision absolute pressure |
| `<channel>PressureRaw`, `<channel>Status` | Raw pressure payload and measurement validity |
| `PressureUnits` | Configured display units |
| `Connected`, `CommStatus`, `Firmware` | Communication health and firmware identification |
| `IGEnable`, `IGEnabled` | Off/On command and on/off readback |
| `Degas`, `DegasActive` | Off/On command and degas readback |
| `Emission`, `EmissionReadback` | 100 uA / 4 mA / 10 mA selection and reported setting |
| `Filament`, `FilamentReadback` | Filament 1/2 command and selection readback |
| `IGDeviceStatus` | Controller's ion-gauge status/error response |
| `RelayMask`, `Relay1` ... `Relay6` | Six relay state bits and individual energized states |
| `EmissionCurrent`, `FilamentVoltage`, `FilamentCurrent`, `IonCurrent` | Optional research diagnostics (A, V, A, A) |

The manual's `1.10E+03` off/over-range sentinel and rejected pressure queries
produce NaN rather than a usable pressure reading. Check the channel status
and raw payload for the reason. Missing gauges or unsupported optional queries
do not disconnect the other channels. Unavailable integer readbacks are -1.

Transport failures invalidate measurements and retry the connection after five
seconds. Polling and writes share a lock to prevent crossed replies. Commands
only run on explicit PV puts while the server is started; device rejections
are propagated to the client. Before enabling the ion gauge or degas, observe
the manual's pressure limits and filament precautions. Startup never enables
either function and never performs gauge calibration.

## Tests

```sh
uv run python -m unittest discover -s tests -v
```

Tests use a local TCP simulator with real PyVISA socket sessions, plus an
isolated PVAccess server/client. They do not connect to or control hardware.
