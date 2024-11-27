# coding=utf-8

from __future__ import absolute_import

import subprocess
import requests
import platform
import struct
import numpy as np
import re

from math import pi, sqrt, floor, ceil, sin
from datetime import datetime

from octoprint.util import ResettableTimer
from octoprint.util.comm import regex_float_pattern, parse_position_line, regex_firmware_splitter
import octoprint.plugin

from .cfg import *
from .ismags import get_ismag
from .service_exceptions import *
from .service_abstraction import autocal_service_solve, autocal_service_guidata, verify_credentials, save_post_as_file, autocal_service_share, save_post_as_file, get_run_post_data

from .accelerometers.accelerometer_abc import AcclrmtrCfg, AcclrmtrRateCfg, AcclrmtrRangeCfg, AcclrmtrSelfTestSts, AcclrmtrStatus
from .accelerometers.accelerometer_abc import DaemonNotRunning, PigpioNotInstalled, PigpioConnectionFailed, SpiOpenFailed
from .accelerometers.accelerometer_sim import SimulatedAccelerometer
from .accelerometers.accelerometer_adxl345 import Adxl345

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
                         'ANALYZE_AUTO',
                         'ANALYZE_MANUAL'])


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
                    octoprint.plugin.StartupPlugin,
                    octoprint.plugin.BlueprintPlugin
):

    def __init__(self):
        self.initialized = False
        return
    

    def on_startup(self, *args, **kwargs):
        self._init()
    

    def _init(self):
        # Use this to init stuff dependent on the injected properties (including _logger)
        if self.initialized: return

        self.tab_layout = TabLayout()
        
        self.fsm = AxisRespnsFSMData()
        self.fsm.state = AxisRespnsFSMStates.IDLE
        
        self.accelerometer = None

        self.sts_self_test_active = False
        self.sts_acclrmtr_connected = False
        self.sts_acclrmtr_active = False
        self.sts_axis_calibration_active = False
        self.sts_axis_verification_active = False
        self.sts_axis_calibration_axis = None
        self.sts_calibration_saved = False
        self.sts_manual_mode_ready_for_user_selections = False
        self.sts_manual_calibration_data_ready_for_share = False
        self.sts_manual_calibration_data_shared = False
        self.active_solution = None
        self.active_solution_axis = None
        self.active_verification_result = None
        self.x_calibration_sent_to_printer = False
        self.y_calibration_sent_to_printer = False

        self.calibration_vtol = 0.05

        self.metadata = {}

        self.verify_credentials_and_update_tab_layout()
    
        if not SIMULATION:
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

            try:
                ip_link_out_as_str = subprocess.check_output(["ip", "link"]).decode()
                search_match = re.search(r'link/ether\s([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}', ip_link_out_as_str, re.M)
                match_split = re.split(r'\s', search_match.group(0))
                self.metadata['MACADDR'] = match_split[1]
            except:
                self.metadata['MACADDR'] = 'NA'
        else:
            self.metadata['BOARDCPUSERIAL'] = 'NA'
            self.metadata['BOARDMODEL'] = 'NA'
            self.metadata['MACADDR'] = 'XX:XX:XX:XX:XX:XX'

        self.initialized = True


    def send_printer_command(self, cmd):
        if SIMULATION:
            self._logger.info('In simulation: sending command to printer: ' + cmd)
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

        accelerometer_data_y = [0.]*ACCLRMTR_LIVE_VIEW_NUM_SAMPLES

        if self.sts_self_test_active:
            buffer_to_plot = self.accelerometer.z_buff_anim.copy()
        else:
            if self.fsm.axis == 'x': buffer_to_plot = self.accelerometer.x_buff_anim.copy()
            else: buffer_to_plot = self.accelerometer.y_buff_anim.copy() # Assume self.fsm.axis == 'y'.

        n = len(buffer_to_plot)
        if n < ACCLRMTR_LIVE_VIEW_NUM_SAMPLES:
            accelerometer_data_y[-n:] = buffer_to_plot
        else:
            accelerometer_data_y[:] = buffer_to_plot[-ACCLRMTR_LIVE_VIEW_NUM_SAMPLES:]

        accelerometer_data_x = list(range(ACCLRMTR_LIVE_VIEW_NUM_SAMPLES))
        accelerometer_data_x = [(self.accelerometer.T*self.accelerometer.downsample_factor)*(n + xi) for xi in accelerometer_data_x]
        
        data = dict(
            type='accelerometer_data',
            values_x=accelerometer_data_x,
            values_y=accelerometer_data_y,
            prompt_user=False
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
            damping_slider_visible = self.tab_layout.damping_slider_visible,
            vtol_slider_visible = self.tab_layout.vtol_slider_visible,
            is_active_client = self.tab_layout.is_active_client,
            enable_controls_by_data_share = self.tab_layout.enable_controls_by_data_share,
            mode = self.tab_layout.mode,
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
            self.tab_layout.damping_slider_visible = False
            self.tab_layout.vtol_slider_visible = False
        else:
            self.tab_layout.acclrmtr_connect_btn.disabled = False
            self.tab_layout.clear_session_btn.disabled = False

            if self.sts_acclrmtr_connected:
                self.tab_layout.calibrate_x_axis_btn.disabled = False
                self.tab_layout.calibrate_y_axis_btn.disabled = False

            enable_calibration_buttons = False
            if self.active_solution is not None:
                # Also verify wc is set (in manual mode, it is not set
                # until user selects a frequency for the first time).
                if self.active_solution.wc is not None: enable_calibration_buttons = True

            if enable_calibration_buttons:
                for calibration_key in calibration_keys:
                    calibration_btn = getattr(self.tab_layout, 'select_' + calibration_key + '_cal_btn')
                    calibration_btn.disabled = False
            else:
                for calibration_key in calibration_keys:
                    calibration_btn = getattr(self.tab_layout, 'select_' + calibration_key + '_cal_btn')
                    calibration_btn.state = CalibrationSelectionButtonStates.NOTSELECTED
                    calibration_btn.disabled = True

            self.tab_layout.damping_slider_visible = False
            if self.sts_manual_mode_ready_for_user_selections:
                if self.active_solution is not None:
                    if self.active_solution.wc is not None:
                        self.tab_layout.damping_slider_visible = True

            self.tab_layout.vtol_slider_visible = False
            if self.get_selected_calibration_type() in ['ei', 'ei2h', 'ei3h']:
                if (self.active_solution_axis == 'x' and not self.x_calibration_sent_to_printer) or \
                (self.active_solution_axis == 'y' and not self.y_calibration_sent_to_printer):
                    self.tab_layout.vtol_slider_visible = True

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

        self.tab_layout.enable_controls_by_data_share = self.sts_manual_calibration_data_shared

        # Mode
        self.tab_layout.mode = 'auto' if self._settings.get(["use_caas_service"]) else 'manual'
        
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


    def send_client_close_popups(self):
        data = dict(
            type='close_popups'
        )
        self._plugin_manager.send_plugin_message(self._identifier, data)


    def fsm_update(self):
        if self._settings.get(["log_routine_debug_info"]): self._logger.info(f'FSM update: {self.fsm.state}.')

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
        elif self.fsm.state == AxisRespnsFSMStates.ANALYZE_AUTO:
            if self.fsm.state_prev != AxisRespnsFSMStates.ANALYZE_AUTO:
                self.fsm_on_ANALYZE_AUTO_entry()
            else:
                self.fsm_on_ANALYZE_AUTO_during(); return
        elif self.fsm.state == AxisRespnsFSMStates.ANALYZE_MANUAL:
            if self.fsm.state_prev != AxisRespnsFSMStates.ANALYZE_MANUAL:
                self.fsm_on_ANALYZE_MANUAL_entry()
            else:
                self.fsm_on_ANALYZE_MANUAL_during(); return
        
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
        # Get selected calibration type.
        type = self.get_selected_calibration_type()
        if type is None:
            self._logger.error("Can't send result without a calibration selected!")
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
                except: pass # We'll ignore a fail here, since it could be
                             # due to the pigpio daemon no longer running.
            self.acclerometer_cfg = AcclrmtrCfg(range=AcclrmtrRangeCfg[self._settings.get(["accelerometer_range"])],
                                                rate=AcclrmtrRateCfg[self._settings.get(["accelerometer_rate"])])
            
            if SIMULATION: self.accelerometer = SimulatedAccelerometer(self.acclerometer_cfg)
            else: self.accelerometer = Adxl345(self.acclerometer_cfg) # FUTURE: Use self._settings.get(["accelerometer_device"])
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
            if platform.system() == "Windows":
                self.send_client_popup(type='error', title='Windows is not currently supported.',
                                    message=f"The accelerometer hasn't been connected"\
                                    " because an accelerometer compatible with Windows"\
                                    " is not currently supported.", hide=False)
            else: self.send_client_popup(type='error', title='Accelerometer Startup Failed',
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
        
        if self.accelerometer is None: self.update_tab_layout(); return
        
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
            
            self.sts_manual_mode_ready_for_user_selections = False
            self.sts_manual_calibration_data_ready_for_share = False
            self.sts_manual_calibration_data_shared = False

            self.update_tab_layout()
            self.send_client_clear_calibration_result()
            self.send_client_clear_verification_result()

            self._logger.info(f'Calibration started on axis: {axis}')
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
            self.send_client_calibration_result(type, reset_sliders=True)
        self.update_tab_layout()


    def send_client_calibration_result(self, type, reset_sliders=False):
        ismag = get_ismag(self.active_solution.w_bp, type, self.active_solution.wc, self.active_solution.zt, vtol=self.calibration_vtol)
        data = dict(
            type = 'calibration_result',
            istype = type, # TODO: Confusing.
            w_bp = (self.active_solution.w_bp / 2. / pi).tolist(),
            G = self.active_solution.G.tolist(),
            compensator_mag = ismag.tolist(),
            new_mag = (self.active_solution.G * ismag).tolist(),
            axis = self.active_solution_axis,
            reset_sliders = reset_sliders
        )
        self._plugin_manager.send_plugin_message(self._identifier, data)

    
    def on_load_calibration_btn_click(self):
        if self.tab_layout.load_calibration_btn.disabled: return

        type = self.get_selected_calibration_type()

        if not SIMULATION:
            connection_string, _, _, _ = self._printer.get_current_connection()

            if(connection_string != "Operational"):
                self.send_client_popup(type='error', title='Printer not connected.', message='Printer must be connected in order to download calibration.')
                return
        
        if type is None or self.fsm.state is not AxisRespnsFSMStates.IDLE:
            self._logger.error(f'Calibration load command conditions not correct.')
            return
        
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

        self._logger.info(f'Configuring printer with: {printer_configuration_command}')
        self.send_client_logger_info('Sent printer: ' + printer_configuration_command \
                                        + ' (Set the ' + self.active_solution_axis.upper() + ' axis to use ' + type.upper() \
                                        + f' shaping @ {self.active_solution.wc/2./pi:0.2f}Hz & ζ = {self.active_solution.zt:0.4f}' \
                                        + (f' & vtol = {self.calibration_vtol:0.2f}).' if ei_type else ').') )
        self.send_printer_command(printer_configuration_command)

        self.sts_calibration_saved = False

        self.sts_axis_verification_active = True
        self.sts_manual_mode_ready_for_user_selections = False
        self.sts_manual_calibration_data_ready_for_share = False
        self.sts_manual_calibration_data_shared = False
        self._logger.info(f'Verification started on axis: {self.active_solution_axis}.')
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


    def on_damping_slider_update(self, val):
        self.active_solution.zt = min(0.9999, max(0.0001, float(val)/1000))
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
        self.sts_manual_mode_ready_for_user_selections = False
        self.sts_manual_calibration_data_ready_for_share = False
        self.sts_manual_calibration_data_shared = False
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


    def on_accelerometer_data_plot_click(self, xval):
        if not self.sts_manual_mode_ready_for_user_selections: return

        f = self.i2f_bm[0] + self.i2f_bm[1]*xval/self.accelerometer.T

        self._logger.info(f'User selected frequency of {f:.1f} Hz on graph.')

        is_first_freq_selection = self.active_solution.wc is None # Infer this is the first selection on this calibration run.

        self.active_solution.wc = f*2.*pi
        self.active_solution.zt = 0.1

        if is_first_freq_selection:
            self.tab_layout.select_zvd_cal_btn.disabled = False
            self.on_select_calibration_btn_click('zvd') # Set ZVD as default shaper selection.
            self.send_client_close_popups()
        
        if self.active_solution_axis == 'x': self.x_calibration_sent_to_printer = False
        elif self.active_solution_axis == 'y': self.y_calibration_sent_to_printer = False
        self.sts_calibration_saved = False
        self.send_client_clear_verification_result()
        self.send_client_calibration_result(self.get_selected_calibration_type())
        
        self.update_tab_layout()


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
            damping_slider_update=['val'],
            vtol_slider_update=['val'],
            get_connection_status=[],
            start_over_btn_click=[],
            clear_session_btn_click=[],
            prompt_cancel_click=[],
            prompt_proceed_click=[],
            on_settings_close=[],
            on_accelerometer_data_plot_click=['xval']
        )

    
    def on_api_command(self, command, data):
        if not self.initialized:
            self._logger.info(f'Ignored command "{command}" because not yet initialized.')
            return
        if command == 'get_layout_status': self.send_client_layout_status()
        elif command == 'acclrmtr_connect_btn_click': self.on_acclrmtr_connect_btn_click()
        elif command == 'calibrate_axis_btn_click': self.on_calibrate_axis_btn_click(data['axis'])
        elif command == 'select_calibration_btn_click': self.on_select_calibration_btn_click(data['type'])
        elif command == 'load_calibration_btn_click': self.on_load_calibration_btn_click()
        elif command == 'save_calibration_btn_click': self.on_save_calibration_btn_click()
        elif command == 'damping_slider_update': self.on_damping_slider_update(data['val'])
        elif command == 'vtol_slider_update': self.on_vtol_slider_update(data['val'])
        elif command == 'get_connection_status': self.report_connection_status()
        elif command == 'clear_session_btn_click': self.on_clear_session_btn_click()
        elif command == 'prompt_cancel_click': self.on_prompt_cancel_click()
        elif command == 'prompt_proceed_click': self.on_prompt_proceed_click()
        elif command == 'on_settings_close': self.on_settings_close()
        elif command == 'on_accelerometer_data_plot_click': self.on_accelerometer_data_plot_click(data['xval'])


    def verify_credentials_and_update_tab_layout(self):
        try:
            check_status = verify_credentials(self._settings.get(["ORG"]),
                                              self._settings.get(["ACCESSID"]),
                                              self._settings.get(["MACHINEID"]),
                                              self._logger)
        except Exception as e:
            self.handle_calibration_service_exceptions(e)
            check_status = False
        self.tab_layout.is_active_client = check_status
        self.update_tab_layout()


    def check_accelerometer_settings_changed(self):
        if self.accelerometer is not None:
            if (self.acclerometer_cfg.range != AcclrmtrRangeCfg[self._settings.get(["accelerometer_range"])]
                or
                self.acclerometer_cfg.rate != AcclrmtrRateCfg[self._settings.get(["accelerometer_rate"])]):
                self.sts_acclrmtr_connected = False
                self.accelerometer = None
                self.update_tab_layout()
            

    def on_settings_close(self):
        self.verify_credentials_and_update_tab_layout()
        self.check_accelerometer_settings_changed()

        if (not self.sts_manual_calibration_data_shared
            and self._settings.get(["share_calibration_data"])
            and self.sts_manual_calibration_data_ready_for_share):
            self.send_client_popup(type='info', title='Sharing Data', message='Sharing data, please wait...')
            self.share_calibration_data()
            self.update_tab_layout()


    
    ##~~ Hooks
    def proc_rx(self, comm_instance, line, *args, **kwargs):
        if not self.initialized:
            self._logger.error(f'Ignored line from printer "{line}" because not yet initialized.')
            return line
        try:
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
                    if self._settings.get(["log_routine_debug_info"]): self._logger.info('Metadata updated (received FTMCFG):'); self._logger.info(self.metadata)
                elif 'profile ran to completion' in line:
                    if self.fsm.state == AxisRespnsFSMStates.SWEEP:
                        self.fsm.sweep_done_recvd = True
                        if self._settings.get(["log_routine_debug_info"]): self._logger.info(f'Got sweep done message.')

            elif self.fsm.state == AxisRespnsFSMStates.CENTER and (self.fsm.axis.upper() + ':') in line:
                self.fsm.axis_last_reported_pos = parse_position_line(line)[self.fsm.axis]
                if self._settings.get(["log_routine_debug_info"]): self._logger.info(f'Got reported position = {self.fsm.axis_last_reported_pos}.')
            elif 'NAME:' in line or line.startswith('NAME.'):
                split_line = regex_firmware_splitter.split(line.strip())[
                    1:
                ]  # first entry is empty start of trimmed string
                result = {}
                for _, key, value in chunks(split_line, 3):
                        result[key] = value.strip()
                if result.get('FIRMWARE_NAME') is not None:
                    self.metadata['FIRMWARE'] = result
                    if self._settings.get(["log_routine_debug_info"]): self._logger.info('Metadata updated (received firmware name):'); self._logger.info(self.metadata)
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
                    if self._settings.get(["log_routine_debug_info"]): self._logger.info('Metadata updated (received M92):'); self._logger.info(self.metadata)
            elif self.fsm.state == AxisRespnsFSMStates.CENTER and 'echo:Home' in line and 'First' in line:
                split_line_0 = re.split(r"echo:Home ", line.strip())
                split_line_1 = re.split(r" First", split_line_0[1].strip())
                self.fsm.printer_requires_additional_homing = True
                self.fsm.printer_additional_homing_axes = split_line_1[0]

            return line
        except Exception as e:
            self._logger.error(f"An error occurred processing the line received by the printer: {str(e)}")
            return line


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
                                    f'ter {SERVICE_TIMEOUT_THD} seconds.', hide=False)
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
            if self._settings.get(["use_caas_service"]):
                self.send_client_popup(type='error', title='Not authenticated.',
                                        message='Unable to verify plugin credentials. Please'\
                                        ' verify your plugin configuration.', hide=False)
            else:
                self.send_client_popup(type='info', title='Not authenticated.',
                                        message='Unable to verify plugin credentials. Only manual'\
                                        ' features will be available.')
        except MachineIDNotFound:
            self.send_client_popup(type='error', title='Machine ID not found.',
                                    message='The machine ID provided in settings is'\
                                    ' not found in our server.', hide=False)
        except PictureUploadError:
            self.send_client_popup(type='error', title='Feedback Upload Error.',
                                    message='There is a problem uploading your feedback'\
                                        ' to the server.', hide=False)
        except Exception:
            self.send_client_popup(type='error', title='Unknown error.',
                                    message=str(e), hide=False)


    def share_calibration_data(self, show_errors=True):
            try:
                if self.sts_axis_verification_active:
                    autocal_service_share(self._plugin_version, self.fsm.axis, self.sts_axis_verification_active, self.accelerometer, self.sweep_cfg, self.metadata, self._settings, self._logger, self.get_selected_calibration_type(), self.active_solution.wc, self.active_solution.zt, self.calibration_vtol)
                else:
                    autocal_service_share(self._plugin_version, self.fsm.axis, self.sts_axis_verification_active, self.accelerometer, self.sweep_cfg, self.metadata, self._settings, self._logger)
            except requests.exceptions.ConnectionError:
                if show_errors: self.send_client_popup( type='info', title='Sharing Data Failed',
                                                        message=f'Sharing the calibration data failed because the service' \
                                                                ' is unreachable. If you are connected to the internet,' \
                                                                ' please try again later.', hide=False)
            except Exception as e:
                if show_errors: self.send_client_popup( type='info', title='Sharing Data Failed',
                                                        message=f'Sharing the calibration data failed: {str(e)}.', hide=False)
            else:
                self.sts_manual_calibration_data_shared = True


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
        if self._settings.get(["log_routine_debug_info"]): self._logger.info(f'on_CENTER vars: {self.fsm.axis_last_reported_pos}, {self.fsm.axis_reported_len}, {self.fsm.axis_centering_wait_time}.')
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

        if SIMULATION: self.fsm.axis_reported_steps_per_mm = 80
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

        if SIMULATION:
            self.accelerometer.set_simulation_params(self.sweep_cfg.f0, self.sweep_cfg.f1, self.sweep_cfg.dfdt,
                                                     self.sweep_cfg.a, self.sweep_cfg.step_ti/1000., self.sweep_cfg.step_a,
                                                     self.sweep_cfg.dly1_ti/1000., self.sweep_cfg.dly2_ti/1000., self.sweep_cfg.dly3_ti/1000.)
        
        self.accelerometer.start()
        self.sts_acclrmtr_active = True
        self.send_client_acclrmtr_data_TMR = ResettableTimer(ACCLRMTR_LIVE_VIEW_RATE_SEC, self.send_client_acclrmtr_data)
        self.send_client_acclrmtr_data_TMR.start()
        

    def fsm_on_SWEEP_during(self):
        
        if self.fsm.in_state_time > FSM_SWEEP_START_DLY and not self.fsm.sweep_initiated:
            if not SIMULATION:
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

        if SIMULATION:
            stop_accelerometer = self.accelerometer.simulation_done()
        else:
            stop_accelerometer = self.fsm.sweep_done_recvd

        if stop_accelerometer and not self.fsm.accelerometer_stopped:
            self.accelerometer.stop()
            if self._settings.get(["log_routine_debug_info"]): self._logger.info('Triggering accelerometer data collection stop.')
            self.fsm.accelerometer_stopped = True

        if self.accelerometer.status != AcclrmtrStatus.COLLECTING:
            f_abort = False
            if self.accelerometer.status == AcclrmtrStatus.STOPPED:
                self.sts_acclrmtr_active = False
                if (self._settings.get(["use_caas_service"])): self.fsm.state = AxisRespnsFSMStates.ANALYZE_AUTO
                else: self.fsm.state = AxisRespnsFSMStates.ANALYZE_MANUAL
            elif self.accelerometer.status == AcclrmtrStatus.OVERRUN:
                if self.fsm.missed_sample_retry_count < MAX_RETRIES_FOR_MISSED_SAMPLES: # Setup a retry
                    self.fsm.missed_sample_retry_count += 1

                    self.send_printer_command('M494 A99')
                    
                    self.send_client_popup(type='info', title='Retrying', message='Some accelerometer data was lost, the routine will be retried.')
                    
                    self.fsm_reset(reset_for_retry=True)
                    self.sts_acclrmtr_active = False
                    self.fsm.state = AxisRespnsFSMStates.HOME

                else:  # Max retries hit.
                    self.send_client_popup(type='error', title='Retry Limit', message='Retry limit reached, exiting this attempt.')
                    f_abort = True
            else:
                self.send_client_popup(type='error', title='Accelerometer Connection Lost', message=f'Accelerometer connection was lost during the routine (error code: {self.accelerometer.status.value}).')
                f_abort = True
                
            if f_abort:
                self.send_printer_command('M494 A99')
                self.fsm_kill()

        return


    def fsm_on_ANALYZE_AUTO_entry(self):
        
        self.fsm.missed_sample_retry_count = 0

        if not self.sts_axis_verification_active:
            try:
                self.send_client_popup(type='info', title='Processing Data', message='Processing data, please wait...')
                wc, zt, w_gui_bp, G_gui = autocal_service_solve(self._plugin_version, self.fsm.axis, self.accelerometer, self.sweep_cfg, self.metadata, self._settings)
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
                self.send_client_popup(type='info', title='Verifying Calibration', message='Please wait...')
                _, g_gui = autocal_service_guidata(self._plugin_version, self.fsm.axis, self.accelerometer, self.sweep_cfg, self.metadata, self._settings)

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

    
    def fsm_on_ANALYZE_AUTO_during(self):
        self.fsm.state = AxisRespnsFSMStates.IDLE
        return


    def fsm_on_ANALYZE_MANUAL_error(self):
        self.fsm.state = AxisRespnsFSMStates.IDLE
        self.active_solution = None
        self.sts_axis_calibration_active = False
        self.sts_axis_verification_active = False
        self.update_tab_layout()


    def fsm_on_ANALYZE_MANUAL_entry(self):
   
        self.sts_manual_calibration_data_ready_for_share = True

        # Share the data if selected.
        if self._settings.get(["share_calibration_data"]): self.share_calibration_data(show_errors=(not self.sts_axis_verification_active))
        else:
            self.send_client_popup( type='info', title='Data Was Not Shared',
                                    message='The calibration data for this run was not shared. To share,'\
                                            ' enable the associated option in the plugin\'s settings.',
                                    hide=False)

        # Following logic is known to fail for data rates below 400 Hz, so perform a check.
        if self.accelerometer.T > (1/300.):
            self.send_client_popup(type='error', title='Accelerometer sample rate too low.',
                                    message='Accelerometer sample rate too low to perform analysis.'\
                                            ' Try setting the rate higher in the plugin\'s settings.', hide=False)
            self.fsm_on_ANALYZE_MANUAL_error(); return

        self.fsm.missed_sample_retry_count = 0

        # Select axis data and trim.
        data = self.accelerometer.x_buff if self.fsm.axis == 'x' else self.accelerometer.y_buff
        data = np.array(data)
        
        n_0_ = round(LOC_DLY2_TI/self.accelerometer.T)
        m_0_ = round(self.sweep_cfg.dly2_ti/1000./self.accelerometer.T)
        o_0_ = round(self.sweep_cfg.dly1_ti/1000./self.accelerometer.T)

        n_1_ = round(LOC_DLY3_TI/self.accelerometer.T)
        m_1_ = round(self.sweep_cfg.dly3_ti/1000./self.accelerometer.T)

        if len(data) < (o_0_ + n_0_ + m_0_ + n_1_ + m_1_):
            self.send_client_popup(type='error', title='Data length error 1.',
                                    message='Insufficient data collected. Try adjusting the calibration'
                                            ' profile in the plugin\'s settings.', hide=False)
            self.fsm_on_ANALYZE_MANUAL_error(); return

        data -= np.sum(data)/len(data)

        minima_ = np.zeros((n_0_,))
        for i in range(n_0_): minima_[i] = np.sum(np.abs(data[o_0_+i:o_0_+i+m_0_]))
        dly1_idx = o_0_ + np.max(np.argmin(minima_))

        minima_ = np.zeros((n_1_,))
        for i in range(n_1_): minima_[i] = np.sum(np.abs(data[-n_1_-m_1_+i:-n_1_+i]))
        dly2_idx = len(data) - n_1_ - m_1_ + np.min(np.argmin(minima_))
        
        data = data[dly1_idx+m_0_:dly2_idx]

        if not self.sts_axis_verification_active:
            # Gross check.
            weak_signal_check_n = round(WEAK_SIGNAL_CHECK_TI/self.accelerometer.T)

            if len(data) < weak_signal_check_n:
                self.send_client_popup(type='error', title='Data length error 2.',
                                        message='Insufficient data collected. Try adjusting the calibration'
                                                ' profile in the plugin\'s settings.', hide=False)
                self.fsm_on_ANALYZE_MANUAL_error(); return

            k1 = pi*self.sweep_cfg.dfdt
            k2 = 2.*pi*self.sweep_cfg.f0
            weak_signal_accum_meas = 0.
            weak_signal_accum_expctd = 0.
            for i in range(weak_signal_check_n):
                tau = i*self.accelerometer.T
                weak_signal_accum_expctd += abs(-self.sweep_cfg.a*sin(k1*tau*tau + k2*tau))
                weak_signal_accum_meas += abs(data[i])

            self._logger.info(f'Weak signal check stats: {weak_signal_accum_meas:.1f}/{weak_signal_accum_expctd:.1f} = {weak_signal_accum_meas/weak_signal_accum_expctd:.2f}.')

            if weak_signal_accum_meas/weak_signal_accum_expctd < WEAK_SIGNAL_CHECK_THD:
                self.send_client_popup(type='error', title='Weak signal detected.',
                                        message='Could not calibrate due to a weak signal. Is '\
                                        'the accelerometer mounted on the correct axis and in '\
                                        'the correct orientation?', hide=False)
                self.fsm_on_ANALYZE_MANUAL_error(); return

            # Compute magnitude for the plot.
            Y = np.fft.fft(data)
            NT = len(Y)*self.accelerometer.T
            f = np.arange(len(Y))/NT
            Y = Y/(len(data)/2)

            f0_idx = ceil(self.sweep_cfg.f0*NT)
            f1_idx = floor(self.sweep_cfg.f1*NT)

            mag = np.abs(Y)*(self.sweep_cfg.f1-self.sweep_cfg.f0)/self.sweep_cfg.a/sqrt(self.sweep_cfg.dfdt)

            f = f[f0_idx:f1_idx]; mag = mag[f0_idx:f1_idx]

            # Filter the data for a nicer plot.
            kbp1s = np.arange(start=0, stop=0.4, step=((max(f) - min(f)) / (len(f) - 1)))
            n = len(kbp1s)
            k_bp = np.concatenate((np.flip(kbp1s)[:-1], kbp1s))
            del kbp1s
            w = k_bp/(sum(k_bp))

            mag_fild = []
            for i in range(n-1, len(f) - n): mag_fild.append(np.dot(w, mag[i-n+1 : i+n]))
            f = f[n-1:-n]

            f_bp = f.copy()
            self.active_solution = InpShprSolution(wc=None, zt=None, w_bp=f*2.*pi, G=np.array(mag_fild))
            self.active_solution_axis = self.fsm.axis
            del f, Y, NT, n

            # Compute the frequency versus index parameters.
            try:
                wl = self.sweep_cfg.dfdt/4.; wo = 0.66
                ws = wl*(1.-wo)
                wN = round(wl/self.accelerometer.T)
                sN = round(ws/self.accelerometer.T)

                H = np.arange(start=0, stop=wN, step=1)
                H = 0.5*(1. - np.cos(2.*pi*H/wN))

                ns = []; fs = []

                for i in range(floor((len(data) - wN)/sN) + 1):
                    sidx = sN*i
                    eidx = sidx + wN

                    y_ = H*data[sidx:eidx]
                    Y_ = np.fft.fft(np.array(y_))
                    NT = len(Y_)*self.accelerometer.T
                    f_ = np.arange(len(Y_))/NT

                    minf_idx = ceil(self.sweep_cfg.f0*NT)
                    maxf_idx = floor(self.sweep_cfg.f1*NT)

                    f_ = f_[minf_idx:maxf_idx]; Y_ = Y_[minf_idx:maxf_idx]

                    fs.append(f_[np.min(np.argmax(np.abs(Y_)))])
                    ns.append(round(sidx+eidx)/2)

                ns = np.array(ns, dtype=float)
                fs = np.array(fs)

                max_ns = max(ns)
                ns /= max_ns
                fs /= self.sweep_cfg.f1

                w = np.clip(np.interp(fs*self.sweep_cfg.f1, f_bp, mag_fild), a_min=None, a_max=1.)

                w = np.pow(w, SIGNAL_WEIGHTING_POWER)

                rng = np.random.default_rng()
                e = np.inf
                self.i2f_bm = None
                for _ in range(I2F_MAX_ITERATIONS):
                    idcs1 = rng.permutation(len(ns))
                    hi = idcs1[:I2F_RANDOM_IDCS]
                    X = np.block([np.ones((I2F_RANDOM_IDCS, 1)), ns[hi].reshape(-1, 1)])
                    W = np.diag(w[hi])
                    bm_ = np.linalg.inv(X.T @ W @ X) @ X.T @ W @ fs[hi]
                    ytil = np.block([np.ones((len(idcs1), 1)), ns[idcs1].reshape(-1, 1)]) @ bm_
                    e_ = (fs[idcs1] - ytil)**2
                    idcs2 = idcs1[I2F_RANDOM_IDCS:][np.where(e_[I2F_RANDOM_IDCS:] < I2F_CANDIDATE_ERROR_THD)]
                    if len(idcs2) > I2F_CONSENSUS_THD:
                        idcs = np.block([hi, idcs2])
                        X_ = np.block([np.ones((len(idcs), 1)), ns[idcs].reshape(-1, 1)])
                        W = np.diag(w[idcs])
                        bm__ = np.linalg.inv(X_.T @ W @ X_) @ X_.T @ W @ fs[idcs]
                        ytil_ = np.block([np.ones((len(idcs), 1)), ns[idcs].reshape(-1, 1)]) @ bm__
                        e__ = np.sum((fs[idcs] - ytil_)**2)/len(idcs)
                        if e__ < e: e = e__; self.i2f_bm = bm__

                self.i2f_bm[0] *= self.sweep_cfg.f1
                self.i2f_bm[1] *= self.sweep_cfg.f1/max_ns

                bm1_expected = self.sweep_cfg.dfdt*self.accelerometer.T
                bm1_ratio = self.i2f_bm[1]/bm1_expected
                self._logger.info(f'Frequency map result: {self.i2f_bm[0]:.3f};{self.i2f_bm[1]:.9f};{bm1_expected:.9f}; ratio={bm1_ratio:.3f}.')

                if bm1_ratio < I2F_BM1_RATIO_LOW_THD or bm1_ratio > I2F_BM1_RATIO_HIGH_THD:
                    self.send_client_popup(type='error', title='Error in frequency analysis.',
                                            message='The mapping cross check failed. Please try again.', hide=False)
                    self.fsm_on_ANALYZE_MANUAL_error(); return
                
            except Exception as e:
                self.send_client_popup(type='error', title='Error in frequency analysis.', message='Please try again using the default profile settings.', hide=False)
                self.fsm_on_ANALYZE_MANUAL_error(); return
            
            self.sts_axis_calibration_active = False
            self.sts_manual_mode_ready_for_user_selections = True
            
            self.send_client_popup( type='info', title='Select Peak Acceleration',
                                    message='To proceed, select the peak acceleration point on the'\
                                            ' data graph.',
                                    hide=False)
            
            prompt_user = True

        else: # Verification actions.
            if self.active_solution_axis == 'x': self.x_calibration_sent_to_printer = True
            elif self.active_solution_axis == 'y': self.y_calibration_sent_to_printer = True
            self.send_client_popup(type='success', title='Calibration Applied', message=('The calibration for the '+self.active_solution_axis.upper()+' axis was applied successfully.'))
            self.sts_axis_verification_active = False

            prompt_user = False

        # Common actions to calibration and verification.

        # Put the accelerometer data on the graph.
        accelerometer_data_x = list(range(len(data)))
        accelerometer_data_x = [self.accelerometer.T*xi for xi in accelerometer_data_x]
        
        data = dict(
            type='accelerometer_data',
            values_x=accelerometer_data_x,
            values_y=data.tolist(),
            prompt_user=prompt_user
        )

        self._plugin_manager.send_plugin_message(self._identifier, data)

        # Re-enable page controls.
        self.update_tab_layout()

        return

    
    def fsm_on_ANALYZE_MANUAL_during(self):
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
                    MODELID="MODELID",
                    CONDITIONS="DEFAULT",
                    MANUFACTURER_NAME="MANUFACTURERNAME",
                    use_caas_service=False,
                    accelerometer_device='ADXL345',
                    accelerometer_range='+/-2g',
                    accelerometer_rate='800Hz',
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
                    delay3_time=1000,
                    share_calibration_data=True,
                    log_routine_debug_info=False,
                    save_post_data_locally=False
                    )

    def get_template_vars(self):
        return dict(ORG=self._settings.get(["ORG"]),
                    ACCESSID=self._settings.get(["ACCESSID"]),
                    MACHINEID=self._settings.get(["MACHINEID"]),
                    url=self._settings.get(["url"]),
                    MODELID=self._settings.get(["MODELID"]),
                    MANUFACTURER_NAME=self._settings.get(["MANUFACTURER_NAME"]),
                    CONDITIONS=self._settings.get(["CONDITIONS"]),
                    use_caas_service=self._settings.get(["use_caas_service"]),
                    accelerometer_device=self._settings.get(["accelerometer_device"]),
                    accelerometer_range=self._settings.get(["accelerometer_range"]),
                    accelerometer_rate=self._settings.get(["accelerometer_rate"]),
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
                    delay3_time=self._settings.get(["delay3_time"]),
                    share_calibration_data=self._settings.get(["share_calibration_data"]),
                    log_routine_debug_info=self._settings.get(["log_routine_debug_info"]),
                    save_post_data_locally=self._settings.get(["save_post_data_locally"])
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
