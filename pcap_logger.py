import struct
import time
import threading
import socket

def compute_ip_checksum(header):
    s = 0
    for i in range(0, len(header), 2):
        w = (header[i] << 8) + header[i+1]
        s += w
    while s >> 16:
        s = (s & 0xffff) + (s >> 16)
    return (~s) & 0xffff

def compute_tcp_checksum(src_ip, dst_ip, tcp_header_pre, payload_bytes):
    src_bytes = socket.inet_aton(src_ip)
    dst_bytes = socket.inet_aton(dst_ip)
    proto = 6  # TCP protocol number
    tcp_len = len(tcp_header_pre) + len(payload_bytes)
    pseudo_hdr = struct.pack('!4s4sBBH', src_bytes, dst_bytes, 0, proto, tcp_len)
    
    data = pseudo_hdr + tcp_header_pre + payload_bytes
    if len(data) % 2 == 1:
        data += b'\x00'
        
    s = sum(struct.unpack(f'!{len(data)//2}H', data))
    while s >> 16:
        s = (s & 0xffff) + (s >> 16)
    return (~s) & 0xffff

class PcapLogger:
    def __init__(self, filename="capture.pcap"):
        self.filename = filename
        self.lock = threading.Lock()
        self.ident = 0
        self.tcp_seqs = {}  # Keep track of sequence numbers for TCP streams
        
        # Write Global PCAP Header
        # Magic: 0xa1b2c3d4 (Big Endian)
        # Version: 2.4
        # Timezone: 0, Sigfigs: 0
        # Snaplen: 65535
        # Link-Type: 1 (Ethernet)
        with open(self.filename, "wb") as f:
            global_header = struct.pack('!IHHiIII', 0xa1b2c3d4, 2, 4, 0, 0, 65535, 1)
            f.write(global_header)

    def write_packet(self, src_ip, src_port, dst_ip, dst_port, protocol, payload_bytes):
        """
        Logs a packet into the PCAP file.
        protocol: 'udp' or 'tcp' or 'http' (modeled as TCP) or 'mqtt' (modeled as TCP)
        """
        with self.lock:
            self.ident = (self.ident + 1) & 0xffff
            
            # 1. Build Ethernet Header (14 bytes)
            # Destination MAC: 00:00:00:00:00:00
            # Source MAC: 00:00:00:00:00:00
            # EtherType: 0x0800 (IPv4)
            eth_header = struct.pack('!6s6sH', b'\x00'*6, b'\x00'*6, 0x0800)
            
            proto_num = 17 if protocol.lower() == 'udp' else 6
            
            # 2. Build Transport Layer + Payload
            if proto_num == 17:
                # UDP Header
                length = 8 + len(payload_bytes)
                udp_header = struct.pack('!HHHH', src_port, dst_port, length, 0)
                transport_packet = udp_header + payload_bytes
            else:
                # TCP Header
                # Track sequence numbers to make TCP flows look standard
                stream_key = (src_ip, src_port, dst_ip, dst_port)
                seq = self.tcp_seqs.get(stream_key, 1)
                ack = 0
                
                # Flag 0x18 = PSH | ACK
                flags = 0x18 
                data_offset_res_flags = (5 << 12) | flags
                window = 64240
                urgent = 0
                
                tcp_header_pre = struct.pack('!HHIIHHHH',
                    src_port, dst_port, seq, ack, data_offset_res_flags, window, 0, urgent
                )
                
                checksum = compute_tcp_checksum(src_ip, dst_ip, tcp_header_pre, payload_bytes)
                
                tcp_header = struct.pack('!HHIIHHHH',
                    src_port, dst_port, seq, ack, data_offset_res_flags, window, checksum, urgent
                )
                transport_packet = tcp_header + payload_bytes
                
                # Increment sequence number for next packet
                self.tcp_seqs[stream_key] = seq + len(payload_bytes)
                
            # 3. Build IP Header
            version_ihl = 0x45
            tos = 0x00
            total_len = 20 + len(transport_packet)
            flags_fragment = 0x4000  # DF (Don't fragment)
            ttl = 64
            
            src_bytes = socket.inet_aton(src_ip)
            dst_bytes = socket.inet_aton(dst_ip)
            
            ip_header_pre = struct.pack('!BBHHHBBH4s4s',
                version_ihl, tos, total_len, self.ident, flags_fragment,
                ttl, proto_num, 0, src_bytes, dst_bytes
            )
            
            ip_checksum = compute_ip_checksum(ip_header_pre)
            
            ip_header = struct.pack('!BBHHHBBH4s4s',
                version_ihl, tos, total_len, self.ident, flags_fragment,
                ttl, proto_num, ip_checksum, src_bytes, dst_bytes
            )
            
            full_packet = eth_header + ip_header + transport_packet
            packet_len = len(full_packet)
            
            # 4. Write PCAP Packet Header
            # Epoch timestamp
            t = time.time()
            ts_sec = int(t)
            ts_usec = int((t - ts_sec) * 1000000)
            
            pcap_pkt_hdr = struct.pack('!IIII', ts_sec, ts_usec, packet_len, packet_len)
            
            # Write to file
            with open(self.filename, "ab") as f:
                f.write(pcap_pkt_hdr)
                f.write(full_packet)
