import socket
import threading
import json
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from collections import deque
from pcap_logger import PcapLogger

# Color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

# Global Configuration variables
global_host = "127.0.0.1"
global_udp_port = 5005
global_tcp_port = 5006
global_http_port = 5007

# Statistics tracker
stats = {
    'udp_packets': 0,
    'tcp_packets': 0,
    'http_packets': 0,
    'mqtt_packets': 0,
    'total_bytes': 0,
    'bytes_last_sec': 0,
    'start_time': time.time()
}
stats_lock = threading.Lock()

# Rolling buffer of recent logs for dashboard (max 15 items)
recent_logs = deque(maxlen=15)

# IDS/IPS States
blocked_devices = set()
device_packet_times = {}
alerts = deque(maxlen=20)
firewall_enabled = True

# Initialize PCAP Logger
pcap_writer = PcapLogger("capture.pcap")

def update_stats(protocol, byte_count):
    with stats_lock:
        stats[f'{protocol.lower()}_packets'] += 1
        stats['total_bytes'] += byte_count
        stats['bytes_last_sec'] += byte_count

def log_packet(protocol, text):
    t = time.strftime('%H:%M:%S')
    with stats_lock:
        recent_logs.append({
            'time': t,
            'proto': protocol.upper(),
            'text': text
        })

# Intrusion Detection System (IDS) Engine
def analyze_traffic(device_id, protocol, payload):
    if not device_id:
        return
    
    current_time = time.time()
    
    with stats_lock:
        if device_id not in device_packet_times:
            device_packet_times[device_id] = []
        
        timestamps = device_packet_times[device_id]
        timestamps.append(current_time)
        
        # Prune timestamps older than 5.0 seconds
        pruned_timestamps = [t for t in timestamps if current_time - t <= 5.0]
        device_packet_times[device_id] = pruned_timestamps
        
        # Compute packets per second (pps) rate over 5s window
        rate = len(pruned_timestamps) / 5.0
        
        # 1. Rate-limiting check: DDoS flood detection
        if rate > 12.0 and device_id not in blocked_devices:
            blocked_devices.add(device_id)
            alert_text = f"DDoS flood detected! Rate: {rate:.1f} pps. Firewall rule applied: Blocking device."
            alerts.append({
                'time': time.strftime('%H:%M:%S'),
                'device_id': device_id,
                'type': 'DDoS Flooding Threat',
                'severity': 'HIGH',
                'message': alert_text
            })
            print(f"{Colors.FAIL}[IDS ALERT] {alert_text} Device: {device_id}{Colors.ENDC}")
            return
            
        # 2. Signature-based check: Malicious status signature
        if payload.get('status') == 'OVERFLOW_ATTACK' and device_id not in blocked_devices:
            blocked_devices.add(device_id)
            alert_text = "Malicious botnet payload signature detected. Firewall rule applied: Blocking device."
            alerts.append({
                'time': time.strftime('%H:%M:%S'),
                'device_id': device_id,
                'type': 'Botnet Payload Threat',
                'severity': 'HIGH',
                'message': alert_text
            })
            print(f"{Colors.FAIL}[IDS ALERT] {alert_text} Device: {device_id}{Colors.ENDC}")
            return
            
        # 3. Operational Anomaly checks
        data = payload.get('data')
        if data:
            # Temperature Anomaly
            temp = data.get('temperature')
            if temp is not None and temp > 75.0:
                alert_text = f"Critical environment alert: Temperature reported {temp}°C (exceeds threshold 75°C)."
                alerts.append({
                    'time': time.strftime('%H:%M:%S'),
                    'device_id': device_id,
                    'type': 'Critical Temperature',
                    'severity': 'MEDIUM',
                    'message': alert_text
                })
                print(f"{Colors.WARNING}[IDS ALERT] {alert_text} Device: {device_id}{Colors.ENDC}")
                
            # Door intrusion Anomaly
            door_state = data.get('door_state')
            if door_state == 'OPEN_FORCED':
                alert_text = "Security intrusion alert: Entry door opened by force! Alarm triggered."
                alerts.append({
                    'time': time.strftime('%H:%M:%S'),
                    'device_id': device_id,
                    'type': 'Security Breach',
                    'severity': 'MEDIUM',
                    'message': alert_text
                })
                print(f"{Colors.WARNING}[IDS ALERT] {alert_text} Device: {device_id}{Colors.ENDC}")
                
            # Power grid anomaly
            voltage = data.get('voltage')
            if voltage is not None and voltage < 195.0:
                alert_text = f"Power grid drop anomaly: Line voltage dropped to {voltage}V."
                alerts.append({
                    'time': time.strftime('%H:%M:%S'),
                    'device_id': device_id,
                    'type': 'Voltage Drop Anomaly',
                    'severity': 'MEDIUM',
                    'message': alert_text
                })
                print(f"{Colors.WARNING}[IDS ALERT] {alert_text} Device: {device_id}{Colors.ENDC}")

