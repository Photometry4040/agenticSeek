"""
Secure Code Execution Sandbox for AgenticSeek

Replaces unsafe exec() and shell=True with sandboxed alternatives.

Features:
- RestrictedPython for Python code
- Subprocess without shell=True for bash
- Whitelist-based command filtering
- Resource limits (memory, CPU, time)
- Network isolation option

Usage:
    from security.patches.code_sandbox import SecurePythonExecutor, SecureBashExecutor

    # Python execution
    py_executor = SecurePythonExecutor()
    result = py_executor.execute("print('Hello')")

    # Bash execution
    bash_executor = SecureBashExecutor()
    result = bash_executor.execute(["ls", "-la"])
"""

import sys
import subprocess
import shlex
import tempfile
import os
import resource
from typing import List, Dict, Any, Optional
from io import StringIO
import logging

logger = logging.getLogger("sandbox")

class SecurePythonExecutor:
    """
    Secure Python code executor using RestrictedPython

    Prevents:
    - import os, sys, subprocess
    - exec(), eval(), __import__()
    - File operations
    - Network access
    - System calls
    """

    def __init__(self, timeout: int = 30, max_memory_mb: int = 512):
        """
        Initialize secure executor

        Args:
            timeout: Maximum execution time in seconds
            max_memory_mb: Maximum memory in MB
        """
        self.timeout = timeout
        self.max_memory_bytes = max_memory_mb * 1024 * 1024

        try:
            from RestrictedPython import compile_restricted, safe_globals
            from RestrictedPython.Guards import guarded_iter_unpack_sequence
            self.compile_restricted = compile_restricted
            self.safe_globals = safe_globals
            self.guarded_iter_unpack_sequence = guarded_iter_unpack_sequence
            logger.info("RestrictedPython available - using sandboxed execution")
        except ImportError:
            logger.warning("RestrictedPython not installed - falling back to Docker sandbox")
            self.compile_restricted = None

    def execute(self, code: str) -> str:
        """
        Execute Python code in sandbox

        Args:
            code: Python code to execute

        Returns:
            str: Output from code execution

        Raises:
            SecurityError: If code contains dangerous operations
            TimeoutError: If execution exceeds timeout
            MemoryError: If execution exceeds memory limit
        """
        # Validate code first
        if not self._validate_code(code):
            raise SecurityError("Code contains prohibited operations")

        if self.compile_restricted:
            return self._execute_restricted_python(code)
        else:
            return self._execute_docker_sandbox(code)

    def _validate_code(self, code: str) -> bool:
        """
        Validate code for dangerous patterns

        Args:
            code: Code to validate

        Returns:
            bool: True if code is safe
        """
        # Blacklist dangerous imports and operations
        dangerous_patterns = [
            'import os',
            'import sys',
            'import subprocess',
            'import socket',
            'import urllib',
            'import requests',
            '__import__',
            'exec(',
            'eval(',
            'compile(',
            'open(',
            'file(',
            'input(',
            'raw_input(',
        ]

        code_lower = code.lower()
        for pattern in dangerous_patterns:
            if pattern.lower() in code_lower:
                logger.warning(f"Blocked dangerous pattern: {pattern}")
                return False

        return True

    def _execute_restricted_python(self, code: str) -> str:
        """
        Execute using RestrictedPython

        Args:
            code: Python code to execute

        Returns:
            str: Output from execution
        """
        # Compile with restrictions
        byte_code = self.compile_restricted(
            code,
            filename='<sandbox>',
            mode='exec'
        )

        if byte_code.errors:
            error_msg = '\n'.join(byte_code.errors)
            raise SecurityError(f"Code compilation failed: {error_msg}")

        # Create restricted globals
        restricted_globals = {
            '__builtins__': self.safe_globals,
            '_iter_unpack_sequence_': self.guarded_iter_unpack_sequence,
            '_getiter_': self.guarded_iter_unpack_sequence,
            # Add safe built-ins
            'print': print,
            'len': len,
            'range': range,
            'enumerate': enumerate,
            'zip': zip,
            'map': map,
            'filter': filter,
            'str': str,
            'int': int,
            'float': float,
            'bool': bool,
            'list': list,
            'dict': dict,
            'tuple': tuple,
            'set': set,
        }

        # Capture output
        stdout_buffer = StringIO()
        old_stdout = sys.stdout
        sys.stdout = stdout_buffer

        try:
            # Set resource limits
            self._set_resource_limits()

            # Execute with timeout
            import signal
            signal.signal(signal.SIGALRM, self._timeout_handler)
            signal.alarm(self.timeout)

            exec(byte_code.code, restricted_globals)

            signal.alarm(0)  # Cancel alarm

            return stdout_buffer.getvalue()

        except TimeoutError:
            logger.error("Code execution timeout")
            raise

        except MemoryError:
            logger.error("Code execution exceeded memory limit")
            raise

        finally:
            sys.stdout = old_stdout

    def _execute_docker_sandbox(self, code: str) -> str:
        """
        Execute in isolated Docker container

        Args:
            code: Python code to execute

        Returns:
            str: Output from execution
        """
        import docker

        try:
            client = docker.from_env()

            # Write code to temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(code)
                code_file = f.name

            # Run in isolated container
            container = client.containers.run(
                image="python:3.11-alpine",
                command=f"python {code_file}",
                detach=True,
                network_mode="none",     # No network access
                mem_limit="512m",        # Memory limit
                cpu_quota=50000,         # CPU limit (50%)
                remove=True,
                read_only=True,          # Read-only filesystem
                security_opt=["no-new-privileges"],
                volumes={
                    code_file: {'bind': code_file, 'mode': 'ro'}
                }
            )

            # Wait for completion with timeout
            try:
                container.wait(timeout=self.timeout)
                output = container.logs().decode()
                return output

            except Exception as e:
                container.kill()
                raise TimeoutError(f"Execution timeout: {e}")

        finally:
            os.unlink(code_file)

    def _set_resource_limits(self):
        """Set resource limits for process"""
        try:
            # Memory limit
            resource.setrlimit(
                resource.RLIMIT_AS,
                (self.max_memory_bytes, self.max_memory_bytes)
            )

            # CPU time limit
            resource.setrlimit(
                resource.RLIMIT_CPU,
                (self.timeout, self.timeout)
            )

        except Exception as e:
            logger.warning(f"Could not set resource limits: {e}")

    def _timeout_handler(self, signum, frame):
        """Handle timeout signal"""
        raise TimeoutError("Code execution timeout")


