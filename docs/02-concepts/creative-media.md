# Video and speech

Creative tools include image generation/editing, video generation and speech.
Enable `VideoGenerationTool`, `VideoStatusTool` and `SpeakTool` in the tool picker.

## Video

Configure **Settings → Model Roles → Video generation** with a LiteLLM video
model. Refresh model capabilities to discover models whose upstream mode is
`video_generation`, or enter a custom model ID. This role does not inherit the
chat model. Model-specific duration, size and reference-image limits still apply.

`generate_video(prompt, seconds?, size?, image_path?)` submits a paid provider job
and returns a `job_id`. Reference images are local files of up to 20 MB.
`check_video(job_id)` queries progress and downloads a completed result as MP4.
Wait at least 10 seconds between checks. Job records persist in the project
`videos/` directory and are scoped to the originating chat. A new process can
resume checks; there is no background polling while Suzent is closed. Provider
retention limits still apply. Retry **check_video**, not generation, after a
transient status/download error. After an ambiguous submission timeout, inspect
provider jobs before resubmitting to avoid duplicate charges.

Example: “Generate an 8-second landscape video of mist moving through a forest.
Check its progress, then show the finished video.” For image-to-video, attach an
image and ask to use that image as the reference.

Completed videos appear outside the activity rail at the point they were
retrieved, with playback controls. Later tools start another rail segment.

## Speech

**Settings → Voice & audio** saves the API speech model and global defaults together.
Model Roles shows a TTS summary linking to this page. Gemini and OpenAI models
provide built-in voice suggestions and model-specific controls; unknown/custom
providers retain a manual voice ID field. Changing models resets the voice and
incompatible options before Save. Each `speak`
call may override engine, voice, speed, volume, language, pitch, output format,
and `prompt` (tone/style instructions).

- **System**: no API or TTS model required. Uses a local voice
  installed on the device viewing the message. Supports voice, language, speed,
  pitch and volume. Install a system voice if none are available. This mode does
  not export audio or interpret style instructions. Voice availability depends on the device/webview.
- **API**: uses the TTS model role and provider credentials; saves audio in the
  project's `audio/` directory for replay. Supports provider voice IDs, speed,
  format and style instructions. Pitch/language overrides apply to system speech
  only. Volume controls playback. Auto format uses WAV for Gemini and MP3 for
  other providers. Gemini style instructions are included in its text prompt;
  numeric speed and formats other than WAV are rejected before generation because
  this adapter supports WAV and prompt-based pacing for Gemini. Gemini audio
  requests carry the configured credentials directly, bypassing LiteLLM’s speech
  bridge. Other models may impose their own limits.

New speech results in the current chat play automatically by default. System and
API speech share a queue and provide Stop and Replay controls. Disable
**Automatically play new tool speech** in Voice settings for manual playback.
History loading, refresh, chat switches and repeated stream snapshots do not
replay earlier results. Switching chats stops playback and clears the queue.
If device/browser autoplay is blocked, click Play to retry.

An existing TTS role defaults to API speech until voice settings are saved;
otherwise the default is system speech. System and API voices use different IDs.

Examples:

- “Read this in Chinese using system speech, speed 0.9, pitch 1.1.”
- “Generate API speech with voice alloy, as a WAV file, in a calm tone.”

The `speak` tool now returns playable results in chat instead of opening the
backend server's speaker device. Hardware voice-node playback is unchanged.

Specialist role recommendations require a configured provider (credentials for
API services, explicitly enabled models for keyless local services). Unconfigured
providers are excluded without deleting existing role assignments. This checks
configuration, not account/model access, and does not make verification requests.
