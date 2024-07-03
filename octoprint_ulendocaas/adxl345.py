import subprocess
import threading
import pigpio
import time

from enum import Enum


## Configurations
POLL_TI_SEC = 0.001
READ_CONTINUE_THD = 5
FIFO_ACQ_TIMOUT_TI = 0.5
ACCLRMTR_LIVE_VIEW_DOWNSAMPLE_FACTOR = 24
FIFO_ACQ_TIMEOUT_THD = 25


class Adxl345Error(Exception): pass
class DaemonNotRunning(Adxl345Error): pass
class PigpioNotInstalled(Adxl345Error): pass
class PigpioConnectionFailed(Adxl345Error): pass
class SpiOpenFailed(Adxl345Error): pass

AcclrmtrRangeCfg = Enum('AcclrmtrRangeCfg', ['+/-2g', '+/-4g', '+/-8g', '+/-16g'])
AcclrmtrStatus = Enum('AcclrmtrStatus', ['INIT', 'COLLECTING', 'CONNECTION_FAILED',
                                         'READ_FAILED', 'OVERRUN', 'OUT_OF_RANGE', 'STOPPED'])
AcclrmtrSelfTestSts = Enum('AcclrmtrSelfTestSts', ['PASS', 'FAIL'])


class Adxl345:
    def __init__(self, range: AcclrmtrRangeCfg):
        try:
            subprocess.check_output(['service', 'pigpiod', 'status'])
        except subprocess.CalledProcessError as cpe:
            if cpe.returncode == 3:
                if b'Loaded: not-found' in cpe.stdout: raise PigpioNotInstalled
                else: raise DaemonNotRunning
            if cpe.returncode == 4: raise PigpioNotInstalled

        self.rpi = pigpio.pi()
        if not self.rpi.connected: raise PigpioConnectionFailed
            
        try:
            self.spi0 = self.rpi.spi_open(spi_channel=0, baud=4000000, spi_flags=3)
        except: raise SpiOpenFailed

        self.range = range
        if range == AcclrmtrRangeCfg['+/-2g']: self.lsb_to_mm_per_sec_sqr = 2.*2./1024.*9806.65
        elif range == AcclrmtrRangeCfg['+/-4g']: self.lsb_to_mm_per_sec_sqr = 2.*4./1024.*9806.65
        elif range == AcclrmtrRangeCfg['+/-8g']: self.lsb_to_mm_per_sec_sqr = 2.*8./1024.*9806.65
        else: self.lsb_to_mm_per_sec_sqr = 2.*16./1024.*9806.65 # +/- 16 g range.
        self.status = AcclrmtrStatus.INIT
        self._stop = False


    def close(self): self.rpi.spi_close(self.spi0)


    def spi0_read_bytes(self, addr, count):
        addr_ = addr | 0x80         # Set read bit
        if count > 1: addr_ |= 0x40 # Set multi bit
        (count, rx_data) = self.rpi.spi_xfer(self.spi0, [addr_] + [0xFF]*count)
        if count < 0: raise Exception
        else: return rx_data[1:]
    

    def cnfgr_for_data_acq(self):
        '''Writes the device registers to set it up for data acquisition.'''
        self.rpi.spi_write(self.spi0, [0x2C, 0b00001110]) # Data rate register; 1600 Hz
        # Data format register.
        if self.range == AcclrmtrRangeCfg['+/-2g']: self.rpi.spi_write(self.spi0, [0x31, 0b00000000])
        elif self.range == AcclrmtrRangeCfg['+/-4g']: self.rpi.spi_write(self.spi0, [0x31, 0b00000001])
        elif self.range == AcclrmtrRangeCfg['+/-8g']: self.rpi.spi_write(self.spi0, [0x31, 0b00000010])
        else: self.rpi.spi_write(self.spi0, [0x31, 0b00000011]) # +/- 16 g range.
        self.rpi.spi_write(self.spi0, [0x38, 0b10000000]) # FIFO control register; FIFO mode to stream
        self.rpi.spi_write(self.spi0, [0x2D, 0b00001000]) # Power control register; Enter measurement mode

    
    def read_fifo(self, n):
        for _ in range(n):
            try: xyz = self.spi0_read_bytes(0x32, 6)
            except: return False

            x = self.lsb_to_mm_per_sec_sqr*int.from_bytes(xyz[0:1+1], byteorder='little', signed=True)
            y = self.lsb_to_mm_per_sec_sqr*int.from_bytes(xyz[2:3+1], byteorder='little', signed=True)
            z = self.lsb_to_mm_per_sec_sqr*int.from_bytes(xyz[4:5+1], byteorder='little', signed=True)

            self.x_buff.append(x); self.y_buff.append(y); self.z_buff.append(z)

            self.x_anim += x; self.y_anim += y; self.z_anim += z
            self.samples_for_anim_idx += 1

            if self.samples_for_anim_idx == ACCLRMTR_LIVE_VIEW_DOWNSAMPLE_FACTOR:
                self.x_buff_anim.append(self.x_anim/ACCLRMTR_LIVE_VIEW_DOWNSAMPLE_FACTOR)
                self.y_buff_anim.append(self.y_anim/ACCLRMTR_LIVE_VIEW_DOWNSAMPLE_FACTOR)
                self.z_buff_anim.append(self.z_anim/ACCLRMTR_LIVE_VIEW_DOWNSAMPLE_FACTOR)
                self.x_anim = 0.; self.y_anim = 0.; self.z_anim = 0.
                self.samples_for_anim_idx = 0
        return True


    def collect_samples(self):

        try: n_fifo = self.spi0_read_bytes(0x39, 1)[0] & 0b00111111
        except: self.status = AcclrmtrStatus.READ_FAILED; return

        if n_fifo == 0: # No samples ready
            self.n_fifo_zero_cnt += 1
            if self.n_fifo_zero_cnt > FIFO_ACQ_TIMEOUT_THD: self.status = AcclrmtrStatus.CONNECTION_FAILED
            else: self.refresh_collect_timer()

        elif n_fifo > 0 and n_fifo <= 32: # Samples are ready
            self.n_fifo_zero_cnt = 0

            success = self.read_fifo(n_fifo)
            if not success: self.status = AcclrmtrStatus.READ_FAILED; return

            while True:
                try: n_fifo = self.spi0_read_bytes(0x39, 1)[0] & 0b00111111
                except: self.status = AcclrmtrStatus.READ_FAILED; return
                if n_fifo < READ_CONTINUE_THD: break
                elif n_fifo == 32: self.status = AcclrmtrStatus.OVERRUN; return
                else:
                    success = self.read_fifo(n_fifo)
                    if not success: self.status = AcclrmtrStatus.READ_FAILED; return

            self.refresh_collect_timer()

            if n_fifo == 32: # Overrun
                self.status = AcclrmtrStatus.OVERRUN
        else:
            self.status = AcclrmtrStatus.OUT_OF_RANGE


    def refresh_collect_timer(self):
        if not self._stop: threading.Timer(POLL_TI_SEC, self.collect_samples).start()
        else: self.status = AcclrmtrStatus.STOPPED


    def start(self, self_test_mode=False):
        self._stop = False

        self.x_buff = []; self.y_buff = []; self.z_buff = []
        self.x_anim = 0.; self.y_anim = 0.; self.z_anim = 0.
        self.x_buff_anim = []; self.y_buff_anim = []; self.z_buff_anim = []
        self.samples_collected = 0
        self.samples_for_anim_idx = 0
        self.n_fifo_zero_cnt = 0

        if not self_test_mode:
            self.cnfgr_for_data_acq()
            time.sleep(0.1) # 100 msec delay for samples to steady.

        # Clear the current buffer and start:
        try: n_fifo = self.spi0_read_bytes(0x39, 1)[0] & 0b00111111
        except: self.status = AcclrmtrStatus.READ_FAILED; return
        if n_fifo >= 0 and n_fifo <= 32:
            for _ in range(n_fifo):
                try: _ = self.spi0_read_bytes(0x32, 6)
                except: self.status = AcclrmtrStatus.READ_FAILED; return
            
            self.status = AcclrmtrStatus.COLLECTING
            threading.Timer(POLL_TI_SEC, self.collect_samples).start()
        else:
            self.status = AcclrmtrStatus.OUT_OF_RANGE
        

    def stop(self):
        self._stop = True
        while self.status == AcclrmtrStatus.COLLECTING: time.sleep(POLL_TI_SEC)
        self.rpi.spi_write(self.spi0, [0x2D, 0b00000000]) # Power control register; Stop measurement mode


    def cnfgr_for_self_test(self):
        '''Writes the device registers to set it up for self-test.'''
        self.rpi.spi_write(self.spi0, [0x2C, 0b00001100]) # Data rate register; 400 Hz
        self.rpi.spi_write(self.spi0, [0x31, 0b00001011]) # Data format register; FULL_RES mode and +/- 16g range
        self.rpi.spi_write(self.spi0, [0x38, 0b10000000]) # FIFO control register; FIFO mode to stream
        self.rpi.spi_write(self.spi0, [0x2D, 0b00001000]) # Power control register; Enter measurement mode


    def ena_self_test(self):
        '''Writes the device register that enables self-test. To disable,
        configure the device for data acquisition using other provided method.'''
        self.rpi.spi_write(self.spi0, [0x31, 0b10001011])
    

    def self_test(self):
        '''Confirms a working device is connected by using the self-test routine.
        For functional details, it is best to refer to the datasheet.
        '''
        self.cnfgr_for_self_test()
        self.start(self_test_mode=True)
        time.sleep(0.25) # Requires 0.1 sec of data or greater -- use 0.25 and first 32 will be discarded.
        self.stop()
        if self.status != AcclrmtrStatus.STOPPED: return AcclrmtrSelfTestSts.FAIL
        x_st_off = self.x_buff.copy(); y_st_off = self.y_buff.copy(); z_st_off = self.z_buff.copy()
        self.cnfgr_for_self_test(); self.ena_self_test()
        self.start(self_test_mode=True)
        time.sleep(0.25)
        self.stop()
        if self.status != AcclrmtrStatus.STOPPED: return AcclrmtrSelfTestSts.FAIL
        x_st_on = self.x_buff.copy(); y_st_on = self.y_buff.copy(); z_st_on = self.z_buff.copy()
        self.cnfgr_for_self_test() # Disable the self-test.
        self.rpi.spi_write(self.spi0, [0x2D, 0b00000000]) # Power control register; Stop measurement mode

        if not (len(x_st_on) > 32 and len(y_st_on) > 32 and len(z_st_on) > 32 and
                len(x_st_off) > 32 and len(y_st_off) > 32 and len(z_st_off) > 32): return AcclrmtrSelfTestSts.FAIL
        
        x_st_off_avg = sum(x_st_off[32:])/len(x_st_off[32:])
        y_st_off_avg = sum(y_st_off[32:])/len(y_st_off[32:])
        z_st_off_avg = sum(z_st_off[32:])/len(z_st_off[32:])

        x_st_on_avg = sum(x_st_on[32:])/len(x_st_on[32:])
        y_st_on_avg = sum(y_st_on[32:])/len(y_st_on[32:])
        z_st_on_avg = sum(z_st_on[32:])/len(z_st_on[32:])

        x_st = (x_st_on_avg - x_st_off_avg)/self.lsb_to_mm_per_sec_sqr
        y_st = (y_st_on_avg - y_st_off_avg)/self.lsb_to_mm_per_sec_sqr
        z_st = (z_st_on_avg - z_st_off_avg)/self.lsb_to_mm_per_sec_sqr

        # Evaluate using thresholds from Table 15 and adjusting to 3.3 V from Table 14
        x_pass = (x_st > 1.77*50 and x_st < 1.77*540)
        y_pass = (y_st > 1.77*-540 and y_st < 1.77*-50)
        z_pass = (z_st > 1.47*75 and z_st < 1.47*875)

        return AcclrmtrSelfTestSts.PASS if (x_pass and y_pass and z_pass) else AcclrmtrSelfTestSts.FAIL
