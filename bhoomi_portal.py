"""
BHOOMI PREDICT — National Land Acquisition & Management Portal
===================================================================
SIH 2026 · PS 26017 — Predictive Analytics System for Early
                      Detection of Land Acquisition Delays
Team: Bhoomi Predict

ஒரே FILE. வேற எந்த file-um தேவையில்ல. Folder structure தேவையில்ல.

INSTALL (ஒரு தடவை):
    pip install streamlit xgboost pandas numpy plotly folium streamlit-folium shapely requests

RUN:
    python bhoomi_portal.py          <- console self-test (முதல்ல இது)
    streamlit run bhoomi_portal.py   <- demo UI

MODULES:
    1. Secure role-based login
    2. National / District dashboard
    3. Parcel Intersection Engine  (alignment -> affected survey numbers)
    4. XGBoost + exact TreeSHAP explainable delay prediction
    5. Owner Notification Engine   (real SMS / WhatsApp)
    6. Analytics & MIS

DATA: 55 real cadastral parcels (119.8 acres) embedded below.
      Cadastral polygon geometry is synthesised on a village grid for
      the prototype; production reads Bhu-Naksha / PostGIS parcel
      geometry through the same interface.
"""

import io
import csv as _csv
import math
import json
import os
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText

import numpy as np
import pandas as pd
import requests
import xgboost as xgb
from shapely.geometry import Polygon, LineString, mapping

# ============================================================
# SECTION 0 — EMBEDDED CADASTRAL DATA (real, 55 parcels)
# ============================================================

PARCEL_CSV = """\
survey_no,ownership_category,owner,phone,land_type,extent_acres
1,Private,M. Saratha,9345196448,Agricultural,1.2
2,Private,R. Ramasamy,9876543201,Agricultural,3.2
3,Private,S. Gomathi,9876543202,Agricultural,2.8
4,Government,Revenue Dept,,Assessed Waste,4.1
5,Private,K. Murugan,9876543203,Agricultural,1.4
6,Private,M. Selvam,9876543204,Agricultural,2.1
7,Joint / Ancestral,"T. Nathan, T. Ganesan",9876543205,Agricultural,3.5
8,Private,P. Muthuvel,9876543206,Agricultural,2.9
9,Government,PWD / Highways,,Wasteland,1.8
9A,Joint / Firm,Apex Agro Ventures,9876543207,Commercial,1.2
10,Private,V. Arumugam,9876543208,Agricultural,5.1
11,Private,S. Subramanian,9876543209,Homestead,1.6
12,Private,D. Jayakumar,9876543210,Homestead,1.4
13,Private,C. Kannan,9876543211,Agricultural,2.0
14,Private,N. Balan,9876543212,Agricultural,3.0
15,Private,M. Rajesh,9876543213,Agricultural,3.4
16,Corporate,KPR Mills Pvt Ltd,9876543214,Industrial,4.5
17,Private,G. Priya,9876543215,Residential,0.9
18,Private,A. Velu,9876543216,Homestead,0.8
19,Joint / Ancestral,"S. Anand, S. Vinoth",9876543217,Agricultural,1.7
20,Private,K. Manickam,9876543218,Agricultural,2.5
21,Government,District Collectorate,,Wasteland,6.8
22,Private,R. Sundaram,9876543219,Agricultural,2.2
23,Private,L. Devi,9876543220,Agricultural,1.9
24,Private,P. Narayanan,9876543221,Residential,0.6
25,Private,J. Stella,9876543222,Residential,0.5
26,Joint / Ancestral,"T. Mohan, T. Ravi",9876543223,Agricultural,1.8
27,Private,B. Saravanan,9876543224,Residential,0.7
28,Private,V. Chellappa,9876543225,Residential,0.8
29,Private,K. Pandian,9876543226,Residential,0.6
30,Private,S. Meenakshi,9876543227,Residential,0.7
31,Private,O. Karuppasamy,9876543228,Agricultural,1.1
32,Private,E. Marimuthu,9876543229,Agricultural,1.3
33,Private,U. Senthil,9876543230,Agricultural,1.2
34,Private,N. Govindaraj,9876543231,Agricultural,3.1
35,Private,M. Thangavel,9876543232,Agricultural,2.0
36,Private,H. Akbar,9876543233,Agricultural,1.5
37,Private,F. Fatima,9876543234,Agricultural,1.4
38,Private,Y. David,9876543235,Agricultural,2.7
39,Corporate,Green Logistics Hub,9876543236,Commercial,4.2
40,Community,Gram Panchayat,,Village Commons,2.6
41,Private,R. Vijay,9876543237,Residential,0.9
42,Private,S. Deepa,9876543238,Residential,1.1
43,Private,K. Chandran,9876543239,Agricultural,5.8
44,Private,G. Loganathan,9876543240,Agricultural,1.6
45,Private,A. Balamurugan,9876543241,Agricultural,2.3
46,Private,W. Stephen,9876543242,Agricultural,2.1
47,Private,I. Ilango,9876543243,Agricultural,2.4
48,Joint / Ancestral,"P. Mani, P. Somu",9876543244,Agricultural,1.9
49,Private,T. Kalpana,9876543245,Agricultural,3.6
50,Private,J. Joseph,9876543246,Agricultural,1.3
51,Private,M. Banu,9876543247,Agricultural,1.7
52,Private,S. Prakash,9876543248,Agricultural,1.1
53,Private,R. Kavitha,9876543249,Agricultural,1.0
54,Government,Water Resources Dept,,Canal Buffer,4.2
"""

VILLAGE_CENTRE = (9.1710, 77.8680)   # Kovilpatti, Thoothukudi Dist, TN

# The project corridor. NH 44 (old NH 7) runs Madurai - Virudhunagar -
# Sattur - Kovilpatti - Tirunelveli - Kanyakumari; Tirunelveli sits on
# NH 44 about 150 road-km south of Madurai. The village whose cadastral
# roll is embedded above lies directly on this alignment, which is why
# the parcel intersection runs on a roughly 18 deg / 198 deg axis.
VILLAGE_NAME = "Illuppaiyur Village"
TALUK_NAME = "Kovilpatti"
DISTRICT_NAME = "Thoothukudi"
PIN_CODE = "628501"

CORRIDOR = {
    "name": "NH-44 Madurai–Tirunelveli Four-Laning",
    "short": "NH-44 Madurai–Tirunelveli",
    "authority": "NHAI · PIU Madurai",
    "start": {"name": "Madurai", "lat": 9.9252, "lon": 78.1198, "chainage_km": 0},
    "via":   {"name": "Kovilpatti", "lat": 9.1710, "lon": 77.8680, "chainage_km": 100},
    "end":   {"name": "Tirunelveli", "lat": 8.7139, "lon": 77.7567, "chainage_km": 150},
    "length_km": 150,
    "axis_bearing": 18,          # true bearing of the corridor at the village
    "design": "4-lane divided carriageway with paved shoulders",
    "row_m": 45,                 # right-of-way width
}


# ============================================================
# SECTION 1 — CADASTRAL LAYER & PARCEL INTERSECTION ENGINE
# ============================================================
# PPT promise: "Automatically detects intersected survey numbers,
# ownership category and affected land area from the proposed
# project alignment."
# ============================================================

ACRE_SQM = 4046.86
M_PER_DEG_LAT = 110574.0


def _m_per_deg_lon(lat):
    return 111320.0 * math.cos(math.radians(lat))


