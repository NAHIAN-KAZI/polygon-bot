# VOICE, IMAGE AND LANGUAGE — Integration Handoff

What changed in the chat endpoint for the mobile app, beyond the per-intent handoffs:

1. **Reply language.** The bot answers in the customer's language.
2. **Voice messages.** The customer records a message; the bot turns it into text and answers it like typed text.
3. **Image messages.** The customer attaches a picture; the bot reads it into text and answers.
4. **Capabilities.** One call tells the app whether voice and image are switched on.

Read `COMMON.md` first. Everything in the per-intent handoffs (result types, payloads, boxes) is unchanged: a voice
or image message ends up as ordinary text, so it produces the same `result` events as a typed one.

---

## 1. Reply language

| The customer writes | The bot replies in |
|---|---|
| English | English |
| Bangla in Bengali script (`আমার ব্যালেন্স কত?`) | Bangla (Bengali script) |
| Banglish — Bangla typed in English letters (`amar balance koto`) | **Bangla in Bengali script**, never Banglish |
| Voice message | The language that was spoken, by the same rule (the transcript is Bengali script for spoken Bangla) |
| A reply with no language of its own (`yes`, `500`, a name) | The language of the customer's earlier messages |

What the app has to know:

- The decision is made by the bot per message. The app sends nothing about language and must not translate.
- Amounts, masked numbers and names stay exactly as in the data, with digits 0–9 (`Tk 57,762.77`, `••••0056`).
  Numbered lists in a Bangla reply may use Bengali digits (`১.`, `২.`); that is only list numbering.
- The text bubble must render Bengali script. Flutter falls back to the platform font for glyphs the app font lacks
  (Noto Sans Bengali on Android, Kohinoor Bangla on iOS); check a Bangla reply on a real Android and iOS device and add
  a `fontFamilyFallback` only if glyphs are missing.
- The app's own text (box labels, buttons, banners, the greeting) follows the app's language, not the bot's. A Bangla
  bubble next to an English box is expected.
- The single fixed text, shown when the model is unreachable, is bilingual:
  `Sorry, I'm having trouble right now. Please try again in a moment.` and
  `দুঃখিত, এখন একটু সমস্যা হচ্ছে। অনুগ্রহ করে কিছুক্ষণ পরে আবার চেষ্টা করুন।`
- Match on `result.type`, `category`, `service` and `payload`, never on the bubble text, which varies by language.

---

## 2. Request — new fields on `POST /chat`

| Field | Type | Notes |
|---|---|---|
| `audio` | string | A voice message as a data URL: `data:audio/wav;base64,<base64>`. See "Voice" below. |
| `image` | string | An image as a data URL: `data:image/png|jpeg|webp|gif;base64,<base64>`. At most `max_image_mb` (5). |
| `message` | string | Still the typed text. With `audio` it may be empty or omitted; any text typed next to the recording is kept in front of the transcript. Maximum 4000 characters. |
| `audio_mode` | `transcript` \| `both` \| `audio` \| `nemo` | **The mobile app always sends `"nemo"`**: the recording is turned into text by Titu STT, a Bangla speech-to-text model on its own server, and that text is then answered like typed text. The app shows the transcript in the customer's own bubble (see UI below). Default (if left out) is `transcript`; `both` and `audio` are the language model's own modes, used by the demo page. |
| `include_stats` | bool | Leave out. Adds a timing/tokens `stats` event used by the demo page. |

Existing fields (`message`, `session_id`, `top_k`, `category`, `service`, `subservice`, `payload`) are unchanged.
Through the gateway they are `message`, `sessionKey`, `topK`, `category`, `service`, `subservice`, `payload`.

### Voice

- Format: **WAV, PCM 16-bit, mono**. The demo page records at **16 000 Hz**; do the same. Anything else answers
  `Send the voice message as a WAV recording.`
- Length: at least 0.3 s and at most `max_audio_seconds` (30). At 16 kHz mono 16-bit, 30 s is about 960 KB, so about 1.3 MB
  as base64.
