import multiprocessing
import threading
from typing import Callable, Any

class JobRunner:
    """
    Service to handle the execution of background tasks.
    """
    
    @staticmethod
    def run_background_task(target: Callable, args: tuple = (), daemon: bool = True):
        """
        Run a task in a separate process to avoid blocking the GIL and main thread.
        This is preferred for heavy CPU tasks like Training or detailed Analysis.
        """
        process = multiprocessing.Process(
            target=target,
            args=args,
            daemon=daemon
        )
        process.start()
        return process

    @staticmethod
    def run_threaded_task(target: Callable, args: tuple = (), daemon: bool = True):
        """
        Run a task in a separate thread. 
        Suitable for I/O bound tasks that don't block the GIL significantly.
        """
        thread = threading.Thread(
            target=target,
            args=args,
            daemon=daemon
        )
        thread.start()
        return thread

job_runner = JobRunner()
