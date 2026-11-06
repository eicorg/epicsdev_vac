"""EPICS PVAccess server for vacuum gauge controllers."""
# pylint: disable=invalid-name
__version__ = 'v0.0.3 2026-11-05'

import argparse
import math
import re
import time
from threading import RLock
from collections import namedtuple

import pyvisa
from pyvisa.rname import parse_resource_name
from epicsdev import epicsdev as edev

DEFAULT_VISA_RESOURCE = 'TCPIP::mds-911c-term1::2103::SOCKET'

# Gauge controller PV definitions.
Model = namedtuple('Model',
    ['firmware','pressures','controls','diagnostics','relays'])
Gauge = {
'BRAX_3000': Model(
    firmware={'Firmware': 'VER'},#{'Firmware': None},
    pressures={'IG': 'RDIG', 'CG1': 'RDCG1', 'CG2': 'RDCG2', 'AI': 'RDAI'},
    controls={
        'IGEnable': ('IG', {'Off': '0', 'On': '1'}),
        'Degas': ('DG', {'Off': '0', 'On': '1'}),
        'Emission': ('SE', {'100 uA': '0', '4 mA': '1', '10 mA': '2'}),
        'Filament': ('SF', {'1': '1', '2': '2'}),
    },
    diagnostics={
        'EmissionCurrent':('RDIGE', 'A'), 'FilamentVoltage':('RDIGV', 'V'),
        'FilamentCurrent':('RDIGA', 'A'), 'IonCurrent':('RDIGC', 'A')},
    relays=[1, 2, 3, 4, 5, 6]
)
}

GP_MODEL = Model(
    firmware={'Firmware': None},
    pressures={'IG': 'DS IG', 'CG1': 'DS CG1', 'CG2': 'DS CG2'},
    controls={
        'IG1Enable': ('IG1 ', {'Off': 'OFF', 'On': 'ON'}),
        'IG2Enable': ('IG2 ', {'Off': 'OFF', 'On': 'ON'}),
        'Degas': ('DG ', {'Off': 'OFF', 'On': 'ON'}),
    },
    diagnostics={}, relays=[1, 2, 3, 4, 5, 6],
)
Gauge.update({'GP307': GP_MODEL, 'GP358': GP_MODEL})

Threadlock = RLock()

class ControllerError(ValueError):
    """The controller rejected a syntactically valid transaction."""


class C_:
    """Container for module state variables."""

    pargs = None
    manager = None
    instrument = None
    last_command = 0.0
    next_connect = 0.0


def myPVDefs():
    """Return PV definitions; pressure units must match the front panel."""
    model = Gauge[C_.pargs.model]
    pv_defs = [
        ['dateTime', 'Server local date/time', 'N/A'],
        ['resource', 'VISA resource string', C_.pargs.resource],
        ['Connected', 'Controller communication is healthy', 0],
        ['CommStatus', 'Last communication result', 'Not connected'],
        ['Firmware', 'Controller firmware part number and revision', '?'],
        ['PressureUnits', 'Configured units; must match controller display', C_.pargs.units],
        ['IGEnable', 'Ion gauge control', ['Off', 'On'],
         {'features': 'WD', 'setter': set_control}],
        ['IGEnabled', 'Measured ion gauge on/off status', -1],
        ['Degas', 'Ion gauge degas control', ['Off', 'On'],
         {'features': 'WD', 'setter': set_control}],
        ['DegasActive', 'Measured degas on/off status', -1],
        ['Emission', 'Emission current selection', ['100 uA', '4 mA', '10 mA'],
         {'features': 'WD', 'setter': set_control}],
        ['EmissionReadback', 'Emission current setting reported by SES', '?'],
        ['Filament', 'Filament selection', ['1', '2'],
         {'features': 'WD', 'setter': set_control}],
        ['FilamentReadback', 'Selected filament; -1 if unavailable', -1],
        ['IGDeviceStatus', 'Ion gauge status/error response', '?'],
        ['RelayMask', 'Six relay state bits; -1 if unavailable', -1],
    ]
    if model is GP_MODEL:
        native_only = {
            'Firmware', 'IGEnable', 'IGEnabled', 'Emission', 'EmissionReadback',
            'Filament', 'FilamentReadback', 'IGDeviceStatus',
        }
        pv_defs = [definition for definition in pv_defs if definition[0] not in native_only]
        for filament in (1, 2):
            pv_defs.append([
                f'IG{filament}Enable', f'Ion gauge filament {filament} control', ['Off', 'On'],
                {'features': 'WD', 'setter': set_control},
            ])
    for channel in Gauge[C_.pargs.model].pressures.keys():
        pv_defs.extend([
            [f'{channel}Pressure', f'{channel} absolute pressure', math.nan,
             {'type': 'f64', 'units': C_.pargs.units}],
            [f'{channel}PressureRaw', f'{channel} raw pressure response', '?'],
            [f'{channel}Status', f'{channel} measurement validity', 'Not connected'],
        ])
    for relay in range(1, 7):
        pv_defs.append([f'Relay{relay}', 'Relay energized; -1 if unavailable', -1])
    if C_.pargs.diagnostics:
        for name, (_, units) in Gauge[C_.pargs.model].diagnostics.items():
            pv_defs.append([name, f'Ion gauge {name}', math.nan,
                            {'type': 'f64', 'units': units}])
    return pv_defs