- Recording UX: tap the mic to start, tap again (or reach the limit) to send. There is no hold-to-talk.
- With `audio_mode: "nemo"` (the mobile app's mode) the chatbot sends the recording to the Titu STT server (`STT_URL`),
  which returns Bangla text, and answers that text. Every later step (checks that quote the customer's own words, the reply
  and its language, follow-ups on the next message) works on the text, so a voice turn is checked like a typed one. Typed
  text sent with the recording is kept in front of the transcript.
- Titu is trained on Bangla. English words come out transliterated into Bangla script, so mixed English–Bangla speech is
  read less well than by the language-model modes.
- The mode exists only where the STT server is set up. Without it the chatbot does not list `nemo` in `voice_modes`
  (section 4) and the app must not show the mic; sending `nemo` anyway answers an error.

### Image

- Downscale before sending: the demo page limits the longer side to 1280 px and sends JPEG at quality 0.85.
- The bot reads the image into one to three sentences (visible amounts, bank names, error text; card numbers, PINs and
  OTPs are written as `[hidden]`). With no typed text, the question is "Please look at this image."
- Image and voice can be sent in the same turn.

---

## 3. Response — new SSE events

The stream is unchanged (`token`, `result`, `done`, `error`) plus two events that arrive **before the first `token`**
and one optional event before `done`.

| Event | `data` | When | What the app does |
|---|---|---|---|
| `transcript` | `{"text": "<what was said>"}` | Every voice turn except `audio_mode` `audio` | Show it in the customer's own voice bubble, replacing the `🎤 Voice message` placeholder, so they can see whether they were understood. |
| `image` | `{"text": "<what the image shows>"}` | Image read | Show it as a small caption under the customer's bubble, so they can check it. |
| `stats` | `{"server_ms", "llm_ms", "llm_calls", "prompt_tokens", "completion_tokens", "context_tokens", "context_window", "model"}` | Only with `include_stats` | Ignore. |

Sequence for a voice turn in the app's `nemo` mode: `transcript` → `token`… → `result` → `done`. A parser that ignores unknown event names (the
Polygon AI parser does) stays safe if it does not handle them yet.

### Errors

A failed voice or image turn sends one `error` event and then ends. `detail` is a sentence safe to show:

| `detail` | Cause |
|---|---|
| `Send the voice message as a WAV recording.` | Not a WAV data URL |
| `The voice message couldn't be read.` | Bad base64 or WAV header |
| `Voice messages can be at most 30 seconds.` | Too long |
| `The voice message was too short. Hold the mic button and speak.` | Under 0.3 s (the wording says "hold"; the app taps) |
| `I couldn't hear anything in that voice message. Please try again.` | Silence |
| `Voice input isn't enabled for this assistant.` | `audio_input` is false |
| `The voice message couldn't be heard right now.` | Model failure |
| `Attach a PNG, JPEG, WebP or GIF image.` | Not an image data URL |
| `The image is larger than 5 MB.` | Too big |
| `The attached image couldn't be read.` | Bad base64 or unreadable |
| `Image input isn't enabled for this assistant.` | `image_input` is false |
| `The attached image couldn't be read right now.` | Model failure |

Show these through the app's existing error path (snackbar plus the failed bubble); a retry resends the same request.

---

## 4. `GET /chat/capabilities`

Needs the API key like `/chat`. Response:

```json
{"image_input": true, "max_image_mb": 5, "audio_input": true,
 "voice_modes": ["both", "transcript", "audio", "nemo"], "max_audio_seconds": 30, "read_aloud": false}
```

Show the attach button only when `image_input` is true, and the mic only when `voice_modes` contains `"nemo"` (the mode the
app sends). `audio_input` means something else (the language model itself hears audio) and is not used for the mic;
`read_aloud` is for the demo page. If the call fails, or `voice_modes` is missing, hide the mic.

Picture input is off unless `LLM_IMAGE_INPUT=true` and needs a model that reads images (Gemma4 on vLLM does; Ollama's
`llama3.1:8b` does not). The app's voice mode is off unless `STT_URL` points at a running Titu STT server (`stt_service/`,
on a GPU box).

---

## 5. Internet-banking gateway (Java, `support` service)

The mobile app talks to `POST /support/v1/ai/chat`, not to the chatbot, so the `support` service has to pass the new
fields on. **Done on the internet-banking `Chatbot-ui` branch** (commits `1640f97f` and `65d7eee1`, 18 tests passing in a
Java 25 Maven container):

1. `AiChatRequest` takes `image`, `audio` and `audioMode`. `message` may be empty when `audio` is present. `image` and
   `audio` must be inline data URLs (`data:image/(png|jpeg|webp|gif);base64,…`, `data:audio/wav;base64,…`); links and
   `file:` URLs are rejected. `audioMode` must be `transcript`, `both`, `audio` or `nemo`.
2. `RagChatClient.streamChat` forwards `image`, `audio` and `audio_mode` upstream, and leaves out an empty `message`.
3. `GET /support/v1/ai/capabilities` (customer JWT) proxies `GET /chat/capabilities`. When the assistant is off or the
   chatbot is unreachable it answers `{"image_input":false,"max_image_mb":5,"audio_input":false,"max_audio_seconds":30}`
   instead of an error.
