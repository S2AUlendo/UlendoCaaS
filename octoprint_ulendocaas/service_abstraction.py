from .cfg import *
from .service_exceptions import *

import requests
import base64
import socket
import struct
import json

import numpy as np

from datetime import datetime


def verify_credentials(org_id, access_id, machine_id, self):
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
    
    postreq = requests.post(SERVICE_URL, json=json.dumps(postdata))
    response_body = postreq.json()
    self._logger.info(f'Output from verify creds: {response_body}')

    if 'exception' in response_body: 
        raise_exception_from_response(response_body['message'])
        return False
    else: return True


def get_source_ip():

    hostname = socket.gethostname()
    try:
        ip_address = str(socket.gethostbyname(hostname))
    except:
        ip_address = "0.0.0.0"
        
    
    return ip_address
    

def encode_float_list_to_base64(list):
    bin_data = struct.pack(f'{len(list)}f', *list)
    return base64.b64encode(bin_data).decode('utf-8')


def autocal_service_solve(axis, sweep_cfg, metadata, accelerometer, client_ID, access_ID, org_ID, machine_ID, machine_name, model_ID, manufacturer_name, self):

    now = datetime.now()

    postdata =  {   'ACTION': 'CALIBRATE',
                    'XAXISRESPONSE': encode_float_list_to_base64(accelerometer.x_buff),
                    'YAXISRESPONSE': encode_float_list_to_base64(accelerometer.y_buff),
                    'ZAXISRESPONSE': encode_float_list_to_base64(accelerometer.z_buff),
                    'AXIS': axis,
                    'OPERATION': 'SOLVE',
                    'METADATA': metadata if metadata is not {} else 'N/A',
                    'ACCESS':{
                        'CLIENT_ID': org_ID,
                        'ORG_ID': org_ID,
                        'ACCESS_ID': access_ID,
                        'MACHINE_ID': machine_ID,
                        'MACHINE_NAME': machine_name
                     },
                    'REQUEST': {
                        'REQUEST_TIME': now.strftime("%d/%m/%Y_%H:%M:%S"),        # Get the client time, even if its errorneous
                        'CLIENT_VERSION':'V0.3',               # TODO: Get the plugin version number from octoprint
                        'RequestSource': get_source_ip()
                    },
                    "SWEEP_CFG": sweep_cfg.as_dict(),
                    "CONDITIONS":str(self._settings.get(["CONDITIONS"])),
                    "PRINTER": {
                        "PRINTER_MAKE":self._settings.get(["MANUFACTURER_NAME"]), 
                        "PRINTER_MODEL":self._settings.get(["MODELID"]),
                        'VERSION': "V0.01",
                        'MANUFACTURER_NAME': ""
                    },                    
                }
        
    postreq = requests.post(SERVICE_URL, json=json.dumps(postdata), timeout=SERVICE_TIMEOUT_THD)
    response_body = json.loads(postreq.text)
        
    if 'exception' in response_body: raise_exception_from_response(response_body['exception'])
    elif 'solution' in response_body:
        solution = json.loads(response_body['solution'])
        gui_data = json.loads(response_body['gui_data'])
        return solution[0], solution[1], np.array(gui_data['bp']), np.array(gui_data['g'])
    elif 'message' in response_body:
        if response_body['message'] == 'Internal server error': raise AutocalInternalServerError
    else: return None


def autocal_service_guidata(axis, sweep_cfg, metadata, accelerometer, client_ID, access_ID, org_ID, machine_ID, machine_name, model_ID, manufacturer_name, self):
    
    now = datetime.now()
    postdata =  {   'ACTION': 'CALIBRATE',
                    'XAXISRESPONSE': encode_float_list_to_base64(accelerometer.x_buff),
                    'YAXISRESPONSE': encode_float_list_to_base64(accelerometer.y_buff),
                    'ZAXISRESPONSE': encode_float_list_to_base64(accelerometer.z_buff),
                    'AXIS': axis,
                    'OPERATION': 'VERIFY',
                    'METADATA': metadata if metadata is not {} else 'N/A',
                    'ACCESS':{
                        'CLIENT_ID': org_ID,
                        'ORG_ID': org_ID,
                        'ACCESS_ID': access_ID,
                        'MACHINE_ID': machine_ID,
                        'MACHINE_NAME': machine_name
                    },
                    'REQUEST': {
                        'REQUEST_TIME': now.strftime("%d/%m/%Y_%H:%M:%S"),        # Get the client time, even if its errorneous
                        'CLIENT_VERSION':'V0.3',               # TODO: Get the plugin version number from octoprint
                        'RequestSource': get_source_ip()
                    },
                    "SWEEP_CFG": sweep_cfg.as_dict(),
                    "CONDITIONS":str(self._settings.get(["CONDITIONS"])),
                    "PRINTER": {
                        "PRINTER_MAKE":self._settings.get(["MANUFACTURER_NAME"]), 
                        "PRINTER_MODEL":self._settings.get(["MODELID"]),
                        'MODELID': "V0.01",
                        'MANUFACTURER_NAME':""
                    }, 
                }
    
    postreq = requests.post(SERVICE_URL, json=json.dumps(postdata), timeout=SERVICE_TIMEOUT_THD)
    response_body = json.loads(postreq.text)

    if 'exception' in response_body: raise_exception_from_response(response_body['exception'])
    elif 'verification' in response_body:
        gui_data = json.loads(response_body['gui_data'])
        return np.array(gui_data['bp']), np.array(gui_data['g'])
    elif 'message' in response_body:
        if response_body['message'] == 'Internal server error': raise AutocalInternalServerError
    else: return None


def raise_exception_from_response(exception_str):
    if exception_str == "NoSignalError": raise NoSignalError
    elif exception_str == "SignalSyncError": raise SignalSyncError
    elif exception_str == "NoQualifiedSolution": raise NoQualifiedSolution
    elif exception_str == "NoVibrationDetected": raise NoVibrationDetected