def parse_reply(reply, address):
    """Validate the 13-byte native reply (PyVISA removes its final CR)."""
    if len(reply) != 12 or reply[0] not in '*?' or reply[1:3] != address or reply[3] != ' ':
        raise ValueError(f'Malformed or misaddressed Instrument reply: {reply!r}')
    payload = reply[4:].strip()
    if reply[0] == '?':
        raise ControllerError(payload)
    return payload


def close_connection():
    """Close the VISA session, including after a partial/timed-out reply."""
    with Threadlock:
        instrument, C_.instrument = C_.instrument, None
        if instrument is not None:
            try:
                instrument.close()
            except (pyvisa.errors.Error, OSError):
                pass


def communication_failed(error):
    """Invalidate old readings and arrange a later reconnect."""
    close_connection()
    C_.next_connect = time.monotonic() + 5.0
    edev.publish('Connected', 0, True)
    edev.publish('CommStatus', str(error), True)
    for channel in Gauge[C_.pargs.model].pressures.keys():
        edev.publish(f'{channel}Pressure', math.nan)
        edev.publish(f'{channel}Status', 'Communication failure', True)
    names = ('DegasActive', 'RelayMask') if Gauge[C_.pargs.model] is GP_MODEL else (
        'IGEnabled', 'DegasActive', 'FilamentReadback', 'RelayMask')
    for name in names:
        edev.publish(name, -1, True)
    for relay in range(1, 7):
        edev.publish(f'Relay{relay}', -1, True)
    if Gauge[C_.pargs.model] is not GP_MODEL:
        for name in ('Firmware', 'EmissionReadback', 'IGDeviceStatus'):
            edev.publish(name, '?', True)
    if C_.pargs.diagnostics:
        for name, (_, units) in Gauge[C_.pargs.model].diagnostics.items():
            edev.publish(name, math.nan, {'type': 'f64', 'units': units})
    edev.printe(f'Instrument communication: {error}')


def devCmd(command):
    """Perform one paced, serialized request/reply in the selected protocol."""
    if command is None:
        return '?'
    with Threadlock:
        if C_.instrument is None:
            raise ConnectionError('Instrument is not connected')
        remaining = 0.1 - (time.monotonic() - C_.last_command)
        if remaining > 0:
            time.sleep(remaining)
        compatibility = Gauge[C_.pargs.model] is GP_MODEL
        wire = command if compatibility else f'#{C_.pargs.address}{command}'
        edev.printvv(f'Instrument > {wire!r}')
        C_.last_command = time.monotonic()
        reply = C_.instrument.query(wire)
        edev.printvv(f'Instrument < {reply!r}')
        if compatibility:
            if reply == 'INVALID':
                raise ControllerError(reply)
            return reply
        return parse_reply(reply, C_.pargs.address)


def read_optional(command):
    """An absent gauge or unsupported feature must not take other gauges offline."""
    try:
        return devCmd(command)
    except ControllerError as error:
        return f'?{error}'


def set_control(value, pv):
    """Write only on an explicit client put; never restore hardware on startup."""
    command, choices = Gauge[C_.pargs.model].controls[pv.name]
    if str(value) not in choices:
        raise ValueError(f'Invalid {pv.name} choice: {value}')
    with Threadlock:
        if not edev.serverState().startswith('Start'):
            raise RuntimeError('Start the server before controlling the Instrument')
        try:
            reply = devCmd(command + choices[str(value)])
            acknowledgement = 'OK' if Gauge[C_.pargs.model] is GP_MODEL else 'PROGM OK'
            if reply != acknowledgement:
                raise ValueError(f'Unexpected acknowledgement: {reply!r}')
        except ControllerError as error:
            edev.publish('CommStatus', f'{pv.name}: {error}')
            raise
        except (pyvisa.errors.Error, OSError, ValueError) as error:
            communication_failed(error)
            raise


