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
| `audio_mode` | `transcript` \| `both` \| `audio` | Leave out. Default `transcript` (the bot works from the transcript). The other two are for the model team's experiments. |
| `include_stats` | bool | Leave out. Adds a timing/tokens `stats` event used by the demo page. |

Existing fields (`message`, `session_id`, `top_k`, `category`, `service`, `subservice`, `payload`) are unchanged.
Through the gateway they are `message`, `sessionKey`, `topK`, `category`, `service`, `subservice`, `payload`.

### Voice

- Format: **WAV, PCM 16-bit, mono**. The demo page records at **16 000 Hz**; do the same. Anything else answers
  `Send the voice message as a WAV recording.`
- Length: at least 0.3 s and at most `max_audio_seconds` (30). At 16 kHz mono 16-bit, 30 s is about 960 KB, so about 1.3 MB
  as base64.
- Recording UX: tap the mic to start, tap again (or reach the limit) to send. There is no hold-to-talk.
- The bot never sees the audio file itself unless `audio_mode` is changed; it transcribes it first.

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
| `transcript` | `{"text": "<what was said>"}` | Voice message understood | Replace the placeholder in the customer's bubble with this text (see UI below). |
| `image` | `{"text": "<what the image shows>"}` | Image read | Show it as a small caption under the customer's bubble, so they can check it. |
| `stats` | `{"server_ms", "llm_ms", "llm_calls", "prompt_tokens", "completion_tokens", "context_tokens", "context_window", "model"}` | Only with `include_stats` | Ignore. |

