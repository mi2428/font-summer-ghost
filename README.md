# Summer Ghost

A Japanese monospace font designed for Ghostty.

- Blends [Ubuntu Mono](https://design.ubuntu.com/font) for Latin characters with Japanese glyphs based on [Circle M+](https://itouhiro.github.io/mixfont-mplus-ipa/mplus/) and [BIZ UDGothic](https://github.com/googlefonts/morisawa-biz-ud-gothic), supplemented by [IBM Plex Sans JP](https://github.com/IBM/plex/tree/master/packages/plex-sans-jp).
- Feels like a natural Japanese extension of the Ubuntu font family while intentionally delegating [Nerd Fonts](https://www.nerdfonts.com/) icons to Ghostty's built-in fallback, keeping character widths and box-drawing glyphs predictable.

Latin and Japanese glyphs are balanced instead of being forced into the same bounding box:

- **Grid:** UPM 1024 with 512-unit half-width and 1024-unit full-width cells.
- **Optical scale:** Ubuntu Mono ASCII is 103% vertically and 100% horizontally; adjusted Cyroit Japanese remains at 100%; direct BIZ UDGothic and IBM Plex Sans JP fallbacks are scaled to 87% and 90%, respectively.
- **Line metrics:** Ascent 850, descent 174, and line gap 0 produce an exact 1-em line height while keeping Latin, kana, and kanji visually aligned.
- **Terminal geometry:** Ubuntu Mono box-drawing and block-element glyphs remain unscaled so terminal UI lines retain their original weight and proportions.

## Installation

[uv](https://docs.astral.sh/uv/) is required. The first build downloads pinned upstream assets and verifies their SHA-256 digests.

```console
$ make install

download https://assets.ubuntu.com/v1/0cef8205-ubuntu-font-family-0.83.zip
download https://raw.githubusercontent.com/omonomo/Ubroit/v1.8.0/sourceFonts/Cyroit.nopatch/Cyroit-Regular.nopatch.ttf
download https://raw.githubusercontent.com/omonomo/Ubroit/v1.8.0/sourceFonts/Cyroit.nopatch/Cyroit-Bold.nopatch.ttf
download https://github.com/googlefonts/morisawa-biz-ud-gothic/releases/download/v1.051/BIZUDGothic.zip
download https://raw.githubusercontent.com/IBM/plex/ceee82fa88781b8310b198fd302480efaeac609e/packages/plex-sans-jp/fonts/complete/ttf/unhinted/IBMPlexSansJP-Regular.ttf
download https://raw.githubusercontent.com/IBM/plex/ceee82fa88781b8310b198fd302480efaeac609e/packages/plex-sans-jp/fonts/complete/ttf/unhinted/IBMPlexSansJP-Bold.ttf

=== Regular ===
wrote    SummerGhost-Regular.ttf: 16,683 codepoints, IBM fallback 3,684, UVS 9,689

=== Bold ===
wrote    SummerGhost-Bold.ttf: 16,683 codepoints, IBM fallback 3,684, UVS 9,689

=== Italic ===
wrote    SummerGhost-Italic.ttf: 16,683 codepoints, IBM fallback 3,684, UVS 9,689

=== BoldItalic ===
wrote    SummerGhost-BoldItalic.ttf: 16,683 codepoints, IBM fallback 3,684, UVS 9,689
wrote    dist/provenance.json
ok       SummerGhost-Regular.ttf: 16,683 codepoints, 16,781 glyphs, 6 selectors
ok       SummerGhost-Bold.ttf: 16,683 codepoints, 16,781 glyphs, 6 selectors
ok       SummerGhost-Italic.ttf: 16,683 codepoints, 16,786 glyphs, 6 selectors
ok       SummerGhost-BoldItalic.ttf: 16,683 codepoints, 16,786 glyphs, 6 selectors
validated Summer Ghost Regular/Bold/Italic/BoldItalic
Installed Summer Ghost into ~/Library/Fonts
```

Configure Ghostty to use the family:

```ini
font-family = Summer Ghost
```

Run `make help` to see the available commands and how to override the installation directory.

## License

Summer Ghost contains font software covered by the Ubuntu Font Licence 1.0 and the SIL Open Font License 1.1.
