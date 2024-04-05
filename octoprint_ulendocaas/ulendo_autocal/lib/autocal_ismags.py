from math import sqrt, exp, pi, sin, cos, log10
import numpy as np


def zv_mag1(wc, zt, w):
    df = sqrt(1. - zt*zt)
    k_ = exp(-zt*pi/df)
    a0 = 1/(1+k_)
    a1 = k_/(1+k_)
    im = a1*sin((w/wc)*(pi/df))
    re = a0 + a1*cos((w/wc)*(pi/df))
    return 20.*log10(sqrt(re*re + im*im))
    

def zv_mag2(wc, zt, w):
    if w > 2*wc*sqrt(1. - zt*zt):
        return 0.
    else:
        return zv_mag1(wc, zt, w)
    

def zv_mags(wc, zt, w):
    df = sqrt(1. - zt*zt)
    k_ = exp(-zt*pi/df)
    a0 = 1/(1+k_)
    a1 = k_/(1+k_)
    arg = (w/wc)*(pi/df)
    im = a1*np.sin(arg)
    re = a0 + a1*np.cos(arg)
    return np.sqrt(re**2 + im**2)
    

def zvd_mag1(wc, zt, w):
    df = sqrt(1. - zt*zt)
    k_ = exp(-zt*pi/df)
    a0 = 1/(1+2*k_+k_*k_)
    a1 = 2*k_*a0
    a2 = k_*k_*a0
    im = a1*sin((w/wc)*(pi/df)) + a2*sin(2*(w/wc)*(pi/df))
    re = a0 + a1*cos((w/wc)*(pi/df)) + a2*cos(2*(w/wc)*(pi/df))
    return 20.*log10(sqrt(re*re + im*im))
    

def zvd_mag2(wc, zt, w):
    if w > 2*wc*sqrt(1. - zt*zt):
        return 0.
    else:
        return zvd_mag1(wc, zt, w)


def zvd_mags(wc, zt, w):
    df = sqrt(1. - zt*zt)
    k_ = exp(-zt*pi/df)
    a0 = 1/(1+2*k_+k_*k_)
    a1 = 2*k_*a0
    a2 = k_*k_*a0
    arg = (w/wc)*(pi/df)
    arg2 = 2.*arg
    im = a1*np.sin(arg) + a2*np.sin(arg2)
    re = a0 + a1*np.cos(arg) + a2*np.cos(arg2)
    return np.sqrt(re**2 + im**2)


def mzv_mag1(wc, zt, w):
    df = sqrt(1. - zt*zt)
    k_ = exp(-zt*pi/df)
    B = 1.4142135623730950488016887242097*k_
    a0 = 1./(1.+B+k_*k_)
    a1 = B*a0
    a2 = k_*k_*a0
    im = a1*sin((w/wc)*(0.75*pi/df)) + a2*sin(2*(w/wc)*(0.75*pi/df))
    re = a0 + a1*cos((w/wc)*(0.75*pi/df)) + a2*cos(2*(w/wc)*(0.75*pi/df))
    return 20.*log10(sqrt(re*re + im*im))


def mzv_mag2(wc, zt, w):
    if w > wc*sqrt(1. - zt*zt)/0.375:
        return 0.
    else:
        return mzv_mag1(wc, zt, w)
    

def mzv_mags(wc, zt, w):
    df = sqrt(1. - zt*zt)
    k_ = exp(-zt*pi/df)
    B = 1.4142135623730950488016887242097*k_
    a0 = 1./(1.+B+k_*k_)
    a1 = B*a0
    a2 = k_*k_*a0
    arg = (w/wc)*(0.75*pi/df)
    arg2 = 2.*arg
    im = a1*np.sin(arg) + a2*np.sin(arg2)
    re = a0 + a1*np.cos(arg) + a2*np.cos(arg2)
    return np.sqrt(re**2 + im**2)


def ei_mag1(wc, zt, vtol, w):
    df = sqrt(1. - zt*zt)
    k_ = exp(-zt*pi/df)
    a0 = 0.25 * (1. + vtol)
    a1 = 0.5 * (1. - vtol) * k_
    a2 = a0 * k_*k_
    a_adj = 1. / (a0 + a1 + a2)
    a0 *= a_adj
    a1 *= a_adj
    a2 *= a_adj
    im = a1*sin((w/wc)*(pi/df)) + a2*sin(2*(w/wc)*(pi/df))
    re = a0 + a1*cos((w/wc)*(pi/df)) + a2*cos(2*(w/wc)*(pi/df))
    return 20.*log10(sqrt(re*re + im*im))


def ei_mag2(wc, zt, vtol, w):
    if w > 2*wc*sqrt(1. - zt*zt):
        return 0.
    else:
        return ei_mag1(wc, zt, vtol, w)


def ei_mags(wc, zt, vtol, w):
    df = sqrt(1. - zt*zt)
    k_ = exp(-zt*pi/df)
    a0 = 0.25 * (1. + vtol)
    a1 = 0.5 * (1. - vtol) * k_
    a2 = a0 * k_*k_
    a_adj = 1. / (a0 + a1 + a2)
    a0 *= a_adj
    a1 *= a_adj
    a2 *= a_adj
    arg = (w/wc)*(pi/df)
    arg2 = 2.*arg
    im = a1*np.sin(arg) + a2*np.sin(arg2)
    re = a0 + a1*np.cos(arg) + a2*np.cos(arg2)
    return np.sqrt(re**2 + im**2)


