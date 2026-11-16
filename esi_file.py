# module with common ESI handling

__version__ = '0.1.0'

import xml.etree.ElementTree as ET
import re
import copy # need deepcopy of subitemtypes since they get reused

class EsiFile:
    def from_string(cls, s: str):
        return cls(ET.fromstring(s), "")

    @classmethod
    def from_file(cls, filename: str):
        tree = ET.parse(filename)
        return cls(tree.getroot(), filename)
        
    def __init__(self, root, filename):
        self.root = root
        self.filename = filename
        self.vendor = root.find('Vendor/Name').text;
        self.vendor_id = EsiFile._hex_string(root.find('Vendor/Id').text);
        self.devices = {}
        for device_node in root.findall('Descriptions/Devices/Device'):
            device = {}
            device_name = device_node.find('Name').text;
            device_type = device_node.find('Type')
            device["Type"] = device_type.text;
            device["ProductCode"] = EsiFile._hex_string(device_type.get('ProductCode'))
            # objdict belongs to a profile. for now, assume one profile 
            device["ObjectDictionary"] = ObjectDictionary(self, device_node)
            device["Fmmu"] = self._parse_fmmu(device_node)
            device["Sm"] = self._parse_sync_managers(device_node)
            device["RxPdos"] = self._parse_pdos(device_node, "RxPdo")
            device["TxPdos"] = self._parse_pdos(device_node, "TxPdo")
            self.devices[device_name] = device

    def _parse_fmmu(self, device_node: ET.Element):
        fmmu_nodes = device_node.findall('Fmmu')
        fmmus = []
        for fmmu_node in fmmu_nodes:
            fmmus.append(fmmu_node.text)
        return fmmus

    def _parse_sync_managers(self, device_node: ET.Element):
        sm_nodes = device_node.findall('Sm')
        sms = {}
        for sm_node in sm_nodes:
            sm = {}
            sm["StartAddress"] = EsiFile._hex_string(sm_node.get("StartAddress"))
            sm["Type"] = EsiFile._sync_manager_type(sm_node.text)
            sm["DefaultSize"] = EsiFile._hex_string(sm_node.get("DefaultSize"))
            sm["MinSize"] = EsiFile._hex_string(sm_node.get("MinSize"))
            sm["MaxSize"] = EsiFile._hex_string(sm_node.get("MaxSize"))
            sm["Enable"] = EsiFile._xmlbool(sm_node.get("Enable"))
            sm["ControlByte"] = EsiFile._hex_string(sm_node.get("ControlByte"))
            sms[sm_node.text] = sm
        return sms

    def _parse_pdos(self, device_node: ET.Element, which_direction: str):
        ''' which_direction is TxPdo or RxPdo, can be multiple '''
        all = []
        for pdo_node in device_node.iter(which_direction):
            pdo = {}
            pdo["Index"] = EsiFile._hex_string(pdo_node.find('Index').text)
            pdo["Name"] = pdo_node.find('Name').text
            # now enumerate members
            size = 0
            entries = []
            for entry_node in pdo_node.iter('Entry'):
                entry = {}
                data_type = entry_node.find('DataType').text
                entry["DataType"] = data_type
                size = size + EsiFile._data_type_size(data_type)
                entry["Name"] = entry_node.find('Name').text
                entry["Index"] = EsiFile._hex_string(entry_node.find('Index').text)
                entry["SubIndex"] = EsiFile._hex_string(entry_node.find('SubIndex').text)
                entries.append(entry)
            pdo["Entries"] = entries
            pdo["Size"] = size
            all.append(pdo)
        return all

    @staticmethod
    def _hex_string(text):
        if not text:
            return None
        if '#x' == text[0:2]:
            return int(text[2:], 16)
        else:
            return int(text) # assume it's decimal

    @staticmethod
    def _xmlbool(text: str):
        if not text:
            return True # missing boolean attribute means true
        elif "1" == text:
            return True
        elif "0" == text:
            return False
        else:
            return ValueError("unrecognized bool value " + text)

    @staticmethod
    def _sync_manager_type(xmltext):
        '''
        https://content.helpme-codesys.com/en/libs/EtherCATStack/Current/EtherCATStack/pou-ETCSlaveStack/DynamicConfig/AddSyncManager.html
        '''
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

    @staticmethod
    def _data_type_size(data_type: str):
        return 0 # STUB

