from .accelerometer_abc import Accelerometer, AcclrmtrCfg, AcclrmtrRateCfg, AcclrmtrSelfTestSts
from math import pi, sin, sqrt

import numpy as np
import time


RATE_MULTIPLIER = 20. # Speed things up for simulation.


class SimulatedAccelerometer(Accelerometer):
    def __init__(self, config: AcclrmtrCfg):

        super().__init__(config)

        if config.rate == AcclrmtrRateCfg['3200Hz']: self.T = 1/3200.; self.config.poll_time = 0.0005
        elif config.rate == AcclrmtrRateCfg['1600Hz']: self.T = 1/1600.; self.config.poll_time = 0.001
        elif config.rate == AcclrmtrRateCfg['800Hz']: self.T = 1/800.; self.config.poll_time = 0.001
        elif config.rate == AcclrmtrRateCfg['400Hz']: self.T = 1/400.; self.config.poll_time = 0.001
        elif config.rate == AcclrmtrRateCfg['200Hz']: self.T = 1/200.; self.config.poll_time = 0.001
        else: raise Exception('Unknown rate configuration.')

        self.downsample_factor = round((1/1600.) / self.T * 24)


    
    def set_simulation_params(self, f0, f1, dfdt, a, step_ti, step_a, dly1_ti, dly2_ti, dly3_ti):
        prfl_cfg = ChirpConfig(f0, f1, dfdt, a, step_ti, step_a, dly1_ti, dly2_ti, dly3_ti)
        self.sim_data = np.gradient(np.gradient(make_profile(prfl_cfg, self.T, sim=True)/self.T)/self.T)


    def simulation_done(self): return self.sim_sample_idx == len(self.sim_data)


    def self_test(self): return AcclrmtrSelfTestSts.PASS


    def start(self):
        self.last_collect_time = time.perf_counter()
        self.sim_sample_idx = 0
        super().start()


    def _collect_samples(self):
        n_new_samples = round(RATE_MULTIPLIER * (time.perf_counter() - self.last_collect_time) / self.T)
        n_new_samples = min(n_new_samples, len(self.sim_data) - self.sim_sample_idx)
        
        for _ in range(n_new_samples):
            new_sample = float(self.sim_data[self.sim_sample_idx])
            self.x_buff.append(new_sample)
            self.y_buff.append(new_sample)
            self.z_buff.append(new_sample)

            self._x_anim += new_sample
            self._y_anim += new_sample
            self._z_anim += new_sample
            self._samples_for_anim_idx += 1

            if self._samples_for_anim_idx == self.downsample_factor:
                self.x_buff_anim.append(self._x_anim/self.downsample_factor)
                self.y_buff_anim.append(self._y_anim/self.downsample_factor)
                self.z_buff_anim.append(self._z_anim/self.downsample_factor)
                self._x_anim = 0.; self._y_anim = 0.; self._z_anim = 0.
                self._samples_for_anim_idx = 0
                
            self.sim_sample_idx += 1

        self.last_collect_time = time.perf_counter()
        self._refresh_collect_timer()

    
    def close(self): return


class ChirpConfig:
    def __init__(self, f0, f1, dfdt, a, step_ti, step_a, dly1_ti, dly2_ti, dly3_ti):
        self.f0 = f0; self.f1 = f1; self.dfdt = dfdt; self.a = a
        self.step_ti = step_ti; self.step_a = step_a; self.dly1_ti = dly1_ti; self.dly2_ti = dly2_ti; self.dly3_ti = dly3_ti


