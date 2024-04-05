## Script to run accelerometer data acquisition. Results are saved in local files
# and errors returned via exit code. Monitors for stop command to halt the data
# collection.

from threading import Thread

if __package__ is None:
    import sys, struct, os
    from os import path
    sys.path.append( path.dirname( path.dirname( path.abspath(__file__) ) ) )
    from lib.autocal_adxl345 import Adxl345, ACC_LSB_TO_MM_PER_SEC_SQR
    from autocal_exceptions import DaemonNotRunning, CommunicationError
else:
    print(f'Error : {__name__} not called as script !'); exit()



def stop_handler(accelerometer):
    while True:
        s = input()
        if s == 'stop': accelerometer.external_stop = True
        return


return_code = 0

try:
    accelerometer = Adxl345() # Opens spi connection.
except DaemonNotRunning:
    return_code = 2
else:
    try:
        stop_handler_thread = Thread(target=stop_handler, args=[accelerometer], daemon=True) # TODO: even with daemon true, this thread persists and prevents exit. find a non blocking way to monitor input()
        stop_handler_thread.start()

        accelerometer.acquire()

    except CommunicationError as e:
        if e.type == 'connection':
            return_code = 3
        elif e.type == 'streaming':
            return_code = 4
        else:
            raise Exception(f'Unknown CommunicationError type: ' + e.type + '!')

    else:
        f_x_raw = open(path.join(path.dirname(__file__), '..', 'data', 'tmpxrw'), 'wb')
        f_y_raw = open(path.join(path.dirname(__file__), '..', 'data', 'tmpyrw'), 'wb')
        f_z_raw = open(path.join(path.dirname(__file__), '..', 'data', 'tmpzrw'), 'wb')

        for i, _ in enumerate(accelerometer.x_buff):
            f_x_raw.write(struct.pack('f', ACC_LSB_TO_MM_PER_SEC_SQR*float(accelerometer.x_buff[i])))
            f_y_raw.write(struct.pack('f', ACC_LSB_TO_MM_PER_SEC_SQR*float(accelerometer.y_buff[i])))
            f_z_raw.write(struct.pack('f', ACC_LSB_TO_MM_PER_SEC_SQR*float(accelerometer.z_buff[i])))

        f_x_raw.close()
        f_y_raw.close()
        f_z_raw.close()
    finally:
        accelerometer.close()

os._exit(return_code) # Note that built-in exit() will join threads before exiting (waits for stop input).
