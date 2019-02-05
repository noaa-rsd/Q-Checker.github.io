import json


config_data = {
    'project_name': 'FL1608-TB-N_DogIsland_p',
    'tile_size': 500,
    'contractor_shp': r'C:\QAQC_contract\nantucket\EXTENTS\final\Nantucket_TileGrid.shp',
    'dz_classes_template': r'C:\QAQC_contract\dz_classes.lyr',
    'dz_export_settings': r'C:\QAQC_contract\dz_export_settings.xml',
    'dz_mxd': r'C:\QAQC_contract\nantucket\QAQC_nantucket.mxd',
    'qaqc_gdb': r'C:\QAQC_contract\nantucket\qaqc_nantucket.gdb',
    'qaqc_dir': r'C:\QAQC_contract\nantucket',
    'las_tile_dir': r'C:\QAQC_contract\nantucket\CLASSIFIED_LAS',
    'checks_to_do': {
        'naming_convention': True,
        'version': True,
        'pdrf': True,
        'gps_time_type': True,
        'hor_datum': True,
        'ver_datum': False,
        'point_source_ids': False,
        'expected_classes': True,
    },
    'checks_keys': {
        'expected_classes': '2,26',
        'pdrf': '6',
        'naming_convention': 'yyyy_[easting]e_[northing]n_las',
        'hor_datum': 'NAD_1983_2011_UTM_Zone_4N',
        'gps_time_type': 'Satellite GPS Time',
        'version': '1.4',
        'point_source_ids': '?',
        'ver_datum': 'MHW',
    },
    'surfaces_to_make': {
        'Dz': True,
        'Hillshade': False,
        'Dz_dir': '"C:/QAQC_contract/nantucket/dz',
        'Hillshade_dir': '"C:/QAQC_contract/nantucket/hillshade',
    },  
    'mosaics_to_make': {
        'Dz': False,
        'Hillshade': False,
    },
}

with open('Z:\qaqc\qaqc_config.json', 'w') as f:
    json.dump(config_data, f)
