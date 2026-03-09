# dump the object directory from an EtherCAT ESI file to a CSV table

import argparse
from esi_file import ObjectDictionary

parser = argparse.ArgumentParser(description='Extract object directory from EtherCAT ESI file as table in CSV format')
parser.add_argument('input_filename', help='path of ESI file')
parser.add_argument('output_filename', help='path of CSV file')
args = parser.parse_args()

obj_dict = ObjectDictionary.from_file(args.input_filename)

print(len(obj_dict.subitemtypes_dict), 'SubItems')
print(len(obj_dict.enumtypes_dict), 'Enums')
print(len(obj_dict.objects_dict), 'Objects and sub-Objects')

def write_enum(name, enum, csv_file):
    print('', file=csv_file)
    basetype = enum['BaseType']
    print(f'enum {name} {basetype}', file=csv_file)
    print('value, name, comment', file=csv_file)
    enum_writer = DictWriter(csv_file, fieldnames = ['Value', 'Text', 'Comment'])
    for value in enum['Values'].values():
        enum_writer.writerow(value)

from csv import DictWriter
with open(args.output_filename, 'wt', encoding='UTF-8') as csv_file:
    writer = DictWriter(csv_file, fieldnames = obj_dict.object_fieldnames)
    writer.writeheader()
    for object in obj_dict.objects_dict.values():
        writer.writerow(object)
    for name, enum in obj_dict.enumtypes_dict.items():
        write_enum(name, enum, csv_file)
