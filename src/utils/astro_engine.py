"""
astro_engine.py — real-time planetary position calculator.

Uses the `ephem` library (PyEphem) which implements the full VSOP87
planetary theory — same accuracy used by professional ephemeris tables.

For each horoscope generation call this module computes:
  • Which zodiac sign each planet currently occupies
  • Which planets are retrograde
  • Active aspects between planets (within a 6° orb)
  • Moon phase and sign
  • Any planets crossing into or out of a new sign within the period
  • Current solar season / ingress dates
  • North Node sign (mean node)

All results are returned as a structured dict that
horoscope_script_agent.py injects verbatim into the Groq prompt.
"""

import math
from datetime import date, timedelta
from typing import Optional
import ephem


# ── Constants ─────────────────────────────────────────────────────────────────

ZODIAC_SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer",
    "Leo", "Virgo", "Libra", "Scorpio",
    "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

# Degree boundaries for each sign (0° = 0° Aries)
SIGN_START_DEG = {sign: i * 30 for i, sign in enumerate(ZODIAC_SIGNS)}

# Planets to track (ephem objects)
PLANET_FACTORIES = {
    "Sun":     ephem.Sun,
    "Moon":    ephem.Moon,
    "Mercury": ephem.Mercury,
    "Venus":   ephem.Venus,
    "Mars":    ephem.Mars,
    "Jupiter": ephem.Jupiter,
    "Saturn":  ephem.Saturn,
    "Uranus":  ephem.Uranus,
    "Neptune": ephem.Neptune,
    "Pluto":   ephem.Pluto,
}

# Aspect definitions: (name, exact_degrees, max_orb)
ASPECTS = [
    ("conjunction",  0,   6),
    ("opposition",   180, 6),
    ("trine",        120, 5),
    ("square",       90,  5),
    ("sextile",      60,  4),
    ("quincunx",     150, 3),
]

# Planets considered slow-moving enough to matter for retrograde narration
RETROGRADE_PLANETS = ["Mercury", "Venus", "Mars", "Jupiter", "Saturn",
                      "Uranus", "Neptune", "Pluto"]


# ── Core helpers ──────────────────────────────────────────────────────────────

def _ephem_date(d: date) -> ephem.Date:
    return ephem.Date(d.strftime("%Y/%m/%d"))


def _ecliptic_longitude(body, d: date) -> float:
    """Return ecliptic longitude in degrees (0-360) for a body on date d."""
    body.compute(_ephem_date(d), epoch=ephem.J2000)
    # ephem gives ra/dec; convert to ecliptic
    ecl = ephem.Ecliptic(body, epoch=ephem.J2000)
    lon = math.degrees(ecl.lon) % 360
    return lon