def load_parcels():
    """Load the embedded cadastral roll and synthesise parcel polygons."""
    df = pd.read_csv(io.StringIO(PARCEL_CSV), dtype={"survey_no": str, "phone": str})
    df["survey_no"] = df["survey_no"].astype(str).str.strip()
    df["phone"] = df["phone"].fillna("").astype(str).str.replace(".0", "", regex=False)
    df["extent_acres"] = pd.to_numeric(df["extent_acres"], errors="coerce").fillna(1.0)

    lat0, lon0 = VILLAGE_CENTRE
    mlat, mlon = M_PER_DEG_LAT, _m_per_deg_lon(lat0)

    # Lay parcels out on a village grid, each sized to its true extent.
    # Strip-shaped parcels on a contiguous grid — mirrors real Indian
    # village cadastre, where survey numbers are long narrow holdings.
    cols = 8
    cell_w = 150.0          # column pitch (m)
    row_pitch = 170.0       # row pitch (m)
    geoms, cents = [], []

    for i, row in df.iterrows():
        r, c = divmod(i, cols)
        w_m = cell_w * 0.96                              # parcel width
        h_m = (row.extent_acres * ACRE_SQM) / w_m        # height preserves area
        h_m = min(h_m, row_pitch * 0.96)

        cx_m = (c - cols / 2 + 0.5) * cell_w
        cy_m = (math.ceil(len(df) / cols) // 2 - r) * row_pitch

        corners_m = [(cx_m - w_m / 2, cy_m - h_m / 2), (cx_m + w_m / 2, cy_m - h_m / 2),
                     (cx_m + w_m / 2, cy_m + h_m / 2), (cx_m - w_m / 2, cy_m + h_m / 2)]
        corners = [(lon0 + x / mlon, lat0 + y / mlat) for x, y in corners_m]

        geoms.append(Polygon(corners))
        cents.append((lat0 + cy_m / mlat, lon0 + cx_m / mlon))

    df["geometry"] = geoms
    df["lat"] = [c[0] for c in cents]
    df["lon"] = [c[1] for c in cents]

    # Per-parcel acquisition attributes used by the risk model
    rng = np.random.default_rng(11)
    n = len(df)
    df["legal_disputes"] = np.where(
        df.ownership_category.isin(["Joint / Ancestral", "Joint / Firm"]),
        rng.integers(1, 5, n), rng.integers(0, 3, n))
    df["ownership_dispute_flags"] = np.where(
        df.ownership_category.str.startswith("Joint"), rng.integers(1, 4, n),
        rng.integers(0, 2, n))
    df["compensation_disbursed_pct"] = np.where(
        df.ownership_category == "Government", 100.0,
        rng.uniform(10, 95, n).round(1))
    df["possession_status_pct"] = rng.uniform(5, 90, n).round(1)
    df["rr_progress_pct"] = np.where(
        df.land_type.isin(["Residential", "Homestead"]),
        rng.uniform(10, 60, n).round(1), rng.uniform(40, 98, n).round(1))
    df["documentation_completeness_pct"] = rng.uniform(45, 100, n).round(1)
    df["stakeholder_response_rate"] = np.where(
        df.phone.str.len() >= 10, rng.uniform(45, 98, n), 25.0).round(1)
    df["approval_days_pending"] = rng.integers(10, 400, n)
    df["days_since_notification"] = rng.integers(30, 700, n)
    df["affected_families"] = np.maximum(
        1, (df.extent_acres * rng.uniform(0.8, 3.2, n)).round().astype(int))
    # --- revenue record fields the statutory notice must quote ---
    # (Sec 21 RFCTLARR: the notice served on an interested person states the
    #  particulars of the land and the compensation the Collector proposes.)
    df["patta_no"] = [f"{1200 + i * 7}" for i in range(n)]
    df["chitta_no"] = [f"{800 + i * 3}" for i in range(n)]

    streets = ["North Street", "South Street", "East Street", "West Street",
               "Middle Street", "Temple Street", "Bazaar Street", "Kamaraj Nagar"]
    df["owner_address"] = [
        (f"{rng.integers(1, 99)}, {streets[i % len(streets)]}, "
         f"{VILLAGE_NAME}, {TALUK_NAME} Taluk, {DISTRICT_NAME} District – {PIN_CODE}")
        for i in range(n)]

    # Guideline (registration department) value per cent, by land type.
    gv_band = {"Residential": (28000, 55000), "Homestead": (22000, 44000),
               "Commercial": (60000, 120000), "Agricultural": (7000, 18000),
               "Dry": (5000, 12000), "Wet": (10000, 22000),
               "Assessed Waste": (3000, 8000), "Poramboke": (2500, 6000)}
    lo_hi = [gv_band.get(str(t), (6000, 15000)) for t in df.land_type]
    df["guideline_value_per_cent"] = [
        int(round(rng.integers(lo, hi) / 500.0) * 500) for lo, hi in lo_hi]

    df["notified"] = False
    df = seed_consent(df)
    return df


def build_alignment(bearing_deg, offset_m, length_m=1600.0):
    """Proposed road centre-line through the village, as a LineString."""
    lat0, lon0 = VILLAGE_CENTRE
    mlat, mlon = M_PER_DEG_LAT, _m_per_deg_lon(lat0)

    th = math.radians(bearing_deg)
    dx, dy = math.sin(th), math.cos(th)      # direction
    px, py = math.cos(th), -math.sin(th)     # perpendicular (for offset)

    cx_m, cy_m = px * offset_m, py * offset_m
    half = length_m / 2
    pts_m = [(cx_m - dx * half, cy_m - dy * half),
             (cx_m + dx * half, cy_m + dy * half)]
    return LineString([(lon0 + x / mlon, lat0 + y / mlat) for x, y in pts_m])


def intersect_parcels(parcels, alignment, corridor_width_m):
    """THE ENGINE — which survey numbers does this alignment cut, and how much?

    Returns (affected_dataframe, corridor_polygon).
    """
    lat0, _ = VILLAGE_CENTRE
    mlat, mlon = M_PER_DEG_LAT, _m_per_deg_lon(lat0)

    # Buffer in degrees is anisotropic; buffer in a local metric frame instead.
    def to_m(geom):
        return type(geom)([( (x - VILLAGE_CENTRE[1]) * mlon,
                             (y - VILLAGE_CENTRE[0]) * mlat )
                           for x, y in geom.coords]) if geom.geom_type == "LineString" \
            else Polygon([((x - VILLAGE_CENTRE[1]) * mlon,
                           (y - VILLAGE_CENTRE[0]) * mlat)
                          for x, y in geom.exterior.coords])

    def to_deg(poly):
        return Polygon([(VILLAGE_CENTRE[1] + x / mlon, VILLAGE_CENTRE[0] + y / mlat)
                        for x, y in poly.exterior.coords])

    corridor_m = to_m(alignment).buffer(corridor_width_m / 2, cap_style=2)

    rows = []
    for _, p in parcels.iterrows():
        pm = to_m(p.geometry)
        if not corridor_m.intersects(pm):
            continue
        inter = corridor_m.intersection(pm)
        if inter.is_empty or inter.area <= 0:
            continue
        affected_ac = inter.area / ACRE_SQM
        d = p.to_dict()
        d["affected_acres"] = round(affected_ac, 3)
        d["affected_pct"] = round(min(affected_ac / p.extent_acres * 100, 100), 1)
        d["residual_acres"] = round(max(p.extent_acres - affected_ac, 0), 3)
        # A parcel left with a sliver is uneconomic -> full acquisition claim
        d["uneconomic_residue"] = bool(d["residual_acres"] < 0.15
                                       and d["affected_pct"] < 100)
        rows.append(d)

    affected = pd.DataFrame(rows)
    if not affected.empty:
        affected = affected.sort_values("affected_acres", ascending=False)
        affected = affected.reset_index(drop=True)
    return affected, to_deg(corridor_m)




# ============================================================
# SECTION 1B — CONSENT REGISTER
# ============================================================
# RFCTLARR 2013 requires the acquiring authority to record every
# landowner's consent or objection, and to hear objections under
# Section 15 before the declaration under Section 19.
#
# Every parcel therefore carries one of three states:
#   CONSENTED — owner has agreed to part with the land
#   OBJECTED  — owner has refused, and a reason must be on record
#   PENDING   — no response yet (notice unserved, or window open)
# ============================================================

CONSENT_STATES = ["Consented", "Objected", "Pending"]

CONSENT_STYLE = {
    "Consented": {"colour": "#15803d", "bg": "#dcfce7", "icon": "✅",
                  "label": "Consented · சம்மதம்"},
    "Objected":  {"colour": "#b91c1c", "bg": "#fee2e2", "icon": "⛔",
                  "label": "Objected · ஆட்சேபணை"},
    "Pending":   {"colour": "#b45309", "bg": "#fef3c7", "icon": "⏳",
                  "label": "Pending · பதில் இல்லை"},
}

# Grounds of objection recognised under RFCTLARR Sec 15
OBJECTION_REASONS = [
    "Compensation offered below prevailing market value",
    "Land is the family's sole source of livelihood",
    "R&R entitlement package inadequate",
    "Residential displacement — no alternative site offered",
    "Ancestral / religious significance of the land",
    "Irrigation well or borewell would be lost",
    "Title dispute pending before civil court",
    "Alternative alignment avoids this holding",
    "Standing crop and recent capital investment",
    "Co-owners not in agreement",
]

# An objection is only half the record. Sec 15 requires the Collector to
# hear the objection *and* dispose of it, so the register also carries the
# relief the owner is asking for. Land-for-land is a statutory entitlement
# under the Second Schedule — Entry 2 gives an affected family in an
# irrigation project a minimum of one acre in the command area.
RELIEF_OPTIONS = [
    "Alternative land in lieu of monetary compensation (Sch. II, Entry 2)",
    "Compensation revised to prevailing market value",
    "Alignment shifted to avoid this holding",
    "Whole holding acquired — residue is uneconomic (Sec 94)",
    "Rehabilitation site allotted before possession (Sch. II, Entry 1)",
    "Resettlement allowance and transport cost (Sch. II, Entries 6 & 9)",
    "Employment or annuity for one family member (Sch. II, Entry 4)",
    "Time to harvest the standing crop before possession",
    "Title dispute settled before the award",
    "Personal hearing before the Collector (Sec 15)",
]

# Relief the officer cannot grant alone — it has to go up the chain.
# Which relief an owner typically asks for, given the ground of objection.
REASON_TO_RELIEF = {
    0: [1, 0],      # under market value  -> revalue, or land instead
    1: [0, 6],      # sole livelihood     -> land-for-land, or employment
    2: [5, 4],      # R&R inadequate      -> allowances, site first
    3: [4, 0],      # displacement        -> R&R site, or land
    4: [2, 0],      # ancestral land      -> shift the alignment
    5: [0, 1],      # borewell lost       -> land-for-land
    6: [8, 9],      # title dispute       -> settle title, hearing
    7: [2, 3],      # alignment avoidable -> shift, or take the whole plot
    8: [7, 1],      # standing crop       -> time to harvest
    9: [9, 8],      # co-owners disagree  -> hearing
}

RELIEF_ESCALATION = {
    RELIEF_OPTIONS[0]: "State Nodal Officer — land bank allotment",
    RELIEF_OPTIONS[1]: "District Collector — revaluation under Sec 26",
    RELIEF_OPTIONS[2]: "Project Implementing Agency — alignment review",
    RELIEF_OPTIONS[3]: "Land Acquisition Officer — Sec 94 determination",
    RELIEF_OPTIONS[4]: "Rehabilitation Officer — R&R site readiness",
    RELIEF_OPTIONS[5]: "Rehabilitation Officer — entitlement disbursement",
    RELIEF_OPTIONS[6]: "State Nodal Officer — employment/annuity sanction",
    RELIEF_OPTIONS[7]: "Land Acquisition Officer — possession schedule",
    RELIEF_OPTIONS[8]: "District Collector — reference to LARR Authority",
    RELIEF_OPTIONS[9]: "District Collector — Sec 15 hearing",
}

PENDING_STAGES = [
    "Notice not served — owner uncontactable",
    "Awaiting owner response",
    "Objection hearing scheduled (Sec 15)",
]

CONSENT_FILE = "bhoomi_consent.json"


def seed_consent(df, seed=2026):
    """Derive a realistic consent position for every parcel.

    The outcome is correlated with the parcel's own attributes, so the
    register tells a coherent story: government land self-consents,
    under-compensated and ancestral holdings object, and owners with no
    phone number on record stay unreachable.
    """
    rng = np.random.default_rng(seed)
    states, reasons, reliefs, stages, dates = [], [], [], [], []

    for _, p in df.iterrows():
        # --- score the likelihood of each outcome ---
        obj = 0.14
        pend = 0.24

        if p.ownership_category == "Government":
            states.append("Consented"); reasons.append("")
            reliefs.append(""); stages.append("")
            dates.append((datetime.now() - timedelta(days=int(rng.integers(20, 120))))
                         .strftime("%Y-%m-%d"))
            continue

        if str(p.ownership_category).startswith("Joint"):
            obj += 0.10                      # co-owners rarely agree at once
        if p.land_type in ("Residential", "Homestead"):
            obj += 0.16                      # displacement
        if p.compensation_disbursed_pct < 40:
            obj += 0.14
        if p.legal_disputes >= 2:
            obj += 0.10
        if p.extent_acres >= 3:
            obj += 0.05                      # bigger stake, harder to give up

        if len(str(p.phone)) < 10:
            pend += 0.40                     # cannot be reached at all
        if p.stakeholder_response_rate < 45:
            pend += 0.22
        if p.documentation_completeness_pct < 60:
            pend += 0.08

        obj = min(obj, 0.55)
        pend = min(pend, 0.80 - obj) if obj < 0.75 else 0.05
        cons = max(1.0 - obj - pend, 0.05)

        tot = obj + pend + cons
        state = rng.choice(CONSENT_STATES, p=[cons / tot, obj / tot, pend / tot])
        states.append(state)

        if state == "Objected":
            # pick a reason that actually fits this parcel
            pool = []
            if p.compensation_disbursed_pct < 50:
                pool += [OBJECTION_REASONS[0], OBJECTION_REASONS[0]]
            if p.land_type == "Agricultural":
                pool += [OBJECTION_REASONS[1], OBJECTION_REASONS[5],
                         OBJECTION_REASONS[8]]
            if p.land_type in ("Residential", "Homestead"):
                pool += [OBJECTION_REASONS[3], OBJECTION_REASONS[3]]
            if p.rr_progress_pct < 60:
                pool += [OBJECTION_REASONS[2]]
            if str(p.ownership_category).startswith("Joint"):
                pool += [OBJECTION_REASONS[9], OBJECTION_REASONS[4]]
            if p.legal_disputes >= 2:
                pool += [OBJECTION_REASONS[6]]
            if not pool:
                pool = [OBJECTION_REASONS[7], OBJECTION_REASONS[0]]
            chosen = str(rng.choice(pool))
            reasons.append(chosen)
            idx = OBJECTION_REASONS.index(chosen)
            opts = REASON_TO_RELIEF.get(idx, [0])
            # A cultivating family more often wants land back, not money
            want_land = (p.land_type == "Agricultural"
                         and p.extent_acres >= 2 and rng.random() < 0.55)
            reliefs.append(RELIEF_OPTIONS[0] if want_land
                           else RELIEF_OPTIONS[int(rng.choice(opts))])
            stages.append("")
            dates.append((datetime.now() - timedelta(days=int(rng.integers(3, 90))))
                         .strftime("%Y-%m-%d"))
        elif state == "Pending":
            reasons.append(""); reliefs.append("")
            unreachable = (len(str(p.phone)) < 10
                           or p.stakeholder_response_rate < 50)
            stages.append(PENDING_STAGES[0] if unreachable
                          else str(rng.choice(PENDING_STAGES[1:])))
            dates.append("")
        else:
            reasons.append(""); reliefs.append(""); stages.append("")
            dates.append((datetime.now() - timedelta(days=int(rng.integers(3, 110))))
                         .strftime("%Y-%m-%d"))

    df["consent_status"] = states
    df["objection_reason"] = reasons
    df["relief_sought"] = reliefs
    df["referred_to"] = [RELIEF_ESCALATION.get(r, "") for r in reliefs]
    df["owner_note"] = ""
    df["pending_stage"] = stages
    df["response_date"] = dates
    return df


def load_consent_overrides():
    """Responses recorded by officers inside the portal."""
    if os.path.exists(CONSENT_FILE):
        try:
            with open(CONSENT_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_consent_override(survey_no, status, reason="", stage="",
                          officer="", relief="", note=""):
    data = load_consent_overrides()
    data[str(survey_no)] = {
        "consent_status": status, "objection_reason": reason,
        "relief_sought": relief, "owner_note": note,
        "referred_to": RELIEF_ESCALATION.get(relief, ""),
        "pending_stage": stage, "officer": officer,
        "response_date": datetime.now().strftime("%Y-%m-%d"),
        "recorded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(CONSENT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data


# ---------- owner response links ----------
# The notice carries a link. The owner opens it on the phone, taps
# CONSENT or OBJECT, and the register updates in the portal at once —
# so a reply is recorded against the survey number, not lost in an inbox.
# On demo day the phone is on the laptop's hotspot, so the LAN address
# below is reachable from the owner's handset.

RESPONSE_SECRET = "bhoomi-predict-response-v1"
LINK_FILE = "bhoomi_link.json"


def response_token(survey_no):
    """Short per-parcel token so a link cannot be guessed from the next one."""
    import hashlib as _h
    return _h.blake2s((RESPONSE_SECRET + "|" + str(survey_no)).encode(),
                      digest_size=3).hexdigest()


def lan_ip():
    """This machine's address on the local network (hotspot or Wi-Fi)."""
    import socket
    try:
        sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sk.connect(("8.8.8.8", 80))          # no packet is actually sent
        ip = sk.getsockname()[0]
        sk.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


def load_base_url():
    """Where the notice's reply link should point.

    Order: an explicit setting saved in the portal, then a deployment
    variable (BHOOMI_BASE_URL or a Streamlit secret — this is how the
    hosted build learns its own public address), then the LAN address,
    which is right for a laptop demo and wrong on a cloud host.
    """
    if os.path.exists(LINK_FILE):
        try:
            with open(LINK_FILE, encoding="utf-8") as f:
                u = json.load(f).get("base_url", "").strip()
            if u:
                return u.rstrip("/")
        except Exception:
            pass

    env = os.environ.get("BHOOMI_BASE_URL", "").strip()
    if env:
        return env.rstrip("/")
    try:
        import streamlit as _st
        sec = str(_st.secrets.get("BHOOMI_BASE_URL", "")).strip()
        if sec:
            return sec.rstrip("/")
    except Exception:
        pass

    return f"http://{lan_ip()}:8501"


def is_hosted():
    """True when running on a cloud host rather than the officer's laptop."""
    return bool(os.environ.get("BHOOMI_BASE_URL")
                or os.environ.get("HOSTNAME", "").startswith("streamlit")
                or os.path.exists("/mount/src"))


def save_base_url(url):
    with open(LINK_FILE, "w", encoding="utf-8") as f:
        json.dump({"base_url": url.strip().rstrip("/")}, f, indent=2)


def response_link(survey_no, base_url=None):
    base = (base_url or load_base_url()).rstrip("/")
    return f"{base}/?r={survey_no}-{response_token(survey_no)}"


def parse_response_ref(ref):
    """Return the survey number a link refers to, or None if the token is wrong."""
    if not ref or "-" not in str(ref):
        return None
    sno, tok = str(ref).rsplit("-", 1)
    return sno if response_token(sno) == tok else None


def apply_consent_overrides(df):
    """Officer-recorded responses take precedence over the seeded position."""
    ov = load_consent_overrides()
    if not ov:
        return df
    df = df.copy()
    for i, sn in df["survey_no"].items():
        rec = ov.get(str(sn))
        if rec:
            for k in ("consent_status", "objection_reason", "relief_sought",
                      "owner_note", "referred_to", "pending_stage",
                      "response_date"):
                df.at[i, k] = rec.get(k, df.at[i, k])
    return df


def consent_summary(df):
    """Counts and extents per consent state."""
    out = {}
    area_col = "affected_acres" if "affected_acres" in df.columns else "extent_acres"
    for s in CONSENT_STATES:
        sub = df[df.consent_status == s]
        out[s] = {"count": len(sub), "acres": round(float(sub[area_col].sum()), 2),
                  "families": int(sub.affected_families.sum()) if len(sub) else 0}
    out["total"] = {"count": len(df),
                    "acres": round(float(df[area_col].sum()), 2),
                    "families": int(df.affected_families.sum()) if len(df) else 0}
    out["consent_pct"] = round(out["Consented"]["count"] / max(len(df), 1) * 100, 1)
    return out


# ============================================================
# SECTION 2 — XGBOOST + EXACT TreeSHAP DELAY MODEL
# ============================================================

FEATURES = [
    "project_type_code", "land_area_acres", "affected_families",
    "approval_days_pending", "legal_disputes_count",
    "compensation_disbursed_pct", "possession_status_pct", "rr_progress_pct",
    "stakeholder_response_rate", "documentation_completeness_pct",
    "ownership_dispute_flags", "days_since_notification",
    "district_historical_delay_avg",
]

LABELS = {
    "project_type_code": "Project Type",
    "land_area_acres": "Land Area (acres)",
    "affected_families": "Affected Families",
    "approval_days_pending": "Pending Approvals (days)",
    "legal_disputes_count": "Legal Disputes",
    "compensation_disbursed_pct": "Compensation Disbursed %",
    "possession_status_pct": "Possession Status %",
    "rr_progress_pct": "R&R Progress %",
    "stakeholder_response_rate": "Stakeholder Responsiveness",
    "documentation_completeness_pct": "Documentation Completeness %",
    "ownership_dispute_flags": "Ownership Dispute Flags",
    "days_since_notification": "Days Since Notification",
    "district_historical_delay_avg": "District Historical Delay",
}

PROJECT_TYPES = ["Highway", "Railway", "Irrigation", "Industrial Corridor",
                 "Urban Development", "Renewable Energy"]

ACTIONS = {
    "approval_days_pending": "Escalate pending file to District Collector; invoke statutory timeline under RFCTLARR Sec 25.",
    "legal_disputes_count": "Refer disputed parcels to Sec 64 LARR Authority; schedule mediation within 15 days.",
    "compensation_disbursed_pct": "Release pending compensation tranche; verify beneficiary bank mandates with Treasury.",
    "rr_progress_pct": "Convene R&R committee; expedite entitlement matrix and resettlement site readiness.",
    "possession_status_pct": "Issue Sec 38 possession notice; depute Revenue Inspector for physical handover.",
    "documentation_completeness_pct": "Deploy field officer for verification; digitise pending patta/chitta records.",
    "stakeholder_response_rate": "Trigger regional-language SMS/WhatsApp reminder cycle; schedule gram sabha.",
    "ownership_dispute_flags": "Initiate co-owner reconciliation; obtain legal heir certificates via Tahsildar.",
    "affected_families": "Scale up R&R staffing proportionate to displacement load.",
    "days_since_notification": "Review Sec 11 notification validity; prevent lapse under Sec 19(7).",
    "land_area_acres": "Split acquisition into phased parcels to parallelise survey and award.",
    "district_historical_delay_avg": "Assign district to priority monitoring cell; weekly State review.",
    "project_type_code": "Apply project-type SOP; benchmark against similar completed projects.",
}


def generate_training_data(n=1200, seed=42):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        "project_type_code": rng.integers(0, len(PROJECT_TYPES), n),
        "land_area_acres": rng.gamma(3, 60, n).clip(5, 2000),
        "affected_families": rng.gamma(2.2, 55, n).clip(1, 1500).astype(int),
        "approval_days_pending": rng.gamma(2, 45, n).clip(0, 720),
        "legal_disputes_count": rng.poisson(1.4, n).clip(0, 12),
        "compensation_disbursed_pct": rng.beta(2.2, 1.8, n) * 100,
        "possession_status_pct": rng.beta(1.9, 2.1, n) * 100,
        "rr_progress_pct": rng.beta(2.0, 2.2, n) * 100,
        "stakeholder_response_rate": rng.beta(3, 1.7, n) * 100,
        "documentation_completeness_pct": rng.beta(4, 1.5, n) * 100,
        "ownership_dispute_flags": rng.poisson(0.9, n).clip(0, 8),
        "days_since_notification": rng.gamma(2.5, 70, n).clip(0, 1095),
        "district_historical_delay_avg": rng.normal(95, 38, n).clip(10, 300),
    })
    delay = (
        10
        + df.legal_disputes_count ** 1.35 * 5.2
        + df.approval_days_pending * 0.105
        + (100 - df.compensation_disbursed_pct) * 0.31
        + (100 - df.rr_progress_pct) * 0.17
        + (100 - df.possession_status_pct) * 0.12
        + (100 - df.documentation_completeness_pct) * 0.16
        + (100 - df.stakeholder_response_rate) * 0.19
        + df.ownership_dispute_flags ** 1.2 * 3.4
        + np.log1p(df.affected_families) * 2.1
        + np.log1p(df.land_area_acres) * 1.1
        + df.days_since_notification * 0.020
        + df.district_historical_delay_avg * 0.13
        + (df.legal_disputes_count * (100 - df.compensation_disbursed_pct)) * 0.032
        + ((100 - df.stakeholder_response_rate) * np.log1p(df.affected_families)) * 0.018
        + rng.normal(0, 7, n)
    )
    df["delay_days"] = delay.clip(0, 400)
    return df


class BhoomiDelayModel:
    """XGBoost regressor with exact TreeSHAP explanations (native pred_contribs)."""

    def __init__(self):
        self.model = None
        self.metrics = {}
        self._dist = None

    def train(self, df=None, verbose=False):
        df = generate_training_data() if df is None else df
        X, y = df[FEATURES], df["delay_days"]
        k = int(len(df) * 0.8)
        Xtr, Xte, ytr, yte = X.iloc[:k], X.iloc[k:], y.iloc[:k], y.iloc[k:]

        self.model = xgb.XGBRegressor(
            n_estimators=350, max_depth=6, learning_rate=0.06,
            subsample=0.85, colsample_bytree=0.85, min_child_weight=3,
            reg_lambda=1.2, random_state=42, n_jobs=2)
        self.model.fit(Xtr, ytr)

        pred = self.model.predict(Xte)
        mae = float(np.mean(np.abs(pred - yte)))
        rmse = float(np.sqrt(np.mean((pred - yte) ** 2)))
        r2 = 1 - float(np.sum((yte - pred) ** 2)) / float(np.sum((yte - np.mean(yte)) ** 2))
        self.metrics = {"MAE": mae, "RMSE": rmse, "R2": r2,
                        "train_n": len(Xtr), "test_n": len(Xte)}
        self._dist = np.sort(self.model.predict(X))
        if verbose:
            print(f"  MAE {mae:.2f} d | RMSE {rmse:.2f} d | R2 {r2:.4f}")
        return self

    def _contribs(self, X):
        dm = xgb.DMatrix(X[FEATURES], feature_names=FEATURES)
        return self.model.get_booster().predict(dm, pred_contribs=True)

    def explain(self, rec):
        X = pd.DataFrame([{f: rec.get(f, 0) for f in FEATURES}])
        pred = float(self.model.predict(X)[0])
        c = self._contribs(X)[0]
        shap_vals, base = c[:-1], float(c[-1])

        drivers = sorted(
            [{"feature": f, "label": LABELS[f], "value": rec.get(f, 0),
              "shap": float(v), "direction": "increases" if v > 0 else "reduces",
              "action": ACTIONS.get(f, "")}
             for f, v in zip(FEATURES, shap_vals)],
            key=lambda d: abs(d["shap"]), reverse=True)

        risk = float(np.searchsorted(self._dist, pred) / len(self._dist) * 100)
        level, colour = (("CRITICAL", "#c62828") if risk > 75 else
                         ("HIGH", "#ef6c00") if risk > 55 else
                         ("MEDIUM", "#f9a825") if risk > 30 else
                         ("LOW", "#2e7d32"))
        return {
            "predicted_delay_days": round(pred, 1), "base_value": round(base, 1),
            "risk_score": round(risk, 1), "risk_level": level, "risk_colour": colour,
            "drivers": drivers, "top_drivers": [d for d in drivers if d["shap"] > 0][:5],
            "shap_sum_check": round(base + float(shap_vals.sum()), 2),
        }

    def global_importance(self, n=400):
        c = self._contribs(generate_training_data(n, seed=7))
        return (pd.DataFrame({"feature": FEATURES,
                              "label": [LABELS[f] for f in FEATURES],
                              "mean_abs_shap": np.abs(c[:, :-1]).mean(axis=0)})
                .sort_values("mean_abs_shap", ascending=False).reset_index(drop=True))


def parcel_to_features(parcel, project_type="Highway", district_avg=95.0):
    """Map a cadastral parcel row onto the model's feature vector."""
    return {
        "project_type_code": PROJECT_TYPES.index(project_type),
        "land_area_acres": float(parcel.get("affected_acres",
                                            parcel.get("extent_acres", 1.0))),
        "affected_families": int(parcel.get("affected_families", 1)),
        "approval_days_pending": float(parcel.get("approval_days_pending", 100)),
        "legal_disputes_count": float(parcel.get("legal_disputes", 0)),
        "compensation_disbursed_pct": float(parcel.get("compensation_disbursed_pct", 50)),
        "possession_status_pct": float(parcel.get("possession_status_pct", 50)),
        "rr_progress_pct": float(parcel.get("rr_progress_pct", 60)),
        "stakeholder_response_rate": float(parcel.get("stakeholder_response_rate", 70)),
        "documentation_completeness_pct": float(parcel.get("documentation_completeness_pct", 80)),
        "ownership_dispute_flags": float(parcel.get("ownership_dispute_flags", 0)),
        "days_since_notification": float(parcel.get("days_since_notification", 200)),
        "district_historical_delay_avg": district_avg,
    }


# ============================================================
# SECTION 3 — OWNER NOTIFICATION ENGINE (multi-channel, auto-fallback)
# ============================================================
# Four real delivery channels. In "auto" mode the engine tries them
# in order and stops at the first one that succeeds — so a single
# provider outage never breaks a notice.
#
#   1. Phone SMS      your own Android SIM via SMS Gateway app · free · real SMS
#   2. WhatsApp       Twilio sandbox · free trial · instant
#   3. SMS (Fast2SMS) Quick route · ₹5/SMS · operator-approved
#   4. Email          Gmail SMTP · free · always available
#
# Settings are saved to bhoomi_channels.json on this computer so
# nothing has to be typed on demo day.
# ============================================================

LOG_FILE = "bhoomi_notice_log.json"
CHANNEL_FILE = "bhoomi_channels.json"

CHANNELS = ["Phone SMS", "WhatsApp", "SMS", "Email"]

CHANNEL_DEFAULTS = {
    "order": ["Phone SMS", "WhatsApp", "SMS", "Email"],
    "Phone SMS": {"enabled": False, "mode": "Local (same Wi-Fi / hotspot)",
                  "host": "", "user": "", "password": "", "to": ""},
    "WhatsApp": {"enabled": False, "sid": "", "token": "",
                 "from_no": "whatsapp:+14155238886", "to": ""},
    "SMS": {"enabled": False, "key": "", "to": ""},
    "Email": {"enabled": False, "gmail": "", "app_pw": "", "to": ""},
}


ACRE_IN_CENT = 100          # 1 acre = 100 cent (Tamil Nadu revenue unit)


def _inr(amount):
    """Format in the Indian grouping — 2,16,000 not 216,000."""
    n = int(round(amount))
    s_ = str(abs(n))
    if len(s_) > 3:
        head, tail = s_[:-3], s_[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s_ = ",".join(parts) + "," + tail
    return ("-" if n < 0 else "") + s_


def notice_particulars(row, project, purpose, deadline, contact):
    """Everything the statutory notice must quote, computed from one parcel."""
    total_ac = float(row.get("extent_acres", 0) or 0)
    req_ac = float(row.get("affected_acres", total_ac) or 0)
    req_cent = req_ac * ACRE_IN_CENT
    gv = float(row.get("guideline_value_per_cent", 0) or 0)
    return {
        "project": project, "purpose": purpose,
        "deadline": deadline, "contact": contact,
        "owner": row.get("owner", ""),
        "address": row.get("owner_address", ""),
        "survey_no": row.get("survey_no", ""),
        "patta_no": row.get("patta_no", ""),
        "chitta_no": row.get("chitta_no", ""),
        "total_acres": round(total_ac, 3),
        "total_cent": round(total_ac * ACRE_IN_CENT, 1),
        "req_acres": round(req_ac, 3),
        "req_cent": round(req_cent, 1),
        "guideline": gv,
        "compensation": req_cent * gv,
        "link": response_link(row.get("survey_no", "")),
    }


def notice_text(d, lang="english", short=False):
    """Statutory land-acquisition notice.

    The heading omits "Govt" — acquisition is of private holdings as much
    as government land — and the full form quotes the particulars an owner
    needs before giving or refusing consent: patta/chitta, total extent,
    the extent required, the guideline value and the compensation payable.
    """
    if lang == "tamil":
        if short:
            return (f"நில கையகப்படுத்தல் அறிவிப்பு – தேசிய நெடுஞ்சாலைத் திட்டம்\n"
                    f"சர்வே எண் {d['survey_no']} · பட்டா {d['patta_no']}\n"
                    f"தேவைப்படும் பரப்பு: {d['req_cent']:g} சென்ட் "
                    f"(மொத்தம் {d['total_cent']:g} சென்ட்)\n"
                    f"இழப்பீடு: ரூ.{_inr(d['compensation'])}\n"
                    f"{d['deadline']} க்குள் பதிவு செய்க: {d.get('link', '')}\n"
                    f"தொடர்பு: {d['contact']}")
        return (
            f"நில கையகப்படுத்தல் அறிவிப்பு\n"
            f"தேசிய நெடுஞ்சாலைத் திட்டம்\n"
            f"திட்டம்: {d['project']}\n\n"
            f"நில உரிமையாளர்: {d['owner']}\n"
            f"முகவரி: {d['address']}\n"
            f"சர்வே எண்: {d['survey_no']}\n"
            f"பட்டா எண்: {d['patta_no']} · சிட்டா எண்: {d['chitta_no']}\n"
            f"தங்கள் நிலத்தின் மொத்த பரப்பு: {d['total_acres']:g} ஏக்கர் "
            f"({d['total_cent']:g} சென்ட்)\n"
            f"நெடுஞ்சாலைத் துறைக்குத் தேவைப்படும் பரப்பு: "
            f"{d['req_cent']:g} சென்ட் ({d['req_acres']:g} ஏக்கர்)\n\n"
            f"தற்போதைய வழிகாட்டி மதிப்பு: ரூ.{_inr(d['guideline'])} / சென்ட்\n"
            f"அரசு வழிகாட்டி மதிப்புப்படி வழங்கப்படும் இழப்பீடு: "
            f"ரூ.{_inr(d['compensation'])}\n\n"
            f"மேற்கண்ட நிலம் {d['purpose']} க்காக கையகப்படுத்தப்பட உள்ளது. "
            f"{d['deadline']} க்குள் தங்கள் சம்மதம் அல்லது ஆட்சேபணையைத் "
            f"தெரிவிக்கவும்.\n"
            f"பதிவு செய்ய: {d.get('link', '')}\n"
            f"அல்லது பதில்: சம்மதம் – YES / ஆட்சேபணை – NO\n"
            f"தொடர்பு: {d['contact']}\n"
            f"– வருவாய்த்துறை, {TALUK_NAME} வட்டம்")

    if short:
        return (f"LAND ACQUISITION NOTICE – NATIONAL HIGHWAYS PROJECT\n"
                f"Survey No {d['survey_no']} · Patta {d['patta_no']}\n"
                f"Extent required: {d['req_cent']:g} cent "
                f"(of {d['total_cent']:g} cent)\n"
                f"Compensation: Rs.{_inr(d['compensation'])}\n"
                f"Reply before {d['deadline']}: {d.get('link', '')}\n"
                f"Contact: {d['contact']}")

    return (
        f"LAND ACQUISITION NOTICE\n"
        f"NATIONAL HIGHWAYS PROJECT\n"
        f"Project: {d['project']}\n\n"
        f"Name of the land owner: {d['owner']}\n"
        f"Address: {d['address']}\n"
        f"Survey No: {d['survey_no']}\n"
        f"Patta No: {d['patta_no']} · Chitta No: {d['chitta_no']}\n"
        f"Total extent of your land: {d['total_acres']:g} acre "
        f"({d['total_cent']:g} cent)\n"
        f"Area required for acquisition by Highways Department: "
        f"{d['req_cent']:g} cent ({d['req_acres']:g} acre)\n\n"
        f"Current guideline value for your land: "
        f"Rs.{_inr(d['guideline'])} per cent\n"
        f"As per the Government guideline value, Rs.{_inr(d['compensation'])} "
        f"will be issued as compensation.\n\n"
        f"The above land is proposed for acquisition for {d['purpose']}. "
        f"Please confirm your consent or objection before {d['deadline']}.\n"
        f"Record your reply here: {d.get('link', '')}\n"
        f"or reply YES to consent / NO to object.\n"
        f"Contact: {d['contact']}\n"
        f"– Revenue Department, {TALUK_NAME} Taluk")


def _digits10(number):
    d = "".join(ch for ch in str(number) if ch.isdigit())
    return d[-10:] if len(d) >= 10 else ""


def _err(e):
    """Human-readable network error."""
    s = str(e)
    low = s.lower()
    if "timed out" in low or "timeout" in low:
        return "Network timeout — check internet, or switch to a mobile hotspot."
    if "expecting value" in low or "jsondecode" in type(e).__name__.lower():
        return ("Got a web page instead of an API reply — this network is probably "
                "blocking the site. Switch to a mobile hotspot and retry.")
    if ("connection" in low or "resolve" in low or "getaddrinfo" in low
            or "proxy" in low or "ssl" in low):
        return ("Cannot reach the service — no internet, or blocked on this network. "
                "Try a mobile hotspot.")
    return f"Error: {s[:200]}"


# ---------------- Channel 1 · Phone SMS (SMS Gateway for Android) ----------------
# The officer's own Android phone sends a genuine SMS from its SIM.
# App: "SMS Gateway for Android" (capcom6, open source, Apache-2.0).
#   Local mode : POST http://<phone-ip>:8080/message        (same network)
#   Cloud mode : POST https://api.sms-gate.app/3rdparty/v1/messages
# Both use HTTP basic auth with the username/password shown in the app.

PHONE_CLOUD = "https://api.sms-gate.app/3rdparty/v1"


def _phone_base(mode, host):
    if mode.startswith("Cloud"):
        return PHONE_CLOUD
    h = host.strip().replace("http://", "").replace("https://", "").rstrip("/")
    if h and ":" not in h:
        h += ":8080"
    return f"http://{h}"


def _phone_send_url(mode, host):
    base = _phone_base(mode, host)
    return f"{base}/messages" if mode.startswith("Cloud") else f"{base}/message"


def phone_test(mode, host, user, password):
    if not mode.startswith("Cloud") and not host.strip():
        return False, "Enter the phone's local IP shown in the app (e.g. 192.168.43.1)."
    base = _phone_base(mode, host)
    try:
        r = requests.get(f"{base}/health", auth=(user.strip(), password.strip()),
                         timeout=10)
        if r.status_code == 401:
            return False, "Phone reached, but username/password are wrong."
        if r.status_code < 500:
            return True, (f"Phone gateway reachable at {base} "
                          f"(HTTP {r.status_code}). Send a test message to confirm.")
        return False, f"Gateway error HTTP {r.status_code}."
    except Exception as e:
        if not mode.startswith("Cloud"):
            return False, ("Cannot reach the phone. Put the laptop on the phone's "
                           "hotspot (or the same Wi-Fi), make sure the app shows "
                           "'Local server' ON, and check the IP.")
        return False, _err(e)


def send_phone_sms(mode, host, user, password, number, message):
    num = _digits10(number)
    if not num:
        return False, f"Invalid mobile number: {number}"
    url = _phone_send_url(mode, host)
    auth = (user.strip(), password.strip())
    try:
        body = {"textMessage": {"text": message}, "phoneNumbers": [f"+91{num}"]}
        r = requests.post(url, json=body, auth=auth, timeout=20)
        if r.status_code == 400:
            # older app builds used a flat "message" field
            r = requests.post(url, json={"message": message,
                                         "phoneNumbers": [f"+91{num}"]},
                              auth=auth, timeout=20)
        if r.status_code in (200, 201, 202):
            try:
                d = r.json()
                return True, f"Sent from your SIM · id {d.get('id', '?')} ({d.get('state', 'queued')})"
            except Exception:
                return True, "Sent from your SIM."
        if r.status_code == 401:
            return False, "Phone rejected the username/password."
        try:
            return False, r.json().get("message", f"HTTP {r.status_code}")
        except Exception:
            return False, f"HTTP {r.status_code}"
    except Exception as e:
        if not mode.startswith("Cloud"):
            return False, ("Cannot reach the phone — laptop must be on the phone's "
                           "hotspot or the same Wi-Fi, with the app's Local server ON.")
        return False, _err(e)


# ---------------- Channel 2 · WhatsApp (Twilio) ----------------

def wa_test(sid, token):
    try:
        r = requests.get(f"https://api.twilio.com/2010-04-01/Accounts/{sid.strip()}.json",
                         auth=(sid.strip(), token.strip()), timeout=15)
        if r.status_code == 200:
            d = r.json()
            return True, f"Twilio OK · {d.get('friendly_name', 'account')} ({d.get('status')})"
        return False, r.json().get("message", f"HTTP {r.status_code} — check SID / token.")
    except Exception as e:
        return False, _err(e)


def send_whatsapp(sid, token, number, message, from_no="whatsapp:+14155238886"):
    num = _digits10(number)
    if not num:
        return False, f"Invalid mobile number: {number}"
    try:
        r = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid.strip()}/Messages.json",
            data={"From": from_no.strip(), "To": f"whatsapp:+91{num}", "Body": message},
            auth=(sid.strip(), token.strip()), timeout=20)
        d = r.json()
        if r.status_code in (200, 201):
            return True, f"Queued · WhatsApp SID {d.get('sid')}"
        msg = d.get("message", str(d))
        code = d.get("code")
        if code == 63015 or "63015" in msg:
            msg += " — this number has not joined your sandbox (send 'join <code>')."
        elif code == 63016 or "63016" in msg:
            msg += (" — 24-hour window closed. Send 'hi' to the sandbox number "
                    "from this phone, then retry.")
        return False, msg
    except Exception as e:
        return False, _err(e)