class ObjectDictionary:
    '''
    extract EtherCATInfo/Descriptions/Devices/Device/Profile/Dictionary/Objects
    as a flattened Python dictionary. This assumes there's a single device
    and profile in the document.
    '''
    def __init__(self, esi_file: EsiFile, device_node: ET.Element):
        self.esi_file = esi_file # for access to parent object
        self._tag_list = list() # list of an object's field names 
        # for testing if we have this one yet
        self._tag_set = set()
        # add the tags we want up front
        self._add_tag('Index')
        self._add_tag('SubIdx')
        self._add_tag('Name')
        self._add_tag('Type')
        self._add_tag('BitSize')
        self._add_tag('BitOffs')
        self._add_tag('DefaultValue')
        self._add_tag('MinValue')
        self._add_tag('MaxValue')
        self._add_tag('Access')
        self._add_tag('ModbusRegister')
        self._add_tag('PdoMapping')
        self._add_tag('Comment')
        # custom objects can refer to datatypes for internal
        # structure so first extract the custom types
        self.subitemtypes_dict = dict()
        self.enumtypes_dict = dict()
        self.datatypes = device_node.findall('Profile/Dictionary/DataTypes/DataType')
        for datatype in self.datatypes:
            datatype_name = datatype.find('Name').text
            if ObjectDictionary._is_builtin_datatype(datatype_name):
                pass # ignore these
            elif datatype.find('EnumInfo'):
                self.enumtypes_dict[datatype_name] = self._parse_enum(datatype_name, datatype)
            elif datatype.find('SubItem'):
                self.subitemtypes_dict[datatype_name] = self._parse_subitem(datatype)
            elif datatype.find('ArrayInfo'):
                self.subitemtypes_dict[datatype_name] = self._parse_array(datatype)
            else:
                print(f'Unknown datatype {datatype_name}')
        self.objects_dict = dict()
        objects = device_node.findall('Profile/Dictionary/Objects/Object')
        for object in objects:
            d = self._parse_object(object)
            dt = d['Type'] # datatype
            if ObjectDictionary._m.match(dt):
                # custom type, insert its subitems from DataType table
                for subitem in self.subitemtypes_dict[dt]['SubItems'].values():
                    # assume all uses have a common Index
                    newsubitem = copy.deepcopy(subitem)
                    newsubitem['Index'] = d['Index']
                    newsubitem['Name'] = d['Name'] + '/' + newsubitem['Name']
                    self.objects_dict[ObjectDictionary._make_object_key(newsubitem)] = newsubitem
            else:
                self.objects_dict[ObjectDictionary._make_object_key(d)] = d
            # expand objects with custom types
            self.object_fieldnames = self._tag_list

    def _add_tag(self, newTag):
        if newTag not in self._tag_set:
            self._tag_list.append(newTag)
            self._tag_set.add(newTag)
            #print("add_tag(" + newTag + ")")

    def _parse_object(self, object):
        d = dict()
        # init dummy keys for object table
        d['Index'] = ''
        d['SubIdx'] = ''
        for node in object:
            if 'Properties' == node.tag:
                for prop in node:
                    if 'Property' == prop.tag:
                        # should have Name and Value children
                        propname = prop.find('Name').text
                        propvalue = prop.find('Value').text
                        d[propname] = propvalue
                        self._add_tag(propname)
                    else:
                        print('Properties node contains ' + node.tag + ', skipping')
            elif ('Info' == node.tag) or ('Flags' == node.tag):
                # add the child nodes, instead, like flag names or min/max/default
                for subnode in node:
                    self._add_tag(subnode.tag)
                    d[subnode.tag] = subnode.text
            elif 'Comment' == node.tag:
                # multiple comments are allowed, concatenate, possibly adding a period.
                # this tag gets quoted, and double quotes get doubled to escape them.
                if node.tag in d:
                    if '.' != d[node.tag][-1]:
                        d[node.tag] = d[node.tag] + '.'
                    d[node.tag] = d[node.tag] + ' ' + node.text
                else:
                    d[node.tag] = node.text
            elif 'Property' == node.tag:
                # should have Name and Value children
                propname = node.find('Name').text
                propvalue = node.find('Value').text
                d[propname] = propvalue
                self._add_tag(propname)
            else:
                self._add_tag(node.tag)
                d[node.tag] = node.text
        return d
    
    def _parse_subitem(self, datatype):
        d = dict()
        subitems = dict()
        last_subidx = 0
        for node in datatype:
            if 'SubItem' == node.tag:
                subitem = self._parse_object(node)
                subidx = subitem['SubIdx']
                if '' != subidx:
                    last_subidx = int(subidx)
                else:
                    #print('SubItem ' + subitem['Name'] + ' lacks SubIdx node (array?)')
                    # synthesize one to sort at end
                    subidx_number = last_subidx + 1
                    subidx = f"{subidx_number}"
                    subitem['SubIdx'] = subidx
                    last_subidx = subidx_number
                subitems[subidx] = subitem
            else:
                d[node.tag] = node.text
        if len(subitems) > 0:
            d['SubItems'] = subitems
        return d;

    def _parse_array(self, datatype):
        d = dict()
        d['BaseType'] = datatype.find('BaseType').text
        dArrayInfo = dict()
        array_info = datatype.find('ArrayInfo')
        dArrayInfo['LBound'] = array_info.find('LBound').text
        dArrayInfo['Elements'] = array_info.find('Elements').text
        d['ArrayInfo'] = dArrayInfo
        return d;

    def _parse_enum(self, datatype_name, datatype):
        d = dict()
        d['Name'] = datatype_name
        d['BaseType'] = datatype.find('BaseType').text
        enumValues = dict()
        for enumInfo in datatype.iter('EnumInfo'):
            info = dict()
            info['Text'] = enumInfo.find('Text').text
            comment = enumInfo.find('Comment')
            if comment:
                info['Comment'] = comment.text
            value = enumInfo.find('Enum').text
            info['Value'] = value
            enumValues[value] = info
        d['Values'] = enumValues
        return d

    @staticmethod
    def _is_builtin_datatype(name):
        if name in [
            'BOOL',
            'SINT',
            'INT',
            'DINT',
            'LINT',
            'USINT',
            'BYTE',
            'UINT',
            'WORD',
            'UDINT',
            'DWORD',
            'ULINT',
            'LWORD',
            'REAL',
            'LREAL',
            # synonyms with encoded size
            'INT8',
            'INT16',
            'INT32',
            'INT64',
            'UINT8',
            'UINT16',
            'UINT32',
            'UINT64',
            'REAL32',
            'REAL64',
            # bit fields 
            'BIT',
            'BIT1',
            'BIT2',
            'BIT3',
            'BIT4',
            'BIT5',
            'BIT6',
            'BIT7',
            'BIT8',
            'BITARR8',
            'BITARR16',
            'BITARR32'
            ] :
            return True;
        if name.startswith('ARRAY ['):
            return True;
        if name.startswith('STRING('):
            return True;
        if name.startswith('VISIBLE_STRING('):
            return True;
        return False;

    # custom types should be DT followed by 4 hex digits
    _m = re.compile('^DT[0-9A-F]{4}$')

    @staticmethod
    def _make_object_key(object):
        ''' key looks like #x1234:56 with index in hex and subindex in decimal '''
        ''' subindex may be empty string '''
        ''' hex letters are uppercase '''
        return object['Index'] + ':' + object['SubIdx']


