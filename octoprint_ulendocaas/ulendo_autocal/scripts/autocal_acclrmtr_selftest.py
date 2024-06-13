## Script to run the accelerometer self test and return results via exit code.
import argparse

if __package__ is None:
    import sys
    from os import path
    sys.path.append( path.dirname( path.dirname( path.abspath(__file__) ) ) )
    from lib.autocal_adxl345 import Adxl345, StSts
    from autocal_exceptions import DaemonNotRunning, CommunicationError
else:
    print(f'Error : {__name__} not called as script !'); exit()
    
    
def main(data_folder):
    return_code = 0

    try:
        accelerometer = Adxl345(data_folder) # Opens spi connection.
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

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Script to run accelerometer data acquisition.")
    parser.add_argument('data_folder', type=str, help="Directory to save the acquired data.")
    args = parser.parse_args()

    main(args.data_folder)
