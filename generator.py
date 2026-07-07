import socket
import threading
import json
import time
import random
import urllib.request
import urllib.error

# Color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

# Helper to encode MQTT remaining length
def encode_remaining_length(length):
    encoded = bytearray()
    while True:
        digit = length % 128
        length = length // 128
        if length > 0:
            digit = digit | 0x80
        encoded.append(digit)
        if length <= 0:
            break
    return bytes(encoded)

# Helper to build MQTT CONNECT packet
def make_mqtt_connect_packet(client_id):
    proto_name = b"\x00\x04MQTT"
    proto_level = b"\x04"  # Version 3.1.1
    connect_flags = b"\x02"  # Clean session
    keep_alive = b"\x00\x3c"  # 60s
    
    client_bytes = client_id.encode('utf-8')
    client_len = len(client_bytes).to_bytes(2, 'big')
    
    payload = proto_name + proto_level + connect_flags + keep_alive + client_len + client_bytes
    rem_len = encode_remaining_length(len(payload))
    return bytes([0x10]) + rem_len + payload

# Helper to build MQTT PUBLISH packet
def make_mqtt_publish_packet(topic, message):
    topic_bytes = topic.encode('utf-8')
    topic_len = len(topic_bytes).to_bytes(2, 'big')
    
    msg_bytes = message.encode('utf-8')
    
    payload = topic_len + topic_bytes + msg_bytes
    rem_len = encode_remaining_length(len(payload))
    return bytes([0x30]) + rem_len + payload

# Generate simulated sensor data
def generate_sensor_data(device_id, device_type, profile):
    timestamp = time.time()
    
    if profile == "attack":
        # Malicious high-rate payload / generic noise
        return {
            "device_id": device_id,
            "timestamp": timestamp,
            "status": "OVERFLOW_ATTACK",
            "payload_noise": "A" * random.randint(100, 500)
        }
    
    # Base data
    data = {
        "device_id": device_id,
        "timestamp": timestamp,
        "device_type": device_type
    }
    
    if device_type == "temperature_humidity":
        if profile == "burst":
            # Anomaly: Fire or HVAC failure
            data["data"] = {
                "temperature": round(random.uniform(70.0, 95.0), 2),
                "humidity": round(random.uniform(10.0, 20.0), 2),
                "status": "CRITICAL_HIGH_TEMP"
            }
        else:
            # Normal environmental data
            data["data"] = {
                "temperature": round(random.uniform(20.0, 26.0), 2),
                "humidity": round(random.uniform(40.0, 60.0), 2),
                "status": "NORMAL"
            }
            
    elif device_type == "security_door":
        if profile == "burst":
            # Anomaly: Intrusions/forced entries
            data["data"] = {
                "door_state": "OPEN_FORCED",
                "motion_detected": True,
                "alarm_triggered": True
            }
        else:
            # Normal door state
            data["data"] = {
                "door_state": "CLOSED" if random.random() > 0.05 else "OPEN",
                "motion_detected": False,
                "alarm_triggered": False
            }
            
    elif device_type == "hvac_control":
        if profile == "burst":
            data["data"] = {
                "fan_speed_rpm": 4500,
                "compressor_load_pct": 100.0,
                "filter_health_pct": 12.0
            }
        else:
            data["data"] = {
                "fan_speed_rpm": 1200,
                "compressor_load_pct": 45.5,
                "filter_health_pct": 89.2
            }
            
    elif device_type == "smart_power_meter":
        if profile == "burst":
            data["data"] = {
                "voltage": round(random.uniform(180.0, 190.0), 2),  # Brownout simulation
                "current_amps": round(random.uniform(45.0, 60.0), 2),
                "power_watts": round(random.uniform(8000.0, 11000.0), 2)
            }
        else:
            data["data"] = {
                "voltage": round(random.uniform(220.0, 240.0), 2),
                "current_amps": round(random.uniform(2.0, 10.0), 2),
                "power_watts": round(random.uniform(440.0, 2400.0), 2)
            }
            
    else:
        data["data"] = {"generic_value": random.randint(0, 100)}
        
    return data

# UDP Traffic Sender
def send_udp_traffic(target_host, target_port, device_id, device_type, interval, stop_event, profile_func):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print(f"[UDP Sender] Started thread for Device: {device_id} targeting {target_host}:{target_port}")
    
    while not stop_event.is_set():
        profile = profile_func()
        payload = generate_sensor_data(device_id, device_type, profile)
        message = json.dumps(payload).encode('utf-8')
        
        try:
            sock.sendto(message, (target_host, target_port))
        except Exception as e:
            pass
            
        # Adjust sleep based on profile
        if profile == "attack":
            time.sleep(0.01)  # Flood rate (10ms)
        elif profile == "burst":
            time.sleep(interval / 4)  # Faster updates
        else:
            time.sleep(interval)
            
    sock.close()

# TCP Traffic Sender
def send_tcp_traffic(target_host, target_port, device_id, device_type, interval, stop_event, profile_func):
    print(f"[TCP Sender] Started thread for Device: {device_id} targeting {target_host}:{target_port}")
    
    while not stop_event.is_set():
        profile = profile_func()
        payload = generate_sensor_data(device_id, device_type, profile)
        message = json.dumps(payload).encode('utf-8')
        
        try:
            # Connect, send, and close connection (standard for many TCP-based IoT endpoints)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2.0)
            sock.connect((target_host, target_port))
            sock.sendall(message)
            sock.close()
        except Exception as e:
            pass
            
        if profile == "attack":
            time.sleep(0.02)  # Flood rate
        elif profile == "burst":
            time.sleep(interval / 4)
        else:
            time.sleep(interval)

