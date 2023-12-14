from labjack import ljm
import atexit
import csv

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
scanRate = 1000  # Hz
scansPerRead = int(scanRate / 10)

totSkip = 0  # The number of skipped samples

try:
    # Configure and start stream
    scanRate = ljm.eStreamStart(handle, scansPerRead, numAddresses, aScanList, scanRate)
    print("\nStream started with a scan rate of %0.0f Hz." % scanRate)
    while True:
        ret = ljm.eStreamRead(handle)
        aData = ret[0]
        totSkip += aData.count(-9999.0) / NUMBER_OF_AINS
        scans = len(aData) / numAddresses
        print(type(aData), scans, totSkip)
        rows = [aData[i:i+NUMBER_OF_AINS] for i in range(0, len(aData), NUMBER_OF_AINS)]
        with open(OUTPUT_DIR + "/" + OUTPUT_FILENAME, "a", newline='') as f:
            writer = csv.writer(f)
            writer.writerows(rows)
except Exception as e:
    print("\nUnexpected error: %s" % str(e))
finally:
    print("\nStop Stream")
    ljm.eStreamStop(handle)

    # Close handle
    ljm.close(handle)