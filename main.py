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
THRESHOLDS = np.array([0.6, 0.6, 1.2])  # x, y, z
TICK_PER_SECOND = 40e6  # T7 core timer ticks per second

# Initialize variables
last_spike_times = np.zeros(NUMBER_OF_AINS)
max_values = np.zeros(NUMBER_OF_AINS)
in_event = np.array([False, False, False])
total_data_points = 0
raw_data = []
scan_backlog = 0
total_errors = 0
total_time_elapsed = 0

# Create a lock for scan_system_times
scan_system_times_lock = threading.Lock()

# Define process data function for stream
scan_system_times = []

def process_data(data):
    global total_data_points, max_values, last_spike_times, in_event
    # Convert data to numpy arrays
    data = np.array(data)
    # Reshape the data into a 2D array with one row per channel
    data = data.reshape(-1, NUMBER_OF_AINS).T
    current_time = scan_system_times[total_data_points:total_data_points + data.shape[1]]
    # Calculate a boolean array where the data is above the threshold
    above_threshold = data > THRESHOLDS[:, None]
    # Update max_values and last_spike_times where the data is above the threshold
    for i in range(NUMBER_OF_AINS):
        if above_threshold[i].any():
            max_values[i] = np.maximum(max_values[i], data[i][above_threshold[i]].max())
            last_spike_times[i] = current_time[above_threshold[i]].max()
            in_event[i] = True
    # Calculate a boolean array where the data is below the threshold and the buffer period has passed
    below_threshold_and_buffer_passed = np.logical_and(~above_threshold, (current_time - last_spike_times[:, None]) > BUFFER_PERIOD)
    # Print and reset max_values where below_threshold_and_buffer_passed is True and an event has occurred
    for i in np.where(np.logical_and(below_threshold_and_buffer_passed.any(axis=1), in_event))[0]:
        time_str = datetime.fromtimestamp(last_spike_times[i]).strftime('%y/%m/%d %H:%M:%S.%f')[:21]
        print(f"\nMax value for channel {i}: {max_values[i]:.5f}g at {time_str}")
        max_values[i] = 0
        in_event[i] = False
    total_data_points += data.shape[1]
    

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
        starting = time.time()
        new_data = ((np.array(ret[0]) - ACCEL_TO_G_OFFSET)/ACCEL_TO_G_SENSITIVITY).tolist()  # Convert to g
        raw_data.extend(new_data)
        # Calculate the scan timestamps for the new data
        num_new_scans = len(new_data) / NUMBER_OF_AINS
        new_scanTimesElapsed = np.arange(num_new_scans) / scanRate
        total_time_elapsed += new_scanTimesElapsed[-1]
        new_scanTimestamps = streamStartTimeSystemAligned + new_scanTimesElapsed + total_time_elapsed
        with scan_system_times_lock:
            # scan_system_times = scanTimestamps
            scan_system_times = np.concatenate((scan_system_times, new_scanTimestamps))
        # Start a new thread to process the data
        t = threading.Thread(target=process_data, args=(new_data,))
        t.start()
        # Print total errors
        # total_errors += new_data.count(ljm.constants.DUMMY_VALUE)
        # print(f"\nTotal Errors: {total_errors}")
        ending = time.time()
        print(f"\nTime to read data: {ending - starting:.5f} s")
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