#!/usr/bin/env python
# Filename: get_subImages 
"""
introduction: get sub Images (and Labels) from training polygons directly, without gdal_rasterize

authors: Huang Lingcao
email:huanglingcao@gmail.com
add time: 26 September, 2019
"""

import sys,os
from optparse import OptionParser

HOME = os.path.expanduser('~')
# path of DeeplabforRS
codes_dir2 = HOME + '/codes/PycharmProjects/DeeplabforRS'
sys.path.insert(0, codes_dir2)

import basic_src.io_function as io_function
import basic_src.basic as basic

# import thest two to make sure load GEOS dll before using shapely
import shapely
import shapely.geometry

import rasterio
from rasterio.mask import mask
from rasterio.features import rasterize
from shapely.geometry import mapping # transform to GeJSON format

import geopandas as gpd

import math

def get_image_tile_bound_boxes(image_tile_list):
    '''
    get extent of all the images
    :param image_tile_list:  a list containing all the image path
    :return:  a list of boxes
    '''
    boxes = []
    for image_path in image_tile_list:
        with rasterio.open(image_path) as src:
            # the extent of the raster
            raster_bounds = src.bounds
            boxes.append(raster_bounds)

    return boxes

def get_overlap_image_index(polygons,image_boxes):
    '''
    get the index of images that the polygons overlap
    :param polygons: a list of polygons
    :param image_boxes: the extent of the all the images
    :return:
    '''

     # find the images which the polygons overlap (one or two images)
    img_idx = []
    # for a_poly in polygons:
    #     a_poly_json = mapping(a_poly)
    #     polygon_box = rasterio.features.bounds(a_poly_json)
    polygon_box = get_bounds_of_polygons(polygons)
    for idx, img_box in enumerate(image_boxes):
        if rasterio.coords.disjoint_bounds(img_box, polygon_box) is False:
            if idx not in img_idx:
                img_idx.append(idx)
    return img_idx

def check_polygons_invalidity(polygons, shp_path):
    '''
    check if all the polygons are valid
    :param polygons:  polygons in shapely format
    :param shp_path:  the shape file containing the polygons
    :return:
    '''
    invalid_polygon_idx = []
    for idx, geom in enumerate(polygons):
        if geom.is_valid is False:
            invalid_polygon_idx.append(idx + 1)

    if len(invalid_polygon_idx) < 1:
        return True
    else:
        raise ValueError('error, polygons %s (index start from 1) in %s are invalid, please fix them first '%(str(invalid_polygon_idx),shp_path))

def check_projection_rasters(image_path_list):
    '''
    check the rasters: have the samep projectoin
    :param image_path_list: a list containing all the images
    :return:
    '''

    if len(image_path_list) < 2:
        return True
    proj4 = get_projection_proj4(image_path_list[0])
    for idx in range(1,len(image_path_list)):
        proj4_tmp = get_projection_proj4(image_path_list[idx])
        if proj4_tmp != proj4:
            raise ValueError('error, %s have different projection with the first raster'%image_path_list[idx])
    return True

def meters_to_degress_onEarth(distance):
    return (distance/6371000.0)*180.0/math.pi


def get_projection_proj4(geo_file):
    '''
    get the proj4 string
    :param geo_file: a shape file or raster file
    :return: projection string in prj4 format
    '''

    shp_args_list = ['gdalsrsinfo','-o','proj4',geo_file]
    prj4_str = basic.exec_command_args_list_one_string(shp_args_list)
    if prj4_str is False:
        raise ValueError('error, get projection information of %s failed'%geo_file)
    return prj4_str

def get_bounds_of_polygons(polygons):
    '''
    Return a (left, bottom, right, top) bounding box for several polygons
    :param polygons:  a list of polygons
    :return:
    '''

    X_min, Y_min, X_max, Y_max = polygons[0].bounds
    if len(polygons) < 2:
        return (X_min, Y_min, X_max, Y_max)
    else:
        for idx in range(1, len(polygons)):
            bounds = polygons[idx].bounds  # return (X_min, Y_min, X_max, Y_max)
            if bounds[0] < X_min: X_min = bounds[0]
            if bounds[1] < Y_min: Y_min = bounds[1]
            if bounds[2] > X_max: X_max = bounds[2]
            if bounds[3] > Y_max: Y_max = bounds[3]

    return (X_min, Y_min, X_max, Y_max)