4. The pre-login chat (`/support/v1/ai/public/chat`) refuses voice and picture messages with an SSE `error` frame:
   `Voice and picture messages are available after you sign in.`
5. `AiChatServiceImpl.relay` already forwards events by name, so `transcript`, `image` and `stats` need no change.
6. Request size: the dev nginx allows 20 MB and the local one 10 MB, enough for a 5 MB picture (about 6.7 MB as base64) and a
   30 s voice message (about 1.3 MB). Check any other ingress in front of `support` for a smaller body limit.

## 6. Mobile app work (`user_app/lib/features/polygon_ai`)

Do these in order; each is a small, separately testable step.

| # | Step | Files |
|---|---|---|
| 1 | New stream events `AiTranscriptEvent`, `AiImageEvent`; parse `transcript` and `image` | `domain/entity/ai_stream_event.dart`, `data/repo_impl/ai_sse_stream_parser.dart` |
| 2 | Send `image` and `audio` (and allow an empty `message` with `audio`) | `domain/repo/polygon_ai_repository.dart`, `domain/usecase/stream_polygon_ai_chat_use_case.dart`, `data/repo_impl/polygon_ai_http_impl.dart`, the public chat repo/use case, the `PolygonAiStreamCall` typedef |
| 3 | Capabilities: `AiCapabilities` model, `getCapabilities()`, URL `polygonAiCapabilitiesUrl` (`/support/v1/ai/capabilities`) | `domain/entity/ai_capabilities.dart`, repo, `core/data/http/urls/polygon_ai_api_urls.dart` and its implementation |
| 4 | Controller: capabilities, pending image, voice recording state, `sendVoice`, transcript and image events | `presentation/controller/polygon_ai_chat_controller_base.dart` |
| 5 | Voice recorder (the `record` package, 16 kHz mono WAV, sent with `audio_mode: nemo`) | `presentation/media/ai_voice_recorder.dart` and `presentation/media/ai_image_picker.dart`, `pubspec.yaml`, Android and iOS permissions |
| 6 | Composer: attach button, image tray, mic button with recording state | `presentation/widgets/polygon_ai_composer.dart` |
| 7 | Bubbles: voice placeholder, image caption | `presentation/widgets/polygon_ai_message_bubble.dart`, `domain/entity/ai_chat_message_item.dart` |
| 8 | Tests | `test/features/polygon_ai/` |

### Controller contract

```dart
// state
final Rxn<AiCapabilities> capabilities = Rxn<AiCapabilities>();   // null until loaded / on failure -> hide buttons
final RxnString pendingImage = RxnString();                          // data URL of the attached picture
final RxBool isRecording = false.obs;

// send: typed text, optional picture
Future<void> send() async {
  final text = inputController.text.trim();
  final image = pendingImage.value;
  if ((text.isEmpty && image == null) || isSending.value) return;
  ...
  await _runTurn(text.isEmpty ? 'Please look at this image.' : text, image: image);
}

// voice: a finished recording, transcribed by Titu STT on the server (the request carries audio_mode: "nemo")
Future<void> sendVoice(String wavDataUrl) => _runTurn('', audio: wavDataUrl, display: '🎤 Voice message');

// events
case AiTranscriptEvent(:final text):   // what Titu heard, shown in the customer's bubble
  messages[assistantIndex - 1] = messages[assistantIndex - 1].copyWith(content: '🎤 “$text”');
case AiImageEvent(:final text):        // caption on the user bubble
  messages[assistantIndex - 1] = messages[assistantIndex - 1].copyWith(imageCaption: text);
```

`_runTurn` forwards `image` and `audio` to the stream call. A Retry of a voice or image turn resends the same request, so
keep `audio` and `image` in the stored retryable request.

### UI to build

The composer follows the messenger layout: attach on the left, the text box in the middle, **one action button on the right
that changes with what the customer is doing**.

```
Empty                          Typing / picture attached        Recording
[📎] [ Ask Polygon AI…   ] [🎤]   [📎] [ Hello, my card… ] [➤]    [🗑] [ ● 0:07 / 0:30  Recording… tap ➤ to send ] [➤]
 📎 only if image_input         🎤 turns into ➤                   📎 turns into the trash; ➤ stops and sends
 🎤 only if voice_modes has nemo

Picture attached (above the row)        Attach sheet (tap 📎)
┌─────────────────────────────────┐     ┌──────────────────────────────┐
│ [thumb] photo.jpg           [✕] │     │ 🖼  Photo library            │
│         Ready to send           │     │     Send a picture from your │
└─────────────────────────────────┘     │     gallery                  │
 hint becomes "Add a message             │ 📷  Camera                   │
 (optional)"                             │     Take a picture now       │
                                         └──────────────────────────────┘
```

