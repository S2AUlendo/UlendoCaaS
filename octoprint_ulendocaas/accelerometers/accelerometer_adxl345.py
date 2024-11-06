from .accelerometer_abc import AcclerometerOverSPI, AcclrmtrCfg, AcclrmtrRangeCfg, AcclrmtrRateCfg, AcclrmtrSelfTestSts, AcclrmtrStatus

import time


READ_CONTINUE_THD = 5
FIFO_ACQ_TIMOUT_TI = 0.5
FIFO_ACQ_TIMEOUT_THD = 25


class Adxl345(AcclerometerOverSPI):
    def __init__(self, config: AcclrmtrCfg):
        
        super().__init__(config)

        if config.range == AcclrmtrRangeCfg['+/-2g']: self._lsb_to_mm_per_sec_sqr = 2.*2./1024.*9806.65
        elif config.range == AcclrmtrRangeCfg['+/-4g']: self._lsb_to_mm_per_sec_sqr = 2.*4./1024.*9806.65
        elif config.range == AcclrmtrRangeCfg['+/-8g']: self._lsb_to_mm_per_sec_sqr = 2.*8./1024.*9806.65
        elif config.range == AcclrmtrRangeCfg['+/-16g']: self._lsb_to_mm_per_sec_sqr = 2.*16./1024.*9806.65
        else: raise Exception('Got unexpected range config.')
        self.status = AcclrmtrStatus.INIT

        if config.rate == AcclrmtrRateCfg['3200Hz']: self.T = 1/3200.; self.config.poll_time = 0.0005
        elif config.rate == AcclrmtrRateCfg['1600Hz']: self.T = 1/1600.; self.config.poll_time = 0.001
        elif config.rate == AcclrmtrRateCfg['800Hz']: self.T = 1/800.; self.config.poll_time = 0.001
        elif config.rate == AcclrmtrRateCfg['400Hz']: self.T = 1/400.; self.config.poll_time = 0.001
        elif config.rate == AcclrmtrRateCfg['200Hz']: self.T = 1/200.; self.config.poll_time = 0.001
        else: raise Exception('Unknown rate configuration.')

        self.downsample_factor = round((1/1600.) / self.T * 24)

    
    def __cnfgr_for_data_acq(self):
        '''Writes the device registers to set it up for data acquisition.'''
        
        if self.config.rate == AcclrmtrRateCfg['3200Hz']: self._rpi.spi_write(self._spi0, [0x2C, 0b00001111])
        elif self.config.rate == AcclrmtrRateCfg['1600Hz']: self._rpi.spi_write(self._spi0, [0x2C, 0b00001110])
        elif self.config.rate == AcclrmtrRateCfg['800Hz']: self._rpi.spi_write(self._spi0, [0x2C, 0b00001101])
        elif self.config.rate == AcclrmtrRateCfg['400Hz']: self._rpi.spi_write(self._spi0, [0x2C, 0b00001100])
        elif self.config.rate == AcclrmtrRateCfg['200Hz']: self._rpi.spi_write(self._spi0, [0x2C, 0b00001011])
        else: raise Exception('Unknown rate configuration.')

        if self.config.range == AcclrmtrRangeCfg['+/-2g']: self._rpi.spi_write(self._spi0, [0x31, 0b00000000])
        elif self.config.range == AcclrmtrRangeCfg['+/-4g']: self._rpi.spi_write(self._spi0, [0x31, 0b00000001])
        elif self.config.range == AcclrmtrRangeCfg['+/-8g']: self._rpi.spi_write(self._spi0, [0x31, 0b00000010])
        elif self.config.range == AcclrmtrRangeCfg['+/-16g']: self._rpi.spi_write(self._spi0, [0x31, 0b00000011])
        else: raise Exception('Unknown range configuration.')
        
        self._rpi.spi_write(self._spi0, [0x38, 0b10000000]) # FIFO control register; FIFO mode to stream
        self._rpi.spi_write(self._spi0, [0x2D, 0b00001000]) # Power control register; Enter measurement mode

    
    def __cnfgr_for_self_test(self):
        '''Writes the device registers to set it up for self-test.'''
        self._rpi.spi_write(self._spi0, [0x2C, 0b00001100]) # Data rate register; 400 Hz
        self._rpi.spi_write(self._spi0, [0x31, 0b00001011]) # Data format register; FULL_RES mode and +/- 16g range
        self._rpi.spi_write(self._spi0, [0x38, 0b10000000]) # FIFO control register; FIFO mode to stream
        self._rpi.spi_write(self._spi0, [0x2D, 0b00001000]) # Power control register; Enter measurement mode


    def __ena_self_test(self):
        '''Writes the device register that enables self-test. To disable,
        configure the device for data acquisition using other provided method.'''
        self._rpi.spi_write(self._spi0, [0x31, 0b10001011])
    

    def __read_fifo(self, n):
        for _ in range(n):
            try: xyz = self._spi0_read_bytes(0x32, 6)
            except: return False

            x = self._lsb_to_mm_per_sec_sqr*int.from_bytes(xyz[0:1+1], byteorder='little', signed=True)
            y = self._lsb_to_mm_per_sec_sqr*int.from_bytes(xyz[2:3+1], byteorder='little', signed=True)
            z = self._lsb_to_mm_per_sec_sqr*int.from_bytes(xyz[4:5+1], byteorder='little', signed=True)

            self.x_buff.append(x); self.y_buff.append(y); self.z_buff.append(z)

            self._x_anim += x; self._y_anim += y; self._z_anim += z
            self._samples_for_anim_idx += 1

            if self._samples_for_anim_idx == self.downsample_factor:
                self.x_buff_anim.append(self._x_anim/self.downsample_factor)
                self.y_buff_anim.append(self._y_anim/self.downsample_factor)
                self.z_buff_anim.append(self._z_anim/self.downsample_factor)
                self._x_anim = 0.; self._y_anim = 0.; self._z_anim = 0.
                self._samples_for_anim_idx = 0
        return True
    

    def self_test(self):
        '''Confirms a working device is connected by using the self-test routine.
        For functional details, it is best to refer to the datasheet.
        '''
        self.__cnfgr_for_self_test()
        self.start(self_test_mode=True)
        time.sleep(0.25) # Requires 0.1 sec of data or greater -- use 0.25 and first 32 will be discarded.
        self.stop()
        if self.status != AcclrmtrStatus.STOPPED: return AcclrmtrSelfTestSts.FAIL
        x_st_off = self.x_buff.copy(); y_st_off = self.y_buff.copy(); z_st_off = self.z_buff.copy()
        self.__cnfgr_for_self_test(); self.__ena_self_test()
        self.start(self_test_mode=True)
        time.sleep(0.25)
        self.stop()
        if self.status != AcclrmtrStatus.STOPPED: return AcclrmtrSelfTestSts.FAIL
        x_st_on = self.x_buff.copy(); y_st_on = self.y_buff.copy(); z_st_on = self.z_buff.copy()
        self.__cnfgr_for_self_test() # Disable the self-test.
        self._rpi.spi_write(self._spi0, [0x2D, 0b00000000]) # Power control register; Stop measurement mode

        if not (len(x_st_on) > 32 and len(y_st_on) > 32 and len(z_st_on) > 32 and
                len(x_st_off) > 32 and len(y_st_off) > 32 and len(z_st_off) > 32): return AcclrmtrSelfTestSts.FAIL
        
        x_st_off_avg = sum(x_st_off[32:])/len(x_st_off[32:])
        y_st_off_avg = sum(y_st_off[32:])/len(y_st_off[32:])
        z_st_off_avg = sum(z_st_off[32:])/len(z_st_off[32:])

        x_st_on_avg = sum(x_st_on[32:])/len(x_st_on[32:])
        y_st_on_avg = sum(y_st_on[32:])/len(y_st_on[32:])
        z_st_on_avg = sum(z_st_on[32:])/len(z_st_on[32:])

        x_st = (x_st_on_avg - x_st_off_avg)/self._lsb_to_mm_per_sec_sqr
        y_st = (y_st_on_avg - y_st_off_avg)/self._lsb_to_mm_per_sec_sqr
        z_st = (z_st_on_avg - z_st_off_avg)/self._lsb_to_mm_per_sec_sqr

        # Evaluate using thresholds from Table 15 and adjusting to 3.3 V from Table 14
        x_pass = (x_st > 1.77*50 and x_st < 1.77*540)
        y_pass = (y_st > 1.77*-540 and y_st < 1.77*-50)
        z_pass = (z_st > 1.47*75 and z_st < 1.47*875)

        return AcclrmtrSelfTestSts.PASS if (x_pass and y_pass and z_pass) else AcclrmtrSelfTestSts.FAIL


    def start(self, self_test_mode=False):
        
        self._n_fifo_zero_cnt = 0

        if not self_test_mode:
            self.__cnfgr_for_data_acq()
            time.sleep(0.1) # 100 msec delay for samples to steady.

        # Clear the current buffer and start:
        try: n_fifo = self._spi0_read_bytes(0x39, 1)[0] & 0b00111111
        except: self.status = AcclrmtrStatus.READ_FAILED; return
        if n_fifo >= 0 and n_fifo <= 32:
            for _ in range(n_fifo):
                try: _ = self._spi0_read_bytes(0x32, 6)
                except: self.status = AcclrmtrStatus.READ_FAILED; return
            
            super().start()
        else:
            self.status = AcclrmtrStatus.OUT_OF_RANGE


    def _collect_samples(self):

        try: n_fifo = self._spi0_read_bytes(0x39, 1)[0] & 0b00111111
        except: self.status = AcclrmtrStatus.READ_FAILED; return

        if n_fifo == 0: # No samples ready
            self._n_fifo_zero_cnt += 1
            if self._n_fifo_zero_cnt > FIFO_ACQ_TIMEOUT_THD: self.status = AcclrmtrStatus.CONNECTION_FAILED
            else: self._refresh_collect_timer()

        elif n_fifo > 0 and n_fifo <= 32: # Samples are ready
            self._n_fifo_zero_cnt = 0

            success = self.__read_fifo(n_fifo)
            if not success: self.status = AcclrmtrStatus.READ_FAILED; return

            while True:
                try: n_fifo = self._spi0_read_bytes(0x39, 1)[0] & 0b00111111
                except: self.status = AcclrmtrStatus.READ_FAILED; return
                if n_fifo < READ_CONTINUE_THD: break
                elif n_fifo == 32: self.status = AcclrmtrStatus.OVERRUN; return
                else:
                    success = self.__read_fifo(n_fifo)
                    if not success: self.status = AcclrmtrStatus.READ_FAILED; return

            self._refresh_collect_timer()

            if n_fifo == 32: # Overrun
                self.status = AcclrmtrStatus.OVERRUN
        else:
            self.status = AcclrmtrStatus.OUT_OF_RANGE


    def stop(self):
        super().stop()
        self._rpi.spi_write(self._spi0, [0x2D, 0b00000000]) # Power control register; Stop measurement mode

    
    def close(self): self._rpi.spi_close(self._spi0)