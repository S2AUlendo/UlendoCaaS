class Adxl345Error(Exception): pass
class DaemonNotRunning(Adxl345Error): pass
class CommunicationError(Adxl345Error):
    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self.type = kwargs.get('type')


class ChirpResultError(Exception): pass
class NoSignalError(ChirpResultError): pass
class SignalSyncError(ChirpResultError): pass


class SolverError(Exception): pass
class NoQualifiedSolution(SolverError): pass
class NoVibrationDetected(SolverError): pass

class AutocalInternalServerError(Exception): pass
class DataFileNotFoundError(Exception): pass
