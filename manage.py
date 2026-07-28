#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import socket
import sys

from config.env import load_env


def _prefer_ipv4_dns() -> None:
    """Avoid hangs when DNS returns IPv6 first but IPv6 routing is broken (common with Neon)."""
    _orig = socket.getaddrinfo

    def getaddrinfo(*args, **kwargs):
        infos = _orig(*args, **kwargs)
        v4 = [i for i in infos if i[0] == socket.AF_INET]
        return v4 + [i for i in infos if i[0] != socket.AF_INET] if v4 else infos

    socket.getaddrinfo = getaddrinfo  # type: ignore[assignment]


def main():
    """Run administrative tasks."""
    load_env()
    _prefer_ipv4_dns()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
