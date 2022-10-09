# Copyright 2016–2021 Julien Danjou
# Copyright 2016 Joshua Harlow
# Copyright 2013-2014 Ray Holder
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import subprocess
from typing import List

from tenacity import Retrying
from tenacity.stop import stop_base, stop_never, stop_after_attempt, stop_after_delay
from tenacity.wait import wait_base, wait_none, wait_fixed

parser = argparse.ArgumentParser(description="Retry shell scripts and applications whenever they fail.")
parser.add_argument(
    "-a",
    "--attempts",
    dest="attempts",
    type=int,
    help="Number of attempts to retry for before failing.",
)
parser.add_argument(
    "-d",
    "--delay",
    dest="delay",
    type=int,
    help="Delay time after which to stop in seconds.",
)
parser.add_argument(
    "-w",
    "--wait-time",
    dest="wait_time",
    type=int,
    help="Fixed time to wait between each attempt in seconds.",
)
parser.add_argument(
    "--ignore-code",
    dest="ignore_codes",
    action="append",
    type=int,
    help="Status code that should be ignored. This argument can be called multiple times.",
)
parser.add_argument(
    "-s",
    "--statistics",
    dest="statistics",
    action="store_true",
    help="Display statistics.",
)
parser.add_argument("command")
parser.add_argument("args", nargs=argparse.REMAINDER)


def runner(commands: List[str], ignore_codes: List[int]) -> None:
    ret_code: int = subprocess.call(commands)
    if ret_code != 0 and ret_code not in ignore_codes:
        raise RuntimeError(f"Return code: {ret_code}")


def main() -> None:
    args = parser.parse_args()

    stop_action: stop_base = stop_never
    wait_action: wait_base = wait_none()

    if args.attempts:
        stop_action |= stop_after_attempt(args.attempts)

    if args.delay:
        stop_action |= stop_after_delay(args.delay)

    if args.wait_time:
        wait_action += wait_fixed(args.wait_time)

    command = [args.command, *args.args]

    retryer = Retrying(stop=stop_action, wait=wait_action, reraise=True)
    try:
        retryer(runner, command, args.ignore_codes or [])
    except RuntimeError as e:
        print(f"\nError: {e}")
    finally:
        if args.statistics:
            stats = retryer.statistics
            print(
                f"""
STATISTICS
----------
Attempts: {stats.get('attempt_number', 0)}
Idle For: {stats.get('idle_for', 0.0)}s
Delay Since First Attempt: {stats.get('delay_since_first_attempt', 0.0)}s
            """
            )


if __name__ == "__main__":
    main()
