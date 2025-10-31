# Code generator for EtherCAT master.
# From ESI file, generate structured text code to initialize a slave.

import io
import re

stTypesToPrefix = {
    'BOOL' : 'x',
    'SINT' : 'si',
    'INT' : 'i',
    'DINT' : 'di',
    'LINT' : 'li',
    'USINT' : 'usi',
    'BYTE' : 'by',
    'UINT' : 'ui',
    'WORD' : 'w',
    'UDINT' : 'udi',
    'DWORD' : 'dw',
    'ULINT' : 'uli',
    'LWORD' : 'lw',
    'REAL' : 'r',
    'LREAL' : 'lr',
}

def stTypeToPrefix(dataType):
    if 'ARRAY ' == dataType[0:6]:
        # prefix is 'a' followed by the prefix of the array element
        return 'a' + stTypesToPrefix[dataType[dataType.rfind(' ') + 1:]]
    else:
        return stTypesToPrefix[dataType]

def dataTypeSize(dataType):
    return 0 # STUB

# hex constants in ESI files look like #x0123. Remove the 0x and replace with ST's 16# prefix. 
def numstring(xmltext):
    if '#x' == xmltext[0:2]:
        return '16#' + xmltext[2:]
    else:
        return xmltext # it's decimal

def syncManagerType(xmltext):
    if "MBoxOut" == xmltext:
        return 3
    elif "MBoxIn" == xmltext:
        return 2
    elif "Outputs" == xmltext:
        return 1
    elif "Inputs" == xmltext:
        return 0
    else:
        raise ValueError("unknown sync manager type " + xmltext)

def xmlbool(xmltext):
    if "1" == xmltext:
        return "TRUE"
    elif "0" == xmltext:
        return "FALSE"
    else:
        return ValueError("unrecognized bool value " + xmltext)

def cleanName(name):
    return re.sub(r'[ -]', '_', name)

def makeSymbol(text, dataType):
    # strip spaces and add hungarian prefix
    return stTypeToPrefix(dataType) + re.sub(r'[ ]', '', text)

def pdoToStruct(device, deviceName, which, output):
    xml = device.find(which)
    if not xml:
        return 0
    index = numstring(xml.find('Index').text)
    name = xml.find('Name').text
    structName = cleanName(deviceName) + '_' + which
    print(f"// {index} {name}", file=output)
    print("{attribute 'pack_mode' := '8'}", file=output)
    print(f"TYPE {structName} :", file=output)
    print("STRUCT", file=output)
    # now enumerate members
    size = 0
    for entry in xml.iter('Entry'):
        dataType = entry.find('DataType').text
        size = size + dataTypeSize(dataType)
        member = makeSymbol(entry.find('Name').text, dataType)
        indexEntry = numstring(entry.find('Index').text)
        subindexEntry = numstring(entry.find('SubIndex').text)
        if '0' == subindexEntry:
            subindexEntry = ''
        else:
            subindexEntry = ':' + subindexEntry
        print(f'\t{member} : {dataType}; // {indexEntry}{subindexEntry}', file=output)
    print("END_STRUCT", file=output)
    print("END_TYPE", file=output)
    print('\n', file=output)
    return size

import argparse
parser = argparse.ArgumentParser(description='Code generator for EtherCAT master. From ESI file, generate structured text code to initialize a slave.')
parser.add_argument('input_filename', help='path of ESI file')
parser.add_argument('output_filename', help='path of ST file')
args = parser.parse_args()

# Step 1: Read and parse the XML file
import xml.etree.ElementTree as ET
tree = ET.parse(args.input_filename)
root = tree.getroot()

# Step 2: Extract the required information

vendor = root.find('Vendor')
id = numstring(vendor.find('Id').text)
name = vendor.find('Name').text

structsString = io.StringIO() # to store struct declarations for the end

stFile = open(args.output_filename, 'w')
print('CASE readeeprom.dwVendorID OF', file=stFile)
print(f'\t{id}: // {name}', file=stFile)
print('\t\tCASE readeeprom.dwProductID OF', file=stFile)

devices = root.find('Descriptions').find('Devices')
for device in devices.iter('Device'):
    deviceType = device.find('Type')
    productCode = numstring(deviceType.get('ProductCode'))
    name = device.find('Name').text
    print(f'\t\t\t{productCode}: // {name}', file=stFile)
    syncManagers = {} # so we can look up SM properties to invoke AddFMMU properly

    rxPdoSize = pdoToStruct(device, name, 'RxPdo', structsString)
    txPdoSize = pdoToStruct(device, name, 'TxPdo', structsString)

    for sm in device.iter('Sm'):
        syncManager = {}
        startAddress = numstring(sm.get('StartAddress'))
        syncManager['StartAddress'] = startAddress
        smText = sm.text
        smType = syncManagerType(smText)
        if 'DefaultSize' in sm.attrib:
            defaultSize = numstring(sm.get('DefaultSize'))
        else:
            if 'Outputs' == smText:
                defaultSize = txPdoSize
            elif 'Inputs' == smText:
                defaultSize = rxPdoSize
            else:
                raise ValueError("no default size for sync manager")
        syncManager['DefaultSize'] = defaultSize
        if 'DefaultSize' in sm.attrib:
            enable = xmlbool(sm.get('Enable'))
        else:
            enable = '1'
        controlByte = numstring(sm.get("ControlByte"))
        syncManager['ControlByte'] = controlByte
        syncManagers[smText] = syncManager
        print(f'\t\t\t\tpSlave^.AddSyncManager(wStartAddress := {startAddress}, wLength := {defaultSize}, usiMode := {controlByte}, xEnable := {enable}, usiType := {smType});', file=stFile)
        
    for fmmu in device.iter('Fmmu'):
        if 'MBoxState' == fmmu.text:
            print('\t\t\t\tpSlave^.AddFMMU(0, 1, 0, 0, 16#80D, 0, 1, 1);', file=stFile)
            print('\t\t\t\tpSlave^.AlignFMMU();', file=stFile)
        else:
            syncManager = syncManagers[fmmu.text]
            lengthBytes = syncManager['DefaultSize']
            startAddress = syncManager['StartAddress']
            if 'Inputs' == fmmu.text:
                access = '1' # read
            else:
                access = '2' # write
            print(f'\t\t\t\tpSlave^.AddFMMU(dwGlobalStartAddress := 0, wLength := {lengthBytes}, usiStartBit := 0, usiEndBit := 7, wPhysStartAddress := {startAddress}, usiPhysStartBit := 0, usiAccess := {access}, dwFlags := 1);', file=stFile)

    print('\t\t\t\txKnown := TRUE;' , file=stFile)


print('\t\tEND_CASE', file=stFile)
print('END_CASE', file=stFile)
print('\n', file=stFile)

print(structsString.getvalue(), file=stFile)