def print_stats():
    while True:
        time.sleep(10)
        with stats_lock:
            elapsed = time.time() - stats['start_time']
            print(f"\n{Colors.HEADER}=== RECEIVER STATISTICS (Elapsed: {elapsed:.1f}s) ==={Colors.ENDC}")
            print(f"UDP Packets:  {stats['udp_packets']}")
            print(f"TCP Packets:  {stats['tcp_packets']}")
            print(f"HTTP Packets: {stats['http_packets']}")
            print(f"MQTT Packets: {stats['mqtt_packets']}")
            print(f"Total Bytes:  {stats['total_bytes']} bytes")
            print(f"Blocked Nodes: {len(blocked_devices)}")
            print(f"Avg Rate:     {stats['total_bytes'] / max(1, elapsed):.2f} B/s")
            print(f"{Colors.HEADER}=================================================={Colors.ENDC}\n")

# UDP Server
def run_udp_server(host, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((host, port))
        print(f"{Colors.OKBLUE}[UDP Server] Listening on {host}:{port}{Colors.ENDC}")
        while True:
            data, addr = sock.recvfrom(4096)
            
            # Extract device_id to check blocked status
            device_id = None
            payload = {}
            try:
                payload = json.loads(data.decode('utf-8'))
                device_id = payload.get('device_id')
            except Exception:
                pass
            
            with stats_lock:
                is_blocked = (device_id in blocked_devices) and firewall_enabled if device_id else False
                
            if is_blocked:
                # Active prevention: drop packet silently
                print(f"{Colors.FAIL}[IPS FIREWALL] Blocked UDP packet dropped from Device: {device_id}{Colors.ENDC}")
                continue
                
            update_stats('udp', len(data))
            
            # Log to PCAP
            pcap_writer.write_packet(addr[0], addr[1], host, port, 'udp', data)
            
            try:
                dev_id = payload.get('device_id')
                data_val = payload.get('data')
                
                log_packet('udp', f"Device: {dev_id} | Data: {data_val}")
                print(f"{Colors.OKBLUE}[UDP] Received from {addr[0]}:{addr[1]} -> Device: {dev_id} | Data: {data_val}{Colors.ENDC}")
                
                if dev_id:
                    analyze_traffic(dev_id, 'udp', payload)
            except Exception as e:
                # In case of attack traffic/raw flood
                raw_text = data.decode('utf-8', errors='ignore')
                log_packet('udp', f"Raw packet: {raw_text[:60]}")
                print(f"{Colors.WARNING}[UDP] Raw/Malformed data received ({len(data)} bytes) from {addr}{Colors.ENDC}")
    except Exception as e:
        print(f"{Colors.FAIL}[UDP Server Error] {e}{Colors.ENDC}")
    finally:
        sock.close()

# TCP Client Handler
def handle_tcp_client(client_sock, addr, host, port):
    try:
        while True:
            data = client_sock.recv(4096)
            if not data:
                break
            
            device_id = None
            payload = {}
            try:
                payload = json.loads(data.decode('utf-8'))
                device_id = payload.get('device_id')
            except Exception:
                pass
                
            with stats_lock:
                is_blocked = (device_id in blocked_devices) and firewall_enabled if device_id else False
                
            if is_blocked:
                print(f"{Colors.FAIL}[IPS FIREWALL] Blocked TCP stream packet dropped from Device: {device_id}{Colors.ENDC}")
                continue
                
            update_stats('tcp', len(data))
            
            # Log to PCAP
            pcap_writer.write_packet(addr[0], addr[1], host, port, 'tcp', data)
            
            try:
                dev_id = payload.get('device_id')
                data_val = payload.get('data')
                
                log_packet('tcp', f"Device: {dev_id} | Data: {data_val}")
                print(f"{Colors.OKCYAN}[TCP] Received from {addr[0]}:{addr[1]} -> Device: {dev_id} | Data: {data_val}{Colors.ENDC}")
                
                if dev_id:
                    analyze_traffic(dev_id, 'tcp', payload)
            except Exception as e:
                raw_text = data.decode('utf-8', errors='ignore')
                log_packet('tcp', f"Raw packet: {raw_text[:60]}")
                print(f"{Colors.WARNING}[TCP] Raw data received ({len(data)} bytes) from {addr}{Colors.ENDC}")
    except Exception as e:
        pass
    finally:
        client_sock.close()

# TCP Server
def run_tcp_server(host, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
        sock.listen(10)
        print(f"{Colors.OKCYAN}[TCP Server] Listening on {host}:{port}{Colors.ENDC}")
        while True:
            client_sock, addr = sock.accept()
            threading.Thread(target=handle_tcp_client, args=(client_sock, addr, host, port), daemon=True).start()
    except Exception as e:
        print(f"{Colors.FAIL}[TCP Server Error] {e}{Colors.ENDC}")
    finally:
        sock.close()

# HTTP Request Handler
class IoTHTTPRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def do_GET(self):
        if self.path in ('/', '/dashboard'):
            try:
                with open('dashboard.html', 'r', encoding='utf-8') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                self.wfile.write(content.encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f"Error loading dashboard: {e}".encode('utf-8'))
        elif self.path == '/api/stats':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            
            # Fetch active override profile from config.json
            active_profile = None
            try:
                with open('config.json', 'r') as f:
                    config = json.load(f)
                active_profile = config.get("global_settings", {}).get("traffic_profile_override")
            except Exception:
                pass

            elapsed = time.time() - stats['start_time']
            with stats_lock:
                current_rate = stats['bytes_last_sec']
                stats['bytes_last_sec'] = 0  # Reset counter for next second
                
                payload = {
                    'udp_packets': stats['udp_packets'],
                    'tcp_packets': stats['tcp_packets'],
                    'http_packets': stats['http_packets'],
                    'mqtt_packets': stats['mqtt_packets'],
                    'total_bytes': stats['total_bytes'],
                    'avg_rate': stats['total_bytes'] / max(1, elapsed),
                    'current_rate': current_rate,
                    'elapsed': elapsed,
                    'active_profile': active_profile,
                    'recent_logs': list(recent_logs),
                    'blocked_devices': list(blocked_devices),
                    'alerts': list(alerts),
                    'firewall_enabled': firewall_enabled
                }
            self.wfile.write(json.dumps(payload).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'{"error": "Not Found"}')

    def do_POST(self):
        if self.path == '/api/config':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data.decode('utf-8'))
                override = data.get("traffic_profile_override")
                
                with open('config.json', 'r') as f:
                    config = json.load(f)
                
                config["global_settings"]["traffic_profile_override"] = override
                
                with open('config.json', 'w') as f:
                    json.dump(config, f, indent=2)
                    
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"status": "success"}')
            except Exception as e:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(f'{{"error": "{e}"}}'.encode('utf-8'))
                
        elif self.path == '/api/unblock':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data.decode('utf-8'))
                device_id = data.get("device_id")
                
                with stats_lock:
                    if device_id in blocked_devices:
                        blocked_devices.remove(device_id)
                        # Reset timestamp tracker for this device
                        if device_id in device_packet_times:
                            device_packet_times[device_id] = []
                            
                print(f"{Colors.OKGREEN}[IPS FIREWALL] Device manually unblocked: {device_id}{Colors.ENDC}")
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"status": "success"}')
            except Exception as e:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(f'{{"error": "{e}"}}'.encode('utf-8'))
                
        elif self.path == '/api/firewall':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data.decode('utf-8'))
                enabled = data.get("enabled", True)
                
                global firewall_enabled
                with stats_lock:
                    firewall_enabled = bool(enabled)
                    
                status_str = "ENABLED (IPS Active Drop)" if firewall_enabled else "DISABLED (IDS Only - Monitoring)"
                print(f"{Colors.WARNING}[IPS FIREWALL] Status changed to: {status_str}{Colors.ENDC}")
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "firewall_enabled": firewall_enabled}).encode('utf-8'))
            except Exception as e:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(f'{{"error": "{e}"}}'.encode('utf-8'))
                
        else:
            # Telemetry endpoint
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            device_id = None
            payload = {}
            try:
                payload = json.loads(post_data.decode('utf-8'))
                device_id = payload.get('device_id')
            except Exception:
                pass
                
            with stats_lock:
                is_blocked = (device_id in blocked_devices) and firewall_enabled if device_id else False
                
            if is_blocked:
                self.send_response(403)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"status": "blocked", "message": "IPS active block list"}')
                print(f"{Colors.FAIL}[IPS FIREWALL] Blocked HTTP POST dropped from Device: {device_id}{Colors.ENDC}")
                return
                
            update_stats('http', len(post_data))
            
            # Log to PCAP
            pcap_writer.write_packet(self.client_address[0], self.client_address[1], global_host, global_http_port, 'http', post_data)
            
            # Send HTTP response
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status": "success", "message": "Telemetry received"}')
            
            try:
                dev_id = payload.get('device_id')
                data_val = payload.get('data')
                
                log_packet('http', f"Device: {dev_id} | Data: {data_val}")
                print(f"{Colors.OKGREEN}[HTTP] Received POST from {self.client_address[0]}:{self.client_address[1]} -> Device: {dev_id} | Data: {data_val}{Colors.ENDC}")
                
                if dev_id:
                    analyze_traffic(dev_id, 'http', payload)
            except Exception as e:
                raw_text = post_data.decode('utf-8', errors='ignore')
                log_packet('http', f"Raw POST: {raw_text[:60]}")
                print(f"{Colors.WARNING}[HTTP] Raw POST data: {post_data}{Colors.ENDC}")

