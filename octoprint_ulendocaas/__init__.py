# coding=utf-8

from __future__ import absolute_import

import requests
import struct
import flask
import re

from math import pi, sqrt, floor
from datetime import datetime

from octoprint.util import ResettableTimer
from octoprint.util.comm import regex_float_pattern, parse_position_line, regex_firmware_splitter
import octoprint.plugin

from .cfg import *
from .ismags import get_ismag
from .service_exceptions import *
from .service_abstraction import autocal_service_solve, autocal_service_guidata, verify_credentials
from .adxl345 import Adxl345, AcclrmtrRangeCfg, AcclrmtrSelfTestSts, AcclrmtrStatus, ACCLRMTR_LIVE_VIEW_DOWNSAMPLE_FACTOR
from .adxl345 import DaemonNotRunning, PigpioNotInstalled, PigpioConnectionFailed, SpiOpenFailed

from .tab_layout import *
from .tab_buttons import *

BYTES_PER_FLOAT = len(struct.pack('f', float(0)))

calibration_keys = ['zv', 'zvd', 'mzv', 'ei', 'ei2h', 'ei3h']

def chunks(l, n): return [l[i:i + n] for i in range(0, len(l), n)]

regex_steps_per_unit = re.compile(
    r"X\s*(?P<x>{float})\s*Y\s*(?P<y>{float})\s*Z\s*(?P<z>{float})".format(
        float=regex_float_pattern
    )
)

regex_ftmcfg_splitter = re.compile(r"(^|\s+)([A-Z][A-Z0-9_]*):")
"""Regex to use for splitting M949 FTMCFG responses."""


AxisRespnsFSMStates = Enum('AxisRespnsFSMStates',
                        ['NONE',
                         'INIT',
                         'IDLE',
                         'HOME',
                         'GET_AXIS_INFO',
                         'CENTER',
                         'SWEEP',
                         'ANALYZE'])

class AxisRespnsFSMData():
    def __init__(self):
        self.state = AxisRespnsFSMStates.INIT
        self.state_prev = AxisRespnsFSMStates.NONE
        self.in_state_time = 0

        # States that should get reset
        self.axis = None
        self.axis_reported_len = None
        self.axis_reported_len_recvd = False
        self.axis_reported_steps_per_mm = None
        self.axis_reported_steps_per_mm_recvd = False
        self.axis_last_reported_pos = 0.

        self.axis_centering_wait_time = 0.
        self.sweep_initiated = False
        self.sweep_done_recvd = False
        self.accelerometer_stopped = False

        self.missed_sample_retry_count = 0


        self.printer_requires_additional_homing = False
        self.printer_additional_homing_axes = None


class InpShprSolution():
    def __init__(self, wc, zt, w_bp, G): self.wc = wc; self.zt = zt; self.w_bp = w_bp; self.G = G


class SweepConfig:
    def __init__(self, f0, f1, dfdt, a, step_ti, step_a, dly1_ti, dly2_ti, dly3_ti):
        self.f0 = f0; self.f1 = f1; self.dfdt = dfdt; self.a = a
        self.step_ti = step_ti; self.step_a = step_a; self.dly1_ti = dly1_ti; self.dly2_ti = dly2_ti; self.dly3_ti = dly3_ti
    def as_dict(self): return { "f0": self.f0, "f1": self.f1, "dfdt": self.dfdt, "a": self.a,
                                "step_ti": self.step_ti, "step_a": self.step_a, "dly1_ti": self.dly1_ti, "dly2_ti": self.dly2_ti, "dly3_ti": self.dly3_ti }