class TrajGenConfig:
    def __init__(self, prfl_cfg):
        f0_ = prfl_cfg.f0 - 1.
        t1 = (prfl_cfg.f1 - f0_) / prfl_cfg.dfdt
        self.k1 = pi*prfl_cfg.dfdt
        self.k2 = 2.*pi*f0_
        self.pcws_ti = [prfl_cfg.dly1_ti,
                        prfl_cfg.dly1_ti + 4 * prfl_cfg.step_ti,
                        prfl_cfg.dly1_ti + 4 * prfl_cfg.step_ti + prfl_cfg.dly2_ti,
                        prfl_cfg.dly1_ti + 4 * prfl_cfg.step_ti + prfl_cfg.dly2_ti + t1,
                        prfl_cfg.dly1_ti + 4 * prfl_cfg.step_ti + prfl_cfg.dly2_ti + t1 + prfl_cfg.dly3_ti,
                        prfl_cfg.dly1_ti + 8 * prfl_cfg.step_ti + prfl_cfg.dly2_ti + t1 + prfl_cfg.dly3_ti,
                        ]
        self.step_a_x_0p5 = 0.5*prfl_cfg.step_a
        self.step_a_x_step_ti_x_step_ti = prfl_cfg.step_a * (prfl_cfg.step_ti)**2
        self.step_ti_x_2 = 2. * prfl_cfg.step_ti
        self.step_ti_x_3 = 3. * prfl_cfg.step_ti
        self.step_ti_x_4 = 4. * prfl_cfg.step_ti
        

def make_profile(prfl_cfg, T, sim=False):
    """Python implementation of the firmware profile generation.
    """

    FTM_TS = T # Variable names are intended to match the firmware implementation.

    traj_gen_cfg = TrajGenConfig(prfl_cfg)
    max_intervals = round(traj_gen_cfg.pcws_ti[-1]/T + 0.5) # ceil

    s = np.zeros((max_intervals,))
    
    for makeVector_idx in range(max_intervals):
        
        tau = makeVector_idx * FTM_TS

        if ( tau <= traj_gen_cfg.pcws_ti[0] ): s_ = 0.0
        
        elif ( tau <= traj_gen_cfg.pcws_ti[1] ):
            tau_ = tau - traj_gen_cfg.pcws_ti[0]
            if tau_ < prfl_cfg.step_ti:
                s_ = traj_gen_cfg.step_a_x_0p5 * tau_ * tau_
            elif tau_ < traj_gen_cfg.step_ti_x_3:
                k_ = tau_ - traj_gen_cfg.step_ti_x_2; s_ = traj_gen_cfg.step_a_x_step_ti_x_step_ti - traj_gen_cfg.step_a_x_0p5 * k_**2
            else:
                k_ = tau_ - traj_gen_cfg.step_ti_x_4; s_ = traj_gen_cfg.step_a_x_0p5 * k_**2

        elif ( tau <= traj_gen_cfg.pcws_ti[2] ): s_ = 0.0
        
        elif ( tau <= traj_gen_cfg.pcws_ti[3] ):
            tau_ = tau - traj_gen_cfg.pcws_ti[2]
            tau_tau_ = tau_*tau_
            tau_tau_tau_ = tau_tau_*tau_
            k_ = 1 / (2*traj_gen_cfg.k1*tau_ + traj_gen_cfg.k2)
            A_ = (tau_tau_tau_ if (tau_tau_tau_ < 1.) else 1.) * prfl_cfg.a * k_ * k_
            if sim:
                f = prfl_cfg.f0 - 1. + tau_*prfl_cfg.dfdt
                A_ *= 1./sqrt((1.-(f/35)**2)**2+(.2*f/35)**2)
            s_ = A_*sin(traj_gen_cfg.k1*tau_tau_ + traj_gen_cfg.k2*tau_)
        
        elif ( tau <= traj_gen_cfg.pcws_ti[4] ): s_ = 0.0

        elif ( tau <= traj_gen_cfg.pcws_ti[5] ):
            tau_ = tau - traj_gen_cfg.pcws_ti[4]
            if tau_ < prfl_cfg.step_ti:
                s_ = -traj_gen_cfg.step_a_x_0p5 * tau_ * tau_
            elif tau_ < traj_gen_cfg.step_ti_x_3:
                k_ = tau_ - traj_gen_cfg.step_ti_x_2; s_ = -traj_gen_cfg.step_a_x_step_ti_x_step_ti + traj_gen_cfg.step_a_x_0p5 * k_**2
            else:
                k_ = tau_ - traj_gen_cfg.step_ti_x_4; s_ = -traj_gen_cfg.step_a_x_0p5 * k_**2

        else : s_ = 0.0
        
        s[makeVector_idx] = s_

    return s