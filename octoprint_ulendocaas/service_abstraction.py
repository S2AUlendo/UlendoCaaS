from .cfg import *
from .service_exceptions import *

import requests
import base64
import socket
import struct
import json
from PIL import Image
from io import BytesIO

import numpy as np

from datetime import datetime


def verify_credentials(org_id, access_id, machine_id, plugin_logger):
    now = datetime.now()
    postdata =  {   'ACTION': 'VERIFY',
                    'ACCESS':{
                        'CLIENT_ID': org_id,
                        'ACCESS_ID': access_id,
                        'MACHINE_ID': machine_id,
                    },
                    'REQUEST': {
                        'REQUEST_TIME': now.strftime("%d/%m/%Y_%H:%M:%S"),        # Get the client time, even if its errorneous
                        'CLIENT_VERSION':'V0.3',               # TODO: Get the plugin version number from octoprint
                        'RequestSource': get_source_ip()
                    }
                }
       
    try: 
        postreq = requests.post(SERVICE_URL, json=json.dumps(postdata))
        response_body = postreq.json()
        plugin_logger.info(f'Output from verify creds: {response_body}')

        if 'exception' in response_body: raise_exception_from_response(response_body['exception'])
        else: return True
    except requests.RequestException as e:
        plugin_logger.error(f'Network error in verify_credentials: {str(e)}')
        raise
    except Exception as e:
        plugin_logger.error(f'Unexpected error in verify_credentials: {str(e)}')
        raise


def upload_image_rating(image_bytes, rating, org_id, access_id, machine_id, machine_name, logger):
    now = datetime.now()
    
    postdata =  {   
                    'ACTION': 'UPDATE',
                    'TASK': 'UPLOAD_IMAGE', 
                    'RATING': rating,     
                    'IMAGE_B64': image_bytes,        
                    'ACCESS':{
                        'CLIENT_ID': org_id,
                        'ACCESS_ID': access_id,
                        'MACHINE_ID': machine_id,
                        'MACHINE_NAME': machine_name
                    },
                    'REQUEST': {
                        'REQUEST_TIME': now.strftime("%d/%m/%Y_%H:%M:%S"),        # Get the client time, even if its errorneous
                        'CLIENT_VERSION':'V0.3',               # TODO: Get the plugin version number from octoprint
                        'RequestSource': get_source_ip()
                    }
                }
    
    try: 
        postreq = requests.post(SERVICE_URL, json=postdata)
        response_body = postreq.json()
        logger.info(f'Output from upload image: {response_body}')

        if 'exception' in response_body: 
            raise_exception_from_response(response_body['message'])
        else: return True
    except requests.RequestException as e:
        logger.error(f'Network error in upload image: {str(e)}')
        raise
    except Exception as e:
        logger.error(f'Unexpected error in upload image: {str(e)}')
        raise
    

def get_source_ip():

    try:
        hostname = socket.gethostname()
        ip_address = str(socket.gethostbyname(hostname))
    except:
        ip_address = "0.0.0.0"
        
    
    return ip_address
    

def encode_float_list_to_base64(list):
    bin_data = struct.pack(f'{len(list)}f', *list)
    return base64.b64encode(bin_data).decode('utf-8')


def get_run_post_data(version, axis, accelerometer, sweep_cfg, metadata, plugin_settings):

    now = datetime.now()

    postdata =  {   'ACTION': 'CALIBRATE',
                    'ACCELEROMETER_CFG': {
                        'DEVICE': plugin_settings.get(["accelerometer_device"]),
                        'RANGE': plugin_settings.get(["accelerometer_range"]),
                        'RATE': plugin_settings.get(["accelerometer_rate"])
                    },
                    'XAXISRESPONSE': encode_float_list_to_base64(accelerometer.x_buff),
                    'YAXISRESPONSE': encode_float_list_to_base64(accelerometer.y_buff),
                    'ZAXISRESPONSE': encode_float_list_to_base64(accelerometer.z_buff),
                    'AXIS': axis,
                    'OPERATION': '',
                    'METADATA': metadata if metadata is not {} else 'N/A',
                    'ACCESS':{
                        'CLIENT_ID': plugin_settings.get(["ORG"]), # TODO
                        'ORG_ID': plugin_settings.get(["ORG"]),
                        'ACCESS_ID': plugin_settings.get(["ACCESSID"]),
                        'MACHINE_ID': plugin_settings.get(["MACHINEID"]),
                        'MACHINE_NAME': plugin_settings.get(["MACHINENAME"])
                    },
                    'REQUEST': {
                        'REQUEST_TIME': now.strftime("%d/%m/%Y_%H:%M:%S"), # Get the client time, even if its errorneous
                        'POST_VERSION': version,
                        'RequestSource': get_source_ip()
                    },
                    "SWEEP_CFG": sweep_cfg.as_dict(),
                    "CONDITIONS":str(plugin_settings.get(["CONDITIONS"])),
                    "PRINTER": {
                        "PRINTER_MAKE":plugin_settings.get(["MANUFACTURER_NAME"]), 
                        "PRINTER_MODEL":plugin_settings.get(["MODELID"]),
                        'VERSION': "V0.01",
                        'MANUFACTURER_NAME': ""
                    },                    
                }
    
    return postdata


