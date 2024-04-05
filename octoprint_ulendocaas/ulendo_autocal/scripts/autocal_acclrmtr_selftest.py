## Script to run the accelerometer self test and return results via exit code.

if __package__ is None:
    import sys
    from os import path
    sys.path.append( path.dirname( path.dirname( path.abspath(__file__) ) ) )
    from lib.autocal_adxl345 import Adxl345, StSts
    from autocal_exceptions import DaemonNotRunning, CommunicationError
else:
    print(f'Error : {__name__} not called as script !'); exit()
    

return_code = 0

try:
    accelerometer = Adxl345() # Opens spi connection.
except DaemonNotRunning:
    return_code = 2
else:
    try:
        st_sts = accelerometer.self_test()

    except CommunicationError as e:
        if e.type == 'connection':
            return_code = 3
        elif e.type == 'streaming':
            return_code = 4
        else:
            raise Exception(f'Unknown CommunicationError type: ' + e.type + '!')

    else:
        if (st_sts == StSts.ST_FAIL):
            return_code = 5
    finally:
        accelerometer.close()

exit(return_code)
