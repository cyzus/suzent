# Play Console answers

Answers for **Policy and programs → App content** and the release forms,
checked against the Android build that drops the Google code scanner (first
shipped after 0.5.3). Re-check them when the manifest or dependencies change.

## Privacy policy

https://suzent.com/mobile-privacy

No change needed: the app has no analytics or tracking SDKs, which matches the
policy and the Data safety answers below.

## App access

**All or some functionality is restricted.** Add one instruction set:

- Name: Offline demo
- No username or password
- Instructions: the review notes below.

> Suzent is a companion client for a user's self-hosted Suzent desktop app.
> To explore without a desktop, open the app and tap "Try offline demo" at the
> bottom of the connection screen (if already paired: Settings → About → Try
> offline demo). The demo uses scripted, on-device sample data and calls no AI
> service. On the start page, tap "Plan my Lisbon weekend" for a streamed
> example reply, or "Tidy up my Downloads folder" to allow or reject a
> simulated command. Settings offers Reset demo and Exit demo. Real pairing
> with a desktop is shown in this video: <PAIRING VIDEO LINK>

## Ads

No, the app does not contain ads.

## Content rating (IARC questionnaire)

- Category: **All other app types** (not a game, not social, not a news app)
- Violence, sexuality, language, controlled substances, gambling: **No**
- User-generated content shared with other users: **No** (conversations stay
  between one user and their own desktop)
- Shares user location with others: **No**
- Allows purchases of digital goods: **No**
- Unrestricted internet access: **Yes** (in-app links open in Custom Tabs, and
  the agent can return arbitrary web content)

Expected result: roughly PEGI 3 / Everyone, with the "unrestricted internet"
interactive element noted.

## Target audience and content

- Target age groups: **18 and over** only. Picking younger groups pulls the
  app into the Families policy.
- Appeals to children: **No**

## Data safety

The developer receives nothing and no SDK sends data off the device. Messages
and attachments go only to the user's own desktop, which Google does not count
as collection by the developer. QR pairing uses the bundled ZXing scanner, not
the Google code scanner, so ML Kit telemetry does not apply.

| Question | Answer |
| --- | --- |
| Does your app collect or share any of the required user data types? | **No** |

That answer skips the rest of the form, and the listing shows **No data
collected**, matching the iOS "Data Not Collected" label.

## Generative AI apps

Play's [AI-Generated Content policy](https://support.google.com/googleplay/android-developer/answer/13985936)
requires apps whose central feature is an AI chatbot to let users report or
flag offensive output **inside the app**. Suzent replies come from the user's
own backend and provider, but a reviewer sees a chat app, so expect this to be
enforced. The Android build has no report action today; add one before the
production review (for example a "Report response" item in the message
actions that opens a prefilled email to support@suzent.com).

## Other declarations

| Form | Answer |
| --- | --- |
| Government apps | No |
| Financial features | None |
| Health apps | None |
| News apps | No |
| COVID-19 contact tracing and status | No |
| Account deletion | Not applicable: the app has no accounts |
| Foreground services, background location, exact alarms, SMS/Call log, All files access | Not used, no declaration needed |
| Advertising ID | No (the merged release manifest has only `INTERNET` and `CAMERA`; recheck after dependency changes) |
| Camera permission | Declared in the manifest; used for QR pairing and photo attachments, no extra Play declaration |