# ---------------- Channel 3 · SMS (Fast2SMS) ----------------

def sms_test(api_key):
    try:
        r = requests.get("https://www.fast2sms.com/dev/wallet",
                         params={"authorization": api_key.strip()}, timeout=15)
        d = r.json()
        if d.get("return") is True:
            bal = d.get("wallet", "?")
            try:
                n = int(float(bal) // 5)
                return True, f"Key OK · wallet ₹{bal} (≈ {n} Quick SMS at ₹5 each)"
            except Exception:
                return True, f"Key OK · wallet ₹{bal}"
        return False, str(d.get("message", d))
    except Exception as e:
        return False, _err(e)


def send_fast2sms(api_key, number, message, unicode_msg=False):
    num = _digits10(number)
    if not num:
        return False, f"Invalid mobile number: {number}"
    try:
        r = requests.get("https://www.fast2sms.com/dev/bulkV2", timeout=25, params={
            "authorization": api_key.strip(), "route": "q", "message": message,
            "language": "unicode" if unicode_msg else "english",
            "flash": "0", "numbers": num})
        d = r.json()
        if d.get("return") is True:
            return True, (f"Accepted · request {d.get('request_id')} "
                          f"(Quick SMS may await operator approval)")
        return False, str(d.get("message", d))
    except Exception as e:
        return False, _err(e)


# ---------------- Channel 4 · Email ----------------

def email_test(gmail, app_pw):
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as s:
            s.login(gmail.strip(), app_pw.replace(" ", "").strip())
        return True, f"Gmail OK · signed in as {gmail.strip()}"
    except smtplib.SMTPAuthenticationError:
        return False, "Gmail rejected the login — use a 16-character App Password."
    except Exception as e:
        return False, _err(e)


def send_email(gmail, app_pw, to_email, subject, message):
    if "@" not in str(to_email):
        return False, f"Invalid email: {to_email}"
    try:
        m = MIMEText(message, "plain", "utf-8")
        m["Subject"], m["From"], m["To"] = subject, gmail.strip(), to_email.strip()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as s:
            s.login(gmail.strip(), app_pw.replace(" ", "").strip())
            s.send_message(m)
        return True, f"Delivered · email to {to_email.strip()}"
    except smtplib.SMTPAuthenticationError:
        return False, "Gmail rejected the login — use a 16-character App Password."
    except Exception as e:
        return False, _err(e)


# ---------------- settings persistence ----------------

def load_channels():
    cfg = json.loads(json.dumps(CHANNEL_DEFAULTS))          # deep copy
    if os.path.exists(CHANNEL_FILE):
        try:
            with open(CHANNEL_FILE, encoding="utf-8") as f:
                saved = json.load(f)
            for k, v in saved.items():
                if isinstance(v, dict) and k in cfg:
                    cfg[k].update(v)
                else:
                    cfg[k] = v
        except Exception:
            pass
    cfg["order"] = [c for c in cfg.get("order", []) if c in CHANNELS] + \
                   [c for c in CHANNELS if c not in cfg.get("order", [])]
    return cfg


def save_channels(cfg):
    with open(CHANNEL_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def channel_ready(cfg, ch):
    c = cfg.get(ch, {})
    if not c.get("enabled"):
        return False
    need = {"Phone SMS": ["user", "password"], "WhatsApp": ["sid", "token"],
            "SMS": ["key"], "Email": ["gmail", "app_pw"]}[ch]
    if ch == "Phone SMS" and not str(c.get("mode", "")).startswith("Cloud"):
        need = need + ["host"]
    return all(str(c.get(k, "")).strip() for k in need)


def dispatch(cfg, message, owner_phone="", subject="Land Acquisition Notice",
             tamil=False, mode="auto", only=None):
    """Deliver one notice.

    mode="auto"  → try channels in cfg['order']; stop at first success.
    mode="all"   → send on every ready channel.
    only=<name>  → use just that channel.

    Returns (ok, attempts) where attempts is a list of
    (channel, ok, detail, target).
    """
    order = [only] if only else [c for c in cfg.get("order", CHANNELS) if c in CHANNELS]
    attempts = []
    for ch in order:
        if not channel_ready(cfg, ch):
            if only:
                attempts.append((ch, False, "Channel not configured or disabled.", ""))
            continue
        c = cfg[ch]
        # A phone channel with no number anywhere is a setup gap, not a bad number.
        if ch in ("Phone SMS", "WhatsApp", "SMS") and not (str(c.get("to", "")).strip()
                                              or str(owner_phone).strip()):
            attempts.append((ch, False, "No recipient number — fill “Deliver to” "
                                        "in Channel Setup.", ""))
            continue
        if ch == "Phone SMS":
            target = c.get("to") or owner_phone
            ok, info = send_phone_sms(c.get("mode", "Local"), c.get("host", ""),
                                      c["user"], c["password"], target, message)
        elif ch == "WhatsApp":
            target = c.get("to") or owner_phone
            ok, info = send_whatsapp(c["sid"], c["token"], target, message,
                                     c.get("from_no") or "whatsapp:+14155238886")
        elif ch == "SMS":
            target = c.get("to") or owner_phone
            ok, info = send_fast2sms(c["key"], target, message, unicode_msg=tamil)
        else:
            target = c.get("to") or c["gmail"]
            ok, info = send_email(c["gmail"], c["app_pw"], target, subject, message)

        attempts.append((ch, ok, info, target))
        if ok and mode == "auto":
            return True, attempts

    return any(a[1] for a in attempts), attempts


def log_notice(rec):
    logs = []
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, encoding="utf-8") as f:
                logs = json.load(f)
        except Exception:
            logs = []
    logs.insert(0, rec)
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs[:500], f, ensure_ascii=False, indent=2)


def read_notices():
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


# ============================================================
# ============================================================
# SECTION 4 — AUTHORITY HIERARCHY & SECURE USER MANAGEMENT
# ============================================================
# PS 26016 Scope of Study · Security & Governance:
#   "Implement role-based access control, audit trails, secure
#    authentication, encryption, and compliance with Government
#    of India cybersecurity standards."
#
# Stakeholder hierarchy taken verbatim from the problem statement:
#   Central Ministries > State Governments > District Administrations
#   > Land Acquiring Authorities > Land Requiring Bodies
#   + Rehabilitation Authorities, Project Implementing Agencies,
#     Policy Makers
#
# Users persist in bhoomi_users.json. Passwords are never stored in
# plain text — PBKDF2-HMAC-SHA256, 240,000 iterations, per-user salt.
# ============================================================

import hashlib
import secrets

USER_DB = "bhoomi_users.json"
AUDIT_DB = "bhoomi_audit.json"

PBKDF2_ROUNDS = 240_000

# ---- Permission atoms ----
P_DASH = "dashboard"
P_ALIGN = "alignment"
P_RISK = "risk"
P_NOTIFY = "notify"
P_ANALYTICS = "analytics"
P_USERS = "users"          # create / manage other accounts
P_APPROVE = "approve"      # sanction proposals

# ---- Authority hierarchy (level 1 = apex) ----
AUTHORITY_ROLES = {
    "Central Ministry Officer": {
        "level": 1, "jurisdiction": "National",
        "perms": [P_DASH, P_ALIGN, P_RISK, P_NOTIFY, P_ANALYTICS, P_USERS, P_APPROVE],
        "desc": "Ministry of Road Transport / Rural Development — national oversight",
    },
    "State Nodal Officer": {
        "level": 2, "jurisdiction": "State",
        "perms": [P_DASH, P_ALIGN, P_RISK, P_NOTIFY, P_ANALYTICS, P_USERS, P_APPROVE],
        "desc": "State Government nodal authority for land acquisition",
    },
    "District Collector": {
        "level": 3, "jurisdiction": "District",
        "perms": [P_DASH, P_ALIGN, P_RISK, P_NOTIFY, P_ANALYTICS, P_USERS, P_APPROVE],
        "desc": "District administration — competent authority under RFCTLARR",
    },
    "Land Acquisition Officer": {
        "level": 4, "jurisdiction": "Taluk",
        "perms": [P_DASH, P_ALIGN, P_RISK, P_NOTIFY, P_ANALYTICS],
        "desc": "Land Acquiring Authority — award and possession",
    },
    "Rehabilitation Officer": {
        "level": 4, "jurisdiction": "Taluk",
        "perms": [P_DASH, P_RISK, P_NOTIFY, P_ANALYTICS],
        "desc": "Rehabilitation & Resettlement Authority",
    },
    "Project Implementing Agency": {
        "level": 5, "jurisdiction": "Project",
        "perms": [P_DASH, P_ALIGN, P_ANALYTICS],
        "desc": "NHAI / Railways / Irrigation — land requiring body",
    },
    "Field Verification Officer": {
        "level": 6, "jurisdiction": "Village",
        "perms": [P_DASH, P_ALIGN, P_NOTIFY],
        "desc": "VAO / Revenue Inspector — ground verification",
    },
    "Policy Analyst": {
        "level": 7, "jurisdiction": "Read-only",
        "perms": [P_DASH, P_RISK, P_ANALYTICS],
        "desc": "NIC / policy cell — analytics access only",
    },
}

ROLE_ORDER = sorted(AUTHORITY_ROLES, key=lambda r: AUTHORITY_ROLES[r]["level"])


# ---------------- password hashing ----------------

def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ROUNDS)
    return salt, dk.hex()


def verify_password(password, salt, stored_hash):
    _, h = hash_password(password, salt)
    return secrets.compare_digest(h, stored_hash)


def password_problems(pw):
    """Government password policy checks. Returns list of failures."""
    out = []
    if len(pw) < 8:
        out.append("at least 8 characters")
    if not any(c.isupper() for c in pw):
        out.append("one uppercase letter")
    if not any(c.islower() for c in pw):
        out.append("one lowercase letter")
    if not any(c.isdigit() for c in pw):
        out.append("one digit")
    if not any(not c.isalnum() for c in pw):
        out.append("one special character")
    return out


# ---------------- persistent store ----------------

SEED_USERS = [
    ("ministry@morth.gov.in", "Ministry@2026", "Smt. Kavitha Menon, I.A.S.",
     "Central Ministry Officer", "MoRTH, New Delhi", "9800000001"),
    ("nodal@tn.gov.in", "Nodal@2026", "Thiru. A. Rajendran, I.A.S.",
     "State Nodal Officer", "Revenue Dept, Government of Tamil Nadu", "9800000002"),
    ("collector.ttn@tn.gov.in", "Collector@2026", "Dr. R. Anitha, I.A.S.",
     "District Collector", "Thoothukudi District", "9800000003"),
    ("lao.kovilpatti@tn.gov.in", "Officer@2026", "Thiru. S. Vetrivel",
     "Land Acquisition Officer", "Kovilpatti Taluk", "9800000004"),
    ("rr.kovilpatti@tn.gov.in", "Rehab@2026", "Tmt. G. Lakshmi",
     "Rehabilitation Officer", "Kovilpatti Taluk", "9800000005"),
    ("pd.nhai@nhai.gov.in", "Agency@2026", "Er. V. Prakash",
     "Project Implementing Agency", "NHAI PIU Madurai", "9800000006"),
    ("vao.village@tn.gov.in", "Field@2026", "Thiru. M. Karthik",
     "Field Verification Officer", "Illuppaiyur Village", "9800000007"),
    ("analyst@nic.in", "Analyst@2026", "Ms. P. Divya",
     "Policy Analyst", "NIC State Unit", "9800000008"),
]


def _new_user_record(email, password, name, role, office, phone,
                     created_by="SYSTEM", must_reset=False):
    salt, h = hash_password(password)
    meta = AUTHORITY_ROLES[role]
    return {
        "email": email.strip().lower(),
        "employee_id": "",          # filled by caller
        "name": name,
        "role": role,
        "level": meta["level"],
        "jurisdiction": meta["jurisdiction"],
        "office": office,
        "phone": phone,
        "perms": list(meta["perms"]),
        "salt": salt,
        "hash": h,
        "active": True,
        "must_reset": must_reset,
        "created_by": created_by,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "last_login": "",
        "login_count": 0,
    }


def _next_employee_id(users):
    n = len(users) + 1
    existing = {u.get("employee_id", "") for u in users.values()}
    while f"BP{n:04d}" in existing:
        n += 1
    return f"BP{n:04d}"


def load_users():
    """Load the user store, seeding it on first run."""
    if os.path.exists(USER_DB):
        try:
            with open(USER_DB, encoding="utf-8") as f:
                users = json.load(f)
            if users:
                return users
        except Exception:
            pass

    users = {}
    for email, pw, name, role, office, phone in SEED_USERS:
        rec = _new_user_record(email, pw, name, role, office, phone)
        rec["employee_id"] = _next_employee_id(users)
        users[rec["email"]] = rec
    save_users(users)
    return users


def save_users(users):
    with open(USER_DB, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)


