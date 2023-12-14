from labjack import ljm

# Define constants for convenience
FIRST_AIN_CHANNEL = 0  # 0 = AIN0
NUMBER_OF_AINS = 3

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

# Stream Configuration
aScanListNames = ["AIN%i" % i for i in range(FIRST_AIN_CHANNEL, FIRST_AIN_CHANNEL + NUMBER_OF_AINS)]  # Scan list names to stream
numAddresses = len(aScanListNames)
aScanList = ljm.namesToAddresses(numAddresses, aScanListNames)[0]
scanRate = 30000  # Hz
scansPerRead = int(scanRate / 2)

# Configure and start stream
scanRate = ljm.eStreamStart(handle, scansPerRead, numAddresses, aScanList, scanRate)
print("\nStream started with a scan rate of %0.0f Hz." % scanRate)

ret = ljm.eStreamRead(handle)
aData = ret[0]
scans = len(aData) / numAddresses

print("\nStop Stream")
ljm.eStreamStop(handle)

# Close handle
ljm.close(handle)




