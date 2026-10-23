# Signing & notarizing DiscKit.app

Right now DiscKit builds **unsigned**: macOS asks you to approve it once (right-click → Open, or on
macOS 15+ System Settings → Privacy & Security → Open Anyway). The GitHub build is already set up for
signing. When the five secrets below are in your GitHub repo, the next build will automatically:

1. sign every part of the app with your **Developer ID Application** certificate (hardened runtime),
2. send it to Apple's notary service and wait for approval,
3. *staple* Apple's approval ticket into the app and the .dmg, so it opens with a plain double-click,
   **even on a Mac with no internet** (important for an offline archive).

If any secret is missing, the build still succeeds and produces `DiscKit-…-unsigned.dmg`.

You need an **Apple Developer Program** membership ($99/year): <https://developer.apple.com/programs/enroll/>.
Enrolling as an individual usually takes a day or two.

---

## Step 1 – Create the Developer ID Application certificate (on your Mac)
1. Open **Keychain Access** → menu *Keychain Access* → *Certificate Assistant* →
   **Request a Certificate From a Certificate Authority…**
   Enter your email and name, choose **Saved to disk**, and save `CertificateSigningRequest.certSigningRequest`.
2. Go to <https://developer.apple.com/account/resources/certificates/add>, choose
   **Developer ID Application** (choose the *G2 Sub-CA* option if asked) → Continue → upload the request file
   → Download `developerID_application.cer`.
3. Double-click the downloaded `.cer` to add it to Keychain Access (login keychain).
4. In Keychain Access → *My Certificates*, find **Developer ID Application: Your Name (TEAMID)**, expand it
   so the private key shows, select **both** the certificate and its key → right-click → **Export 2 items…** →
   save as `DiscKit.p12` and choose a strong export password. Keep that password.
5. Turn the file into text for GitHub (in Terminal):
   ```
   base64 -i ~/Desktop/DiscKit.p12 | pbcopy
   ```
   That's your `MACOS_CERT_P12_BASE64`. The export password is `MACOS_CERT_PASSWORD`.

## Step 2 – Create an App Store Connect API key (used to request notarization)
1. Go to <https://appstoreconnect.apple.com/access/integrations/api> (*Users and Access → Integrations →
   App Store Connect API*). If asked, request access first. Only the Account Holder can do this.
2. Under **Team Keys** press **+**, name it `DiscKit notarization`, Access: **Developer** → Generate.
3. Note the **Issuer ID** (shown above the table) → `ASC_API_ISSUER_ID`.
4. Note the key's **Key ID** → `ASC_API_KEY_ID`.
5. Press **Download API Key**. You get `AuthKey_XXXXXXXXXX.p8`, and **it can only be downloaded once**.
   Turn it into text:
   ```
   base64 -i ~/Downloads/AuthKey_XXXXXXXXXX.p8 | pbcopy
   ```
   That's `ASC_API_KEY_P8_BASE64`.

## Step 3 – Add the five secrets to GitHub
Your repo on github.com → **Settings → Secrets and variables → Actions → New repository secret**:

| Name | Value |
|---|---|
| `MACOS_CERT_P12_BASE64` | base64 text of `DiscKit.p12` |
| `MACOS_CERT_PASSWORD` | the .p12 export password |
| `ASC_API_KEY_P8_BASE64` | base64 text of `AuthKey_….p8` |
| `ASC_API_KEY_ID` | Key ID, e.g. `2X9R4HXF34` |
| `ASC_API_ISSUER_ID` | Issuer ID (a UUID) |

These live only in GitHub's encrypted secrets. They are never stored in the app, the repo files, or the .dmg.

## Step 4 – Build
GitHub → **Actions → Build DiscKit.app (macOS) → Run workflow** (or push a change / a `disckit-v*` tag).
Approval by Apple usually takes 2–15 minutes. In the run's log look for `status: Accepted`,
`The staple and validate action worked!` and `source=Notarized Developer ID`.
Download the **DiscKit-macOS-arm64** artifact. The file name has no `-unsigned` suffix.

## Check it on your Mac
```
spctl --assess --type execute -vv /Applications/DiscKit.app   # → accepted, source=Notarized Developer ID
xcrun stapler validate /Applications/DiscKit.app              # → The validate action worked!
```

## Troubleshooting
- **"No 'Developer ID Application' certificate found"**: the .p12 was exported without its private key, or
  it's an *Apple Development* / *Mac App Distribution* certificate. Export again (Step 1.4).
- **Notarization "Invalid"**: the run prints Apple's log. The usual causes are an unsigned binary inside the app
  (the script signs all of them) or a revoked or expired certificate.
- **401 / authentication errors**: re-check the Key ID and Issuer ID, and that the `.p8` text was copied whole.
- Certificates last 5 years. Rotate the secrets when you renew.