# HTTP Server
def run_http_server(host, port):
    try:
        server = HTTPServer((host, port), IoTHTTPRequestHandler)
        print(f"{Colors.OKGREEN}[HTTP Server] Listening on {host}:{port}{Colors.ENDC}")
        server.serve_forever()
    except Exception as e:
        print(f"{Colors.FAIL}[HTTP Server Error] {e}{Colors.ENDC}")

# Helpers for MQTT Subscriber
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

def decode_remaining_length(sock):
    multiplier = 1
    value = 0
    while True:
        b = sock.recv(1)
        if not b:
            raise socket.error("Socket closed during remaining length decode")
        digit = b[0]
        value += (digit & 127) * multiplier
        if (digit & 128) == 0:
            break
        multiplier *= 128
    return value

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

def make_mqtt_subscribe_packet(topic):
    pkt_id = b"\x00\x01"  # Packet identifier
    topic_bytes = topic.encode('utf-8')
    topic_len = len(topic_bytes).to_bytes(2, 'big')
    qos = b"\x00"  # QoS 0
    
    payload = pkt_id + topic_len + topic_bytes + qos
    rem_len = encode_remaining_length(len(payload))
    return bytes([0x82]) + rem_len + payload

# MQTT Subscriber background thread
def run_mqtt_subscriber(broker, port):
    topic = "iot/devices/+/telemetry"
    print(f"{Colors.HEADER}[MQTT Subscriber] Target Broker: {broker}:{port} | Topic: {topic}{Colors.ENDC}")
    
    while True:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(8.0)
            sock.connect((broker, port))
            
            # Send CONNECT
            connect_pkt = make_mqtt_connect_packet("receiver-sub-99")
            sock.sendall(connect_pkt)
            connack = sock.recv(4)
            
            if len(connack) < 4 or connack[3] != 0:
                sock.close()
                time.sleep(5)
                continue
                
            # Send SUBSCRIBE
            sub_pkt = make_mqtt_subscribe_packet(topic)
            sock.sendall(sub_pkt)
            suback = sock.recv(5)
            
            print(f"{Colors.HEADER}[MQTT Subscriber] Successfully subscribed to {topic}{Colors.ENDC}")
            
            sock.settimeout(None)  # Block on recv indefinitely
            while True:
                header_byte = sock.recv(1)
                if not header_byte:
                    break
                pkt_type = header_byte[0]
                rem_len = decode_remaining_length(sock)
                
                payload = b""
                while len(payload) < rem_len:
                    chunk = sock.recv(rem_len - len(payload))
                    if not chunk:
                        break
                    payload += chunk
                    
                if len(payload) < rem_len:
                    break  # Reconnect
                    
                if (pkt_type & 0xF0) == 0x30:
                    # PUBLISH Packet
                    topic_len = int.from_bytes(payload[0:2], 'big')
                    recv_topic = payload[2:2+topic_len].decode('utf-8')
                    msg = payload[2+topic_len:].decode('utf-8')
                    
                    # Parse JSON to check block list
                    device_id = None
                    msg_payload = {}
                    try:
                        msg_payload = json.loads(msg)
                        device_id = msg_payload.get('device_id')
                    except Exception:
                        pass
                        
                    with stats_lock:
                        is_blocked = (device_id in blocked_devices) and firewall_enabled if device_id else False
                        
                    if is_blocked:
                        print(f"{Colors.FAIL}[IPS FIREWALL] Blocked MQTT packet dropped from Device: {device_id}{Colors.ENDC}")
                        continue
                        
                    update_stats('mqtt', len(msg))
                    
                    # Log to PCAP
                    pcap_writer.write_packet(broker, port, "127.0.0.1", port, 'mqtt', msg.encode('utf-8'))
                    
                    # Log to recent logs
                    log_packet('mqtt', f"Topic: {recv_topic} | Data: {msg}")
                    print(f"{Colors.HEADER}[MQTT] Received from Broker -> Topic: {recv_topic} | Data: {msg}{Colors.ENDC}")
                    
                    if device_id:
                        analyze_traffic(device_id, 'mqtt', msg_payload)
                        
        except Exception as e:
            time.sleep(5)

