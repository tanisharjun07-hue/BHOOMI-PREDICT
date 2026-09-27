# 🌐 Website-ஐ Online-ல Deploy பண்றது

**Streamlit Community Cloud** — இலவசம், GitHub-ல இருந்து தானா deploy ஆகும்.
மொத்தம் 20 நிமிஷம்.

முடிஞ்சதும் உங்க website:
```
https://bhoomi-predict.streamlit.app
```

---

## ஏன் deploy பண்ணணும்

**Reply link வேலை செய்யும் இடம் மாறுது.** இப்போ link உங்க laptop-ஐ
சுட்டுது (`http://192.168.x.x:8501`) — அதனால owner-ஓட phone உங்க hotspot-ல
இருக்கணும்.

Deploy பண்ணா link public ஆகும் → **judge-ஓட phone எங்க இருந்தாலும் வேலை
செய்யும்.** Hotspot வேணாம், WiFi வேணாம்.

---

## ⚠️ முதல்ல தெரிஞ்சுக்கணும்

**1. Phone SMS (Local mode) cloud-ல வேலை செய்யாது.**
Cloud server உங்க phone-ஐ LAN-ல reach பண்ண முடியாது. ரெண்டு வழி:
- App-ல **Cloud mode** use பண்ணுங்க (SMS Gateway app-ல தனி credentials இருக்கு)
- அல்லது **Email** channel — அது cloud-ல நல்லா வேலை செய்யும்

**2. Data permanent இல்ல.**
App restart ஆனா accounts, consent replies, audit trail எல்லாம் reset ஆகும்.
Demo-க்கு அது பரவாயில்ல. Judge கேட்டா:

> "Hosted demo-ல storage ephemeral. Permanent installation-ல PostgreSQL
> use பண்ணுவோம் — schema ஏற்கனவே normalised, driver மட்டும் மாறும்."

**3. API keys-ஐ GitHub-ல போடாதீங்க.**
`.gitignore` ஏற்கனவே சரியா set பண்ணியிருக்கு. `bhoomi_channels.json`-ல
Twilio/Gmail credentials இருக்கு — அது commit ஆகாது.

---

## Step 1 — GitHub account

github.com → **Sign up** (email + password)

ஏற்கனவே account இருந்தா இந்த step தேவையில்ல.

---

## Step 2 — Repository உருவாக்குங்க

1. GitHub-ல மேல வலது மூலையில **`+`** → **New repository**
2. Repository name: `bhoomi-predict`
3. **Public** தேர்ந்தெடுங்க (Streamlit free tier-க்கு public வேணும்)
4. **Create repository**

---

## Step 3 — File upload பண்ணுங்க

புது repo page-ல **"uploading an existing file"** link-ஐ click பண்ணுங்க.

`deploy` folder-ல இருந்து இந்த **நாலு** file-ஐயும் இழுத்து போடுங்க:

```
bhoomi_portal.py
requirements.txt
.gitignore
.streamlit/config.toml
```

⚠️ **`.streamlit` folder** — browser-ல drag பண்ணும்போது folder structure
காப்பாத்தப்படும். சரியா ஏறலைன்னா, repo-ல `.streamlit/config.toml`
ன்னு file path கொடுத்து manual-ஆ create பண்ணுங்க.

கீழ **Commit changes** அழுத்துங்க.

---

## Step 4 — Streamlit Cloud

1. **share.streamlit.io** → **Sign in with GitHub**
2. **Create app** → **Deploy a public app from GitHub**
3. நிரப்புங்க:
   - Repository: `உங்கusername/bhoomi-predict`
   - Branch: `main`
   - Main file path: `bhoomi_portal.py`
   - App URL: `bhoomi-predict` (இது தான் உங்க address ஆகும்)
4. **Deploy**

3-5 நிமிஷம் ஆகும். Package install ஆகும் log தெரியும்.

---

## Step 5 — Reply link-ஐ சரி பண்ணுங்க ⭐

**இது மறக்காதீங்க.** இது இல்லாம reply link வேலை செய்யாது.

1. App-ஓட **Settings** (⚙️ icon) → **Secrets**
2. இதை paste பண்ணுங்க — URL-ஐ உங்கதா மாத்திக்கோங்க:

```toml
BHOOMI_BASE_URL = "https://bhoomi-predict.streamlit.app"
```

3. **Save** → app தானா restart ஆகும்

---

## Step 6 — Test

1. App URL-ஐ திறங்க
2. Login: `collector.ttn@tn.gov.in` / `Collector@2026`
3. **Alignment** tab → slider நகர்த்துங்க → map வேலை செய்யுதா
4. **Notices** → Channel Setup → **🔗 Reply link** expander திறங்க
   → address `https://...streamlit.app` ன்னு இருக்கணும், `192.168...` இல்ல
5. Preview-ல link-ஐ **phone-ல திறந்து** பாருங்க → response page வரணும்

---

## Step 7 — Message channel

Cloud-ல **Email** தான் எளிது:

Channel Setup → **📧 Email** → Gmail + App password → Test → Save

Phone SMS வேணும்ன்னா, SMS Gateway app-ல **Cloud Server** section-ல
credentials இருக்கும் — portal-ல Connection = **Cloud** select பண்ணி
அதை போடுங்க.

---

## 🎤 Demo-ல இது எப்படி உதவும்

**முன்ன:** "judge phone-ஐ என் hotspot-ல connect பண்ணுங்க"
**இப்போ:** "இந்த link-ஐ உங்க phone-ல திறங்க"

Judge-ஓட mobile data-லயே வேலை செய்யும். Network risk இல்ல.

**சொல்ல ஒரு வரி:**
> "Portal cloud-ல deploy ஆகியிருக்கு. Notice-ல இருக்கற link எந்த
> phone-லயும் வேலை செய்யும் — owner எங்க இருந்தாலும் consent பதிவு
> பண்ணலாம்."

---

## பிரச்சனை வந்தா

| Log-ல வர்ற error | செய்ய வேண்டியது |
|---|---|
| `ModuleNotFoundError` | `requirements.txt` upload ஆகலை — repo-ல இருக்கான்னு பாருங்க |
| `Error installing requirements` | Log-ல எந்த package-ன்னு பாருங்க, version constraint தளர்த்துங்க |
| App theme கருப்பா இருக்கு | `.streamlit/config.toml` repo-ல இல்ல |
| Reply link `192.168...` ஆ இருக்கு | Step 5 பண்ணல — Secrets-ல `BHOOMI_BASE_URL` போடுங்க |
| `Oh no. Error running app` | Manage app → logs → கீழ scroll → traceback படிங்க |

Error வந்தா அந்த log-ஐ copy பண்ணி எனக்கு அனுப்புங்க.

---

## Backup plan

Cloud-ல ஏதாவது தப்பா போனா, **laptop version அப்படியே இருக்கு**.
`RUN.bat` double-click பண்ணா local-ஆ ஓடும். ரெண்டையும் ready-ஆ
வச்சுக்கோங்க — cloud primary, laptop backup.