def get_adjacent_polygons(center_polygon, all_polygons, class_int_all, buffer_size):
    '''
    find the adjacent polygons
    :param center_polygon: a center polygon
    :param all_polygons: the full set of training polygons
    :param class_int_all: the class the full set of training polygons
    :param buffer_size: a size to define adjacent areas e.g., 300m
    :return: the list contain adjacent polygons, and their class
    '''

    # get buffer area
    expansion_polygon = center_polygon.buffer(buffer_size)
    adjacent_polygon = []
    adjacent_polygon_class = []
    for idx, polygon in enumerate(all_polygons):
        # skip itself
        if polygon == center_polygon:
            continue
        # print(idx)
        inte_res = expansion_polygon.intersection(polygon)
        if inte_res.is_empty is False:
            adjacent_polygon.append(polygon)
            adjacent_polygon_class.append(class_int_all[idx])

    return adjacent_polygon, adjacent_polygon_class

def get_sub_image(idx,selected_polygon, image_tile_list, image_tile_bounds, save_path, dstnodata, brectangle ):
    '''
    get a mask image based on a selected polygon, it may cross two image tiles
    :param selected_polygon: selected polygons
    :param image_tile_list: image list
    :param image_tile_bounds: the boxes of images in the list
    :param save_path: save path
    :param brectangle: if brectangle is True, crop the raster using bounds, else, use the polygon
    :return: True is successful, False otherwise
    '''

    # find the images which the center polygon overlap (one or two images)
    img_index = get_overlap_image_index([selected_polygon], image_tile_bounds)
    if len(img_index) < 1:
        basic.outputlogMessage(
            'Warning, %dth polygon do not overlap any image tile, please check ' #and its buffer area
            '(1) the shape file and raster have the same projection'
            'and (2) this polygon is in the extent of images' % idx)
        return False

    image_list = [image_tile_list[item] for item in img_index]

    # check it cross two or more images
    if len(image_list) == 1:
        # for the case that the polygon only overlap one raster
        with rasterio.open(image_list[0]) as src:
            polygon_json = mapping(selected_polygon)

            # not necessary
            # overlap_win = rasterio.features.geometry_window(src, [polygon_json], pad_x=0, pad_y=0, north_up=True, rotated=False,
            #                               pixel_precision=3)

            if brectangle:
                # polygon_box = selected_polygon.bounds
                polygon_json = mapping(selected_polygon.envelope) #shapely.geometry.Polygon([polygon_box])

            # crop image and saved to disk
            out_image, out_transform = mask(src, [polygon_json], nodata=dstnodata, all_touched=True, crop=True)

            # test: save it to disk
            out_meta = src.meta.copy()
            out_meta.update({"driver": "GTiff",
                             "height": out_image.shape[1],
                             "width": out_image.shape[2],
                             "transform": out_transform})  # note that, the saved image have a small offset compared to the original ones (~0.5 pixel)
            with rasterio.open(save_path, "w", **out_meta) as dest:
                dest.write(out_image)
        pass
    else:
        # for the case it overlap more than one raster, need to produce a mosaic
        tmp_saved_files = []

        for k_img,image_path in enumerate(image_list):
            with rasterio.open(image_path) as src:
                polygon_json = mapping(selected_polygon)
                if brectangle:
                    # polygon_box = selected_polygon.bounds
                    polygon_json = mapping(selected_polygon.envelope)  # shapely.geometry.Polygon([polygon_box])

                # crop image and saved to disk
                out_image, out_transform = mask(src, [polygon_json], nodata=dstnodata, all_touched=True, crop=True)

                tmp_saved = os.path.splitext(save_path)[0] +'_%d'%k_img + os.path.splitext(save_path)[1]
                # test: save it to disk
                out_meta = src.meta.copy()
                out_meta.update({"driver": "GTiff",
                                 "height": out_image.shape[1],
                                 "width": out_image.shape[2],
                                 "transform": out_transform})  # note that, the saved image have a small offset compared to the original ones (~0.5 pixel)
                with rasterio.open(tmp_saved, "w", **out_meta) as dest:
                    dest.write(out_image)
                tmp_saved_files.append(tmp_saved)

        # mosaic files in tmp_saved_files
        mosaic_args_list = ['gdal_merge.py', '-o', save_path,'-n',str(dstnodata),'-a_nodata',str(dstnodata)]
        mosaic_args_list.extend(tmp_saved_files)
        if basic.exec_command_args_list_one_file(mosaic_args_list,save_path) is False:
            raise IOError('error, obtain a mosaic (%s) failed'%save_path)

        # # for test
        # if idx==13:
        #     raise ValueError('for test')

        # remove the tmp files
        for tmp_file in tmp_saved_files:
            io_function.delete_file_or_dir(tmp_file)

    # if it will output a very large image (10000 by 10000 pixels), then raise a error

    return True

