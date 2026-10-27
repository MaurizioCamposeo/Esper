# Esper: an instrument for recall

The user named Esper after the instrument in *Blade Runner*. The project is
also inspired by a Ted Chiang story about an instrument for recalling images
from the past. The exact story title has not been confirmed; do not attribute
one by guesswork.

The interface should feel like a personal memory-retrieval instrument:

- Natural-language search is the primary activity and the main call to action.
- Use black, white, and grayscale in both dark and light themes.
- Optical framing, fine rules, focus marks, and quiet monospace typography give
  structure to the interface. Keep actual document content readable.
- The recall viewer uses archive images and their stored dates, with selectable
  frames that open the corresponding document. Do not invent telemetry or
  present decorative numbers as system measurements.
- Use a short focus/scan transition when recalling an image, slow optical-ring
  movement, and brief document reveals. Support the system reduced-motion
  preference and the persistent animation pause control.
- Preserve archive browsing, document states, tags, previews, import, and deletion.
- The user approved the optical concept and requested a more minimal reading
  experience: remove repeated slogans, protocol captions, decorative identifiers,
  and explanatory copy that repeats an obvious action. Keep the main prompt,
  concise search examples, navigation, file metadata, and useful error messages.
- Typography must be comfortably readable: about 14px for navigation and file
  names, 16–17px for the search input, 15px for document passages, and 11–12px
  for secondary metadata. Avoid shrinking controls and labels on mobile.
- The frontend still uses mock data. The design does not implement real backend
  search, image enhancement, or a lifelogging system.

## Generated demonstration photograph

Asset: `public/demo/memory-coast.png`.

Created using the built-in image generation tool on 2026-10-27. This is a
fictional, AI-generated demonstration photograph, used in the mock archive's
coastal image example. It is not a user's memory or an authenticated photograph
of a named location. The original SVG sample remains available in `art.ts`.
No external image service is requested at runtime.

Final generation prompt:

> Use case: photorealistic-natural. Asset type: a sample archive photograph inside Esper, a monochrome futuristic personal-memory retrieval web application. Create only the photograph, no UI mockup. Scene: a quiet Mediterranean rocky coast seen from a seaside overlook at dusk, a single distant anonymous person seen from behind standing near the water, sea horizon dissolving into pale atmospheric mist, low sun reflected in water, dark rocky silhouette in foreground. A credible candid everyday memory, contemplative, slightly ambiguous, cinematic black-and-white 35mm film photography with restrained grain, strong blacks, soft silver midtones, luminous atmospheric depth, subtle imperfect archival texture. Landscape framing, subject and horizon readable in a small 2:1 crop. The mood should feel like revisiting a long-forgotten moment through an optical instrument, with understated near-future cinematic sensibility. Strictly monochrome grayscale. No text, no letters, no frame, no graphic overlays, no interface, no logos, no watermark, no neon, no spaceships, no robots. Generate a single landscape photo.
