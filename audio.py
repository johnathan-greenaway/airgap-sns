import logging
import numpy as np
import asyncio
from typing import Optional, Callable, Any, Dict
import threading
import queue

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("airgap-sns-audio")

# Try to import ggwave and sounddevice, with graceful fallback
try:
    import ggwave
    import sounddevice as sd
    AUDIO_AVAILABLE = True
except ImportError:
    logger.warning("ggwave or sounddevice not available. Audio features disabled.")
    AUDIO_AVAILABLE = False

# Audio configuration
DEFAULT_SAMPLE_RATE = 48000
DEFAULT_PROTOCOL = 1  # Default ggwave protocol (0-7)
DEFAULT_VOLUME = 50   # Default volume (0-100)
DEFAULT_RX_TIMEOUT = 5.0  # Default receive timeout in seconds

class AudioTransceiver:
    """Handles audio transmission and reception using ggwave"""
    
    def __init__(
        self,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        protocol: int = DEFAULT_PROTOCOL,
        volume: int = DEFAULT_VOLUME,
        callback: Optional[Callable[[str], Any]] = None
    ):
        """Initialize the audio transceiver"""
        if not AUDIO_AVAILABLE:
            raise RuntimeError("Audio functionality not available. Install ggwave and sounddevice.")
            
        self.sample_rate = sample_rate
        self.protocol = protocol
        self.volume = volume
        self.callback = callback
        self.running = False
        self.rx_queue = queue.Queue()
        self.rx_thread = None
        
        # Initialize ggwave instance
        self.ggwave = ggwave.init()
        
        logger.info(f"Audio transceiver initialized (protocol: {protocol}, volume: {volume})")
    
    def transmit(self, message: str) -> bool:
        """Transmit a message via audio"""
        if not AUDIO_AVAILABLE:
            logger.error("Audio functionality not available")
            return False
            
        try:
            # Encode the message using ggwave
            wave = ggwave.encode(
                self.ggwave,
                message,
                protocolId=self.protocol,
                volume=self.volume
            )
            
            if not wave:
                logger.error("Failed to encode audio message")
                return False
                
            # Convert to numpy array and normalize
            audio = np.frombuffer(wave, dtype=np.int16).astype(np.float32) / 32768.0
            
            # Play the audio
            sd.play(audio, self.sample_rate)
            sd.wait()  # Wait until playback is finished
            
            logger.info(f"Transmitted audio message: {message}")
            return True
            
        except Exception as e:
            logger.error(f"Audio transmission failed: {str(e)}")
            return False
    
    def _rx_worker(self):
        """Background worker for continuous audio reception"""
        logger.info("Audio receiver started")
        
        try:
            # Configure the audio stream
            with sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                callback=self._audio_callback,
                blocksize=16384,
                dtype=np.float32
            ):
                # Keep running until stopped
                while self.running:
                    # Process any received messages from the queue
                    try:
                        message = self.rx_queue.get(timeout=0.1)
                        if message and self.callback:
                            self.callback(message)
                    except queue.Empty:
                        pass
                        
        except Exception as e:
            logger.error(f"Audio receiver error: {str(e)}")
        finally:
            logger.info("Audio receiver stopped")
    
    def _audio_callback(self, indata, frames, time, status):
        """Callback for audio input processing"""
        if status:
            logger.warning(f"Audio input status: {status}")
            
        # Convert float32 to int16 for ggwave
        audio_data = (indata.flatten() * 32768.0).astype(np.int16)
        
        # Process with ggwave
        result = ggwave.decode(self.ggwave, audio_data.tobytes())
        
        # If we got a message, add it to the queue
        if result:
            logger.debug(f"Received audio message: {result}")
            self.rx_queue.put(result)
    
    def start_receiver(self):
        """Start the audio receiver in a background thread"""
        if not AUDIO_AVAILABLE:
            logger.error("Audio functionality not available")
            return False
            
        if self.running:
            logger.warning("Audio receiver already running")
            return True
            
        self.running = True
        self.rx_thread = threading.Thread(target=self._rx_worker)
        self.rx_thread.daemon = True
        self.rx_thread.start()
        
        return True
    
    def stop_receiver(self):
        """Stop the audio receiver"""
        if not self.running:
            return
            
        self.running = False
        if self.rx_thread:
            self.rx_thread.join(timeout=1.0)
            self.rx_thread = None
            
        logger.info("Audio receiver stopped")
    
    def __del__(self):
        """Clean up resources"""
        self.stop_receiver()
        if hasattr(self, 'ggwave') and self.ggwave:
            ggwave.free(self.ggwave)

# Simple synchronous receive function for one-off reception
def receive_audio(timeout: float = DEFAULT_RX_TIMEOUT, sample_rate: int = DEFAULT_SAMPLE_RATE) -> Optional[str]:
    """Receive a single audio message with timeout"""
    if not AUDIO_AVAILABLE:
        logger.error("Audio functionality not available")
        return None
        
    try:
        # Record audio for the specified duration
        recording = sd.rec(
            int(sample_rate * timeout),
            samplerate=sample_rate,
            channels=1,
            dtype=np.float32
        )
        sd.wait()  # Wait until recording is finished
        
        # Convert to int16 for ggwave
        audio_data = (recording.flatten() * 32768.0).astype(np.int16)
        
        # Initialize ggwave and decode
        instance = ggwave.init()
        try:
            result = ggwave.decode(instance, audio_data.tobytes())
            return result
        finally:
            ggwave.free(instance)
            
    except Exception as e:
        logger.error(f"Audio reception failed: {str(e)}")
        return None

# Async wrapper for the transmit function
async def async_transmit(message: str, protocol: int = DEFAULT_PROTOCOL, volume: int = DEFAULT_VOLUME) -> bool:
    """Async wrapper for audio transmission"""
    if not AUDIO_AVAILABLE:
        logger.error("Audio functionality not available")
        return False
        
    # Create a transceiver instance
    transceiver = AudioTransceiver(protocol=protocol, volume=volume)
    
    # Run the transmit function in a thread pool
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, transceiver.transmit, message)

# Async wrapper for the receive function
async def async_receive(timeout: float = DEFAULT_RX_TIMEOUT) -> Optional[str]:
    """Async wrapper for audio reception"""
    if not AUDIO_AVAILABLE:
        logger.error("Audio functionality not available")
        return None
        
    # Run the receive function in a thread pool
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, receive_audio, timeout)

# Simple test function
def test_audio():
    """Test audio transmission and reception"""
    if not AUDIO_AVAILABLE:
        print("Audio functionality not available. Install ggwave and sounddevice.")
        return
        
    print("Testing audio transmission and reception...")
    print("Transmitting test message...")
    
    # Create a transceiver
    tx = AudioTransceiver()
    
    # Transmit a test message
    tx.transmit("!!BURST(dest=test;wc=audio;encrypt=no)!!")
    
    print("Listening for 5 seconds...")
    result = receive_audio(timeout=5.0)
    
    if result:
        print(f"Received: {result}")
    else:
        print("No message received.")

if __name__ == "__main__":
    test_audio()
