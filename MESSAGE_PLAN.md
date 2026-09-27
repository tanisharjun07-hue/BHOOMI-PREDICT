# 📱 MESSAGE SYSTEM — Setup & Demo Checklist

**4 channel, automatic fallback.** Onnu fail aana adutha channel thaanaave deliver pannum.

```
📱 Phone SMS  →  💬 WhatsApp  →  📩 Fast2SMS  →  📧 Email
   (main)                                         (backup)
```

| Channel | Cost | Speed | Demo risk |
|---|---|---|---|
| 📱 **Phone SMS** | **Free** (unga SIM pack) | Instant | **Kammi** — real SMS, approval illa |
| 💬 WhatsApp | Free trial | Instant | Nadutharam — 3 naal expiry, 24h window |
| 📩 Fast2SMS | **₹5 / SMS** | Operator approval | **Athigam** — kaathirukkalaam |
| 📧 Email | Free | Instant | Kammi — aana phone notification medhu |

**Kandippa rendu channel setup pannunga: Phone SMS + Email.**

---

## 1️⃣ Phone SMS — main channel (10 nimisham)

**Phone-la:**
1. Play Store → **SMS Gateway for Android** install
   (kidaikkalaina: github.com/capcom6/android-sms-gateway → Releases → APK)
2. Open → **SMS permission Allow**
3. **Local Server** switch → ON
4. Keezha **Offline** button tap → **Online** aaganum
5. **Username** + **Password** screen-la therium → ezhudhikonga
6. Phone Settings → Apps → SMS Gateway → Battery → **Unrestricted**

**Laptop-la:**
7. Phone-la **Mobile Hotspot ON**
8. Laptop Wi-Fi → andha hotspot-la connect
9. `Win + R` → `cmd` → `ipconfig` → **Wireless LAN adapter Wi-Fi** keezha
   **Default Gateway** = phone IP (`192.168.43.1` maadhiri)

**Portal-la:**
10. Notices → **⚙️ Channel Setup** → **📱 Phone SMS**
    - Enable ✅ · Connection **Local** · IP, Username, Password
    - Deliver to: **team member number** (unga sondha number vendaam)
11. **🔌 Test connection** → pacha varanum
12. **💾 Save** → **🧪 Send a test message**

✅ Team member phone-la SMS vandhaa ready.

**Cloud mode:** Hotspot/IP velai seiyalana, app-oda **Cloud Server** section-la
thani username/password irukkum. Portal-la Connection = **Cloud** select panni
adha podunga — appo phone-la internet irundhaa podhum.

---

## 2️⃣ Email — backup (5 nimisham)

1. myaccount.google.com → **Security** → **2-Step Verification** ON
2. myaccount.google.com/apppasswords → App name `Bhoomi Portal` → **Create**
3. 16 ezhuthu code copy
4. Portal → **📧 Email** → Gmail + App password → **🔌 Test login** → **💾 Save**

⚠️ Gmail login password velai seiyaadhu. **App Password** dhaan.

---

## 📍 Demo naal checklist

**Munnadi naal:**
- [ ] Phone SMS test message vandhadhu
- [ ] Email test message vandhadhu
- [ ] Battery → Unrestricted podhaachu
- [ ] **Screen recording** — Issue notice → phone-la SMS varradhu
      (network muzhusa poonaa idha kaattalaam)

**Demo-ku 1 mani neram munnadi:**
- [ ] Phone hotspot ON → SMS Gateway app **Online**
- [ ] Laptop hotspot-la connect
- [ ] Channel Setup → **🧪 Send a test message** → varudhaa paarunga
- [ ] Phone charge full, Gateway app open

**Demo-la:**
1. Alignment → slider nagathunga → parcels sivappa maarum
2. Consent → yaaru kudukkuranga, yaaru maattanga, en-nu kaatunga
3. Notices → owner select → Tamil → **Issue notice**
4. **Team member phone-a judge-kitta kaatunga** — Tamil SMS live-a varum 🎯
5. Result table → **Path** column: `Phone SMS ✅`
   *"Oru channel fail aana adutha channel thaanaave deliver pannum"*

---

## ⚠️ College Wi-Fi

College network pala site-a block pannum. Error ippadi vandhaa:

> *Got a web page instead of an API reply — this network is probably blocking the site.*

→ **Udane mobile hotspot-ku maarunga.** Phone SMS-ku hotspot dhaan anyway
thevai, so adhu indha problem-a thaandidum.

---

## Error vandhaa

| App-la varra message | Seiya vendiyadhu |
|---|---|
| *Cannot reach the phone…* | App **Online**-a? Laptop hotspot-la? IP sari-a (`ipconfig`)? |
| *Phone rejected the username/password* | App screen-la irukkuradha thirumba copy |
| *Gmail rejected the login* | App Password (16 char) use pannunga |
| *No recipient number* | Channel Setup-la "Deliver to" fill pannunga |

---

## Judge kelvigal

**"Idhu unmaiyaana SMS-a?"**
> Aama. Officer phone-oda SIM-la irundhu telecom network vazhiyaa poguthu.
> Production-la NIC SMS Gateway alladhu DLT-registered sender use pannuvom —
> code-la oru channel maathinaa podhum.

**"Owner-ku neradiyaa pogumaa?"**
> Production-la ovvoru owner-oda registered number-ku — cadastral roll-la
> phone number irukku. Demo-kaaga officer phone-ku route panrom, real
> owners-ku test notice anuppa koodaadhu.

**"Oru channel down aanaa?"**
> Auto-fallback. Path column-la entha channel try aachu, edhu deliver
> pannuchu-nu audit trail-la record aagum.

---

## Files (thaanaa uruvaagum — delete pannadheenga)

`bhoomi_channels.json` (API keys — GitHub-la push pannadheenga) ·
`bhoomi_notice_log.json` · `bhoomi_users.json` · `bhoomi_audit.json` ·
`bhoomi_consent.json`
