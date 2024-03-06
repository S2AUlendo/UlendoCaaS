from enum import Enum


class ClickableButton():
    def __init__(self):
        self.disabled = True


AcclrmtrConnectButtonStates = Enum('AcclrmtrConnectButtonStates',
                                   ['NOTCONNECTED', 'CONNECTING', 'CONNECTED'])
class AcclrmtrConnectButton(ClickableButton):
    def __init__(self):
        super().__init__()
        self.disabled = False
        self.state = AcclrmtrConnectButtonStates.NOTCONNECTED


CalibrateAxisButtonStates = Enum('CalibrateAxisButtonStates',
                           ['NOTCALIBRATED', 'CALIBRATING', 'CALIBRATIONREADY', 'CALIBRATIONAPPLIED'])
class CalibrateAxisButton(ClickableButton):
    def __init__(self):
        super().__init__()
        self.state = CalibrateAxisButtonStates.NOTCALIBRATED


CalibrationSelectionButtonStates = Enum('CalibrationSelectionButtonStates',
                           ['NOTSELECTED', 'SELECTED'])
class CalibrationSelectionButton(ClickableButton):
    def __init__(self):
        super().__init__()
        self.state = CalibrationSelectionButtonStates.NOTSELECTED


LoadCalibrationButtonStates = Enum('LoadCalibrationButtonStates',
                           ['NOTLOADED', 'LOADING', 'LOADED'])
class LoadCalibrationButton(ClickableButton):
    def __init__(self):
        super().__init__()
        self.state = LoadCalibrationButtonStates.NOTLOADED


SaveCalibrationButtonStates = Enum('SaveCalibrationButtonStates',
                           ['NOTSAVED', 'SAVED'])
class SaveCalibrationButton(ClickableButton):
    def __init__(self):
        super().__init__()
        self.state = SaveCalibrationButtonStates.NOTSAVED


class ClearSessionButton(ClickableButton):
    def __init__(self):
        super().__init__()