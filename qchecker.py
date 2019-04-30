import os
import json
import logging
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, Polygon
from shapely import wkt
import subprocess
from laspy.file import File
import xml.etree.ElementTree as ET
import arcpy
import pathos.pools as pp
import re
from geodaisy import GeoObject
import ast
import math
import time
import progressbar

from bokeh.models.widgets import Panel, Tabs
from bokeh.io import output_file, show
from bokeh.models import ColumnDataSource, PrintfTickFormatter, GeoJSONDataSource, Legend, Range1d
from bokeh.plotting import figure
from bokeh.tile_providers import get_provider, Vendors
from bokeh.palettes import Blues
from bokeh.transform import log_cmap, factor_cmap
from bokeh.layouts import layout, gridplot


os.environ["GDAL_DATA"] = r'C:\\Users\\Nick.Forfinski-Sarko\\AppData\\Local\\Continuum\\anaconda3\\envs\\qchecker\\Library\\share\\gdal'
os.environ["PROJ_LIB"] = r'C:\\Users\\Nick.Forfinski-Sarko\\AppData\\Local\\Continuum\\anaconda3\\envs\\qchecker\\Library\\share'

# may also have to add the following paths
# C:\Program Files\ArcGIS\Pro\bin
# C:\Program Files\ArcGIS\Pro\Resources\ArcPy
# C:\Program Files\ArcGIS\Pro\Resources\ArcToolbox\Scripts