def audit(action, actor, detail=""):
    logs = []
    if os.path.exists(AUDIT_DB):
        try:
            with open(AUDIT_DB, encoding="utf-8") as f:
                logs = json.load(f)
        except Exception:
            logs = []
    logs.insert(0, {"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "action": action, "actor": actor, "detail": detail})
    with open(AUDIT_DB, "w", encoding="utf-8") as f:
        json.dump(logs[:500], f, ensure_ascii=False, indent=2)


def read_audit():
    if os.path.exists(AUDIT_DB):
        try:
            with open(AUDIT_DB, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


# ---------------- operations ----------------

def authenticate(identifier, password):
    """Sign in by official email OR employee ID."""
    users = load_users()
    ident = identifier.strip().lower()

    rec = users.get(ident)
    if rec is None:                      # try employee ID
        for u in users.values():
            if u.get("employee_id", "").lower() == ident:
                rec = u
                break

    if rec is None:
        return None, "No account found for that email or employee ID."
    if not rec.get("active", True):
        return None, "This account has been deactivated by the administrator."
    if not verify_password(password, rec["salt"], rec["hash"]):
        audit("LOGIN_FAILED", rec["email"], "wrong password")
        return None, "Incorrect password."

    rec["last_login"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rec["login_count"] = rec.get("login_count", 0) + 1
    users[rec["email"]] = rec
    save_users(users)
    audit("LOGIN", rec["email"], f"{rec['role']} · {rec['office']}")
    return rec, "ok"


def create_user(actor, email, password, name, role, office, phone,
                must_reset=True):
    users = load_users()
    email = email.strip().lower()

    if not email or "@" not in email:
        return False, "Enter a valid official email address.", None
    if email in users:
        return False, "An account with that email already exists.", None
    if role not in AUTHORITY_ROLES:
        return False, "Unknown authority role.", None
    probs = password_problems(password)
    if probs:
        return False, "Password must contain " + ", ".join(probs) + ".", None

    # An officer may only create accounts at or below their own level.
    actor_level = AUTHORITY_ROLES[actor["role"]]["level"]
    if AUTHORITY_ROLES[role]["level"] < actor_level:
        return False, (f"A {actor['role']} cannot create a higher authority "
                       f"({role}, level {AUTHORITY_ROLES[role]['level']})."), None

    rec = _new_user_record(email, password, name, role, office, phone,
                           created_by=actor["email"], must_reset=must_reset)
    rec["employee_id"] = _next_employee_id(users)
    users[email] = rec
    save_users(users)
    audit("USER_CREATED", actor["email"], f"{email} as {role} ({rec['employee_id']})")
    return True, "Account created.", rec


def change_own_password(email, old_pw, new_pw, confirm_pw):
    users = load_users()
    rec = users.get(email.strip().lower())
    if rec is None:
        return False, "Account not found."
    if not verify_password(old_pw, rec["salt"], rec["hash"]):
        return False, "Current password is incorrect."
    if new_pw != confirm_pw:
        return False, "New passwords do not match."
    probs = password_problems(new_pw)
    if probs:
        return False, "Password must contain " + ", ".join(probs) + "."
    if verify_password(new_pw, rec["salt"], rec["hash"]):
        return False, "New password must differ from the current one."

    rec["salt"], rec["hash"] = hash_password(new_pw)
    rec["must_reset"] = False
    users[rec["email"]] = rec
    save_users(users)
    audit("PASSWORD_CHANGED", rec["email"], "self-service")
    return True, "Password updated."


def admin_reset_password(actor, target_email, new_pw):
    users = load_users()
    rec = users.get(target_email.strip().lower())
    if rec is None:
        return False, "Account not found."
    if AUTHORITY_ROLES[rec["role"]]["level"] < AUTHORITY_ROLES[actor["role"]]["level"]:
        return False, "Cannot reset the password of a higher authority."
    probs = password_problems(new_pw)
    if probs:
        return False, "Password must contain " + ", ".join(probs) + "."

    rec["salt"], rec["hash"] = hash_password(new_pw)
    rec["must_reset"] = True
    users[rec["email"]] = rec
    save_users(users)
    audit("PASSWORD_RESET", actor["email"], f"reset for {rec['email']}")
    return True, f"Password reset. {rec['name']} must set a new one at next sign-in."


def set_user_active(actor, target_email, active):
    users = load_users()
    rec = users.get(target_email.strip().lower())
    if rec is None:
        return False, "Account not found."
    if rec["email"] == actor["email"]:
        return False, "You cannot deactivate your own account."
    if AUTHORITY_ROLES[rec["role"]]["level"] < AUTHORITY_ROLES[actor["role"]]["level"]:
        return False, "Cannot modify a higher authority."
    rec["active"] = bool(active)
    users[rec["email"]] = rec
    save_users(users)
    audit("USER_ACTIVATED" if active else "USER_DEACTIVATED",
          actor["email"], rec["email"])
    return True, ("Account activated." if active else "Account deactivated.")


def update_user(actor, target_email, name=None, office=None, phone=None, role=None):
    users = load_users()
    rec = users.get(target_email.strip().lower())
    if rec is None:
        return False, "Account not found."
    if AUTHORITY_ROLES[rec["role"]]["level"] < AUTHORITY_ROLES[actor["role"]]["level"]:
        return False, "Cannot modify a higher authority."

    changed = []
    if name and name != rec["name"]:
        rec["name"] = name; changed.append("name")
    if office and office != rec["office"]:
        rec["office"] = office; changed.append("office")
    if phone and phone != rec["phone"]:
        rec["phone"] = phone; changed.append("phone")
    if role and role != rec["role"]:
        if AUTHORITY_ROLES[role]["level"] < AUTHORITY_ROLES[actor["role"]]["level"]:
            return False, "Cannot promote above your own authority level."
        meta = AUTHORITY_ROLES[role]
        rec.update({"role": role, "level": meta["level"],
                    "jurisdiction": meta["jurisdiction"],
                    "perms": list(meta["perms"])})
        changed.append("role")

    if not changed:
        return False, "Nothing to update."
    users[rec["email"]] = rec
    save_users(users)
    audit("USER_UPDATED", actor["email"], f"{rec['email']}: {', '.join(changed)}")
    return True, "Account updated (" + ", ".join(changed) + ")."


def delete_user(actor, target_email):
    users = load_users()
    rec = users.get(target_email.strip().lower())
    if rec is None:
        return False, "Account not found."
    if rec["email"] == actor["email"]:
        return False, "You cannot delete your own account."
    if AUTHORITY_ROLES[rec["role"]]["level"] < AUTHORITY_ROLES[actor["role"]]["level"]:
        return False, "Cannot delete a higher authority."
    del users[rec["email"]]
    save_users(users)
    audit("USER_DELETED", actor["email"], rec["email"])
    return True, f"Account {rec['email']} removed."


def can(user, perm):
    return perm in user.get("perms", [])


# ============================================================
# SECTION 5 — GOVERNMENT PORTAL DESIGN SYSTEM
# ============================================================
# Light, high-contrast and projector-safe: a dark dashboard with
# low-opacity ornament washes out in a bright demo hall, so the
# portal uses a paper-white surface, deep navy type and restrained
# tricolour accents — the visual language of india.gov.in.
# Motion is limited to a slow survey-contour drift in the masthead
# and gentle card lifts. Pure CSS: no CDN, no JS, nothing to fail.
# ============================================================

# Chart palettes — the same navy/saffron/green the chrome uses, so a figure
# never arrives in Plotly's default purple.
GOV_SEQ = ["#154a8a", "#e8801f", "#137a3a", "#0e7490", "#b4530f",
           "#42566b", "#5b21b6", "#9a6209"]
GOV_SCALE = [[0.0, "#e3ecf7"], [0.35, "#7ba7d4"], [0.7, "#2c6bb5"], [1.0, "#0d2b52"]]
GOV_SCALE_RG = [[0.0, "#b3251f"], [0.5, "#e8a33d"], [1.0, "#137a3a"]]

THEME_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Noto+Serif:wght@600;700&display=swap');

/* ============================================================
   Design tokens. Colour carries meaning here — consent state,
   authority level, risk band. Everything else is navy on paper.
   ============================================================ */
:root{
  --navy:#0d2b52; --navy-2:#164a8a; --navy-3:#2c6bb5;
  --ink:#10233c; --ink-2:#3d566f; --muted:#6b839c; --faint:#93a8c0;
  --saffron:#e8801f; --saffron-2:#c9670e; --green:#137a3a; --gold:#b8860b;

  --paper:#ffffff; --canvas:#eef2f7; --sunk:#f6f9fc;
  --line:#dde5ee; --line-2:#c9d6e4;

  --ok-bg:#e7f6ec; --ok-fg:#146c39; --ok-line:#a8dcbb;
  --no-bg:#fdeaea; --no-fg:#b3251f; --no-line:#f2b5b2;
  --wait-bg:#fdf2dc; --wait-fg:#9a6209; --wait-line:#ecd199;

  --sh-1:0 1px 2px rgba(13,43,82,.06);
  --sh-2:0 1px 2px rgba(13,43,82,.06), 0 6px 18px rgba(13,43,82,.07);
  --sh-3:0 2px 4px rgba(13,43,82,.07), 0 16px 36px rgba(13,43,82,.11);
  --r-s:8px; --r-m:11px; --r-l:15px;
}

html, body, .stApp, [class*="css"]{
  font-family:'Inter',"Segoe UI",system-ui,-apple-system,sans-serif;
  color:var(--ink);
  -webkit-font-smoothing:antialiased;
}

/* Numbers must line up in columns. */
[data-testid="stMetricValue"], .k-value, .stDataFrame, table,
.num, code, .mono{ font-variant-numeric:tabular-nums lining-nums; }

[data-testid="stAppViewContainer"]{
  background:
    radial-gradient(1100px 520px at 92% -10%, #e4edf8 0%, transparent 62%),
    radial-gradient(820px 440px at -5% 4%, #e9f3ec 0%, transparent 58%),
    var(--canvas);
  background-attachment:fixed;
}
[data-testid="stHeader"]{background:transparent;}
.main .block-container{padding-top:.9rem; padding-bottom:3rem; max-width:1560px;}

/* ---------- sidebar: a control panel, not a leftover column ---------- */
[data-testid="stSidebar"]{
  background:var(--paper);
  border-right:1px solid var(--line);
  box-shadow:1px 0 0 rgba(13,43,82,.02);
}
[data-testid="stSidebar"] > div{padding-top:1.1rem;}
[data-testid="stSidebar"] .stMarkdown,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] span{color:var(--ink);}
[data-testid="stSidebar"] .stMarkdown h3{
  color:var(--navy); font-weight:700; font-size:1.02rem; margin-bottom:.15rem;}
[data-testid="stSidebar"] .stCaption, [data-testid="stSidebar"] small{
  color:var(--muted);}
[data-testid="stSidebar"] .stButton>button,
[data-testid="stSidebar"] .stButton>button *{color:#fff !important;}
[data-testid="stSidebar"] .stButton>button{width:100%;}
[data-testid="stSidebar"] hr{margin:.85rem 0; border-color:var(--line);}

/* ---------- masthead ---------- */
.gov-strip{
  height:3px; border-radius:3px; margin-bottom:10px;
  background:linear-gradient(90deg,var(--saffron) 0 33.3%,#fff 33.3% 66.6%,var(--green) 66.6%);
  box-shadow:0 1px 2px rgba(13,43,82,.14);
}

.gov-header{
  position:relative; overflow:hidden;
  display:flex; align-items:center; gap:17px; flex-wrap:wrap;
  background:linear-gradient(118deg,#0b2447 0%,#14386b 58%,#1b4d8f 100%);
  border-radius:var(--r-l); padding:17px 24px; margin-bottom:16px;
  box-shadow:var(--sh-2);
}
/* survey-contour drift — the only motion in the chrome */
.gov-header::before{
  content:""; position:absolute; inset:-60%;
  background-image:
    repeating-linear-gradient(115deg, rgba(255,255,255,.05) 0 1px, transparent 1px 44px),
    repeating-linear-gradient(25deg,  rgba(255,255,255,.035) 0 1px, transparent 1px 60px);
  animation:contour 38s linear infinite; pointer-events:none;
}
@keyframes contour{ from{transform:translate3d(0,0,0);} to{transform:translate3d(44px,60px,0);} }
.gov-header > *{position:relative; z-index:1;}
.gov-header > div:nth-child(2){min-width:290px;}
.gov-header > div:last-child{min-width:176px;}

.gov-emblem{
  width:54px; height:54px; flex:0 0 54px; border-radius:50%;
  display:flex; align-items:center; justify-content:center;
  box-shadow:0 3px 14px rgba(0,0,0,.34);
}
.gov-emblem-svg{width:54px; height:54px; display:block;}
.gov-title{
  font-family:'Noto Serif',Georgia,serif;
  font-size:21px; font-weight:700; color:#fff; margin:0;
  letter-spacing:.1px; line-height:1.24;
}
.gov-sub{font-size:11.5px; color:#b9d2f0; margin:4px 0 0; line-height:1.55;}
.gov-ps{
  display:inline-block; margin-top:7px; padding:2px 9px;
  border:1px solid rgba(255,214,166,.4); border-radius:20px;
  font-size:9.5px; font-weight:700; letter-spacing:1.3px;
  color:#ffd9a8; text-transform:uppercase;
}

/* ---------- surfaces ---------- */
.gov-card{
  background:var(--paper); border:1px solid var(--line);
  border-radius:var(--r-m); padding:17px 19px; box-shadow:var(--sh-1);
  transition:box-shadow .18s ease, border-color .18s ease;
}
.gov-card:hover{box-shadow:var(--sh-2); border-color:var(--line-2);}

/* ---------- KPI tiles ---------- */
.kpi{
  position:relative; background:var(--paper);
  border:1px solid var(--line); border-radius:var(--r-m);
  padding:14px 16px 13px; box-shadow:var(--sh-1); height:100%;
  overflow:hidden;
}
.kpi::before{
  content:""; position:absolute; left:0; top:0; bottom:0; width:3px;
  background:var(--navy-2);
}
.kpi .k-label{
  font-size:10px; font-weight:700; letter-spacing:.85px;
  text-transform:uppercase; color:var(--muted); margin:0 0 6px;
}
.kpi .k-value{
  font-size:26px; font-weight:800; color:var(--navy); margin:0;
  line-height:1.1; letter-spacing:-.4px;
}
.kpi .k-note{
  font-size:11.5px; color:var(--ink-2); margin:6px 0 0;
  padding-top:6px; border-top:1px solid var(--line);
}
.kpi.ok::before{background:var(--ok-fg);}   .kpi.ok   .k-value{color:var(--ok-fg);}
.kpi.no::before{background:var(--no-fg);}   .kpi.no   .k-value{color:var(--no-fg);}
.kpi.wait::before{background:var(--wait-fg);} .kpi.wait .k-value{color:var(--wait-fg);}

/* ---------- state pills ---------- */
.pill{
  display:inline-flex; align-items:center; gap:4px;
  padding:3px 10px; border-radius:999px;
  font-size:11px; font-weight:700; letter-spacing:.1px;
  border:1px solid transparent;
}
.pill-ok{background:var(--ok-bg); color:var(--ok-fg); border-color:var(--ok-line);}
.pill-no{background:var(--no-bg); color:var(--no-fg); border-color:var(--no-line);}
.pill-wait{background:var(--wait-bg); color:var(--wait-fg); border-color:var(--wait-line);}

.reason-row{
  background:var(--paper); border:1px solid var(--line);
  border-left:3px solid var(--no-fg); border-radius:var(--r-s);
  padding:9px 13px; margin:6px 0; box-shadow:var(--sh-1);
}

/* ---------- authority badges ---------- */
.gov-badge{
  display:inline-block; padding:3px 10px; border-radius:999px;
  font-size:10px; font-weight:700; letter-spacing:.45px; color:#fff;
  text-transform:uppercase;
}
.lv1{background:#5b21b6;} .lv2{background:#1d4ed8;} .lv3{background:#0e7490;}
.lv4{background:#146c39;} .lv5{background:#b4530f;} .lv6{background:#52504c;}
.lv7{background:#42566b;}

/* st.container(border=True) should match .gov-card, not Streamlit's default */
[data-testid="stVerticalBlockBorderWrapper"]{
  border-radius:var(--r-m); background:var(--paper);
}
[data-testid="stVerticalBlockBorderWrapper"] > div{
  background:var(--paper); border-radius:var(--r-m);
}
div[data-testid="stVerticalBlockBorderWrapper"][style*="border"],
div[data-testid="stVerticalBlockBorderWrapper"]:has(> div[style*="border"]){
  background:var(--paper) !important;
  border:1px solid var(--line) !important; border-radius:var(--r-m) !important;
  box-shadow:var(--sh-2) !important;
}

/* ---------- sign-in page ---------- */
h3.login-h, .login-h{
  font-family:'Noto Serif',Georgia,serif !important; font-size:1.18rem !important;
  font-weight:700 !important; color:var(--navy) !important;
  margin:0 0 5px !important; padding:0 !important; line-height:1.3 !important;
}
h3.login-h a{display:none !important;}
.login-sub{
  font-size:13px !important; color:var(--ink-2) !important;
  margin:0 0 14px !important; line-height:1.6 !important;
}
.login-foot{
  font-size:11px; color:var(--muted); margin:14px 0 0;
  padding-top:11px; border-top:1px solid var(--line); line-height:1.6;
}
.login-facts{
  background:linear-gradient(160deg,#f7fafd,#eef3f9);
  border:1px solid var(--line); border-left:3px solid var(--saffron);
  border-radius:var(--r-m); padding:18px 20px; box-shadow:var(--sh-1);
}
.fact-grid{
  display:grid; grid-template-columns:repeat(3,1fr);
  gap:1px; background:var(--line);
  border:1px solid var(--line); border-radius:var(--r-s); overflow:hidden;
}
.fact-grid > div{background:var(--paper); padding:11px 13px;}
.fact-grid b{
  display:block; font-size:19px; font-weight:800; color:var(--navy);
  line-height:1.15; font-variant-numeric:tabular-nums;
}
.fact-grid span{
  display:block; font-size:9.5px; font-weight:600; letter-spacing:.5px;
  text-transform:uppercase; color:var(--muted); margin-top:3px;
}
@media (max-width:900px){ .fact-grid{grid-template-columns:repeat(2,1fr);} }

/* ---------- section lead ---------- */
.sec{margin:.1rem 0 1.15rem; padding-bottom:.6rem; border-bottom:2px solid var(--navy);}
.sec .sec-eyebrow, .sec-eyebrow{
  font-size:9.5px !important; font-weight:700 !important; letter-spacing:1.5px;
  text-transform:uppercase; color:var(--saffron-2) !important;
  margin:0 0 2px !important; line-height:1.4 !important;
}
.sec h2.sec-title, .sec-title{
  font-family:'Noto Serif',Georgia,serif !important;
  font-size:1.3rem !important; font-weight:700 !important;
  color:var(--navy) !important; margin:0 !important; padding:0 !important;
  letter-spacing:-.2px; line-height:1.25 !important;
}
.sec .sec-note, .sec-note{
  font-size:12.5px !important; color:var(--muted) !important;
  margin:4px 0 0 !important; line-height:1.55 !important;
}
.sec h2.sec-title a, .sec-title a{display:none !important;}

/* ---------- typography ---------- */
h1,h2,h3,h4,h5{color:var(--navy); font-weight:700; letter-spacing:-.2px;}
h5{
  font-size:1rem; margin:.2rem 0 .55rem; padding-bottom:.4rem;
  border-bottom:1px solid var(--line);
}
.main p, .main li{color:var(--ink-2);}

/* ---------- Streamlit metric ---------- */
[data-testid="stMetric"]{
  background:var(--paper); border:1px solid var(--line);
  border-radius:var(--r-m); padding:12px 15px; box-shadow:var(--sh-1);
}
[data-testid="stMetricLabel"] *{
  color:var(--muted) !important; font-size:10px !important;
  font-weight:700 !important; letter-spacing:.8px; text-transform:uppercase;
}
[data-testid="stMetricValue"]{
  color:var(--navy) !important; font-size:1.55rem !important;
  font-weight:800 !important; letter-spacing:-.4px;
}

/* ---------- buttons ---------- */
.stButton>button{
  background:var(--navy); color:#fff; border:1px solid var(--navy);
  border-radius:var(--r-s); padding:.46rem 1.05rem;
  font-weight:600; font-size:.875rem; letter-spacing:.1px;
  transition:background .15s ease, box-shadow .15s ease, transform .12s ease;
}
.stButton>button:hover{
  background:var(--navy-2); border-color:var(--navy-2); color:#fff;
  transform:translateY(-1px); box-shadow:0 5px 14px rgba(13,43,82,.24);
}
.stButton>button:active{transform:translateY(0); box-shadow:none;}
.stButton>button:focus-visible{outline:2px solid var(--saffron); outline-offset:2px;}
.stButton>button[kind="primary"]{
  background:linear-gradient(135deg,var(--saffron),var(--saffron-2));
  border-color:var(--saffron-2);
}
.stButton>button[kind="primary"]:hover{
  box-shadow:0 5px 16px rgba(232,128,31,.34);
}
.stButton>button:disabled, .stButton>button[disabled]{
  background:var(--sunk) !important; color:var(--faint) !important;
  border-color:var(--line) !important; box-shadow:none !important;
  transform:none !important; cursor:not-allowed;
}
.stButton>button:disabled *, .stButton>button[disabled] *{color:var(--faint) !important;}
[data-testid="stDownloadButton"]>button{
  background:var(--paper); color:var(--navy); border:1px solid var(--line-2);
  font-weight:600;
}
[data-testid="stDownloadButton"]>button:hover{
  background:var(--sunk); color:var(--navy); border-color:var(--navy-3);
}

/* ---------- owner reply: yes is green, no is red ---------- */
.st-key-owner_yes .stButton>button, .st-key-owner_yes button{
  background:var(--green) !important;
  background-image:linear-gradient(135deg,#169244,#0f6330) !important;
  border-color:#0f6330 !important; color:#fff !important;
  font-size:1rem !important; font-weight:700 !important; padding:.68rem 1rem !important;
}
.st-key-owner_yes button:hover{box-shadow:0 6px 18px rgba(19,122,58,.36) !important;}
.st-key-owner_no .stButton>button, .st-key-owner_no button{
  background:var(--paper) !important; background-image:none !important;
  border:1.5px solid var(--no-fg) !important; color:var(--no-fg) !important;
  font-size:1rem !important; font-weight:700 !important; padding:.68rem 1rem !important;
}
.st-key-owner_no button *{color:var(--no-fg) !important;}
.st-key-owner_no button:hover{
  background:var(--no-bg) !important;
  box-shadow:0 6px 18px rgba(179,37,31,.2) !important;
}

/* ---------- tabs: a segmented control, not a row of chips ----------
   Streamlit 1.64 renders tabs through react-aria: [data-testid="stTab"]
   inside [role="tablist"]. The older [data-baseweb="tab"] hooks are gone,
   so both are matched and either one will take. */
.stTabs [role="tablist"], .stTabs [data-baseweb="tab-list"]{
  gap:3px; background:var(--paper); border:1px solid var(--line);
  border-radius:var(--r-m); padding:4px; box-shadow:var(--sh-1);
  flex-wrap:wrap; margin-bottom:.2rem;
}
.stTabs [data-testid="stTab"], .stTabs [role="tab"], .stTabs [data-baseweb="tab"]{
  background:transparent !important; border:0 !important;
  border-radius:var(--r-s) !important; padding:7px 15px !important;
  font-weight:600 !important; font-size:.85rem !important;
  color:var(--ink-2) !important;
  transition:background .14s ease, color .14s ease;
}
.stTabs [data-testid="stTab"] p, .stTabs [role="tab"] p{
  color:inherit !important; font-size:.85rem !important; font-weight:600 !important;
}
.stTabs [role="tab"]:hover{background:var(--sunk) !important;}
.stTabs [role="tablist"] [role="tab"][aria-selected="true"],
.stTabs [role="tablist"] [data-testid="stTab"][data-selected="true"],
.stTabs [role="tablist"] [data-testid="stTab"][aria-selected="true"]{
  background:var(--navy) !important;
  background-image:none !important;
  color:#fff !important;
  border:0 !important; border-bottom:0 !important;
  box-shadow:0 2px 6px rgba(13,43,82,.28) !important;
}
.stTabs [role="tablist"] [role="tab"][aria-selected="true"] *,
.stTabs [role="tablist"] [data-testid="stTab"][data-selected="true"] *{
  color:#fff !important;
}
/* Streamlit paints the active marker as a pseudo-element underline */
.stTabs [role="tablist"] [role="tab"]::after,
.stTabs [role="tablist"] [role="tab"]::before{display:none !important;}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"],
.stTabs [role="tablist"] + div[class*="highlight"]{display:none !important;}
.stTabs [role="tabpanel"], .stTabs [data-baseweb="tab-panel"]{padding-top:1.15rem;}

/* ---------- data tables ---------- */
div[data-testid="stDataFrame"]{
  border:1px solid var(--line); border-radius:var(--r-m);
  overflow:hidden; box-shadow:var(--sh-1);
}
div[data-testid="stDataFrame"] [role="columnheader"]{
  background:var(--sunk) !important; color:var(--navy) !important;
  font-weight:700 !important; font-size:.78rem !important;
  letter-spacing:.3px; text-transform:uppercase;
  border-bottom:1px solid var(--line-2) !important;
}
div[data-testid="stDataFrame"] [role="gridcell"]{font-size:.855rem;}

/* ---------- expanders ---------- */
[data-testid="stExpander"]{
  border:1px solid var(--line) !important; border-radius:var(--r-m) !important;
  background:var(--paper); box-shadow:var(--sh-1); overflow:hidden;
}
[data-testid="stExpander"] summary{
  font-weight:600; font-size:.9rem; color:var(--navy); padding:.6rem .9rem;
}
[data-testid="stExpander"] summary:hover{background:var(--sunk);}

/* ---------- form controls ---------- */
.stSlider label, .stSelectbox label, .stTextInput label,
.stRadio label, .stMultiSelect label, .stCheckbox label,
.stTextArea label, [data-testid="stWidgetLabel"] p{
  color:var(--ink) !important; font-weight:600 !important;
  font-size:.845rem !important;
}
[data-baseweb="input"], [data-baseweb="base-input"],
[data-baseweb="textarea"], [data-baseweb="select"]>div,
[data-testid="stTextInput"]>div>div, [data-testid="stNumberInput"]>div>div,
[data-testid="stTextArea"]>div>div{
  background:var(--paper) !important;
  border:1.5px solid var(--line-2) !important; border-radius:var(--r-s) !important;
  box-shadow:var(--sh-1) !important;
}
[data-testid="stTextInput"] input, [data-testid="stNumberInput"] input,
[data-testid="stTextArea"] textarea,
[data-baseweb="input"] input, [data-baseweb="base-input"] input{
  background:transparent !important; color:var(--ink) !important;
  border:0 !important; -webkit-text-fill-color:var(--ink) !important;
}
[data-testid="stTextInput"] input::placeholder,
[data-testid="stTextArea"] textarea::placeholder{
  color:var(--faint) !important; -webkit-text-fill-color:var(--faint) !important;
}
[data-baseweb="input"]:hover, [data-baseweb="base-input"]:hover,
[data-testid="stTextInput"]>div>div:hover{border-color:var(--navy-3) !important;}
[data-baseweb="input"]:focus-within, [data-baseweb="base-input"]:focus-within,
[data-testid="stTextInput"]>div>div:focus-within{
  border-color:var(--saffron) !important;
  box-shadow:0 0 0 3px rgba(232,128,31,.15) !important;
}
[data-testid="stTextInput"] button, [data-testid="stTextInput"] svg{
  color:var(--muted) !important; fill:var(--muted) !important;
}

/* radio / multiselect chips */
[data-baseweb="tag"]{
  background:var(--navy) !important; border-radius:var(--r-s) !important;
}
[data-baseweb="tag"] span{color:#fff !important;}

/* slider in the project's own palette */
[data-testid="stSlider"] [data-baseweb="slider"] [role="slider"]{
  border-color:var(--saffron) !important;
}

/* ---------- inline code ---------- */
code, [data-testid="stCode"], .stCode, pre{
  background:var(--sunk) !important; color:var(--navy) !important;
  border:1px solid var(--line) !important; border-radius:6px !important;
  font-size:.83rem !important;
}
pre code{border:0 !important;}
[data-testid="stCode"]{box-shadow:var(--sh-1);}

/* ---------- alerts ---------- */
[data-testid="stAlert"]{
  border-radius:var(--r-m); border-width:1px; box-shadow:var(--sh-1);
  font-size:.875rem;
}
[data-testid="stAlert"] p{color:inherit !important;}

hr{border-color:var(--line); margin:1.1rem 0;}

/* ---------- map frame ---------- */
iframe{border-radius:var(--r-m) !important;}

/* ---------- respect reduced motion ---------- */
@media (prefers-reduced-motion: reduce){
  .gov-header::before{animation:none;}
  .stButton>button{transition:none;}
  .stButton>button:hover{transform:none;}
}
</style>
"""


STREAMLIT_CONFIG = """# Written by Bhoomi Predict so Streamlit's own widgets
# (inputs, code chips, sidebar) match the light portal theme.
[theme]
base = "light"
primaryColor = "#f28c28"
backgroundColor = "#eef2f7"
secondaryBackgroundColor = "#ffffff"
textColor = "#11243d"
font = "sans serif"

[server]
headless = false

[browser]
gatherUsageStats = false
"""


def ensure_theme_config():
    """Create .streamlit/config.toml on first run.

    Without it Streamlit keeps its own base theme for widget internals,
    which leaves dark input boxes on the light portal surface.
    """
    try:
        d = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".streamlit")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, "config.toml")
        if not os.path.exists(p):
            with open(p, "w", encoding="utf-8") as f:
                f.write(STREAMLIT_CONFIG)
            return True, p
        return False, p
    except Exception:
        return False, ""



# ---------- portal emblem ----------
# A purpose-drawn seal rather than an emoji: a survey ring of 24 ticks
# around a cadastral grid, with the proposed alignment cutting across it.
# The State Emblem of India (Lion Capital) is deliberately NOT used — its
# use is restricted under the State Emblem of India (Prohibition of
# Improper Use) Act, 2005.
# Switch the look with EMBLEM_STYLE: "seal" | "chakra" | "parcel".

EMBLEM_STYLE = "seal"


def _emblem_svg(style="seal"):
    ticks = "".join(
        f"<line x1='32' y1='4.2' x2='32' y2='{9.4 if i % 3 == 0 else 8.2}' "
        f"stroke='#0d2b52' stroke-width='{2.4 if i % 3 == 0 else 1.6}' "
        f"stroke-linecap='round' transform='rotate({i * 30} 32 32)'/>"
        for i in range(12))

    if style == "chakra":
        spokes = "".join(
            f"<line x1='32' y1='32' x2='32' y2='11' stroke='#0d2b52' "
            f"stroke-width='1.5' stroke-linecap='round' "
            f"transform='rotate({i * 15} 32 32)'/>" for i in range(24))
        inner = (f"<circle cx='32' cy='32' r='21' fill='none' stroke='#0d2b52' "
                 f"stroke-width='2.4'/>{spokes}"
                 f"<circle cx='32' cy='32' r='4.4' fill='#0d2b52'/>")
    elif style == "parcel":
        inner = ("<g stroke='#0d2b52' stroke-width='1.6' fill='none'>"
                 "<rect x='14' y='16' width='15' height='13' rx='1.5'/>"
                 "<rect x='31' y='16' width='19' height='13' rx='1.5'/>"
                 "<rect x='14' y='31' width='19' height='17' rx='1.5'/>"
                 "<rect x='35' y='31' width='15' height='17' rx='1.5'/></g>"
                 "<path d='M12 47 C24 41, 30 26, 52 18' stroke='#c0392b' "
                 "stroke-width='3.4' fill='none' stroke-linecap='round'/>")
    else:  # seal
        inner = (
            # cadastral holdings
            "<g stroke='#0d2b52' stroke-width='2.2' fill='#0d2b52' fill-opacity='.14' "
            "stroke-linejoin='round'>"
            "<rect x='14' y='18' width='14' height='12' rx='1.6'/>"
            "<rect x='30' y='18' width='20' height='12' rx='1.6'/>"
            "<rect x='14' y='32' width='20' height='14' rx='1.6'/>"
            "<rect x='36' y='32' width='14' height='14' rx='1.6'/></g>"
            # proposed alignment, with its right-of-way band
            "<path d='M12 47 L52 17' stroke='#fdf3d8' stroke-width='7.8' "
            "stroke-linecap='round'/>"
            "<path d='M12 47 L52 17' stroke='#c0392b' stroke-width='3.6' "
            "stroke-linecap='round'/>"
            # survey stations at the corridor ends, clear of the parcels
            "<circle cx='12' cy='47' r='3.1' fill='#0d2b52'/>"
            "<circle cx='52' cy='17' r='3.1' fill='#0d2b52'/>")

    return (
        "<svg class='gov-emblem-svg' viewBox='0 0 64 64' "
        "xmlns='http://www.w3.org/2000/svg' role='img' "
        "aria-label='Bhoomi Predict emblem'>"
        "<defs><radialGradient id='bpGold' cx='34%' cy='28%'>"
        "<stop offset='0%' stop-color='#fbe8ac'/>"
        "<stop offset='55%' stop-color='#e6c25f'/>"
        "<stop offset='100%' stop-color='#b8860b'/>"
        "</radialGradient></defs>"
        "<circle cx='32' cy='32' r='31' fill='url(#bpGold)'/>"
        "<circle cx='32' cy='32' r='29.2' fill='none' stroke='#8a6508' "
        "stroke-width='.9' stroke-opacity='.65'/>"
        f"{ticks}<circle cx='32' cy='32' r='24' fill='none' "
        "stroke='#0d2b52' stroke-width='1.8'/>"
        f"{inner}</svg>")


def inject_theme(st):
    st.markdown(THEME_CSS, unsafe_allow_html=True)


def gov_header(st, right_html=""):
    st.markdown("<div class='gov-strip'></div>", unsafe_allow_html=True)
    st.markdown(f"""
      <div class='gov-header'>
        <div class='gov-emblem'>{_emblem_svg(EMBLEM_STYLE)}</div>
        <div style='flex:1'>
          <p class='gov-title'>Bhoomi Predict · भूमि प्रेडिक्ट</p>
          <p class='gov-sub'>National Land Acquisition &amp; Management System ·
             தேசிய நில கையகப்படுத்தல் மேலாண்மை அமைப்பு</p>
          <span class='gov-ps'>Smart India Hackathon 2026 · PS 26017</span>
        </div>
        <div style='text-align:right'>{right_html}</div>
      </div>""", unsafe_allow_html=True)


def kpi(label, value, note="", tone=""):
    """Return HTML for one KPI tile. tone: '' | 'ok' | 'no' | 'wait'."""
    return (f"<div class='kpi {tone}'><p class='k-label'>{label}</p>"
            f"<p class='k-value'>{value}</p>"
            f"{f'<p class=k-note>{note}</p>' if note else ''}</div>")


def section(st, eyebrow, title, note=""):
    """Lead heading for a tab: small uppercase eyebrow over a serif title."""
    st.markdown(
        f"<div class='sec'><p class='sec-eyebrow'>{eyebrow}</p>"
        f"<h2 class='sec-title'>{title}</h2>"
        f"{f'<p class=sec-note>{note}</p>' if note else ''}</div>",
        unsafe_allow_html=True)


def pill(state):
    cls = {"Consented": "pill-ok", "Objected": "pill-no", "Pending": "pill-wait"}[state]
    st_ = CONSENT_STYLE[state]
    return f"<span class='pill {cls}'>{st_['icon']} {state}</span>"


# ============================================================
# SECTION 6 — CONSOLE SELF-TEST
# ============================================================

def console_test():
    print("=" * 70)
    print("BHOOMI PREDICT — National Land Acquisition Portal · Self Test")
    print("=" * 70)

    print("\n[1] Cadastral layer")
    p = load_parcels()
    print(f"    {len(p)} parcels · {p.extent_acres.sum():.1f} acres · "
          f"{p.phone.str.len().ge(10).sum()} contactable owners")

    print("\n[2] Parcel Intersection Engine")
    print(f"    Corridor: {CORRIDOR['name']}")
    print(f"    {CORRIDOR['start']['name']} → {CORRIDOR['via']['name']} (km "
          f"{CORRIDOR['via']['chainage_km']}) → {CORRIDOR['end']['name']} · "
          f"{CORRIDOR['length_km']} km")
    aff, _ = intersect_parcels(
        p, build_alignment(CORRIDOR["axis_bearing"], 0, 2000), CORRIDOR["row_m"])
    print(f"    Intersected survey numbers: {len(aff)} · "
          f"{aff.affected_acres.sum():.2f} acres")
    print(f"    Survey Nos: {', '.join(aff.survey_no.head(8))} …")

    print("\n[3] Consent register")
    reg = apply_consent_overrides(p)
    su = consent_summary(reg)
    for state in CONSENT_STATES:
        print(f"    {CONSENT_STYLE[state]['icon']} {state:<10}"
              f"{su[state]['count']:>3} holdings · {su[state]['acres']:>6} ac · "
              f"{su[state]['families']:>4} families")
    print(f"    consent rate: {su['consent_pct']}%")
    top = reg[reg.consent_status == "Objected"].objection_reason.value_counts()
    print(f"    grounds of objection on record: {len(top)}")
    for r, n in top.head(3).items():
        print(f"      • {r} ({n})")

    print("\n[4] XGBoost + exact TreeSHAP")
    m = BhoomiDelayModel().train(verbose=True)
    r = m.explain(parcel_to_features(aff.iloc[0].to_dict()))
    ok = abs(r["shap_sum_check"] - r["predicted_delay_days"]) < 0.5
    print(f"    additivity: base {r['base_value']} + Σshap = {r['shap_sum_check']} "
          f"vs {r['predicted_delay_days']}  {'✅ PASS' if ok else '❌ FAIL'}")

    print("\n[5] Authority hierarchy")
    for role in ROLE_ORDER:
        meta = AUTHORITY_ROLES[role]
        print(f"    L{meta['level']}  {role:<30}{meta['jurisdiction']:<12}"
              f"{len(meta['perms'])} perms")

    print("\n[6] Secure user store")
    users = load_users()
    print(f"    {len(users)} accounts seeded")
    raw = open(USER_DB, encoding="utf-8").read()
    leaked = [pw for _, pw, *_ in SEED_USERS if pw in raw]
    print(f"    PBKDF2-HMAC-SHA256 × {PBKDF2_ROUNDS:,} rounds, per-user salt")
    print(f"    plaintext passwords on disk: "
          f"{'❌ ' + str(leaked) if leaked else '✅ none'}")

    print("\n[7] Authentication")
    u, msg = authenticate("collector.ttn@tn.gov.in", "Collector@2026")
    print(f"    ✅ email login   → {u['name']} ({u['employee_id']}, {u['role']})")
    u2, _ = authenticate(u["employee_id"], "Collector@2026")
    print(f"    ✅ empID login   → {u2['name']}")
    print(f"    ✅ wrong password → {authenticate('collector.ttn@tn.gov.in','x')[1]}")

    print("\n[8] User creation & guard rails")
    ok, msg, rec = create_user(u, "selftest@tn.gov.in", "Strong@2026",
                               "Self Test Officer", "Land Acquisition Officer",
                               "Ettayapuram Taluk", "9800000099")
    print(f"    create ........ {ok} · {rec['employee_id'] if rec else msg}")
    if rec:
        print(f"    escalation .... "
              f"{create_user(rec,'x@y.gov.in','Strong@2026','X','Central Ministry Officer','D','9')[1]}")
        print(f"    weak password . "
              f"{create_user(u,'w@y.gov.in','abc','W','Policy Analyst','D','9')[1]}")
        print(f"    change own pw . "
              f"{change_own_password('selftest@tn.gov.in','Strong@2026','Newer@2026','Newer@2026')[1]}")
        print(f"    deactivate .... {set_user_active(u,'selftest@tn.gov.in',False)[1]}")
        print(f"    blocked login . {authenticate('selftest@tn.gov.in','Newer@2026')[1]}")
        delete_user(u, "selftest@tn.gov.in")
        print(f"    cleanup ....... self-test account removed")

    print(f"\n[9] Audit trail: {len(read_audit())} entries recorded")

    print("\n" + "=" * 70)
    print("✅ ALL MODULES WORKING.")
    print("   இப்போ:  streamlit run bhoomi_portal.py")
    print("=" * 70)


# ============================================================
# SECTION 7 — STREAMLIT PORTAL
# ============================================================

def streamlit_app():
    import streamlit as st
    import plotly.graph_objects as go
    import plotly.express as px
    import folium
    from streamlit_folium import st_folium

    st.set_page_config(page_title="Bhoomi Predict · Government Portal",
                       page_icon="🏛️", layout="wide")
    inject_theme(st)

    @st.cache_resource
    def get_model():
        return BhoomiDelayModel().train()

    @st.cache_data
    def get_parcels():
        return load_parcels()

    # A template rather than loose layout keys: call sites are free to pass
    # their own xaxis / yaxis without colliding with the theme.
    LIGHT_TPL = go.layout.Template(layout=dict(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#11243d", family="Inter, Segoe UI, sans-serif", size=12),
        xaxis=dict(gridcolor="#e5ecf4", zerolinecolor="#dbe4ee",
                   linecolor="#dbe4ee", title_font=dict(size=12)),
        yaxis=dict(gridcolor="#e5ecf4", zerolinecolor="#dbe4ee",
                   linecolor="#dbe4ee", title_font=dict(size=12)),
        colorway=["#154a8a", "#f28c28", "#137a3a", "#7c3aed", "#0e7490", "#b91c1c"],
        hoverlabel=dict(bgcolor="#ffffff", bordercolor="#dbe4ee",
                        font=dict(color="#11243d")),
    ))
    PLOT_BG = dict(template=LIGHT_TPL)

    def _show(st_, ok, msg):
        """Statement-form success/error so Streamlit magic never sees a
        bare expression (which it would try to auto-render)."""
        if ok:
            st_.success(msg)
        else:
            st_.error(msg)

    for k in ("user", "affected", "scored", "ptype"):
        st.session_state.setdefault(k, None)

    # ==========================================================
    # PUBLIC OWNER RESPONSE PAGE  (?r=<survey>-<token>)
    # ==========================================================
    # Reached from the link in the notice. No sign-in: the landowner is
    # not an officer. The token in the link is what authorises the reply.
    try:
        ref = st.query_params.get("r")
    except Exception:
        ref = None
    if ref:
        sno = parse_response_ref(ref)
        gov_header(st)
        mid = st.columns([1, 2.2, 1])[1]
        with mid:
            if not sno:
                st.error("This response link is not valid. Please check the "
                         "link in your notice, or contact the Revenue Office.")
                return
            reg = apply_consent_overrides(get_parcels())
            match = reg[reg.survey_no.astype(str) == str(sno)]
            if match.empty:
                st.error(f"Survey No {sno} was not found in the village register.")
                return
            row = match.iloc[0]

            if st.session_state.get("responded_" + str(sno)):
                state = st.session_state["responded_" + str(sno)]
                stl = CONSENT_STYLE[state]
                st.markdown(
                    f"<div class='gov-card' style='text-align:center;padding:28px'>"
                    f"<div style='font-size:40px'>{stl['icon']}</div>"
                    f"<h3 style='margin:6px 0'>Reply recorded</h3>"
                    f"<p>Survey No <b>{sno}</b> — <b>{state}</b></p>"
                    + (f"<p style='margin:10px 0 0'>Relief sought:<br>"
                       f"<b>{st.session_state.get('relief_' + str(sno))}</b></p>"
                       f"<p style='color:#5b7089;font-size:12.5px'>Referred to: "
                       f"{RELIEF_ESCALATION.get(st.session_state.get('relief_' + str(sno), ''), 'Revenue Department')}</p>"
                       if st.session_state.get("relief_" + str(sno)) else "")
                    + f"<p style='color:#5b7089;font-size:13px'>The Revenue "
                    f"Department has been notified. Keep this for your record.</p>"
                    f"</div>", unsafe_allow_html=True)
                return

            req_cent = float(row.affected_acres if "affected_acres" in row
                             else row.extent_acres) * ACRE_IN_CENT
            gv = float(row.get("guideline_value_per_cent", 0) or 0)
            st.markdown(f"""<div class='gov-card'>
              <h4 style='margin-top:0'>Land Acquisition Notice — your reply</h4>
              <p style='margin:2px 0'><b>{CORRIDOR['name']}</b></p>
              <hr>
              <p style='margin:4px 0'>Land owner: <b>{row.owner}</b></p>
              <p style='margin:4px 0'>Survey No: <b>{row.survey_no}</b> ·
                 Patta: {row.patta_no} · Chitta: {row.chitta_no}</p>
              <p style='margin:4px 0'>Total extent:
                 <b>{row.extent_acres:g} acre ({row.extent_acres*100:g} cent)</b></p>
              <p style='margin:4px 0'>Extent required:
                 <b>{req_cent:.1f} cent</b></p>
              <p style='margin:4px 0'>Guideline value: ₹{_inr(gv)} per cent</p>
              <p style='margin:10px 0 0;font-size:17px'>Compensation payable:
                 <b style='color:#15803d'>₹{_inr(req_cent*gv)}</b></p>
            </div>""", unsafe_allow_html=True)
            st.write("")
            st.markdown("##### Do you consent to this acquisition?")

            b1, b2 = st.columns(2)
            if b1.button("✅  I CONSENT", use_container_width=True,
                         type="primary", key="owner_yes"):
                save_consent_override(sno, "Consented", officer="owner-link")
                audit("OWNER_REPLY", f"owner:{row.owner}", f"S.No {sno} → Consented")
                st.session_state["responded_" + str(sno)] = "Consented"
                st.rerun()
            if b2.button("⛔  I OBJECT", use_container_width=True,
                         key="owner_no"):
                st.session_state["obj_form_" + str(sno)] = True

            if st.session_state.get("obj_form_" + str(sno)):
                st.divider()
                st.markdown("##### 1. Why are you objecting?")
                st.caption("Recorded under Sec 15, RFCTLARR 2013.")
                reason = st.selectbox("Ground of objection", OBJECTION_REASONS,
                                      key="own_reason")
                other = st.text_input("Or state another ground", key="own_other")

                st.markdown("##### 2. What do you want instead?")
                st.caption("The Collector must dispose of your objection, so "
                           "tell us the relief you are asking for.")
                relief = st.selectbox("Relief sought", RELIEF_OPTIONS,
                                      key="own_relief")

                if relief == RELIEF_OPTIONS[0]:
                    st.info("**Land in lieu of compensation.** Under the Second "
                            "Schedule of the RFCTLARR Act, an affected family in "
                            "an irrigation project is entitled to a minimum of "
                            "one acre in the command area. Your request will be "
                            "referred to the State land bank.", icon="🌾")

                note = st.text_area("Anything else the Collector should know "
                                    "(optional)", key="own_note", height=90,
                                    placeholder="e.g. the well on this land "
                                                "irrigates two other holdings")

                if st.button("Submit objection", use_container_width=True,
                             type="primary"):
                    g = other.strip() or reason
                    save_consent_override(sno, "Objected", reason=g,
                                          officer="owner-link",
                                          relief=relief, note=note.strip())
                    audit("OWNER_REPLY", f"owner:{row.owner}",
                          f"S.No {sno} → Objected · ground: {g} · "
                          f"relief: {relief}")
                    st.session_state["responded_" + str(sno)] = "Objected"
                    st.session_state["relief_" + str(sno)] = relief
                    st.rerun()
        return

    # ==========================================================
    # LOGIN
    # ==========================================================
    if st.session_state.user is None:
        gov_header(st)
        # Two columns: the sign-in card, and the standing project facts beside
        # it — an empty half-page under a floating form looks unfinished.
        left, gap, right = st.columns([1.15, .12, 1])

        with left:
            with st.container(border=True):
                st.markdown(
                    "<p class='sec-eyebrow'>Restricted access</p>"
                    "<h3 class='login-h'>Authorised Officer Sign-in</h3>"
                    "<p class='login-sub'>Use your official email address or "
                    "employee ID. Every sign-in is written to the audit "
                    "trail.</p>", unsafe_allow_html=True)

                ident = st.text_input("Official email / Employee ID",
                                      placeholder="collector.ttn@tn.gov.in  or  BP0003")
                pw = st.text_input("Password", type="password")

                if st.button("Sign in", type="primary", use_container_width=True):
                    u, msg = authenticate(ident, pw)
                    if u:
                        st.session_state.user = u
                        st.rerun()
                    else:
                        st.error(msg)

                st.markdown(
                    "<p class='login-foot'>Passwords are stored as "
                    "PBKDF2-HMAC-SHA256 hashes with a per-user salt. "
                    "This portal holds no plaintext credential.</p>",
                    unsafe_allow_html=True)

        with right:
            _p = load_parcels()
            _al = build_alignment(CORRIDOR["axis_bearing"], 0, 2000)
            _hit, _ = intersect_parcels(_p, _al, CORRIDOR["row_m"])
            _cs = consent_summary(apply_consent_overrides(seed_consent(_p)))
            st.markdown(f"""
              <div class='login-facts'>
                <p class='sec-eyebrow'>Project under administration</p>
                <h3 class='login-h'>{CORRIDOR['name']}</h3>
                <p class='login-sub'>{VILLAGE_NAME} · {TALUK_NAME} taluk ·
                   {DISTRICT_NAME} district — {PIN_CODE}</p>
                <div class='fact-grid'>
                  <div><b>{len(_p)}</b><span>parcels on roll</span></div>
                  <div><b>{CORRIDOR['length_km']} km</b><span>corridor length</span></div>
                  <div><b>{len(_hit)}</b><span>parcels intersected</span></div>
                  <div><b>{CORRIDOR['row_m']} m</b><span>right of way</span></div>
                  <div><b>{_cs['Consented']['count']}</b><span>consented</span></div>
                  <div><b>{_cs['Objected']['count']}</b><span>objections filed</span></div>
                </div>
                <p class='login-foot'>Proceedings under the Right to Fair
                   Compensation and Transparency in Land Acquisition,
                   Rehabilitation and Resettlement Act, 2013.</p>
              </div>""", unsafe_allow_html=True)

        with left:
            with st.expander("Demo credentials (seeded accounts)"):
                users = load_users()
                seeds = {e: pw for e, pw, *_ in SEED_USERS}
                st.dataframe(pd.DataFrame([
                    {"Employee ID": u["employee_id"], "Email": e,
                     "Password": seeds.get(e, "— changed —"),
                     "Role": u["role"], "Level": u["level"]}
                    for e, u in sorted(users.items(), key=lambda x: x[1]["level"])
                ]), use_container_width=True, hide_index=True)
                st.caption("Accounts you create later appear here as “changed”, "
                           "because only their hash is stored.")
        return

    user = st.session_state.user
    model = get_model()
    parcels = apply_consent_overrides(get_parcels())
    lvl = AUTHORITY_ROLES[user["role"]]["level"]

    gov_header(st, f"""
      <div style='font-size:13px;color:#fff;font-weight:600'>{user['name']}</div>
      <div style='font-size:11px;color:#9fc0e8'>{user['office']}</div>
      <span class='gov-badge lv{lvl}'>L{lvl} · {user['role']}</span>""")

    # ---------------- sidebar ----------------
    with st.sidebar:
        st.markdown(f"### {user['name']}")
        st.caption(f"{user['employee_id']} · {user['role']}")
        st.caption(f"Jurisdiction: {user['jurisdiction']}")
        if user.get("last_login"):
            st.caption(f"Last sign-in: {user['last_login']}")
        st.divider()
        if st.button("Sign out", use_container_width=True):
            audit("LOGOUT", user["email"])
            st.session_state.user = None
            st.rerun()

    if is_hosted() and not st.session_state.get("_hosted_notice_seen"):
        st.info("Hosted deployment — accounts, consent replies and the audit "
                "trail are stored on the server's disk and are reset when the "
                "app restarts or redeploys. A permanent installation uses "
                "PostgreSQL.", icon="ℹ️")
        st.session_state["_hosted_notice_seen"] = True

    if user.get("must_reset"):
        st.warning("⚠️ Your password was set by an administrator. "
                   "Please change it in **My Account**.")

    # ---------------- tabs by permission ----------------
    # (key, label, permission) — plain wording, no emoji. A revenue portal
    # should read like one; the key is separate so labels can change freely.
    tab_defs = [("dash",    "Dashboard",        P_DASH),
                ("align",   "Alignment",        P_ALIGN),
                ("consent", "Consent Register", P_DASH),
                ("risk",    "Risk Model",       P_RISK),
                ("notices", "Notices",          P_NOTIFY),
                ("stats",   "Analytics",        P_ANALYTICS),
                ("users",   "User Management",  P_USERS)]
    visible = [(k, l) for k, l, p in tab_defs if can(user, p)] + [("me", "My Account")]
    tabs = st.tabs([l for _, l in visible])
    T = {k: tabs[i] for i, (k, _) in enumerate(visible)}

    # ==================== DASHBOARD ====================
    if "dash" in T:
        with T["dash"]:
            vsu = consent_summary(parcels)
            a, b, c, d = st.columns(4)
            a.markdown(kpi("Cadastral parcels", len(parcels),
                           f"{parcels.extent_acres.sum():.1f} acres"),
                       unsafe_allow_html=True)
            b.markdown(kpi("Consented", vsu["Consented"]["count"],
                           f"{vsu['Consented']['acres']} ac", "ok"),
                       unsafe_allow_html=True)
            c.markdown(kpi("Objected", vsu["Objected"]["count"],
                           f"{vsu['Objected']['acres']} ac", "no"),
                       unsafe_allow_html=True)
            d.markdown(kpi("Pending", vsu["Pending"]["count"],
                           f"{vsu['Pending']['acres']} ac", "wait"),
                       unsafe_allow_html=True)
            st.write("")
            e, f_, g = st.columns(3)
            e.metric("Affected families", int(parcels.affected_families.sum()))
            f_.metric("Contactable owners",
                      f"{int(parcels.phone.str.len().ge(10).sum())}/{len(parcels)}")
            g.metric("Consent rate", f"{vsu['consent_pct']}%")
            st.divider()

            l, r = st.columns(2)
            with l:
                st.markdown("##### Ownership category")
                vc = parcels.ownership_category.value_counts()
                fig = px.pie(values=vc.values, names=vc.index, hole=.45,
                             color_discrete_sequence=GOV_SEQ)
                fig.update_layout(height=340, margin=dict(t=8, b=8), **PLOT_BG)
                st.plotly_chart(fig, use_container_width=True)
            with r:
                st.markdown("##### Land type by extent")
                lt = parcels.groupby("land_type").extent_acres.sum().sort_values()
                fig = px.bar(x=lt.values, y=lt.index, orientation="h",
                             labels={"x": "Acres", "y": ""},
                             color=lt.values, color_continuous_scale=GOV_SCALE)
                fig.update_layout(height=340, margin=dict(t=8, b=8),
                                  coloraxis_showscale=False, **PLOT_BG)
                st.plotly_chart(fig, use_container_width=True)

            st.markdown("##### Village cadastral roll")
            st.dataframe(parcels[["survey_no", "owner", "ownership_category",
                                  "land_type", "extent_acres", "consent_status",
                                  "objection_reason", "phone"]],
                         use_container_width=True, hide_index=True, height=290)

    # ==================== ALIGNMENT ====================
    if "align" in T:
        with T["align"]:
            section(st, "Corridor alignment",
                    f"{CORRIDOR['name']}",
                    f"{CORRIDOR['length_km']} km · {CORRIDOR['row_m']} m right of way · "
                    f"chainage measured from {CORRIDOR['start']['name']}")
            st.markdown(
                f"<div class='gov-card' style='padding:13px 18px;margin-bottom:12px'>"
                f"<span style='font-size:12.5px;color:#5b7089'>"
                f"<b style='color:#0d2b52'>{CORRIDOR['start']['name']}</b>"
                f" &nbsp;──&nbsp; <b style='color:#c0392b'>"
                f"{CORRIDOR['via']['name']} · km {CORRIDOR['via']['chainage_km']}</b>"
                f" &nbsp;──&nbsp; <b style='color:#0d2b52'>"
                f"{CORRIDOR['end']['name']}</b> &nbsp;·&nbsp; "
                f"{CORRIDOR['length_km']} km &nbsp;·&nbsp; {CORRIDOR['design']}"
                f" &nbsp;·&nbsp; {CORRIDOR['authority']}</span></div>",
                unsafe_allow_html=True)
            st.caption(f"The study village sits at km "
                       f"{CORRIDOR['via']['chainage_km']} of the corridor. Move the "
                       f"alignment and the engine recomputes every intersected parcel, "
                       f"its ownership category and the extent to be acquired.")

            c1, c2, c3, c4 = st.columns(4)
            bearing = c1.slider("Bearing (°)", 0, 180,
                                CORRIDOR["axis_bearing"], 2,
                                help="18° is the true NH-44 axis through the village.")
            offset = c2.slider("Lateral offset (m)", -400, 400, 0, 25)
            width = c3.slider("Corridor width (m)", 15, 90,
                              CORRIDOR["row_m"], 5,
                              help="45 m is the standard right-of-way for a "
                                   "4-lane divided National Highway.")
            ptype = c4.selectbox("Project type", PROJECT_TYPES)

            alignment = build_alignment(bearing, offset, 2000)
            affected, corridor = intersect_parcels(parcels, alignment, width)
            st.session_state.affected = affected
            st.session_state.ptype = ptype

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Parcels intersected", len(affected))
            m2.metric("Extent to acquire",
                      f"{affected.affected_acres.sum():.2f} ac" if len(affected) else "0 ac")
            m3.metric("Full acquisitions",
                      int((affected.affected_pct >= 99.9).sum()) if len(affected) else 0)
            m4.metric("Uneconomic residue",
                      int(affected.uneconomic_residue.sum()) if len(affected) else 0)

            # OpenStreetMap needs no API key; CartoDB basemaps now do.
            if len(affected):
                asu = consent_summary(affected)
                b1, b2, b3 = st.columns(3)
                b1.markdown(kpi("Consented on this line",
                                asu["Consented"]["count"],
                                f"{asu['Consented']['acres']} ac", "ok"),
                            unsafe_allow_html=True)
                b2.markdown(kpi("Objected on this line",
                                asu["Objected"]["count"],
                                f"{asu['Objected']['acres']} ac", "no"),
                            unsafe_allow_html=True)
                b3.markdown(kpi("Awaiting response",
                                asu["Pending"]["count"],
                                f"{asu['Pending']['acres']} ac", "wait"),
                            unsafe_allow_html=True)
                st.caption("Shift the alignment to route around objecting holdings — "
                           "the split updates live.")
                st.write("")

            fmap = folium.Map(location=list(VILLAGE_CENTRE), zoom_start=15,
                              tiles="OpenStreetMap")
            folium.TileLayer(
                tiles="https://server.arcgisonline.com/ArcGIS/rest/services/"
                      "World_Imagery/MapServer/tile/{z}/{y}/{x}",
                attr="Esri", name="Satellite").add_to(fmap)

            hits = set(affected.survey_no) if len(affected) else set()
            for _, p in parcels.iterrows():
                hit = p.survey_no in hits
                col = CONSENT_STYLE[p.consent_status]["colour"] if hit else "#93a9c4"
                extra = ""
                if p.consent_status == "Objected" and p.objection_reason:
                    extra = f"<br><i>Objection: {p.objection_reason}</i>"
                elif p.consent_status == "Pending" and p.pending_stage:
                    extra = f"<br><i>{p.pending_stage}</i>"
                folium.Polygon(
                    locations=[(y, x) for x, y in p.geometry.exterior.coords],
                    color=col, weight=2 if hit else 1, fill=True, fill_color=col,
                    fill_opacity=.60 if hit else .10,
                    tooltip=f"S.No {p.survey_no} · {p.owner} · {p.consent_status}",
                    popup=folium.Popup(
                        f"<b>Survey No {p.survey_no}</b><br>{p.owner}<br>"
                        f"{p.ownership_category} · {p.land_type}<br>"
                        f"Extent {p.extent_acres} ac<br>"
                        f"<b>{CONSENT_STYLE[p.consent_status]['icon']} "
                        f"{p.consent_status}</b>{extra}", max_width=270)).add_to(fmap)

            folium.Polygon([(y, x) for x, y in corridor.exterior.coords],
                           color="#f28c28", weight=3, fill=True,
                           fill_color="#f28c28", fill_opacity=.25,
                           tooltip=f"Corridor · {width} m").add_to(fmap)
            folium.PolyLine([(y, x) for x, y in alignment.coords],
                            color="#0d2b52", weight=3, dash_array="9,6",
                            tooltip="Centre-line").add_to(fmap)
            folium.LayerControl().add_to(fmap)
            st_folium(fmap, height=470, use_container_width=True, returned_objects=[])
            st.markdown(
                "<div style='display:flex;gap:18px;flex-wrap:wrap;font-size:12px;"
                "color:#5b7089;margin-top:-6px'>"
                "<span>🟩 on line · consented</span>"
                "<span>🟥 on line · objected</span>"
                "<span>🟧 on line · pending</span>"
                "<span>⬜ not on this alignment</span>"
                "<span>🟠 proposed corridor</span></div>",
                unsafe_allow_html=True)

            with st.expander(f"🗺️ Corridor overview — {CORRIDOR['start']['name']} to "
                             f"{CORRIDOR['end']['name']} ({CORRIDOR['length_km']} km)"):
                mid = ((CORRIDOR["start"]["lat"] + CORRIDOR["end"]["lat"]) / 2,
                       (CORRIDOR["start"]["lon"] + CORRIDOR["end"]["lon"]) / 2)
                cmap = folium.Map(location=list(mid), zoom_start=9,
                                  tiles="OpenStreetMap")
                pts = [CORRIDOR["start"], CORRIDOR["via"], CORRIDOR["end"]]
                folium.PolyLine([(p["lat"], p["lon"]) for p in pts],
                                color="#f28c28", weight=5, opacity=.85,
                                tooltip=CORRIDOR["short"]).add_to(cmap)
                for p in pts:
                    here = p["name"] == CORRIDOR["via"]["name"]
                    folium.CircleMarker(
                        (p["lat"], p["lon"]), radius=9 if here else 7,
                        color="#c0392b" if here else "#0d2b52", fill=True,
                        fill_color="#c0392b" if here else "#0d2b52", fill_opacity=.9,
                        tooltip=f"{p['name']} · km {p['chainage_km']}"
                                + (" · study village" if here else "")).add_to(cmap)
                st_folium(cmap, height=330, use_container_width=True,
                          returned_objects=[], key="corridor_map")
                st.caption(f"The 55-parcel cadastral roll is the village at km "
                           f"{CORRIDOR['via']['chainage_km']}, near "
                           f"{CORRIDOR['via']['name']}.")

            st.markdown("##### Intersected parcels")
            if len(affected) == 0:
                st.info("No parcels intersected — adjust the alignment.")
            else:
                show = affected[["survey_no", "patta_no", "chitta_no", "owner",
                                 "ownership_category", "land_type",
                                 "extent_acres", "affected_acres", "affected_pct",
                                 "residual_acres", "uneconomic_residue",
                                 "guideline_value_per_cent",
                                 "consent_status", "objection_reason", "phone"]].copy()
                # Revenue records work in cent; compensation follows the
                # registration department's guideline value.
                show["req_cent"] = (show.affected_acres * ACRE_IN_CENT).round(1)
                show["total_cent"] = (show.extent_acres * ACRE_IN_CENT).round(1)
                show["compensation"] = (show.req_cent
                                        * show.guideline_value_per_cent).round(0)
                show = show[["survey_no", "patta_no", "chitta_no", "owner",
                             "ownership_category", "land_type",
                             "extent_acres", "total_cent", "affected_acres",
                             "req_cent", "affected_pct", "residual_acres",
                             "uneconomic_residue", "guideline_value_per_cent",
                             "compensation", "consent_status",
                             "objection_reason", "phone"]]
                show.columns = ["Survey No", "Patta No", "Chitta No", "Owner",
                                "Category", "Land type", "Total (ac)",
                                "Total (cent)", "Required (ac)", "Required (cent)",
                                "Affected %", "Residue (ac)", "Uneconomic",
                                "Guideline ₹/cent", "Compensation ₹", "Consent",
                                "Objection reason", "Phone"]
                tot = float(show["Compensation ₹"].sum())
                st.markdown(
                    f"<div class='gov-card' style='padding:13px 18px;margin-bottom:10px'>"
                    f"<b>Compensation payable on this alignment: "
                    f"₹{_inr(tot)}</b> &nbsp;·&nbsp; "
                    f"<span style='color:#5b7089;font-size:12.5px'>"
                    f"{show['Required (cent)'].sum():.1f} cent across "
                    f"{len(show)} holdings, at the registration department's "
                    f"guideline value</span></div>", unsafe_allow_html=True)
                st.dataframe(show, use_container_width=True, hide_index=True)
                st.download_button("⬇️ Download 3(a) schedule (CSV)",
                                   show.to_csv(index=False).encode(),
                                   f"affected_parcels_{bearing}deg_{width}m.csv", "text/csv")

    # ==================== CONSENT REGISTER ====================
    if "consent" in T:
        with T["consent"]:
            section(st, "Section 15 · RFCTLARR 2013", "Consent Register",
                    "Who is giving land, who is not, and on what stated ground")
            st.caption("Recorded under RFCTLARR 2013 Sec 15. Every holding sits in one "
                       "of three states, and every refusal carries a reason on record.")

            affected = st.session_state.affected
            scope = st.radio("Scope", ["Parcels on the current alignment",
                                       "Whole village register"],
                             horizontal=True, key="cons_scope")
            if scope.startswith("Parcels") and affected is not None and len(affected):
                reg = apply_consent_overrides(affected.copy())
                area_col = "affected_acres"
                st.caption(f"{len(reg)} parcels intersected by the current alignment.")
            else:
                reg = apply_consent_overrides(parcels.copy())
                area_col = "extent_acres"
                if scope.startswith("Parcels"):
                    st.info("No alignment set yet — showing the whole village register.")

            su = consent_summary(reg)

            # ---- headline split ----
            k1, k2, k3, k4 = st.columns(4)
            k1.markdown(kpi("Total holdings", su["total"]["count"],
                            f"{su['total']['acres']} acres"), unsafe_allow_html=True)
            k2.markdown(kpi("Consented", su["Consented"]["count"],
                            f"{su['Consented']['acres']} ac · "
                            f"{su['Consented']['families']} families", "ok"),
                        unsafe_allow_html=True)
            k3.markdown(kpi("Objected", su["Objected"]["count"],
                            f"{su['Objected']['acres']} ac · "
                            f"{su['Objected']['families']} families", "no"),
                        unsafe_allow_html=True)
            k4.markdown(kpi("Pending", su["Pending"]["count"],
                            f"{su['Pending']['acres']} ac · "
                            f"{su['Pending']['families']} families", "wait"),
                        unsafe_allow_html=True)
            st.write("")

            c1, c2 = st.columns([1, 1.25])
            with c1:
                st.markdown("**Consent position**")
                vals = [su[s]["count"] for s in CONSENT_STATES]
                fig = go.Figure(go.Pie(
                    labels=[CONSENT_STYLE[s]["label"] for s in CONSENT_STATES],
                    values=vals, hole=.56, sort=False,
                    marker=dict(colors=[CONSENT_STYLE[s]["colour"]
                                        for s in CONSENT_STATES],
                                line=dict(color="#fff", width=2)),
                    textinfo="percent"))
                fig.update_layout(height=310, margin=dict(t=6, b=6, l=6, r=6),
                                  showlegend=True,
                                  legend=dict(orientation="h", y=-.12),
                                  annotations=[dict(
                                      text=f"<b>{su['consent_pct']}%</b><br>"
                                           f"<span style='font-size:11px'>consented</span>",
                                      x=.5, y=.5, showarrow=False, font=dict(size=20))],
                                  **PLOT_BG)
                st.plotly_chart(fig, use_container_width=True)

            with c2:
                st.markdown("**Extent by consent position (acres)**")
                fig = go.Figure()
                for s in CONSENT_STATES:
                    fig.add_bar(x=[su[s]["acres"]], y=["Extent"], orientation="h",
                                name=s, marker_color=CONSENT_STYLE[s]["colour"],
                                text=f"{su[s]['acres']} ac", textposition="inside",
                                insidetextfont=dict(color="#fff", size=13))
                fig.update_layout(barmode="stack", height=150, showlegend=True,
                                  legend=dict(orientation="h", y=-.45),
                                  margin=dict(t=6, b=6, l=6, r=6),
                                  yaxis=dict(showticklabels=False), **PLOT_BG)
                st.plotly_chart(fig, use_container_width=True)

                obj = reg[reg.consent_status == "Objected"]
                st.markdown("**Why owners are refusing**")
                if len(obj) == 0:
                    st.caption("No objections on record for this scope.")
                else:
                    rc = obj.objection_reason.value_counts()
                    fig = go.Figure(go.Bar(
                        x=rc.values, y=[r[:46] + ("…" if len(r) > 46 else "")
                                        for r in rc.index],
                        orientation="h", marker_color="#b91c1c",
                        text=rc.values, textposition="outside"))
                    fig.update_layout(height=max(180, 34 * len(rc)),
                                      margin=dict(t=6, b=6, l=6, r=40),
                                      yaxis=dict(categoryorder="total ascending"),
                                      xaxis=dict(title="Holdings"), **PLOT_BG)
                    st.plotly_chart(fig, use_container_width=True)

            # ---- relief sought: objections turned into an action list ----
            if len(obj):
                st.divider()
                st.markdown("##### What the objecting owners are asking for")
                st.caption("An objection is only half the record. Sec 15 requires "
                           "the Collector to hear it and dispose of it, so the "
                           "register carries the relief sought and the authority "
                           "it has to be referred to.")

                land_col = "affected_acres" if "affected_acres" in obj.columns \
                    else "extent_acres"
                land_req = obj[obj.relief_sought.astype(str)
                               .str.startswith("Alternative land")]

                q1, q2, q3 = st.columns(3)
                q1.markdown(kpi("Objections on record", len(obj),
                                f"{obj[land_col].sum():.2f} ac", "no"),
                            unsafe_allow_html=True)
                q2.markdown(kpi("Want land, not money", len(land_req),
                                f"{land_req[land_col].sum():.2f} ac to re-allot"),
                            unsafe_allow_html=True)
                q3.markdown(kpi("Authorities to refer to",
                                obj.referred_to.replace("", np.nan).nunique(),
                                "across the objection set"),
                            unsafe_allow_html=True)
                st.write("")

                if len(land_req):
                    st.info(f"**{len(land_req)} owner(s) want alternative land "
                            f"instead of compensation** — a Second Schedule "
                            f"entitlement, not a request the Collector can refuse "
                            f"outright. Entry 2 gives an affected family in an "
                            f"irrigation project a minimum of one acre in the "
                            f"command area. **{land_req[land_col].sum():.2f} "
                            f"acres** must be found in the State land bank.",
                            icon="🌾")

                rl, rr_ = st.columns([1.15, 1])
                with rl:
                    rc2 = obj.relief_sought.replace("", np.nan).dropna().value_counts()
                    if len(rc2):
                        fig = go.Figure(go.Bar(
                            x=rc2.values,
                            y=[r[:44] + ("…" if len(r) > 44 else "") for r in rc2.index],
                            orientation="h", marker_color="#0d2b52",
                            text=rc2.values, textposition="outside"))
                        fig.update_layout(height=max(200, 36 * len(rc2)),
                                          margin=dict(t=6, b=6, l=6, r=40),
                                          yaxis=dict(categoryorder="total ascending"),
                                          xaxis=dict(title="Holdings"), **PLOT_BG)
                        st.plotly_chart(fig, use_container_width=True)
                with rr_:
                    st.markdown("**Referred to**")
                    ref = (obj.referred_to.replace("", np.nan).dropna()
                           .value_counts())
                    for who, n_ in ref.items():
                        st.markdown(
                            f"<div class='gov-card' style='padding:10px 14px;"
                            f"margin-bottom:7px'>"
                            f"<b style='color:#0d2b52'>{n_}</b> "
                            f"<span style='font-size:12.5px'>{who}</span></div>",
                            unsafe_allow_html=True)

                with st.expander(f"Objection disposal list — {len(obj)} holdings"):
                    disp = obj[["survey_no", "owner", land_col,
                                "objection_reason", "relief_sought",
                                "referred_to"]].copy()
                    disp.columns = ["Survey No", "Owner", "Acres",
                                    "Ground (Sec 15)", "Relief sought",
                                    "Referred to"]
                    st.dataframe(disp, use_container_width=True, hide_index=True)
                    st.download_button("⬇️ Download disposal list (CSV)",
                                       disp.to_csv(index=False).encode(),
                                       "objection_disposal_list.csv", "text/csv")

            st.divider()

            # ---- three columns of names ----
            st.markdown("##### Register")
            g1, g2, g3 = st.columns(3)
            for col, state in zip((g1, g2, g3), CONSENT_STATES):
                sub = reg[reg.consent_status == state]
                style = CONSENT_STYLE[state]
                with col:
                    st.markdown(
                        f"<div style='background:{style['bg']};color:{style['colour']};"
                        f"padding:9px 14px;border-radius:10px;font-weight:700;"
                        f"text-align:center'>{style['icon']} {state} — {len(sub)}</div>",
                        unsafe_allow_html=True)
                    st.write("")
                    if len(sub) == 0:
                        st.caption("None.")
                    for _, p in sub.iterrows():
                        extra = ""
                        if state == "Objected" and p.objection_reason:
                            extra = (f"<div style='font-size:11.5px;color:#b91c1c;"
                                     f"margin-top:5px'>⛔ {p.objection_reason}</div>")
                            if str(p.get("relief_sought", "")):
                                extra += (
                                    f"<div style='font-size:11.5px;color:#0d2b52;"
                                    f"margin-top:4px;padding:5px 8px;"
                                    f"background:#eef3f9;border-radius:6px'>"
                                    f"🙏 Seeks: {p.relief_sought}</div>")
                        elif state == "Pending" and p.pending_stage:
                            extra = (f"<div style='font-size:11.5px;color:#b45309;"
                                     f"margin-top:5px'>⏳ {p.pending_stage}</div>")
                        elif state == "Consented" and p.response_date:
                            extra = (f"<div style='font-size:11.5px;color:#15803d;"
                                     f"margin-top:5px'>✅ Agreed {p.response_date}</div>")
                        st.markdown(
                            f"<div class='gov-card' style='padding:12px 14px;"
                            f"margin-bottom:9px'>"
                            f"<b>S.No {p.survey_no}</b> · {p[area_col]} ac<br>"
                            f"<span style='font-size:12.5px'>{p.owner}</span><br>"
                            f"<span style='font-size:11.5px;color:#5b7089'>"
                            f"{p.ownership_category} · {p.land_type}</span>"
                            f"{extra}</div>", unsafe_allow_html=True)

            st.divider()

            # ---- record a response ----
            st.markdown("##### Record an owner's response")
            if not can(user, P_NOTIFY):
                st.info("Your role may view the register but not record responses.")
            else:
                opts = {f"S.No {p.survey_no} · {p.owner} · {p.consent_status}":
                        p.survey_no for _, p in reg.iterrows()}
                r1, r2 = st.columns([1.4, 1])
                sel = r1.selectbox("Holding", list(opts.keys()), key="cons_sel")
                new_state = r2.selectbox("Response received", CONSENT_STATES,
                                         key="cons_state")
                reason, stage, relief, note = "", "", "", ""
                if new_state == "Objected":
                    reason = st.selectbox("Ground of objection (Sec 15)",
                                          OBJECTION_REASONS, key="cons_reason")
                    other = st.text_input("Or state another ground", key="cons_other")
                    reason = other.strip() or reason
                    relief = st.selectbox("Relief sought by the owner",
                                          RELIEF_OPTIONS, key="cons_relief")
                    if RELIEF_ESCALATION.get(relief):
                        st.caption(f"Will be referred to: "
                                   f"**{RELIEF_ESCALATION[relief]}**")
                    note = st.text_area("Officer's note (optional)",
                                        key="cons_note", height=80)
                elif new_state == "Pending":
                    stage = st.selectbox("Stage", PENDING_STAGES, key="cons_stage")

                if st.button("💾 Record response", type="primary",
                             use_container_width=True):
                    sn = opts[sel]
                    save_consent_override(sn, new_state, reason, stage,
                                          officer=user["email"],
                                          relief=relief, note=note.strip())
                    audit("CONSENT_RECORDED", user["email"],
                          f"S.No {sn} → {new_state}"
                          + (f" · {reason}" if reason else "")
                          + (f" · relief: {relief}" if relief else ""))
                    st.success(f"Survey No {sn} recorded as **{new_state}**.")
                    st.rerun()

            # ---- export ----
            out = reg[["survey_no", "owner", "ownership_category", "land_type",
                       area_col, "consent_status", "objection_reason",
                       "relief_sought", "referred_to", "pending_stage",
                       "response_date", "phone"]].copy()
            out.columns = ["Survey No", "Owner", "Category", "Land type", "Acres",
                           "Consent", "Objection reason", "Relief sought",
                           "Referred to", "Pending stage", "Response date", "Phone"]
            st.download_button("⬇️ Download consent register (CSV)",
                               out.to_csv(index=False).encode(),
                               "consent_register.csv", "text/csv")

    # ==================== RISK + SHAP ====================
    if "risk" in T:
        with T["risk"]:
            s1, s2, s3 = st.columns(3)
            s1.metric("Model MAE", f"{model.metrics['MAE']:.1f} days")
            s2.metric("R²", f"{model.metrics['R2']:.3f}")
            s3.metric("Training records", model.metrics["train_n"])
            st.caption("SHAP computed by XGBoost native TreeSHAP "
                       "(Lundberg & Lee, 2017) — exact, not approximated.")

            affected = st.session_state.affected
            if affected is None or len(affected) == 0:
                st.warning("Set an alignment on the **Alignment** tab first.")
            else:
                ptype = st.session_state.ptype or "Highway"
                rows = []
                for _, row in affected.iterrows():
                    r = model.explain(parcel_to_features(row.to_dict(), ptype))
                    rows.append({"Survey No": row.survey_no, "Owner": row.owner,
                                 "Affected (ac)": row.affected_acres,
                                 "Delay (days)": r["predicted_delay_days"],
                                 "Risk %": r["risk_score"], "Risk": r["risk_level"],
                                 "Top driver": r["top_drivers"][0]["label"]
                                 if r["top_drivers"] else "—"})
                sdf = pd.DataFrame(rows).sort_values("Delay (days)", ascending=False)
                st.session_state.scored = sdf

                st.markdown("##### Parcel-wise risk ranking")
                # Colour the risk band and shade the delay column, so the
                # table reads at a glance instead of being scanned row by row.
                _band = {"CRITICAL": ("#fdeaea", "#b3251f"),
                         "HIGH":     ("#fdf0e3", "#b4530f"),
                         "MEDIUM":   ("#fdf6dc", "#9a6209"),
                         "LOW":      ("#e7f6ec", "#146c39")}

                def _risk_cell(v):
                    bg, fg = _band.get(str(v).upper(), ("", ""))
                    return (f"background-color:{bg};color:{fg};font-weight:700"
                            if bg else "")

                st.dataframe(
                    sdf.style
                       .map(_risk_cell, subset=["Risk"])
                       .background_gradient(cmap="Blues", subset=["Delay (days)"],
                                            vmin=float(sdf["Delay (days)"].min()),
                                            vmax=float(sdf["Delay (days)"].max()) * 1.35)
                       .format({"Affected (ac)": "{:.3f}", "Delay (days)": "{:.1f}",
                                "Risk %": "{:.1f}"}),
                    use_container_width=True, hide_index=True)
                st.divider()

                pick = st.selectbox("Explain a parcel", sdf["Survey No"].tolist())
                row = affected[affected.survey_no == pick].iloc[0]
                r = model.explain(parcel_to_features(row.to_dict(), ptype))

                a, b, c = st.columns(3)
                a.metric("Predicted delay", f"{r['predicted_delay_days']:.0f} days")
                b.metric("Risk percentile", f"{r['risk_score']:.0f}%", r["risk_level"])
                c.metric("Portfolio baseline", f"{r['base_value']:.0f} days")
                st.markdown(
                    f"<div style='background:{r['risk_colour']};color:#fff;padding:12px;"
                    f"border-radius:9px;text-align:center;font-weight:700'>"
                    f"Survey No {pick} — {r['risk_level']} RISK · "
                    f"{r['predicted_delay_days']:.0f} day delay predicted</div>",
                    unsafe_allow_html=True)

                st.markdown("##### SHAP waterfall — why this prediction?")
                top = r["drivers"][:8]
                other = sum(d["shap"] for d in r["drivers"][8:])
                names = ["Baseline E[f(x)]"] + [d["label"] for d in top]
                vals = [r["base_value"]] + [d["shap"] for d in top]
                meas = ["absolute"] + ["relative"] * len(top)
                if abs(other) > .4:
                    names.append("other features"); vals.append(other); meas.append("relative")
                names.append("Prediction"); vals.append(0); meas.append("total")

                fig = go.Figure(go.Waterfall(
                    orientation="v", measure=meas, x=names, y=vals,
                    text=[f"{v:+.0f}" if mm == "relative" else f"{v:.0f}"
                          for v, mm in zip(vals, meas)],
                    textposition="outside", connector={"line": {"color": "#9fb3c8"}},
                    increasing={"marker": {"color": "#c0392b"}},
                    decreasing={"marker": {"color": "#15803d"}},
                    totals={"marker": {"color": "#0d2b52"}}))
                fig.update_layout(height=430, yaxis_title="Delay (days)",
                                  xaxis_tickangle=-38, showlegend=False,
                                  margin=dict(t=20, b=130), **PLOT_BG)
                st.plotly_chart(fig, use_container_width=True)
                st.caption("🔴 increases delay · 🟢 reduces delay · 🔵 baseline and total. "
                           "Bars sum exactly to the prediction.")

                st.markdown("##### Recommended interventions")
                for i, d in enumerate(r["top_drivers"], 1):
                    st.markdown(f"**{i}. {d['label']}** — value `{d['value']}` · "
                                f"**+{d['shap']:.0f} days**")
                    st.info(d["action"])

                with st.expander("Full SHAP attribution & additivity proof"):
                    st.dataframe(pd.DataFrame([
                        {"Feature": d["label"], "Value": d["value"],
                         "SHAP (days)": round(d["shap"], 2), "Effect": d["direction"]}
                        for d in r["drivers"]]),
                        use_container_width=True, hide_index=True)
                    st.success(f"Additivity: baseline {r['base_value']} + Σ SHAP = "
                               f"**{r['shap_sum_check']}** ≈ prediction "
                               f"**{r['predicted_delay_days']}** ✅")

                st.divider()
                st.markdown("##### Global delay drivers")
                gi = model.global_importance()
                fig = go.Figure(go.Bar(x=gi.mean_abs_shap, y=gi.label, orientation="h",
                                       marker_color="#154a8a",
                                       text=[f"{v:.1f}" for v in gi.mean_abs_shap],
                                       textposition="outside"))
                fig.update_layout(height=460, xaxis_title="Mean |SHAP| (days)",
                                  yaxis={"categoryorder": "total ascending"},
                                  margin=dict(l=10, r=60, t=10), **PLOT_BG)
                st.plotly_chart(fig, use_container_width=True)

    # ==================== NOTICES ====================
    if "notices" in T:
        with T["notices"]:
            section(st, "Statutory intimation", "Owner Notification Engine",
                    "Notice of acquisition with land particulars and a reply link")
            st.caption("Four real delivery channels with automatic fallback — if one "
                       "provider fails, the next one delivers the notice.")

            cfg = load_channels()
            ready = [c for c in cfg["order"] if channel_ready(cfg, c)]

            # status strip
            cols = st.columns(4)
            icons = {"Phone SMS": "📱", "WhatsApp": "💬",
                     "SMS": "📩", "Email": "📧"}
            for col, ch in zip(cols, CHANNELS):
                on = channel_ready(cfg, ch)
                col.markdown(
                    f"<div class='gov-card' style='padding:12px;text-align:center'>"
                    f"<div style='font-size:22px'>{icons[ch]}</div>"
                    f"<b>{ch}</b><br><small>{'🟢 Ready' if on else '⚪ Not set up'}"
                    f"</small></div>", unsafe_allow_html=True)
            st.write("")
            if ready:
                st.success("Delivery chain: " + "  →  ".join(ready))
            else:
                st.warning("No channel is set up yet. Open **⚙️ Channel Setup** below.")

            ntab = st.tabs(["Issue Notices", "Channel Setup", "Notice Log"])

            # ---------------------------------------------------- SETUP
            with ntab[1]:
                st.info("Set up at least **two** channels. On demo day the engine "
                        "falls back automatically, so one failure never stops a notice. "
                        "**Phone SMS** sends a genuine SMS from your own SIM; "
                        "**Email** is the simplest backup.")

                # ---- Phone SMS ----
                with st.expander("📱 Phone SMS — real SMS from your own SIM (free)",
                                 expanded=not channel_ready(cfg, "Phone SMS")):
                    st.markdown(
                        "1. On your Android phone install **SMS Gateway for Android** "
                        "(Play Store, or APK from github.com/capcom6/android-sms-gateway)\n"
                        "2. Open it → allow **SMS** permission → turn **Local Server** ON "
                        "→ tap **Offline** so it switches to **Online**\n"
                        "3. The app shows an **IP address**, **username** and "
                        "**password** — copy them below\n"
                        "4. Turn on the phone's **mobile hotspot** and connect this "
                        "laptop to it — now both are on the same network, "
                        "and college Wi-Fi no longer matters\n\n"
                        "Uses your SIM's SMS pack (most plans: 100 SMS/day). "
                        "Tamil works. Keep the app open during the demo.")
                    if is_hosted():
                        st.warning("This portal is running on a hosted server, so "
                                   "it cannot reach a phone on your local network. "
                                   "Use **Cloud** mode below (the app's own Cloud "
                                   "Server credentials), or run the portal on the "
                                   "officer's laptop for Local mode.")
                    ph = cfg["Phone SMS"]
                    ph["enabled"] = st.checkbox("Enable Phone SMS", ph["enabled"],
                                                key="ph_en")
                    modes = ["Local (same Wi-Fi / hotspot)", "Cloud (api.sms-gate.app)"]
                    ph["mode"] = st.radio("Connection", modes, horizontal=True,
                                          index=1 if str(ph.get("mode", "")).startswith("Cloud") else 0,
                                          key="ph_mode",
                                          help="Local needs the laptop on the phone's "
                                               "network. Cloud works over any internet "
                                               "but uses the cloud username/password "
                                               "shown in the app's Cloud section.")
                    if not ph["mode"].startswith("Cloud"):
                        ph["host"] = st.text_input("Phone IP (from the app)", ph["host"],
                                                   key="ph_host",
                                                   placeholder="192.168.43.1")
                    a_, b_ = st.columns(2)
                    ph["user"] = a_.text_input("Username", ph["user"], key="ph_user")
                    ph["password"] = b_.text_input("Password", ph["password"],
                                                   type="password", key="ph_pw")
                    ph["to"] = st.text_input("Deliver to (your number for the demo)",
                                             ph["to"], key="ph_to",
                                             placeholder="9876543210",
                                             help="Leave blank to use each owner's "
                                                  "number from the cadastral roll.")
                    if st.button("🔌 Test connection", key="ph_test",
                                 disabled=not (ph["user"] and ph["password"])):
                        ok, msg = phone_test(ph["mode"], ph.get("host", ""),
                                             ph["user"], ph["password"])
                        _show(st, ok, msg)

                # ---- WhatsApp ----
                with st.expander("💬 WhatsApp via Twilio sandbox (free trial)"):
                    st.markdown(
                        "1. twilio.com → sign up → Console → **Messaging → Try it out → "
                        "Send a WhatsApp message** → Confirm\n"
                        "2. From **your** phone, WhatsApp `join <your-code>` to "
                        "**+1 415 523 8886**\n"
                        "3. Copy **Account SID** and **Auth Token** from the Console home\n\n"
                        "⚠️ Sandbox joins expire after **3 days**. Free-form messages need "
                        "you to have messaged the sandbox in the last **24 hours** — send "
                        "`hi` to it an hour before the demo.")
                    wa = cfg["WhatsApp"]
                    wa["enabled"] = st.checkbox("Enable WhatsApp", wa["enabled"], key="wa_en")
                    wa["sid"] = st.text_input("Account SID", wa["sid"],
                                              type="password", key="wa_sid")
                    wa["token"] = st.text_input("Auth Token", wa["token"],
                                                type="password", key="wa_tok")
                    wa["to"] = st.text_input("Deliver to (your joined number)", wa["to"],
                                             key="wa_to", placeholder="9876543210",
                                             help="Leave blank to use each owner's number.")
                    if st.button("🔌 Test connection", key="wa_test",
                                 disabled=not (wa["sid"] and wa["token"])):
                        ok, msg = wa_test(wa["sid"], wa["token"])
                        _show(st, ok, msg)

                # ---- SMS ----
                with st.expander("📩 SMS via Fast2SMS (₹5 per SMS)"):
                    st.markdown(
                        "1. fast2sms.com → sign up → **Dev API** → copy the key\n"
                        "2. Add money to the wallet — Quick SMS costs **₹5 each**\n\n"
                        "⚠️ Quick-route messages can wait for **operator approval** before "
                        "delivery. Test well before the demo; keep Phone SMS as the live "
                        "channel.")
                    sm = cfg["SMS"]
                    sm["enabled"] = st.checkbox("Enable SMS", sm["enabled"], key="sm_en")
                    sm["key"] = st.text_input("Authorization key", sm["key"],
                                              type="password", key="sm_key")
                    sm["to"] = st.text_input("Deliver to (optional)", sm["to"],
                                             key="sm_to", placeholder="9876543210",
                                             help="Leave blank to use each owner's number.")
                    if st.button("🔌 Test key & balance", key="sm_test",
                                 disabled=not sm["key"]):
                        ok, msg = sms_test(sm["key"])
                        _show(st, ok, msg)

                # ---- Email ----
                with st.expander("📧 Email via Gmail (free backup)"):
                    st.markdown(
                        "1. Google Account → **Security** → turn on **2-Step Verification**\n"
                        "2. Search **App passwords** → create one → copy the 16 characters")
                    em = cfg["Email"]
                    em["enabled"] = st.checkbox("Enable Email", em["enabled"], key="em_en")
                    em["gmail"] = st.text_input("Gmail address", em["gmail"], key="em_g")
                    em["app_pw"] = st.text_input("App password", em["app_pw"],
                                                 type="password", key="em_pw")
                    em["to"] = st.text_input("Deliver to", em["to"], key="em_to",
                                             placeholder="leave blank = send to yourself")
                    if st.button("🔌 Test login", key="em_test",
                                 disabled=not (em["gmail"] and em["app_pw"])):
                        ok, msg = email_test(em["gmail"], em["app_pw"])
                        _show(st, ok, msg)

                st.divider()
                st.markdown("**Fallback order**")
                order = st.multiselect("Channels are tried in this order",
                                       CHANNELS, default=cfg["order"], key="ch_order")
                if order:
                    cfg["order"] = order + [c for c in CHANNELS if c not in order]

                s1, s2 = st.columns(2)
                if s1.button("💾 Save settings on this computer", type="primary",
                             use_container_width=True):
                    save_channels(cfg)
                    audit("CHANNELS_SAVED", user["email"],
                          ", ".join(c for c in CHANNELS if channel_ready(cfg, c)))
                    st.success("Saved. You won't need to type these again.")
                    st.rerun()
                if s2.button("🧪 Send a test message now", use_container_width=True):
                    save_channels(cfg)
                    test = (f"✅ Bhoomi Predict test message\n"
                            f"Sent by {user['name']} ({user['employee_id']})\n"
                            f"{datetime.now().strftime('%d %b %Y, %I:%M %p')}")
                    ok, attempts = dispatch(cfg, test, subject="Bhoomi Predict — test",
                                            mode="all")
                    if not attempts:
                        st.error("No channel is enabled and filled in.")
                    for ch, a_ok, info, tgt in attempts:
                        _show(st, a_ok, f"{icons[ch]} {ch} → {tgt or '—'} · {info}")

            # ---------------------------------------------------- ISSUE
            with ntab[0]:
                affected = st.session_state.affected
                if affected is None or len(affected) == 0:
                    st.warning("Set an alignment on the **Alignment** tab first.")
                elif not ready:
                    st.warning("Set up a delivery channel in **⚙️ Channel Setup** first.")
                else:
                    c1, c2 = st.columns(2)
                    project = c1.text_input("Project name", CORRIDOR["name"])
                    purpose = c2.text_input("Public purpose",
                                            "four-laning of the National Highway")
                    c3, c4 = st.columns(2)
                    deadline = c3.text_input("Response deadline",
                                             (datetime.now() + timedelta(days=30))
                                             .strftime("%d %B %Y"))
                    contact = c4.text_input("Officer contact", user.get("phone", ""))
                    c5, c6 = st.columns(2)
                    lang = c5.radio("Notice language", ["English", "தமிழ்"],
                                    horizontal=True)
                    mode_lbl = c6.radio("Delivery mode",
                                        ["Auto-fallback", "All channels"],
                                        horizontal=True,
                                        help="Auto-fallback stops at the first channel "
                                             "that succeeds.")
                    mode = "auto" if mode_lbl == "Auto-fallback" else "all"
                    with st.expander("🔗 Reply link — where the notice points"):
                        st.caption(
                            "The notice carries a link. The owner opens it on "
                            "their phone and taps CONSENT or OBJECT; the reply "
                            "lands in the Consent Register at once. For the demo, "
                            "keep the phone on this laptop's hotspot so it can "
                            "reach this address.")
                        cur = load_base_url()
                        nb = st.text_input("Portal address", cur, key="base_url")
                        bc1, bc2 = st.columns(2)
                        if bc1.button("💾 Save address", use_container_width=True):
                            save_base_url(nb)
                            st.success(f"Notices will link to {nb.rstrip('/')}")
                            st.rerun()
                        if bc2.button("🔄 Detect from this network",
                                      use_container_width=True):
                            save_base_url(f"http://{lan_ip()}:8501")
                            st.rerun()
                        st.caption(f"Example link: {response_link('43', nb)}")

                    form_lbl = st.radio(
                        "Notice form",
                        ["Full statutory notice", "Short (SMS-sized)"],
                        horizontal=True,
                        help="The full notice quotes patta/chitta, extents, "
                             "guideline value and compensation — it runs to "
                             "several SMS parts. The short form carries the "
                             "same figures in one or two.")
                    short = form_lbl.startswith("Short")

                    opts = {f"S.No {r.survey_no} · {r.owner} · {r.affected_acres} ac": r.survey_no
                            for _, r in affected.iterrows()}
                    picked = st.multiselect("Owners to notify", list(opts.keys()),
                                            default=list(opts.keys())[:1])

                    if picked:
                        s0 = affected[affected.survey_no == opts[picked[0]]].iloc[0]
                        prev = notice_text(
                            notice_particulars(s0, project, purpose, deadline, contact),
                            "tamil" if lang == "தமிழ்" else "english", short=short)
                        st.markdown("**Preview**")
                        st.code(prev, language=None)
                        seg = 70 if lang == "தமிழ்" else 160
                        parts = max(1, -(-len(prev) // seg))
                        st.caption(f"{len(prev)} characters · about {parts} SMS "
                                   f"part(s) · Chain: " + "  →  ".join(ready))

                    if st.button(f"📤 Issue {len(picked)} notice(s)", type="primary",
                                 use_container_width=True, disabled=not picked):
                        prog, rows, delivered = st.progress(0.0), [], 0
                        for i, label in enumerate(picked):
                            row = affected[affected.survey_no == opts[label]].iloc[0]
                            msg = notice_text(
                                notice_particulars(row, project, purpose,
                                                   deadline, contact),
                                "tamil" if lang == "தமிழ்" else "english",
                                short=short)
                            ok, attempts = dispatch(
                                cfg, msg, owner_phone=row.phone,
                                subject=f"Land Acquisition Notice — {project}",
                                tamil=(lang == "தமிழ்"), mode=mode)
                            delivered += int(ok)
                            path = " → ".join(f"{a[0]} {'✅' if a[1] else '❌'}"
                                              for a in attempts)
                            last = attempts[-1] if attempts else ("—", False, "no channel", "")
                            rows.append({"Survey No": row.survey_no, "Owner": row.owner,
                                         "Result": "✅ Delivered" if ok else "❌ Failed",
                                         "Path": path, "Detail": last[2]})
                            log_notice({
                                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "survey_no": row.survey_no, "owner": row.owner,
                                "status": "SENT" if ok else "FAILED", "path": path,
                                "detail": last[2],
                                "issued_by": f"{user['employee_id']} · {user['name']}"})
                            prog.progress((i + 1) / len(picked))

                        if delivered:
                            st.success(f"✅ {delivered}/{len(picked)} notices delivered.")
                            st.balloons()
                            audit("NOTICES_ISSUED", user["email"],
                                  f"{delivered}/{len(picked)} delivered")
                        if delivered < len(picked):
                            st.error(f"❌ {len(picked) - delivered} could not be "
                                     f"delivered on any channel — see Detail.")
                        st.dataframe(pd.DataFrame(rows), use_container_width=True,
                                     hide_index=True)

            # ---------------------------------------------------- LOG
            with ntab[2]:
                owner_replies = [a for a in read_audit()
                                 if a.get("action") == "OWNER_REPLY"]
                st.markdown("##### Replies received from owners")
                if owner_replies:
                    st.success(f"{len(owner_replies)} owner(s) have replied "
                               f"through the notice link.")
                    st.dataframe(pd.DataFrame(owner_replies)[
                        ["time", "actor", "detail"]].rename(columns={
                            "time": "Received", "actor": "From",
                            "detail": "Reply"}),
                        use_container_width=True, hide_index=True, height=190)
                else:
                    st.caption("No owner has replied through the link yet. "
                               "Replies appear here and in the Consent Register.")
                st.divider()
                st.markdown("##### Notices issued")
                logs = read_notices()
                if logs:
                    st.dataframe(pd.DataFrame(logs), use_container_width=True,
                                 hide_index=True, height=320)
                else:
                    st.caption("No notices issued yet.")

    # ==================== ANALYTICS ====================
    if "stats" in T:
        with T["stats"]:
            l, r_ = st.columns(2)
            with l:
                st.markdown("##### Compensation disbursement by category")
                g = parcels.groupby("ownership_category") \
                           .compensation_disbursed_pct.mean().sort_values()
                fig = px.bar(x=g.values, y=g.index, orientation="h",
                             labels={"x": "Avg disbursed %", "y": ""},
                             color=g.values, color_continuous_scale=GOV_SCALE_RG)
                fig.update_layout(height=340, coloraxis_showscale=False,
                                  margin=dict(t=8), **PLOT_BG)
                st.plotly_chart(fig, use_container_width=True)
            with r_:
                st.markdown("##### Legal disputes vs R&R progress")
                fig = px.scatter(parcels, x="rr_progress_pct", y="legal_disputes",
                                 size="extent_acres", color="ownership_category",
                                 hover_name="survey_no",
                                 labels={"rr_progress_pct": "R&R progress %",
                                         "legal_disputes": "Legal disputes"})
                fig.update_layout(height=340, margin=dict(t=8), **PLOT_BG)
                st.plotly_chart(fig, use_container_width=True)

            scored = st.session_state.scored
            if scored is not None and len(scored):
                st.divider()
                st.markdown("##### Predicted delay across affected parcels")
                fig = px.bar(scored, x="Survey No", y="Delay (days)", color="Risk",
                             color_discrete_map={"CRITICAL": "#c62828", "HIGH": "#ef6c00",
                                                 "MEDIUM": "#f9a825", "LOW": "#2e7d32"},
                             hover_data=["Owner", "Top driver"])
                fig.update_layout(height=370, margin=dict(t=8), **PLOT_BG)
                st.plotly_chart(fig, use_container_width=True)
                st.download_button("⬇️ Download risk report (CSV)",
                                   scored.to_csv(index=False).encode(),
                                   "bhoomi_risk_report.csv", "text/csv")

    # ==================== USER MANAGEMENT ====================
    if "users" in T:
        with T["users"]:
            section(st, "Access control", "Authority Accounts")
            st.caption(f"You are **L{lvl} · {user['role']}**. You may create and manage "
                       f"accounts at your own level or below.")

            users = load_users()
            sub = st.tabs(["Create Account", "Directory",
                           "Manage", "Audit Trail"])

            # ---- create ----
            with sub[0]:
                allowed = [r for r in ROLE_ORDER if AUTHORITY_ROLES[r]["level"] >= lvl]
                with st.form("create_user", clear_on_submit=False):
                    c1, c2 = st.columns(2)
                    n_name = c1.text_input("Officer name *", placeholder="Thiru. S. Kumar")
                    n_email = c2.text_input("Official email *",
                                            placeholder="officer@tn.gov.in")
                    c3, c4 = st.columns(2)
                    n_role = c3.selectbox("Authority role *", allowed)
                    n_phone = c4.text_input("Mobile", placeholder="9876543210")
                    n_office = st.text_input("Office / jurisdiction *",
                                             placeholder="Kovilpatti Taluk")

                    meta = AUTHORITY_ROLES[n_role]
                    st.info(f"**{n_role}** — Level {meta['level']} · "
                            f"{meta['jurisdiction']}  \n{meta['desc']}  \n"
                            f"Modules: {', '.join(meta['perms'])}")

                    c5, c6 = st.columns(2)
                    n_pw = c5.text_input("Initial password *", type="password")
                    n_pw2 = c6.text_input("Confirm password *", type="password")
                    force = st.checkbox("Require password change at first sign-in",
                                        value=True)
                    st.caption("Policy: 8+ characters with an uppercase letter, "
                               "a lowercase letter, a digit and a special character.")

                    if st.form_submit_button("➕ Create account", type="primary",
                                             use_container_width=True):
                        if not all([n_name, n_email, n_office, n_pw]):
                            st.error("Fill every field marked *.")
                        elif n_pw != n_pw2:
                            st.error("Passwords do not match.")
                        else:
                            ok, msg, rec = create_user(user, n_email, n_pw, n_name,
                                                       n_role, n_office, n_phone, force)
                            if ok:
                                st.success(f"✅ {msg}")
                                st.balloons()
                                st.markdown(f"""<div class='gov-card'>
                                  <b>Account issued</b><br>
                                  Employee ID: <code>{rec['employee_id']}</code><br>
                                  Email: <code>{rec['email']}</code><br>
                                  Role: {rec['role']} (Level {rec['level']})<br>
                                  <small>The officer can now sign in with either the
                                  email or the employee ID.</small></div>""",
                                            unsafe_allow_html=True)
                            else:
                                st.error(msg)

            # ---- directory ----
            with sub[1]:
                users = load_users()
                q = st.text_input("🔍 Search", placeholder="name, email, role or office")
                rows = []
                for e, u in sorted(users.items(), key=lambda x: (x[1]["level"], x[0])):
                    blob = f"{u['name']}{e}{u['role']}{u['office']}".lower()
                    if q and q.lower() not in blob:
                        continue
                    rows.append({"ID": u["employee_id"], "Name": u["name"],
                                 "Email": e, "Role": u["role"], "L": u["level"],
                                 "Office": u["office"], "Phone": u["phone"],
                                 "Status": "Active" if u["active"] else "Disabled",
                                 "Logins": u.get("login_count", 0),
                                 "Created by": u["created_by"]})
                st.dataframe(pd.DataFrame(rows), use_container_width=True,
                             hide_index=True, height=360)
                st.caption(f"{len(rows)} account(s). "
                           "Passwords are stored only as PBKDF2 hashes.")

            # ---- manage ----
            with sub[2]:
                users = load_users()
                manageable = {f"{u['employee_id']} · {u['name']} ({u['role']})": e
                              for e, u in users.items()
                              if AUTHORITY_ROLES[u["role"]]["level"] >= lvl
                              and e != user["email"]}
                if not manageable:
                    st.info("No accounts at or below your authority level to manage.")
                else:
                    sel = st.selectbox("Select account", list(manageable.keys()))
                    tgt = users[manageable[sel]]

                    st.markdown(f"<div class='gov-card'><b>{tgt['name']}</b> · "
                                f"<code>{tgt['employee_id']}</code><br>{tgt['email']}<br>"
                                f"<span class='gov-badge lv{tgt['level']}'>"
                                f"L{tgt['level']} · {tgt['role']}</span> "
                                f"{'🟢 Active' if tgt['active'] else '🔴 Disabled'}<br>"
                                f"<small>Created {tgt['created_at']} by "
                                f"{tgt['created_by']} · {tgt.get('login_count',0)} "
                                f"sign-ins</small></div>", unsafe_allow_html=True)
                    st.write("")

                    e1, e2 = st.columns(2)
                    with e1:
                        st.markdown("**Edit details**")
                        u_name = st.text_input("Name", tgt["name"], key="u_name")
                        u_office = st.text_input("Office", tgt["office"], key="u_office")
                        u_phone = st.text_input("Phone", tgt["phone"], key="u_phone")
                        opts_r = [r for r in ROLE_ORDER
                                  if AUTHORITY_ROLES[r]["level"] >= lvl]
                        u_role = st.selectbox("Role", opts_r,
                                              index=opts_r.index(tgt["role"])
                                              if tgt["role"] in opts_r else 0)
                        if st.button("💾 Save changes", use_container_width=True):
                            ok, msg = update_user(user, tgt["email"], u_name,
                                                  u_office, u_phone, u_role)
                            _show(st, ok, msg)
                            if ok:
                                st.rerun()

                    with e2:
                        st.markdown("**Reset password**")
                        r_pw = st.text_input("New password", type="password", key="r_pw")
                        if st.button("🔑 Reset password", use_container_width=True):
                            ok, msg = admin_reset_password(user, tgt["email"], r_pw)
                            _show(st, ok, msg)

                        st.markdown("**Account status**")
                        if tgt["active"]:
                            if st.button("⏸️ Deactivate", use_container_width=True):
                                ok, msg = set_user_active(user, tgt["email"], False)
                                _show(st, ok, msg)
                                if ok:
                                    st.rerun()
                        else:
                            if st.button("▶️ Reactivate", use_container_width=True):
                                ok, msg = set_user_active(user, tgt["email"], True)
                                _show(st, ok, msg)
                                if ok:
                                    st.rerun()

                        st.markdown("**Remove account**")
                        sure = st.checkbox("I confirm permanent removal")
                        if st.button("🗑️ Delete account", disabled=not sure,
                                     use_container_width=True):
                            ok, msg = delete_user(user, tgt["email"])
                            _show(st, ok, msg)
                            if ok:
                                st.rerun()

            # ---- audit ----
            with sub[3]:
                logs = read_audit()
                if not logs:
                    st.caption("No audit entries yet.")
                else:
                    st.dataframe(pd.DataFrame(logs), use_container_width=True,
                                 hide_index=True, height=420)
                    st.caption(f"{len(logs)} entries · sign-ins, account changes and "
                               "notices are all recorded (PS 26016 · audit trails).")

    # ==================== MY ACCOUNT ====================
    with T["me"]:
        section(st, "Signed in", "My Account")
        c1, c2 = st.columns([1, 1])
        with c1:
            st.markdown(f"""<div class='gov-card'>
              <b>{user['name']}</b><br>
              Employee ID: <code>{user['employee_id']}</code><br>
              Email: <code>{user['email']}</code><br>
              <span class='gov-badge lv{lvl}'>L{lvl} · {user['role']}</span><br><br>
              Office: {user['office']}<br>
              Jurisdiction: {user['jurisdiction']}<br>
              Phone: {user['phone']}<br>
              <small>Account created {user['created_at']} by {user['created_by']}<br>
              {user.get('login_count',0)} sign-ins · last {user.get('last_login','—')}
              </small></div>""", unsafe_allow_html=True)
            st.write("")
            st.markdown("**Modules available to you**")
            for p in user["perms"]:
                st.markdown(f"- {p}")

        with c2:
            st.markdown("**Change my password**")
            with st.form("chpw"):
                old = st.text_input("Current password", type="password")
                new = st.text_input("New password", type="password")
                cfm = st.text_input("Confirm new password", type="password")
                st.caption("8+ characters with an uppercase letter, a lowercase "
                           "letter, a digit and a special character.")
                if st.form_submit_button("🔑 Update password", type="primary",
                                         use_container_width=True):
                    ok, msg = change_own_password(user["email"], old, new, cfm)
                    if ok:
                        st.success(msg + " Please sign in again.")
                        st.session_state.user = None
                        st.rerun()
                    else:
                        st.error(msg)


# ============================================================
# ENTRY POINT
# ============================================================

ensure_theme_config()


def _under_streamlit():
    try:
        from streamlit.runtime import exists
        return exists()
    except Exception:
        return False


if _under_streamlit():
    streamlit_app()
elif __name__ == "__main__":
    console_test()
