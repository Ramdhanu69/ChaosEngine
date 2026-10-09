import subprocess
import tempfile
import pathlib
import sys
import json
import time

try:
    import psutil
except ImportError:
    psutil = None

def _kill_proc_tree(proc):
    if psutil:
        try:
            parent = psutil.Process(proc.pid)
            children = parent.children(recursive=True)
            for child in children:
                try:
                    child.kill()
                except Exception:
                    pass
            try:
                parent.kill()
            except Exception:
                pass
            psutil.wait_procs(children + [parent], timeout=2.0)
        except (psutil.NoSuchProcess, Exception):
            pass
    try:
        proc.kill()
    except Exception:
        pass
    try:
        proc.wait(timeout=2.0)
    except Exception:
        pass
    try:
        if proc.stdout:
            proc.stdout.close()
        if proc.stderr:
            proc.stderr.close()
    except Exception:
        pass

def run_in_sandbox(code_str: str, timeout_s: float = 5.0, mem_limit_mb: int = 256) -> dict:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        tdp = pathlib.Path(td)
        script_path = tdp / "sandbox_target.py"
        
        # Add basic network stub
        wrapper = (
            "import sys\n"
            "import json\n\n"
            "class BlockedSocket:\n"
            "    def __init__(self, *args, **kwargs):\n"
            "        raise PermissionError(\"Network blocked\")\n\n"
            "try:\n"
            "    import socket\n"
            "    socket.socket = BlockedSocket\n"
            "except Exception:\n"
            "    pass\n\n"
            + code_str
            + "\n"
        )
        script_path.write_text(wrapper, encoding="utf-8")
        
        cmd = [sys.executable, "-I", str(script_path)]
        proc = None
        
        try:
            # We use subprocess.Popen to monitor memory
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=str(tdp))
            
            start_time = time.time()
            out, err = "", ""
            
            while proc.poll() is None:
                time.sleep(0.05)
                
                if time.time() - start_time > timeout_s:
                    _kill_proc_tree(proc)
                    return {"error": "timeout", "output": ""}
                    
                if psutil:
                    try:
                        p = psutil.Process(proc.pid)
                        mem_mb = p.memory_info().rss / (1024 * 1024)
                        if mem_mb > mem_limit_mb:
                            _kill_proc_tree(proc)
                            return {"error": "memory_limit_exceeded", "output": ""}
                    except (psutil.NoSuchProcess, Exception):
                        pass

            out, err = proc.communicate(timeout=1.0)
            
            if proc.returncode != 0:
                return {"error": "execution_failed", "output": err}
                
            try:
                # Expect the code to print JSON on the last line
                lines = out.strip().split("\n")
                if not lines:
                    return {"error": "no_output", "output": ""}
                return {"result": json.loads(lines[-1]), "output": out}
            except json.JSONDecodeError:
                return {"error": "malformed_json_result", "output": out}
                
        except Exception as e:
            return {"error": str(e), "output": ""}
        finally:
            if proc is not None and proc.poll() is None:
                _kill_proc_tree(proc)

