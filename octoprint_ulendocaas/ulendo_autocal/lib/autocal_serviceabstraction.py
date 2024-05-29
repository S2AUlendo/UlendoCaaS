if "ulendo_autocal.lib" in __package__:
    from ..autocal_cfg import *
    from ..autocal_exceptions import *
elif __package__ == "lib":
    from autocal_cfg import *
    from autocal_exceptions import *
else:
    print(f'{__file__} __package__ is {__package__}')

import os
import requests
import json
import base64
import numpy as np


from datetime import datetime        
import socket

def get_source_ip():

    hostname = socket.gethostname()
    try:
        ip_address = str(socket.gethostbyname(hostname))
    except:
        ip_address = "0.0.0.0"
        
    
    return ip_address
    

def read_acclrmtr_data(axis):

    rawdata_filename = os.path.join(os.path.dirname(__file__), '..', 'data', 'tmp' + axis + 'rw')
    rawdata_file = open(rawdata_filename, 'rb')
    rawdata_bytes = rawdata_file.read(); rawdata_file.close()
    rawdata_str = base64.b64encode(rawdata_bytes).decode('utf-8')

    return rawdata_str



def autocal_service_solve(axis, sweep_cfg, metadata, client_ID, access_ID, org_ID, machine_ID, machine_name, model_ID, manufacturer_name, self):

    now = datetime.now()

    postdata =  {   'ACTION': 'CALIBRATE',
                    'XAXISRESPONSE': read_acclrmtr_data('x'),
                    'YAXISRESPONSE': read_acclrmtr_data('y'),
                    'ZAXISRESPONSE': read_acclrmtr_data('z'),
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
    
    post_filename = 'solve_post_' + now.strftime("%y%m%d_%H%M%S") + '.txt'
    post_file = open(os.path.join(os.path.dirname(__file__) , '..', 'data', post_filename), 'w') 
    json.dump(postdata, post_file, sort_keys=True, indent=4, ensure_ascii=False)
    post_file.close()
    
    
    postreq = requests.post(SERVICE_URL, json=json.dumps(postdata), timeout=SERVICE_TIMEOUT_THD)
    response_body = json.loads(postreq.text)
    
    response_filename = 'json_response.txt'
    response_file = open(os.path.join(os.path.dirname(__file__), '..', 'data', response_filename), 'w')
    json.dump(response_body, response_file, sort_keys=True, indent=4, ensure_ascii=False)
    response_file.close()
    self._logger.info('Output from solver', response_body)
    
    if 'exception' in response_body: raise_exception_from_response(response_body['exception'])
    elif 'solution' in response_body:
        solution = json.loads(response_body['solution'])
        gui_data = json.loads(response_body['gui_data'])
        return solution[0], solution[1], np.array(gui_data['bp']), np.array(gui_data['g'])
    elif 'message' in response_body:
        if response_body['message'] == 'Internal server error': raise AutocalInternalServerError
    else: return None


def autocal_service_guidata(axis, sweep_cfg, metadata, client_ID, access_ID, org_ID, machine_ID, machine_name, model_ID, manufacturer_name, self):
    
    now = datetime.now()
    postdata =  {   'ACTION': 'CALIBRATE',
                    'XAXISRESPONSE': read_acclrmtr_data('x'),
                    'YAXISRESPONSE': read_acclrmtr_data('y'),
                    'ZAXISRESPONSE': read_acclrmtr_data('z'),
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
    
    verify_filename = 'verify_post_' + now.strftime("%y%m%d_%H%M%S") + '.txt'
    verify_file = open(os.path.join(os.path.dirname(__file__), '..', 'data', verify_filename), 'w')
    json.dump(postdata, verify_file, sort_keys=True, indent=4, ensure_ascii=False)
    verify_file.close()


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

