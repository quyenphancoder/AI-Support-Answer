"""Install a daily cron schedule or execute one logged pipeline run."""

import fcntl
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ENV_PATH = Path('/tmp/amber-atlas-cron-env.json')


def schedule():
    hour = int(os.getenv('DAILY_HOUR_UTC', '2'))
    minute = int(os.getenv('DAILY_MINUTE_UTC', '0'))
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError('Invalid daily schedule time')
    # Cron starts with a minimal environment. Preserve container configuration privately.
    descriptor = os.open(ENV_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, 'w') as output:
        json.dump(dict(os.environ), output)
    entry = f'{minute} {hour} * * * cd /app && /usr/local/bin/python /app/deploy/daily.py >> /proc/1/fd/1 2>> /proc/1/fd/2\n'
    subprocess.run(['crontab', '-'], input=entry, text=True, check=True)
    print(f'Daily job scheduled at {hour:02}:{minute:02} UTC. No run on startup.', flush=True)
    os.execvp('cron', ['cron', '-f'])


def run():
    if ENV_PATH.exists():
        os.environ.update(json.loads(ENV_PATH.read_text()))
    os.chdir('/app')
    data = Path(os.getenv('DATA_DIR', 'data'))
    data.mkdir(parents=True, exist_ok=True)
    logs = Path('/app/logs')
    logs.mkdir(parents=True, exist_ok=True)
    with (data / 'daily.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Daily run skipped: a daily job is already running.', flush=True)
            return 0
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
        started = datetime.now(timezone.utc).isoformat()
        print(f'Starting daily run {stamp}', flush=True)
        limit = int(os.getenv('DAILY_LIMIT', '0'))
        command = [sys.executable, 'main.py']
        if limit > 0:
            command.extend(['--limit', str(limit)])
        with (logs / f'{stamp}.log').open('w') as output:
            result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT)
        summary = {'started_at': started, 'finished_at': datetime.now(timezone.utc).isoformat(),
                   'exit_code': result.returncode, 'log': f'{stamp}.log'}
        artifact = logs / 'last-run.json'
        if artifact.exists():
            detail = json.loads(artifact.read_text())
            if detail.get('started_at', '') >= started:
                summary['pipeline'] = detail
        (logs / f'{stamp}.json').write_text(json.dumps(summary, indent=2))
        print(json.dumps(summary), flush=True)
        return result.returncode


if __name__ == '__main__':
    if '--schedule' in sys.argv:
        schedule()
    else:
        raise SystemExit(run())