class UlendocaasPlugin(octoprint.plugin.SettingsPlugin,
                    octoprint.plugin.AssetPlugin,
                    octoprint.plugin.TemplatePlugin,
                    octoprint.plugin.SimpleApiPlugin,
                    octoprint.plugin.StartupPlugin
):

    def __init__(self):
        self.initialized = False
        return
        
    
    def on_after_startup(self):
        self._init()


    def _init(self):
        # Use this to init stuff dependent on the injected properties (including _logger, used by AxisRespnsFSM)
        if self.initialized: return

        self.tab_layout = TabLayout()
        
        self.fsm = AxisRespnsFSMData()
        self.fsm.state = AxisRespnsFSMStates.IDLE
        
        self.accelerometer = None

        self.sts_self_test_active = False
        self.sts_axis_calibration_active = False
        self.sts_axis_verification_active = False
        self.sts_acclrmtr_connected = False
        self.sts_acclrmtr_active = False
        self.sts_axis_calibration_axis = None
        self.sts_calibration_saved = False
        self.active_solution = None
        self.active_solution_axis = None
        self.active_verification_result = None
        self.x_calibration_sent_to_printer = False
        self.y_calibration_sent_to_printer = False

        self.calibration_vtol = 0.05

        self.metadata = {}
    
        if not SIMULATION:
            self.tab_layout.is_active_client = self.on_startup_verify_credentials()
            try:
                with open('/proc/cpuinfo', 'rb') as f:
                    model = f.read().strip()
                split_line = re.split(b'\n', model)
                for line in split_line:
                    if re.match(b'Serial', line): self.metadata['BOARDCPUSERIAL'] = re.split(b'Serial\t\t: ', line)[1].decode('utf-8')
                    if re.match(b'Model', line): self.metadata['BOARDMODEL'] = re.split(b'Model\t\t: ', line)[1].decode('utf-8')
            except:
                self.metadata['BOARDCPUSERIAL'] = 'NA'
                self.metadata['BOARDMODEL'] = 'NA'
            self.initialized = True


    def on_startup_verify_credentials(self):
        try:
            org_id, access_id, machine_id = self.get_credentials()
            check_status = verify_credentials(org_id, access_id, machine_id, self)
            return check_status
        except Exception as e:
            self.handle_calibration_service_exceptions(e)
            return False


    def send_printer_command(self, cmd):
        if SIMULATION:
            if VERBOSE > 1: self._logger.info('SIMULATION sending command to printer: ' + cmd)
            return
        self._printer.commands(cmd)

    ##~~ AssetPlugin mixin

    def get_assets(self):
        # Define your plugin's asset files to automatically include in the
        # core UI here.
        return {
            "js": ["js/ulendocaas.js", 
                   "js/plotly.js"
                   ],
            "css": ["css/ulendocaas.css"
                    ]
        }


    def send_client_acclrmtr_data(self):
        self.send_client_acclrmtr_data_TMR.cancel()

        if self.accelerometer is None: return

        acclrmtr_live_data_y = [0.]*ACCLRMTR_LIVE_VIEW_NUM_SAMPLES

        if self.sts_self_test_active:
            buffer_to_plot = self.accelerometer.z_buff_anim.copy()
        else:
            if self.fsm.axis == 'x': buffer_to_plot = self.accelerometer.x_buff_anim.copy()
            else: buffer_to_plot = self.accelerometer.y_buff_anim.copy() # Assume self.fsm.axis == 'y'.

        n = len(buffer_to_plot)
        if n < ACCLRMTR_LIVE_VIEW_NUM_SAMPLES:
            acclrmtr_live_data_y[-n:] = buffer_to_plot
        else:
            acclrmtr_live_data_y[:] = buffer_to_plot[-ACCLRMTR_LIVE_VIEW_NUM_SAMPLES:]

        acclrmtr_live_data_x = list(range(ACCLRMTR_LIVE_VIEW_NUM_SAMPLES))
        acclrmtr_live_data_x = [(T_DFLT*ACCLRMTR_LIVE_VIEW_DOWNSAMPLE_FACTOR)*(n + xi) for xi in acclrmtr_live_data_x]
        
        data = dict(
            type='acclrmtr_live_data',
            values_x=acclrmtr_live_data_x,
            values_y=acclrmtr_live_data_y
        )

        self._plugin_manager.send_plugin_message(self._identifier, data)

        if self.sts_acclrmtr_active or self.sts_self_test_active:
            self.send_client_acclrmtr_data_TMR = ResettableTimer(ACCLRMTR_LIVE_VIEW_RATE_SEC, self.send_client_acclrmtr_data)
            self.send_client_acclrmtr_data_TMR.start()


    def send_client_layout_status(self):
        data = dict(
            type = 'layout_status_1',
            acclrmtr_connect_btn_disabled = self.tab_layout.acclrmtr_connect_btn.disabled,
            acclrmtr_connect_btn_state = self.tab_layout.acclrmtr_connect_btn.state.name,
            calibrate_x_axis_btn_disabled = self.tab_layout.calibrate_x_axis_btn.disabled,
            calibrate_x_axis_btn_state = self.tab_layout.calibrate_x_axis_btn.state.name,
            calibrate_y_axis_btn_disabled = self.tab_layout.calibrate_y_axis_btn.disabled,
            calibrate_y_axis_btn_state = self.tab_layout.calibrate_y_axis_btn.state.name,
            select_zv_btn_disabled = self.tab_layout.select_zv_cal_btn.disabled,
            select_zv_btn_state = self.tab_layout.select_zv_cal_btn.state.name,
            select_zvd_btn_disabled = self.tab_layout.select_zvd_cal_btn.disabled,
            select_zvd_btn_state = self.tab_layout.select_zvd_cal_btn.state.name,
            select_mzv_btn_disabled = self.tab_layout.select_mzv_cal_btn.disabled,
            select_mzv_btn_state = self.tab_layout.select_mzv_cal_btn.state.name,
            select_ei_btn_disabled = self.tab_layout.select_ei_cal_btn.disabled,
            select_ei_btn_state = self.tab_layout.select_ei_cal_btn.state.name,
            select_ei2h_btn_disabled = self.tab_layout.select_ei2h_cal_btn.disabled,
            select_ei2h_btn_state = self.tab_layout.select_ei2h_cal_btn.state.name,
            select_ei3h_btn_disabled = self.tab_layout.select_ei3h_cal_btn.disabled,
            select_ei3h_btn_state = self.tab_layout.select_ei3h_cal_btn.state.name,
            load_calibration_btn_disabled = self.tab_layout.load_calibration_btn.disabled,
            save_calibration_btn_disabled = self.tab_layout.save_calibration_btn.disabled,
            load_calibration_btn_state = self.tab_layout.load_calibration_btn.state.name,
            save_calibration_btn_state = self.tab_layout.save_calibration_btn.state.name,
            clear_session_btn_disabled = self.tab_layout.clear_session_btn.disabled,
            vtol_slider_visible = self.tab_layout.vtol_slider_visible,
            is_active_client = self.tab_layout.is_active_client,
        )
        self._plugin_manager.send_plugin_message(self._identifier, data)


    def send_client_clear_calibration_result(self):
        for calibration_key in calibration_keys:
            calibration_btn = getattr(self.tab_layout, 'select_' + calibration_key + '_cal_btn')
            calibration_btn.state = CalibrationSelectionButtonStates.NOTSELECTED
        self.update_tab_layout()
        data = dict(
            type = 'clear_calibration_result'
        )
        self._plugin_manager.send_plugin_message(self._identifier, data)


    def send_client_clear_verification_result(self):
        data = dict(
            type = 'clear_verification_result'
        )
        self._plugin_manager.send_plugin_message(self._identifier, data)


    def update_tab_layout(self):
        busy = self.sts_self_test_active or self.sts_axis_calibration_active or self.sts_axis_verification_active

        # Button enable/disable
        if busy:
            # Disable all buttons
            btn_names = [a for a in self.tab_layout.__dict__ if '_btn' in a]
            for btn_name in btn_names:
                btn = getattr(self.tab_layout, btn_name)
                btn.disabled = True
            self.tab_layout.vtol_slider_visible = False
        else:
            self.tab_layout.acclrmtr_connect_btn.disabled = False
            self.tab_layout.clear_session_btn.disabled = False

            if self.sts_acclrmtr_connected:
                self.tab_layout.calibrate_x_axis_btn.disabled = False
                self.tab_layout.calibrate_y_axis_btn.disabled = False

            if self.active_solution is not None:
                for calibration_key in calibration_keys:
                    calibration_btn = getattr(self.tab_layout, 'select_' + calibration_key + '_cal_btn')
                    calibration_btn.disabled = False
            else:
                for calibration_key in calibration_keys:
                    calibration_btn = getattr(self.tab_layout, 'select_' + calibration_key + '_cal_btn')
                    calibration_btn.state = CalibrationSelectionButtonStates.NOTSELECTED

            if self.get_selected_calibration_type() in ['ei', 'ei2h', 'ei3h']:
                self.tab_layout.vtol_slider_visible = True
            else:
                self.tab_layout.vtol_slider_visible = False

            if self.get_selected_calibration_type() is not None and self.sts_acclrmtr_connected:
                self.tab_layout.load_calibration_btn.disabled = False
            else:
                self.tab_layout.load_calibration_btn.disabled = True

            if (self.active_solution_axis == 'x' and self.x_calibration_sent_to_printer) or \
               (self.active_solution_axis == 'y' and self.y_calibration_sent_to_printer):
                self.tab_layout.save_calibration_btn.disabled = False
            else:
                self.tab_layout.save_calibration_btn.disabled = True


        # Button states
        if self.sts_self_test_active:
            self.tab_layout.acclrmtr_connect_btn.state = AcclrmtrConnectButtonStates.CONNECTING
        if self.sts_acclrmtr_connected:
            self.tab_layout.acclrmtr_connect_btn.state = AcclrmtrConnectButtonStates.CONNECTED
        else:
            if not self.sts_self_test_active: self.tab_layout.acclrmtr_connect_btn.state = AcclrmtrConnectButtonStates.NOTCONNECTED

        if self.x_calibration_sent_to_printer:
            self.tab_layout.calibrate_x_axis_btn.state = CalibrateAxisButtonStates.CALIBRATIONAPPLIED
        elif not self.sts_axis_calibration_active and self.active_solution_axis == 'x':
            self.tab_layout.calibrate_x_axis_btn.state = CalibrateAxisButtonStates.CALIBRATIONREADY
        elif self.sts_axis_calibration_active and self.sts_axis_calibration_axis == 'x':
            self.tab_layout.calibrate_x_axis_btn.state = CalibrateAxisButtonStates.CALIBRATING
        else:
            self.tab_layout.calibrate_x_axis_btn.state = CalibrateAxisButtonStates.NOTCALIBRATED

        if self.y_calibration_sent_to_printer:
            self.tab_layout.calibrate_y_axis_btn.state = CalibrateAxisButtonStates.CALIBRATIONAPPLIED
        elif not self.sts_axis_calibration_active and self.active_solution_axis == 'y':
            self.tab_layout.calibrate_y_axis_btn.state = CalibrateAxisButtonStates.CALIBRATIONREADY
        elif self.sts_axis_calibration_active and self.sts_axis_calibration_axis == 'y':
            self.tab_layout.calibrate_y_axis_btn.state = CalibrateAxisButtonStates.CALIBRATING
        else:
            self.tab_layout.calibrate_y_axis_btn.state = CalibrateAxisButtonStates.NOTCALIBRATED

        if self.sts_axis_verification_active:
            self.tab_layout.load_calibration_btn.state = LoadCalibrationButtonStates.LOADING
        elif (self.active_solution_axis == 'x' and self.x_calibration_sent_to_printer) or \
             (self.active_solution_axis == 'y' and self.y_calibration_sent_to_printer):
            self.tab_layout.load_calibration_btn.state = LoadCalibrationButtonStates.LOADED
        else:
            self.tab_layout.load_calibration_btn.state = LoadCalibrationButtonStates.NOTLOADED

        if self.sts_calibration_saved:
            self.tab_layout.save_calibration_btn.state = SaveCalibrationButtonStates.SAVED
        else:
            self.tab_layout.save_calibration_btn.state = SaveCalibrationButtonStates.NOTSAVED

        self.send_client_layout_status()


    def send_client_popup(self, type, title, message, hide=True):
        data = dict(
            type='popup',
            popup=type, # TODO: this is confusing
            title=title,
            message=message,
            hide=hide
        )
        self._plugin_manager.send_plugin_message(self._identifier, data)


    def send_client_prompt_popup(self, title, message):
        data = dict(
            type='prompt_popup',
            title=title,
            message=message
        )
        self.awaiting_prompt_popup_reply = True
        self.prompt_popup_response = None
        self._plugin_manager.send_plugin_message(self._identifier, data)


    def fsm_update(self):
        if VERBOSE > 1: self._logger.info(f'FSM update: {self.fsm.state}')

        if self.fsm.state != self.fsm.state_prev:
            self.fsm.in_state_time = 0.
        else:
            self.fsm.in_state_time += FSM_UPDATE_RATE_SEC        

        if self.fsm.state == AxisRespnsFSMStates.INIT:
            if self.fsm.state_prev != AxisRespnsFSMStates.INIT:
                self.fsm_on_INIT_entry()
            else:
                self.fsm_on_INIT_during(); return
        elif self.fsm.state == AxisRespnsFSMStates.IDLE:
            if self.fsm.state_prev != AxisRespnsFSMStates.IDLE:
                self.fsm_on_IDLE_entry()
            else:
                self.fsm_on_IDLE_during(); return
        elif self.fsm.state == AxisRespnsFSMStates.HOME:
            if self.fsm.state_prev != AxisRespnsFSMStates.HOME:
                self.fsm_on_HOME_entry()
            else:
                self.fsm_on_HOME_during(); return
        elif self.fsm.state == AxisRespnsFSMStates.CENTER:
            if self.fsm.state_prev != AxisRespnsFSMStates.CENTER:
                self.fsm_on_CENTER_entry()
            else:
                self.fsm_on_CENTER_during(); return
        elif self.fsm.state == AxisRespnsFSMStates.GET_AXIS_INFO:
            if self.fsm.state_prev != AxisRespnsFSMStates.GET_AXIS_INFO:
                self.fsm_on_GET_AXIS_INFO_entry()
            else:
                self.fsm_on_GET_AXIS_INFO_during(); return
        elif self.fsm.state == AxisRespnsFSMStates.SWEEP:
            if self.fsm.state_prev != AxisRespnsFSMStates.SWEEP:
                self.fsm_on_SWEEP_entry()
            else:
                self.fsm_on_SWEEP_during(); return
        elif self.fsm.state == AxisRespnsFSMStates.ANALYZE:
            if self.fsm.state_prev != AxisRespnsFSMStates.ANALYZE:
                self.fsm_on_ANALYZE_entry()
            else:
                self.fsm_on_ANALYZE_during(); return
        
        self.fsm.state_prev = self.fsm.state

    
    def fsm_update_and_manage_tmr(self):
        
        self.fsm_update_TMR.cancel()

        self.fsm_update()

        # Routine is not finished.
        if self.fsm.state is not AxisRespnsFSMStates.IDLE:
            self.fsm_update_TMR = ResettableTimer(FSM_UPDATE_RATE_SEC, self.fsm_update_and_manage_tmr)
            self.fsm_update_TMR.start()


    def get_selected_calibration_type(self):
        type = None
        for calibration_key in calibration_keys:
            calibration_btn = getattr(self.tab_layout, 'select_' + calibration_key + '_cal_btn')
            if calibration_btn.state == CalibrationSelectionButtonStates.SELECTED: type = calibration_key
        return type
    

    def send_client_verification_result(self):
        # Get selected calibration type
        type = self.get_selected_calibration_type()
        if type is None:
            if VERBOSE: self._logger.error("Can't send result without a calibration selected!")
            return
        ismag = get_ismag(self.active_solution.w_bp, type, self.active_solution.wc, self.active_solution.zt, vtol=self.calibration_vtol)
        data = dict(
            type = 'verification_result',
            w_bp = (self.active_solution.w_bp / 2. / pi).tolist(),
            oldG = self.active_solution.G.tolist(),
            compensator_mag = ismag.tolist(),
            new_mag = (self.active_solution.G * ismag).tolist(),
            G = self.active_verification_result.tolist()
        )
        self._plugin_manager.send_plugin_message(self._identifier, data)


    def startup_accelerometer(self):
        try:
            if self.accelerometer is not None:
                try: self.accelerometer.close()
                except: pass # We'll ignore a fail here, since it could be due to the
                             # pigpio daemon no longer running.
            self.accelerometer = Adxl345(range = AcclrmtrRangeCfg['+/-2g'])
            return True
        except DaemonNotRunning:
            self.send_client_popup(type='error', title='Pigpio Not Running',
                                    message=f'The accelerometer cannot be connected'\
                                    ' because the pigpio daemon is not running.', hide=False)
        except PigpioNotInstalled:
            self.send_client_popup(type='error', title='Pigpio Not Installed',
                                    message=f'The accelerometer cannot be connected'\
                                    ' because the pigpio library is not installed.', hide=False)
        except PigpioConnectionFailed:
            self.send_client_popup(type='error', title='Pigpio Connection Failed',
                                    message=f'The accelerometer cannot be connected'\
                                    ' because the pigpio connection failed.', hide=False)
        except SpiOpenFailed:
            self.send_client_popup(type='error', title='Pigpio SPI Open Failed',
                                    message=f'The accelerometer cannot be connected'\
                                    ' because the SPI connection could not be opened.', hide=False)
        except Exception as e:
            self.send_client_popup(type='error', title='Accelerometer Startup Failed',
                                    message=str(e), hide=False)
        return False


    def on_acclrmtr_connect_btn_click(self):
        
        if self.tab_layout.acclrmtr_connect_btn.disabled: return
        
        self.sts_self_test_active = True
        self.sts_acclrmtr_connected = False
        self.update_tab_layout()
        
        if not self.startup_accelerometer():
            self.sts_self_test_active = False
            self.update_tab_layout()
            return

        self.send_client_acclrmtr_data_TMR = ResettableTimer(ACCLRMTR_LIVE_VIEW_RATE_SEC, self.send_client_acclrmtr_data)
        self.send_client_acclrmtr_data_TMR.start()

        st_result = self.accelerometer.self_test()

        self.send_client_acclrmtr_data_TMR.cancel()

        if st_result == AcclrmtrSelfTestSts.PASS:
            self.sts_acclrmtr_connected = True
        else:
            if self.accelerometer.status == AcclrmtrStatus.STOPPED:
                self.send_client_popup(type='error', title='Accelerometer Error', message='Accelerometer self-test failed. Try another device.')
            else:
                self.send_client_popup(type='error', title='Accelerometer Error', message='Connecting to the accelerometer failed. Check hardware and wiring.')
            self.sts_acclrmtr_connected = False
            self.accelerometer.close()

        self.sts_self_test_active = False
        self.update_tab_layout()


    def report_connection_status(self):
        connection_string, port, _, _ = self._printer.get_current_connection()

        status = 'notconnected'
        if (connection_string == "Operational"):
            status = 'connected'
            self.metadata['CONNECTPORT'] = port
        if SIMULATION: status = 'connected'
        
        data = dict(
            type = 'printer_connection_status',
            status = status
        )
        self._plugin_manager.send_plugin_message(self._identifier, data)


    def on_calibrate_axis_btn_click(self, axis):
        if (axis == 'x' and self.tab_layout.calibrate_x_axis_btn.disabled) or \
           (axis == 'y' and self.tab_layout.calibrate_y_axis_btn.disabled): return
        
        if not SIMULATION:
            connection_string, _, _, _ = self._printer.get_current_connection()

            if(connection_string != "Operational"):
                self.send_client_popup(type='error', title='Printer not connected.', message='Printer must be connected in order to start calibration.')
                return
        
        if self.fsm.state is AxisRespnsFSMStates.IDLE:
            self.sts_axis_calibration_active = True
            self.sts_axis_calibration_axis = axis
            
            if (axis == 'x'): self.x_calibration_sent_to_printer = False
            elif (axis == 'y'): self.y_calibration_sent_to_printer = False
            self.active_solution = None
            self.active_solution_axis = None

            self.update_tab_layout()
            self.send_client_clear_calibration_result()
            self.send_client_clear_verification_result()

            if VERBOSE > 1: self._logger.info(f'calibrate_axis started on axis: {axis}')
            self.fsm_update_TMR = ResettableTimer(FSM_UPDATE_RATE_SEC, self.fsm_update_and_manage_tmr)
            self.fsm_update_TMR.start()
            self.fsm_start(axis)
    

    def on_select_calibration_btn_click(self, type):
        selection_changed = False
        for calibration_key in calibration_keys:
            calibration_btn = getattr(self.tab_layout, 'select_' + calibration_key + '_cal_btn')
            if calibration_key == type:
                if not calibration_btn.disabled:
                    selection_changed = calibration_btn.state is not CalibrationSelectionButtonStates.SELECTED
                    calibration_btn.state = CalibrationSelectionButtonStates.SELECTED
            else:
                calibration_btn.state = CalibrationSelectionButtonStates.NOTSELECTED
        if selection_changed:
            if self.active_solution_axis == 'x': self.x_calibration_sent_to_printer = False
            elif self.active_solution_axis == 'y': self.y_calibration_sent_to_printer = False
            self.sts_calibration_saved = False
            self.send_client_clear_verification_result()
            self.send_client_calibration_result(type)
        self.update_tab_layout()


    def send_client_calibration_result(self, type):
        ismag = get_ismag(self.active_solution.w_bp, type, self.active_solution.wc, self.active_solution.zt, vtol=self.calibration_vtol)
        data = dict(
            type = 'calibration_result',
            istype = type, # TODO: Confusing.
            w_bp = (self.active_solution.w_bp / 2. / pi).tolist(),
            G = self.active_solution.G.tolist(),
            compensator_mag = ismag.tolist(),
            new_mag = (self.active_solution.G * ismag).tolist(),
            axis = self.active_solution_axis
        )
        self._plugin_manager.send_plugin_message(self._identifier, data)

    
    def on_load_calibration_btn_click(self):
        if self.tab_layout.load_calibration_btn.disabled: return

        type = self.get_selected_calibration_type()
        if type is None or self.fsm.state is not AxisRespnsFSMStates.IDLE: # TODO: Check printer is connected
            if VERBOSE: self._logger.error(f'Calibration load command conditions not correct.')
            return
        
        if VERBOSE > 1: self._logger.info(f'Sending calibration ' + type)

        mode_code = ''
        if type == 'zv': mode_code = '1'
        elif type == 'zvd': mode_code = '2'
        elif type == 'zvdd': mode_code = '3'
        elif type == 'zvddd': mode_code = '4'
        elif type == 'mzv': mode_code = '8'
        elif type == 'ei': mode_code = '5'
        elif type == 'ei2h': mode_code = '6'
        elif type == 'ei3h': mode_code = '7'

        frequency_code = ''
        zeta_code = ''
        vtol_code = ''
        if self.active_solution_axis == 'x':
            frequency_code = 'A'
            zeta_code = 'I'
            vtol_code = 'Q'
        elif self.active_solution_axis == 'y':
            frequency_code = 'B'
            zeta_code = 'J'
            vtol_code = 'R'
        
        printer_configuration_command = 'M493 ' + self.active_solution_axis.upper() + mode_code + ' ' \
                                        + frequency_code + f'{self.active_solution.wc/2./pi:0.2f}' + ' ' \
                                        + zeta_code + f'{self.active_solution.zt:0.4f}'
        ei_type = type in ['ei', 'ei2h', 'ei3h']
        if ei_type:
            printer_configuration_command += ' ' + vtol_code + f'{self.calibration_vtol:0.2f}'

        if VERBOSE > 1: self._logger.info(f'Configuring printer with: {printer_configuration_command}')
        self.send_client_logger_info('Sent printer: ' + printer_configuration_command \
                                        + ' (Set the ' + self.active_solution_axis.upper() + ' axis to use ' + type.upper() \
                                        + f' shaping @ {self.active_solution.wc/2./pi:0.2f}Hz & ζ = {self.active_solution.zt:0.4f}' \
                                        + (f' & vtol = {self.calibration_vtol:0.2f}).' if ei_type else ').') )
        self.send_printer_command(printer_configuration_command)

        self.sts_calibration_saved = False

        self.sts_axis_verification_active = True
        if VERBOSE > 1: self._logger.info(f'verify started on axis: {self.active_solution_axis}')
        self.fsm_update_TMR = ResettableTimer(FSM_UPDATE_RATE_SEC, self.fsm_update_and_manage_tmr)
        self.fsm_update_TMR.start()
        self.fsm_start(self.active_solution_axis)

        self.update_tab_layout()


    def on_save_calibration_btn_click(self):
        if self.tab_layout.save_calibration_btn.disabled: return
        self.send_printer_command('M500')
        self.sts_calibration_saved = True
        self.send_client_logger_info('Sent printer: M500 (settings saved to EEPROM).')
        self.send_client_popup(type='info', title='Saved to EEPROM',
                                message='Settings have been saved to printer.')
        self.update_tab_layout()


    def on_vtol_slider_update(self, val):
        val = float(val)
        if (val/100.) != self.calibration_vtol:
            if self.get_selected_calibration_type() == 'ei2h':
                self.calibration_vtol = max(0.01, val/100.) # 2H EI does not support 0 vtol.
            else: self.calibration_vtol = val/100.
            if self.active_solution_axis == 'x': self.x_calibration_sent_to_printer = False
            elif self.active_solution_axis == 'y': self.y_calibration_sent_to_printer = False
            self.sts_calibration_saved = False
            self.send_client_clear_verification_result()
            self.send_client_calibration_result(self.get_selected_calibration_type())
            self.update_tab_layout()


    def on_clear_session_btn_click(self):
        if self.tab_layout.clear_session_btn.disabled: return

        # FSM State Reset
        self.fsm_reset()
        self.fsm.state = AxisRespnsFSMStates.IDLE

        # Plugin Data Reset
        self.sts_self_test_active = False
        self.sts_axis_calibration_active = False
        self.sts_axis_verification_active = False
        self.sts_acclrmtr_connected = False
        self.sts_axis_calibration_axis = None
        self.sts_calibration_saved = False
        self.active_solution = None
        self.active_solution_axis = None
        self.active_verification_result = None
        self.x_calibration_sent_to_printer = False
        self.y_calibration_sent_to_printer = False
        self.update_tab_layout()


    def on_prompt_cancel_click(self):
        self.awaiting_prompt_popup_reply = False
        self.prompt_popup_response = 'cancel'

    def on_prompt_proceed_click(self):
        self.awaiting_prompt_popup_reply = False
        self.prompt_popup_response = 'proceed'


    def send_client_logger_info(self, text):
        now = datetime.now()
        text_w_timestamp = now.strftime("%H:%M:%S") + ' ' + text
        data = dict(
            type = 'logger_info',
            message = text_w_timestamp
        )
        self._plugin_manager.send_plugin_message(self._identifier, data)


    ##~~ SimpleApiPlugin mixin
    def get_api_commands(self):
        return dict(
            get_layout_status=[], # TODO: make this request load graphs as well
            acclrmtr_connect_btn_click=[],
            calibrate_axis_btn_click=['axis'],
            select_calibration_btn_click=['type'],
            load_calibration_btn_click=[],
            save_calibration_btn_click=[],
            vtol_slider_update=['val'],
            get_connection_status=[],
            start_over_btn_click=[],
            clear_session_btn_click=[],
            prompt_cancel_click=[],
            prompt_proceed_click=[],
            on_settings_close_verify_credentials=[],
        )

    
    def on_api_command(self, command, data):
        if command == 'get_layout_status': self.send_client_layout_status()
        elif command == 'acclrmtr_connect_btn_click': self.on_acclrmtr_connect_btn_click()
        elif command == 'calibrate_axis_btn_click': self.on_calibrate_axis_btn_click(data['axis'])
        elif command == 'select_calibration_btn_click': self.on_select_calibration_btn_click(data['type'])
        elif command == 'load_calibration_btn_click': self.on_load_calibration_btn_click()
        elif command == 'save_calibration_btn_click': self.on_save_calibration_btn_click()
        elif command == 'vtol_slider_update': self.on_vtol_slider_update(data['val'])
        elif command == 'get_connection_status': self.report_connection_status()
        elif command == 'clear_session_btn_click': self.on_clear_session_btn_click()
        elif command == 'prompt_cancel_click': self.on_prompt_cancel_click()
        elif command == 'prompt_proceed_click': self.on_prompt_proceed_click()
        elif command == 'on_settings_close_verify_credentials':  return self.on_settings_close_verify_credentials()
        
    def on_settings_close_verify_credentials(self):
        try:
            org_id, access_id, machine_id = self.get_credentials()
            check_status = verify_credentials(org_id, access_id, machine_id, self)
            self.tab_layout.is_active_client = check_status
            self.update_tab_layout()
            return flask.jsonify(license_status=check_status)
        except Exception as e:
            self.handle_calibration_service_exceptions(e)
            return False
    
    def get_credentials(self):
        
        org_id = self._settings.get(["ORG"])
        access_id = self._settings.get(["ACCESSID"])
        machine_id = self._settings.get(["MACHINEID"])
        
        return org_id, access_id, machine_id
    
    ##~~ Hooks
    def proc_rx(self, comm_instance, line, *args, **kwargs):
        try:
            if VERBOSE > 2: self._logger.info(f'Got line from printer: {line}')
            if not self.initialized: return line
            if 'M494' in line:
                if 'FTMCFG' in line:
                    split_line = regex_ftmcfg_splitter.split(line.strip())[
                        1:
                    ]  # first entry is empty start of trimmed string
                    result = {}
                    for _, key, value in chunks(split_line, 3):
                            result[key] = value.strip()
                            if self.fsm.state == AxisRespnsFSMStates.GET_AXIS_INFO:
                                if key == self.fsm.axis.upper() + '_MAX_LENGTH':
                                    self.fsm.axis_reported_len_recvd = True
                                    self.fsm.axis_reported_len = float(result[key])
                    self.metadata['FTMCFG'] = result
                    if VERBOSE > 1: self._logger.info('Metadata updated:')
                    if VERBOSE > 1: self._logger.info(self.metadata)
                elif 'profile ran to completion' in line:
                    if self.fsm.state == AxisRespnsFSMStates.SWEEP:
                        self.fsm.sweep_done_recvd = True
                        if VERBOSE > 1: self._logger.info(f'Got sweep done message')

            elif self.fsm.state == AxisRespnsFSMStates.CENTER and (self.fsm.axis.upper() + ':') in line:
                self.fsm.axis_last_reported_pos = parse_position_line(line)[self.fsm.axis]
                if VERBOSE > 1: self._logger.info(f'Got reported position = {self.fsm.axis_last_reported_pos}')
            elif 'NAME:' in line or line.startswith('NAME.'):
                split_line = regex_firmware_splitter.split(line.strip())[
                    1:
                ]  # first entry is empty start of trimmed string
                result = {}
                for _, key, value in chunks(split_line, 3):
                        result[key] = value.strip()
                if result.get('FIRMWARE_NAME') is not None:
                    self.metadata['FIRMWARE'] = result
                    if VERBOSE > 1: self._logger.info('Metadata updated:')
                    if VERBOSE > 1: self._logger.info(self.metadata)
            elif 'M92' in line:
                match = regex_steps_per_unit.search(line)
                if match is not None:
                    result = {
                        "x": float(match.group("x")),
                        "y": float(match.group("y")),
                        "z": float(match.group("z")),
                    }
                    self.fsm.axis_reported_steps_per_mm = result[self.fsm.axis]
                    self.fsm.axis_reported_steps_per_mm_recvd = True
                    self.metadata['STEPSPERUNIT'] = str(result)
                    if VERBOSE > 1: self._logger.info('Metadata updated:')
                    if VERBOSE > 1: self._logger.info(self.metadata)
            elif self.fsm.state == AxisRespnsFSMStates.CENTER and 'echo:Home' in line and 'First' in line:
                split_line_0 = re.split(r"echo:Home ", line.strip())
                split_line_1 = re.split(r" First", split_line_0[1].strip())
                self.fsm.printer_requires_additional_homing = True
                self.fsm.printer_additional_homing_axes = split_line_1[0]

            return line
        
        except Exception as e:
            self._logger.error(f"Network error in autocal_service_guidata: {e}")
            raise

    # TODO: 
    def get_update_information(self):
        # Define the configuration for your plugin to use with the Software Update
        # Plugin here. See https://docs.octoprint.org/en/master/bundledplugins/softwareupdate.html
        # for details.
        return {
            "ulendocaas": {
                "displayName": "Ulendo Calibration Plugin",
                "displayVersion": self._plugin_version,

                # version check: github repository
                "type": "github_release",
                "user": "S2AUlendo",
                "repo": "UlendoCaas",
                "current": self._plugin_version,

                # update method: pip
                "pip": "https://github.com/S2AUlendo/UlendoCaaS/archive/{target_version}.zip",
            }
        }
    

    def handle_calibration_service_exceptions(self, e):
        try: raise e
        except requests.exceptions.Timeout:
            self.send_client_popup(type='error', title='Timed out connecting to Ulendo server.',
                                    message=f'Timed out connecting to the Ulendo server af'\
                                    'ter {SERVICE_TIMEOUT_THD} seconds.', hide=False)
        except (requests.exceptions.HTTPError,
                    requests.exceptions.ConnectionError,
                    requests.exceptions.RequestException):
            self.send_client_popup(type='error', title='Error connecting to Ulendo server.',
                                    message='Got an error while connecting to the Ulendo s'\
                                    'erver. If you are connected to the internet, it could'\
                                    ' be a problem with the service. Try again later.', hide=False)
        except NoSignalError:
            self.send_client_popup(type='error', title='Weak signal detected.',
                                    message='Could not calibrate due to a weak signal. Is '\
                                    'the accelerometer mounted on the correct axis and in '\
                                    'the correct orientation?', hide=False)
        except SignalSyncError:
            self.send_client_popup(type='error', title='Signal detection issue.',
                                    message='Could not calibrate due to a signal detection'\
                                    ' issue. Is the accelerometer mounted on the correct a'\
                                    'xis and in the correct orientation?', hide=False)
        except NoVibrationDetected:
            self.send_client_popup(type='info', title='No vibration detected.',
                                    message='No vibration on the axis was detected -- shap'\
                                    'ing on this axis has been disabled, but you may wish '\
                                    'to use the same shaper as the other axis. Contact Ule'\
                                    'ndo for more details.', hide=False) # TODO: automate or provide a guide
            self.send_printer_command('M493 S1 ' + self.fsm.axis.upper() + '0')
        except (NoQualifiedSolution, AutocalInternalServerError):
            self.send_client_popup(type='error', title='Internal Ulendo error.',
                                    message='An internal Ulendo error occured. This cannot'\
                                    ' be solved at this time.', hide=False)
        except UnknownResponse:
            self.send_client_popup(type='error', title='Unknown response received.',
                                    message='This cannot be solved at this time. Please'\
                                    ' contact Ulendo for this matter.', hide=False)
        except NotAuthenticated:
            self.send_client_popup(type='error', title='Not authenticated.',
                                    message='Unable to verify plugin credentials. Please'\
                                    ' verify your plugin configuration.', hide=False)
        except MachineIDNotFound:
            self.send_client_popup(type='error', title='Machine ID not found.',
                                    message='The machine ID provided in settings is'\
                                    ' not found in our server.', hide=False)
        except Exception:
            self.send_client_popup(type='error', title='Unknown error.',
                                    message=str(e), hide=False)


