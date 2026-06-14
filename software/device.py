import serial
import serial.tools.list_ports
import time

class LogicAnalyzerDevice:
    """Device driver for STM32-UART-LA8 Logic Analyzer (DMA Version)"""
    
    STREAM_MAGIC = b'STRM'
    STREAM_HEADER_SIZE = 14
    STREAM_TRAILER_SIZE = 2
    STREAM_SAMPLE_COUNT = 1024
    STREAM_RATES = {100, 1_000, 10_000, 50_000}

    def __init__(self, port=None, baudrate=1_000_000):
        self.port = port
        self.baudrate = baudrate
        self.serial = None
        self.device_info = None
        self.stream_buffer = bytearray()
        self.last_stream_sequence = None
        self.stream_corrupt_frames = 0
        self.last_error = None
    
    @staticmethod
    def list_ports():
        """List available serial ports"""
        ports = serial.tools.list_ports.comports()
        return [port.device for port in ports]
    
    def connect(self):
        """Connect to device"""
        try:
            self.serial = serial.Serial(self.port, self.baudrate, timeout=2)
            time.sleep(0.1)

            # A previous GUI process may have closed while the MCU was still
            # streaming binary data. Stop that stream before requesting text.
            self.serial.write(b'QQQ')
            time.sleep(0.5)
            self.serial.reset_input_buffer()
            self.stream_buffer.clear()

            info = None
            for _ in range(3):
                self.serial.reset_input_buffer()
                self.serial.write(b'I')
                info = self._read_device_info(timeout=1.0)
                if info:
                    break
            if not info:
                self.serial.close()
                self.serial = None
                return False

            self.device_info = info
            return True
            
        except Exception as e:
            print(f"Connection error: {e}")
            if self.serial:
                self.serial.close()
                self.serial = None
            raise

    def _read_device_info(self, timeout):
        """Read only exact INFO protocol lines, ignoring residual binary."""
        fields = {}
        buffer = bytearray()
        deadline = time.time() + timeout

        while time.time() < deadline:
            waiting = self.serial.in_waiting
            if waiting:
                buffer.extend(self.serial.read(waiting))

                while b'\n' in buffer:
                    raw_line, _, remainder = buffer.partition(b'\n')
                    buffer = bytearray(remainder)
                    line = raw_line.decode('ascii', errors='ignore').strip()

                    if line.startswith('INFO:'):
                        fields['device_name'] = line[len('INFO:'):]
                    elif line.startswith('VERSION:'):
                        fields['version'] = line[len('VERSION:'):]
                    elif line.startswith('CHANNELS:'):
                        value = line[len('CHANNELS:'):]
                        if value.isdigit():
                            fields['channels'] = int(value)
                    elif line.startswith('BUFFER:'):
                        value = line[len('BUFFER:'):]
                        if value.isdigit():
                            fields['buffer_size'] = int(value)
                    elif line.startswith('MAX:'):
                        fields['max_rate'] = self._parse_rate(
                            line[len('MAX:'):]
                        )
                    elif line.startswith('STATUS:'):
                        if (
                            fields.get('device_name') == 'STM32-UART-LA8'
                            and fields.get('channels') == 8
                            and fields.get('buffer_size')
                            and fields.get('max_rate')
                        ):
                            return {'type': 'info', **fields}
            else:
                time.sleep(0.005)

        return None

    @staticmethod
    def _parse_rate(value):
        """Parse protocol rates such as 6MHz, 100kHz, or 100Hz."""
        value = value.strip()
        multipliers = (
            ('MHz', 1_000_000),
            ('kHz', 1_000),
            ('Hz', 1),
        )
        for suffix, multiplier in multipliers:
            if value.endswith(suffix):
                number = value[:-len(suffix)]
                try:
                    return int(float(number) * multiplier)
                except ValueError:
                    return None
        return None
    
    def disconnect(self):
        """Disconnect from device"""
        if self.serial:
            self.stop_stream()
            self.serial.close()
            self.serial = None
    
    def reset_device(self):
        """Reset device using firmware 'R' command"""
        if not self.serial:
            return False
        
        try:
            # Send reset command
            self.serial.reset_input_buffer()
            self.serial.write(b'R')
            time.sleep(0.5)  # Wait for reset to complete
            
            # Clear any response
            if self.serial.in_waiting > 0:
                self.serial.read(self.serial.in_waiting)
            
            self.serial.reset_input_buffer()
            return True
        except Exception as e:
            print(f"Reset error: {e}")
            return False
    
    def capture(self, timeout=35):
        """Request capture and read data"""
        if not self.serial:
            return None
        
        try:
            # Clear buffers
            self.serial.reset_input_buffer()
            
            # Send capture command
            self.serial.write(b'C')
            
            # Read header line "DATA:"
            start_time = time.time()
            header_found = False
            buffer = b''
            
            while time.time() - start_time < timeout:
                if self.serial.in_waiting > 0:
                    buffer += self.serial.read(self.serial.in_waiting)
                    
                    if b'DATA:' in buffer:
                        # Find position of DATA:
                        data_pos = buffer.find(b'DATA:')
                        buffer = buffer[data_pos + len(b'DATA:'):]
                        header_found = True
                        break

                    if b'ERROR:TRIGGER_TIMEOUT' in buffer:
                        return {'type': 'trigger_timeout'}

                    if b'ERROR' in buffer:
                        print(f"Error in response: {buffer}")
                        return None
                else:
                    time.sleep(0.01)
            
            if not header_found:
                print(f"Error: DATA header not found. Received: {buffer[:100]}")
                return None
            
            # Read count (4 bytes)
            while len(buffer) < 4 and time.time() - start_time < timeout:
                if self.serial.in_waiting > 0:
                    buffer += self.serial.read(self.serial.in_waiting)
                else:
                    time.sleep(0.01)
            
            if len(buffer) < 4:
                return None
            
            count_bytes = buffer[:4]
            buffer = buffer[4:]
            
            sample_count = int.from_bytes(count_bytes, byteorder='little')
            if not 0 < sample_count <= 1_000_000:
                print(f"Error: Invalid sample count: {sample_count}")
                return None
            
            # Read sample_rate_hz (4 bytes)
            while len(buffer) < 4 and time.time() - start_time < timeout:
                if self.serial.in_waiting > 0:
                    buffer += self.serial.read(self.serial.in_waiting)
                else:
                    time.sleep(0.01)
            
            if len(buffer) < 4:
                return None
            
            rate_bytes = buffer[:4]
            buffer = buffer[4:]
            
            sample_rate_hz = int.from_bytes(rate_bytes, byteorder='little')
            
            # Read newline
            while len(buffer) < 1 and time.time() - start_time < timeout:
                if self.serial.in_waiting > 0:
                    buffer += self.serial.read(self.serial.in_waiting)
                else:
                    time.sleep(0.01)
            
            if buffer[0:1] == b'\n':
                buffer = buffer[1:]
            
            # Read sample data
            while len(buffer) < sample_count and time.time() - start_time < timeout:
                if self.serial.in_waiting > 0:
                    buffer += self.serial.read(self.serial.in_waiting)
                else:
                    time.sleep(0.01)
            
            samples = buffer[:sample_count]
            buffer = buffer[sample_count:]
            
            if len(samples) < sample_count:
                print(f"Warning: Expected {sample_count} samples, got {len(samples)}")
                return None
            
            # Calculate sample period in nanoseconds from sample rate
            if sample_rate_hz > 0:
                sample_period_ns = int(1_000_000_000 / sample_rate_hz)
            else:
                sample_period_ns = 1000  # Default 1us if rate is 0
            
            # Return in expected format
            return {
                'type': 'capture',
                'samples': samples,
                'sample_period_ns': sample_period_ns,
                'sample_count': len(samples),
                'sample_rate_hz': sample_rate_hz
            }
            
        except Exception as e:
            print(f"Capture error: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def set_sample_rate(self, rate_code):
        """Set sample rate using firmware commands
        rate_code: '1' = 1MHz, '2' = 2MHz, '5' = 5MHz, '6' = 6MHz
        """
        if not self.serial:
            return False
        
        self.serial.reset_input_buffer()
        self.serial.write(rate_code.encode())
        time.sleep(0.1)
        
        # Read response
        if self.serial.in_waiting > 0:
            response = self.serial.readline().decode('utf-8', errors='ignore').strip()
            return 'OK:' in response
        
        return False

    def set_trigger(self, enabled):
        """Enable PA0 falling-edge trigger or return to immediate capture."""
        if not self.serial:
            return False

        self.serial.reset_input_buffer()
        self.serial.write(b'T' if enabled else b'N')
        time.sleep(0.1)

        if self.serial.in_waiting > 0:
            response = self.serial.readline().decode('utf-8', errors='ignore').strip()
            return 'OK:TRIGGER:' in response

        return False

    def start_stream(self):
        """Start continuous circular-DMA streaming."""
        if not self.serial:
            return False

        self.last_error = None
        self.serial.reset_input_buffer()
        self.stream_buffer.clear()
        self.last_stream_sequence = None
        self.stream_corrupt_frames = 0
        self.serial.write(b'S')

        response = self._wait_for_response(
            ('OK:STREAM:START', 'ERROR:'),
            timeout=1.0,
        )
        if response == 'OK:STREAM:START':
            return True

        self.last_error = response or 'No response from firmware'
        return False

    def _wait_for_response(self, prefixes, timeout):
        """Read exact text protocol lines while ignoring unrelated bytes."""
        buffer = bytearray()
        deadline = time.time() + timeout

        while time.time() < deadline:
            waiting = self.serial.in_waiting
            if waiting:
                buffer.extend(self.serial.read(waiting))
                while b'\n' in buffer:
                    raw_line, _, remainder = buffer.partition(b'\n')
                    buffer = bytearray(remainder)
                    line = raw_line.decode('ascii', errors='ignore').strip()
                    if any(line.startswith(prefix) for prefix in prefixes):
                        return line
            else:
                time.sleep(0.002)

        return None

    def stop_stream(self, drain=True):
        """Stop streaming and optionally return every complete queued frame."""
        if not self.serial or not self.serial.is_open:
            return []

        frames = []
        try:
            self.serial.write(b'Q')
            if drain:
                deadline = time.time() + 0.3
                last_data_at = time.time()
                while time.time() < deadline:
                    waiting = self.serial.in_waiting
                    new_frames = self.read_stream_frames()
                    if waiting or new_frames:
                        last_data_at = time.time()
                    frames.extend(new_frames)
                    if time.time() - last_data_at >= 0.05:
                        break
                    time.sleep(0.002)
            else:
                time.sleep(0.05)

            self.serial.reset_input_buffer()
            self.stream_buffer.clear()
        except Exception:
            pass
        return frames

    def read_stream_frames(self):
        """Read all complete stream frames currently available."""
        if not self.serial:
            return []

        waiting = self.serial.in_waiting
        if waiting:
            self.stream_buffer.extend(self.serial.read(waiting))

        frames = []
        while True:
            magic_pos = self.stream_buffer.find(self.STREAM_MAGIC)
            if magic_pos < 0:
                if len(self.stream_buffer) > len(self.STREAM_MAGIC) - 1:
                    del self.stream_buffer[:-(len(self.STREAM_MAGIC) - 1)]
                break
            if magic_pos > 0:
                del self.stream_buffer[:magic_pos]
            if len(self.stream_buffer) < self.STREAM_HEADER_SIZE:
                break

            sample_count = int.from_bytes(self.stream_buffer[4:6], 'little')
            sample_rate_hz = int.from_bytes(self.stream_buffer[6:10], 'little')
            sequence = int.from_bytes(self.stream_buffer[10:14], 'little')
            if (
                sample_count != self.STREAM_SAMPLE_COUNT
                or sample_rate_hz not in self.STREAM_RATES
            ):
                del self.stream_buffer[0]
                continue

            frame_size = (
                self.STREAM_HEADER_SIZE
                + sample_count
                + self.STREAM_TRAILER_SIZE
            )
            if len(self.stream_buffer) < frame_size:
                break

            payload_end = self.STREAM_HEADER_SIZE + sample_count
            samples = bytes(
                self.stream_buffer[self.STREAM_HEADER_SIZE:payload_end]
            )
            expected_crc = int.from_bytes(
                self.stream_buffer[payload_end:frame_size],
                'little',
            )
            if self._crc16(samples) != expected_crc:
                self.stream_corrupt_frames += 1
                del self.stream_buffer[0]
                continue

            del self.stream_buffer[:frame_size]

            dropped = 0
            if self.last_stream_sequence is not None:
                delta = (sequence - self.last_stream_sequence) & 0xFFFFFFFF
                if delta == 0:
                    continue
                if 1 < delta < 100_000:
                    dropped = delta - 1
            self.last_stream_sequence = sequence

            frames.append({
                'type': 'stream',
                'samples': samples,
                'sample_period_ns': int(1_000_000_000 / sample_rate_hz),
                'sample_count': sample_count,
                'sample_rate_hz': sample_rate_hz,
                'sequence': sequence,
                'dropped_frames': dropped,
                'corrupt_frames': self.stream_corrupt_frames,
            })

        return frames

    @staticmethod
    def _crc16(data):
        crc = 0xFFFF
        for value in data:
            crc ^= value << 8
            for _ in range(8):
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
        return crc