def get_one_sub_image_label(idx,center_polygon, class_int, polygons_all,class_int_all, bufferSize, img_tile_boxes,image_tile_list):
    '''
    get an sub image and the corresponding labe raster
    :param idx: the polygon index
    :param center_polygon: the polygon in training polygon
    :param class_int: the class number of this polygon
    :param polygons_all: the full set of training polygons, for generating label images
    :param class_int_all: the class number for the full set of training polygons
    :param bufferSize: the buffer area to generate sub-images
    :param img_tile_boxes: the bound boxes of all the image tiles
    :param image_tile_list: the list of image paths
    :return:
    '''

    ############# This funciton is not working  #############

    # center_polygon corresponds to one polygon in the full set of training polygons, so it is not necessary to check
    # get adjacent polygon
    adj_polygons, adj_polygons_class = get_adjacent_polygons(center_polygon, polygons_all, class_int_all, bufferSize)

    # add the center polygons to adj_polygons
    adj_polygons.extend([center_polygon])
    adj_polygons_class.extend([class_int])
    basic.outputlogMessage('get a sub image covering %d training polygons'%len(adj_polygons))

    # find the images which the center polygon overlap (one or two images)
    img_index = get_overlap_image_index(adj_polygons, img_tile_boxes)
    if len(img_index) < 1:
        basic.outputlogMessage('Warning, %dth polygon and the adjacent ones do not overlap any image tile, please check '
                               '(1) the shape file and raster have the same projection'
                               'and (2) this polygon is in the extent of images'%idx)

    image_list = [image_tile_list[item] for item in img_index]

    # open the raster to get projection, resolution
    # with rasterio.open(image_list[0]) as src:
    #     resX = src.res[0]
    #     resY = src.res[1]
    #     src_profile = src.profile
    src = rasterio.open(image_list[0])
    resX = src.res[0]
    resY = src.res[1]
    src_profile = src.profile

    # rasterize the shapes
    burn_shapes = [(item_shape, item_class_int) for (item_shape, item_class_int) in zip(adj_polygons,adj_polygons_class)]
    burn_boxes = get_bounds_of_polygons(adj_polygons)

    # check weather the extent is too large
    burn_boxes_width = math.ceil((burn_boxes[2]- burn_boxes[0])/resX)
    burn_boxes_height = math.ceil((burn_boxes[3] - burn_boxes[1])/resY)

    if  burn_boxes_width*burn_boxes_height > 10000*10000:
        raise ValueError('error, the polygons want to burn cover a very large area')

    # fill as 255 for region outsize shapes for test purpose
    # set all_touched as True, may good small shape
    # new_transform = (burn_boxes[0], resX, 0, burn_boxes[3], 0, -resY )  # (X_min, resX, 0, Y_max, 0, -resY)  # GDAL-style transforms, have been deprecated after raster 1.0
    # affine.Affine() vs. GDAL-style geotransforms: https://rasterio.readthedocs.io/en/stable/topics/migrating-to-v1.html
    new_transform = (resX ,0, burn_boxes[0] , 0, -resY, burn_boxes[3])  # (resX, 0, X_min, 0, -resY, Y_max)
    out_label = rasterize(burn_shapes, out_shape=(burn_boxes_width,burn_boxes_height), transform=new_transform, fill=0, all_touched=False, dtype=rasterio.uint8)
    print('new_transform', new_transform)
    print('out_label', out_label.shape)


    # test, save to disk
    kwargs = src.meta
    kwargs.update(
        dtype=rasterio.uint8,
        count=1,
        width=burn_boxes_width,
        height = burn_boxes_height,
        transform=new_transform)
    with rasterio.open('test_6_albers.tif', 'w', **kwargs) as dst:
        dst.write_band(1, out_label.astype(rasterio.uint8))

    # mask, get pixels cover by polygons, set all_touched as True
    polygons_json = [mapping(item) for item in adj_polygons]
    out_image, out_transform = mask(src, polygons_json, nodata=0, all_touched=True, crop=True)

    #test: output infomation
    print('out_transform', out_transform)
    print('out_image',out_image.shape)

    # test: save it to disk
    out_meta = src.meta.copy()
    out_meta.update({"driver": "GTiff",
                     "height": out_image.shape[1],
                     "width": out_image.shape[2],
                     "transform": out_transform})   # note that, the saved image have a small offset compared to the original ones (~0.5 pixel)
    save_path = "masked_of_polygon_%d.tif"%(idx+1)
    with rasterio.open(save_path, "w", **out_meta) as dest:
        dest.write(out_image)



    # return image_array, label_array
    return 1, 1

