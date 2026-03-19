# ESIUtils

Utilities for manipulating EtherCAT Slave Information (ESI) files.

## EsiObjDirToCsv

Dump the object directory from an EtherCAT ESI file to a CSV table.

Usge: EsiObjDirToCsv.py esi-file csv-file

## EsiToDynamicSlave

Generate structured text source code suitable for use in the CODESYS Dynamic Configuration example. 

Usage: EsiToDynamicSlave.py esi-file st-file

## EsiObjDirToCPPHeader.py

Generate a C++ header file. Sections (common index values) become
namespaces. Objects without a subindex are placed in the outermost
namespace. The overall file is wrapped in namespace CANopen. Each
entry is declared as a const ObjectAddress.

Usage: EsiObjDirToCPPHeader.py esi-file h-file
