# Phase 7 — Mobile packaging (Capacitor → iOS + Android)

> **Effort:** M  ·  **Depends on:** Phase 4 (React web app — Capacitor wraps the web build) and Phase 6 (prod API + web deployed, so native builds point at real prod)  ·  **Unlocks:** Phase 8 (compliance & store readiness) and Phase 9 (launch)
> **Context:** what shipped in phases 0–6 (incl. the React web app this wraps) is recorded in [`../../CHANGELOG.md`](../../CHANGELOG.md).
> The per-PR quality gate applies to EVERY task below: each lands via a PR that is 100% green + ≥80% coverage (backend & frontend) + Playwright E2E. A task is not done until its tests keep coverage ≥80%.

**Goal:** signed iOS and Android builds install and run the full Generate→Review→Discover loop against prod — with OAuth completing inside the native webview, a daily review reminder firing on-device, and OTA web-bundle updates reaching a test channel without a store cycle.

**Status legend:** [ ] todo · [~] in progress · [x] done · [!] blocked

---

## 7.1 — Paid store accounts & identities (start early)  ·  S

_Context: this is the phase where money is spent. Apple identity verification can take days, so kick these off before any code. `com.lengua.app` is the decided bundle id; confirm availability at enrollment._

- [ ] **7.1.1** Kotlar enrolls in the **Apple Developer Program** ($99/yr) at developer.apple.com/programs/enroll/ and completes identity verification.
      verify: the Apple Developer account shows an **active** membership with a visible **Team ID**; a screenshot of the active membership status is attached to the PR/tracker.
- [ ] **7.1.2** Kotlar creates a **Google Play Console** account ($25 one-time) at play.google.com/console.
      verify: the Play Console developer account is active and can reach **Create app**; a screenshot of the account home is attached.
- [ ] **7.1.3** Kotlar invites **Ben Artzi as Admin** on the Apple Developer account; Ben accepts the invite.
      verify: Ben can sign in to App Store Connect and see the Lengua team with the Admin role under **Users and Access**.
      depends: 7.1.1
- [ ] **7.1.4** Kotlar invites **Ben Artzi as Release Manager** on Play Console; Ben accepts.
      verify: Ben can open the Play Console for the developer account and his role shows **Release Manager** under **Users and permissions**.
      depends: 7.1.2
- [ ] **7.1.5** Ben installs the local native toolchains: **Xcode** (Mac, with command-line tools) and **Android Studio** (with an SDK + emulator).
      verify: `xcodebuild -version` and `xcrun simctl list devices` succeed on the Mac, and Android Studio launches with at least one configured SDK + AVD (`sdkmanager --list` succeeds).
- [ ] **7.1.6** Confirm the bundle/app id **`com.lengua.app`** is available and reserve it on both stores (App Store Connect app record + a Play Console app draft).
      verify: an App Store Connect app exists with bundle id `com.lengua.app` and a Play Console app draft uses the same applicationId; neither store reports the id as taken.
      depends: 7.1.3, 7.1.4

## 7.2 — Sign in with Apple key & CI signing secrets  ·  S

