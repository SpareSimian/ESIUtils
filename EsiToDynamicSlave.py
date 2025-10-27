# Code generator for EtherCAT master.
# From ESI file, generate structured text code to initialize a slave.

# hex constants in ESI files look like #x0123. Remove the 0x and replace with ST's 16# prefix. 
def numstring(xmltext):
    if '#x' == xmltext[0:1]:
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

stFile = open(args.output_filename, 'w')
print('CASE readeeprom.dwVendorID OF', file=stFile)
print(f'\t16#{id}: // {name}', file=stFile)
print('\t\tCASE readeeprom.dwProductID OF', file=stFile)

devices = root.find('Descriptions').find('Devices')
for device in devices.iter('Device'):
    deviceType = device.find('Type')
    productCode = numstring(deviceType.get('ProductCode'))
    name = device.find('Name').text
    print(f'\t\t\t16#{productCode}: // {name}', file=stFile)
    syncManagers = {} # so we can look up SM properties to invoke AddFMMU properly

    for sm in device.iter('Sm'):
        syncManager = {}
        startAddress = numstring(sm.get('StartAddress'))
        syncManager['StartAddress'] = startAddress
        defaultSize = numstring(sm.get('DefaultSize'))
        syncManager['DefaultSize'] = defaultSize
        enable = xmlbool(sm.get('Enable'))
        controlByte = numstring(sm.get("ControlByte"))
        syncManager['ControlByte'] = controlByte
        smText = sm.text
        smType = syncManagerType(smText)
        syncManagers[smText] = syncManager
        print(f'\t\t\t\tpSlave^.AddSyncManager(wStartAddress := {startAddress}, wLength := {defaultSize}, usiMode := {controlByte}, xEnable := {enable}, usiType := {smType})', file=stFile)
        
    for fmmu in device.iter('Fmmu'):
        if 'MBoxState' == fmmu.text:
            print('\t\t\t\tpSlave^.AddFMMU(0, 1, 0, 0, 16#80D, 0, 1, 1)', file=stFile)
            print('\t\t\t\tpSlave^.AlighFMMU()', file=stFile)
        else:
            syncManager = syncManagers[fmmu.text]
            lengthBytes = syncManager['DefaultSize']
            startAddress = syncManager['StartAddress']
            if 'Inputs' == fmmu.text:
                access = '1' # read
            else:
                access = '2' # write
            print(f'\t\t\t\tpSlave^.AddFMMU(dwGlobalStartAddress := 0, wLength := {lengthBytes}, usiStartBit := 0, usiEndBit := 7, wPhyssStartAddress := {startAddress}, usiPhysStartBit := 0, usiAccess := {access}, dwFlags := 1)', file=stFile)
    
    rxPdo = device.find('RxPdo')
    txPdo = device.find('TxPdo')

print('\t\tEND_CASE', file=stFile)
print('END_CASE', file=stFile)
