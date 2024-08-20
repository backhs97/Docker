import os
import socket
import threading
import time
import hashlib
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Configuration
NODE_NAME = os.getenv('NODE_NAME')
PORT = int(os.getenv('PORT', 5000))
SYNC_DIR = '/app/sync_dir'
BUFFER_SIZE = 2**22  # 4MB
EXPECTED_PEERS = 4
TIMEOUT = 120
PEER_DISCOVERY_TIMEOUT = 300  # Increased to 5 minutes

peers = {}
node_address = None
all_peers_discovered = threading.Event()
file_versions = {}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s', datefmt='%Y/%m/%d %H:%M:%S')

def get_container_ip(): # This function retrieves the IP address of the container.
    # It first tries to get the IP using the hostname, and if that fails,
    # it creates a temporary socket to obtain the IP.
    try:
        return socket.gethostbyname(socket.gethostname())
    except:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('10.255.255.255', 1))
            IP = s.getsockname()[0]
        except Exception:
            IP = '127.0.0.1'
        finally:
            s.close()
        return IP

def get_file_hash(file_path): # The function calculates the MD5 hash of a given file.
    # It reads the file in chunks to optimize memory usage for large files.
    hasher = hashlib.md5()
    with open(file_path, 'rb') as f:
        buf = f.read(BUFFER_SIZE)
        while buf:
            hasher.update(buf)
            buf = f.read(BUFFER_SIZE)
    return hasher.hexdigest()

