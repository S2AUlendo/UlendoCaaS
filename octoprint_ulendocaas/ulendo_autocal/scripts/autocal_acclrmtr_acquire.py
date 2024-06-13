import sys
import struct
import os
from os import path
from threading import Thread
import argparse

if __package__ is None:
    sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))
    from lib.autocal_adxl345 import Adxl345, ACC_LSB_TO_MM_PER_SEC_SQR
    from autocal_exceptions import DaemonNotRunning, CommunicationError
else:
    print(f'Error: {__name__} not called as script!')
    exit()

def stop_handler(accelerometer):
    while True:
        command = input()
        if command == 'stop':
            accelerometer.external_stop = True
            return
        # Add more command handling here if needed
        # elif command == 'another_command':
        #     handle_another_command()

def main(data_folder):
    return_code = 0

    try:
        accelerometer = Adxl345(data_folder)  # Opens spi connection.
    except DaemonNotRunning:
        return_code = 2
    else:
        try:
            command_handler_thread = Thread(target=stop_handler, args=[accelerometer], daemon=True)
            command_handler_thread.start()

            accelerometer.acquire()

        except CommunicationError as e:
            if e.type == 'connection':
                return_code = 3
            elif e.type == 'streaming':
                return_code = 4
            else:
                raise Exception(f'Unknown CommunicationError type: {e.type}!')
        else:
            f_x_raw = open(path.join(data_folder, 'data', 'tmpxrw'), 'wb')
            f_y_raw = open(path.join(data_folder, 'data', 'tmpyrw'), 'wb')
            f_z_raw = open(path.join(data_folder, 'data', 'tmpzrw'), 'wb')

            for i, _ in enumerate(accelerometer.x_buff):
                f_x_raw.write(struct.pack('f', ACC_LSB_TO_MM_PER_SEC_SQR * float(accelerometer.x_buff[i])))
                f_y_raw.write(struct.pack('f', ACC_LSB_TO_MM_PER_SEC_SQR * float(accelerometer.y_buff[i])))
                f_z_raw.write(struct.pack('f', ACC_LSB_TO_MM_PER_SEC_SQR * float(accelerometer.z_buff[i])))

            f_x_raw.close()
            f_y_raw.close()
            f_z_raw.close()
        finally:
            accelerometer.close()

    os._exit(return_code)  # Note that built-in exit() will join threads before exiting (waits for stop input).

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Script to run accelerometer data acquisition.")
    parser.add_argument('data_folder', type=str, help="Directory to save the acquired data.")
    args = parser.parse_args()

    main(args.data_folder)