def main():
    # Load configuration
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        print(f"{Colors.FAIL}config.json not found! Using default configuration.{Colors.ENDC}")
        config = {
            "target_host": "127.0.0.1",
            "udp_port": 5005,
            "tcp_port": 5006,
            "http_port": 5007,
            "mqtt_broker": "broker.hivemq.com",
            "mqtt_port": 1883
        }

    global global_host, global_udp_port, global_tcp_port, global_http_port
    global_host = config.get("target_host", "127.0.0.1")
    global_udp_port = config.get("udp_port", 5005)
    global_tcp_port = config.get("tcp_port", 5006)
    global_http_port = config.get("http_port", 5007)
    
    mqtt_broker = config.get("mqtt_broker", "broker.hivemq.com")
    mqtt_port = config.get("mqtt_port", 1883)

    print(f"{Colors.BOLD}{Colors.HEADER}=== Starting IoT Traffic Receiver Server ==={Colors.ENDC}")
    print(f"Press Ctrl+C to stop the server.\n")
    print(f"Web Dashboard URL: http://127.0.0.1:{global_http_port}/dashboard\n")
    
    # Start threads for servers, stats printer, and MQTT subscriber
    udp_thread = threading.Thread(target=run_udp_server, args=(global_host, global_udp_port), daemon=True)
    tcp_thread = threading.Thread(target=run_tcp_server, args=(global_host, global_tcp_port), daemon=True)
    http_thread = threading.Thread(target=run_http_server, args=(global_host, global_http_port), daemon=True)
    stats_thread = threading.Thread(target=print_stats, daemon=True)
    mqtt_thread = threading.Thread(target=run_mqtt_subscriber, args=(mqtt_broker, mqtt_port), daemon=True)

    udp_thread.start()
    tcp_thread.start()
    http_thread.start()
    stats_thread.start()
    mqtt_thread.start()

    # Keep the main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print(f"\n{Colors.WARNING}Shutting down Receiver Server...{Colors.ENDC}")

if __name__ == '__main__':
    main()
