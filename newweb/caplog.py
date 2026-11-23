"""Keeps a daemon's log from filling the disk, whatever writes to it.

install('shots') points this process's stdout and stderr (and so those of every child it starts later,
such as Playwright's driver and Chrome) at a pipe. A thread copies the pipe into logs/shots.log and, when the
file passes MAX_BYTES, renames it to shots.log.1 (replacing the old one) and starts a new file. So the log
never takes more than about twice MAX_BYTES, even if something prints in a tight loop.

Runs of the same line are written once, followed by "(last line repeated N times)".

Added 2026-11-22/23 after newweb-shots wrote 86 GB, then 76 GB, of one Playwright warning and nearly filled the
studio's internal disk.
"""
import atexit, os, sys, threading

MAX_BYTES = int(os.environ.get('NEWWEB_LOG_MAX_BYTES', 50_000_000))
LOGS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')


def install(name, max_bytes=MAX_BYTES):
    if sys.stdout.isatty():
        return                          # run by hand: leave output on the terminal
    path = os.path.join(LOGS, name + '.log')
    os.makedirs(LOGS, exist_ok=True)
    r, w = os.pipe()
    sys.stdout.flush(); sys.stderr.flush()
    os.dup2(w, 1); os.dup2(w, 2)
    os.close(w)
    t = threading.Thread(target=_copy, args=(r, path, max_bytes), name='caplog', daemon=True)
    t.start()
    atexit.register(_finish, t)


def _finish(t):
    # Close our ends of the pipe so the copier sees end-of-file and writes the last lines (a crash traceback).
    try:
        sys.stdout.flush(); sys.stderr.flush()
        os.close(1); os.close(2)
    except OSError:
        pass
    t.join(5)


def _copy(r, path, max_bytes):
    out = open(path, 'ab')
    size = out.tell()
    last, repeats, buf = None, 0, b''

    def write(data):
        nonlocal out, size
        if size + len(data) > max_bytes:
            out.close()
            os.replace(path, path + '.1')
            out = open(path, 'ab')
            size = 0
        out.write(data)
        out.flush()
        size += len(data)

    def flush_repeats():
        nonlocal repeats
        if repeats:
            write(b'(last line repeated %d times)\n' % repeats)
            repeats = 0

    while True:
        chunk = os.read(r, 65536)
        if not chunk:
            break
        buf += chunk
        *lines, buf = buf.split(b'\n')
        for line in lines:
            if line == last:
                repeats += 1
                if repeats >= 100_000:
                    flush_repeats()
                continue
            flush_repeats()
            write(line + b'\n')
            last = line
        if len(buf) > 65536:            # a very long line with no newline yet
            write(buf[:65536] + b'\n')
            buf = b''
    flush_repeats()
    if buf:
        write(buf + b'\n')
    out.close()