def save_post_as_file(postdata):

    now = datetime.now()

    try:
        with open(now.strftime('%Y%m%d_%H%M%S_') + postdata['OPERATION'] + '_post.json', 'w', encoding='utf-8') as f:
            json.dump(postdata, f, ensure_ascii=False, indent=4)
    except: pass


def autocal_service_solve(version, axis, accelerometer, sweep_cfg, metadata, plugin_settings):
    
    postdata = get_run_post_data(version, axis, accelerometer, sweep_cfg, metadata, plugin_settings)
    
    postdata['OPERATION'] = 'SOLVE'

    if plugin_settings.get(["save_post_data_locally"]): save_post_as_file(postdata)
         
    postreq = requests.post(SERVICE_URL, json=json.dumps(postdata), timeout=SERVICE_TIMEOUT_THD)
    response_body = json.loads(postreq.text)
        
    if 'exception' in response_body: raise_exception_from_response(response_body['exception'])
    elif 'solution' in response_body:
        solution = json.loads(response_body['solution'])
        gui_data = json.loads(response_body['gui_data'])
        return solution[0], solution[1], np.array(gui_data['bp']), np.array(gui_data['g'])
    elif 'message' in response_body:
        if response_body['message'] == 'Internal server error': raise AutocalInternalServerError
    else: raise UnknownResponse


def autocal_service_guidata(version, axis, accelerometer, sweep_cfg, metadata, plugin_settings):
    
    postdata = get_run_post_data(version, axis, accelerometer, sweep_cfg, metadata, plugin_settings)
    
    postdata['OPERATION'] = 'VERIFY'
    
    if plugin_settings.get(["save_post_data_locally"]): save_post_as_file(postdata)

    postreq = requests.post(SERVICE_URL, json=json.dumps(postdata), timeout=SERVICE_TIMEOUT_THD)
    response_body = json.loads(postreq.text)

    if 'exception' in response_body: raise_exception_from_response(response_body['exception'])
    elif 'verification' in response_body:
        gui_data = json.loads(response_body['gui_data'])
        return np.array(gui_data['bp']), np.array(gui_data['g'])
    elif 'message' in response_body:
        if response_body['message'] == 'Internal server error': raise AutocalInternalServerError
    else: raise UnknownResponse


def autocal_service_share(version, axis, is_verification, accelerometer, sweep_cfg, metadata, plugin_settings, plugin_logger, calibration_type=None, wc=None, zt=None, vtol=None):

    postdata = get_run_post_data(version, axis, accelerometer, sweep_cfg, metadata, plugin_settings)
    
    postdata['OPERATION'] = 'SHARE-MANUAL-ANALYZE' if not is_verification else 'SHARE-MANUAL-VERIFY'

    if is_verification:
        postdata['CALIBRATION_SELECTION'] = {}
        postdata['CALIBRATION_SELECTION']['TYPE'] = calibration_type
        postdata['CALIBRATION_SELECTION']['WC'] = wc
        postdata['CALIBRATION_SELECTION']['ZT'] = zt
        postdata['CALIBRATION_SELECTION']['VTOL'] = vtol

    if plugin_settings.get(["save_post_data_locally"]): save_post_as_file(postdata)

    postreq = requests.post(SERVICE_URL, json=json.dumps(postdata), timeout=SERVICE_TIMEOUT_THD)
    response_body = json.loads(postreq.text)

    if response_body['message'] == 'Data share success.':
        plugin_logger.info(f'The server reported the data was shared successfully.')
    else: raise Exception


def raise_exception_from_response(exception_str):
    if exception_str == "NoSignalError": raise NoSignalError
    elif exception_str == "SignalSyncError": raise SignalSyncError
    elif exception_str == "NoQualifiedSolution": raise NoQualifiedSolution
    elif exception_str == "NoVibrationDetected": raise NoVibrationDetected
    elif exception_str == "NotAuthenticated": raise NotAuthenticated
    elif exception_str == "MachineIDNotFound": raise MachineIDNotFound
    elif exception_str == "PictureUploadError": raise PictureUploadError
    else: raise Exception('Unknown exception returned from service.')

