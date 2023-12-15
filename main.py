from labjack import ljm
import time
import atexit

# Define cleanup function to be called when script finishes
def cleanup():
    print("\nStop Stream")
    ljm.eStreamStop(handle)
    print("\nClose Handle")
    ljm.close(handle)

# Define constants for convenience
FIRST_AIN_CHANNEL = 0  # 0 = AIN0
NUMBER_OF_AINS = 3
OUTPUT_DIR = "data"
OUTPUT_FILENAME = "data.csv"

# Open first found LabJack T7 via USB.
handle = ljm.open(
    deviceType=ljm.constants.dtT7, 
    connectionType=ljm.constants.ctUSB,
    identifier="ANY"
)

# Print device info to confirm it is opened.
info = ljm.getHandleInfo(handle)
print("Opened a LabJack with Device type: %i, Connection type: %i,\n"
      "Serial number: %i, IP address: %s, Port: %i,\nMax bytes per MB: %i" %
      (info[0], info[1], info[2], ljm.numberToIP(info[3]), info[4], info[5]))

# T7 configuration
# Ensure triggered stream is disabled.
ljm.eWriteName(handle, "STREAM_TRIGGER_INDEX", 0)
# Enabling internally-clocked stream.
ljm.eWriteName(handle, "STREAM_CLOCK_SOURCE", 0)
# Set the stream buffer size to the maximum value, 32768 bytes.
max_buffer_size = 32768
ljm.eWriteName(handle, "STREAM_BUFFER_SIZE_BYTES", max_buffer_size)

# AIN ranges are +/-10 V, stream resolution index is 0 (default).
# Negative Channel = GND (single-ended), settling = 0 (default).
aNames = ["AIN_ALL_RANGE", "STREAM_RESOLUTION_INDEX", "AIN_ALL_NEGATIVE_CH", "STREAM_SETTLING_US"]
aValues = [10.0, 0, ljm.constants.GND, 0]

# Register cleanup function to be called when script finishes
atexit.register(cleanup)

# Stream Configuration
aScanListNames = ["AIN%i" % i for i in range(FIRST_AIN_CHANNEL, FIRST_AIN_CHANNEL + NUMBER_OF_AINS)]  # Scan list names to stream
numAddresses = len(aScanListNames)
aScanList = ljm.namesToAddresses(numAddresses, aScanListNames)[0]
scanRate = 30000 # Hz
scansPerRead = int(scanRate)

totSkip = 0  # The number of skipped samples
dat = []

try:
    # Configure and start stream
    scanRate = ljm.eStreamStart(handle, scansPerRead, numAddresses, aScanList, scanRate)
    print("\nStream started with a scan rate of %0.0f Hz." % scanRate)
    while True:
        ret = ljm.eStreamRead(handle)
        dat.extend(ret[0])
        # get rows of data
        rows = [dat[i:i+NUMBER_OF_AINS] for i in range(0, len(dat), NUMBER_OF_AINS)]
        print(rows)
        print(f"Errors: {dat.count(-9999.0)}")
except Exception as e:
    print("\nUnexpected error: %s" % str(e))
finally:
    print("\nStop Stream")
    ljm.eStreamStop(handle)

    # Close handle
    ljm.close(handle)