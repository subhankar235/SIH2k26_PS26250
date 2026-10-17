"""Interactive Real-Time Operational Telemetry & Disruption Simulator.

Provides a live, interactive command terminal for tactical air operations:
- Continuous real-time clock and dynamic flight kinematics (airspeed, altitude, distance, fuel burn, OAT, humidity)
- Real-time telemetry streaming to the backend MAGI agent engine
- Non-blocking hotkey scenario injection (Storm, Threat, Mechanical, Crew Fatigue, Reset)
- Automatic detection of CP-SAT replans, reroutes, standby airframe swaps, and safety margins
"""

import sys
import os
import time
import json
import math
import random
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional

try:
    import httpx
except ImportError:
    print("[ERROR] httpx is required. Install via: pip install httpx")
    sys.exit(1)

# Platform-specific non-blocking keyboard input
IS_WINDOWS = os.name == "nt"
if IS_WINDOWS:
    import msvcrt
else:
    import select
    import termios
    import tty


# ----------------- ANSI COLOR DEFINITIONS -----------------
ESC = "\033["
RESET = f"{ESC}0m"
BOLD = f"{ESC}1m"
DIM = f"{ESC}2m"

# Tactical color palette
C_ORANGE = f"{ESC}38;5;208m"
C_ORANGE_BG = f"{ESC}48;5;208m{ESC}30m"
C_GREEN = f"{ESC}38;5;34m"
C_GREEN_BG = f"{ESC}48;5;34m{ESC}30m"
C_CYAN = f"{ESC}38;5;39m"
C_BLUE = f"{ESC}38;5;33m"
C_AMBER = f"{ESC}38;5;214m"
C_AMBER_BG = f"{ESC}48;5;214m{ESC}30m"
C_RED = f"{ESC}38;5;196m"
C_RED_BG = f"{ESC}48;5;196m{ESC}37m"
C_PURPLE = f"{ESC}38;5;135m"
C_GRAY = f"{ESC}38;5;244m"
C_WHITE = f"{ESC}38;5;255m"


def check_keypress() -> Optional[str]:
    """Check if a keyboard key was pressed without blocking execution."""
    if IS_WINDOWS:
        if msvcrt.kbhit():
            ch = msvcrt.getch()
            try:
                return ch.decode("utf-8", errors="ignore").lower()
            except Exception:
                return None
        return None
    else:
        dr, _, _ = select.select([sys.stdin], [], [], 0)
        if dr:
            return sys.stdin.read(1).lower()
        return None


