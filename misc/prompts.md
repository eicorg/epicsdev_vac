# Prompts for epicsdev_vac
## Initial
Modify __main__.py to provide EPICS PVAccess support for B-RAX vacuum controller.
Use the programming manual in misc/programming_manual.pdf as the primary reference.
Use pyvisa socket interface.
The default IP address will be 192.168.27.10 port 1.

## OPI auto generation
Modify opi/generate_opi.py to generate an OPI for the PVs defined in epicsdev_vac/__main__.py.