class SummaryPlots:

    def __init__(self, config, qaqc_results_df):
        self.config = config
        self.qaqc_results_df = qaqc_results_df

        with open(self.config.qaqc_geojson_WebMercator_CENTROIDS) as f:
            geojson_qaqc_centroids = f.read()

        self.qaqc_centroids = GeoJSONDataSource(geojson=geojson_qaqc_centroids)

        self.check_labels = {
            'naming_passed': 'Naming Convention',
            'version_passed': 'Version',
            'pdrf_passed': 'Point Data Record Format',
            'gps_time_passed': 'GPS Time Type',
            'hdatum_passed': 'Horizontal Datum',
            'vdatum_passed': 'Vertical Datum',
            'pt_src_ids_passed': 'Point Source IDs',
            'exp_cls_passed': 'Expected Classes'}

        def get_classes_present(fields):
            present_classes = []
            for f in fields:
                if 'class' in f:
                    present_classes.append(f)
            return present_classes

        def get_test_results():
            fields = self.qaqc_results_df.columns
            test_result_fields = []
            for f in fields:
                if '_passed' in f:
                    test_result_fields.append(f)
            return self.qaqc_results_df[test_result_fields]

        def get_las_classes():
            las_classes_json = r'las_classes.json'
            with open(las_classes_json) as lcf:
                las_classes = json.load(lcf)
            
            def find(key, dictionary):
                for k, v in dictionary.items():
                    if k == key:
                        yield v
                    elif isinstance(v, dict):
                        for result in find(key, v):
                            yield result
                    elif isinstance(v, list):
                        for d in v:
                            if isinstance(d, dict):
                                for result in find(key, d):
                                    yield result

            return find('classes', las_classes)

        self.las_classes = {}
        for class_list in get_las_classes():
            self.las_classes.update(class_list)

        test_results = get_test_results()
        test_result_fields = test_results.columns

        # add column for PASSED or FAILED if it's not there (to make PASS/FAIL plotting easy)
        self.result_counts = self.qaqc_results_df[test_result_fields].apply(pd.Series.value_counts).fillna(0).transpose()
        if 'FAILED' not in self.result_counts.columns and 'PASSED' in self.result_counts.columns:
            self.result_counts['FAILED'] = 0
        if 'PASSED' not in self.result_counts.columns and 'FAILED' in self.result_counts.columns:
            self.result_counts['PASSED'] = 0
        if 'FAILED' not in self.result_counts.columns and 'PASSED' not in self.result_counts.columns:
            self.result_counts = pd.DataFrame({'FAILED': 0, 'PASSED': 0}, index=['No_Test_Selected'])

        present_classes = get_classes_present(self.qaqc_results_df.columns)
        self.class_counts = self.qaqc_results_df[present_classes].sum().to_frame()
        self.class_counts.columns = ['counts']
        self.TOOLS = 'box_zoom,box_select,crosshair,reset,wheel_zoom'

    @staticmethod
    def add_empty_plots_to_reshape(plot_list):
        len_check_pass_fail_plots = len(plot_list)
        while len_check_pass_fail_plots % 3 != 0:
            p = figure(plot_width=300, plot_height=300)
            p.outline_line_color = None
            p.toolbar.logo = None
            p.toolbar_location = None
            p.xaxis.major_tick_line_color = None
            p.xaxis.minor_tick_line_color = None
            p.yaxis.major_tick_line_color = None
            p.yaxis.minor_tick_line_color = None
            p.xgrid.grid_line_color = None
            p.ygrid.grid_line_color = None
            p.xaxis.major_label_text_font_size = '0pt'
            p.yaxis.major_label_text_font_size = '0pt'
            p.xaxis.axis_line_color = None
            p.yaxis.axis_line_color = None
            p.circle(0, 0, alpha=0.0)
            plot_list.append(p)
            len_check_pass_fail_plots += 1
        return plot_list

    def draw_pass_fail_bar_chart(self):
        # TEST RESULTS PASS/FAIL
        source = ColumnDataSource(self.result_counts)
        if source.data['index'][0] != 'No_Test_Selected':
            source.data.update({'labels': ['{}'.format(self.check_labels[i]) for i in source.data['index']]})

            failed = source.data.get('FAILED')
            passed = source.data.get('PASSED')

            source.data.update({'FAILED_stack': failed + passed})

            cats = ['PASSED', 'FAILED']
            p1 = figure(y_range=source.data['labels'], title="Check PASS/FAIL Results", 
                        plot_width=400, plot_height=400)
            
            p1.min_border_top = 100
            p1.min_border_bottom = 50

            p1.toolbar.logo = None
            p1.toolbar_location = None

            r_pass = p1.hbar(left=0, right='PASSED', y='labels',  height=0.9, color='#3cb371', 
                                source=source, name='PASSED', line_color=None)

            r_fail = p1.hbar(left='PASSED', right='FAILED_stack', y='labels', height=0.9, 
                                color='#FF0000', source=source, name='FAILED', line_color=None)

            p1.xgrid.grid_line_color = None

            max_passed = max(passed)
            max_failed = max(failed)
            max_val = max(max_passed, max_failed)

            p1.x_range = Range1d(0, max_val + 0.1 * max_val)
            p1.axis.minor_tick_line_color = None
            p1.outline_line_color = None

            legend = Legend(items=[
                ("PASSED", [r_pass]),
                ("FAILED", [r_fail]),
                ], location=(1, 15))
            p1.add_layout(legend, 'above')
            p1.legend.orientation = "horizontal"
        else:
            p1 = figure(title="No Tests Selected", 
                        plot_width=400, 
                        plot_height=300) 

        return p1

    def draw_class_count_bar_chart(self):
        # CLASS COUNTS
        self.class_counts['Expected'] = np.zeros(self.class_counts.index.size)
        self.class_counts['Unexpected'] = np.zeros(self.class_counts.index.size)
        for i, class_name in enumerate(self.class_counts.index):
            class_num = int(class_name.replace('class', ''))
            if class_num in self.config.exp_cls_key:
                self.class_counts['Expected'][i] = self.class_counts['counts'][i]
            else:
                self.class_counts['Unexpected'][i] = self.class_counts['counts'][i]

        source = ColumnDataSource(self.class_counts)
        source.data.update({'labels': ['{} (Class {})'.format(
            self.las_classes[c.replace('class', '').zfill(2)], 
            c.replace('class', '').zfill(2)) for c in source.data['index']]})

        p2 = figure(y_range=source.data['labels'], plot_width=400, plot_height=400, 
                    title="Class Counts", tools="")
        p2.min_border_top = 100
        p2.outline_line_color = None
        p2.toolbar.logo = None
        p2.toolbar_location = None
        p2.xaxis[0].formatter = PrintfTickFormatter(format='%4.1e')

        p2_expected = p2.hbar(y='labels', right='Expected', 
                                height=0.9, color='#0074D9', source=source)

        p2_unexpected = p2.hbar(y='labels', right='Unexpected', 
                                height=0.9, color='#FF851B', source=source)

        max_count = max(source.data['counts'])
        self.class_counts = self.class_counts.drop(['counts'], axis=1)
        p2.x_range = Range1d(0, max_count + 0.1 * max_count)
        p2.xgrid.grid_line_color = None
        p2.xaxis.major_label_orientation = "vertical"
        p2.xaxis.minor_tick_line_color = None

        legend = Legend(items=[('EXPECTED', [p2_expected]), ('UNEXPECTED', [p2_unexpected])], location=(0, 10))
        p2.add_layout(legend, 'above')

        return p2

    def draw_pass_fail_maps(self):
        check_pass_fail_plots = []
        if self.result_counts.index[0] != 'No_Test_Selected':
            for i, check_field in enumerate(self.result_counts.index):
                title = self.check_labels[check_field]

                if i > 0:
                    p = figure(title=title, x_axis_type="mercator", y_axis_type="mercator", 
                                x_range=check_pass_fail_plots[0].x_range,
                                y_range=check_pass_fail_plots[0].y_range,
                                plot_width=300, plot_height=300, match_aspect=True, 
                                tools=self.TOOLS)
                else:
                    p = figure(title=title, x_axis_type="mercator", y_axis_type="mercator", 
                                plot_width=300, plot_height=300, match_aspect=True, 
                                tools=self.TOOLS)

                p.toolbar.logo = None
                #p.toolbar_location = None

                cmap = {
                    'PASSED': '#3cb371',
                    'FAILED': '#FF0000',
                    }

                color_mapper = factor_cmap(field_name=check_field, 
                                            palette=list(cmap.values()), 
                                            factors=list(cmap.keys()))

                p.add_tile(get_provider(Vendors.CARTODBPOSITRON))
                #p.patches(xs='xs', ys='ys', source=tile_polygons, fill_color=None, color='lightgray')
                p.circle(x='x', y='y', size=3, alpha=0.5, 
                            source=self.qaqc_centroids, color=color_mapper)
                
                check_pass_fail_plots.append(p)

        check_pass_fail_plots = self.add_empty_plots_to_reshape(check_pass_fail_plots)
        pass_fail_grid_plot = gridplot(check_pass_fail_plots, ncols=3, plot_height=300, 
                                        toolbar_location='right')

        tab1 = Panel(child=pass_fail_grid_plot, title="Checks Pass/Fail")

        return tab1

    def draw_class_count_maps(self):
        min_count = self.qaqc_results_df[self.class_counts.index].min().min()
        max_count = self.qaqc_results_df[self.class_counts.index].max().max()

        class_count_plots = []
        for i, class_field in enumerate(self.class_counts.index):
            palette = Blues[9]
            palette.reverse()

            color_mapper = log_cmap(field_name=class_field, palette=palette, 
                                    low=min_count, high=max_count, nan_color='white')

            las_class = class_field.replace('class', '').zfill(2)
            title = 'Class {} ({})'.format(las_class, self.las_classes[las_class])

            if i > 0:
                p = figure(title=title,
                            x_axis_type="mercator", y_axis_type="mercator", 
                            x_range=class_count_plots[0].x_range,
                            y_range=class_count_plots[0].y_range,
                            plot_width=300, plot_height=300,
                            match_aspect=True, tools=self.TOOLS)
            else:
                p = figure(title=title,
                            x_axis_type="mercator", y_axis_type="mercator", 
                            plot_width=300, plot_height=300,
                            match_aspect=True, tools=self.TOOLS)

            if int(las_class) in self.config.exp_cls_key:
                title_color = '#0074D9'
            else:
                title_color = '#FF851B'

            p.title.text_color = title_color
            #p.outline_line_width = 3
            #p.outline_line_alpha = 0.6
            #p.outline_line_color = title_color
            p.toolbar.logo = None
            #p.toolbar_location = None

            p.add_tile(get_provider(Vendors.CARTODBPOSITRON))
            p.circle(x='x', y='y', size=3, alpha=0.5, 
                        source=self.qaqc_centroids, color=color_mapper)

            class_count_plots.append(p)

        class_count_plots = self.add_empty_plots_to_reshape(class_count_plots)
        class_count_grid_plot = gridplot(class_count_plots, ncols=3, plot_height=300, 
                                            toolbar_location='right')

        tab2 = Panel(child=class_count_grid_plot, title="Class Counts")

        return tab2

    def gen_dashboard(self):

        pass_fail_bar = self.draw_pass_fail_bar_chart()
        class_count_bar = self.draw_class_count_bar_chart()
        pass_fail_tab = self.draw_pass_fail_maps()
        class_count_tab = self.draw_class_count_maps()

        output_file('{}\QAQC_Summary_{}.html'.format(self.config.qaqc_dir, self.config.project_name))

        tabs = Tabs(tabs=[pass_fail_tab, class_count_tab])

        l = layout([
            [[pass_fail_bar, class_count_bar], tabs],
            ])
        show(l)