# ----------------- FLIGHT SIMULATION STATE -----------------
class SimulatedSortie:
    def __init__(
        self,
        id: str,
        callsign: str,
        mission_name: str,
        airframe_id: str,
        airframe_model: str,
        tail_number: str,
        home_base: str,
        pilot: str,
        copilot: str,
        duty_remaining_hrs: float,
        duty_limit_hrs: float,
        payload_desc: str,
        payload_weight_kg: int,
        is_cold_chain: bool,
        origin: str,
        dest: str,
        corridor: str,
        total_distance_km: float,
        cruise_speed_kts: float,
        cruise_altitude_fl: int,
        initial_progress: float = 0.0,
        status: str = "IN-FLIGHT",
    ):
        self.id = id
        self.callsign = callsign
        self.mission_name = mission_name
        self.airframe_id = airframe_id
        self.airframe_model = airframe_model
        self.tail_number = tail_number
        self.home_base = home_base
        self.pilot = pilot
        self.copilot = copilot
        self.duty_remaining_hrs = duty_remaining_hrs
        self.duty_limit_hrs = duty_limit_hrs
        self.payload_desc = payload_desc
        self.payload_weight_kg = payload_weight_kg
        self.is_cold_chain = is_cold_chain
        self.origin = origin
        self.dest = dest
        self.corridor = corridor
        self.total_distance_km = total_distance_km
        self.cruise_speed_kts = cruise_speed_kts
        self.cruise_altitude_fl = cruise_altitude_fl
        self.progress = initial_progress  # 0.0 to 1.0
        self.status = status
        self.fuel_percent = 92.0
        self.current_speed_kts = cruise_speed_kts
        self.current_altitude_ft = cruise_altitude_fl * 100
        self.oat_celsius = -35.0
        self.humidity_percent = 42
        self.cold_chain_temp_c = 3.8 if is_cold_chain else None
        self.delay_delta_min = 0
        self.delay_cause = ""
        self.est_arrival_utc = "11:45 UTC"
        self.deadline_utc = "12:30 UTC"
        self.safety_margin_min = 45

    def tick(self, dt_seconds: float, speed_multiplier: float):
        effective_dt = dt_seconds * speed_multiplier
        speed_kmh = self.current_speed_kts * 1.852

        # In-flight progress
        if self.status in ("IN-FLIGHT", "REROUTED"):
            dist_delta_km = (speed_kmh / 3600.0) * effective_dt
            current_dist_km = self.progress * self.total_distance_km + dist_delta_km
            self.progress = min(1.0, current_dist_km / max(1.0, self.total_distance_km))

            # Fuel burn rate: ~0.006% per sec
            self.fuel_percent = max(5.0, self.fuel_percent - 0.006 * effective_dt)

            # Pilot duty time decreases
            self.duty_remaining_hrs = max(0.0, self.duty_remaining_hrs - (effective_dt / 3600.0))

            # Environmental micro-variations
            self.current_speed_kts = round(
                self.cruise_speed_kts + random.uniform(-4.0, 4.0), 1
            )
            # Atmospheric lapse rate: ~ -6.5C per 1000m
            altitude_m = self.current_altitude_ft * 0.3048
            self.oat_celsius = round(15.0 - (altitude_m / 1000.0) * 6.5 + random.uniform(-0.8, 0.8), 1)
            self.humidity_percent = min(99, max(15, int(42 + random.uniform(-3, 3))))

            if self.is_cold_chain:
                self.cold_chain_temp_c = round(3.8 + random.uniform(-0.2, 0.2), 2)

            # Check for landing / touchdown
            if self.progress >= 0.999:
                self.status = "TOUCHDOWN / LANDED"
                self.current_speed_kts = 0.0
                self.current_altitude_ft = 0
        elif self.status == "TOUCHDOWN / LANDED":
            # Turnaround refuel staging
            self.fuel_percent = min(100.0, self.fuel_percent + 0.5 * effective_dt)
            if self.fuel_percent >= 98.0:
                self.status = "READY FOR NEXT SORTIE"
                self.progress = 0.0
                self.fuel_percent = 100.0