def get_sub_images_and_labels(t_polygons_shp, t_polygons_shp_all, bufferSize, image_tile_list, saved_dir, pre_name, dstnodata, brectangle = True):
    '''
    get sub images (and labels ) from training polygons
    :param t_polygons_shp: training polygon
    :param t_polygons_shp_all: the full set of training polygon, t_polygons_shp is a subset or equal to this one.
    :param bufferSize: buffer size of a center polygon to create a sub images
    :param image_tile_list: image tiles
    :param saved_dir: output dir
    :param dstnodata: nodata when save for the output images
    :param brectangle: True: get the rectangle extent of a images.
    :return:
    '''


    # read polygons
    t_shapefile = gpd.read_file(t_polygons_shp)
    class_labels = t_shapefile['class_int'].tolist()
    center_polygons = t_shapefile.geometry.values
    check_polygons_invalidity(center_polygons,t_polygons_shp)

    # read the full set of training polygons, used this one to produce the label images
    t_shapefile_all = gpd.read_file(t_polygons_shp_all)
    class_labels_all = t_shapefile_all['class_int'].tolist()
    polygons_all = t_shapefile_all.geometry.values
    check_polygons_invalidity(polygons_all,t_polygons_shp_all)


    img_tile_boxes = get_image_tile_bound_boxes(image_tile_list)

    # go through each polygon
    for idx, (c_polygon, c_class_int)  in enumerate(zip(center_polygons,class_labels)):

        # output message
        basic.outputlogMessage('obtaining %d sub-image and the corresponding label raster'%idx)

        ## get an image and the corresponding label raster (has errors)
        ## image_array, label_array = get_one_sub_image_label(idx,c_polygon, class_labels[idx], polygons_all, class_labels_all, bufferSize, img_tile_boxes,image_tile_list)

        # get buffer area
        expansion_polygon = c_polygon.buffer(bufferSize)

        # get one sub-image based on the buffer areas
        subimg_saved_path = os.path.join(saved_dir, 'subImages' , pre_name+'_%d_class_%d.tif'%(idx,c_class_int))
        if get_sub_image(idx,expansion_polygon,image_tile_list,img_tile_boxes, subimg_saved_path, dstnodata, brectangle) is False:
            basic.outputlogMessage('Warning, skip the %dth polygon'%idx)
            continue

        # based on the sub-image, create the corresponding vectors
        # pre_name = 'raster'
        # sublabel_saved_path = os.path.join(saved_dir, 'subLabels', pre_name + '_%d_class_%d.tif' % (idx, c_class_int))

        # save to dir

        pass

    test = 1






    #extract the geometry in GeoJSON format

    if t_polygons_shp_all != t_polygons_shp:
        # find the training polygons in the full set
        pass


    # find the data in the shape


    pass