Sequence for a voice turn: `transcript` → `token`… → `result` → `done`. A parser that ignores unknown event names (the
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
{"image_input": true, "max_image_mb": 5, "audio_input": true, "max_audio_seconds": 30}
```

Show the attach button only when `image_input` is true and the mic only when `audio_input` is true. If the call fails, hide
both. Voice and image are off in any environment where `LLM_AUDIO_INPUT` / `LLM_IMAGE_INPUT` are not set to `true`, and they
need a model that reads audio and images (Gemma4 on vLLM does; Ollama's `llama3.1:8b` does not).

---

## 5. Not part of the mobile app: internet-banking gateway (Java)

The mobile app talks to `POST /support/v1/ai/chat`, not to the chatbot. Voice and image do not work end to end until the
`support` service passes the new fields on. These are backend changes for that team; the app work in section 6 does not
include them.

1. `AiChatRequest`: add `image`, `audio` and `audioMode`; allow an empty `message` when `audio` is present (it is
   `@NotBlank` today, so a voice-only turn is rejected).
2. `RagChatClient.streamChat`: add `image`, `audio` and `audio_mode` to the upstream body (it builds a fixed list of keys).
3. Add `GET /support/v1/ai/capabilities` that proxies `GET /chat/capabilities` (with the API key).
4. Raise the request-body limit in Spring and the ingress: about 1.3 MB for a 30 s voice message, about 6.7 MB for a 5 MB image.
5. `AiChatServiceImpl.relay` already forwards events by name, so `transcript`, `image` and `stats` need no change.

---

## 6. Mobile app work (`user_app/lib/features/polygon_ai`)

Do these in order; each is a small, separately testable step.

| # | Step | Files |
|---|---|---|
| 1 | New stream events `AiTranscriptEvent`, `AiImageEvent`; parse `transcript` and `image` | `domain/entity/ai_stream_event.dart`, `data/repo_impl/ai_sse_stream_parser.dart` |
| 2 | Send `image` and `audio` (and allow an empty `message` with `audio`) | `domain/repo/polygon_ai_repository.dart`, `domain/usecase/stream_polygon_ai_chat_use_case.dart`, `data/repo_impl/polygon_ai_http_impl.dart`, the public chat repo/use case, the `PolygonAiStreamCall` typedef |
| 3 | Capabilities: `AiCapabilities` model, `getCapabilities()`, URL `polygonAiCapabilitiesUrl` (`/support/v1/ai/capabilities`) | `domain/entity/ai_capabilities.dart`, repo, `core/data/http/urls/polygon_ai_api_urls.dart` and its implementation |
| 4 | Controller: capabilities, pending image, voice recording state, `sendVoice`, transcript and image events | `presentation/controller/polygon_ai_chat_controller_base.dart` |
| 5 | Voice recorder (the `record` package, 16 kHz mono WAV) | `presentation/voice/ai_voice_recorder.dart`, `pubspec.yaml`, Android and iOS permissions |
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

// voice: a finished recording
Future<void> sendVoice(String wavDataUrl) => _runTurn('', audio: wavDataUrl, display: '🎤 Voice message');

// events
case AiTranscriptEvent(:final text):   // replace the placeholder in the user bubble just before the reply
  messages[assistantIndex - 1] = messages[assistantIndex - 1].copyWith(content: '🎤 “$text”');
case AiImageEvent(:final text):        // caption on the user bubble
  messages[assistantIndex - 1] = messages[assistantIndex - 1].copyWith(imageCaption: text);
```

`_runTurn` forwards `image` and `audio` to the stream call. A Retry of a voice or image turn resends the same request, so
keep `audio` and `image` in the stored retryable request.

### UI to build

```
Composer, nothing attached
┌──────────────────────────────────────────────┐
│ [🖼] Ask Polygon AI...                [🎤] [↑]│
└──────────────────────────────────────────────┘
 🖼 only when capabilities.image_input   🎤 only when capabilities.audio_input

Image attached                      Recording
┌──────────────────────────────┐    ┌──────────────────────────────┐
│ [thumb] photo.jpg        [✕] │    │ ● Listening… 0:07     [■ Stop]│
└──────────────────────────────┘    └──────────────────────────────┘
```

| Element | Behaviour |
|---|---|
| Attach button | Opens the gallery picker (`image_picker`). Downscale to 1280 px on the longer side, JPEG 0.85, check the size against `max_image_mb`; show a snackbar if it is too big. Shows a thumbnail tray above the input with a remove (✕) button. |
| Send with a picture | Sends the typed text (or "Please look at this image.") plus the picture; the picture appears in the customer's bubble. |
| Mic button | First tap asks for the microphone permission, then starts recording; the input row shows a red dot, a running timer and a Stop button. Second tap (or reaching `max_audio_seconds`) stops and sends. Ignore recordings under 0.5 s. Disable the mic and attach buttons while `isSending`. |
| Voice bubble | The customer's bubble first shows `🎤 Voice message`; when `transcript` arrives it becomes `🎤 “<text>”`. If the turn fails, it stays as the placeholder with the normal failed/retry state. |
| Image caption | Small secondary text under the customer's bubble: `Image read as: <text>`. |
| Permissions | Android `RECORD_AUDIO`; iOS `NSMicrophoneUsageDescription`. The photo library permission already exists. |

### Acceptance checks

1. English, Bangla and Banglish messages each get a reply in the right language (see the table in section 1).
2. A 5-second voice message in Bangla shows `🎤 “…”` in the customer's bubble and gets a Bangla reply.
3. A voice message under 0.3 s or with silence shows the matching error text and offers Retry.
4. With `capabilities` failing or both flags false, neither button is shown, and typed chat still works.
5. An image of a failed-transfer screen shows the caption and the bot's reply refers to what it shows.
6. The pre-login public chat shows neither button.
7. `transcript`, `image` and `stats` frames do not break a build that has not been updated yet.

## Known gaps

1. Voice and image exist only in the backend and the demo web page so far. They have not been run against the Flutter app,
   and they need the gateway changes in section 5.
2. Reply language quality for Banglish and for mixed English–Bangla messages depends on the model (Gemma4); spot-check
   long or very informal messages.
3. The language of a reply to a bare `yes`/`no`/number is taken from earlier turns, but the data-answer path (`balance`,
   transactions) does not pass earlier turns, so a lone number can answer in the default English.