class Configuration:
    def __init__(self, config):

        data = None
        with open(config) as f:
            data = json.load(f)

        self.data = data

        self.project_name = arcpy.ValidateTableName(data['project_name'])
        self.las_tile_dir = data['las_tile_dir']
        
        self.qaqc_dir = os.path.join(data['qaqc_dir'], self.project_name)
        if not os.path.exists(self.qaqc_dir):
            os.makedirs(self.qaqc_dir)

        self.qaqc_gdb = data['qaqc_gdb']
        self.raster_dir = data['qaqc_gdb']
        self.tile_size = float(data['tile_size'])
        self.to_pyramid = data['to_pyramid']

        # checks "answer key"
        self.check_keys = data['check_keys']
        self.hdatum_key = data['check_keys']['hdatum']
        self.vdatum_key = data['check_keys']['vdatum']
        self.exp_cls_key = [int(n) for n in data['check_keys']['exp_cls'].split(',')]
        self.pdrf_key = int(data['check_keys']['pdrf'])
        self.gps_time_key = data['check_keys']['gps_time']
        self.version_key = data['check_keys']['version']
        self.pt_src_ids_key = data['check_keys']['pt_src_ids']

        self.dz_aprx = data['dz_aprx']
        self.dz_export_settings = data['dz_export_settings']
        self.dz_classes_template = data['dz_classes_template']
        self.lp360_ldexport_exe = data['lp360_ldexport_exe']

        self.contractor_shp = data['contractor_shp']
        self.checks_to_do = data['checks_to_do']
        self.surfaces_to_make = data['surfaces_to_make']
        self.mosaics_to_make = data['mosaics_to_make']

        self.qaqc_csv = r'{}\qaqc.csv'.format(self.qaqc_dir)
        self.qaqc_geojson_NAD83_UTM_CENTROIDS = r'{}\qaqc_NAD83_UTM_CENTROIDS.json'.format(self.qaqc_dir)
        self.qaqc_geojson_NAD83_UTM_POLYGONS = r'{}\qaqc_NAD83_UTM_POLYGONS.json'.format(self.qaqc_dir)
        self.qaqc_geojson_WebMercator_CENTROIDS = r'{}\qaqc_WebMercator_CENTROIDS.json'.format(self.qaqc_dir)
        self.qaqc_geojson_WebMercator_POLYGONS = r'{}\qaqc_WebMercator_POLYGONS.json'.format(self.qaqc_dir)
        self.qaqc_shp_NAD83_UTM_POLYGONS = r'{}\qaqc_NAD83_UTM.shp'.format(self.qaqc_dir)

        self.json_dir = r'{}\qaqc_check_results'.format(self.qaqc_dir)
        if not os.path.exists(self.json_dir):
            os.makedirs(self.json_dir)

        self.tile_geojson_WebMercator_POLYGONS = os.path.join(self.qaqc_dir, 'tiles_WebMercator_POLYGONS.json')
        self.tile_shp_NAD83_UTM_CENTROIDS = os.path.join(self.qaqc_dir, 'tiles_centroids_NAD83_UTM.shp')
        self.tile_csv = os.path.join(self.qaqc_dir, 'tiles.csv')

        self.epsg_json = data['epsg_json']

    def __str__(self):
        return json.dumps(self.data, indent=4, sort_keys=True)

    @staticmethod
    def run_console_cmd(cmd):
        process = subprocess.Popen(cmd.split(' '), shell=False, 
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        output, error = process.communicate()
        returncode = process.poll()
        return returncode, output

        
class LasTileCollection():

    def __init__(self, las_tile_dir):
        self.las_tile_dir = las_tile_dir
        self.num_las = len(self.get_las_names())

    def get_las_tile_paths(self):
        return [os.path.join(self.las_tile_dir, f) 
          for f in os.listdir(self.las_tile_dir) 
          if f.endswith('.las')]

    def get_las_names(self):
        return [f for f in os.listdir(self.las_tile_dir) if f.endswith('.las')]

    def get_las_base_names(self):
        return [os.path.splitext(tile)[0] for tile in self.get_las_names()]

    def get_classification_scheme(xml_fpath):
        root = ET.parse(xml_fpath).getroot()
        classes = {}
        for c in root.iter('Class'):
            label = c.find('Label').text
            value = c.find('Values')[0].text
            classes[label] = value
        classes_json_str = json.dumps(classes, indent=2)
        arcpy.AddMessage(classes_json_str)


class LasTile:

    def __init__(self, las_path, config):

        def get_useful_las_header_info():
            info_to_get = 'global_encoding,version_major,version_minor,' \
                          'created_day,created_year,' \
                          'data_format_id,x_min,x_max,y_min,y_max'
            header = {}
            for info in info_to_get.split(','):
                header[info] = self.inFile.header.reader.get_header_property(info)

            self.version = '{}.{}'.format(header['version_major'], header['version_minor'])
            return header

        def get_vlrs():
            vlrs = {}
            for i, vlr in enumerate(self.inFile.header.vlrs):
                vlrs.update({vlr.record_id: vlr.parsed_body})
            return vlrs

        def get_geotif_keys():
            geotiff_key_tag = 34735  # GeoKeyDirectoryTag
            key_entries = list(self.vlrs[geotiff_key_tag])  
            nth = 4
            keys = [key_entries[nth*i:nth*i+nth] for i in range(0, int(math.ceil(len(key_entries)/nth)))]
            # KeyEntry = {KeyID, TIFFTagLocation, Count, Value_Offset}
            geotiff_keys = {}
            for key in keys:
                geotiff_keys.update({
                    key[0]: {
                        'TIFFTagLocation': key[1],
                        'Count': key[2],
                        'Value_Offset': key[3],
                        }
                    })
            return geotiff_keys

        def get_hor_srs():
            hor_srs = None
            if self.version == '1.2':
                try:
                    with open(self.config.epsg_json) as f:  # TODO: doesn't have to happen for every tile
                        epsgs = json.load(f)
                    hor_key_id = 3072  # ProjectedCSTypeGeoKey
                    hor_srs_epsg = str(self.geotiff_keys[hor_key_id]['Value_Offset'])
                    hor_srs = epsgs[hor_srs_epsg]
                except Exception as e:
                    print(e)
                    hor_srs = 'no horizontal coordinate system specified in GeoTiff keys'
            elif self.version == '1.4':
                v14_hcs_key = 2112  # 2112 = Las 1.4 spec for hor. coord. sys. info
                hor_cs_wkt = self.vlrs[v14_hcs_key][0].decode('utf-8')

            return hor_srs

        def get_ver_srs():
            geo_ascii_params_tag = 34737  # GeoAsciiParamsTag (optional in v1.4)
            ver_srs = None
            if self.version == '1.2':  # ver srs specified in geotiff keys
                v12_vcs_keys = [4097, 4096]  # in prefered ordered
                # 4097 = VerticalCitationGeoKey
                # 4096 = VerticalCSTypeGeoKey
                if any(key in self.geotiff_keys.keys() for key in v12_vcs_keys):
                    for key in v12_vcs_keys:
                        start_i = self.geotiff_keys[key]['Value_Offset']
                        end_i = start_i + self.geotiff_keys[key]['Count']
                        ver_srs = self.vlrs[geo_ascii_params_tag][0].decode('utf-8')[start_i:end_i-1]
                        if ver_srs:
                            break
                else:
                    ver_srs = 'no vertical coordinate system specified in GeoTiff keys'
            elif self.version == '1.4':  # ver srs specified in ogc wkt
                if self.inFile.header.get_wkt():  # i.e., if wkt bit is set to 1
                    v14_wkt_key = 2112  # 2112 = Las 1.4 spec for hor. coord. sys. info
                    ver_srs = self.vlrs[v14_wkt_key][0].decode('utf-8')
                else:
                    ver_srs = 'WKT vertical coordinate '

            return ver_srs

        def calc_las_centroid():
            data_nw_x = self.las_extents['ExtentXMin']
            data_nw_y = self.las_extents['ExtentYMax']
            las_nw_x = data_nw_x - (data_nw_x % self.config.tile_size)
            las_nw_y = data_nw_y + self.config.tile_size - (data_nw_y % self.config.tile_size)
            las_centroid_x = las_nw_x + self.config.tile_size / 2
            las_centroid_y = las_nw_y - self.config.tile_size / 2
            return (las_centroid_x, las_centroid_y)
        
        self.path = las_path
        self.name = os.path.splitext(las_path.split(os.sep)[-1])[0]
        self.version = None
        self.inFile = File(self.path, mode="r")
        self.config = config
        self.is_pyramided = os.path.isfile(self.path.replace('.las', '.qvr'))
        self.to_pyramid = self.config.to_pyramid

        self.header = get_useful_las_header_info()
        self.las_extents = {
            'ExtentXMin': self.header['x_min'],
            'ExtentXMax': self.header['x_max'],
            'ExtentYMin': self.header['y_min'],
            'ExtentYMax': self.header['y_max'],
            }

        self.centroid_x, self.centroid_y = calc_las_centroid()

        self.tile_extents = {
            'tile_top': self.centroid_y + self.config.tile_size / 2,
            'tile_bottom': self.centroid_y - self.config.tile_size / 2,
            'tile_left': self.centroid_x - self.config.tile_size / 2,
            'tile_right': self.centroid_x + self.config.tile_size / 2,
            }

        self.tile_poly_wkt = GeoObject(Polygon([
            (self.tile_extents['tile_left'], self.tile_extents['tile_top']), 
            (self.tile_extents['tile_right'], self.tile_extents['tile_top']), 
            (self.tile_extents['tile_right'], self.tile_extents['tile_bottom']), 
            (self.tile_extents['tile_left'], self.tile_extents['tile_bottom']),
            (self.tile_extents['tile_left'], self.tile_extents['tile_top']), 
            ])).wkt()

        self.tile_centroid_wkt = GeoObject(Point(self.centroid_x, self.centroid_y)).wkt()
        self.classes_present, self.class_counts = self.get_class_counts()
        self.has_bathy = True if 'class26' in self.class_counts.keys() else False
        self.has_ground = True if 'class2' in self.class_counts.keys() else False

        self.checks_result = {
            'naming': None,
            'version': None,
            'pdrf': None,
            'gps_time': None,
            'hdatum': None,
            'vdatum': None,
            'pnt_src_ids': None,
            'exp_cls': None,
        }

        self.vlrs = get_vlrs()
        self.geotiff_keys = get_geotif_keys()
        self.hor_srs = get_hor_srs()
        self.ver_srs = get_ver_srs()

        if self.to_pyramid and not self.is_pyramided:
            self.create_las_pyramids()

    def __str__(self):
        info_to_output = {
            'tile_name': self.name,
            'header': self.header,
            'tile_extents': self.las_extents,
            'centroid_x': self.centroid_x,
            'centroid_y': self.centroid_y,
            'class_counts': self.class_counts,
            'check_results': self.checks_result,
            'tile_polygon': self.tile_poly_wkt,
            'tile_centroid': self.tile_centroid_wkt,
            }

        # del keys that are not needed because of repitition
        info_to_output['header'].pop('VLRs', None)
        info_to_output['header'].pop('version_major', None)
        info_to_output['header'].pop('version_minor', None)
        info_to_output['header'].pop('global_encoding', None)
        info_to_output['header'].pop('data_format_id', None)
        return json.dumps(info_to_output, indent=2)

    def output_las_qaqc_to_json(self):
        json_file_name = r'{}\{}.json'.format(self.config.json_dir, self.name)
        with open(json_file_name, 'w') as json_file:
            json_file.write(str(self))

    def get_class_counts(self):
        class_counts = np.unique(self.inFile.classification, return_counts=True)
        classes_present = [c for c in class_counts[0]]
        class_counts = dict(zip(['class{}'.format(str(c)) for c in class_counts[0]],
                                [int(c) for c in class_counts[1]]))
        arcpy.AddMessage(class_counts)
        return classes_present, class_counts

    def get_gps_time(self):
        gps_times = {0: 'GPS Week Time', 1: 'Satellite GPS Time'}
        bit_num_gps_time_type = 0
        gps_time_type_bit = int(bin(self.header['global_encoding'])[2:].zfill(16)[::-1][bit_num_gps_time_type])
        return gps_times[gps_time_type_bit]

    def get_las_version(self):
        return '{}.{}'.format(self.header['version_major'], self.header['version_minor'])

    def get_las_pdrf(self):
        return self.header['data_format_id']

    def get_pt_src_ids(self):
        return np.unique(self.inFile.pt_src_id)

    def create_las_pyramids(self):
        exe = r'C:\Program Files\Common Files\LP360\LDPyramid.exe'
        thin_factor = 12
        cmd_str = '{} -f {} {}'.format(exe, thin_factor, self.path)
        arcpy.AddMessage('generating pyramids for {}...'.format(self.path))
        arcpy.AddMessage(cmd_str)
        try:
            returncode, output = self.config.run_console_cmd(cmd_str)
        except Exception as e:
            arcpy.AddMessage(e)

        pass


class Mosaic:

    def __init__(self, mtype, config):
        self.mtype = mtype
        self.config = config
        self.mosaic_dataset_base_name = r'{}_{}_mosaic'.format(self.config.project_name, self.mtype)
        self.mosaic_dataset_path = os.path.join(self.config.mosaics_to_make[self.mtype][1], 
                                                self.mosaic_dataset_base_name)

    def create_mosaic_dataset(self):
        arcpy.AddMessage('creating mosaic dataset {}...'.format(self.mosaic_dataset_base_name))
        sr = arcpy.SpatialReference(6348)
        try:
            arcpy.CreateMosaicDataset_management(self.config.qaqc_gdb, 
                                                 self.mosaic_dataset_base_name, 
                                                 coordinate_system=sr)
        except Exception as e:
            arcpy.AddMessage(e)

    def add_rasters_to_mosaic_dataset(self):
        arcpy.AddMessage('adding {}_rasters to {}...'.format(self.mtype, self.mosaic_dataset_path))
        arcpy.AddRastersToMosaicDataset_management(self.mosaic_dataset_path, 'Raster Dataset',
                                                   self.config.surfaces_to_make[self.mtype][1],
                                                   build_pyramids='BUILD_PYRAMIDS',
                                                   calculate_statistics='CALCULATE_STATISTICS',
                                                   duplicate_items_action='OVERWRITE_DUPLICATES')

    def export_mosaic_dataset(self):
        try:
            self.config.exported_mosaic_dataset = os.path.join(self.config.qaqc_dir, 
                                                               self.mosaic_dataset_base_name + '.tif')

            arcpy.AddMessage('exporting {} to tif...'.format(self.mosaic_dataset_base_name))
            arcpy.env.overwriteOutput = True
            arcpy.CopyRaster_management(self.mosaic_dataset_path, self.config.exported_mosaic_dataset)
            arcpy.env.overwriteOutput = False
        except Exception as e:
            arcpy.AddMessage(e)

    def add_mosaic_dataset_tif_to_aprx(self):
        try:
            arcpy.AddMessage('adding {} to aprx...'.format(self.mosaic_dataset_base_name + '.tif'))
            #aprx = arcpy.mp.ArcGISProject(self.config.dz_aprx)
            aprx = arcpy.mp.ArcGISProject('CURRENT')
            m = aprx.listMaps('dz_surface')[0]
            arcpy.MakeRasterLayer_management(self.config.exported_mosaic_dataset, 'temp_mosaic_dataset')

            dz_lyr = r'C:\QAQC_contract\FL1608_TB_N_DogIsland_p\{}.lyrx'.format(self.mosaic_dataset_base_name)

            if not os.path.exists(dz_lyr):
                arcpy.SaveToLayerFile_management('temp_mosaic_dataset', dz_lyr)
            
            arcpy.ApplySymbologyFromLayer_management(dz_lyr, self.config.dz_classes_template)
            m.addDataFromPath(dz_lyr)

            aprx.save()
        except Exception as e:
            arcpy.AddMessage(e)

        pass


class Surface:

    def __init__(self, tile, stype, config):
        self.stype = stype
        self.las_path = tile.path
        self.las_name = tile.name
        self.las_extents = tile.las_extents
        self.config = config

        self.binary_path = {'Dz': r'{}\{}_dz_dzValue.flt'.format(self.config.surfaces_to_make[self.stype][1], 
                                                                 self.las_name),
                            'Hillshade': ''}

        self.raster_path = {'Dz': r'{}\dz_{}'.format(self.config.raster_dir, self.las_name),
                            'Hillshade': ''}

    def __str__(self):
        return self.raster_path[self.stype]

    def binary_to_raster(self):
        try:
            arcpy.AddMessage('converting {} to {}...'.format(self.binary_path[self.stype], 
                                                         self.raster_path[self.stype]))
            arcpy.FloatToRaster_conversion(self.binary_path[self.stype], 
                                           self.raster_path[self.stype])
        except Exception as e:
            arcpy.AddMessage(e)

    def update_dz_export_settings_extents(self):
        arcpy.AddMessage('updating dz export settings xml with las extents...')
        tree = ET.parse(self.config.dz_export_settings)
        root = tree.getroot()
        for extent, val in self.las_extents.items():
            for e in root.findall(extent):
                e.text = str(val)
        new_dz_settings = ET.tostring(root).decode('utf-8')  # is byte string
        myfile = open(self.config.dz_export_settings, "w")
        myfile.write(new_dz_settings)

    def gen_dz_surface(self):
        exe = self.config.lp360_ldexport_exe
        las = self.las_path.replace('CLASSIFIED_LAS\\', 'CLASSIFIED_LAS\\\\')
        dz = r'{}\{}'.format(self.config.surfaces_to_make[self.stype][1], self.las_name)
        cmd_str = '{} -s {} -f {} -o {}'.format(exe, self.config.dz_export_settings, las, dz)
        arcpy.AddMessage('generating dz ortho for {}...'.format(las))
        arcpy.AddMessage(cmd_str)
        try:
            returncode, output = self.config.run_console_cmd(cmd_str)
        except Exception as e:
            arcpy.AddMessage(e)

    def gen_hillshade_surface():
        pass

    pass


class QaqcTile:

    passed_text = 'PASSED'
    failed_text = 'FAILED'

    def __init__(self, config):
        self.config = config
        self.checks = {
            'naming': self.check_las_naming,
            'version': self.check_las_version,
            'pdrf': self.check_las_pdrf,
            'gps_time': self.check_las_gps_time,
            'hdatum': self.check_hdatum,
            'vdatum': self.check_vdatum,
            'pt_src_ids': self.check_pt_src_ids,
            'exp_cls': self.check_unexp_cls,
            }

        self.surfaces = {
            'Dz': self.create_dz,
            'Dz_mosaic': None,
            'Hillshade': self.create_hillshade,
            'Hillshade_mosaic': None,
            }

    def check_las_naming(self, tile):
        # for now, the checks assume Northern Hemisphere
        # https://www.e-education.psu.edu/natureofgeoinfo/c2_p23.html
        min_easting = 167000
        max_easting = 833000
        min_northing = 0
        max_northing = 9400000
        #min_northing_sh = 1000000 # sh = southern hemisphere
        #max_northing_sh = 10000000

        # first check general format with regex (e.g., # ####_######e_#[#######]n_las)
        pattern = re.compile(r'[0-9]{4}_[0-9]{6}e_[0-9]{1,8}(n_las)')
        if pattern.match(tile.name):
            # then check name components
            tile_name_parts = tile.name.split('_')
            easting = int(tile_name_parts[1].replace('e', ''))
            northing = int(tile_name_parts[2].replace('n', ''))
            easting_good = self.passed_text if easting >= min_easting and easting <= max_easting else self.failed_text
            northing_good = self.passed_text if northing >= min_northing and northing <= max_northing else self.failed_text
            if easting_good and northing_good:
                passed = self.passed_text
            else:
                passed = self.failed_text
        else:
            passed = self.failed_text
        tile.checks_result['naming'] = tile.name
        tile.checks_result['naming_passed'] = passed
        arcpy.AddMessage(tile.checks_result['naming'])
        return passed

    def check_las_version(self, tile):
        version = tile.get_las_version()
        if version == self.config.version_key:
            passed = self.passed_text
        else:
            passed = self.failed_text
        tile.checks_result['version'] = version
        tile.checks_result['version_passed'] = passed
        arcpy.AddMessage(tile.checks_result['version'])
        return passed

    def check_las_pdrf(self, tile):
        pdrf = tile.get_las_pdrf()
        if pdrf == self.config.pdrf_key:
            passed = self.passed_text
        else:
            passed = self.failed_text
        tile.checks_result['pdrf'] = pdrf
        tile.checks_result['pdrf_passed'] = passed
        arcpy.AddMessage(tile.checks_result['pdrf'])
        return passed

    def check_las_gps_time(self, tile):
        gps_time = tile.get_gps_time()
        if gps_time == self.config.gps_time_key:
            passed = self.passed_text
        else:
            passed = self.failed_text
        tile.checks_result['gps_time'] = gps_time
        tile.checks_result['gps_time_passed'] = passed
        arcpy.AddMessage(tile.checks_result['gps_time'])
        return passed

    def check_hdatum(self, tile):  # TODO
        hdatum = tile.hor_srs
        if hdatum == self.config.hdatum_key:
            passed = self.passed_text
        else:
            passed = self.failed_text
        tile.checks_result['hdatum'] = hdatum
        tile.checks_result['hdatum_passed'] = passed
        arcpy.AddMessage(tile.checks_result['hdatum'])
        return passed

    def check_unexp_cls(self, tile):
        unexp_cls = list(set(tile.classes_present).difference(self.config.exp_cls_key))
        if not unexp_cls:
            passed = self.passed_text
        else:
            passed = self.failed_text
        tile.checks_result['exp_cls'] = str(list(unexp_cls))
        tile.checks_result['exp_cls_passed'] = passed
        arcpy.AddMessage(tile.checks_result['exp_cls'])
        return passed

    def check_vdatum(self, tile):
        vdatum = tile.ver_srs
        if vdatum == self.config.vdatum_key:
            passed = self.passed_text
        else:
            passed = self.failed_text
        tile.checks_result['vdatum'] = vdatum
        tile.checks_result['vdatum_passed'] = passed
        arcpy.AddMessage(tile.checks_result['vdatum'])
        return passed

    def check_pt_src_ids(self, tile):
        unq_pt_src_ids = tile.get_pt_src_ids()
        if len(unq_pt_src_ids) > 1:
            passed = self.passed_text
        else:
            passed = self.failed_text
        tile.checks_result['pt_src_ids'] = str(list(unq_pt_src_ids))
        tile.checks_result['pt_src_ids_passed'] = passed
        arcpy.AddMessage(tile.checks_result['pt_src_ids'])
        return passed

    def calc_pt_cloud_stats(self):
        pass

    def create_dz(self, tile):
        from qaqc import Surface
        if tile.has_bathy or tile.has_ground:
            tile_dz = Surface(tile, 'Dz', self.config)
            tile_dz.update_dz_export_settings_extents()
            tile_dz.gen_dz_surface()
            #tile_dz.binary_to_raster()
        else:
            arcpy.AddMessage('{} has no bathy or ground points; no dz ortho generated'.format(tile.name))

    def create_hillshade(self):
        pass

    def add_tile_check_results(self, tile_check_results):
        arcpy.AddMessage(tile_check_results)

    def update_qaqc_results_table(self):
        pass

    def run_qaqc_checks_multiprocess(self, las_path):
        from qaqc import LasTile, LasTileCollection
        import logging
        import xml.etree.ElementTree as ET
        logging.basicConfig(format='%(asctime)s:%(message)s', level=logging.DEBUG)
        tile = LasTile(las_path, self.config)
        for c in [k for k, v in self.config.checks_to_do.items() if v]:
            logging.debug('running {}...'.format(c))
            result = self.checks[c](tile)
            logging.debug(result)
        tile.output_las_qaqc_to_json()

    def run_qaqc_checks(self, las_paths):       
        num_las = len(las_paths)
        #self.progress[1]['maximum'] = num_las
        tic = time.time()

        print('performing tile qaqc processes (details logged in log file)...')
        for las_path in progressbar.progressbar(las_paths, redirect_stdout=True):
            arcpy.AddMessage('starting {}...'.format(las_path))
            tile = LasTile(las_path, self.config)

            for c in [k for k, v in self.config.checks_to_do.items() if v]:
                logging.debug('running {}...'.format(c))
                result = self.checks[c](tile)
                logging.debug(result)

            for c in [k for k, v in self.config.surfaces_to_make.items() if v[0]]:
                logging.debug('running {}...'.format(c))
                result = self.surfaces[c](tile)
                logging.debug(result)

            tile.output_las_qaqc_to_json()

    def run_qaqc(self, las_paths, multiprocess):
        if multiprocess:
            p = pp.ProcessPool(2)
            arcpy.AddMessage(p)
            p.imap(self.run_qaqc_checks_multiprocess, las_paths)
            p.close()
            p.join()
        else:
            self.run_qaqc_checks(las_paths)


class QaqcTileCollection:

    def __init__(self, las_paths, config,):
        self.las_paths = las_paths
        self.config = config
        self.qaqc_results_df = None

    def run_qaqc_tile_collection_checks(self, multiprocess):
        tiles_qaqc = QaqcTile(self.config)
        tiles_qaqc.run_qaqc(self.las_paths, multiprocess)

    def gen_qaqc_results_dict(self):
        def flatten_dict(d_obj):
            for k, v in d_obj.items():
                if isinstance(v, dict):
                    new_dict = {k2:v2 for k2, v2 in v.items()}
                    for d in flatten_dict(new_dict):
                        yield d
                else:
                    yield k, v

        flattened_dicts = []
        for las_json in os.listdir(self.config.json_dir):
            try:
                las_json = os.path.join(self.config.json_dir, las_json)
                with open(las_json, 'r') as json_file:
                    json_data = json.load(json_file)
                    flattened_json_data = {k:v for k,v in flatten_dict(json_data)}
                    flattened_dicts.append(flattened_json_data)
            except Exception as e:
                arcpy.AddMessage(e)
        return flattened_dicts

    def get_unq_pt_src_ids(self):
        unq_pt_src_ids = set([])
        pnt_src_ids = self.qaqc_results_df['pnt_src_ids'].tolist()
        for i, pnt_src_id_str in enumerate(pnt_src_ids):
            pnt_src_ids_set = set(ast.literal_eval(pnt_src_id_str))
            unq_pt_src_ids = unq_pt_src_ids.union(pnt_src_ids_set)
        return unq_pt_src_ids

    def set_qaqc_results_df(self):
        self.qaqc_results_df = pd.DataFrame(self.gen_qaqc_results_dict())

    def gen_qaqc_results_gdf_NAD83_UTM_CENTROIDS(self):
        df = self.qaqc_results_df
        df['Coordinates'] = df.tile_centroid
        df['Coordinates'] = df['Coordinates'].apply(wkt.loads)
        nad83_utm_z19 = {'init': 'epsg:26919'}
        gdf = gpd.GeoDataFrame(df, crs=nad83_utm_z19, geometry='Coordinates')
        return gdf

    def gen_qaqc_results_gdf_WebMercator_CENTROIDS(self):
        df = self.qaqc_results_df
        df['Coordinates'] = df.tile_centroid
        df['Coordinates'] = df['Coordinates'].apply(wkt.loads)
        nad83_utm_z19 = {'init': 'epsg:26919'}
        gdf = gpd.GeoDataFrame(df, crs=nad83_utm_z19, geometry='Coordinates')
        web_mercator = {'init': 'epsg:3857'}
        gdf = gdf.to_crs(web_mercator)
        return gdf

    def gen_qaqc_results_gdf_WebMercator_POLYGONS(self):
        df = self.qaqc_results_df
        df['Coordinates'] = df.tile_polygon
        df['Coordinates'] = df['Coordinates'].apply(wkt.loads)
        nad83_utm_z19 = {'init': 'epsg:26919'}
        gdf = gpd.GeoDataFrame(df, crs=nad83_utm_z19, geometry='Coordinates')
        web_mercator = {'init': 'epsg:3857'}
        gdf = gdf.to_crs(web_mercator)
        return gdf

    def gen_qaqc_json_NAD83_UTM_CENTROIDS(self, output):
        gdf = self.gen_qaqc_results_gdf_NAD83_UTM_CENTROIDS()
        try:
            os.remove(output)
        except Exception as e:
            arcpy.AddMessage(e)
        gdf.to_file(output, driver="GeoJSON")

    def gen_qaqc_json_WebMercator_CENTROIDS(self):
        output = self.config.qaqc_geojson_WebMercator_CENTROIDS
        gdf = self.gen_qaqc_results_gdf_WebMercator_CENTROIDS()
        try:
            os.remove(output)
        except Exception as e:
            arcpy.AddMessage(e)
        gdf.to_file(output, driver="GeoJSON")
        return output

    def gen_qaqc_json_WebMercator_POLYGONS(self, output):
        gdf = self.gen_qaqc_results_gdf_WebMercator_POLYGONS()
        try:
            os.remove(output)
        except Exception as e:
            arcpy.AddMessage(e)
        gdf.to_file(output, driver="GeoJSON")

    def gen_qaqc_results_gdf_NAD83_UTM_POLYGONS(self):
        df = self.qaqc_results_df
        df['Coordinates'] = df.tile_polygon
        df['Coordinates'] = df['Coordinates'].apply(wkt.loads)
        nad83_utm_z19 = {'init': 'epsg:26919'}
        gdf = gpd.GeoDataFrame(df, crs=nad83_utm_z19, geometry='Coordinates')		
        return gdf

    def gen_qaqc_json_NAD83_UTM_POLYGONS(self, output):
        gdf = self.gen_qaqc_results_gdf_NAD83_UTM_POLYGONS()
        try:
            os.remove(output)
        except Exception as e:
            arcpy.AddMessage(e)
        gdf.to_file(output, driver="GeoJSON")

    def gen_qaqc_csv(self, output):
        gdf = self.gen_qaqc_results_gdf_NAD83_UTM_CENTROIDS()
        def get_x(pt): return (pt.x)
        def get_y(pt): return (pt.y)
        gdf['centroid_x'] = map(get_x, gdf['Coordinates'])
        gdf['centroid_y'] = map(get_y, gdf['Coordinates'])
        wgs84 = {'init': 'epsg:4326'}
        gdf = gdf.to_crs(wgs84)
        gdf['centroid_lon'] = map(get_x, gdf['Coordinates'])
        gdf['centroid_lat'] = map(get_y, gdf['Coordinates'])
        gdf.to_csv(output, index=False)

    def gen_qaqc_shp_NAD83_UTM(self, output):
        print('outputing tile qaqc results to {}...'.format(self.config.qaqc_shp_NAD83_UTM_POLYGONS))
        gdf = self.gen_qaqc_results_gdf_NAD83_UTM_POLYGONS()
        gdf = gdf.drop(columns=['ExtentXMax','ExtentXMin', 'ExtentYMax', 
                                'ExtentYMin', 'centroid_x', 'centroid_y', 
                                'created_day', 'created_year', 'tile_polygon', 
                                'x_max', 'x_min', 'y_max', 'y_min'])
        arcpy.AddMessage(gdf)
        gdf.to_file(output, driver='ESRI Shapefile')
        sr = arcpy.SpatialReference('NAD 1983 UTM Zone 19N')  # 2011?

        try:
            arcpy.AddMessage('defining {} as {}...'.format(output, sr.name))
            arcpy.DefineProjection_management(output, sr)
        except Exception as e:
            arcpy.AddMessage(e)

        arcpy.AddMessage(self.config.dz_aprx)

        try:
            arcpy.AddMessage('adding {} to {}...'.format(output, self.config.dz_aprx))
            aprx = arcpy.mp.ArcGISProject('CURRENT')
            aprx.save()
        except Exception as e:
            arcpy.AddMessage(e)

    def gen_mosaic(self, mtype):
        mosaic = Mosaic(mtype, self.config)
        mosaic.create_mosaic_dataset()
        mosaic.add_rasters_to_mosaic_dataset()
        mosaic.export_mosaic_dataset()
        mosaic.add_mosaic_dataset_tif_to_aprx()

    def gen_tile_geojson_WGS84(shp, geojson):
        wgs84 = {'init': 'epsg:4326'}
        gdf = gpd.read_file(shp).to_crs(wgs84)
        try:
            os.remove(geojson)
        except Exception as e:
            arcpy.AddMessage(e)
        gdf.to_file(geojson, driver="GeoJSON")

    @staticmethod
    def gen_tile_centroids_csv(shp, out_csv):
        gdf = gpd.read_file(shp)
        gdf['geometry'] = gdf['geometry'].centroid
        def get_x(pt): return (pt.x)
        def get_y(pt): return (pt.y)
        gdf['centroid_x'] = map(get_x, gdf['geometry'])
        gdf['centroid_y'] = map(get_y, gdf['geometry'])
        wgs84 = {'init': 'epsg:4326'}
        gdf = gdf.to_crs(wgs84)
        gdf['geometry'] = gdf['geometry'].centroid
        gdf['centroid_lon'] = map(get_x, gdf['geometry'])
        gdf['centroid_lat'] = map(get_y, gdf['geometry'])
        gdf.to_csv(out_csv)

    def gen_tile_centroids_shp_NAD83_UTM(self):
        arcpy.AddMessage('generating shapefile containing centroids of contractor tile polygons...')
        gdf = gpd.read_file(self.config.contractor_shp)
        gdf['geometry'] = gdf['geometry'].centroid
        gdf.to_file(self.config.tile_shp_NAD83_UTM_CENTROIDS, driver='ESRI Shapefile')
        return self.config.tile_shp_NAD83_UTM_CENTROIDS

    def gen_tile_geojson_WebMercator_POLYGONS(self, geojson):
        gdf = gpd.read_file(self.config.contractor_shp)
        try:
            os.remove(geojson)
        except Exception as e:
            arcpy.AddMessage(e)
        WebMercator = {'init': 'epsg:3857'}
        gdf = gdf.to_crs(WebMercator)
        gdf.to_file(geojson, driver="GeoJSON")

    def add_layer_to_aprx(self, layer):
        try:
            aprx = arcpy.mp.ArcGISProject(self.config.dz_aprx)
            m = aprx.listMaps()[0]
            lyr = arcpy.mp.LayerFile(layer)
            m.addLayer(lyr, 'TOP')
            aprx.save()
        except Exception as e:
            arcpy.AddMessage(e)

    pass


def run_qaqc(config_json):
    config = Configuration(config_json)
    arcpy.AddMessage(config)
    
    qaqc_tile_collection = LasTileCollection(config.las_tile_dir)
    qaqc = QaqcTileCollection(qaqc_tile_collection.get_las_tile_paths()[0:10], config)
    
    qaqc.run_qaqc_tile_collection_checks(multiprocess=False)
    qaqc.set_qaqc_results_df()
    qaqc.gen_qaqc_shp_NAD83_UTM(config.qaqc_shp_NAD83_UTM_POLYGONS)
    qaqc.gen_qaqc_json_WebMercator_CENTROIDS()

    dashboard = SummaryPlots(config, qaqc.qaqc_results_df)
    dashboard.gen_dashboard()
    
    if not os.path.isfile(config.tile_shp_NAD83_UTM_CENTROIDS):
        print('creating shapefile containing centroids of contractor tile polygons...')
        tile_centroids = qaqc.gen_tile_centroids_shp_NAD83_UTM()
        qaqc.add_layer_to_aprx(tile_centroids)
    else:
        arcpy.AddMessage('{} already exists'.format(config.tile_shp_NAD83_UTM_CENTROIDS))
    
    # build the mosaics the user checked
    mosaic_types = [k for k, v in config.mosaics_to_make.items() if v[0]]
    if mosaic_types:
        print('building mosaics {}...'.format(tuple([m.encode("utf-8") for m in mosaic_types])))
        for m in progressbar.progressbar(mosaic_types, redirect_stdout=True):
            qaqc.gen_mosaic(m)
    else:
        print('\nno mosaics to build...')

    arcpy.AddMessage('\nYAY, you just QAQC\'d project {}!!!\n'.format(config.project_name))

    pass

    
if __name__ == '__main__':
    arcpy.env.overwriteOutput = True
    
    try:
        run_qaqc(config)
        sys.exit(0)
    except SystemExit:
        pass