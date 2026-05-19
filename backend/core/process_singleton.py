import atexit
import socket


class SingleInstanceError(RuntimeError):
    pass


class ProcessSingleton:
    _BASE_PORT = 47600
    _PORT_RANGE = 1000

    def __init__(self, name, host="127.0.0.1", port=None):
        normalized = str(name).strip().lower().replace(" ", "_")
        self.name = normalized
        self.host = host
        self.port = port or self._derive_port(normalized)
        self._socket = None

    def acquire(self):
        if self._socket is not None:
            return self
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((self.host, self.port))
            sock.listen(1)
        except OSError as exc:
            try:
                sock.close()
            except Exception:
                pass
            raise SingleInstanceError(
                f"{self.name} is already running (lock={self.host}:{self.port}, error={exc.strerror or exc})"
            )
        self._socket = sock
        atexit.register(self.release)
        return self

    def release(self):
        if self._socket is None:
            return
        try:
            self._socket.close()
        finally:
            self._socket = None

    @classmethod
    def _derive_port(cls, name):
        offset = sum(ord(char) for char in name) % cls._PORT_RANGE
        return cls._BASE_PORT + offset