def poll_gp_status():
    """Read the status queries supported by section 8.4."""
    reply = read_optional('DGS')
    if reply.startswith('?'):
        state = -1
    elif reply in ('0', '1'):
        state = int(reply)
    else:
        raise ValueError(f'Invalid DGS reply: {reply!r}')
    edev.publish('DegasActive', state, True)
    reply = devCmd('PCS')
    if re.fullmatch(r'[01](,[01]){5}', reply) is None:
        raise ValueError(f'Invalid relay state: {reply!r}')
    mask = 0
    for relay, state in enumerate(reply.split(','), 1):
        mask |= int(state) << (relay - 1)
        edev.publish(f'Relay{relay}', int(state), True)
    edev.publish('RelayMask', mask, True)


def poll():
    """Reconnect as necessary and publish an independent result for each gauge."""
    with Threadlock:
        try:
            model = Gauge[C_.pargs.model]
            compatibility = model is GP_MODEL
            if C_.instrument is None:
                if time.monotonic() < C_.next_connect:
                    return
                if C_.manager is None:
                    C_.manager = pyvisa.ResourceManager('@py')
                termination = '\r\n' if compatibility else '\r'
                serial_options = {}
                if parse_resource_name(C_.pargs.resource).interface_type == 'ASRL':
                    serial_options['baud_rate'] = C_.pargs.baudrate
                C_.instrument = C_.manager.open_resource(
                    C_.pargs.resource, open_timeout=int(C_.pargs.timeout * 1000),
                    timeout=int(C_.pargs.timeout * 1000),
                    read_termination=termination, write_termination=termination, encoding='ascii',
                    **serial_options,
                )
                if model.firmware['Firmware'] is not None:
                    edev.publish('Firmware', devCmd(model.firmware['Firmware']), True)
            for channel, command in Gauge[C_.pargs.model].pressures.items():
                reply = read_optional(command)
                edev.publish(f'{channel}PressureRaw', reply, True)
                value = math.nan if reply.startswith('?') else float(reply)
                if reply.startswith('?'):
                    status = reply
                elif not math.isfinite(value) or value < 0:
                    raise ValueError(f'Invalid {channel} pressure: {reply!r}')
                elif value == (9.90e9 if compatibility else 1.10e3):
                    value, status = math.nan, f'Off or over range ({reply})'
                else:
                    status = 'OK'
                edev.publish(f'{channel}Pressure', value)
                edev.publish(f'{channel}Status', status, True)
            if compatibility:
                poll_gp_status()
                edev.publish('Connected', 1, True)
                edev.publish('CommStatus', 'OK', True)
                return
            for name, command, suffix in (
                ('IGEnabled', 'IGS', 'IG'), ('DegasActive', 'DGS', 'DG'),
            ):
                reply = read_optional(command)
                if reply.startswith('?'):
                    state = -1
                elif reply in (f'0 {suffix} OFF', f'1 {suffix} ON'):
                    state = int(reply[0])
                else:
                    raise ValueError(f'Invalid {command} reply: {reply!r}')
                edev.publish(name, state, True)
            edev.publish('IGDeviceStatus', read_optional('RSIG'), True)
            edev.publish('EmissionReadback', read_optional('SES'), True)
            reply = read_optional('RF')
            if reply.startswith('?'):
                filament = -1
            elif reply in ('FIL SEL1', 'FIL SEL2'):
                filament = int(reply[-1])
            else:
                raise ValueError(f'Invalid RF reply: {reply!r}')
            edev.publish('FilamentReadback', filament, True)
            reply = devCmd('RL')
            match = re.fullmatch(r'([0-9A-Fa-f]{4}) RL', reply)
            if match is None or int(match[1], 16) > 0x3f:
                raise ValueError(f'Invalid relay state: {reply!r}')
            mask = int(match[1], 16)
            edev.publish('RelayMask', mask, True)
            for relay in range(1, 7):
                edev.publish(f'Relay{relay}', (mask >> (relay - 1)) & 1, True)
            if C_.pargs.diagnostics:
                for name, (command, _) in Gauge[C_.pargs.model].diagnostics.items():
                    reply = read_optional(command)
                    edev.publish(name, math.nan if reply.startswith('?') \
                                 else float(reply), {'type': 'f64', 'units': _})
            edev.publish('Connected', 1, True)
            edev.publish('CommStatus', 'OK', True)
        except (pyvisa.errors.Error, OSError, ValueError) as error:
            communication_failed(error)