# HTTP Traffic Sender
def send_http_traffic(target_host, target_port, device_id, device_type, interval, stop_event, profile_func):
    url = f"http://{target_host}:{target_port}/"
    print(f"[HTTP Sender] Started thread for Device: {device_id} targeting {url}")
    
    while not stop_event.is_set():
        profile = profile_func()
        payload = generate_sensor_data(device_id, device_type, profile)
        data = json.dumps(payload).encode('utf-8')
        
        req = urllib.request.Request(
            url, 
            data=data, 
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        
        try:
            with urllib.request.urlopen(req, timeout=2.0) as response:
                response.read()
        except Exception as e:
            pass
            
        if profile == "attack":
            time.sleep(0.05)  # HTTP requests are slower, flood at 50ms
        elif profile == "burst":
            time.sleep(interval / 4)
        else:
            time.sleep(interval)

# MQTT Traffic Sender (Raw Sockets)
def send_mqtt_traffic(broker_host, broker_port, device_id, device_type, interval, stop_event, profile_func):
    print(f"[MQTT Sender] Started thread for Device: {device_id} targeting broker {broker_host}:{broker_port}")
    topic = f"iot/devices/{device_id}/telemetry"
    
    while not stop_event.is_set():
        profile = profile_func()
        payload = generate_sensor_data(device_id, device_type, profile)
        message = json.dumps(payload)
        
        try:
            # Connect to broker
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((broker_host, broker_port))
            
            # Send CONNECT
            connect_pkt = make_mqtt_connect_packet(device_id)
            sock.sendall(connect_pkt)
            connack = sock.recv(4)  # Wait for CONNACK
            
            # Send PUBLISH
            pub_pkt = make_mqtt_publish_packet(topic, message)
            sock.sendall(pub_pkt)
            
            # Send DISCONNECT gracefully
            sock.sendall(b"\xe0\x00")
            sock.close()
        except Exception as e:
            pass
            
        if profile == "attack":
            time.sleep(0.02)
        elif profile == "burst":
            time.sleep(interval / 4)
        else:
            time.sleep(interval)

def main():
    # Load configuration
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        print("config.json not found! Exiting.")
        return

    host = config.get("target_host", "127.0.0.1")
    udp_port = config.get("udp_port", 5005)
    tcp_port = config.get("tcp_port", 5006)
    http_port = config.get("http_port", 5007)
    mqtt_broker = config.get("mqtt_broker", "broker.hivemq.com")
    mqtt_port = config.get("mqtt_port", 1883)
    
    devices = config.get("devices", [])
    global_settings = config.get("global_settings", {})
    duration = global_settings.get("simulation_duration_seconds", 0)
    
    # Thread control event
    stop_event = threading.Event()
    threads = []
    
    # Function to dynamically resolve a device's current profile (supporting global override)
    def get_profile_resolver(device_profile):
        return lambda: (global_settings.get("traffic_profile_override") or device_profile)

    print(f"=== Starting IoT Traffic Generator ===")
    print(f"Targeting Local Host: {host} (UDP:{udp_port}, TCP:{tcp_port}, HTTP:{http_port})")
    print(f"Targeting MQTT Broker: {mqtt_broker}:{mqtt_port}")
    print(f"Active Devices: {len(devices)}")
    print(f"Press Ctrl+C to terminate simulation.\n")

    # Start generator threads
    for dev in devices:
        dev_id = dev.get("device_id")
        dev_type = dev.get("device_type")
        proto = dev.get("protocol").lower()
        interval = dev.get("interval_seconds", 5.0)
        dev_profile = dev.get("traffic_profile", "normal")
        
        profile_func = get_profile_resolver(dev_profile)
        
        if proto == "udp":
            t = threading.Thread(
                target=send_udp_traffic, 
                args=(host, udp_port, dev_id, dev_type, interval, stop_event, profile_func),
                daemon=True
            )
        elif proto == "tcp":
            t = threading.Thread(
                target=send_tcp_traffic, 
                args=(host, tcp_port, dev_id, dev_type, interval, stop_event, profile_func),
                daemon=True
            )
        elif proto == "http":
            t = threading.Thread(
                target=send_http_traffic, 
                args=(host, http_port, dev_id, dev_type, interval, stop_event, profile_func),
                daemon=True
            )
        elif proto == "mqtt":
            t = threading.Thread(
                target=send_mqtt_traffic, 
                args=(mqtt_broker, mqtt_port, dev_id, dev_type, interval, stop_event, profile_func),
                daemon=True
            )
        else:
            print(f"Unknown protocol '{proto}' for device '{dev_id}'")
            continue
            
        threads.append(t)
        t.start()

    # Handle simulation run duration
    if duration > 0:
        print(f"\nSimulation scheduled to run for {duration} seconds...")
        time.sleep(duration)
        print("\nDuration reached. Stopping simulation...")
        stop_event.set()
    else:
        # Run indefinitely until user aborts
        try:
            while True:
                # Dynamic terminal monitoring config changes (like global_settings overrides)
                # We reload config.json every few seconds to allow runtime control
                time.sleep(2)
                try:
                    with open('config.json', 'r') as f:
                        updated_config = json.load(f)
                    new_override = updated_config.get("global_settings", {}).get("traffic_profile_override")
                    if new_override != global_settings.get("traffic_profile_override"):
                        global_settings["traffic_profile_override"] = new_override
                        print(f"\n[SYSTEM ALERT] Global profile override changed to: {new_override}\n")
                except Exception:
                    pass
        except KeyboardInterrupt:
            print("\nShutting down simulation...")
            stop_event.set()

    # Join threads
    for t in threads:
        t.join(timeout=1.0)
    print("IoT Traffic Generator stopped.")

if __name__ == '__main__':
    main()
