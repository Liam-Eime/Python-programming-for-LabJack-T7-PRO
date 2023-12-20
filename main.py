from labjack import ljm
from datetime import datetime
import numpy as np
import threading
import time
import atexit

# Define constants for convenience
FIRST_AIN_CHANNEL = 0  # 0 = AIN0
NUMBER_OF_AINS = 3
OUTPUT_DIR = "data"
OUTPUT_FILENAME = "data.csv"
ACCEL_TO_G_OFFSET = 2.5  # 2.5 V = 0 g
ACCEL_TO_G_SENSITIVITY = 1  # 1 V/g
BUFFER_PERIOD = 0.05  # Buffer period in seconds
SCAN_RATE = 30000  # Hz
THRESHOLDS = [0.6, 0.6, 1.2]  # x, y, z
TICK_PER_SECOND = 40e6  # T7 core timer ticks per second

# Initialize variables
last_spike_times = [0, 0, 0]
max_values = [0, 0, 0]
in_event = [False, False, False]
total_data_points = 0
raw_data = []
scan_backlog = 0

# Create a lock for scan_system_times
scan_system_times_lock = threading.Lock()

# Define process data function for stream
scan_system_times = []
def process_data(data):
    global total_data_points
    for i in range(NUMBER_OF_AINS):
        for j, value in enumerate(data[i::NUMBER_OF_AINS]):
            with scan_system_times_lock:
                current_time = scan_system_times[total_data_points + j]
            if value > THRESHOLDS[i]:
                if value > max_values[i]:
                    # Value is above the current maximum, update the maximum value and the last spike time
                    max_values[i] = value
                    last_spike_times[i] = current_time
                in_event[i] = True
            elif in_event[i] and current_time - last_spike_times[i] > BUFFER_PERIOD:
                # Value is below the threshold and the buffer period has passed, print and reset the maximum value
                time_str = datetime.fromtimestamp(last_spike_times[i]).strftime('%y/%m/%d %H:%M:%S.%f')[:21]
                print(f"\nMax value for channel {i}: {max_values[i]:.5f}g at {time_str}")
                max_values[i] = 0
                in_event[i] = False
    total_data_points += len(data) // NUMBER_OF_AINS

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
ljm.eWriteNames(handle, len(aNames), aNames, aValues)

# Stream Configuration
aScanListNames = ["AIN%i" % i for i in range(FIRST_AIN_CHANNEL, FIRST_AIN_CHANNEL + NUMBER_OF_AINS)]  # Scan list names to stream
numAddresses = len(aScanListNames)
aScanList = ljm.namesToAddresses(numAddresses, aScanListNames)[0]
scansPerRead = int(SCAN_RATE)

def tick_diff_with_roll(start, end):  # The core timer is a uint32 value that will overflow/rollover
    diffTicks = 0
    if end < start:
        diffTicks = 0xFFFFFFFF - start + end
    else:
        diffTicks = end - start
    return diffTicks

# Perform data acquisition
try:
    # Configure and start stream
    scanRate = ljm.eStreamStart(handle, scansPerRead, numAddresses, aScanList, SCAN_RATE)
    print("\nStream started with a scan rate of %0.0f Hz." % scanRate)
    
    # Get stream start time as a CORE_TIMER value
    start_time = ljm.eReadName(handle, "STREAM_START_TIME_STAMP")
    
    # Read CORE_TIMER
    syncCoreRead = ljm.eReadName(handle, "CORE_TIMER")

    # Calculate system timestamp corresponding to the start of stream
    sysTimestamp = time.time()
    diffTicks = tick_diff_with_roll(start_time, syncCoreRead)  # start_time is the var storing the stream start timestamp
    diffSeconds = diffTicks / TICK_PER_SECOND 
    streamStartTimeSystemAligned = sysTimestamp - diffSeconds  # system timestamp corresponding to the start of stream
    
    while True:
        # Read stream data
        ret = ljm.eStreamRead(handle)
        new_data = ((np.array(ret[0]) - ACCEL_TO_G_OFFSET)/ACCEL_TO_G_SENSITIVITY).tolist()  # Convert to g
        raw_data.extend(new_data)
        num_scans = len(raw_data) / NUMBER_OF_AINS
        scanTimesElapsed = np.arange(num_scans) / scanRate
        scanTimestamps = streamStartTimeSystemAligned + scanTimesElapsed
        with scan_system_times_lock:
            scan_system_times = scanTimestamps
        # Start a new thread to process the data
        t = threading.Thread(target=process_data, args=(new_data,))
        t.start()
        # Print total errors
        print(f"\nTotal Errors: {raw_data.count(ljm.constants.DUMMY_VALUE)}")
except Exception as e:
    print("\nUnexpected error: %s" % str(e))
except KeyboardInterrupt:  # Ctrl+C
    print("\nKeyboard Interrupt caught.")
finally:
    # Stop stream
    print("\nStop Stream")
    ljm.eStreamStop(handle)
    # Close handle
    ljm.close(handle)