| State | Left button | Middle | Right button |
|---|---|---|---|
| Nothing typed, voice available | 📎 attach (if pictures are on) | Text box, hint `Ask Polygon AI...` | 🎤 mic: starts recording |
| Nothing typed, no voice (and the pre-login chat) | 📎 if pictures are on, else none | Text box | ➤ send, dimmed and disabled |
| Right after a voice message was transcribed (until the customer sends anything else) | 📎 | Text box | ⚡ quick actions: replaces the mic |
| Text typed, or a picture attached | 📎 | Text box (hint `Add a message (optional)` with a picture) | ➤ send, filled in the primary colour |
| Recording | 🗑 discard (red-tinted): throws the recording away | Red pulsing dot, `0:07 / 0:30`, `Recording… tap ➤ to send` | ➤ stop and send |
| Reply being fetched | 📎 disabled | Text box | Spinner, not tappable |

| Element | Behaviour |
|---|---|
| ⚡ Quick actions | Shown where the mic normally is from the moment a voice message's `transcript` arrives until the customer sends anything else or starts a new chat; only when the chat has quick replies (the signed-in chat: Balance, My cards, Recent transactions, Transfer money, Fees). Tapping it opens a sheet listing those as one-tap messages, plus **Record another voice message** so voice is never lost. Typed text or a picture still turns the button into ➤ send. |
| Action button | Switches with a short scale-and-fade animation, with a light haptic tick on send and a medium one on starting or ending a recording. Every button is 44 × 44 and has a tooltip. The rules are one pure function, `aiComposerAction(hasText, hasPicture, isRecording, isSending, voiceAvailable, quickActions)`. |
| Attach button | One button left of the text box (a paperclip). Hidden unless `image_input` is on. Opens a bottom sheet: **Photo library** and **Camera**. Disabled while a reply is being fetched. Documents (PDF, Word) are not offered: the chatbot cannot read them. |
| Picture | Downscale to 1280 px on the longer side, JPEG 0.85, check the size against `max_image_mb`; show a snackbar if it is too big. A tray above the input shows the thumbnail, the name, `Ready to send` and a remove (✕) button. |
| Voice message | Mic starts recording after asking for the microphone permission on first use (`Allow microphone access to send a voice message.` if refused). Stopping with ➤ (or reaching `max_audio_seconds`) sends. Under 1 s is dropped with `That was too short. Tap the mic and speak a little longer.` Send is not available while recording. |
| Send with a picture | Sends the typed text (or "Please look at this image.") plus the picture; the picture appears in the customer's bubble. |
| Voice bubble | The customer's bubble first shows `🎤 Voice message`; when the `transcript` event arrives it becomes `🎤 “<what was heard>”`. If the turn fails before that, it keeps the placeholder with the normal failed/retry state. |
| Image caption | Small secondary text under the customer's bubble: `Image read as: <text>`. |
| Permissions | Android `RECORD_AUDIO`; iOS `NSMicrophoneUsageDescription`. The photo library permission already exists. |

### Acceptance checks

1. English, Bangla and Banglish messages each get a reply in the right language (see the table in section 1).
2. A 5-second voice message in Bangla shows `🎤 “…”` with the heard text in the customer's bubble and gets a Bangla reply.
3. A voice message under 0.3 s or with silence shows the matching error text and offers Retry.
4. With `capabilities` failing or both flags false, neither button is shown, and typed chat still works.
5. An image of a failed-transfer screen shows the caption and the bot's reply refers to what it shows.
6. The pre-login public chat shows neither button.
7. `transcript`, `image` and `stats` frames do not break a build that has not been updated yet.
8. The request body of a voice turn carries `"audio_mode": "nemo"`, and the mic is hidden when `voice_modes` lacks `nemo`.

## Known gaps

1. Voice and image have been exercised only through the demo web page and unit tests. The Flutter side compiles, analyses
   cleanly and its tests pass (Flutter 3.44.4), but nobody has recorded a voice message or attached a picture on a real
   device, and the gateway has not been run against a live chatbot.
2. Titu STT (`nemo`, the mobile app's mode) has not been tried from the app and needs its STT server running (`STT_URL`).
   Check a few spoken banking requests in Bangla and in mixed English–Bangla, including a yes/no answer to a confirmation.
   Keep the STT port reachable only from the chatbot host, with `STT_API_KEY` set: customer voice is sent there.
3. Reply language quality for Banglish and for mixed English–Bangla messages depends on the model (Gemma4); spot-check
   long or very informal messages.
4. The language of a reply to a bare `yes`/`no`/number is taken from earlier turns, but the data-answer path (`balance`,
   transactions) does not pass earlier turns, so a lone number can answer in the default English.
