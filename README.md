# ESIUtils

Utilities for manipulating EtherCAT Slave Information (ESI) files.

## EsiObjDirToCsv

Dump the object directory from an EtherCAT ESI file to a CSV table.

Usge: `EsiObjDirToCsv.py esi-file csv-file`

## EsiToDynamicSlave

Generate structured text source code suitable for use in the CODESYS Dynamic Configuration example. 

Usage: `EsiToDynamicSlave.py esi-file st-file`

## `EsiObjDirToCPPHeader.py`

Generate a C++ header file. Sections (common index values) become
namespaces. Objects without a subindex are placed in the outermost
namespace. The overall file is wrapped in namespace CANopen. Each
entry is declared as a constexpr ObjectAddress. Objects include
descriptive strings for apps that want to print ESI symbol names.

Usage: `EsiObjDirToCPPHeader.py esi-file h-file`

## `EsiToValidSdoList.py`

Dump a structured text variable with a list of all known objects and a
count of the number of objects, for use in PLC applications that want
to know what objects are available. This can be used in stress-testing
a slave with random SDO operations. The struct should be defined like
this:
```
TYPE STRUCT_SDO_TARGET :
STRUCT
    wIndex      : WORD;
    bySubIndex  : BYTE;
END_STRUCT
END_TYPE
```
Usage: `EsiToValidSdoList.py esi-file st-file`
