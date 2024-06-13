import subprocess
import pigpio
import struct
import time
import os

from enum import Enum

if "ulendo_autocal.lib" in __package__:
    from ..autocal_cfg import *
    from ..autocal_exceptions import DaemonNotRunning, CommunicationError
elif __package__ == "lib":
    from autocal_cfg import *
    from autocal_exceptions import DaemonNotRunning, CommunicationError


## Configurations
POLL_TI_NS = 16000000 # Set to 80% of 32/1600.
ACC_LSB_TO_MM_PER_SEC_SQR = 2.*2./1024.*9806.65 # +/- 2 g range
# ACC_LSB_TO_MM_PER_SEC_SQR = 2.*4./1024.*9806.65 # +/- 4 g range
ACC_DATA_RATE_NS = (1/1600)*1000000000
FIFO_ACQ_TIMOUT_TI = 0.5

FIFO_ACQ_TIMEOUT_THD = int(FIFO_ACQ_TIMOUT_TI/(POLL_TI_NS/1000000000))


StSts = Enum('StSts', ['ST_PASS', 'ST_FAIL'])


class Adxl345:
    '''Provides necessary accelerometer functions for autocalibration
    using the ADXL345 accelerometer device.'''

    def __init__(self, data_folder):
        '''Opens SPI connection on creation and initializes class storage (data buffers).'''
        # Check if daemon is running
        self.data_folder = data_folder
        try:
            subprocess.check_output(['pidof', 'pigpiod']) # TODO: what is this ?
            self.rpi = pigpio.pi()
            self.spi0 = self.rpi.spi_open(spi_channel=0, baud=4000000, spi_flags=3)
        except:
            self.rpi = None
            self.spi0 = None
            raise DaemonNotRunning('pigpio daemon is not running')
        self.x_buff = []; self.y_buff = []; self.z_buff = []
        self.external_stop = False
    

    def close(self):
        '''Closes the SPI connection.'''
        if self.rpi is not None: self.rpi.spi_close(self.spi0)


    def spi0_read_bytes(self, addr, count):
        '''Reads a number of bytes at address.
        
        Arguments:
            addr -- Address of read.
            count -- Number of bytes to read.
            
        Returns:
            [] -- Received data as bytes.'''
        addr_ = addr | 0x80         # Set read bit
        if count > 1: addr_ |= 0x40 # Set multi bit
        (_, rx_data) = self.rpi.spi_xfer(self.spi0, [addr_] + [0xFF]*count)

        return rx_data[1:]
    

    def cnfgr_for_data_acq(self):
        '''Writes the device registers to set it up for data acquisition.'''
        self.rpi.spi_write(self.spi0, [0x2C, 0b00001110]) # Data rate register; 1600 Hz
        # self.rpi.spi_write(self.spi0, [0x31, 0b00000001]) # Data format register; +/- 4g range
        self.rpi.spi_write(self.spi0, [0x31, 0b00000000]) # Data format register; +/- 2g range
        self.rpi.spi_write(self.spi0, [0x38, 0b10000000]) # FIFO control register; FIFO mode to stream
        self.rpi.spi_write(self.spi0, [0x2D, 0b00001000]) # Power control register; Enter measurement mode


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
    
    
    def collect_samples(self, n_max=None):
        '''Polls the device for data samples until the specified amount has been
        collected. The device is use in FIFO mode so this function polls the FIFO
        entries register. If entries are available, it will read that number of
        samples from data registers and store it (in addition to updating buffers
        for GUI use) in class variables. Some exceptions are provided:
            CommunicationError TODO: Since the device is used in FIFO mode, this is triggered
                if the FIFO entries report 0 for some time (this occurs when the device
                is disconnected so this is the expected error in case of missing device
                or incorrect wiring).
            CommunicationError TODO: This is triggered if the FIFO entries reported are out of
                range. It may indicate some data corruption is occurring.
            CommunicationError TODO: A monitor is provided if the FIFO entries are maxed (32)
                after the initial read. This indicates data may have been missed. In
                any occurrence, the loop time is recorded and used to estimate the
                number of samples that may have been missed. If that number exceeds
                a threshold, this exception is raised. It may indicate other processes
                consuming RPi resources and affecting the timing here.'''
        self.x_buff = []; self.y_buff = []; self.z_buff = []

        # TODO: handle if directory doesnt exist
        os.makedirs(os.path.join(self.data_folder, 'data'), exist_ok=True)
        
        f_x_anim = open(os.path.join(self.data_folder, 'data', 'tmpxfild'), 'ab')
        f_y_anim = open(os.path.join(self.data_folder, 'data', 'tmpyfild'), 'ab')
        f_z_anim = open(os.path.join(self.data_folder, 'data', 'tmpzfild'), 'ab')

        n = 0
        n_fifo_zero_cnt = 0

        x_anim = 0.; y_anim = 0.; z_anim = 0.; anim_idx = 0

        n_max_collected = False
        while not n_max_collected and not self.external_stop:

            poll_ti_t0 = time.perf_counter_ns()
            n_fifo = self.spi0_read_bytes(0x39, 1)[0] & 0b00111111

            if n_fifo == 0: # No samples ready
                n_fifo_zero_cnt += 1
                if n_fifo_zero_cnt > FIFO_ACQ_TIMEOUT_THD:
                    f_x_anim.close(); f_y_anim.close(); f_z_anim.close()
                    raise CommunicationError('fifo status acquisition timeout', type='connection')

            elif n_fifo > 0 and n_fifo <= 32: # Samples are ready
                n_fifo_zero_cnt = 0

                for _ in range(n_fifo):
                    xyz = self.spi0_read_bytes(0x32, 6)
                    x = int.from_bytes(xyz[0:1+1], byteorder='little', signed=True)
                    y = int.from_bytes(xyz[2:3+1], byteorder='little', signed=True)
                    z = int.from_bytes(xyz[4:5+1], byteorder='little', signed=True)
                    self.x_buff.append(x); self.y_buff.append(y); self.z_buff.append(z)
                    # TODO: test if pre allocated array eliminates lost samples


                    x_anim += ACC_LSB_TO_MM_PER_SEC_SQR*x
                    y_anim += ACC_LSB_TO_MM_PER_SEC_SQR*y
                    z_anim += ACC_LSB_TO_MM_PER_SEC_SQR*z
                    anim_idx += 1

                    if anim_idx == ACCLRMTR_LIVE_VIEW_DOWNSAMPLE_FACTOR:
                        f_x_anim.write(struct.pack('f', x_anim/ACCLRMTR_LIVE_VIEW_DOWNSAMPLE_FACTOR))
                        f_y_anim.write(struct.pack('f', y_anim/ACCLRMTR_LIVE_VIEW_DOWNSAMPLE_FACTOR))
                        f_z_anim.write(struct.pack('f', z_anim/ACCLRMTR_LIVE_VIEW_DOWNSAMPLE_FACTOR))
                        x_anim = 0.; y_anim = 0.; z_anim = 0.
                        anim_idx = 0

                f_x_anim.flush()
                f_y_anim.flush()
                f_z_anim.flush()
                if n > 0 and n_fifo == 32: # Overrun
                    raise CommunicationError('fifo overrun detected', type='streaming')
            else:
                f_x_anim.close(); f_y_anim.close(); f_z_anim.close()
                raise CommunicationError('fifo status out of range', type='streaming')

            n += n_fifo

            if n_max is not None and n >= n_max: n_max_collected = True

            while ((time.perf_counter_ns() - poll_ti_t0) < POLL_TI_NS): pass

        f_x_anim.close()
        f_y_anim.close()
        f_z_anim.close()

        # Clear external stop in case was set
        self.external_stop = False


    def self_test(self):
        '''Confirms a working device is connected by using the self-test routine.
        For functional details, it is best to refer to the datasheet.
        
        Returns:
            StSts.ST_PASS if the test passes.
            StSts.ST_FAIL if the test fails.'''
        self.cnfgr_for_self_test()
        self.collect_samples(112)  # 0.1 sec of data or greater; chose 80 samples (0.2 sec @ 400 Hz), plus 32 that will be discarded
        x_st_off = self.x_buff; y_st_off = self.y_buff; z_st_off = self.z_buff
        self.ena_self_test()
        self.collect_samples(112)
        x_st_on = self.x_buff; y_st_on = self.y_buff; z_st_on = self.z_buff
        self.cnfgr_for_data_acq() # To disable the self-test, reconfigure for normal data acquisition.

        self.rpi.spi_write(self.spi0, [0x2D, 0b00000000]) # Power control register; Stop measurement mode

        x_st_off_avg = sum(x_st_off[32:])/len(x_st_off[32:])
        y_st_off_avg = sum(y_st_off[32:])/len(y_st_off[32:])
        z_st_off_avg = sum(z_st_off[32:])/len(z_st_off[32:])

        x_st_on_avg = sum(x_st_on[32:])/len(x_st_on[32:])
        y_st_on_avg = sum(y_st_on[32:])/len(y_st_on[32:])
        z_st_on_avg = sum(z_st_on[32:])/len(z_st_on[32:])

        x_st = x_st_on_avg - x_st_off_avg
        y_st = y_st_on_avg - y_st_off_avg
        z_st = z_st_on_avg - z_st_off_avg

        # Evaluate using thresholds from Table 15 and adjusting to 3.3 V from Table 14
        x_pass = (x_st > 1.77*50 and x_st < 1.77*540)
        y_pass = (y_st > 1.77*-540 and y_st < 1.77*-50)
        z_pass = (z_st > 1.47*75 and z_st < 1.47*875)

        return StSts.ST_PASS if (x_pass and y_pass and z_pass) else StSts.ST_FAIL


    def acquire(self):
        '''Mostly a wrapper for collect_samples; see its documentation for details.
        Prior to collecting samples, the configuration for data acquisition is set,
        and measurement mode is disabled afterwards.'''
        self.cnfgr_for_data_acq()
        t0 = time.perf_counter_ns()
        while ((time.perf_counter_ns() - t0) < 100000000): pass # 100 msec delay for samples to steady
        self.collect_samples()
        self.rpi.spi_write(self.spi0, [0x2D, 0b00000000]) # Power control register; Stop measurement mode
