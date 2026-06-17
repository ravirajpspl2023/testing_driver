from enum import IntEnum
import ctypes

class FocasError(IntEnum):
    EW_OK       = 0   # Normal termination
    EW_FUNC     = 1   # Function not executed / not available
    EW_LENGTH   = 2   # Data block length error
    EW_NUMBER   = 3   # Data number error
    EW_ATTRIB   = 4   # Data attribute error
    EW_DATA     = 5   # Data error
    EW_NOOPT    = 6   # No option
    EW_PROT     = 7   # Write protection
    EW_OVRFLOW  = 8   # Memory overflow
    EW_PARAM    = 9   # Parameter error
    EW_BUFFER   = 10  # Buffer empty/full
    EW_PATH     = 11  # Path number error
    EW_MODE     = 12  # CNC mode error
    EW_REJECT   = 13  # CNC execution rejected
    EW_DTSRVR   = 14  # Data server error
    EW_ALARM    = 15  # Alarm in CNC
    EW_STOP     = 16  # Stop / Emergency
    EW_PASSWD   = 17  # Data protection
    
    # Negative codes (common connection issues)
    EW_BUSY     = -1
    EW_RESET    = -2
    EW_UNEXP    = -6
    EW_HANDLE   = -8
    EW_VERSION  = -7
    EW_SOCKET   = -16
    EW_PROTOCOL = -17
    # ... add more as needed

def get_error_message(ret: int) -> str:
    try:
        return FocasError(ret).name
    except ValueError:
        return f"Unknown error code: {ret}"