def _longitude_to_sign(lon: float) -> tuple[str, float]:
    """Return (sign_name, degrees_into_sign) from an ecliptic longitude."""
    sign_index = int(lon // 30)
    deg_into   = lon % 30
    return ZODIAC_SIGNS[sign_index], round(deg_into, 1)


def _is_retrograde(planet_name: str, d: date) -> bool:
    """
    A planet is retrograde when its ecliptic longitude decreases day-to-day.
    We compare yesterday vs tomorrow to get a clean derivative.
    Sun and Moon never retrograde.
    """
    if planet_name in ("Sun", "Moon"):
        return False
    factory = PLANET_FACTORIES[planet_name]
    lon_yesterday = _ecliptic_longitude(factory(), d - timedelta(days=1))
    lon_tomorrow  = _ecliptic_longitude(factory(), d + timedelta(days=1))
    # Handle 0°/360° wrap-around
    diff = (lon_tomorrow - lon_yesterday + 540) % 360 - 180
    return diff < 0


def _angular_distance(a: float, b: float) -> float:
    """Shortest arc in degrees between two ecliptic longitudes."""
    diff = abs(a - b) % 360
    return diff if diff <= 180 else 360 - diff


def _find_aspects(positions: dict) -> list[dict]:
    """Find active aspects between all planet pairs."""
    planets = list(positions.keys())
    found = []
    for i in range(len(planets)):
        for j in range(i + 1, len(planets)):
            p1, p2 = planets[i], planets[j]
            lon1 = positions[p1]["longitude"]
            lon2 = positions[p2]["longitude"]
            arc  = _angular_distance(lon1, lon2)
            for aspect_name, exact, orb in ASPECTS:
                if abs(arc - exact) <= orb:
                    applying = _is_applying(p1, p2, arc, exact)
                    found.append({
                        "planet1":  p1,
                        "planet2":  p2,
                        "aspect":   aspect_name,
                        "orb":      round(abs(arc - exact), 1),
                        "applying": applying,   # True = building in strength
                    })
                    break   # only report the tightest aspect per pair
    return found


def _is_applying(p1: str, p2: str, current_arc: float, exact: float) -> bool:
    """
    Rough applying/separating check: if the faster body is moving
    toward the exact degree it is 'applying'.  We approximate by
    comparing today's arc to yesterday's.
    """
    try:
        today   = date.today()
        f1_now  = PLANET_FACTORIES[p1](); lon1_now = _ecliptic_longitude(f1_now, today)
        f2_now  = PLANET_FACTORIES[p2](); lon2_now = _ecliptic_longitude(f2_now, today)
        f1_yes  = PLANET_FACTORIES[p1](); lon1_yes = _ecliptic_longitude(f1_yes, today - timedelta(1))
        f2_yes  = PLANET_FACTORIES[p2](); lon2_yes = _ecliptic_longitude(f2_yes, today - timedelta(1))
        arc_now  = _angular_distance(lon1_now, lon2_now)
        arc_yes  = _angular_distance(lon1_yes, lon2_yes)
        return abs(arc_now - exact) < abs(arc_yes - exact)
    except Exception:
        return True   # default to applying when uncertain


def _moon_phase(d: date) -> str:
    moon = ephem.Moon()
    moon.compute(_ephem_date(d))
    phase = moon.phase   # 0-100 (illumination %)
    # Determine phase name from illumination + whether waxing/waning
    # Compute illumination one day later to determine waxing/waning
    moon_tomorrow = ephem.Moon()
    moon_tomorrow.compute(_ephem_date(d + timedelta(1)))
    waxing = moon_tomorrow.phase > moon.phase

    if phase < 2:
        return "New Moon"
    elif phase < 48:
        return "Waxing Crescent" if waxing else "Waning Crescent"
    elif phase < 52:
        return "First Quarter" if waxing else "Last Quarter"
    elif phase < 98:
        return "Waxing Gibbous" if waxing else "Waning Gibbous"
    else:
        return "Full Moon"


def _sign_ingresses(planet_name: str, start: date, end: date) -> list[dict]:
    """
    Return list of sign changes a planet makes between start and end dates.
    Checks daily — accurate enough for all but the fastest-moving bodies
    (Moon moves ~13°/day so is omitted from ingress tracking for weekly+).
    """
    factory = PLANET_FACTORIES[planet_name]
    ingresses = []
    prev_sign = None
    d = start
    while d <= end:
        body = factory()
        lon  = _ecliptic_longitude(body, d)
        sign, _ = _longitude_to_sign(lon)
        if prev_sign is not None and sign != prev_sign:
            ingresses.append({
                "planet": planet_name,
                "from_sign": prev_sign,
                "to_sign": sign,
                "date": d.isoformat(),
            })
        prev_sign = sign
        d += timedelta(1)
    return ingresses


def _north_node_sign(d: date) -> str:
    """True mean North Node sign. Ephem doesn't expose this directly,
    so we compute it from the Moon's ascending node."""
    # ephem.Moon().compute gives us moon.a_ra etc; for the node we use
    # a small Julian Day calculation.  The mean node regresses ~19.3°/year.
    jd = ephem.julian_date(_ephem_date(d))
    # Mean node longitude in degrees (Meeus, Astronomical Algorithms ch. 47)
    T = (jd - 2451545.0) / 36525.0
    omega = 125.0445479 - 1934.1362608 * T + 0.0020754 * T**2
    omega = omega % 360
    if omega < 0:
        omega += 360
    sign_idx = int(omega // 30)
    return ZODIAC_SIGNS[sign_idx]


# ── Public API ────────────────────────────────────────────────────────────────

def get_planetary_context(period: str, reference_date: Optional[date] = None) -> dict:
    """
    Compute the full real-time astrological context for a given period.

    Parameters
    ----------
    period         : "daily" | "weekly" | "monthly" | "yearly"
    reference_date : defaults to today

    Returns a dict ready to be serialised and injected into a Groq prompt.
    """
    today = reference_date or date.today()

    period_ends = {
        "daily":   today,
        "weekly":  today + timedelta(6),
        "monthly": (today.replace(day=1) + timedelta(32)).replace(day=1) - timedelta(1),
        "yearly":  today.replace(month=12, day=31),
    }
    end_date = period_ends.get(period, today)

    # ── 1. Current planetary positions ───────────────────────────────────────
    positions = {}
    for name, factory in PLANET_FACTORIES.items():
        body = factory()
        lon  = _ecliptic_longitude(body, today)
        sign, deg = _longitude_to_sign(lon)
        retro = _is_retrograde(name, today) if name in RETROGRADE_PLANETS else False
        positions[name] = {
            "sign":      sign,
            "degree":    deg,
            "longitude": lon,
            "retrograde": retro,
        }

    # ── 2. Active aspects ────────────────────────────────────────────────────
    aspects = _find_aspects(positions)

    # ── 3. Moon details ──────────────────────────────────────────────────────
    moon_phase = _moon_phase(today)
    moon_sign  = positions["Moon"]["sign"]

    # ── 4. Retrograde summary ────────────────────────────────────────────────
    retrogrades = [
        f"{p} Rx in {positions[p]['sign']}"
        for p in RETROGRADE_PLANETS
        if positions[p]["retrograde"]
    ]

    # ── 5. Sign ingresses during the period ──────────────────────────────────
    ingresses = []
    # Track all planets except Moon for weekly/monthly/yearly
    # For daily, also track Moon ingresses
    planets_for_ingress = list(PLANET_FACTORIES.keys())
    if period in ("monthly", "yearly"):
        planets_for_ingress = [p for p in planets_for_ingress if p != "Moon"]

    if end_date > today:
        for p in planets_for_ingress:
            ingresses.extend(_sign_ingresses(p, today, end_date))

    # ── 6. North Node ────────────────────────────────────────────────────────
    north_node_sign = _north_node_sign(today)
    south_node_sign = ZODIAC_SIGNS[(ZODIAC_SIGNS.index(north_node_sign) + 6) % 12]

    # ── 7. Format readable position summary ─────────────────────────────────
    position_lines = []
    for planet, data in positions.items():
        rx = " (Retrograde)" if data["retrograde"] else ""
        position_lines.append(
            f"  {planet}: {data['degree']:.1f}° {data['sign']}{rx}"
        )

    aspect_lines = []
    for asp in aspects:
        app_sep = "applying" if asp["applying"] else "separating"
        aspect_lines.append(
            f"  {asp['planet1']} {asp['aspect']} {asp['planet2']}"
            f" (orb {asp['orb']}°, {app_sep})"
        )

    ingress_lines = [
        f"  {ing['date']}: {ing['planet']} moves from {ing['from_sign']} → {ing['to_sign']}"
        for ing in ingresses
    ]

    return {
        "reference_date":    today.isoformat(),
        "period":            period,
        "period_end":        end_date.isoformat(),
        "moon_phase":        moon_phase,
        "moon_sign":         moon_sign,
        "north_node_sign":   north_node_sign,
        "south_node_sign":   south_node_sign,
        "retrogrades":       retrogrades,
        "positions":         positions,
        "aspects":           aspects,
        "ingresses":         ingresses,
        # Pre-formatted strings for direct injection into the prompt
        "positions_text":    "\n".join(position_lines),
        "aspects_text":      "\n".join(aspect_lines) if aspect_lines else "  No major aspects within 6° orb",
        "ingresses_text":    "\n".join(ingress_lines) if ingress_lines else "  No sign changes during this period",
        "retrogrades_text":  ", ".join(retrogrades) if retrogrades else "None",
    }


def get_sign_transits(sign: str, context: dict) -> dict:
    """
    From the full planetary context, extract what is specifically
    relevant to a given zodiac sign:

    - Which planets are currently in this sign (stellium etc.)
    - Which planets are in opposite sign (opposition pressure)
    - Which planets are in trine signs (ease / flow)
    - Which planets are in square signs (tension)
    - How the ruling planet is doing (its sign, retrograde status, aspects)
    - Any ingresses INTO this sign during the period

    Returns a dict with pre-formatted text blocks for the Groq prompt.
    """
    from config.zodiac import (
        SIGN_RULERS, SIGN_ELEMENTS, SIGN_MODALITIES,
        SIGN_NATURAL_HOUSE, HOUSE_THEMES,
        ZODIAC_SIGNS as _SIGNS,
    )

    idx        = _SIGNS.index(sign)
    opp_sign   = _SIGNS[(idx + 6) % 12]
    trine1     = _SIGNS[(idx + 4) % 12]
    trine2     = _SIGNS[(idx + 8) % 12]
    square1    = _SIGNS[(idx + 3) % 12]
    square2    = _SIGNS[(idx + 9) % 12]
    sextile1   = _SIGNS[(idx + 2) % 12]
    sextile2   = _SIGNS[(idx + 10) % 12]

    positions  = context["positions"]
    ruler_trad = SIGN_RULERS[sign]["traditional"]
    ruler_mod  = SIGN_RULERS[sign]["modern"]

    # Planets in the sign itself
    in_sign = [
        p for p, d in positions.items() if d["sign"] == sign
    ]

    # Planets in opposition sign
    opposing = [
        p for p, d in positions.items() if d["sign"] == opp_sign
    ]

    # Planets in trine signs
    trining = [
        f"{p} in {positions[p]['sign']}"
        for p in positions
        if positions[p]["sign"] in (trine1, trine2)
    ]

    # Planets in square signs
    squaring = [
        f"{p} in {positions[p]['sign']}"
        for p in positions
        if positions[p]["sign"] in (square1, square2)
    ]

    # Ruling planet status
    ruler_data = positions.get(ruler_trad, {})
    ruler_sign = ruler_data.get("sign", "unknown")
    ruler_rx   = ruler_data.get("retrograde", False)
    ruler_deg  = ruler_data.get("degree", 0)

    # Ruler dignity — is it strong or weak?
    from config.zodiac import PLANET_DIGNITY
    dignity_info = PLANET_DIGNITY.get(ruler_trad, {})
    if ruler_sign == sign:
        ruler_dignity = "domicile (strongest placement — at home)"
    elif ruler_sign == dignity_info.get("exaltation"):
        ruler_dignity = "exalted (very strong, gifts come easily)"
    elif ruler_sign in dignity_info.get("detriment", []):
        ruler_dignity = "in detriment (challenged, must work harder)"
    elif ruler_sign == dignity_info.get("fall"):
        ruler_dignity = "in fall (weakened, requires extra effort)"
    else:
        ruler_dignity = "in neutral dignity"

    # Aspects involving the ruling planet
    ruler_aspects = [
        f"{asp['aspect']} with {asp['planet2'] if asp['planet1']==ruler_trad else asp['planet1']}"
        f" (orb {asp['orb']}°, {'applying' if asp['applying'] else 'separating'})"
        for asp in context["aspects"]
        if asp["planet1"] == ruler_trad or asp["planet2"] == ruler_trad
    ]

    # Ingresses INTO this sign
    arriving = [
        f"{ing['planet']} enters {sign} on {ing['date']}"
        for ing in context["ingresses"]
        if ing["to_sign"] == sign
    ]

    # Natural house and its themes
    house = SIGN_NATURAL_HOUSE[sign]
    house_theme = HOUSE_THEMES[house]

    # Build readable text blocks
    def _fmt_list(items, empty="none"):
        return ", ".join(items) if items else empty

    planets_in_sign_text = (
        f"{', '.join(in_sign)} are currently transiting {sign}"
        if in_sign else f"No major planets are currently transiting {sign}"
    )

    ruler_text = (
        f"{ruler_trad} (ruling planet) is at {ruler_deg:.1f}° {ruler_sign}, "
        f"{ruler_dignity}"
        + (" — RETROGRADE" if ruler_rx else "")
        + (f". Active aspects: {'; '.join(ruler_aspects)}" if ruler_aspects else "")
    )
    if ruler_trad != ruler_mod:
        mod_data = positions.get(ruler_mod, {})
        ruler_text += (
            f". Modern co-ruler {ruler_mod} is in {mod_data.get('sign','?')}"
            + (" Rx" if mod_data.get("retrograde") else "")
        )

    return {
        "in_sign":            in_sign,
        "opposing":           opposing,
        "trining":            trining,
        "squaring":           squaring,
        "arriving":           arriving,
        "ruler_trad":         ruler_trad,
        "ruler_mod":          ruler_mod,
        "ruler_sign":         ruler_sign,
        "ruler_retrograde":   ruler_rx,
        "ruler_dignity":      ruler_dignity,
        "ruler_aspects":      ruler_aspects,
        "house":              house,
        "house_theme":        house_theme,
        # Pre-formatted blocks
        "planets_in_sign_text": planets_in_sign_text,
        "ruler_text":           ruler_text,
        "trining_text":         _fmt_list(trining, "no planets in trine signs"),
        "squaring_text":        _fmt_list(squaring, "no planets in square signs"),
        "opposing_text":        _fmt_list(opposing, "none"),
        "arriving_text":        _fmt_list(arriving, "no planets entering this sign during the period"),
    }
