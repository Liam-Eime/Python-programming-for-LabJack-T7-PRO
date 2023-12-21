# Python-programming-for-LabJack-T7-PRO
Workspace for exploring Python programming with a LabJack T7-PRO data logger.\

Upon exploring the data rate capabilities of the logger it is believed that there is some underlying hardware issue that can cause initial stream reads to skip/miss some of the scans/samples from time to time. This corresponds to 1-2 seconds of data where skipped/missing scans occured for periods of the stream read.\

Another downside of the LabJack T7 series is when using stream mode (required for high scan/sample rates), the logger cannot provide timestamp information along with the data. Current version of program works around this, by an initial synchronization of the host computers system time, and the loggers CORE_TIMER. The timestamps are printed along with the peak values. What is still needed to help ensure accuracy is accounting for clock drift.\

Current version still has time to read data grow, but now incredibly slowly. This is still going to be an issue for permanant deployment of the logger because the stream buffer will overflow eventually as a result and end the program from running. At this stage I am stummped with how else to improve the efficiency of the stream reading to remove this growing read time.