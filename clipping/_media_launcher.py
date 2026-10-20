"""Internal Windows launcher: start the target only after the parent's gate opens."""

import subprocess
import sys


def main():
    if sys.stdin.buffer.read(1) != b'1':
        return 125
    try:
        return subprocess.call(sys.argv[1:], stdin=subprocess.DEVNULL)
    except FileNotFoundError:
        print(f'Install {sys.argv[1]} and make it available on PATH', file=sys.stderr)
        return 127
    except OSError:
        print('The media executable could not be started', file=sys.stderr)
        return 126


if __name__ == '__main__':
    raise SystemExit(main())
