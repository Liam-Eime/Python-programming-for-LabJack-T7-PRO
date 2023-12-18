from labjack import ljm
import numpy as np
import threading
import time
import atexit

# Define the thresholds and the last spike times for each channel
thresholds = [0.3, 0.3, 1.5]  # x, y, z
last_spike_times = [0, 0, 0]

# Initialize the maximum values and the flags for each channel
max_values = [0, 0, 0]
above_threshold = [False, False, False]

# Define process data function for stream
def process_data(data):
    buffer_period = 1.0  # Buffer period in seconds
    for i in range(NUMBER_OF_AINS):
        for value in data[i::NUMBER_OF_AINS]:
            current_time = time.time()
            if value > thresholds[i]:
                # Value is above the threshold, update the maximum value and the last spike time
                max_values[i] = max(max_values[i], value)
                last_spike_times[i] = current_time
                above_threshold[i] = True
            elif above_threshold[i] and current_time - last_spike_times[i] > buffer_period:
                # Value is below the threshold and the buffer period has passed, print and reset the maximum value
                print(f"\nMax value for channel {i}: {max_values[i]:.5f}g")
                max_values[i] = 0
                above_threshold[i] = False


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

# # Register cleanup function to be called when script finishes
# atexit.register(cleanup)

# Stream Configuration
aScanListNames = ["AIN%i" % i for i in range(FIRST_AIN_CHANNEL, FIRST_AIN_CHANNEL + NUMBER_OF_AINS)]  # Scan list names to stream
numAddresses = len(aScanListNames)
aScanList = ljm.namesToAddresses(numAddresses, aScanListNames)[0]
scanRate = 30000 # Hz
scansPerRead = int(scanRate)

totSkip = 0  # The number of skipped samples
raw_data = []
scan_backlog = 0

try:
    # Configure and start stream
    scanRate = ljm.eStreamStart(handle, scansPerRead, numAddresses, aScanList, scanRate)
    print("\nStream started with a scan rate of %0.0f Hz." % scanRate)
    while True:
        ret = ljm.eStreamRead(handle)
        start = time.time()
        new_data =(np.array(ret[0]) - 2.5).tolist()
        raw_data.extend(new_data)
        # Start a new thread to process the data
        t = threading.Thread(target=process_data, args=(new_data,))
        t.start()
        end = time.time()
        print(f"Time to process: {end - start}")
        print(f"Scan Backlog: {ret[1]}")
        print(f"Errors: {raw_data.count(-9999.0)}")
except Exception as e:
    print("\nUnexpected error: %s" % str(e))
except KeyboardInterrupt:  # Ctrl+C
    print("\nKeyboard Interrupt caught.")
finally:
    print("\nStop Stream")
    ljm.eStreamStop(handle)

    # Close handle
    ljm.close(handle)