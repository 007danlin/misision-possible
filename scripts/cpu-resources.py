"""Capture non-secret host and container resource evidence around CPU runs."""
import argparse
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def command(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=20)
    return result.stdout.strip() if result.returncode == 0 else None


def snapshot(container):
    result = {"at": datetime.now(timezone.utc).isoformat(), "host_os": platform.system(),
              "host_arch": platform.machine()}
    if platform.system() == "Darwin":
        for name, args in {
            "cpu": ["sysctl", "-n", "machdep.cpu.brand_string"],
            "ram_bytes": ["sysctl", "-n", "hw.memsize"],
            "swap": ["sysctl", "vm.swapusage"],
            "virtual_memory": ["vm_stat"],
            "memory_pressure": ["memory_pressure", "-Q"],
            "thermal": ["pmset", "-g", "therm"],
        }.items():
            result[name] = command(args)
    raw = command(["docker", "info", "--format", "{{json .}}"])
    if raw:
        info = json.loads(raw)
        result["docker"] = {k: info.get(k) for k in
                            ("Architecture", "NCPU", "MemTotal", "ServerVersion", "KernelVersion")}
    raw = command(["docker", "inspect", container])
    if raw:
        info = json.loads(raw)[0]
        result["container"] = {"image": info["Image"], "state": info["State"]["Status"],
                               "oom_killed": info["State"]["OOMKilled"],
                               **{k: info["HostConfig"].get(k) for k in
                                  ("Memory", "MemorySwap", "CpusetCpus", "NanoCpus")}}
        if info["State"]["Running"]:
            result["cgroup"] = {}
            for name in ("memory.current", "memory.peak", "memory.events", "memory.stat", "cpu.stat"):
                result["cgroup"][name] = command(["docker", "exec", container, "cat", "/sys/fs/cgroup/"+name])
            result["process_memory"] = command(["docker", "exec", container, "cat", "/proc/1/smaps_rollup"])
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", default="odin-request-model-1")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(snapshot(args.container), ensure_ascii=False, indent=2)+"\n")
    print(args.output)
