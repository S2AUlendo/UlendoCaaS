from .tab_buttons import *

class TabLayout(): # Tab layout to use as singleton
    def __init__(self):
        # TODO: add notes about naming
        self.acclrmtr_connect_btn = AcclrmtrConnectButton()
        self.calibrate_x_axis_btn = CalibrateAxisButton()
        self.calibrate_y_axis_btn = CalibrateAxisButton()
        self.select_zv_cal_btn = CalibrationSelectionButton()
        self.select_zvd_cal_btn = CalibrationSelectionButton()
        self.select_mzv_cal_btn = CalibrationSelectionButton()
        self.select_ei_cal_btn = CalibrationSelectionButton()
        self.select_ei2h_cal_btn = CalibrationSelectionButton()
        self.select_ei3h_cal_btn = CalibrationSelectionButton()
        self.load_calibration_btn = LoadCalibrationButton()
        self.save_calibration_btn = SaveCalibrationButton()
        self.vtol_slider_visible = False
