# 🏛️ Bhoomi Predict

**NH-44 Madurai–Tirunelveli Four-Laning · SIH 2026 · PS 26017**

---

## 🌐 Online-ல host பண்ண

**`DEPLOY_GUIDE.md`** படிங்க — முழு steps அதுல இருக்கு.

சுருக்கமா:

1. GitHub-ல `bhoomi-predict` ன்னு **Public** repo உருவாக்குங்க
2. இந்த **நாலு** file-ஐயும் upload பண்ணுங்க:
   ```
   bhoomi_portal.py
   requirements.txt
   .gitignore
   .streamlit/config.toml
   ```
3. **share.streamlit.io** → Deploy → main file `bhoomi_portal.py`
4. ⚠️ **Settings → Secrets**-ல இதை போடுங்க (இல்லாம reply link வேலை செய்யாது):
   ```toml
   BHOOMI_BASE_URL = "https://உங்க-app-name.streamlit.app"
   ```

---

## 💻 Laptop-ல ஓட்ட (backup)

**`RUN.bat`** double-click பண்ணுங்க. Package install பண்ணி, self-test ஓட்டி,
browser-ல திறக்கும்.

---

## 🔐 Login

| Email | Password | Role |
|---|---|---|
| `collector.ttn@tn.gov.in` | `Collector@2026` | District Collector (முழு access) |
| `ministry@morth.gov.in` | `Ministry@2026` | Central Ministry |
| `nodal@tn.gov.in` | `Nodal@2026` | State Nodal Officer |
| `lao.kovilpatti@tn.gov.in` | `Officer@2026` | Land Acquisition Officer |
| `rr.kovilpatti@tn.gov.in` | `Rehab@2026` | Rehabilitation Officer |
| `pd.nhai@nhai.gov.in` | `Agency@2026` | Project Implementing Agency |
| `vao.village@tn.gov.in` | `Field@2026` | Field Verification Officer |
| `analyst@nic.in` | `Analyst@2026` | Policy Analyst |

Email-லயும் Employee ID-லயும் (BP0001…) login பண்ணலாம்.

---

## 📑 Tabs

Dashboard · Alignment · **Consent** · Risk + SHAP · Notices · Analytics · Users

---

## 📱 Message channels

`MESSAGE_PLAN.md` பாருங்க.

```
Phone SMS  →  WhatsApp  →  Fast2SMS  →  Email
```

⚠️ Cloud-ல **Phone SMS (Local mode) வேலை செய்யாது** — server உங்க phone-ஐ
LAN-ல reach பண்ண முடியாது. **Email** use பண்ணுங்க, அல்லது SMS Gateway
app-ஓட **Cloud mode**.

---

## ⚠️ முக்கியம்

**API keys-ஐ GitHub-ல போடாதீங்க.** `.gitignore` சரியா set பண்ணியிருக்கு —
`bhoomi_channels.json`-ல Twilio/Gmail credentials இருக்கு, அது commit ஆகாது.

**Cloud-ல data permanent இல்ல.** App restart ஆனா accounts, consent replies,
audit trail reset ஆகும். Demo-க்கு பரவாயில்ல. Judge கேட்டா —
*"Permanent installation-ல PostgreSQL. Schema ஏற்கனவே normalised."*

---

## தானா உருவாகும் files (delete பண்ணாதீங்க)

`bhoomi_users.json` · `bhoomi_audit.json` · `bhoomi_consent.json` ·
`bhoomi_channels.json` · `bhoomi_notice_log.json` · `bhoomi_link.json`
