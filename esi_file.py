# module with common ESI handling

import xml.etree.ElementTree as ET
import re
import copy # need deepcopy of subitemtypes since they get reused

class ObjectDictionary:

    @classmethod
    def from_string(cls, s):
        return cls(ET.fromstring(s), "")

    @classmethod
    def from_file(cls, filename):
        tree = ET.parse(filename)
        return cls(tree.getroot(), filename)
        
    def __init__(self, root, filename):
        self.root = root
        self.filename = filename
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
        # custom objects can refer to datatypes for internal structure
        self.subitemtypes_dict = dict()
        self.enumtypes_dict = dict()
        self.datatypes = root.findall('.//DataTypes/DataType')
        for datatype in self.datatypes:
            datatype_name = datatype.find('Name').text
            if datatype.find('EnumInfo'):
                self.enumtypes_dict[datatype_name] = self._parse_enum(datatype_name, datatype)
            elif datatype.find('SubItem'):
                self.subitemtypes_dict[datatype_name] = self._parse_subitem(datatype)
            #else:
            #   print(f'Unknown datatype {datatype_name}')
        self.objects_dict = dict()
        objects = root.findall('.//Objects/Object')
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
        
    # custom types should be DT followed by 4 hex digits
    _m = re.compile('^DT[0-9A-F]{4}$')

    @staticmethod
    def _make_object_key(object):
        ''' key looks like #x1234:56 with index in hex and subindex in decimal '''
        ''' subindex may be empty string '''
        ''' hex letters are uppercase '''
        return object['Index'] + ':' + object['SubIdx']