_Context: Apple Sign In is mandatory on iOS because Google is offered. The `.p8` key must be created once, downloaded immediately (Apple won't let you re-download), and shared securely. These four GitHub Actions secrets are referenced by later signing/CI tasks._

- [ ] **7.2.1** Create the **Sign in with Apple** key in the Apple Developer portal, download the **`.p8`** private key, and record its **Key ID**; send the `.p8` to Ben over a secure channel (not email/chat plaintext).
      verify: the `.p8` file is held in a secret manager (not committed — `git grep -i "BEGIN PRIVATE KEY"` over the repo returns nothing), and its Key ID matches the key listed under **Keys** in the Apple portal.
      depends: 7.1.1
- [ ] **7.2.2** Set GitHub Actions secrets **`APPLE_TEAM_ID`** and **`APP_BUNDLE_ID`** (`com.lengua.app`).
      verify: `gh secret list` shows both `APPLE_TEAM_ID` and `APP_BUNDLE_ID`; a tiny CI job echoes that each is non-empty (without printing the value).
      depends: 7.1.1, 7.1.6
- [ ] **7.2.3** Set GitHub Actions secrets **`APPLE_SIGN_IN_KEY_ID`** and **`APPLE_SIGN_IN_PRIVATE_KEY`** (the `.p8` contents).
      verify: `gh secret list` shows both secrets; a CI job loads `APPLE_SIGN_IN_PRIVATE_KEY` and confirms it parses as a PKCS#8 EC key (`openssl pkcs8 -nocrypt -in <key>` returns success) without echoing the key.
      depends: 7.2.1

## 7.3 — Capacitor integration & native projects  ·  M

_Context: Capacitor wraps the existing Vite web build; native `ios/` and `android/` projects are generated inside `apps/web`. This is the foundation every later group builds on._

- [ ] **7.3.1** Add `@capacitor/core` + `@capacitor/cli` to `apps/web`, run `cap init` with app id `com.lengua.app` and name "Lengua", and commit `capacitor.config.ts` with `webDir` pointed at the Vite build output.
      verify: `cd apps/web && pnpm cap --version` prints a version and `capacitor.config.ts` shows `appId: 'com.lengua.app'`, `appName: 'Lengua'`, and the correct `webDir`.
- [ ] **7.3.2** Generate the iOS project (`pnpm cap add ios`), committing `apps/web/ios/`.
      verify: `apps/web/ios/App/App.xcodeproj` exists and `cd apps/web && pnpm cap sync ios` completes without error.
      depends: 7.3.1
- [ ] **7.3.3** Generate the Android project (`pnpm cap add android`), committing `apps/web/android/`.
      verify: `apps/web/android/` contains a Gradle project and `cd apps/web && pnpm cap sync android` completes without error.
      depends: 7.3.1
- [ ] **7.3.4** Add a repeatable build script (e.g. `pnpm mobile:sync` = `vite build` → `cap copy` → `cap sync`) and wire a CI job that runs it to catch web↔native drift.
      verify: `pnpm mobile:sync` exits 0 from a clean checkout and the CI job is green; deleting a synced web asset and re-running reproduces it.
      depends: 7.3.2, 7.3.3

## 7.4 — Native app configuration (identity, assets, env)  ·  M

_Context: app metadata, icons/splash, status bar, deep-link scheme, permissions, and pointing the production build at the prod API. Region/data flow stay EU-aligned per the locked decisions._

- [ ] **7.4.1** Set the native display name, version, and build number on both platforms (iOS `CFBundleDisplayName`/`CFBundleShortVersionString`/`CFBundleVersion`; Android `applicationId`/`versionName`/`versionCode`).
      verify: a debug build on each platform installs showing the name "Lengua"; `agvtool what-marketing-version` (iOS) and the `android/app/build.gradle` `versionName` agree with the package version.
- [ ] **7.4.2** Generate and install **app icons** (all required iOS + Android adaptive sizes) from a single source asset via `@capacitor/assets`.
      verify: `pnpm cap assets` (or `npx @capacitor/assets generate`) produces the icon sets, and a build on each platform shows the Lengua icon on the home screen (no default Capacitor placeholder).
      depends: 7.3.2, 7.3.3
- [ ] **7.4.3** Generate and configure **splash screens** for both platforms and add `@capacitor/splash-screen` with a controlled hide-on-ready.
      verify: launching a build on each platform shows the Lengua splash then the app; `pnpm cap assets` output includes splash assets and no default splash appears.
      depends: 7.4.2
- [ ] **7.4.4** Configure the **status bar** (`@capacitor/status-bar`): style/background that matches the theme and does not overlap content (respect safe areas).
      verify: on a real device the status bar text is legible against the app header and content is not clipped under the notch/status bar on both a notched iOS device and an Android device.
- [ ] **7.4.5** Point production native builds at the **prod API base URL** via a build-time env, distinct from local/staging, with **no localhost** baked into release builds.
      verify: a release-config build's bundled config resolves `VITE_API_BASE_URL` to the prod Cloud Run URL (asserted by a test that greps the built bundle); a debug build still targets staging/local.
      depends: Phase 6 prod API deploy
- [ ] **7.4.6** Declare the minimum native **permissions** required for v1 (notifications) in `Info.plist` and `AndroidManifest.xml`, and confirm no unused permissions are requested.
      verify: a static check of `Info.plist`/`AndroidManifest.xml` lists only the notification (and any strictly required) permissions; the Android manifest merger report shows no extra dangerous permissions.

## 7.5 — Deep links & custom URL scheme  ·  S

_Context: the deep-link scheme is needed for OAuth redirect handling (7.7) and any future link-into-app. Use the `App` plugin to receive the inbound URL._

- [ ] **7.5.1** Register a custom URL scheme (e.g. `com.lengua.app://` / `lengua://`) on iOS (`CFBundleURLTypes`) and Android (intent filter), matching `capacitor.config.ts`.
      verify: opening `lengua://test` from Safari (iOS) and `adb shell am start -a android.intent.action.VIEW -d "lengua://test"` (Android) launches the app instead of erroring.
      depends: 7.3.2, 7.3.3
- [ ] **7.5.2** Handle the inbound deep link via the `@capacitor/app` `appUrlOpen` listener and route it inside the SPA.
      verify: a unit/integration test asserts the `appUrlOpen` handler parses a `lengua://...` URL into the right in-app route; on-device, opening a deep link lands on the expected screen.
      depends: 7.5.1

## 7.6 — Native plugins for v1  ·  M

_Context: the v1 plugin set from 04 — Local Notifications (daily reminder), Preferences/secure storage (tokens), Network (offline). All offline/on-device; no server, no FCM/APNs._

- [ ] **7.6.1** Add `@capacitor/preferences` (secure storage) and route Supabase token persistence through it on native, keeping web on its existing storage.
      verify: an integration test confirms the auth store reads/writes tokens via Preferences on native; on a real device, killing and relaunching the app keeps the user signed in.
- [ ] **7.6.2** Add `@capacitor/network` and surface an **offline state**: show a clean offline banner and disable generation/review submission while offline.
      verify: a test mocks the Network plugin offline and asserts the UI shows the offline banner and disables generate; toggling airplane mode on a real device reproduces it and recovers on reconnect.
- [ ] **7.6.3** Add `@capacitor/local-notifications` and implement a **permission prompt** flow (request once, handle granted/denied gracefully).
      verify: first launch on a real device shows the OS notification-permission prompt; a test asserts the app records the permission result and does not re-prompt when already decided.
- [ ] **7.6.4** Schedule the **daily review reminder** on-device when cards are due: compute due state locally, schedule a repeating daily local notification at a sensible time, and reschedule/cancel as due state changes — fully offline, no server.
      verify: a unit test asserts the scheduler creates a daily-repeating notification only when cards are due and cancels it when none are due; on a real device the notification fires at the scheduled time with airplane mode on (proving offline/no-server).
      depends: 7.6.3
- [ ] **7.6.5** Tapping the reminder notification deep-links into the **Review** screen.
      verify: a test asserts the notification-action handler routes to Review; on a real device, tapping the delivered reminder opens the app directly on the Review screen.
      depends: 7.6.4, 7.5.2

## 7.7 — OAuth in the native webview  ·  M

_Context: Google + Apple sign-in must complete inside Capacitor. Apple is mandatory on iOS because Google is offered. Needs Supabase redirect URLs for the app scheme and the `.p8`/Sign in with Apple config from 7.2._

- [ ] **7.7.1** Add the app-scheme **redirect URLs** to Supabase Auth (and the provider consoles) so the OAuth round-trip returns to `lengua://`/`com.lengua.app://` instead of a web URL.
      verify: the Supabase Auth "Redirect URLs" list includes the app scheme; Google/Apple provider configs accept it; a config test asserts the native client requests the app-scheme redirect.
      depends: 7.5.1
- [ ] **7.7.2** Implement the native OAuth flow (open the system browser / in-app browser, capture the `appUrlOpen` redirect, exchange the code, set the Supabase session).
      verify: on a real Android device, **Google** sign-in completes and returns to the app authenticated (session present); covered by an integration test of the redirect→exchange handler.
      depends: 7.7.1, 7.5.2, 7.6.1
- [ ] **7.7.3** Wire **Sign in with Apple** end-to-end using the Sign in with Apple key/Key ID configured in 7.2.
      verify: on a real iOS device, **Apple** sign-in completes and returns to the app authenticated; the resulting Supabase user shows the Apple identity provider.
      depends: 7.7.1, 7.2.1, 7.2.3
- [ ] **7.7.4** Verify token refresh + sign-out behave on native (refresh on expiry, full session clear on sign-out).
      verify: an integration test forces an expired access token and asserts a silent refresh; on a real device, sign-out clears the Preferences-stored session and returns to the login screen.
      depends: 7.7.2, 7.6.1

## 7.8 — iOS signing & build  ·  M

_Context: certificates + provisioning profile for `com.lengua.app`, archived and uploaded. Signing material lives as encrypted CI secrets (consider Fastlane match)._

- [ ] **7.8.1** Create the iOS **distribution certificate** and an App Store **provisioning profile** for `com.lengua.app` (enabling the Sign in with Apple capability).
      verify: Xcode's "Signing & Capabilities" resolves a valid distribution profile for `com.lengua.app` with Sign in with Apple enabled; an archive build signs without a provisioning error.
      depends: 7.1.6, 7.2.1
- [ ] **7.8.2** Store the iOS signing material (cert `.p12` + profile, or a **Fastlane match** repo + passphrase) as **encrypted CI secrets**.
      verify: `gh secret list` shows the iOS signing secrets; `git grep -iE "\.p12|\.mobileprovision"` over the repo finds no committed signing files.
- [ ] **7.8.3** Produce a signed iOS **archive/IPA** locally (or via Fastlane `gym`).
      verify: `xcodebuild -archivePath ... archive` (or `fastlane gym`) yields a signed `.ipa`; `codesign -dv` on the app reports the expected Team ID and `com.lengua.app`.
      depends: 7.8.1
- [ ] **7.8.4** Upload the signed iOS build to **TestFlight** (or `fastlane pilot`).
      verify: the build appears in App Store Connect → TestFlight as **Processed** and is installable via TestFlight on a real iOS device.
      depends: 7.8.3, 7.1.3

## 7.9 — Android signing & build  ·  M

_Context: an upload/release **keystore** stored as encrypted CI secrets; signed AAB to the Play internal track. Consider Fastlane `supply`._

- [ ] **7.9.1** Generate the Android release/upload **keystore** and store it (base64) plus its passwords as **encrypted CI secrets**.
      verify: `gh secret list` shows the keystore + password secrets; `git status`/`git grep -i "\.jks\|\.keystore"` confirm no keystore file is committed.
- [ ] **7.9.2** Configure Gradle release signing to read the keystore + passwords from env/CI secrets (never hardcoded).
      verify: `cd apps/web/android && ./gradlew :app:assembleRelease` produces a signed APK when secrets are present and fails clearly when absent; the release `build.gradle` contains no plaintext passwords (grep check).
      depends: 7.9.1, 7.3.3
- [ ] **7.9.3** Produce a signed Android **App Bundle (AAB)**.
      verify: `./gradlew :app:bundleRelease` yields an `.aab`; `bundletool`/`jarsigner -verify` confirms it is signed with the upload key.
      depends: 7.9.2
- [ ] **7.9.4** Upload the signed AAB to the Play **internal testing** track (or `fastlane supply`).
      verify: the build shows up on the Play Console internal testing track and is installable from the internal-test opt-in link on a real Android device.
      depends: 7.9.3, 7.1.4

## 7.10 — Signed CI build pipeline  ·  M

_Context: fold the signed mobile builds into the release pipeline from 05 (release tag/promote → Fastlane → TestFlight/Play track), reusing the CI signing secrets above. Consider Fastlane to automate build + upload._

- [ ] **7.10.1** Add a CI workflow that, on a release tag/promote, builds the **signed iOS** archive on a macOS runner using the CI signing secrets and uploads to TestFlight.
      verify: triggering the release workflow produces a green run and a new build appears in TestFlight without any local machine involved.
      depends: 7.8.2, 7.8.4
- [ ] **7.10.2** Add a CI job that builds the **signed Android AAB** using the keystore CI secrets and uploads to the Play internal track.
      verify: the release workflow's Android job is green and a new build lands on the Play internal track automatically.
      depends: 7.9.1, 7.9.4
- [ ] **7.10.3** Gate the mobile build/upload jobs on the **release/promote** event (not every PR) so PRs stay fast and store builds are deliberate.
      verify: opening a normal PR does not trigger the mobile upload jobs (CI run shows them skipped); a release tag does trigger them.
      depends: 7.10.1, 7.10.2

## 7.11 — OTA live updates (Capgo/OSS)  ·  M

_Context: ship web-layer fixes without a store review cycle, on **per-environment channels**; native/plugin changes still go through the stores._

- [ ] **7.11.1** Integrate an OTA web-bundle update plugin (e.g. **Capgo**, OSS/free) into the app and register the update check on launch/resume.
      verify: the OTA plugin appears in `package.json` + native projects and `cap sync` succeeds; the app logs an update-check on launch against the OTA backend.
      depends: 7.3.4
- [ ] **7.11.2** Configure **per-environment channels** (e.g. `staging`, `production`) so a build subscribes to the channel matching its API env.
      verify: a staging build reports it is subscribed to the `staging` channel and a prod build to `production` (visible in the OTA dashboard / an in-app debug readout).
      depends: 7.11.1
- [ ] **7.11.3** Publish a web-bundle update to a **test channel** and confirm it reaches a device.
      verify: bump a visible string, publish the bundle to the test channel, and a device on that channel picks up the new bundle on next launch/resume **without** reinstalling from the store.
      depends: 7.11.2
- [ ] **7.11.4** Add an OTA publish step to the release pipeline that pushes the web bundle to the **prod** channel on prod promote, keeping native changes on the store track.
      verify: a prod promote run publishes the web bundle to the production OTA channel (green job), and the OTA dashboard shows the new version on `production`.
      depends: 7.11.2, 7.10.3

## 7.12 — Real-device validation & mobile UX fixes  ·  M

_Context: the headline of the phase — install on real iOS + Android hardware and run the full loop against prod, fixing mobile-specific RTL/keyboard/layout/webview issues (a known risk for diacritics/harakat/nikkud)._

- [ ] **7.12.1** Install and run the app on a **real iOS device** and complete the full **Generate→Review→Discover** loop against prod.
      verify: on the physical iOS device, signing in and running generate→save→review→discover all succeed against the prod API (screen recording attached).
      depends: 7.8.4, 7.7.3, 7.4.5
- [ ] **7.12.2** Install and run the app on a **real Android device** and complete the full loop against prod.
      verify: on the physical Android device, the full generate→save→review→discover loop succeeds against the prod API (screen recording attached).
      depends: 7.9.4, 7.7.2, 7.4.5
- [ ] **7.12.3** Verify **RTL + diacritics** rendering in the mobile webview: Arabic/Hebrew direction, harakat/nikkud, and the vowel-marks toggle render correctly, and **tap-a-word** respects RTL word boundaries on touch.
      verify: on both real devices, an Arabic and a Hebrew card render right-to-left with correct vowel marks and tapping a word opens the correct explanation popover (screenshots attached).
      depends: 7.12.1, 7.12.2
- [ ] **7.12.4** Fix mobile **keyboard & layout** issues: the on-screen keyboard does not cover inputs (word entry, Discover topic), safe-area insets are respected, and scroll/viewport behave with the keyboard open.
      verify: on both real devices, focusing the word-entry and Discover inputs keeps the field visible above the keyboard and no content is hidden behind the notch/home indicator (recordings attached).
      depends: 7.12.1, 7.12.2
- [ ] **7.12.5** Confirm the **429 / daily-limit** and offline states render correctly in the native webview (not just web).
      verify: forcing a quota 429 and toggling offline on both real devices shows the friendly "daily limit reached" and offline UIs without layout breakage.
      depends: 7.12.1, 7.12.2, 7.6.2

---

## Phase 7 exit gate

Phase 7 is DONE only when all of these hold:

- [ ] `cap sync` succeeds and the synced native projects build — verify: `pnpm mobile:sync` exits 0 and both `cap sync ios` and `cap sync android` complete without error (7.3.4).
- [ ] A **signed iOS** build installs and runs the full loop against prod on a **real device** — verify: the TestFlight build installs on a physical iOS device and completes generate→review→discover against the prod API (7.8.4, 7.12.1).
- [ ] A **signed Android** build installs and runs the full loop against prod on a **real device** — verify: the Play internal-track build installs on a physical Android device and completes the full loop against prod (7.9.4, 7.12.2).
- [ ] **OAuth completes inside the native webview** for Google and Apple — verify: Google sign-in returns authenticated on a real Android device and Apple sign-in on a real iOS device (7.7.2, 7.7.3).
- [ ] The **daily review reminder fires** on-device, offline, and opens Review — verify: with cards due and airplane mode on, the scheduled local notification fires and tapping it opens the Review screen (7.6.4, 7.6.5).
- [ ] An **OTA update reaches a test channel** without a store cycle — verify: a published web bundle on the test channel is picked up by a device on next launch with no store reinstall (7.11.3).
- [ ] **RTL/diacritics and keyboard/layout** are correct in the mobile webview — verify: Arabic/Hebrew cards render RTL with correct vowel marks, tap-a-word works, and the keyboard never covers inputs on both real devices (7.12.3, 7.12.4).
- [ ] every task above merged via a green PR with the quality gate held (≥80% coverage, E2E).
