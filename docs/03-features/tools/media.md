---
sidebar_position: 10
title: Images, video & speech
description: Generate and edit images, read pictures, make videos, and have the agent speak, plus the models each one needs.
---

# Images, video & speech

These tools sit in the **Creative** group of the tool picker. Each one runs on
its own specialist model, so assign that model first in
**Settings → Model Roles** (see [Model roles](../../04-models/model-roles.md)).

| You want to | Model role it uses | Asks for approval | Saved to |
|---|---|---|---|
| Generate an image | **Image Generation** | Yes | `images` folder |
| Edit an image | **Image Editing** | Yes | `images` folder |
| Read or describe an image | **Vision** | No | Nothing saved |
| Create a video | **Video generation** | Yes, when it is submitted | `videos` folder |
| Speak text aloud | None (System) or **TTS** (API) | No | `audio` folder (API only) |

Folders are inside the conversation's
[project library](../filesystem.md#where-files-go), so every conversation in
the project can reuse the files. Image generation and editing are on by default;
the agent can switch on the others when a task needs them. Approvals follow your
[permission mode](./human-in-the-loop.md).

## Images

Ask for a picture and the agent generates it, up to four at a time. To change an
existing image, attach it and describe the edit. The agent can combine up to 16
reference images and use a PNG mask to limit the edit to one area, if your model
supports it. Each input image can be up to 20 MB. Results appear in the chat and
can be edited again.

## Reading images

If your chat model can see images, pictures you attach go straight to it. If it
can't, the chat shows a note that the images were not sent, and the agent looks
at them with its image-reading tool instead. That tool uses the **Vision**
model, which falls back to **Primary** when Primary can see images. With
neither, the tool reports that no Vision model is set.

## Video

Assign a **Video generation** model, then ask, for example, "Generate an
8-second landscape video of mist moving through a forest." Video is a paid, slow
job: the agent submits it, checks back on its progress, and shows the finished
video in the chat. To animate a picture, attach it and ask to use it as the
reference image; your video model must support this.

## Speech

Choose how the agent speaks in **Settings → Voice & audio**, under
**Speech engine**:

- **System speech (no API)** uses the voices installed on the device playing the
  message. No model or API key is needed, but the audio can't be saved, and it
  only plays in the Suzent chat window, not in [chat apps](../../05-chat-apps/README.md).
- **API speech** uses your **TTS** model and saves audio you can replay. Pick the
  model under **Speech model** on the same page. Voices, formats, speed, and
  style instructions depend on the provider.

New speech plays automatically. Turn off **Automatically play new tool speech**
if you prefer to press **Play** yourself.

The **Creative** group also holds the tool for sending messages through your
[chat apps](../../05-chat-apps/README.md), which also needs approval.