def main(options, args):

    t_polygons_shp = args[0]
    image_folder = args[1]   # folder for store image tile (many split block of a big image)

    # check training polygons
    assert io_function.is_file_exist(t_polygons_shp)
    t_polygons_shp_all = options.all_training_polygons
    if t_polygons_shp_all is None:
        basic.outputlogMessage('Warning, the full set of training polygons is not assigned, '
                               'it will consider the one in input argument is the full set of training polygons')
        t_polygons_shp_all = t_polygons_shp
    else:
        if get_projection_proj4(t_polygons_shp) != get_projection_proj4(t_polygons_shp_all):
            raise ValueError('error, projection insistence between %s and %s'%(t_polygons_shp, t_polygons_shp_all))
    assert io_function.is_file_exist(t_polygons_shp_all)

    # get image tile list
    image_tile_list = io_function.get_file_list_by_ext(options.image_ext, image_folder, bsub_folder=False)
    if len(image_tile_list) < 1:
        raise IOError('error, failed to get image tiles in folder %s'%image_folder)

    check_projection_rasters(image_tile_list)   # it will raise errors if found problems

    #need to check: the shape file and raster should have the same projection.
    if get_projection_proj4(t_polygons_shp) != get_projection_proj4(image_tile_list[0]):
        raise ValueError('error, the input raster (e.g., %s) and vector (%s) files don\'t have the same projection'%(image_tile_list[0],t_polygons_shp))

    # check these are EPSG:4326 projection
    if get_projection_proj4(t_polygons_shp) == '+proj=longlat +datum=WGS84 +no_defs':
        bufferSize = meters_to_degress_onEarth(options.bufferSize)
    else:
        bufferSize = options.bufferSize

    saved_dir = options.out_dir
    os.system('mkdir -p ' + os.path.join(saved_dir,'subImages'))
    os.system('mkdir -p ' + os.path.join(saved_dir,'subLabels'))
    dstnodata = options.dstnodata
    pre_name = '_'.join(os.path.basename(image_tile_list[0]).split('_')[:4])
    get_sub_images_and_labels(t_polygons_shp, t_polygons_shp_all, bufferSize, image_tile_list, saved_dir, pre_name, dstnodata, brectangle=True)

    # move sub images and sub labels to different folders.



if __name__ == "__main__":
    usage = "usage: %prog [options] training_polygons image_folder"
    parser = OptionParser(usage=usage, version="1.0 2019-9-26")
    parser.description = 'Introduction: get sub Images (and Labels) from training polygons directly, without gdal_rasterize. ' \
                         'The image and shape file should have the same projection.'
    parser.add_option("-f", "--all_training_polygons",
                      action="store", dest="all_training_polygons",
                      help="the full set of training polygons. If the one in the input argument "
                           "is a subset of training polygons, this one must be assigned")
    parser.add_option("-b", "--bufferSize",
                      action="store", dest="bufferSize",type=float,
                      help="buffer size is in the projection, normally, it is based on meters")
    parser.add_option("-e", "--image_ext",
                      action="store", dest="image_ext",default = '.tif',
                      help="the extension of the image file")
    parser.add_option("-o", "--out_dir",
                      action="store", dest="out_dir",
                      help="the folder path for saving output files")
    parser.add_option("-n", "--dstnodata", type=int,
                      action="store", dest="dstnodata",
                      help="the nodata in output images")
    parser.add_option("-r", "--rectangle",
                      action="store_true", dest="rectangle",default=False,
                      help="whether use the rectangular extent of the polygon")


    (options, args) = parser.parse_args()
    if len(sys.argv) < 2 or len(args) < 1:
        parser.print_help()
        sys.exit(2)

    # if options.para_file is None:
    #     basic.outputlogMessage('error, parameter file is required')
    #     sys.exit(2)

    main(options, args)