def ei2h_mag1(wc, zt, vtol, w):
    df = sqrt(1. - zt*zt)
    k_ = exp(-zt*pi/df)
    vtol2 = vtol * vtol
    k2 = pow(vtol2 * (sqrt(1. - vtol2) + 1.), 1./3.)
    a0 = (3.*k2*k2 + 2.*k2 + 3*vtol2) / (16.*k2)
    a1 = (0.5 - a0) * k_
    a2 = a1 * k_
    a3 = a0 * k_*k_*k_
    a_adj = 1. / (a0 + a1 + a2 + a3)
    a0 *= a_adj
    a1 *= a_adj
    a2 *= a_adj
    a3 *= a_adj
    im = a1*sin((w/wc)*(pi/df)) + a2*sin(2*(w/wc)*(pi/df)) + a3*sin(3*(w/wc)*(pi/df))
    re = a0 + a1*cos((w/wc)*(pi/df)) + a2*cos(2*(w/wc)*(pi/df)) + a3*cos(3*(w/wc)*(pi/df))
    return 20.*log10(sqrt(re*re + im*im))

def ei2h_mag2(wc, zt, vtol, w):
    if w > 2*wc*sqrt(1. - zt*zt):
        return 0.
    else:
        return ei2h_mag1(wc, zt, vtol, w)
    

def ei2h_mags(wc, zt, vtol, w):
    df = sqrt(1. - zt*zt)
    k_ = exp(-zt*pi/df)
    vtol2 = vtol * vtol
    k2 = pow(vtol2 * (sqrt(1. - vtol2) + 1.), 1./3.)
    a0 = (3.*k2*k2 + 2.*k2 + 3*vtol2) / (16.*k2)
    a1 = (0.5 - a0) * k_
    a2 = a1 * k_
    a3 = a0 * k_*k_*k_
    a_adj = 1. / (a0 + a1 + a2 + a3)
    a0 *= a_adj
    a1 *= a_adj
    a2 *= a_adj
    a3 *= a_adj
    arg = (w/wc)*(pi/df)
    arg2 = 2.*arg
    arg3 = 3.*arg
    im = a1*np.sin(arg) + a2*np.sin(arg2) + a3*np.sin(arg3)
    re = a0 + a1*np.cos(arg) + a2*np.cos(arg2) + a3*np.cos(arg3)
    return np.sqrt(re**2 + im**2)


def ei3h_mag1(wc, zt, vtol, w):
    df = sqrt(1. - zt*zt)
    k_ = exp(-zt*pi/df)
    a0 = 0.0625 * ( 1. + 3.*vtol + 2.*sqrt(2. * (vtol + 1.)*vtol ) )
    a1 = 0.25 * (1. - vtol) * k_
    a2 = ( 0.5 * (1. + vtol) - 2. * a0 ) * k_ * k_
    a3 = a1 * k_ * k_
    a4 = a0 * k_ * k_ * k_ * k_
    a_adj = 1. / (a0 + a1 + a2 + a3 + a4)
    a0 *= a_adj
    a1 *= a_adj
    a2 *= a_adj
    a3 *= a_adj
    a4 *= a_adj
    im = a1*sin((w/wc)*(pi/df)) + a2*sin(2*(w/wc)*(pi/df)) + a3*sin(3*(w/wc)*(pi/df)) + a4*sin(4*(w/wc)*(pi/df))
    re = a0 + a1*cos((w/wc)*(pi/df)) + a2*cos(2*(w/wc)*(pi/df)) + a3*cos(3*(w/wc)*(pi/df)) + a4*cos(4*(w/wc)*(pi/df))
    return 20.*log10(sqrt(re*re + im*im))


def ei3h_mag2(wc, zt, vtol, w):
    if w > 2*wc*sqrt(1. - zt*zt):
        return 0.
    else:
        return ei3h_mag1(wc, zt, vtol, w)
    

def ei3h_mags(wc, zt, vtol, w):
    df = sqrt(1. - zt*zt)
    k_ = exp(-zt*pi/df)
    a0 = 0.0625 * ( 1. + 3.*vtol + 2.*sqrt(2. * (vtol + 1.)*vtol ) )
    a1 = 0.25 * (1. - vtol) * k_
    a2 = ( 0.5 * (1. + vtol) - 2. * a0 ) * k_ * k_
    a3 = a1 * k_ * k_
    a4 = a0 * k_ * k_ * k_ * k_
    a_adj = 1. / (a0 + a1 + a2 + a3 + a4)
    a0 *= a_adj
    a1 *= a_adj
    a2 *= a_adj
    a3 *= a_adj
    a4 *= a_adj
    arg = (w/wc)*(pi/df)
    arg2 = 2.*arg
    arg3 = 3.*arg
    arg4 = 4.*arg
    im = a1*np.sin(arg) + a2*np.sin(arg2) + a3*np.sin(arg3) + a4*np.sin(arg4)
    re = a0 + a1*np.cos(arg) + a2*np.cos(arg2) + a3*np.cos(arg3) + a4*np.cos(arg4)
    return np.sqrt(re**2 + im**2)


def get_ismag(w, type, wc, zt, vtol=None):
    if type == 'zv': return zv_mags(wc, zt, w)
    elif type == 'zvd': return zvd_mags(wc, zt, w)
    elif type == 'mzv': return mzv_mags(wc, zt, w)
    elif type == 'ei': return ei_mags(wc, zt, vtol, w)
    elif type == 'ei2h': return ei2h_mags(wc, zt, vtol, w)
    elif type == 'ei3h': return ei3h_mags(wc, zt, vtol, w)