# ----------------- SIMULATOR CORE ENGINE -----------------
class OperationalFlightSimulator:
    def __init__(self, agent_engine_url: str = "http://127.0.0.1:8000"):
        self.engine_url = agent_engine_url
        self.sim_time = datetime(2026, 10, 15, 10, 30, 0, tzinfo=timezone.utc)
        self.time_speed = 1.0  # 1x, 2x, 5x, 10x
        self.paused = False
        self.running = True
        self.revision = 1
        self.equilibrium_status = "EQUILIBRIUM MAINTAINED"
        self.is_equilibrium = True
        self.event_log: List[Dict[str, str]] = []
        self.client = httpx.Client(timeout=3.0)

        # Initialize tactical sorties
        self.sorties: List[SimulatedSortie] = [
            SimulatedSortie(
                id="MSN-LOG-110",
                callsign="SAMARITAN-04",
                mission_name="Nyoma ALG Critical Resupply & Blood Plasma",
                airframe_id="C130-KC382",
                airframe_model="Lockheed C-130J Super Hercules",
                tail_number="KC382",
                home_base="Hindon AFS",
                pilot="Sqn Ldr Priya Sharma [PIC]",
                copilot="Flt Lt Rohit Varma (Co-Pilot)",
                duty_remaining_hrs=2.8,
                duty_limit_hrs=10.0,
                payload_desc="14,500 kg Combat Rations + Cold-Chain Blood Plasma Units",
                payload_weight_kg=14500,
                is_cold_chain=True,
                origin="Hindon AFS",
                dest="Nyoma ALG",
                corridor="Corridor Charlie-7 (Direct Low Valley, 640 km)",
                total_distance_km=640.0,
                cruise_speed_kts=360.0,
                cruise_altitude_fl=220,
                initial_progress=0.45,
                status="IN-FLIGHT",
            ),
            SimulatedSortie(
                id="MSN-OP-901",
                callsign="GARUDA-01",
                mission_name="Stand-off BrahMos Strike Boundary Patrol",
                airframe_id="SU30-SB042",
                airframe_model="Sukhoi Su-30MKI Super Flanker",
                tail_number="SB042",
                home_base="Bareilly AFS",
                pilot="Wg Cdr V. Joshi [PIC]",
                copilot="Sqn Ldr Ananya Sen (WSO)",
                duty_remaining_hrs=6.8,
                duty_limit_hrs=8.0,
                payload_desc="2x BrahMos-A + 4x Astra Mk-1 (9,400 kg)",
                payload_weight_kg=9400,
                is_cold_chain=False,
                origin="Bareilly AFS",
                dest="Leh Forward AFS",
                corridor="Corridor Alpha-1 (FL320 High-Speed Vector, 850 km)",
                total_distance_km=850.0,
                cruise_speed_kts=540.0,
                cruise_altitude_fl=320,
                initial_progress=0.25,
                status="IN-FLIGHT",
            ),
            SimulatedSortie(
                id="MSN-CAP-404",
                callsign="HAWK-03",
                mission_name="Sector Air Dominance & BVR Sweep",
                airframe_id="RAF-RB015",
                airframe_model="Dassault Rafale EH",
                tail_number="RB015",
                home_base="Ambala AFS",
                pilot="Wg Cdr Arjun Rathore [PIC]",
                copilot="Single Seat (RBE2 AESA Active)",
                duty_remaining_hrs=4.6,
                duty_limit_hrs=8.0,
                payload_desc="4x Meteor BVR + 2x MICA IR (Combat Load)",
                payload_weight_kg=6200,
                is_cold_chain=False,
                origin="Ambala AFS",
                dest="Udhampur Sector Base",
                corridor="Corridor Alpha-1 (FL340 High Clearance, 720 km)",
                total_distance_km=720.0,
                cruise_speed_kts=520.0,
                cruise_altitude_fl=340,
                initial_progress=0.72,
                status="IN-FLIGHT",
            ),
            SimulatedSortie(
                id="MSN-DEF-301",
                callsign="LIGHTNING-01",
                mission_name="Base Quick-Reaction Intercept Alert",
                airframe_id="TEJ-LA008",
                airframe_model="HAL Tejas Mk-1 FOC",
                tail_number="LA008",
                home_base="Sulur AFS",
                pilot="Sqn Ldr Kabir Bedi [PIC]",
                copilot="Single Seat (Uttam AESA Radar)",
                duty_remaining_hrs=7.5,
                duty_limit_hrs=8.0,
                payload_desc="2x Astra Mk-1 + 2x ASRAAM (Combat Armed)",
                payload_weight_kg=4800,
                is_cold_chain=False,
                origin="Sulur AFS",
                dest="Thanjavur Forward Base",
                corridor="Coastal Intercept Vector (450 km)",
                total_distance_km=450.0,
                cruise_speed_kts=480.0,
                cruise_altitude_fl=0,
                initial_progress=0.0,
                status="ALERT-5 STANDBY",
            ),
        ]

        # Corridors state
        self.corridors = {
            "Corridor Charlie-7": {"condition": "CLEAR", "threat": 0.05, "wind": "260/15 kts"},
            "Corridor Alpha-1": {"condition": "CLEAR", "threat": 0.08, "wind": "290/22 kts"},
            "Corridor Alpha-1 Detour": {"condition": "CLEAR", "threat": 0.02, "wind": "310/18 kts"},
        }

        self.log_event("SYSTEM", "Operational telemetry simulator initialized. Connecting to engine.")
        self.fetch_backend_status()

    def log_event(self, source: str, message: str):
        t_str = self.sim_time.strftime("%H:%M:%S UTC")
        self.event_log.insert(0, {"time": t_str, "source": source, "msg": message})
        if len(self.event_log) > 8:
            self.event_log.pop()

    def fetch_backend_status(self):
        try:
            res = self.client.get(f"{self.engine_url}/api/v1/status")
            if res.status_code == 200:
                d = res.json()
                self.revision = d.get("revision", self.revision)
                self.is_equilibrium = d.get("is_equilibrium", True)
                self.equilibrium_status = (
                    "EQUILIBRIUM MAINTAINED (OPTIMAL)"
                    if self.is_equilibrium
                    else "EQUILIBRIUM BREACHED -> SOLVING"
                )
        except Exception:
            pass

    def send_telemetry_batch(self):
        """Transmit real-time telemetry stream to the agent engine."""
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            events = []
            for s in self.sorties:
                if s.status in ("IN-FLIGHT", "REROUTED"):
                    events.append({
                        "event_type": "flight.telemetry",
                        "entityId": s.airframe_id,
                        "source_id": "ADS-B-TRANSPONDER",
                        "sequence": int(time.time()),
                        "observed_at": now_iso,
                        "payload": {
                            "callsign": s.callsign,
                            "speed_kts": s.current_speed_kts,
                            "altitude_ft": s.current_altitude_ft,
                            "fuel_percent": round(s.fuel_percent, 1),
                            "distance_covered_km": round(s.progress * s.total_distance_km, 1),
                            "oat_c": s.oat_celsius,
                            "humidity_pct": s.humidity_percent,
                            "cold_chain_c": s.cold_chain_temp_c,
                        }
                    })
            if events:
                self.client.post(f"{self.engine_url}/api/v1/events", json=events[0])
        except Exception:
            pass

    def inject_disruption(self, scenario: str):
        """Send disruption scenario to engine and trigger real CP-SAT replanning."""
        self.log_event("INJECT", f"Inducing scenario: {scenario.upper()}...")
        try:
            res = self.client.post(
                f"{self.engine_url}/api/v1/disruption",
                json={"scenario": scenario}
            )
            if res.status_code == 200:
                data = res.json()
                self.revision = data.get("revision", self.revision + 1)
                self.is_equilibrium = not data.get("equilibrium_broken", False)
                self.equilibrium_status = (
                    "CP-SAT REPLAN SUCCESSFUL (AUTONOMOUS EQUILIBRIUM RESTORED)"
                    if not self.is_equilibrium
                    else "EQUILIBRIUM MAINTAINED"
                )

                # Update live sorties based on scenario
                if scenario == "storm_front":
                    self.corridors["Corridor Charlie-7"]["condition"] = "SEVERE STORM CELL"
                    for s in self.sorties:
                        if s.id == "MSN-LOG-110":
                            s.status = "REROUTED"
                            s.delay_delta_min = 25
                            s.corridor = "Corridor Alpha-1 Detour (FL240 High Clearance, 780 km)"
                            s.total_distance_km = 780.0
                            s.est_arrival_utc = "12:10 UTC (T+01:40)"
                            s.safety_margin_min = 20  # 12:30 UTC - 12:10 UTC = exactly 20 min
                            s.delay_cause = "Corridor Charlie-7 closed by storm -> CP-SAT rerouted via Alpha-1 Detour."
                    self.log_event("SOLVER", "CP-SAT rerouted MSN-LOG-110 via Corridor Alpha-1 (+25m). Safe margin +20m.")

                elif scenario == "threat_spike":
                    self.corridors["Corridor Alpha-1"]["threat"] = 0.85
                    for s in self.sorties:
                        if s.id == "MSN-OP-901":
                            s.corridor = "Corridor Alpha-1 (Low-Altitude Terrain Masked FL140, 850 km)"
                            s.current_altitude_ft = 14000
                            s.delay_cause = "S-400 radar active -> Ingress lowered to FL140 terrain-masked vector. 0 delay."
                    self.log_event("SOLVER", "Threat Agent vetoed high FL -> CP-SAT lowered altitude to FL140.")

                elif scenario == "mechanical_fault":
                    for s in self.sorties:
                        if s.id == "MSN-OP-901":
                            s.airframe_id = "RAF-RB011"
                            s.airframe_model = "Dassault Rafale EH (Standby Swap)"
                            s.tail_number = "RB011"
                            s.home_base = "Ambala AFS"
                            s.delay_cause = "Su-30 hydraulic fault -> CP-SAT auto-substituted standby Rafale RB011. 0 delay."
                    self.log_event("SOLVER", "Airframe Su-30 grounded -> CP-SAT auto-substituted reserve Rafale RB011.")

                elif scenario == "crew_fatigue":
                    for s in self.sorties:
                        if s.id == "MSN-LOG-110":
                            s.pilot = "Wg Cdr Rajesh Nair [PIC Reserve]"
                            s.duty_remaining_hrs = 8.5
                            s.delay_cause = "Sqn Ldr Sharma duty limit reached -> Reserve pilot Wg Cdr Nair swapped in."
                    self.log_event("SOLVER", "Crew fatigue guard triggered -> CP-SAT assigned standby pilot Wg Cdr Nair.")

                elif scenario == "reset":
                    self.corridors["Corridor Charlie-7"]["condition"] = "CLEAR"
                    self.corridors["Corridor Alpha-1"]["threat"] = 0.08
                    for s in self.sorties:
                        s.delay_delta_min = 0
                        s.delay_cause = ""
                        s.safety_margin_min = 45
                        s.status = "IN-FLIGHT" if s.id != "MSN-DEF-301" else "ALERT-5 STANDBY"
                    self.log_event("RESET", "Baseline operational equilibrium restored across all air corridors.")
            else:
                self.log_event("ERROR", f"Backend rejected disruption: HTTP {res.status_code}")
        except Exception as e:
            self.log_event("ERROR", f"Connection error injecting {scenario}: {e}")

    def render_hud(self):
        """Render high-contrast military ANSI telemetry HUD to the terminal."""
        out = []
        # Clear screen and return cursor to top
        out.append(f"{ESC}H{ESC}J")

        # Top Banner
        time_str = self.sim_time.strftime("%H:%M:%S UTC")
        speed_badge = f"{self.time_speed:g}x SPEED"
        status_badge = "PAUSED" if self.paused else "LIVE STREAMING"

        out.append(f"{C_ORANGE_BG}{BOLD}  MAGI DEFENSE C2 TELEMETRY & TACTICAL FLIGHT SIMULATOR  {RESET}")
        out.append(
            f"{BOLD}SIM CLOCK:{RESET} {C_WHITE}{time_str}{RESET}  |  "
            f"{BOLD}ACCELERATION:{RESET} {C_CYAN}{speed_badge}{RESET}  |  "
            f"{BOLD}STATUS:{RESET} {C_GREEN if not self.paused else C_AMBER}{status_badge}{RESET}  |  "
            f"{BOLD}REVISION:{RESET} {C_ORANGE}REV #{self.revision}{RESET}"
        )
        out.append(
            f"{BOLD}ENGINE LINK:{RESET} {C_CYAN}{self.engine_url}{RESET}  |  "
            f"{BOLD}STATE:{RESET} {C_GREEN if self.is_equilibrium else C_RED}{self.equilibrium_status}{RESET}"
        )
        out.append(f"{C_GRAY}{'=' * 98}{RESET}")

        # Active Sorties Flight Board
        out.append(f"{BOLD}{C_WHITE}ACTIVE TACTICAL SORTIES & FLIGHT KINEMATICS:{RESET}")
        out.append(
            f"{DIM}  CALLSIGN      AIRCRAFT / TAIL      SPEED    ALTITUDE    DIST / REMAIN    FUEL    TEMP / HUM    STATUS{RESET}"
        )
        out.append(f"{C_GRAY}{'-' * 98}{RESET}")

        for s in self.sorties:
            # Format status color
            if s.status == "REROUTED":
                st_color = C_ORANGE
            elif s.status == "IN-FLIGHT":
                st_color = C_CYAN
            elif s.status == "ALERT-5 STANDBY":
                st_color = C_PURPLE
            elif s.status == "TOUCHDOWN / LANDED":
                st_color = C_GREEN
            else:
                st_color = C_WHITE

            progress_pct = int(s.progress * 100)
            dist_km = int(s.progress * s.total_distance_km)
            total_km = int(s.total_distance_km)

            # Altitude label
            if s.current_altitude_ft >= 18000:
                alt_str = f"FL{int(s.current_altitude_ft/100)}"
            else:
                alt_str = f"{int(s.current_altitude_ft)} ft"

            temp_str = f"{s.oat_celsius:+.0f}C / {s.humidity_percent}%"

            line1 = (
                f"  {BOLD}{s.callsign:<13}{RESET} "
                f"{s.airframe_model[:19]:<19} "
                f"{s.current_speed_kts:>4.0f} kts "
                f"{alt_str:>8}   "
                f"{dist_km:>4}/{total_km:<4} km ({progress_pct:>2}%) "
                f"{s.fuel_percent:>4.0f}%   "
                f"{temp_str:<11} "
                f"{st_color}{BOLD}{s.status}{RESET}"
            )
            out.append(line1)

            # Route & pilot sub-line with progress bar
            bar_len = 24
            filled = int(s.progress * bar_len)
            pbar = f"{C_ORANGE}{'█' * filled}{C_GRAY}{'░' * (bar_len - filled)}{RESET}"

            extra_info = ""
            if s.is_cold_chain and s.cold_chain_temp_c is not None:
                extra_info += f" | {C_CYAN}❄ Plasma: {s.cold_chain_temp_c:.1f}°C (Safe){RESET}"
            if s.delay_delta_min > 0:
                extra_info += f" | {C_AMBER}Delay: +{s.delay_delta_min}m (Margin: +{s.safety_margin_min}m){RESET}"

            line2 = (
                f"    {C_GRAY}├─ Pilot: {s.pilot} ({s.duty_remaining_hrs:.1f}h left) | "
                f"Route: {s.origin} -> {s.dest}{extra_info}{RESET}\n"
                f"    {C_GRAY}└─ [{pbar}] Corridor: {s.corridor}{RESET}"
            )
            out.append(line2)
            if s.delay_cause:
                out.append(f"       {C_AMBER}↳ Replan: {s.delay_cause}{RESET}")

        out.append(f"{C_GRAY}{'-' * 98}{RESET}")

        # Air Corridors & Radar Status
        out.append(f"{BOLD}{C_WHITE}AIR CORRIDORS & RADAR INTELLIGENCE:{RESET}")
        c_lines = []
        for c_name, c_info in self.corridors.items():
            cond_color = C_RED if "STORM" in c_info["condition"] else C_GREEN
            threat_color = C_RED if c_info["threat"] > 0.5 else C_GREEN
            c_lines.append(
                f"  • {BOLD}{c_name}{RESET}: Condition: {cond_color}{c_info['condition']}{RESET} | "
                f"Threat: {threat_color}{c_info['threat']:.2f}{RESET} | Winds: {c_info['wind']}"
            )
        out.extend(c_lines)

        out.append(f"{C_GRAY}{'=' * 98}{RESET}")

        # Event Ticker Log
        out.append(f"{BOLD}{C_WHITE}RECENT ENGINE & SIMULATION EVENTS:{RESET}")
        for ev in self.event_log[:4]:
            out.append(f"  {C_GRAY}[{ev['time']}]{RESET} {BOLD}{ev['source']:<7}{RESET} {ev['msg']}")

        out.append(f"{C_GRAY}{'=' * 98}{RESET}")

        # Interactive Control Keys Legend
        out.append(
            f"{BOLD}{C_ORANGE}INTERACTIVE DISRUPTION INJECTION KEYS:{RESET}\n"
            f"  {BOLD}[S]{RESET} Inject Storm Front (Corridor Charlie)    "
            f"  {BOLD}[T]{RESET} Inject Hostile SAM Radar Threat\n"
            f"  {BOLD}[M]{RESET} Inject Hydraulic Mechanical Fault         "
            f"  {BOLD}[C]{RESET} Inject Pilot Duty Limit Exhaustion\n"
            f"  {BOLD}[R]{RESET} Reset Equilibrium to Baseline            "
            f"  {BOLD}[P]{RESET} Pause/Resume Clock   {BOLD}[+]/[-]{RESET} Speed (1x-10x)   {BOLD}[Q]{RESET} Quit"
        )

        sys.stdout.write("\n".join(out) + "\n")
        sys.stdout.flush()

    def run_loop(self):
        """Main execution loop tracking real time, handling hotkeys, and updating physics."""
        last_tick = time.time()
        last_telemetry = time.time()

        try:
            while self.running:
                now_tick = time.time()
                dt = now_tick - last_tick
                last_tick = now_tick

                # Advance simulation clock if not paused
                if not self.paused:
                    sim_seconds = dt * self.time_speed
                    self.sim_time += timedelta(seconds=sim_seconds)
                    for s in self.sorties:
                        s.tick(dt, self.time_speed)

                    # Send telemetry batch every 2 real seconds
                    if now_tick - last_telemetry >= 2.0:
                        self.send_telemetry_batch()
                        self.fetch_backend_status()
                        last_telemetry = now_tick

                # Render terminal UI
                self.render_hud()

                # Check for keyboard hotkeys
                key = check_keypress()
                if key:
                    if key == "q":
                        self.running = False
                        break
                    elif key == "s":
                        self.inject_disruption("storm_front")
                    elif key == "t":
                        self.inject_disruption("threat_spike")
                    elif key == "m":
                        self.inject_disruption("mechanical_fault")
                    elif key == "c":
                        self.inject_disruption("crew_fatigue")
                    elif key == "r":
                        self.inject_disruption("reset")
                    elif key == "p":
                        self.paused = not self.paused
                        self.log_event("CONTROL", f"Simulation {'PAUSED' if self.paused else 'RESUMED'}")
                    elif key in ("+", "="):
                        if self.time_speed < 10.0:
                            self.time_speed = (
                                2.0 if self.time_speed == 1.0 else 5.0 if self.time_speed == 2.0 else 10.0
                            )
                            self.log_event("CONTROL", f"Time acceleration increased to {self.time_speed}x")
                    elif key in ("-", "_"):
                        if self.time_speed > 1.0:
                            self.time_speed = (
                                5.0 if self.time_speed == 10.0 else 2.0 if self.time_speed == 5.0 else 1.0
                            )
                            self.log_event("CONTROL", f"Time acceleration decreased to {self.time_speed}x")

                # Sleep brief interval for ~5-10 FPS UI update rate
                time.sleep(0.15)

        except KeyboardInterrupt:
            pass
        finally:
            print(f"\n{C_GREEN}Simulator gracefully terminated. Operational state preserved.{RESET}")


def main():
    agent_engine_url = os.getenv("AGENT_ENGINE_URL", "http://127.0.0.1:8000")
    if len(sys.argv) > 1 and sys.argv[1].startswith("http"):
        agent_engine_url = sys.argv[1]

    sim = OperationalFlightSimulator(agent_engine_url=agent_engine_url)
    sim.run_loop()


if __name__ == "__main__":
    main()

