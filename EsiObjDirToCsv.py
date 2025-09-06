# dump the object directory from an EtherCAT ESI file to a CSV table

import argparse
parser = argparse.ArgumentParser(description='Extract object directory from EtherCAT ESI file as table in CSV format')
parser.add_argument('input_filename', help='path of ESI file')
parser.add_argument('output_filename', help='path of CSV file')
args = parser.parse_args()

# Step 1: Read and parse the XML file
import xml.etree.ElementTree as ET
tree = ET.parse(args.input_filename)
root = tree.getroot()

# Step 2: Extract the required information

# collect all potential tags to act as CSV field names
tag_list = list()
tag_set = set() # for testing if we have this one yet

def add_tag(newTag):
    if newTag not in tag_set:
        tag_list.append(newTag)
        tag_set.add(newTag)
        #print("add_tag(" + newTag + ")")

# add the tags we want up front
add_tag('Index')
add_tag('SubIdx')
add_tag('Name')
add_tag('Type')
add_tag('BitSize')
add_tag('BitOffs')
add_tag('DefaultValue')
add_tag('MinValue')
add_tag('MaxValue')
add_tag('Access')
add_tag('Comment')

def parse_object(object):
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
                    add_tag(propname)
                else:
                    print('Properties node contains ' + node.tag + ', skipping')
        elif ('Info' == node.tag) or ('Flags' == node.tag):
            # add the child nodes, instead, like flag names or min/max/default
            for subnode in node:
                add_tag(subnode.tag)
                d[subnode.tag] = subnode.text
        elif 'Comment' == node.tag:
            # multiple comments are allowed, concatenate, possibly adding a period.
            # this tag gets quoted, and double quotes get doubled to escape them.
            if node.tag in d:
                d[node.tag] = d[node.tag] + ' ' + node.text
            else:
                d[node.tag] = node.text
        elif 'Property' == node.tag:
            # should have Name and Value children
            propname = node.find('Name').text
            propvalue = node.find('Value').text
            d[propname] = propvalue
            add_tag(propname)
        else:
            add_tag(node.tag)
            d[node.tag] = node.text
    return d
    
# custom objects can refer to datatypes for internal structure
datatypes_dict = dict()
datatypes = root.findall('.//DataTypes/DataType')
for datatype in datatypes:
    d = dict()
    subitems = dict()
    for node in datatype:
        if 'SubItem' == node.tag:
            subitem = parse_object(node)
            if 'SubIdx' not in subitem:
                print('SubItem ' + subitem['Name'] + ' lacks SubIdx node (array?)')
                # synthesize one to sort at end
                subitem['SubIdx'] = '99'
            subitems[subitem['SubIdx']] = subitem
        else:
            d[node.tag] = node.text
    if len(subitems) > 0:
        d['SubItems'] = subitems
    datatypes_dict[d['Name']] = d;
print(len(datatypes_dict), 'DataTypes')

# custom types should be DT followed by 4 hex digits
import re
m = re.compile('^DT[0-9A-F]{4}$')

objects_dict = dict()

def make_object_key(object):
    return object['Index'] + ':' + object['SubIdx']

objects = root.findall('.//Objects/Object')
for object in objects:
    d = parse_object(object)
    dt = d['Type'] # datatype
    if m.match(dt):
        # custom type, insert its subitems from DataType table
        for subitem in datatypes_dict[dt]['SubItems'].values():
            # assume all uses have a common Index
            subitem['Index'] = d['Index']
            objects_dict[make_object_key(subitem)] = subitem
    objects_dict[make_object_key(d)] = d
    # expand objects with custom types
    
print(len(objects_dict), 'Objects and sub-Objects')
object_fieldnames = tag_list

from csv import DictWriter
with open(args.output_filename, 'w', newline = '', encoding='UTF-8') as csv_file:
    writer = DictWriter(csv_file, fieldnames = object_fieldnames)
    writer.writeheader()
    for id, object in objects_dict.items():
        writer.writerow(object)