def periodic_update():
    """Publish server local time."""
    edev.publish('dateTime', time.strftime('%Y-%m-%d %H:%M:%S'))


def serverStateChanged(newState):
    """Release transport resources on exit."""
    edev.printi(f'{newState} requested')
    if newState.startswith('Exit'):
        close_connection()


def main():
    """Run the PVAccess server."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        epilog=f'{__version__}, epicsdev:{edev.__version__}',
    )
    parser.add_argument('-a', '--autosave', nargs='?', default='',help=
        'Autosave directory; omit for default directory.')
    parser.add_argument('-A', '--address', default='  ',help=
        'Two hex digits for RS485; omit for native RS232.')
    parser.add_argument('-b', '--baudrate', type=int, default=9600, help=
        'Serial ASRL resource baud rate; ignored for TCPIP and other non-serial resources.')
    parser.add_argument('-c', '--recall', action='store_false', help=
        'Do not restore cached PV values (hardware is never restored).')
    parser.add_argument('-d', '--diagnostics', action='store_false',help=
        'Read research diagnostics.')
    parser.add_argument('-i', '--instance', default='0', help=
        'Device instance.')
    parser.add_argument('-m', '--model', choices=Gauge, default='BRAX_3000', help=
        'Instrument models. Choices for B-RAX series and Granville-Phillips 307 and 358.')
    parser.add_argument('-p', '--putlogPV', nargs='?', default='', help=
        'Put logging PV.')
    parser.add_argument('-r', '--resource', default=DEFAULT_VISA_RESOURCE, help=
        'VISA resource string for the vacuum gauge controller.')
    parser.add_argument('--timeout', type=float, default=2.0, help=
        'VISA timeout in seconds.')
    parser.add_argument('-u', '--units', choices=('Torr', 'mbar', 'Pa'), default='Torr',help=
        'Must match controller display units; does not change hardware.')
    parser.add_argument('-v', '--verbose', action='count', default=0, help=
        'Increase verbosity (-vv for more).')
    parser.add_argument('device', nargs='?', help=
        'PV prefix before instance.')
    C_.pargs = parser.parse_args()

    if C_.pargs.device is None:
        C_.pargs.device = f'vac:{C_.pargs.model}:'

    if C_.pargs.baudrate <= 0:
        parser.error('--baudrate must be a positive integer')
    if not math.isfinite(C_.pargs.timeout) or C_.pargs.timeout < 0.001:
        parser.error('--timeout must be finite and at least 0.001 seconds')
    if C_.pargs.address != '  ' and not re.fullmatch(r'[0-9A-Fa-f]{2}', C_.pargs.address):
        parser.error('--address must contain exactly two hexadecimal digits')
    if Gauge[C_.pargs.model] is GP_MODEL:
        if C_.pargs.address != '  ':
            parser.error('GP307/GP358 section 8.4 supports RS232 only; omit --address')
        if C_.pargs.units != 'Torr':
            parser.error('GP307/GP358 pressure responses are always in Torr')
    C_.pargs.address = C_.pargs.address.upper()
    C_.pargs.prefix = f'{C_.pargs.device}{C_.pargs.instance}:'
    if C_.pargs.putlogPV == '':
        C_.pargs.putlogPV = 'putlog:dump'
    PVs = edev.init_epicsdev(
        C_.pargs.prefix, myPVDefs(), C_.pargs.verbose, serverStateChanged,
        '', C_.pargs.autosave, C_.pargs.recall, C_.pargs.putlogPV,
    )
    edev.publish('VERSION', __version__)
    edev.set_server('Start')
    try:
        with edev.Server(providers=[PVs]):
            edev.printi(f'Instrument PVAccess server: {C_.pargs.prefix}')
            while not edev.serverState().startswith('Exit'):
                if not edev.serverState().startswith('Stop'):
                    poll()
                if not edev.sleep():
                    periodic_update()
    except KeyboardInterrupt:
        edev.set_server('Exit')
    finally:
        close_connection()
        if C_.manager is not None:
            C_.manager.close()
    edev.printi('Server is exited')


if __name__ == '__main__':
    main()
