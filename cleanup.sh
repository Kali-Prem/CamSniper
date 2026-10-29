#!/bin/bash
# CamSniper cleanup script
echo "[*] Cleaning up CamSniper session..."
pkill -f server.py 2>/dev/null
pkill -f ngrok 2>/dev/null
pkill -f cloudflared 2>/dev/null
read -rp "Delete all captured data? [y/N]: " choice
if [[ "$choice" =~ ^[Yy]$ ]]; then
  rm -rf /home/kali-prem/Tools/CamSnipper/captures/photos/*
  rm -rf /home/kali-prem/Tools/CamSnipper/captures/data/*
  rm -f /home/kali-prem/Tools/CamSnipper/logs/captures.jsonl
  echo "[✓] All capture data deleted."
else
  echo "[i] Capture data preserved."
fi
echo "[✓] Cleanup complete."
