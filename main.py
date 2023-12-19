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

# Initialize variables
thresholds = [0.3, 0.3, 1.5]  # x, y, z
last_spike_times = [0, 0, 0]
max_values = [0, 0, 0]
in_event = [False, False, False]
total_data_points = 0
raw_data = []
scan_backlog = 0


# Define process data function for stream
def process_data(data):
    global total_data_points
    for i in range(NUMBER_OF_AINS):
        for j, value in enumerate(data[i::NUMBER_OF_AINS]):
            # current_time = start_time + (total_data_points + j) / scanRate
            current_time = scan_system_times[total_data_points + j]
            total_data_points += 1
            if value > thresholds[i]:
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
    # total_data_points += len(data) // NUMBER_OF_AINS

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
scanRate = 30000 # Hz
scansPerRead = int(scanRate)

# Timestamp for data
# Correlate CORE_TIMER with system clock
core_timer_values = []
system_times = []
scan_system_times = []
for _ in range(100):
    start = time.time()
    core_timer = ljm.eReadName(handle, "CORE_TIMER")
    end = time.time()
    core_timer_values.append(core_timer)
    system_times.append((start + end) / 2)  # Assume CORE_TIMER is halfway between start and end
    
# Calculate average distance between CORE_TIMER and system clock
average_difference = np.mean(np.array(system_times) - np.array(core_timer_values))

# Perform data acquisition
try:
    # Configure and start stream
    scanRate = ljm.eStreamStart(handle, scansPerRead, numAddresses, aScanList, scanRate)
    print("\nStream started with a scan rate of %0.0f Hz." % scanRate)
    start_time = ljm.eReadName(handle, "STREAM_START_TIME_STAMP")
    
    while True:
        ret = ljm.eStreamRead(handle)
        new_data = ((np.array(ret[0]) - ACCEL_TO_G_OFFSET)/ACCEL_TO_G_SENSITIVITY).tolist()  # Convert to g
        raw_data.extend(new_data)
        
        # Calculate CORE_TIMER value for each scan
        scan_core_timer_values = (start_time + np.arange(len(ret[0])) / scanRate) / 40e6
        # Convert CORE_TIMER values to system times
        scan_system_times.extend(scan_core_timer_values + average_difference)
        
        # print size of new_data
        print(f"\nnew_data size: {len(new_data)}")
        # print size of scan_system_times
        print(f"\nscan_system_times size: {len(scan_system_times)}")
        
        # Start a new thread to process the data
        t = threading.Thread(target=process_data, args=(new_data,))
        t.start()
        print(f"\nTotal Errors: {raw_data.count(ljm.constants.DUMMY_VALUE)}")
except Exception as e:
    print("\nUnexpected error: %s" % str(e))
except KeyboardInterrupt:  # Ctrl+C
    print("\nKeyboard Interrupt caught.")
finally:
    print("\nStop Stream")
    ljm.eStreamStop(handle)

    # Close handle
    ljm.close(handle)