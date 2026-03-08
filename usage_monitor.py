"""
UsageMonitor: Background thread to track CPU and GPU utilization during agent execution.

"""
import threading
import time
import subprocess
from statistics import median, mean
from typing import Dict, Optional

try:
    import psutil
except ImportError:
    psutil = None
    print("[WARNING] psutil not installed. CPU monitoring disabled.")


class UsageMonitor:
    """
    Monitors CPU and GPU utilization in a background thread.
    
    Usage:
        monitor = UsageMonitor(interval=0.5)
        monitor.start()
        # ... do work ...
        monitor.stop()
        stats = monitor.get_stats()
    """
    
    def __init__(self, interval: float = 0.5):
        """
        Args:
            interval: Sampling interval in seconds (default: 0.5s)
        """
        self.interval = interval
        self.running = False
        self.cpu_usage = []
        self.gpu_usage = []
        self.thread: Optional[threading.Thread] = None
        
    def start(self):
        """Start monitoring in background thread."""
        if self.running:
            return
        self.running = True
        self.cpu_usage = []
        self.gpu_usage = []
        self.thread = threading.Thread(target=self._track, daemon=True)
        self.thread.start()
        
    def stop(self):
        """Stop monitoring and wait for thread to finish."""
        if not self.running:
            return
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
            
    @property
    def cpu_mean(self) -> Optional[float]:
        """Mean CPU utilization percentage."""
        return mean(self.cpu_usage) if self.cpu_usage else None
        
    @property
    def cpu_median(self) -> Optional[float]:
        """Median CPU utilization percentage."""
        return median(self.cpu_usage) if self.cpu_usage else None
        
    @property
    def gpu_mean(self) -> Optional[float]:
        """Mean GPU utilization percentage."""
        return mean(self.gpu_usage) if self.gpu_usage else None
        
    @property
    def gpu_median(self) -> Optional[float]:
        """Median GPU utilization percentage."""
        return median(self.gpu_usage) if self.gpu_usage else None
        
    def get_stats(self) -> Dict[str, Optional[float]]:
        """
        Get computed statistics.
        
        Returns:
            Dict with cpu_mean, cpu_median, gpu_mean, gpu_median
        """
        return {
            "cpu_mean": self.cpu_mean,
            "cpu_median": self.cpu_median,
            "gpu_mean": self.gpu_mean,
            "gpu_median": self.gpu_median,
        }
        
    def _track(self):
        """Internal method to track CPU and GPU utilization in a separate thread."""
        while self.running:
            # CPU tracking via psutil
            if psutil:
                try:
                    cpu_utilization = psutil.cpu_percent(interval=self.interval)
                    self.cpu_usage.append(cpu_utilization)
                except Exception as e:
                    print(f"[UsageMonitor] Error tracking CPU: {e}")
            
            # GPU tracking using nvidia-smi
            try:
                result = subprocess.run(
                    ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                    capture_output=True, 
                    text=True,
                    timeout=1.0
                )
                if result.returncode == 0 and result.stdout.strip():
                    gpu_utilization = [int(util) for util in result.stdout.strip().split("\n")]
                    avg_gpu_utilization = sum(gpu_utilization) / len(gpu_utilization)
                    self.gpu_usage.append(avg_gpu_utilization)
            except subprocess.TimeoutExpired:
                pass  # nvidia-smi hung, skip this sample
            except FileNotFoundError:
                pass  # nvidia-smi not available (expected on non-NVIDIA systems)
            except Exception as e:
                # Only print once to avoid spam
                if not hasattr(self, '_gpu_error_printed'):
                    print(f"[UsageMonitor] GPU monitoring unavailable: {e}")
                    self._gpu_error_printed = True

