# IoT Network Traffic Generator

A modular, lightweight Python-based tool to generate synthetic IoT device telemetry traffic using multiple protocols (UDP, TCP, HTTP, and MQTT) and various traffic profiles (Normal, Burst, and DDoS Attack). Designed for network simulation, security testing, and analysis.

## Features

- **Multi-protocol Support**: Generates traffic over HTTP POST, TCP socket streams, UDP packets, and MQTT (connected to HiveMQ via raw binary encoding).
- **Concurrency**: Simulates multiple IoT devices running simultaneously using Python's threading library.
- **Traffic Profiles**:
  - `normal`: Simulates typical periodic updates from smart sensors (e.g., standard temperature/humidity readings).
  - `burst`: Simulates events/anomalies requiring higher transmission rates and spiked sensor values (e.g., HVAC failure or security door breach).
  - `attack`: Simulates a distributed denial of service (DDoS) flood from compromised devices to evaluate host resilience under network attacks.
- **Dynamic Control**: Change the `traffic_profile_override` configuration parameter in `config.json` at runtime, and the running generator will instantly update its behavior without restarting!
- **Zero External Dependencies**: Implemented using pure Python standard libraries.

---

## File Structure

- [config.json](file:///d:/iot%20network%20traffic%20generator/config.json) - Simulation configuration (device definitions, target endpoints, transmission rates).
- [generator.py](file:///d:/iot%20network%20traffic%20generator/generator.py) - Simulated IoT client engine that generates traffic.
- [receiver.py](file:///d:/iot%20network%20traffic%20generator/receiver.py) - Central receiver server that listens for and logs HTTP, TCP, and UDP traffic.

---

## How to Run

### Step 1: Start the Receiver Server
To capture, display, and log the generated traffic, start the receiver server:
```bash
python receiver.py
```
The server will start listening on the configured ports (5005 for UDP, 5006 for TCP, and 5007 for HTTP) and print out incoming data packets in color-coded blocks. It also logs cumulative transmission statistics every 10 seconds.

### Step 2: Start the IoT Traffic Generator
In a new terminal window, run the generator script:
```bash
python generator.py
```
This will read the device metadata from `config.json` and boot the simulation threads.

---

## Dynamic Traffic Profile Switching

You can modify the traffic characteristics on the fly. Open `config.json` and change `"traffic_profile_override"` in `"global_settings"`:

1. **For Normal Simulation**:
   ```json
   "global_settings": {
     "simulation_duration_seconds": 0,
     "traffic_profile_override": null
   }
   ```
2. **For Anomalies/Events Simulation (Burst Mode)**:
   ```json
   "global_settings": {
     "simulation_duration_seconds": 0,
     "traffic_profile_override": "burst"
   }
   ```
3. **For DDoS Botnet Attack Simulation (Attack Mode)**:
   ```json
   "global_settings": {
     "simulation_duration_seconds": 0,
     "traffic_profile_override": "attack"
   }
   ```

Save the file. The running `generator.py` process will detect the changes in real-time, print a log announcement, and alter packet generation rates and payloads accordingly.