class FileSyncHandler(FileSystemEventHandler): # A class handles file system events.
    # It detects file creation, modification, deletion, and moving events,
    # and performs appropriate synchronization actions.
    def on_created(self, event):
        if not event.is_directory:
            self.sync_file(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self.sync_file(event.src_path)

    def on_deleted(self, event):
        if not event.is_directory:
            self.delete_file(event.src_path)
    
    def on_moved(self, event):
        if not event.is_directory:
            self.rename_file(event.src_path, event.dest_path)

    def sync_file(self, file_path): # Synchronizes a file with other peers.
        # It calculates the file's hash and only transmits to other peers if changed.
        file_name = os.path.basename(file_path)
        file_hash = get_file_hash(file_path)
        
        if file_name not in file_versions or file_versions[file_name] != file_hash:
            file_versions[file_name] = file_hash
            file_size = os.path.getsize(file_path)
            for peer_name, peer_address in peers.items():
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.settimeout(TIMEOUT)
                        s.connect(peer_address)
                        s.sendall(f"SYNC:{file_name}:{file_hash}:{file_size}".encode())
                        response = s.recv(1024).decode()
                        if response == "SEND_FILE":
                            with open(file_path, 'rb') as f:
                                sent = 0
                                while sent < file_size:
                                    chunk = f.read(BUFFER_SIZE)
                                    if not chunk:
                                        break
                                    s.sendall(chunk)
                                    sent += len(chunk)
                                    logging.info(f"Sent {sent}/{file_size} bytes of '{file_name}' to {peer_name}")
                            logging.info(f"Transferred file '{file_name}' to {peer_name} successfully")
                        elif response == "UP_TO_DATE":
                            logging.info(f"File '{file_name}' is up to date on {peer_name}")
                except Exception as e:
                    logging.error(f"Error syncing file {file_name} with {peer_name}: {e}")

    def delete_file(self, file_path):
        file_name = os.path.basename(file_path)
        if file_name in file_versions:
            del file_versions[file_name]
        for peer_name, peer_address in peers.items():
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(TIMEOUT)
                    s.connect(peer_address)
                    s.sendall(f"DELETE:{file_name}".encode())
                logging.info(f"Sent delete request for '{file_name}' to {peer_name}")
            except Exception as e:
                logging.error(f"Error sending delete request for {file_name} to {peer_name}: {e}")

    def rename_file(self, src_path, dest_path):
        src_name = os.path.basename(src_path)
        dest_name = os.path.basename(dest_path)
        if src_name in file_versions:
            file_versions[dest_name] = file_versions.pop(src_name)
        for peer_name, peer_address in peers.items():
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(TIMEOUT)
                    s.connect(peer_address)
                    s.sendall(f"RENAME:{src_name}:{dest_name}".encode())
                logging.info(f"Sent rename request from '{src_name}' to '{dest_name}' to {peer_name}")
            except Exception as e:
                logging.error(f"Error sending rename request for {src_name} to {dest_name} to {peer_name}: {e}")

def handle_incoming_file(conn, addr): # The function handles incoming file synchronization requests from other peers.
    # It performs SYNC, DELETE, and RENAME operations.
    conn.settimeout(TIMEOUT)
    try:
        data = conn.recv(BUFFER_SIZE).decode()
        if data.startswith("SYNC:"):
            # Handles SYNC requests. It checks if the file is up-to-date,
            # and receives the file if necessary.
            _, file_name, file_hash, file_size = data.split(":")
            file_size = int(file_size)
            file_path = os.path.join(SYNC_DIR, file_name)
            
            if file_name in file_versions and file_versions[file_name] == file_hash:
                conn.sendall(b"UP_TO_DATE")
                logging.info(f"File '{file_name}' is already up to date")
            else:
                conn.sendall(b"SEND_FILE")
                with open(file_path, 'wb') as f:
                    received = 0
                    while received < file_size:
                        chunk = conn.recv(min(BUFFER_SIZE, file_size - received))
                        if not chunk:
                            raise Exception("Connection closed unexpectedly")
                        f.write(chunk)
                        received += len(chunk)
                        logging.info(f"Received {received}/{file_size} bytes of '{file_name}' from peer {addr[0]}:{addr[1]}")
                file_versions[file_name] = file_hash
                logging.info(f"Successfully received file '{file_name}' from peer {addr[0]}:{addr[1]}")
        elif data.startswith("DELETE:"):
            # Handles "DELETE" requests. It deletes the specified file.
            file_name = data.split(":")[1]
            file_path = os.path.join(SYNC_DIR, file_name)
            if os.path.exists(file_path):
                os.remove(file_path)
                if file_name in file_versions:
                    del file_versions[file_name]
                logging.info(f"Deleted file '{file_name}' as requested by peer {addr[0]}:{addr[1]}")
        elif data.startswith("RENAME:"):
            # Handles "RENAME" requests. It renames the file and
            # creates a new file with a different name if a conflict occurs.
            _, src_name, dest_name = data.split(":")
            src_path = os.path.join(SYNC_DIR, src_name)
            dest_path = os.path.join(SYNC_DIR, dest_name)
            if os.path.exists(src_path):
                if os.path.exists(dest_path):
                    base, ext = os.path.splitext(dest_name)
                    counter = 1
                    while os.path.exists(os.path.join(SYNC_DIR, f"{base}_{counter}{ext}")):
                        counter += 1
                    new_dest_name = f"{base}_{counter}{ext}"
                    new_dest_path = os.path.join(SYNC_DIR, new_dest_name)
                    os.rename(src_path, new_dest_path)
                    if src_name in file_versions:
                        file_versions[new_dest_name] = file_versions.pop(src_name)
                    logging.info(f"Created new file '{new_dest_name}' as '{dest_name}' already exists")
                else:
                    os.rename(src_path, dest_path)
                    if src_name in file_versions:
                        file_versions[dest_name] = file_versions.pop(src_name)
                    logging.info(f"Renamed file from '{src_name}' to '{dest_name}' as requested by peer {addr[0]}:{addr[1]}")
    except Exception as e:
        logging.error(f"Error handling incoming file from {addr}: {e}")

def start_server(): # The function starts the server and handles incoming connections.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', PORT))
        s.listen()
        logging.info(f"Listening for connections on '0.0.0.0:{PORT}'")
        while True:
            conn, addr = s.accept()
            threading.Thread(target=handle_incoming_file, args=(conn, addr)).start()

def broadcast_presence(): # This function broadcasts the node's presence to the network.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        message = f"{NODE_NAME}:{get_container_ip()}:{PORT}".encode()
        while not all_peers_discovered.is_set():
            sock.sendto(message, ('<broadcast>', PORT))
            time.sleep(1)
        logging.info(f"Finished broadcasting presence. Discovered peers: {peers}")

def listen_for_peers(): # The function listens for broadcast messages from other peers
    # and builds the peer list.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(('', PORT))
        sock.settimeout(1)  # Set a timeout for the socket
        start_time = time.time()
        while time.time() - start_time < PEER_DISCOVERY_TIMEOUT:
            try:
                data, addr = sock.recvfrom(1024)
                message = data.decode()
                node_name, ip, port = message.split(':')
                if node_name != NODE_NAME and node_name not in peers:
                    peers[node_name] = (ip, int(port))
                    logging.info(f"Discovered peer: {node_name} at {ip}:{port}")
                    if len(peers) == EXPECTED_PEERS - 1:  # -1 because we don't count ourselves
                        all_peers_discovered.set()
                        logging.info(f"All expected peers discovered: {peers}")
                        return
            except socket.timeout:
                continue
        
        logging.warning(f"Peer discovery timed out. Discovered {len(peers)} peers: {peers}")
        all_peers_discovered.set()  # Set the event even if we didn't find all peers

def sync_existing_files():  # This function synchronizes all existing files at startup.
    for filename in os.listdir(SYNC_DIR):
        file_path = os.path.join(SYNC_DIR, filename)
        if os.path.isfile(file_path):
            FileSyncHandler().sync_file(file_path)

if __name__ == "__main__": # The main execution part. It starts the server,
    # performs peer discovery, and starts file system monitoring.
    logging.info(f"Starting node {NODE_NAME} with IP {get_container_ip()}")
    logging.info(f"Using folder {SYNC_DIR}")
    
    server_thread = threading.Thread(target=start_server)
    server_thread.start()

    udp_listener_thread = threading.Thread(target=listen_for_peers)
    udp_listener_thread.start()

    broadcast_thread = threading.Thread(target=broadcast_presence)
    broadcast_thread.start()

    event_handler = FileSyncHandler()
    observer = Observer()
    observer.schedule(event_handler, SYNC_DIR, recursive=True)
    observer.start()

    try:
        all_peers_discovered.wait()
        sync_existing_files()
        
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        logging.info("Shutting down...")
    observer.join()