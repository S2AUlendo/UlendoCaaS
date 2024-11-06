import subprocess
import threading
import pigpio
import time

from abc import ABC, abstractmethod
from enum import Enum


AcclrmtrRangeCfg = Enum('AcclrmtrRangeCfg', ['+/-2g', '+/-4g', '+/-8g', '+/-16g'])
AcclrmtrRateCfg = Enum('AcclrmtrRateCfg', ['3200Hz', '1600Hz', '800Hz', '400Hz', '200Hz'])


class AcclrmtrCfg():
    def __init__(self, range: AcclrmtrRangeCfg, rate: AcclrmtrRateCfg):
        self.range = range
        self.rate = rate
        self.poll_time = None # To be calibrateable by each implementer.


AcclrmtrStatus = Enum('AcclrmtrStatus', ['INIT', 'COLLECTING', 'CONNECTION_FAILED',
                                         'READ_FAILED', 'OVERRUN', 'OUT_OF_RANGE', 'STOPPED'])
AcclrmtrSelfTestSts = Enum('AcclrmtrSelfTestSts', ['PASS', 'FAIL'])


class Accelerometer(ABC):
    '''Abstract base class for an accelerometer that's sampled via polling.'''
    def __init__(self, config: AcclrmtrCfg):
        self.config = config
        self.status = AcclrmtrStatus.INIT
        self._stop = False


    def _refresh_collect_timer(self):
        if not self._stop: threading.Timer(self.config.poll_time, self._collect_samples).start()
        else: self.status = AcclrmtrStatus.STOPPED


    @abstractmethod
    def self_test(self): pass


    @abstractmethod
    def start(self):
        self._stop = False

        self.x_buff = []; self.y_buff = []; self.z_buff = []
        self._x_anim = 0.; self._y_anim = 0.; self._z_anim = 0.
        self.x_buff_anim = []; self.y_buff_anim = []; self.z_buff_anim = []; self.t_buff_anim = []
        self.samples_collected = 0
        self._samples_for_anim_idx = 0
    
        self.status = AcclrmtrStatus.COLLECTING
        threading.Timer(self.config.poll_time, self._collect_samples).start()


    @abstractmethod
    def _collect_samples(self):
        self._refresh_collect_timer()


    def stop(self):
        self._stop = True
        while self.status == AcclrmtrStatus.COLLECTING: time.sleep(self.config.poll_time)

    
    @abstractmethod
    def close(self): pass


class AcclerometerOverSPIError(Exception): pass
class DaemonNotRunning(AcclerometerOverSPIError): pass
class PigpioNotInstalled(AcclerometerOverSPIError): pass
class PigpioConnectionFailed(AcclerometerOverSPIError): pass
class SpiOpenFailed(AcclerometerOverSPIError): pass


class AcclerometerOverSPI(Accelerometer):
    def __init__(self, config: AcclrmtrCfg):
        try:
            subprocess.check_output(['service', 'pigpiod', 'status'])
        except subprocess.CalledProcessError as cpe:
            if cpe.returncode == 3:
                if b'Loaded: not-found' in cpe.stdout: raise PigpioNotInstalled
                else: raise DaemonNotRunning
            if cpe.returncode == 4: raise PigpioNotInstalled

        self._rpi = pigpio.pi()
        if not self._rpi.connected: raise PigpioConnectionFailed
            
        try:
            self._spi0 = self._rpi.spi_open(spi_channel=0, baud=4000000, spi_flags=3) # TODO: As SPI config.
        except: raise SpiOpenFailed

        super().__init__(config)


    def _spi0_read_bytes(self, addr, count):
        addr_ = addr | 0x80         # Set read bit
        if count > 1: addr_ |= 0x40 # Set multi bit
        (count, rx_data) = self._rpi.spi_xfer(self._spi0, [addr_] + [0xFF]*count)
        if count < 0: raise Exception
        else: return rx_data[1:]

    
    # Note: derived classes will still need to define the abstract
    # methods of the Accelerometer ABC even if they are not defined
    # here.