#
# FSM State Logic
#

    def fsm_reset(self, reset_for_retry=False):
        
        self.fsm.axis_reported_len = None
        self.fsm.axis_reported_len_recvd = False
        self.fsm.axis_reported_steps_per_mm = None
        self.fsm.axis_reported_steps_per_mm_recvd = False
        self.fsm.axis_last_reported_pos = 0.

        self.fsm.axis_centering_wait_time = 0.
        self.fsm.sweep_initiated = False
        self.fsm.sweep_done_recvd = False
        self.fsm.accelerometer_stopped = False

        self.fsm.printer_requires_additional_homing = False

        if not reset_for_retry:
            self.fsm.axis = None
            self.fsm.missed_sample_retry_count = 0


    def fsm_on_INIT_entry(self): return
    

    def fsm_on_INIT_during(self): self.fsm.state = AxisRespnsFSMStates.IDLE; return
    

    def fsm_on_IDLE_entry(self): return
        

    def fsm_on_IDLE_during(self): return
    

    def fsm_on_HOME_entry(self):
        global GET_AXIS_INFO_TIMEOUT

        if not self.sts_axis_verification_active:
            self.send_printer_command('M493 S1 ' + self.fsm.axis.upper() + '0')

        if self.fsm.printer_requires_additional_homing:
            if (not self._settings.get(["home_axis_before_calibration"])):
                self.send_client_popup(type='error', title='Homing Configuration Error',
                                       message='Your printer wants homing to occur before it can accept \
                                                movement commands, but homing before calibration is disa\
                                                bled in settings. Re-enable the setting and try again.')
                self.fsm_kill()
            else:
                self.send_client_prompt_popup(title='Printer Homing Confirm',
                                                message='Your printer wants to home the ' + 
                                                self.fsm.printer_additional_homing_axes + ' axes before \
                                                moving. Verify motion is clear and proceed.')
                GET_AXIS_INFO_TIMEOUT = 45 # Temporarily prevent an error during a longer homing. TODO: properly monitor busy response
        else:
            if (self._settings.get(["home_axis_before_calibration"])):
                self.send_printer_command('G28 ' + self.fsm.axis.upper())

    
    def fsm_on_HOME_during(self):
        if self.fsm.printer_requires_additional_homing:
            if self.awaiting_prompt_popup_reply: return
            else:
                if self.prompt_popup_response == 'cancel':
                    self.fsm_kill(); return
                if self.prompt_popup_response == 'proceed':
                    self.send_printer_command('G28 ' + self.fsm.printer_additional_homing_axes)
                    self.fsm.printer_requires_additional_homing = False
        self.fsm.state = AxisRespnsFSMStates.GET_AXIS_INFO

    
    def fsm_on_GET_AXIS_INFO_entry(self):
        self.send_printer_command('M494')
        self.send_printer_command('M92')
        self.send_client_popup(type='info', title='Calibrating',
                                   message='Initiating calibration sweep procedure...')

    
    def fsm_on_GET_AXIS_INFO_during(self):
        if self.fsm.in_state_time > GET_AXIS_INFO_TIMEOUT:
            self.sts_axis_calibration_active = False
            self.sts_axis_verification_active = False
            self.send_client_popup(type='error', title='Axis Info. Error',
                                   message='Couldn\'t get information about the axis. Is the firmware compatible?')
            self.fsm_kill()
        else:
            if self.fsm.axis_reported_len_recvd:
                if (self._settings.get(["home_axis_before_calibration"])):
                    self.fsm.state = AxisRespnsFSMStates.CENTER
                else: self.fsm.state = AxisRespnsFSMStates.SWEEP
            if SIMULATION:
                self.fsm.axis_reported_len = 255.
                self.fsm.state = AxisRespnsFSMStates.CENTER

    
    def fsm_on_CENTER_entry(self):
        self.send_printer_command('G1 ' + self.fsm.axis.upper() + str(round(self.fsm.axis_reported_len/2)) + ' F' + str(MOVE_TO_CENTER_SPEED_MM_PER_MIN))

    
    def fsm_on_CENTER_during(self):
        if self.fsm.printer_requires_additional_homing:
            self.fsm.axis_reported_len_recvd = False
            self.fsm.state = AxisRespnsFSMStates.HOME
        self.send_printer_command('M114')
        if VERBOSE > 1: self._logger.info(f'on_CENTER vars: {self.fsm.axis_last_reported_pos}, {self.fsm.axis_reported_len}, {self.fsm.axis_centering_wait_time}')
        if abs(self.fsm.axis_last_reported_pos - self.fsm.axis_reported_len/2) < 1. or not self._settings.get(["home_axis_before_calibration"]) or SIMULATION:
            
            if self.fsm.axis_centering_wait_time >= self.fsm.axis_reported_len/2/(MOVE_TO_CENTER_SPEED_MM_PER_MIN/60):
                self.fsm.state = AxisRespnsFSMStates.SWEEP
            self.fsm.axis_centering_wait_time += FSM_UPDATE_RATE_SEC
        if self.fsm.in_state_time > CENTER_AXIS_TIMEOUT:
            self.send_client_popup(type='error', title='Axis Center Timeout',
                                   message='Unknown error moving the axis to center.')
            self.fsm_kill()
    

    def fsm_on_SWEEP_entry(self):
        self.send_printer_command('M115')

        self.accelerometer.start()
        self.sts_acclrmtr_active = True
        self.send_client_acclrmtr_data_TMR = ResettableTimer(ACCLRMTR_LIVE_VIEW_RATE_SEC, self.send_client_acclrmtr_data)
        self.send_client_acclrmtr_data_TMR.start()
        

    def fsm_on_SWEEP_during(self):
        
        if self.fsm.in_state_time > FSM_SWEEP_START_DLY and not self.fsm.sweep_initiated:
            if not SIMULATION:

                f1_max = floor(sqrt(int(self._settings.get(["acceleration_amplitude"]))*self.fsm.axis_reported_steps_per_mm)/(2.*pi))
                if self._settings.get(["override_end_frequency"]):
                    f1 = min( f1_max, int(self._settings.get(["end_frequency_override"])))
                else:
                    f1 = f1_max
                
                self.sweep_cfg = SweepConfig(   f0=int(self._settings.get(["starting_frequency"])),
                                                f1=int(f1),
                                                dfdt=int(self._settings.get(["frequency_sweep_rate"])),
                                                a=int(self._settings.get(["acceleration_amplitude"])),
                                                step_ti=int(self._settings.get(["step_time"])),
                                                step_a=int(self._settings.get(["step_acceleration"])),
                                                dly1_ti=int(self._settings.get(["delay1_time"])),
                                                dly2_ti=int(self._settings.get(["delay2_time"])),
                                                dly3_ti=int(self._settings.get(["delay3_time"]))
                                            )
                # M494
                #
                #  *    A<mode> Start / abort a frequency sweep profile.
                #  *
                #  *       0: None active.
                #  *       1: Continuous sweep on X axis.
                #  *       2: Continuous sweep on Y axis.
                #  *       99: Abort the current sweep.
                #  * 
                #  *    B<float> Start frequency.
                #  *    C<float> End frequency.
                #  *    D<float> Frequency rate.
                #  *    E<float> Acceleration amplitude.
                #  *    F<float> Step time.
                #  *    H<float> Step acceleration amplitude.
                #  *    I<float> Delay time to opening step.
                #  *    J<float> Delay time from opening step to sweep.
                #  *    K<float> Delay time from sweep to closing step.

                mode_code = 0
                if self.fsm.axis == 'x': mode_code = 1
                elif self.fsm.axis == 'y': mode_code = 2
                cmd =    'M494' + ' A' + str(mode_code) \
                                + ' B' + str(self.sweep_cfg.f0) \
                                + ' C' + str(self.sweep_cfg.f1) \
                                + ' D' + str(self.sweep_cfg.dfdt) \
                                + ' E' + str(self.sweep_cfg.a) \
                                + ' F' + f'{self.sweep_cfg.step_ti/1000:0.3f}' \
                                + ' H' + str(self.sweep_cfg.step_a) \
                                + ' I' + f'{self.sweep_cfg.dly1_ti/1000:0.3f}' \
                                + ' J' + f'{self.sweep_cfg.dly2_ti/1000:0.3f}' \
                                + ' K' + f'{self.sweep_cfg.dly3_ti/1000:0.3f}'
                self.send_printer_command(cmd)

            self.fsm.sweep_initiated = True

        if not self.fsm.accelerometer_stopped and ((SIMULATION and self.fsm.in_state_time > 60.) or
                                               (not SIMULATION and self.fsm.sweep_done_recvd)):
            self.accelerometer.stop()
            if VERBOSE > 1: self._logger.info('Triggering accelerometer data collection stop.')
            self.fsm.accelerometer_stopped = True

        if self.accelerometer.status != AcclrmtrStatus.COLLECTING:
            f_abort = False
            if self.accelerometer.status == AcclrmtrStatus.STOPPED:
                self.sts_acclrmtr_active = False
                self.fsm.state = AxisRespnsFSMStates.ANALYZE
            elif self.accelerometer.status == AcclrmtrStatus.OVERRUN:
                if self.fsm.missed_sample_retry_count < MAX_RETRIES_FOR_MISSED_SAMPLES: # Setup a retry
                    self.fsm.missed_sample_retry_count += 1

                    self.send_printer_command('M494 A99')
                    
                    self.send_client_popup(type='info', title='Retrying', message='Some accelerometer data was lost, the routine will be retried.')
                    
                    self.fsm_reset(reset_for_retry=True)
                    self.sts_acclrmtr_active = False
                    self.fsm.state = AxisRespnsFSMStates.HOME

                else:  # Max retries hit
                    self.send_client_popup(type='error', title='Retry Limit', message='Retry limit reached, exiting this attempt.')
                    f_abort = True
            else:
                self.send_client_popup(type='error', title='Accelerometer Connection Lost', message=f'Accelerometer connection was lost during the routine (error code: {self.accelerometer.status.value}).')
                f_abort = True
                
            if f_abort:
                self.send_printer_command('M494 A99')
                self.fsm_kill()

        return


    def fsm_on_ANALYZE_entry(self):
        
        self.fsm.missed_sample_retry_count = 0

        if SIMULATION:
            self.sts_axis_calibration_active = False
            self.update_tab_layout()
            return

        if not self.sts_axis_verification_active:
            try:
                self.send_client_popup(type='info', title='Processing Data', message='Processing data, please wait...')
                client_ID = self._settings.get(["CLIENTID"])
                org_ID = self._settings.get(["ORG"])
                access_ID = self._settings.get(["ACCESSID"])
                machine_ID = self._settings.get(["MACHINEID"])
                machine_name = self._settings.get(["MACHINENAME"])
                model_ID = self._settings.get(["MODELID"])
                manufacturer_name = self._settings.get(["MANUFACTURER_NAME"])
                wc, zt, w_gui_bp, G_gui = autocal_service_solve(self.fsm.axis, self.sweep_cfg, self.metadata, self.accelerometer, client_ID, access_ID, org_ID, machine_ID, machine_name, model_ID, manufacturer_name, self)
                self.send_client_popup(type='success', title='Calibration Received', message='')
                
            except Exception as e:
                self.handle_calibration_service_exceptions(e)
                self.active_solution = None
            else:
                self.active_solution = InpShprSolution(wc, zt, w_gui_bp, G_gui)
                self.active_solution_axis = self.fsm.axis
                self.tab_layout.select_zvd_cal_btn.disabled = False
                self.on_select_calibration_btn_click('zvd') # Set ZVD as default shaper selection.
            finally:
                self.sts_axis_calibration_active = False
                self.update_tab_layout()
        else:
            try:
                client_ID = self._settings.get(["CLIENTID"])
                org_ID = self._settings.get(["ORG"])
                access_ID = self._settings.get(["ACCESSID"])
                machine_ID = self._settings.get(["MACHINEID"])
                machine_name = self._settings.get(["MACHINENAME"])
                model_ID = self._settings.get(["MODELID"])
                manufacturer_name = self._settings.get(["MANUFACTURER_NAME"])
                self.send_client_popup(type='info', title='Verifying Calibration', message='Please wait...')
                _, g_gui = autocal_service_guidata(self.fsm.axis, self.sweep_cfg, self.metadata, self.accelerometer, client_ID, access_ID, org_ID, machine_ID, machine_name, model_ID, manufacturer_name, self)

            except Exception as e:
                self.handle_calibration_service_exceptions(e)
                self.active_verification_result = None
            else:
                self.active_verification_result = g_gui
                if self.active_solution_axis == 'x':
                 self.x_calibration_sent_to_printer = True
                elif self.active_solution_axis == 'y':
                 self.y_calibration_sent_to_printer = True
                self.send_client_popup(type='success', title='Calibration Applied', message=('The calibration for the '+self.active_solution_axis.upper()+' axis was applied successfully.'))
                    
            finally:
                self.sts_axis_verification_active = False
                self.update_tab_layout()
        return

    
    def fsm_on_ANALYZE_during(self):
        self.fsm.state = AxisRespnsFSMStates.IDLE
        return


    def fsm_start(self, axis):
        self.fsm_reset()

        if axis in ['x', 'y']: self.fsm.axis = axis
        else: return

        self.fsm.state = AxisRespnsFSMStates.HOME

    
    def fsm_kill(self):
        self.sts_axis_calibration_active = False
        self.sts_axis_verification_active = False
        self.sts_acclrmtr_connected = False

        self.sts_acclrmtr_active = False
        self.fsm_reset()
        self.fsm.state = AxisRespnsFSMStates.IDLE
        self.fsm.state_prev = AxisRespnsFSMStates.NONE

        self.update_tab_layout()


    def get_settings_defaults(self):
        return dict(
                    CLIENTID=None,
                    ORG=None, 
                    ACCESSID=None, 
                    MACHINEID=None, 
                    MACHINENAME=None,
                    url="https://github.com/S2AUlendo/UlendoCaaS",
                    MODELID="TAZPro",
                    CONDITIONS="DEFAULT",
                    MANUFACTURER_NAME="ULENDO",
                    home_axis_before_calibration=True,
                    acceleration_amplitude=4000,
                    starting_frequency=5,
                    frequency_sweep_rate=4,
                    override_end_frequency=False,
                    end_frequency_override=80,
                    step_time=50,
                    step_acceleration=4000,
                    delay1_time=500,
                    delay2_time=1000,
                    delay3_time=1000
                    )

    def get_template_vars(self):
        return dict(ORG=self._settings.get(["ORG"]), 
                    ACCESSID=self._settings.get(["ACCESSID"]), 
                    MACHINEID=self._settings.get(["MACHINEID"]), 
                    url=self._settings.get(["url"]),
                    MODELID=self._settings.get(["MODELID"]),
                    MANUFACTURER_NAME=self._settings.get(["MANUFACTURER_NAME"]),
                    CONDITIONS=self._settings.get(["CONDITIONS"]),
                    home_axis_before_calibration=self._settings.get(["home_axis_before_calibration"]),
                    acceleration_amplitude=self._settings.get(["acceleration_amplitude"]),
                    starting_frequency=self._settings.get(["starting_frequency"]),
                    frequency_sweep_rate=self._settings.get(["frequency_sweep_rate"]),
                    override_end_frequency=self._settings.get(["override_end_frequency"]),
                    end_frequency_override=self._settings.get(["end_frequency_override"]),
                    step_time=self._settings.get(["step_time"]),
                    step_acceleration=self._settings.get(["step_acceleration"]),
                    delay1_time=self._settings.get(["delay1_time"]),
                    delay2_time=self._settings.get(["delay2_time"]),
                    delay3_time=self._settings.get(["delay3_time"])
)

    def get_template_configs(self):
        return [            
            dict(type="settings", custom_bindings=False)
        ]

# If you want your plugin to be registered within OctoPrint under a different name than what you defined in setup.py
# ("OctoPrint-PluginSkeleton"), you may define that here. Same goes for the other metadata derived from setup.py that
# can be overwritten via __plugin_xyz__ control properties. See the documentation for that.
__plugin_name__ = "Ulendo CaaS"


# Set the Python version your plugin is compatible with below. Recommended is Python 3 only for all new plugins.
# OctoPrint 1.4.0 - 1.7.x run under both Python 3 and the end-of-life Python 2.
# OctoPrint 1.8.0 onwards only supports Python 3.
__plugin_pythoncompat__ = ">=3,<4"  # Only Python 3

def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = UlendocaasPlugin()

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information,
        "octoprint.comm.protocol.gcode.received": __plugin_implementation__.proc_rx
    }