class SecureBashExecutor:
    """
    Secure bash command executor

    Prevents:
    - Shell injection via shell=True
    - Command substitution $(...)
    - Pipe attacks (|)
    - Redirection attacks (>, <, >>)
    - Path traversal
    """

    def __init__(self, work_dir: str = "/tmp", timeout: int = 300):
        """
        Initialize secure bash executor

        Args:
            work_dir: Working directory (must be absolute path)
            timeout: Maximum execution time in seconds
        """
        self.work_dir = os.path.abspath(work_dir)
        self.timeout = timeout

        # Whitelist of allowed commands
        self.allowed_commands = {
            'ls', 'pwd', 'echo', 'cat', 'grep', 'find',
            'head', 'tail', 'wc', 'sort', 'uniq',
            'date', 'whoami', 'hostname',
            'mkdir', 'touch', 'cp', 'mv',
            # Add more as needed
        }

        logger.info(f"Bash executor initialized - work_dir: {self.work_dir}")

    def execute(self, command: str) -> str:
        """
        Execute bash command safely

        Args:
            command: Command to execute

        Returns:
            str: Command output

        Raises:
            SecurityError: If command is not allowed
            subprocess.TimeoutExpired: If command times out
        """
        # Parse command safely
        try:
            cmd_parts = shlex.split(command)
        except ValueError as e:
            raise SecurityError(f"Invalid command syntax: {e}")

        if not cmd_parts:
            raise SecurityError("Empty command")

        # Validate command
        if not self._validate_command(cmd_parts):
            raise SecurityError(f"Command not allowed: {cmd_parts[0]}")

        # Execute without shell=True
        try:
            result = subprocess.run(
                cmd_parts,
                shell=False,          # ✓ Prevents shell injection
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=self.work_dir,    # Set working directory
                timeout=self.timeout,
                universal_newlines=True,
                check=False
            )

            return result.stdout

        except subprocess.TimeoutExpired:
            logger.error(f"Command timeout: {command}")
            raise

        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            raise

    def _validate_command(self, cmd_parts: List[str]) -> bool:
        """
        Validate command is allowed

        Args:
            cmd_parts: Parsed command parts

        Returns:
            bool: True if command is allowed
        """
        if not cmd_parts:
            return False

        # Check if base command is allowed
        base_command = os.path.basename(cmd_parts[0])

        if base_command not in self.allowed_commands:
            logger.warning(f"Blocked command: {base_command}")
            return False

        # Check for dangerous arguments
        dangerous_args = ['&', '|', ';', '$', '`', '>', '<', '>>']
        for part in cmd_parts:
            if any(char in part for char in dangerous_args):
                logger.warning(f"Blocked dangerous argument: {part}")
                return False

        # Check for path traversal
        for part in cmd_parts:
            if '..' in part or part.startswith('/'):
                logger.warning(f"Blocked path traversal: {part}")
                return False

        return True


class SecurityError(Exception):
    """Custom exception for security violations"""
    pass


# Example usage
if __name__ == "__main__":
    print("=" * 70)
    print("Secure Code Execution Sandbox Demo")
    print("=" * 70)

    # Python execution
    print("\n[*] Testing Python executor...")
    py_exec = SecurePythonExecutor()

    # Safe code
    safe_code = """
result = sum(range(10))
print(f"Sum: {result}")
"""
    print(f"\nSafe code:\n{safe_code}")
    try:
        output = py_exec.execute(safe_code)
        print(f"Output: {output}")
    except Exception as e:
        print(f"Error: {e}")

    # Dangerous code
    dangerous_code = """
import os
os.system("rm -rf /")
"""
    print(f"\nDangerous code:\n{dangerous_code}")
    try:
        output = py_exec.execute(dangerous_code)
        print(f"Output: {output}")
    except SecurityError as e:
        print(f"✓ Blocked: {e}")

    # Bash execution
    print("\n[*] Testing Bash executor...")
    bash_exec = SecureBashExecutor()

    # Safe command
    print("\nSafe command: ls -la")
    try:
        output = bash_exec.execute("ls -la")
        print(f"Output: {output[:200]}...")
    except Exception as e:
        print(f"Error: {e}")

    # Dangerous command
    print("\nDangerous command: ls; rm -rf /")
    try:
        output = bash_exec.execute("ls; rm -rf /")
        print(f"Output: {output}")
    except SecurityError as e:
        print(f"✓ Blocked: {e}")

    print("\n" + "=" * 70)
