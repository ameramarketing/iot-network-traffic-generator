import socket
import threading
import json
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

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

# Statistics tracker
stats = {
    'udp_packets': 0,
    'tcp_packets': 0,
    'http_packets': 0,
    'total_bytes': 0,
    'start_time': time.time()
}
stats_lock = threading.Lock()

def update_stats(protocol, byte_count):
    with stats_lock:
        stats[f'{protocol.lower()}_packets'] += 1
        stats['total_bytes'] += byte_count

def print_stats():
    while True:
        time.sleep(10)
        with stats_lock:
            elapsed = time.time() - stats['start_time']
            print(f"\n{Colors.HEADER}=== RECEIVER STATISTICS (Elapsed: {elapsed:.1f}s) ==={Colors.ENDC}")
            print(f"UDP Packets:  {stats['udp_packets']}")
            print(f"TCP Packets:  {stats['tcp_packets']}")
            print(f"HTTP Packets: {stats['http_packets']}")
            print(f"Total Bytes:  {stats['total_bytes']} bytes")
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
            update_stats('udp', len(data))
            try:
                payload = json.loads(data.decode('utf-8'))
                print(f"{Colors.OKBLUE}[UDP] Received from {addr[0]}:{addr[1]} -> Device: {payload.get('device_id')} | Data: {payload.get('data')}{Colors.ENDC}")
            except Exception as e:
                # In case of attack traffic/raw flood
                print(f"{Colors.WARNING}[UDP] Raw/Malformed data received ({len(data)} bytes) from {addr}{Colors.ENDC}")
    except Exception as e:
        print(f"{Colors.FAIL}[UDP Server Error] {e}{Colors.ENDC}")
    finally:
        sock.close()

# TCP Client Handler
def handle_tcp_client(client_sock, addr):
    try:
        while True:
            data = client_sock.recv(4096)
            if not data:
                break
            update_stats('tcp', len(data))
            try:
                payload = json.loads(data.decode('utf-8'))
                print(f"{Colors.OKCYAN}[TCP] Received from {addr[0]}:{addr[1]} -> Device: {payload.get('device_id')} | Data: {payload.get('data')}{Colors.ENDC}")
            except Exception as e:
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
            threading.Thread(target=handle_tcp_client, args=(client_sock, addr), daemon=True).start()
    except Exception as e:
        print(f"{Colors.FAIL}[TCP Server Error] {e}{Colors.ENDC}")
    finally:
        sock.close()

# HTTP Request Handler
class IoTHTTPRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppressing default console output to keep output clean
        return

    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        update_stats('http', len(post_data))
        
        # Send HTTP response
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"status": "success", "message": "Telemetry received"}')
        
        try:
            payload = json.loads(post_data.decode('utf-8'))
            print(f"{Colors.OKGREEN}[HTTP] Received POST from {self.client_address[0]}:{self.client_address[1]} -> Device: {payload.get('device_id')} | Data: {payload.get('data')}{Colors.ENDC}")
        except Exception as e:
            print(f"{Colors.WARNING}[HTTP] Raw POST data: {post_data}{Colors.ENDC}")

# HTTP Server
def run_http_server(host, port):
    try:
        server = HTTPServer((host, port), IoTHTTPRequestHandler)
        print(f"{Colors.OKGREEN}[HTTP Server] Listening on {host}:{port}{Colors.ENDC}")
        server.serve_forever()
    except Exception as e:
        print(f"{Colors.FAIL}[HTTP Server Error] {e}{Colors.ENDC}")

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
            "http_port": 5007
        }

    host = config.get("target_host", "127.0.0.1")
    udp_port = config.get("udp_port", 5005)
    tcp_port = config.get("tcp_port", 5006)
    http_port = config.get("http_port", 5007)

    print(f"{Colors.BOLD}{Colors.HEADER}=== Starting IoT Traffic Receiver Server ==={Colors.ENDC}")
    print(f"Press Ctrl+C to stop the server.\n")
    
    # Start threads for servers and stats printer
    udp_thread = threading.Thread(target=run_udp_server, args=(host, udp_port), daemon=True)
    tcp_thread = threading.Thread(target=run_tcp_server, args=(host, tcp_port), daemon=True)
    http_thread = threading.Thread(target=run_http_server, args=(host, http_port), daemon=True)
    stats_thread = threading.Thread(target=print_stats, daemon=True)

    udp_thread.start()
    tcp_thread.start()
    http_thread.start()
    stats_thread.start()

    # Keep the main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print(f"\n{Colors.WARNING}Shutting down Receiver Server...{Colors.ENDC}")

if __name__ == '__main__':
    main()
