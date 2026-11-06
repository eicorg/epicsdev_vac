# EPICS PVAccess server for various vacuum gauge controllers
Instruments supported:
 - B-RAX 3000 series from InstruTech.
 - Granville-Philips 307 and 358 .

Communication uses PyVISA's pure-Python backend, and supports following interfaces:
`R232, RS485 and TCP socket to a transparent serial gateway

## Running

From this directory:

```sh
uv sync
uv run epicsdev_vac
```

Commands are paced at 0.1-second intervals; configure the gateway baud separately.
`--units` must match the controller display for the native command set:
the native protocol returns readings in display units but does not provide a
unit query. No unit conversion or hardware unit change is performed.
Use `--resource` (or `-r`), `--timeout`, and `--instance` to override the defaults.
For example: `uv run epicsdev_vac --resource TCPIP0::192.168.27.10::1::SOCKET`.
For a direct serial connection, use an ASRL resource and `--baudrate`
(default: 19200), matching the controller's configured speed:

```sh
uv run epicsdev_vac --resource ASRL/dev/ttyUSB0::INSTR --baudrate 9600
```

`--baudrate` configures serial resources only; TCPIP and other non-serial
resources ignore it. Serial gateway settings must still be configured separately.
`--diagnostics` enables research measurements added after January 2017.

Autosave follows epicsdev defaults. Select a writable directory with
`--autosave /path/to/cache`, or pass bare `--autosave` to disable it.
Restoring cached control PVs never writes hardware; control PVs show the last
requested value, while separate readbacks show the measured device state.

## Device PVs

The table below describes the native `BRAX_3000` mode. Names follow the
configured prefix. Standard epicsdev server controls,
heartbeat, timing, and status PVs are also available.

| PV | Meaning |
| --- | --- |
| `resource` | Configured VISA resource string |
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

## OPI generation

Generate a Phoebus operator interface using
[opi/generate_opi.py](opi/generate_opi.py). From this directory, run:

```sh
uv run --with phoebusgen python opi/generate_opi.py
```

`--with phoebusgen` supplies the generator dependency without adding it to
the server's dependencies. Generation does not require a running server or
a hardware connection. Open the generated `.bob` file in Phoebus Display
Builder and run it with the PVAccess server available.

| Option | Meaning | Default |
| --- | --- | --- |
| `-m`, `--model` | `B-RAX_3000`, `GP307`, or `GP358` | `B-RAX_3000` |
| `-i`, `--instance` | Instance used in the title, PV prefix, and filename | `0` |
| `-t`, `--title` | Custom screen title | `<model> instance <instance>` |
| `--diagnostics` | Include native B-RAX research diagnostic widgets | Disabled |
| `prefix` | Optional full PV prefix, including `pva://` and trailing colon | `pva://vac:<model>:<instance>:` |

Output is written beside the generator as `opi/<model>_<instance>.bob`,
overwriting an existing file with that name. A custom title or prefix does
not change the filename. The default command writes `opi/B-RAX_3000_0.bob`
and uses `pva://vac:B-RAX_3000:0:`.

The screen prefix must match the IOC's actual prefix. For an IOC using the
default `vac:brax:0:` prefix, pass it explicitly:

```sh
uv run --with phoebusgen python opi/generate_opi.py pva://vac:brax:0:
```

For GP307, select the GP layout and the matching IOC prefix:

```sh
uv run --with phoebusgen python opi/generate_opi.py --model GP307 pva://vac:brax:0:
```

This writes `opi/GP307_0.bob` with IG/CG1/CG2 pressures, separate filament
1/2 controls, degas control/readback, and relay states. The former `--GP307`
and `--GP358` flags have been replaced by `--model`.

Current limitation: `--model GP358` selects a GP-sized screen but still
includes some native-only widgets. For a GP358 IOC, use `--model GP307`
with a custom title and the GP358 IOC's actual prefix, for example:

```sh
uv run --with phoebusgen python opi/generate_opi.py --model GP307 --title "GP358 instance 0" pva://vac:GP358:0:
```

For a native B-RAX instance with diagnostics:

```sh
uv run --with phoebusgen python opi/generate_opi.py --model B-RAX_3000 --instance 1 --title "B-RAX 3000 instance 1" --diagnostics pva://vac:brax:1:
```

This writes `opi/B-RAX_3000_1.bob`. Use `--diagnostics` only for a native
B-RAX IOC exposing emission current, filament voltage/current, and ion
current PVs. GP command sets do not expose these diagnostic PVs.

## Tests

```sh
uv run python -m unittest discover -s tests -v
uv run --with phoebusgen python -m unittest discover -s tests -p test_opi.py -v
```

Tests use a local TCP simulator with real PyVISA socket sessions, plus an
isolated PVAccess server/client. They do not connect to or control hardware.
Screen tests require the optional `phoebusgen` dependency and otherwise skip.
