#!/usr/bin/env python
# Filename: get_intersection 
"""
introduction: get intersection polygons

authors: Huang Lingcao
email:huanglingcao@gmail.com
add time: 1 March, 2019
"""

import os,sys
from optparse import OptionParser

HOME = os.path.expanduser('~')
# path of DeeplabforRS
codes_dir2 = HOME + '/codes/PycharmProjects/DeeplabforRS'
sys.path.insert(0, codes_dir2)

import basic_src.basic as basic
import vector_features


def main(options, args):

    polygons_shp1  = args[0]
    polygons_shp2  = args[1]
    output = options.output

    copy_fields = options.copy_fields
    if copy_fields is not None:
        copy_fields = copy_fields.split(',')

    if vector_features.get_intersection_of_polygon_polygon(polygons_shp1,polygons_shp2,output,copy_field=copy_fields):
        basic.outputlogMessage('get intersection, save to %s'%output)
    else:
        basic.outputlogMessage('get intersection failed')


if __name__ == "__main__":
    usage = "usage: %prog [options] shp_file1 shp_file2"
    parser = OptionParser(usage=usage, version="1.0 2019-3-1")
    parser.description = 'Introduction: get intersection polygons'

    parser.add_option("-o", "--output",
                      action="store", dest="output",
                      help="the output")

    parser.add_option("-c", "--copy_fields",
                      action="store", dest="copy_fields",
                      help="the multi field names to be copied, e.g., 'area,perimeter', use comma to sperate them but no space")


    (options, args) = parser.parse_args()
    if len(sys.argv) < 2:
        parser.print_help()
        sys.exit(2)

    main(options, args)