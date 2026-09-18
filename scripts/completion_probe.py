#!/usr/bin/env python3
"""Pause all PostgreSQL responses to distinguish local return from acknowledgement.

The transparent proxy continues forwarding requests during the two-second gate.
Run serially after the performance matrix, against the disposable server only.
"""
import asyncio
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "results" / sys.argv[1] if len(sys.argv) > 1 else ROOT / "results"
DESTINATION.mkdir(parents=True, exist_ok=True)
if (DESTINATION / "completion-probe.json").exists():
    raise FileExistsError("Choose a new output directory to preserve the existing probe")

async def main():
    gate = asyncio.Event()
    gate.set()
    counts = {"forwarded_server_bytes": 0}

    async def proxy(client_reader, client_writer):
        server_reader, server_writer = await asyncio.open_connection("127.0.0.1", 55432)

        async def forward(reader, writer, gated):
            try:
                while data := await reader.read(65536):
                    if gated:
                        await gate.wait()
                        counts["forwarded_server_bytes"] += len(data)
                    writer.write(data)
                    await writer.drain()
            except (ConnectionError, asyncio.CancelledError):
                pass
            finally:
                writer.close()

        await asyncio.gather(forward(client_reader, server_writer, False),
                             forward(server_reader, client_writer, True))

    records = []
    async with await asyncio.start_server(proxy, "127.0.0.1", 55433):
        for mode in ("sql", "postgrex", "ecto", "epgsql"):
            env = os.environ | {"BENCH_MODE": mode, "PGPORT": "55433",
                                "ERL_FLAGS": "+S 10:10 +SDcpu 2 +SDio 2"}
            process = await asyncio.create_subprocess_exec(
                "mix", "run", "--no-compile", "--no-deps-check", "-e",
                "BeamSqlBench.completion_probe()", cwd=ROOT, env=env,
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT)
            lines = []

            async def read_until(marker):
                while True:
                    raw = await process.stdout.readline()
                    if not raw:
                        raise RuntimeError(lines)
                    line = raw.decode().strip()
                    lines.append(line)
                    if line.startswith(marker):
                        return line

            await asyncio.wait_for(read_until("PROBE_READY"), 30)
            gate.clear()
            before = counts["forwarded_server_bytes"]
            process.stdin.write(b"go\n")
            await process.stdin.drain()
            returned = asyncio.create_task(read_until("PROBE_RETURNED"))
            await asyncio.sleep(2)
            early = returned.done()
            blocked_bytes = counts["forwarded_server_bytes"] - before
            gate.set()
            result = await asyncio.wait_for(returned, 30)
            await asyncio.wait_for(read_until("PROBE_DRAINED"), 30)
            await asyncio.wait_for(process.wait(), 30)
            if process.returncode:
                raise RuntimeError(lines)
            record = {"mode": mode, "gate_seconds": 2,
                      "returned_while_responses_blocked": early,
                      "server_bytes_forwarded_while_blocked": blocked_bytes,
                      "return_microseconds": int(result.split()[1]), "log": lines}
            assert blocked_bytes == 0, record
            assert early == (mode == "sql"), record
            records.append(record)
            print(json.dumps(record), flush=True)
    (DESTINATION / "completion-probe.json").write_text(json.dumps(records, indent=2) + "\n")

asyncio.run(main())
