SIMULATION = True

T_DFLT = 1./1600.    # Default sample time to use (accelerometer sample time).

FSM_UPDATE_RATE_SEC = 0.25

VERBOSE = 1 # 0 -- Muted.
            # 1 -- Send errors to octoprint logger.
            # 2 -- Send all info messages to octoprint logger.
            # 3 -- Send printer messages to octoprint logger.


# Plugin tab behavior.
ACCLRMTR_LIVE_VIEW_RATE_SEC = 0.1
ACCLRMTR_LIVE_VIEW_NUM_SAMPLES = 200


# Calibration routine behavior.
GET_AXIS_INFO_TIMEOUT = 10.
CENTER_AXIS_TIMEOUT = 12.
MOVE_TO_CENTER_SPEED_MM_PER_MIN = 6000
FSM_SWEEP_START_DLY = 0.5
MAX_RETRIES_FOR_MISSED_SAMPLES = 2


SERVICE_URL = 'https://ogsxeca3e2.execute-api.us-east-2.amazonaws.com/beta/solve'
SERVICE_TIMEOUT_THD = 30
