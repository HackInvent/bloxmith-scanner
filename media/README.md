# Scanner artwork

This illustration belongs to the BloxSmith industrial pixel-art block family.
It communicates the block's function; it is not a screenshot of Studio or a
promise of additional runtime features.

## Files

- `cover.png`: original square PNG cover, preserved without retouching.
- `thumbnail.webp`: 320 × 320 WebP derivative for README and catalog cards.
- Accent: Cyan / teal.
- Meaning: An installed physical scanner produces an image-based PDF. No OCR, text extraction or AI document analysis is implied.

The module's silhouette, viewpoint, light, framing and steel/graphite housing are
shared with the other pilot blocks. A large roof symbol and a single English title
provide identification without relying only on color. Descriptive alt text must
accompany the image wherever it is rendered.

These are documentation assets, not executable UI assets. Their presence does
not automatically register them in Studio or the public compatibility catalog.
The block version and runtime contract remain unchanged.

## Provenance

Created on 2026-09-27 with the built-in image generation tool, using owner-supplied
visual references. No image API key or CLI fallback was used.
The generated Audio Mixer cover is the family anchor. Use the cover from the companion HackInvent/bloxmith-audio-mixer repository as the input reference.

The selected generated PNG was copied byte for byte. Only the thumbnail was
resized and encoded; no text, recoloring or compositing was applied afterwards.
The artwork is distributed under this repository's [Apache-2.0 license](../LICENSE).

Thumbnail export with ImageMagick:

```sh
convert media/cover.png -thumbnail 320x320 -strip -quality 88 -define webp:method=6 media/thumbnail.webp
```

## Generation prompt

The following is the exact prompt used for the selected cover. Generation is
not deterministic; retain this selected cover as the reference for future edits.

```text
Use case: stylized-concept.
Asset type: square cover illustration for the Scanner hardware-integration block in the BloxSmith catalog.
Input image: the Audio Mixer cube is the exact family reference. Retain its cube proportions, front/top/right three-quarter viewpoint, position, square framing, white backdrop, corner reinforcements, housing materials, restrained pixel-art technique and upper-left lighting. Create the Scanner variant, not an audio device.
Subject changes: replace all orange accents with restrained cyan/teal light while keeping charcoal/graphite housing and steel corner reinforcements. Change the roof display to one LARGE luminous document-page symbol surrounded by four scan-corner brackets. Replace the front upper title with exactly "SCANNER" in crisp white uppercase pixel lettering. The main front panel presents a large simple flatbed scanner pictogram: a partially raised lid, a white sheet on the glass and a horizontal cyan scan beam, leading via a small arrow to ONE folded-corner digital document icon. Keep the actual scanner pictogram large and recognizable, clearly not a printer ejecting paper. Below it, two or three simple understated controls, using a scan button glyph, a color/grayscale symbol and a resolution grid. No labels. The side face uses sparse generic device/data connectors and a cyan light strip.
Semantic truth: the software block scans using an already installed physical SANE scanner and outputs an image-based PDF. It does NOT perform OCR, text extraction, translation, AI analysis, field detection, document classification or printing. Show no extracted text, AI symbols, brains or categorized files.
Composition: one single complete cube, identical visual scale and margins to the reference. One square image, no collage. Keep its plain near-white background and subtle grounded shadow. Match the title plate placement and visual hierarchy. The roof document symbol and front scanner must be identifiable at 320 px.
Style: premium crisp industrial pixel-art illustration, deliberately stepped edges, controlled pixel clusters and tactile metal, no photorealism, no excessive neon, no decorative clutter.
Text (verbatim): "SCANNER" exactly once, and no other words, fake text, subtitles, slogans, version numbers, watermarks, logos or labels.
Avoid: all waveforms, faders, audio connectors, orange accents, robots, cats, people, desks, floating props, detached devices and any OCR claims.
```
